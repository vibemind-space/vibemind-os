"""
Security Audit Report Generator
=================================
Generiert einen professionellen HTML-Report aus dem Security Audit.
Kann als PDF gedruckt werden (Browser -> Drucken -> PDF).

Nutzung:
  python report_generator.py https://goldbach-financial.com
  python report_generator.py https://example.com --output report.html
  python report_generator.py https://example.com --company "Firma GmbH"
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_client, get_model

from tools import (
    security_audit, whois_lookup, check_ssl_cert,
    dns_records, http_headers, page_content_scan,
    robots_sitemap_scan, subdomain_enum, cors_check,
    port_scan, path_discovery,
    cms_version_detect, login_security_check, subdomain_content_scan,
    xss_reflection_check, sqli_check,
    open_redirect_check, http_methods_check, js_secrets_scanner,
    email_spoofing_test, waf_detection, rate_limit_check,
    dns_zone_transfer, breach_check,
    # v2 checks
    tls_cipher_suite_grading, cookie_security_audit,
    api_endpoint_discovery, dependency_cve_scan,
    subdomain_takeover_check, secret_validator,
    # Intelligence
    site_fingerprint,
    # v3 dynamic checks
    source_map_check, csp_analyzer, smart_crawl,
    dynamic_injection_test, clickjacking_test,
)
from browser_verify import browser_verify


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Security Audit Report - {domain}</title>
<style>
  @page {{
    size: A4;
    margin: 20mm;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #1a1a2e;
    line-height: 1.6;
    background: #fff;
    font-size: 14px;
  }}

  /* Cover */
  .cover {{
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #fff;
    text-align: center;
    padding: 60px 40px;
    page-break-after: always;
  }}
  .cover h1 {{
    font-size: 42px;
    font-weight: 300;
    letter-spacing: 2px;
    margin-bottom: 10px;
  }}
  .cover .subtitle {{
    font-size: 18px;
    opacity: 0.8;
    margin-bottom: 40px;
  }}
  .cover .domain-box {{
    background: rgba(255,255,255,0.1);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 12px;
    padding: 30px 50px;
    margin: 20px 0;
  }}
  .cover .domain-box .domain {{
    font-size: 28px;
    font-weight: 600;
    letter-spacing: 1px;
  }}
  .cover .meta {{
    margin-top: 40px;
    font-size: 14px;
    opacity: 0.7;
  }}
  .cover .meta div {{ margin: 5px 0; }}

  /* Score Ring */
  .score-section {{
    text-align: center;
    padding: 40px 20px;
    page-break-after: always;
  }}
  .score-section h2 {{
    font-size: 28px;
    margin-bottom: 30px;
    color: #1a1a2e;
  }}
  .score-ring {{
    width: 200px;
    height: 200px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 56px;
    font-weight: 700;
    margin: 20px;
    border: 8px solid;
  }}
  .score-ring.critical {{ border-color: #e74c3c; color: #e74c3c; background: #fdf2f2; }}
  .score-ring.warning {{ border-color: #f39c12; color: #f39c12; background: #fef9e7; }}
  .score-ring.good {{ border-color: #27ae60; color: #27ae60; background: #eafaf1; }}
  .score-label {{
    font-size: 16px;
    color: #666;
    margin-top: 10px;
  }}
  .score-breakdown {{
    display: flex;
    justify-content: center;
    gap: 30px;
    margin-top: 30px;
    flex-wrap: wrap;
  }}
  .score-stat {{
    text-align: center;
    padding: 15px 25px;
    border-radius: 8px;
    background: #f8f9fa;
  }}
  .score-stat .num {{
    font-size: 32px;
    font-weight: 700;
  }}
  .score-stat .label {{
    font-size: 12px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}
  .stat-critical .num {{ color: #e74c3c; }}
  .stat-high .num {{ color: #e67e22; }}
  .stat-medium .num {{ color: #f39c12; }}
  .stat-low .num {{ color: #3498db; }}

  /* Content Pages */
  .page {{
    padding: 40px;
    page-break-after: always;
  }}
  .page h2 {{
    font-size: 24px;
    color: #1a1a2e;
    border-bottom: 3px solid #302b63;
    padding-bottom: 10px;
    margin-bottom: 25px;
  }}
  .page h3 {{
    font-size: 18px;
    color: #302b63;
    margin: 20px 0 10px;
  }}

  /* Issue Cards */
  .issue {{
    border-left: 4px solid;
    padding: 15px 20px;
    margin: 15px 0;
    background: #f8f9fa;
    border-radius: 0 8px 8px 0;
  }}
  .issue.critical {{ border-color: #e74c3c; background: #fdf2f2; }}
  .issue.high {{ border-color: #e67e22; background: #fef5e7; }}
  .issue.medium {{ border-color: #f39c12; background: #fef9e7; }}
  .issue.low {{ border-color: #3498db; background: #eef6fb; }}
  .issue .issue-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }}
  .issue .issue-title {{
    font-weight: 600;
    font-size: 16px;
  }}
  .issue .severity-badge {{
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: #fff;
  }}
  .severity-badge.critical {{ background: #e74c3c; }}
  .severity-badge.high {{ background: #e67e22; }}
  .severity-badge.medium {{ background: #f39c12; }}
  .severity-badge.low {{ background: #3498db; }}
  .issue .description {{ color: #555; margin-bottom: 10px; }}
  .issue .fix {{
    background: #1a1a2e;
    color: #7bed9f;
    padding: 10px 15px;
    border-radius: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    overflow-x: auto;
    white-space: pre-wrap;
    margin-top: 8px;
  }}
  .fix-label {{
    font-size: 12px;
    color: #888;
    margin-top: 8px;
    margin-bottom: 3px;
  }}

  /* Info Table */
  .info-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
  }}
  .info-table th, .info-table td {{
    padding: 10px 15px;
    text-align: left;
    border-bottom: 1px solid #eee;
  }}
  .info-table th {{
    background: #f8f9fa;
    font-weight: 600;
    color: #302b63;
    width: 200px;
  }}
  .status-ok {{ color: #27ae60; }}
  .status-warn {{ color: #f39c12; }}
  .status-bad {{ color: #e74c3c; }}

  /* Config Block */
  .config-block {{
    background: #1a1a2e;
    color: #a8e6cf;
    padding: 20px;
    border-radius: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    white-space: pre-wrap;
    margin: 15px 0;
    line-height: 1.8;
  }}
  .config-block .comment {{ color: #666; }}

  /* Proposal Section */
  .proposal {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    padding: 40px;
    border-radius: 12px;
    margin: 20px 0;
  }}
  .proposal h3 {{
    color: #fff;
    font-size: 22px;
    margin-bottom: 15px;
  }}
  .proposal ul {{
    list-style: none;
    padding: 0;
  }}
  .proposal li {{
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.2);
  }}
  .proposal li:last-child {{ border: none; }}

  /* Footer */
  .footer {{
    text-align: center;
    padding: 20px;
    color: #999;
    font-size: 12px;
    border-top: 1px solid #eee;
    margin-top: 40px;
  }}

  @media print {{
    body {{ font-size: 12px; }}
    .cover {{ min-height: auto; padding: 40px; }}
    .page {{ padding: 20px; }}
  }}
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
  <h1>SECURITY AUDIT</h1>
  <div class="subtitle">Comprehensive Security Analysis</div>
  <div class="domain-box">
    <div class="domain">{domain}</div>
  </div>
  <div class="meta">
    <div>Date: {date}</div>
    <div>Client: {company}</div>
    <div>Analyst: VibeMind Security Scanner</div>
    <div>Classification: CONFIDENTIAL</div>
  </div>
</div>

<!-- SCORE PAGE -->
<div class="score-section page">
  <h2>Security Score</h2>
  <div class="score-ring {score_class}">{score}</div>
  <div class="score-label">out of 100</div>
  <div class="score-breakdown">
    <div class="score-stat stat-critical">
      <div class="num">{critical_count}</div>
      <div class="label">Critical</div>
    </div>
    <div class="score-stat stat-high">
      <div class="num">{high_count}</div>
      <div class="label">High</div>
    </div>
    <div class="score-stat stat-medium">
      <div class="num">{medium_count}</div>
      <div class="label">Medium</div>
    </div>
    <div class="score-stat stat-low">
      <div class="num">{low_count}</div>
      <div class="label">Low</div>
    </div>
  </div>
</div>

<!-- EXECUTIVE SUMMARY -->
<div class="page">
  <h2>1. Executive Summary</h2>
  {executive_summary}
</div>

<!-- DOMAIN INFO -->
<div class="page">
  <h2>2. Domain Information</h2>
  {domain_info_html}
  {domain_info_narrative}
</div>

<!-- AUTO-INVESTIGATION -->
<div class="page">
  <h2>3. Auto-Investigation</h2>
  <p>Each finding was automatically investigated further. False positives have been downgraded:</p>
  {investigation_html}
  {investigation_narrative}
</div>

<!-- FINDINGS -->
<div class="page">
  <h2>4. Security Findings</h2>
  {findings_narrative}
  {findings_html}
</div>

<!-- TLS & CERTIFICATE -->
<div class="page">
  <h2>5. TLS / Certificate Analysis</h2>
  {tls_html}
  {tls_narrative}
</div>

<!-- HEADER ANALYSIS -->
<div class="page">
  <h2>6. HTTP Security Headers</h2>
  {headers_html}
  {headers_narrative}
</div>

<!-- FIX CONFIG -->
<div class="page">
  <h2>7. Recommended Server Configuration</h2>
  {server_config_narrative}

  <h3>nginx</h3>
  <div class="config-block">{nginx_config}</div>

  <h3>Apache</h3>
  <div class="config-block">{apache_config}</div>
</div>

<!-- ATTACK SCENARIOS -->
<div class="page">
  <h2>8. Attack Scenarios &amp; Mitigation</h2>
  {attack_scenarios_html}
</div>

<!-- LLM ANALYSIS -->
<div class="page">
  <h2>9. AI-Powered Deep Analysis</h2>
  {llm_analysis_html}
</div>

<!-- PROPOSAL -->
<div class="page">
  <h2>10. Recommended Actions</h2>
  <div class="proposal">
    <h3>Prioritized Remediation Steps</h3>
    <ul>
      {proposal_items}
    </ul>
  </div>
  <p style="margin-top:20px; color:#666;">
    We are happy to assist you with the implementation of these measures.
    Contact us for a customized quote.
  </p>
</div>

<!-- FOOTER -->
<div class="footer">
  Security Audit Report | {domain} | {date} | CONFIDENTIAL<br>
  Generated by VibeMind Security Scanner (LLM-Driven OSINT Analysis)
</div>

</body>
</html>"""


def severity_class(sev: str) -> str:
    return sev.lower() if sev.lower() in ("critical", "high", "medium", "low") else "low"


def _esc(text: str) -> str:
    """Escape HTML special characters in issue text."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_findings_html(issues: list) -> str:
    html = ""
    for issue in sorted(issues, key=lambda x: ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].index(x.get("severity", "INFO"))):
        sev = issue.get("severity", "LOW")
        cls = severity_class(sev)
        html += f"""
        <div class="issue {cls}">
          <div class="issue-header">
            <span class="issue-title">{_esc(issue.get('title', ''))}</span>
            <span class="severity-badge {cls}">{sev}</span>
          </div>
          <div class="description">{_esc(issue.get('description', ''))}</div>
          <div class="fix-label">Recommended Fix:</div>
          <div class="description">{_esc(issue.get('fix', ''))}</div>
"""
        if issue.get("nginx_fix"):
            html += f"""          <div class="fix-label">nginx:</div>
          <div class="fix">{issue['nginx_fix']}</div>
"""
        if issue.get("apache_fix"):
            html += f"""          <div class="fix-label">Apache:</div>
          <div class="fix">{issue['apache_fix']}</div>
"""
        html += "        </div>\n"
    return html


def build_domain_info_html(whois_data: dict, ssl_data: dict, dns_data: dict) -> str:
    rows = []

    def row(label, value, status=""):
        cls = f' class="{status}"' if status else ""
        return f"<tr><th>{label}</th><td{cls}>{value}</td></tr>"

    # WHOIS
    rows.append(row("Domain", whois_data.get("domain", "-")))
    rows.append(row("Registrar", whois_data.get("registrar", "-")))
    rows.append(row("Created", whois_data.get("creation_date", "-")))
    rows.append(row("Expiry Date", whois_data.get("expiry_date", "-")))

    age = whois_data.get("domain_age_days")
    if age:
        status = "status-ok" if age > 365 else "status-warn"
        rows.append(row("Domain Age", f"{age} days", status))

    privacy = whois_data.get("privacy_protected", False)
    rows.append(row("Privacy Protection", "Yes" if privacy else "No"))

    # SSL
    rows.append(row("TLS Version", ssl_data.get("tls_version", "-")))
    rows.append(row("Certificate Issuer", ssl_data.get("cert_issuer", "-")))

    cn_match = ssl_data.get("cn_matches_domain")
    if cn_match is not None:
        status = "status-ok" if cn_match else "status-bad"
        rows.append(row("CN Matches Domain", "Yes" if cn_match else "NO", status))

    expired = ssl_data.get("cert_expired")
    if expired is not None:
        status = "status-ok" if not expired else "status-bad"
        rows.append(row("Certificate Valid", "Yes" if not expired else "EXPIRED", status))

    # DNS
    spf = dns_data.get("spf_found", False)
    rows.append(row("SPF Record", "Present" if spf else "MISSING", "status-ok" if spf else "status-bad"))
    dmarc = dns_data.get("dmarc_found", False)
    rows.append(row("DMARC Record", "Present" if dmarc else "MISSING", "status-ok" if dmarc else "status-bad"))

    return f'<table class="info-table">{"".join(rows)}</table>'


def build_headers_html(header_analysis: dict) -> str:
    rows = []
    for header, info in header_analysis.items():
        present = info.get("present", False)
        value = info.get("value", "-")
        status = "status-ok" if present else "status-bad"
        display = value if present else "MISSING"
        rows.append(f"<tr><th>{header}</th><td class='{status}'>{display}</td></tr>")

    return f'<table class="info-table">{"".join(rows)}</table>'


def build_tls_html(ssl_data: dict, audit_tls: dict) -> str:
    rows = [
        f"<tr><th>TLS Version</th><td>{audit_tls.get('version', ssl_data.get('tls_version', '-'))}</td></tr>",
        f"<tr><th>Cipher Suite</th><td>{audit_tls.get('cipher_name', ssl_data.get('cipher', '-'))}</td></tr>",
        f"<tr><th>Cipher Bits</th><td>{audit_tls.get('cipher_bits', '-')}</td></tr>",
        f"<tr><th>Subject CN</th><td>{ssl_data.get('cert_subject_cn', '-')}</td></tr>",
        f"<tr><th>Issuer</th><td>{ssl_data.get('cert_issuer', '-')}</td></tr>",
        f"<tr><th>Valid From</th><td>{ssl_data.get('cert_not_before', '-')}</td></tr>",
        f"<tr><th>Valid Until</th><td>{ssl_data.get('cert_not_after', '-')}</td></tr>",
        f"<tr><th>Self-Signed</th><td>{'Yes' if ssl_data.get('self_signed') else 'No'}</td></tr>",
    ]
    san = ssl_data.get("cert_san", [])
    if san:
        rows.append(f"<tr><th>SAN Entries</th><td>{', '.join(san[:10])}</td></tr>")

    return f'<table class="info-table">{"".join(rows)}</table>'


ATTACK_SCENARIOS = {
    "Strict-Transport-Security": {
        "attack": "SSL-Stripping / Downgrade Attack",
        "how": (
            "An attacker on the same network (e.g. public WiFi) intercepts the first HTTP request "
            "and redirects the user to an unencrypted HTTP version of the site. "
            "Tools like <strong>sslstrip</strong> automate this attack. "
            "All entered data (login, forms) is transmitted in plaintext."
        ),
        "impact": "Credential interception, session hijacking, man-in-the-middle attack",
        "prevention": "HSTS header enforces HTTPS in the browser. After the first visit, the browser refuses HTTP connections.",
        "severity": "HIGH",
    },
    "Content-Security-Policy": {
        "attack": "Cross-Site Scripting (XSS)",
        "how": (
            "An attacker injects malicious JavaScript code into the website, e.g. via a "
            "comment field, URL parameters, or compromised third-party scripts. "
            "Without CSP, the browser executes any embedded code."
        ),
        "impact": "Session cookie theft, redirection to phishing sites, keylogging, data exfiltration",
        "prevention": "CSP defines allowed sources for scripts, styles, and media. Unauthorized code is blocked by the browser.",
        "severity": "HIGH",
    },
    "X-Frame-Options": {
        "attack": "Clickjacking",
        "how": (
            "The website is invisibly embedded in an iframe on an attacker's page. "
            "The user believes they are clicking harmless buttons, but actually triggers functions "
            "on the embedded original site (e.g. transfers, setting changes)."
        ),
        "impact": "Unintended actions on behalf of the user, account manipulation",
        "prevention": "X-Frame-Options: SAMEORIGIN prevents embedding in third-party sites.",
        "severity": "MEDIUM",
    },
    "X-Content-Type-Options": {
        "attack": "MIME-Type Confusion",
        "how": (
            "An attacker uploads a file disguised as a harmless image that actually contains "
            "JavaScript code. Without the nosniff header, the browser may 'guess' the MIME type "
            "and interpret the file as executable code."
        ),
        "impact": "Execution of malicious code in the browser context",
        "prevention": "X-Content-Type-Options: nosniff forces the browser to respect the declared MIME type.",
        "severity": "MEDIUM",
    },
    "Referrer-Policy": {
        "attack": "Information Leak via Referrer Header",
        "how": (
            "When a user clicks an external link from the site, the browser sends "
            "the full URL (including search terms, session IDs, tokens in query parameters) "
            "as Referrer to the target site."
        ),
        "impact": "Leak of sensitive URL parameters, session tokens, internal paths",
        "prevention": "Referrer-Policy: strict-origin-when-cross-origin sends only the domain, not the full path.",
        "severity": "LOW",
    },
    "Permissions-Policy": {
        "attack": "Browser API Abuse",
        "how": (
            "Third-party scripts (ads, analytics, compromised libraries) can access "
            "camera, microphone, geolocation and other browser APIs "
            "if no Permissions-Policy is set."
        ),
        "impact": "Unauthorized access to camera/microphone, location tracking",
        "prevention": "Permissions-Policy disables unnecessary browser APIs for the entire page.",
        "severity": "LOW",
    },
    "server_version": {
        "attack": "Reconnaissance / Information Gathering",
        "how": (
            "The server version in the header reveals exactly which software is running. "
            "An attacker can specifically search for known CVEs for this version."
        ),
        "impact": "Targeted exploits against known vulnerabilities of the deployed server version",
        "prevention": "Hide server version in configuration (nginx: server_tokens off).",
        "severity": "LOW",
    },
    "http_redirect": {
        "attack": "Unencrypted Initial Access",
        "how": (
            "If a user types the domain without https://, they land on the "
            "HTTP version. Without a redirect, the connection remains unencrypted."
        ),
        "impact": "Entire communication in plaintext, man-in-the-middle possible",
        "prevention": "Configure 301 redirect from HTTP to HTTPS.",
        "severity": "HIGH",
    },
}


def build_attack_scenarios_html(issues: list) -> str:
    """Generate attack scenario cards based on found issues."""
    html = ""
    seen = set()

    for issue in issues:
        # Map issue to attack scenario
        scenario_key = None
        title = issue.get("title", "")

        for header_name in ATTACK_SCENARIOS:
            if header_name in title:
                scenario_key = header_name
                break

        if "HTTP does not redirect" in title:
            scenario_key = "http_redirect"
        elif "Server version" in title:
            scenario_key = "server_version"

        if not scenario_key or scenario_key in seen:
            continue
        seen.add(scenario_key)

        scenario = ATTACK_SCENARIOS[scenario_key]
        cls = severity_class(scenario["severity"])

        html += f"""
        <div class="issue {cls}" style="margin-bottom: 20px;">
          <div class="issue-header">
            <span class="issue-title">{scenario['attack']}</span>
            <span class="severity-badge {cls}">{scenario['severity']}</span>
          </div>
          <h4 style="margin: 10px 0 5px; color: #e74c3c;">Attack Scenario:</h4>
          <div class="description">{scenario['how']}</div>
          <h4 style="margin: 10px 0 5px; color: #e67e22;">Impact:</h4>
          <div class="description">{scenario['impact']}</div>
          <h4 style="margin: 10px 0 5px; color: #27ae60;">Mitigation:</h4>
          <div class="description">{scenario['prevention']}</div>
        </div>
"""

    if not html:
        html = "<p>No specific attack scenarios identified for the detected issues.</p>"

    return html


async def generate_report(
    url: str,
    company: str = "Auftraggeber",
    output_path: str = None,
) -> str:
    """Run all checks and generate HTML report."""

    domain = urlparse(url).netloc or urlparse(url).path.split("/")[0]

    print(f"\n  SECURITY AUDIT REPORT GENERATOR")
    print(f"  Target: {url}")
    print(f"  Company: {company}\n")

    # =====================================================
    # PHASE 0: Site Fingerprinting (adaptive scanning)
    # =====================================================
    print("  [1/10] Fingerprinting target...", flush=True)
    fingerprint = await site_fingerprint(url)
    site_type = fingerprint["site_type"]
    risk_profile = fingerprint["risk_profile"]
    tech_stack = fingerprint["tech_stack"]
    print(f"         Type: {site_type} | Risk: {risk_profile} | Stack: {', '.join(tech_stack) or 'unknown'} | WAF: {fingerprint.get('waf_hint') or 'none'}", flush=True)

    # =====================================================
    # PHASE 1: Base checks (always run)
    # =====================================================
    print("  [2/10] Running base checks...", flush=True)

    whois_result, ssl_result, dns_result, headers_result, content_result, audit_result = (
        await asyncio.gather(
            whois_lookup(domain),
            check_ssl_cert(domain),
            dns_records(domain),
            http_headers(url),
            page_content_scan(url),
            security_audit(url),
        )
    )

    # Update risk_profile with WHOIS domain age
    domain_age = whois_result.get("domain_age_days")
    if domain_age is not None:
        fingerprint["domain_age_days"] = domain_age
        if domain_age < 30:
            risk_profile = "NEW_DOMAIN"
            fingerprint["risk_profile"] = risk_profile
            print(f"         ! Domain is only {domain_age} days old → NEW_DOMAIN", flush=True)

    print(f"  [2/10] Score (base): {audit_result['score']}/100", flush=True)

    # =====================================================
    # PHASE 2: Adaptive extended checks (based on fingerprint)
    # =====================================================

    # Define which checks to run per site type
    # All checks are (name, coroutine_fn, args) tuples
    ALWAYS_RUN = {
        "robots": (robots_sitemap_scan, [url]),
        "subdomain": (subdomain_enum, [domain]),
        "cors": (cors_check, [url]),
        "port": (port_scan, [domain]),
        "methods": (http_methods_check, [url]),
        "js_secrets": (js_secrets_scanner, [url]),
        "email": (email_spoofing_test, [domain]),
        "waf": (waf_detection, [url]),
        "tls_grade": (tls_cipher_suite_grading, [domain]),
        "cookie": (cookie_security_audit, [url]),
        # v3: always run these
        "source_maps": (source_map_check, [url]),
        "clickjacking": (clickjacking_test, [url]),
        "crawl": (smart_crawl, [url]),
    }

    CONDITIONAL_CHECKS = {
        "paths": (path_discovery, [url]),
        "cms": (cms_version_detect, [url]),
        "login": (login_security_check, [url]),
        "xss": (xss_reflection_check, [url]),
        "sqli": (sqli_check, [url]),
        "redirect": (open_redirect_check, [url]),
        "ratelimit": (rate_limit_check, [url]),
        "zone_transfer": (dns_zone_transfer, [domain]),
        "breach": (breach_check, [domain]),
        "api": (api_endpoint_discovery, [url]),
        "cve": (dependency_cve_scan, [url]),
    }

    # Build the check list based on fingerprint
    checks_to_run = dict(ALWAYS_RUN)
    skipped = []

    if site_type == "SPA":
        # SPAs: skip path discovery (catch-all), skip WP-specific checks
        skipped.extend(["paths", "cms", "login", "ratelimit"])
        checks_to_run["api"] = CONDITIONAL_CHECKS["api"]
        checks_to_run["cve"] = CONDITIONAL_CHECKS["cve"]
        checks_to_run["xss"] = CONDITIONAL_CHECKS["xss"]
        checks_to_run["sqli"] = CONDITIONAL_CHECKS["sqli"]
        checks_to_run["redirect"] = CONDITIONAL_CHECKS["redirect"]
        checks_to_run["breach"] = CONDITIONAL_CHECKS["breach"]
        checks_to_run["zone_transfer"] = CONDITIONAL_CHECKS["zone_transfer"]

    elif site_type == "CMS_WORDPRESS":
        # WordPress: full CMS scan, rate limit on wp-login, skip generic API discovery
        checks_to_run.update(CONDITIONAL_CHECKS)
        skipped.append("api")  # WP has its own REST API
        checks_to_run.pop("api", None)

    elif site_type == "PORTAL":
        # Portals (HIS/QIS, Java): focus on auth, cookies, skip CMS/CVE
        skipped.extend(["cms", "cve", "api"])
        checks_to_run["paths"] = CONDITIONAL_CHECKS["paths"]
        checks_to_run["login"] = CONDITIONAL_CHECKS["login"]
        checks_to_run["xss"] = CONDITIONAL_CHECKS["xss"]
        checks_to_run["sqli"] = CONDITIONAL_CHECKS["sqli"]
        checks_to_run["redirect"] = CONDITIONAL_CHECKS["redirect"]
        checks_to_run["ratelimit"] = CONDITIONAL_CHECKS["ratelimit"]
        checks_to_run["breach"] = CONDITIONAL_CHECKS["breach"]
        checks_to_run["zone_transfer"] = CONDITIONAL_CHECKS["zone_transfer"]

    else:
        # STATIC, API, CMS_OTHER, UNKNOWN → run everything
        checks_to_run.update(CONDITIONAL_CHECKS)

    # NEW_DOMAIN overrides: add aggressive checks
    if risk_profile == "NEW_DOMAIN":
        if "breach" not in checks_to_run:
            checks_to_run["breach"] = CONDITIONAL_CHECKS["breach"]
        # Skip wayback (pointless for new domains) — already handled in base checks

    total_checks = len(checks_to_run)
    print(f"  [3/10] Running {total_checks} adaptive checks (skipped: {', '.join(skipped) or 'none'})...", flush=True)

    # Execute all selected checks in parallel
    check_names = list(checks_to_run.keys())
    check_coros = [fn(*args) for fn, args in checks_to_run.values()]
    check_results_list = await asyncio.gather(*check_coros, return_exceptions=True)

    # Map results back to names, handle exceptions
    check_results = {}
    for name, result_or_exc in zip(check_names, check_results_list):
        if isinstance(result_or_exc, Exception):
            check_results[name] = {"issues": [], "error": str(result_or_exc)[:200]}
        else:
            check_results[name] = result_or_exc

    # Assign to named variables for backward compatibility
    robots_result = check_results.get("robots", {"issues": []})
    subdomain_result = check_results.get("subdomain", {"issues": []})
    cors_result = check_results.get("cors", {"issues": []})
    portscan_result = check_results.get("port", {"issues": []})
    paths_result = check_results.get("paths", {"issues": [], "found_paths": [], "env_leaks": []})
    cms_result = check_results.get("cms", {"issues": []})
    login_result = check_results.get("login", {"issues": []})
    xss_result = check_results.get("xss", {"issues": [], "reflections_found": []})
    sqli_result = check_results.get("sqli", {"issues": [], "potential_injections": []})
    redirect_result = check_results.get("redirect", {"issues": []})
    methods_result = check_results.get("methods", {"issues": []})
    js_secrets_result = check_results.get("js_secrets", {"issues": [], "secrets_found": []})
    email_result = check_results.get("email", {"issues": []})
    waf_result = check_results.get("waf", {"issues": []})
    ratelimit_result = check_results.get("ratelimit", {"issues": []})
    zone_transfer_result = check_results.get("zone_transfer", {"issues": []})
    breach_result = check_results.get("breach", {"issues": []})
    tls_grade_result = check_results.get("tls_grade", {"issues": [], "grade": "?"})
    cookie_result = check_results.get("cookie", {"issues": []})
    api_result = check_results.get("api", {"issues": [], "discovered_endpoints": []})
    cve_result = check_results.get("cve", {"issues": []})

    # Phase 2b: scan discovered subdomains + takeover check
    subdomain_scan_result = {"issues": []}
    takeover_result = {"issues": []}
    if subdomain_result.get("found_subdomains"):
        risky_subs = [s["subdomain"] for s in subdomain_result["found_subdomains"] if s.get("risky")]
        if risky_subs:
            print(f"  [3b/10] Scanning {len(risky_subs)} risky subdomains...", flush=True)
            subdomain_scan_result = await subdomain_content_scan(",".join(risky_subs))
        print(f"  [3c/10] Checking subdomain takeover...", flush=True)
        takeover_result = await subdomain_takeover_check(subdomain_result["found_subdomains"])

    # Phase 2c: dependent checks (need results from Phase 2)
    source_map_result = check_results.get("source_maps", {"issues": []})
    clickjacking_result = check_results.get("clickjacking", {"issues": []})
    crawl_result = check_results.get("crawl", {"issues": [], "forms_found": [], "parameters_found": []})

    # CSP analysis (depends on headers_result)
    csp_result = await csp_analyzer(url, headers_result)

    # Dynamic injection tests (depends on crawl_result)
    dynamic_test_result = {"issues": []}
    if crawl_result.get("parameters_found") or crawl_result.get("forms_found"):
        print(f"  [3d/10] Dynamic injection testing ({len(crawl_result.get('parameters_found', []))} params, {len(crawl_result.get('forms_found', []))} forms)...", flush=True)
        dynamic_test_result = await dynamic_injection_test(url, crawl_result)

    # Merge all issues into audit_result
    all_extras = [
        robots_result, subdomain_result, cors_result, portscan_result,
        paths_result, cms_result, login_result, subdomain_scan_result,
        xss_result, sqli_result,
        redirect_result, methods_result, js_secrets_result,
        email_result, waf_result, ratelimit_result,
        zone_transfer_result, breach_result,
        # v2 checks
        tls_grade_result, cookie_result, api_result,
        cve_result, takeover_result,
        # v3 checks
        source_map_result, csp_result, clickjacking_result,
        crawl_result, dynamic_test_result,
    ]
    for extra in all_extras:
        for issue in extra.get("issues", []):
            audit_result["issues"].append(issue)
            deduction = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10, "LOW": 3, "INFO": 0}
            audit_result["score"] = max(0, audit_result["score"] - deduction.get(issue.get("severity", "INFO"), 0))

    # Initialize score for use throughout the pipeline
    score = audit_result["score"]

    print(f"  [4/8] Score (final): {score}/100", flush=True)
    print(f"  [5/8] Total issues: {len(audit_result['issues'])}", flush=True)

    # Extended results summary
    if subdomain_result.get("found_subdomains"):
        print(f"         Subdomains: {subdomain_result['total_found']}", flush=True)
    if portscan_result.get("open_ports"):
        ports_str = ", ".join(str(p["port"]) for p in portscan_result["open_ports"])
        print(f"         Open ports: {ports_str}", flush=True)
    if paths_result.get("found_paths"):
        print(f"         Exposed paths: {len(paths_result['found_paths'])}", flush=True)
    if cms_result.get("cms"):
        ver = cms_result.get("cms_version", "?")
        print(f"         CMS: {cms_result['cms']} {ver}", flush=True)
    if cms_result.get("outdated_libraries"):
        for lib in cms_result["outdated_libraries"]:
            print(f"         Outdated: {lib['name']} {lib['version']} (latest: {lib['latest']})", flush=True)
    if login_result.get("login_page_found"):
        captcha = "yes" if login_result["has_captcha"] else "NO"
        twofa = "yes" if login_result["has_2fa_hint"] else "NO"
        print(f"         Login: CAPTCHA={captcha}, 2FA={twofa}", flush=True)
    if xss_result.get("reflections_found"):
        print(f"         XSS reflections: {len(xss_result['reflections_found'])}", flush=True)
    if sqli_result.get("potential_injections"):
        print(f"         SQLi indicators: {len(sqli_result['potential_injections'])}", flush=True)
    else:
        print(f"         SQLi: clean ({sqli_result.get('tests_run', 0)} tests)", flush=True)
    if js_secrets_result.get("secrets_found"):
        print(f"         JS Secrets: {len(js_secrets_result['secrets_found'])} found!", flush=True)
    if waf_result.get("waf_detected"):
        print(f"         WAF: {waf_result.get('waf_name', 'detected')}", flush=True)
    else:
        print(f"         WAF: none detected", flush=True)
    if email_result.get("spoofable"):
        print(f"         Email spoofing: POSSIBLE", flush=True)
    else:
        print(f"         Email spoofing: protected", flush=True)
    if breach_result.get("breaches_found"):
        print(f"         Breaches: {len(breach_result['breaches_found'])} found!", flush=True)
    # v2 check summaries
    print(f"         TLS Grade: {tls_grade_result.get('grade', '?')}", flush=True)
    if cookie_result.get("insecure_cookies"):
        print(f"         Insecure cookies: {cookie_result['insecure_cookies']}/{cookie_result['total_cookies']}", flush=True)
    if api_result.get("open_endpoints"):
        print(f"         Open API endpoints: {api_result['open_endpoints']}", flush=True)
    if cve_result.get("total_vulnerabilities"):
        print(f"         Vulnerable JS libs: {cve_result['total_vulnerabilities']} CVEs!", flush=True)
    if takeover_result.get("dangling_cnames"):
        print(f"         Subdomain takeover: {len(takeover_result['dangling_cnames'])} dangling CNAMEs!", flush=True)

    # =====================================================
    # AUTO-INVESTIGATION PASS
    # =====================================================
    print("  [5b/8] Auto-Investigation — verifying findings...", flush=True)

    import urllib.request
    import urllib.error
    import re as _re

    issues = audit_result["issues"]
    investigations = []

    # --- 0. TLS consistency check: if tls_cipher_suite_grading says A/A+ but security_audit says "TLS failed", debunk it ---
    tls_grade = tls_grade_result.get("grade", "")
    if tls_grade in ("A", "A+"):
        for issue in issues[:]:
            if issue.get("title") == "TLS connection failed" and issue.get("severity") == "CRITICAL":
                issue["_original_severity"] = issue["severity"]
                issue["severity"] = "INFO"
                issue["title"] += " [FALSE POSITIVE — TLS Grade " + tls_grade + "]"
                score_refund = 30
                score = min(100, score + score_refund)
                investigations.append({
                    "finding": "TLS connection failed",
                    "checks": [{"check": "TLS Grade", "result": f"Grade {tls_grade} confirmed by tls_cipher_suite_grading"}],
                    "verdict": f"FALSE POSITIVE — TLS is healthy (Grade {tls_grade}). The security_audit TLS check timed out.",
                })

    # --- 1. Path Discovery: check actual content (empty body = not really exposed) ---
    for issue in issues[:]:
        if issue.get("category") == "Path Exposure" and "200" in issue.get("title", ""):
            path = ""
            path_match = _re.search(r'(/\S+)\s+accessible', issue.get("title", ""))
            if path_match:
                path = path_match.group(1)
                check_url = url.rstrip("/") + path
                try:
                    req = urllib.request.Request(check_url, headers={"User-Agent": "Mozilla/5.0 (Security Audit)"})
                    resp = await asyncio.get_event_loop().run_in_executor(
                        None, lambda u=check_url: urllib.request.urlopen(
                            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=10
                        )
                    )
                    body = resp.read().decode("utf-8", errors="replace")
                    content_type = resp.headers.get("Content-Type", "")

                    inv = {"finding": f"Path {path}", "checks": [], "verdict": "UNKNOWN"}
                    inv["checks"].append({"check": "Content-Length", "result": f"{len(body)} bytes"})
                    inv["checks"].append({"check": "Content-Type", "result": content_type})

                    if len(body) == 0:
                        inv["verdict"] = "FALSE POSITIVE — file exists but returns empty body (PHP executed, no output)"
                        issue["severity"] = "LOW"
                        issue["title"] += " [EMPTY BODY]"
                        issue["description"] += " (PHP ausfuehrbar, kein Inhalt sichtbar — kein aktives Leck)"
                        # Recalculate score
                        if issue.get("_original_severity") != "LOW":
                            score_refund = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10}.get(issue.get("_original_severity", "MEDIUM"), 0)
                            audit_result["score"] = min(100, audit_result["score"] + score_refund - 3)
                    elif "<?php" in body or "define(" in body:
                        inv["verdict"] = "CRITICAL CONFIRMED — PHP source code visible!"
                        inv["checks"].append({"check": "Content Preview", "result": body[:200]})
                    elif "<html" in body.lower() or "<form" in body.lower():
                        inv["verdict"] = "CONFIRMED — page returns HTML content (login/admin panel)"
                        inv["checks"].append({"check": "Content Preview", "result": body[:100]})
                    else:
                        inv["verdict"] = f"Returns {len(body)} bytes — content type: {content_type}"
                        inv["checks"].append({"check": "Content Preview", "result": body[:100]})

                    investigations.append(inv)
                except Exception:
                    pass

    # --- 2. Port Scan: classify safe vs risky ports ---
    EXPECTED_PORTS = {
        80: "HTTP — expected for web server",
        443: "HTTPS — expected for web server",
        993: "IMAPS — encrypted mail, expected",
        995: "POP3S — encrypted mail, expected",
    }
    MAIL_PORTS = {
        25: "SMTP — needed for email delivery (expected for mail server)",
        110: "POP3 — unencrypted mail access (should use IMAPS/POP3S instead)",
        143: "IMAP — unencrypted mail access (should use IMAPS instead)",
    }

    for issue in issues[:]:
        if issue.get("category") == "Network Exposure":
            port_match = _re.search(r'Port (\d+)', issue.get("title", ""))
            if port_match:
                port = int(port_match.group(1))
                if port in EXPECTED_PORTS:
                    issue["severity"] = "INFO"
                    issue["title"] += " [EXPECTED]"
                    issue["description"] = EXPECTED_PORTS[port]
                    investigations.append({
                        "finding": f"Port {port}",
                        "checks": [{"check": "Classification", "result": EXPECTED_PORTS[port]}],
                        "verdict": "FALSE POSITIVE — expected service port",
                    })
                elif port in MAIL_PORTS:
                    if port in (110, 143):
                        issue["severity"] = "MEDIUM"
                        issue["description"] = MAIL_PORTS[port]
                    else:
                        issue["severity"] = "LOW"
                        issue["description"] = MAIL_PORTS[port]
                    investigations.append({
                        "finding": f"Port {port}",
                        "checks": [{"check": "Classification", "result": MAIL_PORTS[port]}],
                        "verdict": f"EXPECTED for mail server — {'use encrypted alternative' if port in (110, 143) else 'normal'}",
                    })
                elif port == 22:
                    # Check SSH banner for version
                    banner_info = ""
                    for op in portscan_result.get("open_ports", []):
                        if op["port"] == 22 and op.get("banner"):
                            banner_info = op["banner"]
                    investigations.append({
                        "finding": "Port 22 (SSH)",
                        "checks": [
                            {"check": "Banner", "result": banner_info or "no banner"},
                            {"check": "Risk", "result": "SSH publicly accessible — should be behind VPN or IP-restricted"},
                        ],
                        "verdict": "CONFIRMED RISK — SSH should not be publicly exposed for a web application",
                    })

    # --- 3. XSS: check if encoding prevents exploitation ---
    for issue in issues[:]:
        if issue.get("category") == "XSS":
            for refl in xss_result.get("reflections_found", []):
                if refl.get("is_html_encoded"):
                    inv = {
                        "finding": f"XSS reflection: {refl.get('vector_name', '?')}",
                        "checks": [
                            {"check": "HTML Encoding", "result": "Active — browser will not execute injected code"},
                            {"check": "Context", "result": refl.get("context_type", "?")},
                        ],
                        "verdict": "LOW RISK — input is reflected but HTML-encoded. Direct XSS unlikely, but combined with outdated jQuery may be exploitable.",
                    }
                    investigations.append(inv)

    # --- 4. Email spoofing: verify SPF/DMARC details ---
    if email_result.get("spoofable"):
        inv = {
            "finding": "Email spoofing assessment",
            "checks": [],
            "verdict": "UNKNOWN",
        }
        if email_result.get("spf", {}).get("found"):
            strict = email_result["spf"].get("strict", False)
            inv["checks"].append({"check": "SPF", "result": f"Found, strict (-all): {strict}"})
        else:
            inv["checks"].append({"check": "SPF", "result": "NOT FOUND"})

        if email_result.get("dmarc", {}).get("found"):
            policy = email_result["dmarc"].get("policy", "?")
            inv["checks"].append({"check": "DMARC", "result": f"Found, policy: {policy}"})
            if policy == "none":
                inv["verdict"] = "CONFIRMED — DMARC policy is 'none', emails are not rejected. Spoofing possible."
            elif policy == "reject":
                inv["verdict"] = "PROTECTED — DMARC policy is 'reject', spoofed emails will be blocked."
        else:
            inv["checks"].append({"check": "DMARC", "result": "NOT FOUND"})
            inv["verdict"] = "CONFIRMED — no DMARC record, email spoofing is possible."

        if email_result.get("dkim", {}).get("found"):
            inv["checks"].append({"check": "DKIM", "result": "Found"})
        else:
            inv["checks"].append({"check": "DKIM", "result": "NOT FOUND"})

        investigations.append(inv)

    # --- 5. 403 paths: not really exposed ---
    for issue in issues[:]:
        if issue.get("category") == "Path Exposure" and "403" in issue.get("title", ""):
            issue["severity"] = "INFO"
            issue["title"] += " [BLOCKED]"
            investigations.append({
                "finding": issue["title"].replace(" [BLOCKED]", ""),
                "checks": [{"check": "HTTP Status", "result": "403 Forbidden — file exists but access is blocked"}],
                "verdict": "FALSE POSITIVE — server correctly blocks access. File should still be removed from server.",
            })

    # Recalculate score after investigation
    score = 100
    for issue in issues:
        deduction = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10, "LOW": 3, "INFO": 0}
        score -= deduction.get(issue.get("severity", "INFO"), 0)
    audit_result["score"] = max(0, score)

    print(f"  [5c/8] Score (after investigation): {audit_result['score']}/100", flush=True)
    print(f"         {len(investigations)} auto-investigations completed", flush=True)

    # Count severities
    critical_count = sum(1 for i in issues if i.get("severity") == "CRITICAL")
    high_count = sum(1 for i in issues if i.get("severity") == "HIGH")
    medium_count = sum(1 for i in issues if i.get("severity") == "MEDIUM")
    low_count = sum(1 for i in issues if i.get("severity") == "LOW")
    info_count = sum(1 for i in issues if i.get("severity") == "INFO")

    print(f"         Issues: C:{critical_count} H:{high_count} M:{medium_count} L:{low_count} I:{info_count}", flush=True)

    # Score class (score already set and updated during pipeline)
    if score >= 80:
        score_class = "good"
    elif score >= 50:
        score_class = "warning"
    else:
        score_class = "critical"

    # Investigation HTML
    investigation_html = ""
    for inv in investigations:
        verdict = inv.get("verdict", "UNKNOWN")
        if "FALSE POSITIVE" in verdict:
            cls = "low"
        elif "BENIGN" in verdict or "PROTECTED" in verdict or "EXPECTED" in verdict:
            cls = "low"
        elif "CONFIRMED" in verdict:
            cls = "high"
        else:
            cls = "medium"

        checks_html = ""
        for chk in inv.get("checks", []):
            checks_html += f'<tr><td><strong>{chk["check"]}</strong></td><td>{chk["result"][:200]}</td></tr>'

        investigation_html += f"""
        <div class="issue {cls}" style="margin-bottom:15px;">
          <div class="issue-header">
            <span class="issue-title">{_esc(inv['finding'])}</span>
          </div>
          <table class="info-table" style="margin:10px 0;">{checks_html}</table>
          <div class="fix">{_esc(verdict)}</div>
        </div>"""

    if not investigations:
        investigation_html = "<p>No findings required further investigation.</p>"

    # =====================================================
    # ATTACK CHAIN CORRELATION ENGINE
    # =====================================================
    # Pre-init variables that are set in later phases but referenced by correlation engine
    secret_validation_result = {"validated": [], "dead_or_fake": [], "inconclusive": [], "total_checked": 0, "live_count": 0, "issues": []}

    print("  [6/10] Correlating attack chains...", flush=True)

    def _has_issue(category=None, title_kw=None, severity=None):
        """Check if an issue matching criteria exists."""
        for iss in issues:
            if severity and iss.get("severity") != severity:
                continue
            if category and iss.get("category") != category:
                continue
            if title_kw and title_kw.lower() not in iss.get("title", "").lower():
                continue
            return True
        return False

    attack_chains = []

    # Chain 1: XSS + insecure session cookie = session hijacking
    has_xss = _has_issue(title_kw="xss") or _has_issue(title_kw="reflected")
    has_insecure_session = any(c.get("is_session_cookie") and c.get("issues") for c in cookie_result.get("cookies_found", []))
    if has_xss and has_insecure_session:
        attack_chains.append({
            "severity": "CRITICAL",
            "category": "Attack Chain",
            "title": "Session Hijacking: XSS + Insecure Session Cookies",
            "description": "XSS reflection combined with session cookies missing HttpOnly flag allows an attacker to steal user sessions with a single crafted URL.",
            "fix": "1. Fix XSS vulnerabilities. 2. Set HttpOnly + Secure + SameSite=Strict on all session cookies.",
        })

    # Chain 2: Open DB port + no WAF = directly exploitable database
    has_db_port = any("3306" in iss.get("title", "") or "5432" in iss.get("title", "") or "27017" in iss.get("title", "") for iss in issues)
    has_no_waf = not waf_result.get("waf_detected", False)
    if has_db_port and has_no_waf:
        attack_chains.append({
            "severity": "CRITICAL",
            "category": "Attack Chain",
            "title": "Database Exposure: Open DB Port + No WAF",
            "description": "Database port is publicly accessible without a Web Application Firewall. Attackers can attempt direct database connections, brute-force credentials, or exploit known CVEs.",
            "fix": "1. Close database port via firewall. 2. Deploy WAF. 3. Restrict DB access to application servers only.",
        })

    # Chain 3: Email spoofing + exposed admin panel = phishing + admin compromise
    has_email_spoof = email_result.get("spoofable", False)
    has_admin = _has_issue(title_kw="/admin") or _has_issue(title_kw="admin panel")
    if has_email_spoof and has_admin:
        attack_chains.append({
            "severity": "HIGH",
            "category": "Attack Chain",
            "title": "Phishing + Admin Compromise: Email Spoofing + Exposed Admin",
            "description": "Attacker can send emails appearing to be from this domain (no SPF/DMARC) and direct victims to the exposed admin login for credential harvesting.",
            "fix": "1. Configure SPF + DMARC + DKIM. 2. Restrict admin panel to VPN/IP whitelist.",
        })

    # Chain 4: LIVE API keys + no CSP = key theft via XSS
    has_live_keys = secret_validation_result.get("live_count", 0) > 0
    has_no_csp = _has_issue(title_kw="Content-Security-Policy")
    if has_live_keys and (has_no_csp or has_xss):
        attack_chains.append({
            "severity": "CRITICAL",
            "category": "Attack Chain",
            "title": "API Key Theft: Live Secrets + Missing CSP/XSS",
            "description": "Live API keys are exposed in JavaScript. Combined with missing Content-Security-Policy or XSS vulnerabilities, any attacker can exfiltrate these keys via injected scripts.",
            "fix": "1. Remove API keys from frontend code. 2. Implement strict CSP. 3. Use server-side API proxies.",
        })

    # Chain 5: SSH/FTP exposed + no rate limit = brute force
    has_ssh = any("22" in iss.get("title", "") and "SSH" in iss.get("title", "") for iss in issues)
    has_ftp = any("21" in iss.get("title", "") and "FTP" in iss.get("title", "") for iss in issues)
    if (has_ssh or has_ftp) and has_no_waf:
        attack_chains.append({
            "severity": "HIGH",
            "category": "Attack Chain",
            "title": f"Brute Force: {'SSH' if has_ssh else 'FTP'} Exposed + No WAF",
            "description": f"{'SSH' if has_ssh else 'FTP'} port is publicly accessible without rate limiting or WAF protection. Automated brute-force tools can attempt thousands of credential combinations.",
            "fix": f"1. Restrict {'SSH' if has_ssh else 'FTP'} to VPN/specific IPs. 2. Enable fail2ban. 3. Use key-based auth (SSH) or disable FTP entirely.",
        })

    # Chain 6: PUT/DELETE methods + no auth = file upload/deletion
    has_dangerous_methods = _has_issue(title_kw="PUT") or _has_issue(title_kw="DELETE")
    if has_dangerous_methods and has_no_waf:
        attack_chains.append({
            "severity": "HIGH",
            "category": "Attack Chain",
            "title": "Unauthorized File Manipulation: PUT/DELETE + No WAF",
            "description": "Dangerous HTTP methods (PUT/DELETE) are enabled without WAF protection. Attackers can upload web shells or delete critical resources.",
            "fix": "1. Disable PUT/DELETE methods unless required for API. 2. Deploy WAF with method filtering.",
        })

    # Add chains to issues
    for chain in attack_chains:
        issues.append(chain)
        deduction = {"CRITICAL": 25, "HIGH": 15}.get(chain["severity"], 0)
        score = max(0, score - deduction)

    if attack_chains:
        print(f"         {len(attack_chains)} attack chain(s) identified!", flush=True)
    else:
        print(f"         No attack chains detected.", flush=True)

    # =====================================================
    # BROWSER VERIFICATION (Playwright)
    # =====================================================
    print("  [7/10] Browser verification (Playwright)...", flush=True)

    browser_result = {"verified_paths": [], "debunked_paths": [], "verified_xss": [],
                      "debunked_xss": [], "screenshots": [], "summary": "Skipped"}
    try:
        scan_for_browser = {
            "paths": paths_result,
            "xss": xss_result,
            "login": login_result,
        }
        browser_result = await browser_verify(url, scan_for_browser)

        # Downgrade debunked findings in the issues list
        debunked_paths = {d["path"] for d in browser_result.get("debunked_paths", [])}
        debunked_xss = {d.get("vector_name", "") for d in browser_result.get("debunked_xss", [])}

        for issue in issues:
            title = issue.get("title", "")
            # Debunk path findings
            for dp in debunked_paths:
                if dp in title and issue["severity"] in ("CRITICAL", "HIGH"):
                    issue["_original_severity"] = issue["severity"]
                    issue["severity"] = "INFO"
                    issue["title"] += " [DEBUNKED BY BROWSER]"
                    score_refund = {"CRITICAL": 25, "HIGH": 15}.get(issue["_original_severity"], 0)
                    score = min(100, score + score_refund)
                    break
            # Debunk XSS findings
            for dx in debunked_xss:
                if dx in title:
                    issue["_original_severity"] = issue["severity"]
                    issue["severity"] = "INFO"
                    issue["title"] += " [DEBUNKED BY BROWSER]"
                    break

        # Tag verified findings
        verified_paths = {v["path"] for v in browser_result.get("verified_paths", [])}
        for issue in issues:
            title = issue.get("title", "")
            for vp in verified_paths:
                if vp in title:
                    issue["title"] += " [BROWSER VERIFIED]"
                    break

        # Add browser-discovered issues to main list
        for issue in browser_result.get("issues", []):
            issues.append(issue)
            deduction = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10, "LOW": 3, "INFO": 0}
            score = max(0, score - deduction.get(issue.get("severity", "INFO"), 0))

        print(f"  [6/9] Score (after browser verification): {score}/100", flush=True)

    except Exception as e:
        print(f"  [!] Browser verification failed: {e}. Continuing without.", flush=True)

    # =====================================================
    # SECRET VALIDATION (verify if keys are live)
    # =====================================================
    secret_validation_result = {"validated": [], "dead_or_fake": [], "inconclusive": [], "total_checked": 0, "live_count": 0, "issues": []}
    js_secrets_list = js_secrets_result.get("secrets_found", [])
    env_leaks_list = paths_result.get("env_leaks", [])

    if js_secrets_list or env_leaks_list:
        print(f"  [7/10] Validating {len(js_secrets_list)} JS secrets + {sum(len(e.get('secrets',[])) for e in env_leaks_list)} env secrets...", flush=True)
        try:
            secret_validation_result = await secret_validator(js_secrets_list, env_leaks_list)
            print(f"         LIVE: {secret_validation_result['live_count']}, "
                  f"DEAD: {len(secret_validation_result['dead_or_fake'])}, "
                  f"INCONCLUSIVE: {len(secret_validation_result['inconclusive'])}", flush=True)

            # Add validation issues to main issues list
            for issue in secret_validation_result.get("issues", []):
                issues.append(issue)
                deduction = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10, "LOW": 3, "INFO": 0}
                score = max(0, score - deduction.get(issue.get("severity", "INFO"), 0))

        except Exception as e:
            print(f"  [!] Secret validation failed: {e}", flush=True)
    else:
        print(f"  [7/10] No secrets to validate, skipping.", flush=True)

    # =====================================================
    # LLM-DRIVEN REPORT GENERATION
    # =====================================================
    print("  [8/10] LLM report generation (all sections)...", flush=True)

    llm_client = get_client("report")
    llm_model = get_model("report", "poc_site_verifier")

    # Collect all raw results for the LLM
    all_results = {
        "whois": whois_result,
        "ssl": ssl_result,
        "dns": dns_result,
        "headers": headers_result,
        "content": content_result,
        "audit": {k: v for k, v in audit_result.items() if k not in ("header_analysis", "nginx_config_snippet", "apache_config_snippet")},
        "robots": robots_result,
        "subdomains": subdomain_result,
        "subdomain_scan": subdomain_scan_result,
        "subdomain_takeover": takeover_result,
        "cors": cors_result,
        "portscan": portscan_result,
        "paths": paths_result,
        "api_discovery": api_result,
        "cms": cms_result,
        "login": login_result,
        "xss": xss_result,
        "sqli": sqli_result,
        "redirect": redirect_result,
        "methods": methods_result,
        "js_secrets": js_secrets_result,
        "dependency_cves": cve_result,
        "email": email_result,
        "waf": waf_result,
        "ratelimit": ratelimit_result,
        "zone_transfer": zone_transfer_result,
        "breach": breach_result,
        "cookies": cookie_result,
        "tls_grading": tls_grade_result,
        "browser_verification": {
            "verified_paths": browser_result.get("verified_paths", []),
            "debunked_paths": browser_result.get("debunked_paths", []),
            "verified_xss": browser_result.get("verified_xss", []),
            "debunked_xss": browser_result.get("debunked_xss", []),
            "summary": browser_result.get("summary", ""),
        },
        "secret_validation": {
            "validated": secret_validation_result.get("validated", []),
            "dead_or_fake": secret_validation_result.get("dead_or_fake", []),
            "inconclusive": secret_validation_result.get("inconclusive", []),
            "live_count": secret_validation_result.get("live_count", 0),
        },
    }

    # Truncate large fields to fit context window
    truncated = json.loads(json.dumps(all_results, default=str))
    if "whois" in truncated and "raw" in truncated["whois"]:
        truncated["whois"]["raw"] = truncated["whois"]["raw"][:500]
    for key in ("paths", "api_discovery"):
        if key in truncated and isinstance(truncated[key], dict):
            for list_key in ("found_paths", "discovered_endpoints"):
                if list_key in truncated[key] and len(truncated[key][list_key]) > 20:
                    truncated[key][list_key] = truncated[key][list_key][:20]

    issues_json = json.dumps(issues, indent=1, default=str)
    investigations_json = json.dumps(investigations, indent=1, default=str)
    results_json = json.dumps(truncated, indent=1, default=str)

    system_prompt = (
        "You are a Senior Security Consultant writing a professional security audit report.\n\n"
        "You receive raw results from 28 automated security checks. Interpret, correlate, and narrate them.\n\n"
        "RULES:\n"
        "1. CORRELATE findings across checks (e.g. 'open MySQL + no WAF = actively exploitable').\n"
        "2. Do NOT repeat raw data. Interpret what it means for business risk.\n"
        "3. Professional, clear English. No jargon without explanation.\n"
        "4. Format ALL content as HTML fragments (<p>, <ul>, <li>, <strong>, <table>).\n"
        "5. Prioritize by business impact.\n\n"
        "OUTPUT: Return a JSON object with EXACTLY these keys:\n\n"
        "{\n"
        '  "executive_summary": "Section 1: 3-5 paragraphs for C-level. Overall posture, key risks, urgent actions.",\n'
        '  "domain_info_narrative": "Section 2: 1-2 paragraphs interpreting domain/cert/DNS data.",\n'
        '  "investigation_narrative": "Section 3: 1-2 paragraphs on confirmed vs false positive findings.",\n'
        '  "findings_narrative": "Section 4: 2-3 paragraphs overview of the vulnerability landscape.",\n'
        '  "tls_narrative": "Section 5: TLS grade assessment, cipher analysis, recommendations.",\n'
        '  "headers_narrative": "Section 6: What missing/present headers mean practically.",\n'
        '  "server_config_narrative": "Section 7: Context for the configuration changes.",\n'
        '  "attack_scenarios": "Section 8: 3-7 CORRELATED attack scenarios chaining multiple vulns. HTML with severity badges.",\n'
        '  "deep_analysis": "Section 9: Comprehensive technical analysis. Infrastructure, app, email, info disclosure. 4-8 paragraphs.",\n'
        '  "recommended_actions": "Section 10: 8-15 <li> items ordered by priority."\n'
        "}\n\n"
        "Output ONLY the JSON object. No markdown fences. No text before or after."
    )

    user_prompt = (
        f"Domain: {domain}\nCompany: {company}\nScore: {score}/100\n"
        f"Critical: {critical_count}, High: {high_count}, Medium: {medium_count}, Low: {low_count}\n\n"
        f"=== RAW CHECK RESULTS ===\n{results_json}\n\n"
        f"=== MERGED ISSUES (post-investigation) ===\n{issues_json}\n\n"
        f"=== AUTO-INVESTIGATIONS ===\n{investigations_json}\n\n"
        f"Write the complete report."
    )

    llm_content = {}
    try:
        llm_response = await llm_client.chat.completions.create(
            model=llm_model,
            temperature=0,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        llm_text = llm_response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if llm_text.startswith("```"):
            llm_text = llm_text.split("\n", 1)[1] if "\n" in llm_text else llm_text[3:]
            if llm_text.endswith("```"):
                llm_text = llm_text[:-3]

        llm_content = json.loads(llm_text)
        print(f"  [6/8] LLM generated {len(llm_content)} report sections.", flush=True)

    except (json.JSONDecodeError, Exception) as e:
        print(f"  [!] LLM report generation failed: {e}. Using fallback.", flush=True)
        # Fallback: generate basic content programmatically
        fallback_proposal = ""
        for issue in sorted(issues, key=lambda x: ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].index(x.get("severity", "INFO"))):
            fallback_proposal += f"<li><strong>[{issue['severity']}]</strong> {issue.get('fix', issue.get('title', ''))}</li>\n"
        llm_content = {
            "executive_summary": f"<p>Security audit of {domain} completed with a score of {score}/100. {critical_count} critical and {high_count} high severity issues were identified requiring immediate attention.</p>",
            "domain_info_narrative": "",
            "investigation_narrative": "",
            "findings_narrative": "",
            "tls_narrative": "",
            "headers_narrative": "",
            "server_config_narrative": "",
            "attack_scenarios": build_attack_scenarios_html(issues),
            "deep_analysis": "",
            "recommended_actions": fallback_proposal,
        }

    # =====================================================
    # FACT-CHECK LLM OUTPUT
    # =====================================================
    def fact_check_llm(llm_output: dict, scan_issues: list, scan_results: dict) -> list:
        """Validate LLM claims against actual scan data. Returns list of corrections."""
        corrections = []
        all_text = " ".join(str(v) for v in llm_output.values()).lower()

        # --- 1. Severity count check ---
        actual_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for issue in scan_issues:
            sev = issue.get("severity", "INFO").lower()
            if sev in actual_counts:
                actual_counts[sev] += 1

        for sev_name, actual_count in actual_counts.items():
            # Look for wrong counts in LLM text like "5 critical" when there are only 2
            import re as _re
            for m in _re.finditer(r'(\d+)\s+' + sev_name, all_text):
                claimed = int(m.group(1))
                if claimed != actual_count and abs(claimed - actual_count) > 1:
                    corrections.append(f"LLM claims {claimed} {sev_name} issues, actual: {actual_count}")

        # --- 2. Phantom finding check ---
        # Collect all real finding keywords
        real_titles = {issue.get("title", "").lower() for issue in scan_issues}
        real_categories = {issue.get("category", "").lower() for issue in scan_issues}

        # Check if LLM mentions specific vuln types that don't exist in findings
        phantom_checks = [
            ("sql injection", "sqli", scan_results.get("sqli", {}).get("potential_injections", [])),
            ("remote code execution", "rce", []),
            ("directory traversal", "path_traversal", []),
            ("xxe", "xxe", []),
            ("ssrf", "ssrf", []),
            ("deserialization", "deserialization", []),
        ]
        for vuln_name, short_name, actual_findings in phantom_checks:
            if vuln_name in all_text and not actual_findings:
                # Check if it's just mentioned as "not found" or in a negative context
                context_patterns = [f"no {vuln_name}", f"no evidence of {vuln_name}",
                                   f"no {short_name}", f"{vuln_name} was not", f"not vulnerable to {vuln_name}"]
                is_negative = any(cp in all_text for cp in context_patterns)
                if not is_negative:
                    corrections.append(f"LLM mentions '{vuln_name}' but no such finding exists in scan data")

        # --- 3. Score consistency ---
        score_str = str(scan_results.get("audit", {}).get("score", score))
        if f"score" in all_text:
            for m in _re.finditer(r'score\s*(?:of|:|\s)\s*(\d+)', all_text):
                claimed_score = m.group(1)
                if claimed_score != score_str and claimed_score != str(score):
                    corrections.append(f"LLM claims score {claimed_score}, actual: {score}")

        # --- 4. TLS grade check ---
        actual_grade = scan_results.get("tls_grading", {}).get("grade", "")
        if actual_grade:
            grade_claims = _re.findall(r'(?:tls|ssl)\s+grade\s*(?:of|:|\s)\s*([A-F]\+?)', all_text, _re.IGNORECASE)
            for claimed_grade in grade_claims:
                if claimed_grade.upper() != actual_grade.upper():
                    corrections.append(f"LLM claims TLS grade '{claimed_grade}', actual: '{actual_grade}'")

        # --- 5. WAF status check ---
        waf_detected = scan_results.get("waf", {}).get("waf_detected", False)
        waf_name = scan_results.get("waf", {}).get("waf_name", "")
        if "no waf" in all_text or "no web application firewall" in all_text:
            if waf_detected:
                corrections.append(f"LLM claims no WAF, but {waf_name} was detected")
        if ("waf detected" in all_text or "waf is present" in all_text or "waf in place" in all_text):
            if not waf_detected:
                corrections.append("LLM claims WAF is present, but none was detected")

        # --- 6. Browser verification consistency ---
        browser = scan_results.get("browser_verification", {})
        debunked_count = len(browser.get("debunked_paths", [])) + len(browser.get("debunked_xss", []))
        if debunked_count > 0:
            # Check if LLM still claims debunked findings as real
            for d in browser.get("debunked_xss", []):
                vector = d.get("vector_name", "").lower()
                if vector and vector in all_text:
                    # Check it's not mentioned as "debunked" or "false positive"
                    if "false positive" not in all_text and "debunked" not in all_text:
                        corrections.append(f"LLM presents debunked XSS '{d.get('vector_name')}' as real finding")

        # --- 7. Key validation consistency ---
        secret_val = scan_results.get("secret_validation", {})
        dead_keys = secret_val.get("dead_or_fake", [])
        if dead_keys and ("live key" in all_text or "active key" in all_text or "live secret" in all_text):
            if secret_val.get("live_count", 0) == 0:
                corrections.append("LLM claims live/active keys exist, but all keys were validated as DEAD or INVALID")

        return corrections

    corrections = fact_check_llm(llm_content, issues, all_results)

    if corrections:
        print(f"  [!] FACT-CHECK: {len(corrections)} issues found in LLM output:", flush=True)
        for c in corrections:
            print(f"      - {c}", flush=True)

        # Add fact-check warning banner to executive summary
        warning_html = (
            '<div style="margin: 15px 0; padding: 12px; background: #fff3cd; '
            'border-left: 4px solid #ffc107; border-radius: 4px; font-size: 13px;">'
            '<strong style="color: #856404;">&#x26a0; Fact-Check Notice:</strong> '
            'The AI-generated narrative contained claims that deviate from scan data. '
            'Corrections: <ul style="margin-top:6px;">'
        )
        for c in corrections:
            warning_html += f"<li>{_esc(c)}</li>"
        warning_html += "</ul></div>"

        llm_content["executive_summary"] = warning_html + llm_content.get("executive_summary", "")
    else:
        print(f"  [OK] Fact-check passed — LLM output consistent with scan data.", flush=True)

    print("  [9/10] Generating HTML...", flush=True)

    # Build HTML
    html = REPORT_TEMPLATE.format(
        domain=domain,
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        company=company,
        score=score,
        score_class=score_class,
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        executive_summary=llm_content.get("executive_summary", ""),
        domain_info_html=build_domain_info_html(whois_result, ssl_result, dns_result),
        domain_info_narrative=llm_content.get("domain_info_narrative", ""),
        findings_narrative=llm_content.get("findings_narrative", ""),
        findings_html=build_findings_html(issues),
        investigation_html=investigation_html,
        investigation_narrative=llm_content.get("investigation_narrative", ""),
        tls_html=build_tls_html(ssl_result, audit_result.get("tls_details", {})),
        tls_narrative=llm_content.get("tls_narrative", ""),
        headers_html=build_headers_html(audit_result.get("header_analysis", {})),
        headers_narrative=llm_content.get("headers_narrative", ""),
        server_config_narrative=llm_content.get("server_config_narrative", ""),
        nginx_config=audit_result.get("nginx_config_snippet", "# No changes needed"),
        apache_config=audit_result.get("apache_config_snippet", "# No changes needed"),
        attack_scenarios_html=llm_content.get("attack_scenarios", build_attack_scenarios_html(issues)),
        llm_analysis_html=llm_content.get("deep_analysis", ""),
        proposal_items=llm_content.get("recommended_actions", ""),
    )

    # --- Append Leaked Secrets section (env + JS secrets) ---
    leaked_html = ""
    env_leaks = paths_result.get("env_leaks", [])
    js_secrets = js_secrets_result.get("secrets_found", [])

    if env_leaks or js_secrets:
        leaked_html += '<div class="section" style="page-break-before: always;">\n'
        leaked_html += '<h2 style="color:#c0392b; border-bottom: 3px solid #c0392b; padding-bottom: 8px;">Leaked Secrets &mdash; Detail</h2>\n'

        # .env file leaks
        for env in env_leaks:
            leaked_html += f'<h3 style="margin-top:20px; color:#c0392b;">File: <code>{env["file"]}</code> &mdash; {env["total_vars"]} variables ({env["sensitive_vars"]} sensitive)</h3>\n'
            leaked_html += '<table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:13px;">\n'
            leaked_html += '<thead><tr style="background:#c0392b; color:#fff;">'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:5%;">#</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:30%;">Key</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:20%;">Type</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:30%;">Value (masked)</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:15%;">Length</th>'
            leaked_html += '</tr></thead><tbody>\n'
            for i, s in enumerate(env["secrets"], 1):
                bg = "#fff5f5" if s["sensitive"] else "#fff"
                weight = "bold" if s["sensitive"] else "normal"
                leaked_html += f'<tr style="background:{bg};">'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{i}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-weight:{weight};"><code>{s["key"]}</code></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{s["type"]}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-family:monospace;">{s["value_preview"]}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{s["full_length"]} chars</td>'
                leaked_html += '</tr>\n'
            leaked_html += '</tbody></table>\n'

        # JS secrets
        if js_secrets:
            leaked_html += f'<h3 style="margin-top:20px; color:#c0392b;">JavaScript Secrets &mdash; {len(js_secrets)} found in {js_secrets_result.get("js_files_scanned", 0)} files</h3>\n'
            leaked_html += '<table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:13px;">\n'
            leaked_html += '<thead><tr style="background:#c0392b; color:#fff;">'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:5%;">#</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:25%;">Type</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:30%;">File</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:40%;">Value (preview)</th>'
            leaked_html += '</tr></thead><tbody>\n'
            for i, s in enumerate(js_secrets, 1):
                bg = "#fff5f5" if i % 2 else "#fff"
                leaked_html += f'<tr style="background:{bg};">'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{i}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><strong>{s.get("type", "Unknown")}</strong></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><code>{s.get("location", "")}</code></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-family:monospace; word-break:break-all;">{s.get("value_preview", "")}&hellip;</td>'
                leaked_html += '</tr>\n'
            leaked_html += '</tbody></table>\n'

        # Secret validation results
        validated = secret_validation_result.get("validated", [])
        dead_keys = secret_validation_result.get("dead_or_fake", [])
        inconclusive_keys = secret_validation_result.get("inconclusive", [])
        all_validated = validated + dead_keys + inconclusive_keys

        if all_validated:
            leaked_html += f'<h3 style="margin-top:20px; color:#2c3e50;">Key Validation Results &mdash; {len(validated)} LIVE, {len(dead_keys)} dead, {len(inconclusive_keys)} inconclusive</h3>\n'
            leaked_html += '<table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:13px;">\n'
            leaked_html += '<thead><tr style="background:#2c3e50; color:#fff;">'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:5%;">#</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:15%;">Status</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:15%;">Type</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:15%;">Source</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:10%;">Risk</th>'
            leaked_html += '<th style="padding:8px 12px; text-align:left; width:40%;">Details</th>'
            leaked_html += '</tr></thead><tbody>\n'

            STATUS_COLORS = {
                "LIVE": ("#c0392b", "#fff5f5", "&#x26a0; LIVE"),
                "LIKELY_LIVE": ("#e67e22", "#fef9e7", "&#x26a0; LIKELY LIVE"),
                "RESTRICTED": ("#f39c12", "#fef9e7", "RESTRICTED"),
                "EXPIRED": ("#27ae60", "#eafaf1", "EXPIRED"),
                "DEAD": ("#27ae60", "#eafaf1", "DEAD"),
                "INVALID_FORMAT": ("#95a5a6", "#f8f9fa", "INVALID"),
                "PLACEHOLDER": ("#95a5a6", "#f8f9fa", "PLACEHOLDER"),
                "TEST_KEY": ("#3498db", "#ebf5fb", "TEST KEY"),
                "PUBLIC_KEY": ("#3498db", "#ebf5fb", "PUBLIC KEY"),
                "LOCAL_ONLY": ("#27ae60", "#eafaf1", "LOCAL ONLY"),
                "TEMPORARY": ("#e67e22", "#fef9e7", "TEMPORARY"),
                "PATTERN_MATCH": ("#95a5a6", "#f8f9fa", "PATTERN"),
            }

            # Sort: LIVE first, then LIKELY_LIVE, then rest
            priority = {"LIVE": 0, "LIKELY_LIVE": 1, "TEMPORARY": 2, "RESTRICTED": 3}
            all_sorted = sorted(all_validated, key=lambda x: priority.get(x["status"], 9))

            for i, v in enumerate(all_sorted, 1):
                color, bg, label = STATUS_COLORS.get(v["status"], ("#666", "#fff", v["status"]))
                risk = v.get("risk_level", "?")
                risk_color = {"CRITICAL": "#c0392b", "HIGH": "#e67e22", "MEDIUM": "#f39c12", "LOW": "#27ae60", "NONE": "#95a5a6"}.get(risk, "#666")
                leaked_html += f'<tr style="background:{bg};">'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{i}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><strong style="color:{color};">{label}</strong></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{_esc(v.get("type", ""))}</td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><code>{_esc(v.get("source", ""))}</code></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><strong style="color:{risk_color};">{risk}</strong></td>'
                leaked_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-size:12px;">{_esc(v.get("reason", ""))}</td>'
                leaked_html += '</tr>\n'

            leaked_html += '</tbody></table>\n'

        # Immediate actions box
        leaked_html += '<div style="margin-top:20px; padding:16px; background:#fff5f5; border-left:4px solid #c0392b; border-radius:4px;">\n'
        leaked_html += '<strong style="color:#c0392b;">Recommended Immediate Actions:</strong>\n'
        leaked_html += '<ol style="margin-top:8px; padding-left:20px;">\n'
        if env_leaks:
            leaked_html += '<li>Block access to ALL .env files via web server configuration immediately.</li>\n'
            leaked_html += '<li>Rotate ALL credentials, API keys, and tokens found in exposed .env files.</li>\n'
            leaked_html += '<li>Audit server access logs to determine if these files were accessed by unauthorized parties.</li>\n'
        if js_secrets:
            leaked_html += '<li>Remove all secrets from frontend JavaScript bundles.</li>\n'
            leaked_html += '<li>Implement server-side API proxies instead of exposing keys in client code.</li>\n'
        leaked_html += '<li>Add secret scanning to your CI/CD pipeline (e.g. <code>gitleaks</code>, <code>trufflehog</code>).</li>\n'
        leaked_html += '</ol></div>\n'
        leaked_html += '</div>\n'

    # Inject before footer
    if leaked_html:
        html = html.replace("<!-- FOOTER -->", leaked_html + "\n<!-- FOOTER -->")

    # --- Append Browser Evidence section with screenshots ---
    screenshots = browser_result.get("screenshots", [])
    if screenshots:
        evidence_html = '<div class="section" style="page-break-before: always;">\n'
        evidence_html += '<h2 style="border-bottom: 3px solid #2c3e50; padding-bottom: 8px;">Browser Verification &mdash; Evidence</h2>\n'
        evidence_html += f'<p style="margin: 12px 0; color:#666;">{browser_result.get("summary", "")}</p>\n'

        # Debunked summary
        debunked_paths = browser_result.get("debunked_paths", [])
        debunked_xss = browser_result.get("debunked_xss", [])
        if debunked_paths or debunked_xss:
            evidence_html += '<div style="margin: 12px 0; padding: 12px; background: #eafaf1; border-left: 4px solid #27ae60; border-radius: 4px;">\n'
            evidence_html += '<strong style="color:#27ae60;">False Positives Eliminated by Browser:</strong>\n<ul style="margin-top:6px;">\n'
            for d in debunked_paths:
                evidence_html += f'<li><code>{d["path"]}</code> &mdash; {d["reason"]}</li>\n'
            for d in debunked_xss:
                evidence_html += f'<li>XSS {d.get("vector_name", "")}: {d.get("reason", "")}</li>\n'
            evidence_html += '</ul></div>\n'

        # Verified summary
        verified_paths = browser_result.get("verified_paths", [])
        verified_xss = browser_result.get("verified_xss", [])
        if verified_paths or verified_xss:
            evidence_html += '<div style="margin: 12px 0; padding: 12px; background: #fff5f5; border-left: 4px solid #c0392b; border-radius: 4px;">\n'
            evidence_html += '<strong style="color:#c0392b;">Confirmed by Browser:</strong>\n<ul style="margin-top:6px;">\n'
            for v in verified_paths:
                evidence_html += f'<li><code>{v["path"]}</code> &mdash; {v["reason"]}</li>\n'
            for v in verified_xss:
                evidence_html += f'<li>XSS {v.get("vector_name", "")}: {v.get("reason", "")}</li>\n'
            evidence_html += '</ul></div>\n'

        # Network traffic summary
        network = browser_result.get("network", {})
        tp_domains = list(set(tp["domain"] for tp in network.get("third_party_requests", [])))
        api_calls = network.get("api_calls", [])
        mixed = network.get("mixed_content", [])
        ws = network.get("websocket_urls", [])

        if network.get("total_requests", 0) > 0:
            evidence_html += '<h3 style="margin-top:20px;">Network Traffic Analysis</h3>\n'
            evidence_html += '<table style="width:100%; border-collapse:collapse; font-size:13px;">\n'
            evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Total Requests</th><td style="padding:6px; border-bottom:1px solid #ddd;">{network["total_requests"]}</td></tr>\n'
            evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">API Calls (XHR/Fetch)</th><td style="padding:6px; border-bottom:1px solid #ddd;">{len(api_calls)}</td></tr>\n'
            evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Third-Party Domains</th><td style="padding:6px; border-bottom:1px solid #ddd;">{len(tp_domains)}</td></tr>\n'
            if tp_domains:
                evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">&nbsp;</th><td style="padding:6px; border-bottom:1px solid #ddd; font-size:12px;">{", ".join(tp_domains[:15])}</td></tr>\n'
            if mixed:
                evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd; color:#c0392b;">Mixed Content (HTTP!)</th><td style="padding:6px; border-bottom:1px solid #ddd; color:#c0392b;">{len(mixed)} insecure resources</td></tr>\n'
            if ws:
                evidence_html += f'<tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">WebSocket Connections</th><td style="padding:6px; border-bottom:1px solid #ddd;">{len(ws)}</td></tr>\n'
            evidence_html += '</table>\n'

        # Console output
        console = browser_result.get("console", {})
        if console.get("errors") or console.get("csp_violations"):
            evidence_html += '<h3 style="margin-top:20px;">Console Output</h3>\n'
            if console.get("csp_violations"):
                evidence_html += f'<div style="padding:8px; background:#fff5f5; border-left:3px solid #c0392b; margin:8px 0; font-size:12px;"><strong>CSP Violations ({len(console["csp_violations"])}):</strong><br>'
                for v in console["csp_violations"][:5]:
                    evidence_html += f'<code>{_esc(v[:200])}</code><br>'
                evidence_html += '</div>\n'
            if console.get("errors"):
                evidence_html += f'<div style="padding:8px; background:#fef9e7; border-left:3px solid #f39c12; margin:8px 0; font-size:12px;"><strong>JS Errors ({len(console["errors"])}):</strong><br>'
                for e in console["errors"][:5]:
                    evidence_html += f'<code>{_esc(e[:200])}</code><br>'
                evidence_html += '</div>\n'

        # Browser storage
        storage = browser_result.get("storage", {})
        storage_secrets = storage.get("localStorage_secrets", []) + storage.get("sessionStorage_secrets", [])
        if storage_secrets:
            evidence_html += '<h3 style="margin-top:20px; color:#c0392b;">Secrets in Browser Storage</h3>\n'
            evidence_html += '<table style="width:100%; border-collapse:collapse; font-size:13px;">\n'
            evidence_html += '<thead><tr style="background:#c0392b; color:#fff;"><th style="padding:6px 12px;">Storage</th><th style="padding:6px 12px;">Key</th><th style="padding:6px 12px;">Value (preview)</th><th style="padding:6px 12px;">Length</th></tr></thead><tbody>\n'
            for s in storage_secrets:
                storage_type = "localStorage" if s in storage.get("localStorage_secrets", []) else "sessionStorage"
                evidence_html += f'<tr style="background:#fff5f5;"><td style="padding:6px 12px; border-bottom:1px solid #eee;">{storage_type}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><code>{_esc(s["key"])}</code></td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-family:monospace;">{_esc(s["value_preview"])}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{s["length"]} chars</td></tr>\n'
            evidence_html += '</tbody></table>\n'

        # Cookies after JS
        cookies_js = browser_result.get("cookies_after_js", [])
        insecure_cookies = [c for c in cookies_js if c.get("issues")]
        if insecure_cookies:
            evidence_html += '<h3 style="margin-top:20px;">Cookie Audit (post-JavaScript)</h3>\n'
            evidence_html += '<table style="width:100%; border-collapse:collapse; font-size:13px;">\n'
            evidence_html += '<thead><tr style="background:#2c3e50; color:#fff;"><th style="padding:6px 12px;">Cookie</th><th style="padding:6px 12px;">Domain</th><th style="padding:6px 12px;">Secure</th><th style="padding:6px 12px;">HttpOnly</th><th style="padding:6px 12px;">SameSite</th><th style="padding:6px 12px;">Session?</th><th style="padding:6px 12px;">Issues</th></tr></thead><tbody>\n'
            for c in insecure_cookies:
                bg = "#fff5f5" if c["is_session"] else "#fff"
                evidence_html += f'<tr style="background:{bg};">'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;"><code>{_esc(c["name"])}</code></td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{_esc(c.get("domain",""))}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{"Yes" if c["secure"] else "<strong style=color:#c0392b>No</strong>"}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{"Yes" if c["httpOnly"] else "<strong style=color:#c0392b>No</strong>"}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{c.get("sameSite","?")}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee;">{"Yes" if c["is_session"] else "No"}</td>'
                evidence_html += f'<td style="padding:6px 12px; border-bottom:1px solid #eee; font-size:12px;">{", ".join(c["issues"])}</td>'
                evidence_html += '</tr>\n'
            evidence_html += '</tbody></table>\n'

        # Screenshots
        for i, ss in enumerate(screenshots):
            evidence_html += f'<div style="margin-top: 20px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">\n'
            evidence_html += f'<div style="background: #2c3e50; color: #fff; padding: 8px 16px; font-size: 13px;"><strong>Screenshot {i+1}:</strong> {ss["description"]}</div>\n'
            evidence_html += f'<img src="data:image/png;base64,{ss["base64_png"]}" style="width:100%; display:block;" alt="{ss["description"]}" />\n'
            evidence_html += '</div>\n'

        evidence_html += '</div>\n'
        html = html.replace("<!-- FOOTER -->", evidence_html + "\n<!-- FOOTER -->")

    # Save
    if not output_path:
        safe_domain = domain.replace(".", "_").replace(":", "_")
        output_path = f"report_{safe_domain}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [10/10] Report saved: {output_path}")
    print(f"\n  Open in browser and print as PDF (Ctrl+P -> PDF).\n")

    return output_path


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Security Audit Report Generator")
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("--output", "-o", help="Output HTML file path")
    parser.add_argument("--company", "-c", default="Auftraggeber", help="Company name for report")
    args = parser.parse_args()

    url = args.url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    await generate_report(url, company=args.company, output_path=args.output)


if __name__ == "__main__":
    asyncio.run(main())
