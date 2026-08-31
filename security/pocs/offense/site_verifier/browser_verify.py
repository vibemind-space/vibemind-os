"""
Browser Scanner & Verification Module
=======================================
Uses Playwright (headless Chromium) for:
1. Full network traffic capture (XHR, fetch, WebSocket, third-party)
2. Console output capture (errors, CSP violations, stack traces)
3. Browser storage scan (localStorage, sessionStorage secrets)
4. Cookie audit after JS execution (JS-set cookies without flags)
5. Mixed content detection (HTTP resources on HTTPS)
6. Finding verification (paths, XSS, login pages)
7. Screenshot evidence

Called after the fast Python scan + auto-investigation, before LLM report generation.
"""

import asyncio
import base64
import json
import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright


# Patterns for secrets in storage/network
_SECRET_PATTERNS = re.compile(
    r'(eyJ[A-Za-z0-9-_]{20,}\.eyJ[A-Za-z0-9-_]{20,})'  # JWT
    r'|(AIza[0-9A-Za-z\-_]{35})'  # Google API Key
    r'|(sk_live_[0-9a-zA-Z]{24,})'  # Stripe Live
    r'|(AKIA[0-9A-Z]{16})'  # AWS Access Key
    r'|(?:password|passwd|secret|token|api_key)\s*[:=]\s*["\']([^"\']{8,})["\']',  # Generic
    re.IGNORECASE
)

_SESSION_COOKIE_NAMES = re.compile(
    r'(sess|session|sid|phpsessid|jsessionid|token|auth|jwt|csrf|xsrf|_id)',
    re.IGNORECASE
)


async def browser_verify(url: str, scan_results: dict) -> dict:
    """
    Full browser scan + finding verification.

    Args:
        url: Target URL
        scan_results: Dict with all scan result dicts

    Returns:
        Dict with network traffic, console output, storage secrets,
        cookie audit, verification results, and screenshot evidence.
    """
    result = {
        # Verification (existing)
        "verified_paths": [],
        "debunked_paths": [],
        "verified_xss": [],
        "debunked_xss": [],
        "verified_login": [],
        "screenshots": [],
        # NEW: Browser scan data
        "network": {
            "total_requests": 0,
            "third_party_requests": [],
            "api_calls": [],
            "mixed_content": [],
            "websocket_urls": [],
            "large_responses": [],
            "failed_requests": [],
        },
        "console": {
            "errors": [],
            "warnings": [],
            "csp_violations": [],
        },
        "storage": {
            "localStorage_secrets": [],
            "sessionStorage_secrets": [],
            "localStorage_size": 0,
            "sessionStorage_size": 0,
        },
        "cookies_after_js": [],
        "issues": [],
        "summary": "",
    }

    parsed = urlparse(url)
    target_domain = parsed.netloc.lower()
    base_domain = ".".join(target_domain.split(".")[-2:])  # e.g. "lovable.dev"

    print("  [BROWSER] Starting headless Chromium...", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        # =========================================================
        # SETUP: Network & Console listeners
        # =========================================================
        all_requests = []
        failed_requests = []
        console_messages = []
        ws_urls = []

        def on_request(request):
            all_requests.append({
                "url": request.url[:500],
                "method": request.method,
                "resource_type": request.resource_type,
                "is_third_party": base_domain not in request.url.lower(),
            })

        def on_request_failed(request):
            failed_requests.append({
                "url": request.url[:300],
                "method": request.method,
                "failure": request.failure or "unknown",
            })

        def on_console(msg):
            entry = {
                "type": msg.type,
                "text": msg.text[:500],
            }
            console_messages.append(entry)

        def on_websocket(ws):
            ws_urls.append(ws.url[:300])

        page.on("request", on_request)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        page.on("websocket", on_websocket)

        # =========================================================
        # PHASE 1: Load homepage, capture everything
        # =========================================================
        print("  [BROWSER] Loading page + capturing traffic...", flush=True)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)  # Let JS execute + lazy-load fire

            homepage_title = await page.title()
            homepage_screenshot = await page.screenshot(full_page=False)
            result["screenshots"].append({
                "name": "homepage",
                "base64_png": base64.b64encode(homepage_screenshot).decode(),
                "description": f"Homepage: {homepage_title}",
            })
        except Exception as e:
            print(f"  [BROWSER] Homepage load failed: {e}", flush=True)
            await browser.close()
            return result

        # =========================================================
        # PHASE 2: Analyze captured network traffic
        # =========================================================
        print(f"  [BROWSER] Analyzing {len(all_requests)} network requests...", flush=True)
        result["network"]["total_requests"] = len(all_requests)

        for req in all_requests:
            req_url = req["url"]
            req_url_lower = req_url.lower()

            # Third-party requests
            if req["is_third_party"] and req["resource_type"] in ("xhr", "fetch", "script", "image", "stylesheet"):
                domain = urlparse(req_url).netloc
                result["network"]["third_party_requests"].append({
                    "domain": domain,
                    "url": req_url[:200],
                    "type": req["resource_type"],
                })

            # API calls (XHR/fetch)
            if req["resource_type"] in ("xhr", "fetch"):
                result["network"]["api_calls"].append({
                    "url": req_url[:300],
                    "method": req["method"],
                    "is_third_party": req["is_third_party"],
                })

            # Mixed content (HTTP on HTTPS page)
            if parsed.scheme == "https" and req_url.startswith("http://"):
                result["network"]["mixed_content"].append({
                    "url": req_url[:300],
                    "type": req["resource_type"],
                })

        result["network"]["websocket_urls"] = ws_urls
        result["network"]["failed_requests"] = failed_requests[:20]

        # Deduplicate third-party domains
        seen_tp = set()
        deduped_tp = []
        for tp in result["network"]["third_party_requests"]:
            if tp["domain"] not in seen_tp:
                seen_tp.add(tp["domain"])
                deduped_tp.append(tp)
        result["network"]["third_party_requests"] = deduped_tp

        # =========================================================
        # PHASE 3: Console analysis
        # =========================================================
        for msg in console_messages:
            text = msg["text"]
            if msg["type"] == "error":
                result["console"]["errors"].append(text[:300])
                # Check for CSP violations
                if "content security policy" in text.lower() or "csp" in text.lower():
                    result["console"]["csp_violations"].append(text[:300])
            elif msg["type"] == "warning":
                result["console"]["warnings"].append(text[:300])

        result["console"]["errors"] = result["console"]["errors"][:20]
        result["console"]["warnings"] = result["console"]["warnings"][:20]

        # =========================================================
        # PHASE 4: Browser storage scan
        # =========================================================
        print("  [BROWSER] Scanning browser storage...", flush=True)
        try:
            storage_data = await page.evaluate("""() => {
                const result = {
                    localStorage: {},
                    sessionStorage: {},
                    localStorageSize: 0,
                    sessionStorageSize: 0,
                };
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        const val = localStorage.getItem(key);
                        result.localStorage[key] = val ? val.substring(0, 500) : '';
                        result.localStorageSize += (val || '').length;
                    }
                } catch(e) {}
                try {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        const val = sessionStorage.getItem(key);
                        result.sessionStorage[key] = val ? val.substring(0, 500) : '';
                        result.sessionStorageSize += (val || '').length;
                    }
                } catch(e) {}
                return result;
            }""")

            result["storage"]["localStorage_size"] = storage_data.get("localStorageSize", 0)
            result["storage"]["sessionStorage_size"] = storage_data.get("sessionStorageSize", 0)

            # Scan for secrets in localStorage
            for key, val in storage_data.get("localStorage", {}).items():
                matches = _SECRET_PATTERNS.findall(val)
                key_is_sensitive = _SESSION_COOKIE_NAMES.search(key)
                if matches or key_is_sensitive:
                    masked = val[:15] + "..." if len(val) > 15 else val
                    result["storage"]["localStorage_secrets"].append({
                        "key": key,
                        "value_preview": masked,
                        "length": len(val),
                        "has_pattern_match": bool(matches),
                        "sensitive_key_name": bool(key_is_sensitive),
                    })

            # Scan for secrets in sessionStorage
            for key, val in storage_data.get("sessionStorage", {}).items():
                matches = _SECRET_PATTERNS.findall(val)
                key_is_sensitive = _SESSION_COOKIE_NAMES.search(key)
                if matches or key_is_sensitive:
                    masked = val[:15] + "..." if len(val) > 15 else val
                    result["storage"]["sessionStorage_secrets"].append({
                        "key": key,
                        "value_preview": masked,
                        "length": len(val),
                        "has_pattern_match": bool(matches),
                    })

        except Exception as e:
            print(f"  [BROWSER] Storage scan failed: {e}", flush=True)

        # =========================================================
        # PHASE 5: Cookie audit after JS execution
        # =========================================================
        print("  [BROWSER] Auditing cookies (post-JS)...", flush=True)
        try:
            cookies = await context.cookies()
            for cookie in cookies:
                is_session = bool(_SESSION_COOKIE_NAMES.search(cookie["name"]))
                issues = []
                if not cookie.get("secure", False):
                    issues.append("Missing Secure flag")
                if not cookie.get("httpOnly", False):
                    issues.append("Missing HttpOnly flag")
                if cookie.get("sameSite", "None") == "None":
                    issues.append("SameSite=None (cross-site)")
                if cookie.get("expires", -1) > 0:
                    import time
                    remaining = cookie["expires"] - time.time()
                    if remaining > 86400 * 365:
                        issues.append(f"Expires in {int(remaining/86400)} days")

                if issues or is_session:
                    result["cookies_after_js"].append({
                        "name": cookie["name"],
                        "domain": cookie.get("domain", ""),
                        "secure": cookie.get("secure", False),
                        "httpOnly": cookie.get("httpOnly", False),
                        "sameSite": cookie.get("sameSite", "?"),
                        "is_session": is_session,
                        "issues": issues,
                        "path": cookie.get("path", "/"),
                    })
        except Exception:
            pass

        # =========================================================
        # PHASE 6: Verify exposed paths (existing logic)
        # =========================================================
        paths_result = scan_results.get("paths", {})
        found_paths = paths_result.get("found_paths", [])
        critical_paths = [p for p in found_paths if p.get("severity") in ("CRITICAL", "HIGH") and p.get("status") == 200]

        if critical_paths:
            print(f"  [BROWSER] Verifying {len(critical_paths)} exposed paths...", flush=True)

        for path_info in critical_paths[:10]:
            path = path_info["path"]
            full_url = urljoin(url, path)
            try:
                resp = await page.goto(full_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(500)
                status = resp.status if resp else 0
                current_title = await page.title()
                body_text = await page.evaluate("() => document.body?.innerText?.substring(0, 1000) || ''")

                is_real = True
                reason = ""

                if current_title == homepage_title:
                    is_real = False
                    reason = f"Same title as homepage ({homepage_title})"
                elif status == 404:
                    is_real = False
                    reason = "Server returned 404"
                elif "not found" in body_text.lower()[:200]:
                    is_real = False
                    reason = "Page shows 'not found' message"
                else:
                    reason = f"Unique content (title: {current_title[:50]})"

                entry = {"path": path, "status": status, "is_real": is_real, "reason": reason, "page_title": current_title[:100]}

                if is_real:
                    result["verified_paths"].append(entry)
                    screenshot = await page.screenshot(full_page=False)
                    result["screenshots"].append({
                        "name": f"path_{path.replace('/', '_').strip('_')}",
                        "base64_png": base64.b64encode(screenshot).decode(),
                        "description": f"VERIFIED: {path} -- {reason}",
                    })
                    print(f"  [BROWSER]   REAL: {path} -- {reason}", flush=True)
                else:
                    result["debunked_paths"].append(entry)
                    print(f"  [BROWSER]   FAKE: {path} -- {reason}", flush=True)

            except Exception:
                result["debunked_paths"].append({"path": path, "is_real": False, "reason": "Browser error"})

        # =========================================================
        # PHASE 7: Verify XSS reflections (existing logic)
        # =========================================================
        xss_result = scan_results.get("xss", {})
        reflections = xss_result.get("reflections_found", [])

        if reflections:
            print(f"  [BROWSER] Verifying {len(reflections)} XSS reflections...", flush=True)

        for refl in reflections[:5]:
            vector_url = refl.get("url", "")
            vector_name = refl.get("vector_name", "")
            if not vector_url:
                continue

            try:
                xss_marker = f"XSSPROBE{id(refl) % 9999}"
                xss_payload = f"<img src=x onerror=window.__xss_{xss_marker}=1>"

                test_url = re.sub(r'XSSCANARY\d+', xss_payload, vector_url)

                await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)

                xss_fired = await page.evaluate(f"() => window.__xss_{xss_marker} === 1")
                body_html = await page.evaluate("() => document.body?.innerHTML?.substring(0, 5000) || ''")
                payload_in_dom = xss_payload in body_html
                encoded_in_dom = "&lt;img" in body_html and xss_marker in body_html

                if xss_fired:
                    severity = "CRITICAL"
                    reason = "XSS payload executed in browser"
                elif payload_in_dom:
                    severity = "HIGH"
                    reason = "Unencoded HTML injected into DOM"
                elif encoded_in_dom:
                    severity = "LOW"
                    reason = "Input reflected but HTML-encoded (safe)"
                else:
                    severity = None
                    reason = "Payload not reflected in rendered page"

                entry = {
                    "vector_name": vector_name, "url": test_url[:200],
                    "xss_fired": xss_fired, "payload_in_dom": payload_in_dom,
                    "encoded": encoded_in_dom, "severity": severity, "reason": reason,
                }

                if severity and severity in ("CRITICAL", "HIGH"):
                    result["verified_xss"].append(entry)
                    screenshot = await page.screenshot(full_page=False)
                    result["screenshots"].append({
                        "name": f"xss_{vector_name.replace(' ', '_')}",
                        "base64_png": base64.b64encode(screenshot).decode(),
                        "description": f"XSS VERIFIED: {vector_name} -- {reason}",
                    })
                    print(f"  [BROWSER]   XSS CONFIRMED: {vector_name} -- {reason}", flush=True)
                else:
                    result["debunked_xss"].append(entry)
                    print(f"  [BROWSER]   XSS FALSE POS: {vector_name} -- {reason}", flush=True)

            except Exception:
                result["debunked_xss"].append({"vector_name": vector_name, "reason": "Browser error"})

        # =========================================================
        # PHASE 8: Verify login pages (existing logic)
        # =========================================================
        login_result = scan_results.get("login", {})
        if login_result.get("login_page_found"):
            login_url = login_result.get("login_url", "")
            if login_url:
                print(f"  [BROWSER] Verifying login page...", flush=True)
                try:
                    await page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(1000)
                    has_password = await page.evaluate("() => document.querySelector('input[type=password]') !== null")
                    has_username = await page.evaluate("() => document.querySelector('input[type=text], input[type=email], input[name*=user], input[name*=login]') !== null")
                    has_submit = await page.evaluate("() => document.querySelector('button[type=submit], input[type=submit]') !== null")
                    is_real = has_password and (has_username or has_submit)
                    result["verified_login"].append({"url": login_url, "is_real": is_real, "has_password_field": has_password, "has_username_field": has_username})
                    if is_real:
                        screenshot = await page.screenshot(full_page=False)
                        result["screenshots"].append({
                            "name": "login_page",
                            "base64_png": base64.b64encode(screenshot).decode(),
                            "description": f"Login page verified",
                        })
                        print(f"  [BROWSER]   LOGIN REAL: password field + form found", flush=True)
                    else:
                        print(f"  [BROWSER]   LOGIN FAKE: no real login form", flush=True)
                except Exception:
                    pass

        # =========================================================
        # GENERATE ISSUES from browser findings
        # =========================================================
        # Mixed content
        if result["network"]["mixed_content"]:
            mc = result["network"]["mixed_content"]
            result["issues"].append({
                "severity": "HIGH",
                "category": "Mixed Content",
                "title": f"{len(mc)} HTTP resource(s) loaded on HTTPS page",
                "description": f"Insecure resources: {', '.join(m['url'][:80] for m in mc[:5])}. Attackers can intercept or modify these.",
                "fix": "Ensure all resources use HTTPS URLs.",
            })

        # Storage secrets
        all_storage_secrets = result["storage"]["localStorage_secrets"] + result["storage"]["sessionStorage_secrets"]
        if all_storage_secrets:
            keys = ", ".join(s["key"] for s in all_storage_secrets[:5])
            result["issues"].append({
                "severity": "HIGH",
                "category": "Browser Storage",
                "title": f"Sensitive data in browser storage: {keys}",
                "description": f"{len(all_storage_secrets)} secret(s) found in localStorage/sessionStorage. These are accessible to any XSS payload.",
                "fix": "Move sensitive data to httpOnly cookies or server-side sessions. Never store tokens in localStorage.",
            })

        # JS-set cookies without security flags
        insecure_session_cookies = [c for c in result["cookies_after_js"] if c["is_session"] and c["issues"]]
        if insecure_session_cookies:
            names = ", ".join(c["name"] for c in insecure_session_cookies[:5])
            result["issues"].append({
                "severity": "HIGH",
                "category": "Cookie Security (Browser)",
                "title": f"JS-set session cookies without security flags: {names}",
                "description": f"{len(insecure_session_cookies)} session cookie(s) set by JavaScript lack Secure/HttpOnly/SameSite flags. These are vulnerable to XSS theft.",
                "fix": "Set cookies server-side with Secure, HttpOnly, and SameSite=Strict flags.",
            })

        # Console errors
        if result["console"]["csp_violations"]:
            result["issues"].append({
                "severity": "MEDIUM",
                "category": "CSP Violations",
                "title": f"{len(result['console']['csp_violations'])} Content Security Policy violation(s)",
                "description": f"CSP blocked resources: {result['console']['csp_violations'][0][:150]}...",
                "fix": "Review and update CSP to allow required resources or remove unauthorized ones.",
            })

        # Third-party tracking
        tp_domains = list(set(tp["domain"] for tp in result["network"]["third_party_requests"]))
        if len(tp_domains) > 10:
            result["issues"].append({
                "severity": "LOW",
                "category": "Privacy",
                "title": f"{len(tp_domains)} third-party domains contacted",
                "description": f"The page contacts {len(tp_domains)} external domains: {', '.join(tp_domains[:10])}...",
                "fix": "Review third-party integrations. Minimize external dependencies for privacy compliance (GDPR).",
            })

        # =========================================================
        # SUMMARY
        # =========================================================
        verified_count = len(result["verified_paths"]) + len(result["verified_xss"])
        debunked_count = len(result["debunked_paths"]) + len(result["debunked_xss"])
        total_screenshots = len(result["screenshots"])
        n_issues = len(result["issues"])

        result["summary"] = (
            f"Browser scanned {len(all_requests)} network requests "
            f"({len(tp_domains)} third-party domains, "
            f"{len(result['network']['api_calls'])} API calls, "
            f"{len(result['network']['mixed_content'])} mixed content). "
            f"Console: {len(result['console']['errors'])} errors, "
            f"{len(result['console']['csp_violations'])} CSP violations. "
            f"Storage: {len(all_storage_secrets)} secret(s) found. "
            f"Cookies: {len(result['cookies_after_js'])} audited post-JS. "
            f"Verified {verified_count} findings, debunked {debunked_count}. "
            f"{n_issues} new issues found. {total_screenshots} screenshots."
        )

        print(f"  [BROWSER] Requests: {len(all_requests)} ({len(tp_domains)} third-party)", flush=True)
        print(f"  [BROWSER] Console: {len(result['console']['errors'])} errors, {len(result['console']['csp_violations'])} CSP violations", flush=True)
        print(f"  [BROWSER] Storage secrets: {len(all_storage_secrets)}", flush=True)
        print(f"  [BROWSER] Cookies (post-JS): {len(result['cookies_after_js'])} ({len(insecure_session_cookies)} insecure session)", flush=True)
        if result["network"]["mixed_content"]:
            print(f"  [BROWSER] MIXED CONTENT: {len(result['network']['mixed_content'])} HTTP resources!", flush=True)
        if result["network"]["websocket_urls"]:
            print(f"  [BROWSER] WebSockets: {len(result['network']['websocket_urls'])}", flush=True)
        print(f"  [BROWSER] Done: {verified_count} verified, {debunked_count} debunked, {n_issues} new issues, {total_screenshots} screenshots", flush=True)

        await browser.close()

    return result
