"""
Integrated Detection Pipeline
================================
Connects poc_os_shield, poc_log_analyzer, poc_forensics, and poc_alerter
into a unified detection pipeline with cross-source correlation.

Usage:
  from pipeline import run_integrated_scan
  result = await run_integrated_scan(baseline=None, hours=24, alert_enabled=False)
"""

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime

# Add parent paths for cross-module imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _subdir in ("os_shield", "log_analyzer", "forensics", "alerter"):
    _path = os.path.join(_project_root, _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)


# ================================================================
# Unified Finding Format
# ================================================================

@dataclass
class UnifiedFinding:
    id: str
    severity: str        # CRITICAL, HIGH, MEDIUM, LOW, INFO
    category: str        # e.g. privilege_escalation, execution, impact, evasion
    source: str          # os_shield, log_analyzer, forensics
    title: str
    description: str
    timestamp: str       # ISO format
    evidence: dict       # Source-specific evidence


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


# ================================================================
# OS Shield Integration
# ================================================================

async def _run_os_shield_tools(baseline: dict | None = None) -> list[UnifiedFinding]:
    """Run OS Shield detection tools and normalize results."""
    from tools import TOOL_DISPATCH

    findings = []

    # Select tools that don't require special args
    simple_tools = [
        "detect_parent_child_anomalies",
        "detect_encoded_commands",
        "detect_suspicious_paths",
        "detect_lsass_access",
        "detect_token_manipulation",
        "detect_uac_bypass_attempts",
        "detect_service_tampering",
        "detect_wmi_execution",
        "detect_dll_anomalies",
        "detect_script_chains",
        "detect_ransom_indicators",
        "detect_service_disruption",
        # Discovery Detection
        "detect_system_enumeration",
        "detect_network_reconnaissance",
        # Collection Detection
        "detect_collection_activity",
        "detect_sensitive_file_access",
        # Anti-Forensics Detection
        "detect_log_tampering",
        # Credential/Lateral/C2 Detection
        "detect_brute_force_attempts",
        "detect_lateral_movement_tools",
        "detect_c2_channels",
        # External Target Detection
        "detect_vault_attacks",
        "detect_api_scanning",
        "detect_credential_exfiltration",
        "detect_port_scanning",
        "detect_ssh_lateral_movement",
        "detect_supply_chain_tampering",
        "detect_llm_manipulation",
        "detect_abnormal_cleanup",
    ]

    # Tools that need arguments
    param_tools = []
    if baseline:
        pids = json.dumps(baseline.get("baseline_pids", []))
        param_tools.append(("detect_new_processes", {"baseline_pids_json": pids}))
        ips = json.dumps(baseline.get("known_remote_ips", []))
        param_tools.append(("detect_suspicious_connections", {"known_remote_ips_json": ips}))
        autoruns = json.dumps(baseline.get("autorun_entries", []))
        param_tools.append(("check_registry_autoruns", {"baseline_autoruns_json": autoruns}))

    # Also run mass file operations
    simple_tools.append("detect_mass_file_operations")

    # Run all simple tools in parallel
    async def _run_tool(name):
        try:
            fn = TOOL_DISPATCH.get(name)
            if fn:
                return name, await fn()
        except Exception as e:
            return name, {"error": str(e)}
        return name, {}

    async def _run_param_tool(name, kwargs):
        try:
            fn = TOOL_DISPATCH.get(name)
            if fn:
                return name, await fn(**kwargs)
        except Exception as e:
            return name, {"error": str(e)}
        return name, {}

    tasks = [_run_tool(name) for name in simple_tools]
    tasks += [_run_param_tool(name, kwargs) for name, kwargs in param_tools]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for item in results:
        if isinstance(item, Exception):
            continue
        tool_name, result = item
        if not isinstance(result, dict):
            continue

        # Normalize each tool result into findings
        findings.extend(_normalize_os_shield_result(tool_name, result))

    return findings


def _normalize_os_shield_result(tool_name: str, result: dict) -> list[UnifiedFinding]:
    """Convert an OS Shield tool result into UnifiedFindings."""
    findings = []
    now = datetime.now().isoformat()

    # Map tool names to categories
    TOOL_TO_CATEGORY = {
        "detect_parent_child_anomalies": "evasion",
        "detect_encoded_commands": "evasion",
        "detect_suspicious_paths": "evasion",
        "detect_lsass_access": "credential_access",
        "detect_new_processes": "process",
        "detect_suspicious_connections": "lateral_movement",
        "check_registry_autoruns": "persistence",
        "detect_token_manipulation": "privilege_escalation",
        "detect_uac_bypass_attempts": "privilege_escalation",
        "detect_service_tampering": "privilege_escalation",
        "detect_wmi_execution": "execution",
        "detect_dll_anomalies": "execution",
        "detect_script_chains": "execution",
        "detect_mass_file_operations": "impact",
        "detect_ransom_indicators": "impact",
        "detect_service_disruption": "impact",
        "detect_data_exfiltration": "exfiltration",
        "detect_beaconing": "lateral_movement",
        "detect_system_enumeration": "discovery",
        "detect_network_reconnaissance": "discovery",
        "detect_collection_activity": "collection",
        "detect_sensitive_file_access": "collection",
        "detect_log_tampering": "defense_evasion",
        "detect_brute_force_attempts": "credential_access",
        "detect_lateral_movement_tools": "lateral_movement",
        "detect_c2_channels": "c2",
        "detect_vault_attacks": "vault_attack",
        "detect_api_scanning": "reconnaissance",
        "detect_credential_exfiltration": "credential_access",
        "detect_port_scanning": "reconnaissance",
        "detect_ssh_lateral_movement": "lateral_movement",
        "detect_supply_chain_tampering": "supply_chain",
        "detect_llm_manipulation": "llm_attack",
        "detect_abnormal_cleanup": "impact",
    }

    category = TOOL_TO_CATEGORY.get(tool_name, "unknown")

    # Extract findings from common result patterns
    finding_arrays = [
        "anomalies", "suspicious_commands", "suspicious_processes",
        "suspicious_access", "suspicious_tokens", "suspicious_dlls",
        "suspicious_scripts", "script_chains", "wmi_spawned_processes",
        "wmic_commands", "new_processes", "suspicious_new",
        "registry_anomalies", "process_chains", "tampered_services",
        "disrupted_tasks", "encrypted_files", "ransom_notes",
        "large_transfers", "potential_beacons", "rapid_modifications",
        "affected_directories",
        # New detection tools
        "enumeration_processes", "recon_indicators", "discovery_files",
        "collection_indicators", "sensitive_files",
        "tampering_indicators", "timestomped_files",
        "brute_force_indicators", "lateral_movement_indicators",
        "c2_indicators", "suspicious_listeners",
        # External target detection
        "vault_indicators", "scan_indicators", "exfil_indicators",
        "port_scan_indicators", "ssh_indicators",
        "supply_chain_indicators", "llm_indicators", "cleanup_indicators",
    ]

    for key in finding_arrays:
        items = result.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            severity = item.get("severity", "MEDIUM")
            title = item.get("reason", item.get("title", f"{tool_name}: {key}"))
            desc = item.get("description", json.dumps(item, default=str)[:300])

            findings.append(UnifiedFinding(
                id=str(uuid.uuid4())[:8],
                severity=severity,
                category=category,
                source="os_shield",
                title=title[:200],
                description=desc[:500],
                timestamp=now,
                evidence=item,
            ))

    # If no array findings but there's a warning, create a single finding
    if not findings and result.get("warning"):
        findings.append(UnifiedFinding(
            id=str(uuid.uuid4())[:8],
            severity="MEDIUM",
            category=category,
            source="os_shield",
            title=result["warning"][:200],
            description=result["warning"],
            timestamp=now,
            evidence={"tool": tool_name, "warning": result["warning"]},
        ))

    return findings


# ================================================================
# Log Analyzer Integration
# ================================================================

async def _run_log_analyzer(hours: int = 24) -> list[UnifiedFinding]:
    """Run log analyzer tools and normalize results."""
    findings = []

    try:
        # Import log analyzer tools
        log_tools_path = os.path.join(_project_root, "log_analyzer")
        if log_tools_path not in sys.path:
            sys.path.insert(0, log_tools_path)

        from tools import detect_brute_force, detect_priv_escalation, detect_new_services

        results = await asyncio.gather(
            detect_brute_force(hours=hours),
            detect_priv_escalation(hours=hours),
            detect_new_services(hours=hours),
            return_exceptions=True,
        )

        tool_names = ["brute_force", "priv_escalation", "new_services"]
        categories = ["credential_access", "privilege_escalation", "persistence"]

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            if not isinstance(result, dict):
                continue

            issues = result.get("issues", [])
            for issue in issues:
                findings.append(UnifiedFinding(
                    id=str(uuid.uuid4())[:8],
                    severity=issue.get("severity", "MEDIUM"),
                    category=categories[i],
                    source="log_analyzer",
                    title=issue.get("title", tool_names[i]),
                    description=issue.get("description", ""),
                    timestamp=datetime.now().isoformat(),
                    evidence=issue,
                ))

    except ImportError:
        pass
    except Exception:
        pass

    return findings


# ================================================================
# Forensics Integration
# ================================================================

async def _run_forensics() -> list[UnifiedFinding]:
    """Run forensics tools and normalize results."""
    findings = []

    try:
        forensics_path = os.path.join(_project_root, "forensics")
        if forensics_path not in sys.path:
            sys.path.insert(0, forensics_path)

        # Import with the correct module name
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "forensics_main",
            os.path.join(forensics_path, "main.py"),
        )
        forensics_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(forensics_mod)

        results = await asyncio.gather(
            forensics_mod.parse_prefetch(),
            forensics_mod.parse_powershell_history(),
            forensics_mod.parse_usb_history(),
            return_exceptions=True,
        )

        # Prefetch: look for suspicious executables
        if isinstance(results[0], dict):
            for entry in results[0].get("entries", []):
                prog = entry.get("program", "").lower()
                SUSPICIOUS_PROGS = [
                    "mimikatz", "psexec", "beacon", "cobalt", "rubeus",
                    "sharphound", "bloodhound", "lazagne", "procdump",
                    "redblue_",
                ]
                if any(s in prog for s in SUSPICIOUS_PROGS):
                    findings.append(UnifiedFinding(
                        id=str(uuid.uuid4())[:8],
                        severity="HIGH",
                        category="execution",
                        source="forensics",
                        title=f"Suspicious program in Prefetch: {entry.get('program')}",
                        description=f"Executed at {entry.get('last_modified', 'unknown')}",
                        timestamp=datetime.now().isoformat(),
                        evidence=entry,
                    ))

        # PowerShell history: look for suspicious commands
        if isinstance(results[1], dict):
            for cmd in results[1].get("commands", []):
                cmd_text = cmd.get("command", "").lower() if isinstance(cmd, dict) else str(cmd).lower()
                SUSPICIOUS_PS_CMDS = [
                    "invoke-mimikatz", "invoke-expression", "iex(",
                    "downloadstring", "encodedcommand", "bypass",
                    "new-object net.webclient", "reflection.assembly",
                    "redblue_",
                ]
                if any(s in cmd_text for s in SUSPICIOUS_PS_CMDS):
                    findings.append(UnifiedFinding(
                        id=str(uuid.uuid4())[:8],
                        severity="HIGH",
                        category="execution",
                        source="forensics",
                        title="Suspicious PowerShell command in history",
                        description=cmd_text[:300],
                        timestamp=datetime.now().isoformat(),
                        evidence=cmd if isinstance(cmd, dict) else {"command": cmd_text},
                    ))

        # USB: flag new/unknown devices (informational)
        if isinstance(results[2], dict):
            devices = results[2].get("devices", [])
            if devices:
                findings.append(UnifiedFinding(
                    id=str(uuid.uuid4())[:8],
                    severity="INFO",
                    category="collection",
                    source="forensics",
                    title=f"USB devices detected: {len(devices)}",
                    description=json.dumps(devices[:5], default=str)[:300],
                    timestamp=datetime.now().isoformat(),
                    evidence={"device_count": len(devices), "devices": devices[:5]},
                ))

    except Exception:
        pass

    return findings


# ================================================================
# Correlation Engine
# ================================================================

def _correlate_findings(findings: list[UnifiedFinding]) -> list[dict]:
    """Cross-reference findings from different sources.

    Groups by PID, IP, file path — elevates severity when multiple
    sources confirm the same indicator.
    """
    correlations = []

    # Group by PID
    pid_groups = {}
    for f in findings:
        pid = f.evidence.get("pid")
        if pid:
            pid_groups.setdefault(pid, []).append(f)

    for pid, group in pid_groups.items():
        sources = set(f.source for f in group)
        if len(sources) > 1:
            correlations.append({
                "type": "pid_correlation",
                "pid": pid,
                "sources": list(sources),
                "finding_ids": [f.id for f in group],
                "description": f"PID {pid} flagged by {len(sources)} sources: {', '.join(sources)}",
            })
            # Elevate severity for multi-source matches
            for f in group:
                if SEVERITY_ORDER.get(f.severity, 4) > 0:  # Don't elevate CRITICAL
                    sev_idx = max(0, SEVERITY_ORDER.get(f.severity, 4) - 1)
                    f.severity = list(SEVERITY_ORDER.keys())[sev_idx]

    # Group by category for cross-source enrichment
    category_sources = {}
    for f in findings:
        key = f.category
        category_sources.setdefault(key, set()).add(f.source)

    for cat, sources in category_sources.items():
        if len(sources) > 1:
            correlations.append({
                "type": "category_correlation",
                "category": cat,
                "sources": list(sources),
                "description": f"Category '{cat}' confirmed by multiple sources: {', '.join(sources)}",
            })

    return correlations


# ================================================================
# Main Pipeline
# ================================================================

async def run_integrated_scan(
    baseline: dict | None = None,
    hours: int = 24,
    alert_enabled: bool = False,
) -> dict:
    """Run the full integrated detection pipeline.

    1. OS Shield detection tools (process, network, registry, etc.)
    2. Log Analyzer correlation (brute-force, priv esc, new services)
    3. Forensics check (prefetch, PS history, USB)
    4. Cross-source correlation and severity elevation
    5. Optional alerting via poc_alerter

    Returns:
        Dict with findings, counts, severity breakdown, correlations.
    """
    import time
    start = time.time()

    # Run all three sources in parallel
    os_findings, log_findings, forensics_findings = await asyncio.gather(
        _run_os_shield_tools(baseline),
        _run_log_analyzer(hours),
        _run_forensics(),
        return_exceptions=False,
    )

    # Handle exceptions from gather
    if isinstance(os_findings, Exception):
        os_findings = []
    if isinstance(log_findings, Exception):
        log_findings = []
    if isinstance(forensics_findings, Exception):
        forensics_findings = []

    all_findings = os_findings + log_findings + forensics_findings

    # Correlate across sources
    correlations = _correlate_findings(all_findings)

    # Build severity counts
    by_severity = {s: 0 for s in SEVERITY_ORDER}
    for f in all_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    by_source = {
        "os_shield": len(os_findings),
        "log_analyzer": len(log_findings),
        "forensics": len(forensics_findings),
    }

    # Sort by severity
    all_findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 4))

    # Alerting
    if alert_enabled and any(by_severity.get(s, 0) > 0 for s in ["CRITICAL", "HIGH"]):
        try:
            alerter_path = os.path.join(_project_root, "alerter")
            if alerter_path not in sys.path:
                sys.path.insert(0, alerter_path)

            from alerter import send_alert_batch

            alert_findings = [
                {
                    "severity": f.severity,
                    "title": f.title,
                    "details": f.description,
                    "source": f"pipeline/{f.source}",
                }
                for f in all_findings
                if f.severity in ("CRITICAL", "HIGH")
            ]
            if alert_findings:
                await send_alert_batch(alert_findings, source="detection_pipeline")
        except Exception:
            pass

    duration = round(time.time() - start, 2)

    return {
        "findings": [asdict(f) for f in all_findings],
        "finding_count": len(all_findings),
        "by_severity": by_severity,
        "by_source": by_source,
        "correlations": correlations,
        "scan_duration_seconds": duration,
    }
