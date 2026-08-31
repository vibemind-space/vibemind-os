"""
Security Scanner MCP Server
=============================
Exposes the security scanner as an MCP server with high-level tools.
Can be used from Claude Code, other agents, or any MCP client.

Usage:
  # stdio (for Claude Code integration):
  python mcp_server.py

  # HTTP (for web/API access):
  python mcp_server.py --http --port 8088
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

# Import scanner tools
from tools import (
    site_fingerprint, whois_lookup, check_ssl_cert, dns_records,
    http_headers, page_content_scan, security_audit,
    robots_sitemap_scan, subdomain_enum, cors_check, port_scan,
    path_discovery, cms_version_detect, login_security_check,
    xss_reflection_check, sqli_check, open_redirect_check,
    http_methods_check, js_secrets_scanner, email_spoofing_test,
    waf_detection, rate_limit_check, dns_zone_transfer, breach_check,
    tls_cipher_suite_grading, cookie_security_audit,
    api_endpoint_discovery, dependency_cve_scan,
    subdomain_takeover_check, secret_validator,
    source_map_check, csp_analyzer, smart_crawl,
    dynamic_injection_test, clickjacking_test,
    subdomain_content_scan, advanced_xss_probe,
    evolutionary_xss_fuzzer, spa_api_discovery, advanced_sqli_test,
    spa_xss_test, auth_security_test, business_logic_test,
    juice_shop_benchmark, juice_shop_exploit_suite,
    sqli_data_extraction, credential_crack, credential_reuse_test,
    session_hijack_test, data_exfiltration, token_harvest,
    nosql_injection_test, xxe_exploitation, ssrf_exploitation,
    auto_pivot, generate_attack_report,
)
from attack_chain import run_attack_chain
from evasion import obfuscate_payload

# Scan history storage
HISTORY_DIR = Path(__file__).parent / ".scan_history"
HISTORY_DIR.mkdir(exist_ok=True)


mcp = FastMCP(
    "Security Scanner",
    instructions=(
        "Security scanning and website analysis tools. "
        "Use 'scan' for a full adaptive security audit, "
        "'quick_scan' for a fast overview, "
        "'fingerprint' to identify site type, "
        "or individual tools for targeted checks."
    ),
)


def _domain(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return urlparse(url).netloc or url


def _url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _save_scan(domain: str, scan_type: str, result: dict):
    """Save scan result to history."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = domain.replace(".", "_").replace(":", "_")
    path = HISTORY_DIR / f"{safe_domain}_{scan_type}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    return str(path)


def _load_last_scan(domain: str, scan_type: str) -> dict | None:
    """Load the most recent scan for a domain."""
    safe_domain = domain.replace(".", "_").replace(":", "_")
    pattern = f"{safe_domain}_{scan_type}_*.json"
    files = sorted(HISTORY_DIR.glob(pattern), reverse=True)
    if files:
        with open(files[0], encoding="utf-8") as f:
            return json.load(f)
    return None


# ================================================================
# HIGH-LEVEL TOOLS
# ================================================================

@mcp.tool()
async def scan(url: str):
    """
    Full adaptive security scan of a website.
    Fingerprints the site first, then runs only relevant checks.
    Returns a structured summary with all findings.

    Args:
        url: Target URL (e.g. https://example.com)
    """
    url = _url(url)
    domain = _domain(url)

    # Phase 1: Fingerprint
    fp = await site_fingerprint(url)

    # Phase 2: Base checks
    whois_r, ssl_r, dns_r, headers_r, content_r, audit_r = await asyncio.gather(
        whois_lookup(domain), check_ssl_cert(domain), dns_records(domain),
        http_headers(url), page_content_scan(url), security_audit(url),
    )

    # Phase 3: Adaptive extended checks
    checks = {
        "robots": robots_sitemap_scan(url),
        "subdomain": subdomain_enum(domain),
        "cors": cors_check(url),
        "port": port_scan(domain),
        "methods": http_methods_check(url),
        "js_secrets": js_secrets_scanner(url),
        "email": email_spoofing_test(domain),
        "waf": waf_detection(url),
        "tls_grade": tls_cipher_suite_grading(domain),
        "cookie": cookie_security_audit(url),
        "source_maps": source_map_check(url),
        "clickjacking": clickjacking_test(url),
        "crawl": smart_crawl(url),
        "csp": csp_analyzer(url, headers_r),
    }

    # Skip irrelevant checks based on fingerprint
    if fp["site_type"] != "SPA":
        checks["paths"] = path_discovery(url)
        checks["cms"] = cms_version_detect(url)
        checks["login"] = login_security_check(url)
        checks["ratelimit"] = rate_limit_check(url)

    if fp["site_type"] != "CMS_WORDPRESS":
        checks["api"] = api_endpoint_discovery(url)

    checks["xss"] = xss_reflection_check(url)
    checks["sqli"] = sqli_check(url)
    checks["cve"] = dependency_cve_scan(url)
    checks["breach"] = breach_check(domain)

    names = list(checks.keys())
    results = await asyncio.gather(*checks.values(), return_exceptions=True)
    check_results = {}
    for name, res in zip(names, results):
        check_results[name] = res if not isinstance(res, Exception) else {"issues": [], "error": str(res)}

    # Collect all issues
    all_issues = list(audit_r.get("issues", []))
    for cr in check_results.values():
        if isinstance(cr, dict):
            all_issues.extend(cr.get("issues", []))

    # Collect SPA API discovery issues (from smart_crawl's SPA fallback)
    crawl_r = check_results.get("crawl", {})
    spa_r = crawl_r.get("spa_api_discovery", {})
    if spa_r:
        all_issues.extend(spa_r.get("issues", []))

    # Dynamic injection testing
    if crawl_r.get("parameters_found") or crawl_r.get("forms_found"):
        dyn_r = await dynamic_injection_test(url, crawl_r)
        all_issues.extend(dyn_r.get("issues", []))
        check_results["dynamic_injection"] = dyn_r

    # Advanced SQLi + XSS testing on discovered API endpoints (parallel)
    adv_sqli_r = {}
    if spa_r and spa_r.get("api_endpoints"):
        adv_sqli_r, spa_xss_r = await asyncio.gather(
            advanced_sqli_test(url, spa_r),
            spa_xss_test(url, spa_r),
        )
        all_issues.extend(adv_sqli_r.get("issues", []))
        all_issues.extend(spa_xss_r.get("issues", []))
        check_results["advanced_sqli"] = adv_sqli_r
        check_results["spa_xss"] = spa_xss_r

    # Auth + IDOR + JWT testing (uses SQLi results for token if available)
    auth_r = {}
    if spa_r and spa_r.get("api_endpoints"):
        auth_r = await auth_security_test(url, spa_r, adv_sqli_r)
        all_issues.extend(auth_r.get("issues", []))
        check_results["auth_security"] = auth_r

    # Business logic testing (path traversal, tampering, file exposure)
    if spa_r and spa_r.get("api_endpoints"):
        # Extract token from auth test if available
        auth_token = None
        for jwt_f in auth_r.get("jwt_findings", []):
            if jwt_f.get("type") == "jwt_decoded":
                # Try to get the actual token
                for bypass in adv_sqli_r.get("auth_bypass", []):
                    try:
                        data = json.loads(bypass.get("response_preview", "{}"))
                        auth_token = data.get("authentication", {}).get("token")
                    except Exception:
                        pass
        logic_r = await business_logic_test(url, spa_r, auth_token)
        all_issues.extend(logic_r.get("issues", []))
        check_results["business_logic"] = logic_r

    # Validate secrets
    js_secrets_r = check_results.get("js_secrets", {})
    if js_secrets_r.get("secrets_found"):
        val_r = await secret_validator(js_secrets_r["secrets_found"])
        all_issues.extend(val_r.get("issues", []))
        check_results["secret_validation"] = val_r

    # Count severities
    sev_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for iss in all_issues:
        sev = iss.get("severity", "INFO")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    # Build summary
    summary = {
        "url": url,
        "domain": domain,
        "fingerprint": fp,
        "score": audit_r.get("score", 0),
        "total_issues": len(all_issues),
        "severity_counts": sev_counts,
        "checks_run": len(check_results),
        "issues": all_issues,
        "tls_grade": check_results.get("tls_grade", {}).get("grade", "?"),
        "waf": check_results.get("waf", {}).get("waf_name", "none"),
        "subdomains_found": check_results.get("subdomain", {}).get("total_found", 0),
        "secrets_found": len(js_secrets_r.get("secrets_found", [])),
        "pages_crawled": crawl_r.get("pages_crawled", 0),
        "forms_found": len(crawl_r.get("forms_found", [])),
        "spa_endpoints": crawl_r.get("spa_endpoints_found", 0),
    }

    # Save to history
    _save_scan(domain, "full", summary)

    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
async def quick_scan(url: str):
    """
    Fast security overview (~30 seconds). Only base checks: WHOIS, SSL, DNS, headers, TLS grade.
    Use this for a quick first look before deciding on a full scan.

    Args:
        url: Target URL
    """
    url = _url(url)
    domain = _domain(url)

    fp, whois_r, ssl_r, dns_r, headers_r, audit_r, tls_r = await asyncio.gather(
        site_fingerprint(url),
        whois_lookup(domain),
        check_ssl_cert(domain),
        dns_records(domain),
        http_headers(url),
        security_audit(url),
        tls_cipher_suite_grading(domain),
    )

    summary = {
        "url": url,
        "domain": domain,
        "fingerprint": fp,
        "score": audit_r.get("score", 0),
        "tls_grade": tls_r.get("grade", "?"),
        "issues": audit_r.get("issues", []),
        "total_issues": len(audit_r.get("issues", [])),
        "ssl_valid": ssl_r.get("cert_expired") == False,
        "ssl_issuer": ssl_r.get("cert_issuer", "?"),
        "spf": dns_r.get("spf_found", False),
        "dmarc": dns_r.get("dmarc_found", False),
        "server": headers_r.get("server", "?"),
        "missing_headers": headers_r.get("missing_security_headers", []),
    }

    _save_scan(domain, "quick", summary)
    return json.dumps(summary, indent=2, default=str)


@mcp.tool()
async def fingerprint(url: str):
    """
    Identify what type of website this is (SPA, CMS, Portal, etc.),
    its tech stack, and risk profile. Very fast (~3 seconds).

    Args:
        url: Target URL
    """
    url = _url(url)
    fp = await site_fingerprint(url)
    return json.dumps(fp, indent=2, default=str)


@mcp.tool()
async def check_secrets(url: str):
    """
    Scan JavaScript files for exposed API keys, tokens, and credentials.
    Validates found keys against their APIs to check if they're live.

    Args:
        url: Target URL
    """
    url = _url(url)
    secrets_r = await js_secrets_scanner(url)
    result = {"secrets_found": secrets_r.get("secrets_found", []), "js_files_scanned": secrets_r.get("js_files_scanned", 0)}

    if secrets_r.get("secrets_found"):
        val_r = await secret_validator(secrets_r["secrets_found"])
        result["validation"] = {
            "live": val_r.get("validated", []),
            "dead": val_r.get("dead_or_fake", []),
            "inconclusive": val_r.get("inconclusive", []),
            "live_count": val_r.get("live_count", 0),
        }

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def check_email_security(domain: str):
    """
    Check SPF, DKIM, DMARC records and email spoofing possibility.

    Args:
        domain: Domain to check (e.g. example.com)
    """
    r = await email_spoofing_test(domain)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def crawl_site(url: str):
    """
    Crawl a website to discover forms, URL parameters, links, and attack surface.
    Checks forms for CSRF tokens and password field security.

    Args:
        url: Target URL
    """
    url = _url(url)
    r = await smart_crawl(url)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def spa_discover(url: str):
    """
    Discover API endpoints in Single Page Applications (SPAs) using headless browser.
    Loads the SPA in Chromium, intercepts all XHR/fetch calls during navigation,
    parses JavaScript for API routes, and probes discovered endpoints.
    Use this for React, Angular, Vue apps where the regular crawler finds nothing.

    Args:
        url: Target URL
    """
    url = _url(url)
    r = await spa_api_discovery(url)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_injections(url: str):
    """
    Crawl the site first, then test all discovered parameters and forms
    for XSS and SQL injection. Dynamic testing based on real attack surface.

    Args:
        url: Target URL
    """
    url = _url(url)
    crawl_r = await smart_crawl(url)
    if crawl_r.get("parameters_found") or crawl_r.get("forms_found"):
        inj_r = await dynamic_injection_test(url, crawl_r)
        return json.dumps({
            "crawl": {"pages": crawl_r["pages_crawled"], "params": len(crawl_r["parameters_found"]), "forms": len(crawl_r["forms_found"])},
            "injection_results": inj_r,
        }, indent=2, default=str)
    return json.dumps({"message": "No parameters or forms found to test", "crawl": crawl_r}, indent=2, default=str)


@mcp.tool()
async def compare_scans(url: str):
    """
    Compare the latest scan with the previous one for the same domain.
    Shows new issues, resolved issues, and score changes.

    Args:
        url: Target URL or domain
    """
    domain = _domain(_url(url))
    safe_domain = domain.replace(".", "_").replace(":", "_")

    files = sorted(HISTORY_DIR.glob(f"{safe_domain}_full_*.json"), reverse=True)
    if len(files) < 2:
        return json.dumps({"error": f"Need at least 2 full scans for comparison. Found {len(files)}.", "scans_available": len(files)})

    with open(files[0], encoding="utf-8") as f:
        current = json.load(f)
    with open(files[1], encoding="utf-8") as f:
        previous = json.load(f)

    # Compare issues
    curr_titles = {i.get("title", "") for i in current.get("issues", [])}
    prev_titles = {i.get("title", "") for i in previous.get("issues", [])}

    new_issues = [i for i in current.get("issues", []) if i.get("title") not in prev_titles]
    resolved = [i for i in previous.get("issues", []) if i.get("title") not in curr_titles]

    delta = {
        "domain": domain,
        "current_scan": files[0].name,
        "previous_scan": files[1].name,
        "score_change": current.get("score", 0) - previous.get("score", 0),
        "current_score": current.get("score", 0),
        "previous_score": previous.get("score", 0),
        "total_issues_change": current.get("total_issues", 0) - previous.get("total_issues", 0),
        "new_issues": new_issues,
        "resolved_issues": resolved,
        "new_count": len(new_issues),
        "resolved_count": len(resolved),
    }

    return json.dumps(delta, indent=2, default=str)


@mcp.tool()
async def generate_report(url: str, company: str = "Client"):
    """
    Run a full scan AND generate a professional HTML report.
    Opens the report in the browser automatically.

    Args:
        url: Target URL
        company: Client company name for the report header
    """
    url = _url(url)
    domain = _domain(url)

    # Import and run the report generator
    from report_generator import generate_report as _gen
    output_path = f"report_{domain.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    path = await _gen(url, company=company, output_path=output_path)

    return json.dumps({"report_path": str(path), "domain": domain, "message": f"Report saved to {path}"})


@mcp.tool()
async def scan_history(domain: str = ""):
    """
    List all saved scan results. Optionally filter by domain.

    Args:
        domain: Optional domain filter (e.g. example.com). Empty = show all.
    """
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    if domain:
        safe = domain.replace(".", "_").replace(":", "_")
        files = [f for f in files if safe in f.name]

    scans = []
    for f in files[:20]:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            scans.append({
                "file": f.name,
                "domain": data.get("domain", "?"),
                "score": data.get("score", "?"),
                "total_issues": data.get("total_issues", "?"),
                "date": f.stem.split("_")[-2] + "_" + f.stem.split("_")[-1] if "_" in f.stem else "?",
            })
        except Exception:
            pass

    return json.dumps({"total_scans": len(scans), "scans": scans}, indent=2)


# ================================================================
# INDIVIDUAL TOOLS (exposed for targeted use)
# ================================================================

@mcp.tool()
async def check_ports(domain: str):
    """Scan common ports on a domain. Args: domain (e.g. example.com)"""
    r = await port_scan(domain)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def check_tls(domain: str):
    """Test TLS versions and cipher suites, return grade. Args: domain"""
    r = await tls_cipher_suite_grading(domain)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def check_subdomains(domain: str):
    """Enumerate subdomains and check for takeover. Args: domain"""
    sub_r = await subdomain_enum(domain)
    result = {"subdomains": sub_r}
    if sub_r.get("found_subdomains"):
        takeover_r = await subdomain_takeover_check(sub_r["found_subdomains"])
        result["takeover_check"] = takeover_r
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def check_cookies(url: str):
    """Audit all cookies for Secure, HttpOnly, SameSite flags. Args: url"""
    r = await cookie_security_audit(_url(url))
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def check_csp(url: str):
    """Analyze Content-Security-Policy for weaknesses and bypasses. Args: url"""
    r = await csp_analyzer(_url(url))
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def probe_xss(url: str):
    """
    Advanced XSS testing: crawl the site, find reflecting parameters,
    then test 20+ encoding bypass techniques (URL encoding, double encoding,
    unicode, parameter pollution, CRLF, null bytes, case tricks).
    Reports which bypasses succeed and how exploitable the reflections are.

    Args:
        url: Target URL
    """
    url = _url(url)
    crawl_r = await smart_crawl(url)
    r = await advanced_xss_probe(url, crawl_r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def evolve_xss(url: str, param: str, generations: int = 10):
    """
    Evolutionary XSS fuzzer. Evolves payloads across generations using
    mutation, crossover, and fitness-based selection to bypass input validation.

    Starts with known XSS payloads, mutates them (encoding changes, tag swaps,
    separator injection, case tricks), and selects the fittest (closest to
    bypassing validation). Reports the best payload found and whether
    exploitation was confirmed.

    Args:
        url: Target URL with the reflecting endpoint
        param: Parameter name that reflects input (e.g. 'templateQueryString')
        generations: Number of evolutionary generations (default: 10, max: 30)
    """
    url = _url(url)
    gens = min(int(generations), 30)
    r = await evolutionary_xss_fuzzer(url, param_name=param, param_url=url, generations=gens)
    return json.dumps(r, indent=2, default=str)


# ================================================================
# ================================================================
# RED TEAM TOOLS
# ================================================================

@mcp.tool()
async def attack_chain(url: str):
    """
    Full automated attack chain: scan → exploit → extract credentials →
    crack hashes → privilege escalation → data exfiltration.
    Returns structured results with evidence timeline.

    Args:
        url: Target URL
    """
    url = _url(url)
    r = await run_attack_chain(url)
    _save_scan(_domain(url), "attack_chain", r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def extract_sqli_data(url: str):
    """
    Extract database contents through SQL injection.
    Runs SQLi detection first, then extracts schema + credentials.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    sqli_r = await advanced_sqli_test(url, spa_r)
    if sqli_r.get("sqli_findings"):
        extract_r = await sqli_data_extraction(url, sqli_r["sqli_findings"])
        return json.dumps(extract_r, indent=2, default=str)
    return json.dumps({"message": "No SQLi injection points found", "sqli_tests": sqli_r.get("tests_run", 0)})


@mcp.tool()
async def crack_hashes(hashes: str):
    """
    Crack password hashes with built-in dictionary.
    Input: JSON array of {"email": "...", "hash": "..."} objects.

    Args:
        hashes: JSON string of hash objects
    """
    try:
        creds = json.loads(hashes)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON. Expected: [{\"email\": \"...\", \"hash\": \"...\"}]"})
    r = await credential_crack(creds)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_credential_reuse(url: str, credentials: str):
    """
    Test cracked credentials against all discovered login endpoints.
    Input: JSON array of {"email": "...", "cracked": "cleartext_password"} objects.

    Args:
        url: Target URL
        credentials: JSON string of credential objects
    """
    url = _url(url)
    try:
        creds = json.loads(credentials)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON"})
    spa_r = await spa_api_discovery(url)
    r = await credential_reuse_test(url, creds, spa_r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_session_security(url: str):
    """
    Test JWT manipulation, session hijacking, and privilege escalation.
    Registers a test user, obtains a token, then tests all manipulation techniques.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    sqli_r = await advanced_sqli_test(url, spa_r)
    auth_r = await auth_security_test(url, spa_r, sqli_r)
    tokens = [{"type": "jwt", "value": t.get("value", ""), "source": "auth_test"}
              for t in auth_r.get("jwt_findings", []) if t.get("type") == "jwt_decoded"]
    # Also collect tokens from SQLi bypass
    for b in sqli_r.get("auth_bypass", []):
        try:
            data = json.loads(b.get("response_preview", "{}"))
            token = data.get("authentication", {}).get("token", "") or data.get("token", "")
            if token:
                tokens.append({"type": "jwt", "value": token, "source": "sqli_bypass"})
        except Exception:
            pass
    hijack_r = await session_hijack_test(url, tokens, spa_r)
    return json.dumps(hijack_r, indent=2, default=str)


@mcp.tool()
async def obfuscate(payload: str, context: str = "sqli"):
    """
    Generate WAF-bypass variants of an attack payload.
    Returns multiple encoding variants with bypass likelihood.

    Args:
        payload: Original attack payload (e.g. "' OR 1=1--")
        context: Payload type: "sqli", "xss", or "path"
    """
    r = obfuscate_payload(payload, context=context, evasion_level=3)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_nosql(url: str):
    """
    Test for NoSQL injection (MongoDB operator injection).
    Tests $ne, $gt, $regex, $where operators on JSON API endpoints.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    r = await nosql_injection_test(url, spa_r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_xxe(url: str):
    """
    Test for XXE (XML External Entity) injection.
    Sends XXE payloads to XML-accepting endpoints to read files or trigger SSRF.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    r = await xxe_exploitation(url, spa_r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def test_ssrf(url: str):
    """
    Test for SSRF (Server-Side Request Forgery).
    Tests redirect endpoints and URL parameters for internal network access.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    r = await ssrf_exploitation(url, spa_r)
    return json.dumps(r, indent=2, default=str)


@mcp.tool()
async def pivot(url: str):
    """
    Use obtained credentials/tokens to access internal/admin endpoints.
    Runs auth test first to get tokens, then pivots to restricted endpoints.

    Args:
        url: Target URL
    """
    url = _url(url)
    spa_r = await spa_api_discovery(url)
    sqli_r = await advanced_sqli_test(url, spa_r)
    auth_r = await auth_security_test(url, spa_r, sqli_r)

    tokens = []
    for b in sqli_r.get("auth_bypass", []):
        try:
            data = json.loads(b.get("response_preview", "{}"))
            t = data.get("authentication", {}).get("token", "") or data.get("token", "")
            if t:
                tokens.append({"type": "jwt", "value": t, "source": "sqli", "user": "admin", "admin": True})
        except Exception:
            pass

    r = await auto_pivot(url, tokens, spa_r)
    return json.dumps(r, indent=2, default=str)


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    else:
        mcp.run(transport="stdio")
