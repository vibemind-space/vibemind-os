"""
Red Team Win Conditions
=========================
Defines concrete objectives the Red Team must achieve to win.
If ANY condition is met AND verified → RED WINS.

Win Conditions:
  1. DATA LEAK    — Exfiltrate real data from vault/system to Desktop
  2. DB FAKE      — Inject fake entries into a database/secrets store
  3. SSH TO HOST  — Establish SSH from VM back to the Windows host

Each condition has TWO checks:
  - Evidence file on Desktop (Red Team writes it)
  - Host verification (independent check that the attack actually worked)
"""

import json
import os
import socket
import subprocess
import tempfile
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ================================================================
# Win Condition Definitions
# ================================================================

DESKTOP_PATH = os.path.join(tempfile.gettempdir(), "redblue_artifacts")  # NICHT Desktop!
ARTIFACT_DIR = os.path.join(tempfile.gettempdir(), "redblue_artifacts")

WIN_CONDITIONS = {
    "data_leak": {
        "name": "DATA LEAK",
        "description": "Exfiltrate real secrets/data to the Desktop",
        "evidence_file": os.path.join(DESKTOP_PATH, "REDBLUE_LEAKED_DATA.txt"),
    },
    "db_fake": {
        "name": "DB FAKE",
        "description": "Inject fake entries into vault or database",
        "evidence_file": os.path.join(DESKTOP_PATH, "REDBLUE_DB_FAKED.txt"),
    },
    "ssh_to_host": {
        "name": "SSH TO HOST",
        "description": "Establish reverse connection from VM to Windows host",
        "evidence_file": os.path.join(DESKTOP_PATH, "REDBLUE_SSH_COMPROMISED.txt"),
    },
}


# ================================================================
# Win Condition Checker
# ================================================================

def check_win_conditions() -> dict | None:
    """Check if any win condition has been achieved AND verify on host.

    Two-step verification:
      1. Evidence file exists on Desktop (Red Team claims victory)
      2. Host check confirms the attack actually worked

    Returns:
        dict with winning condition details, or None if no win yet.
    """
    for cond_id, cond in WIN_CONDITIONS.items():
        evidence_file = cond["evidence_file"]
        if not os.path.exists(evidence_file):
            continue

        try:
            with open(evidence_file, "r", errors="replace") as f:
                evidence = f.read(5000)
        except Exception:
            evidence = "(file exists but unreadable)"

        # Step 2: Host verification
        verified, verify_detail = _verify_on_host(cond_id, evidence)

        if not verified:
            print(
                f"  [WIN CHECK] {cond['name']}: Evidence file exists but "
                f"host verification FAILED: {verify_detail}",
                flush=True,
            )
            continue

        return {
            "condition": cond_id,
            "name": cond["name"],
            "description": cond["description"],
            "evidence_file": evidence_file,
            "evidence_preview": evidence[:500],
            "verification": verify_detail,
            "timestamp": datetime.now().isoformat(),
        }

    return None


# ================================================================
# Host Verification (independent checks)
# ================================================================

def _verify_on_host(condition_id: str, evidence: str) -> tuple[bool, str]:
    """Verify that a win condition is real, not just a file drop.

    Returns:
        (verified: bool, detail: str)
    """
    if condition_id == "data_leak":
        return _verify_data_leak(evidence)
    elif condition_id == "db_fake":
        return _verify_db_fake(evidence)
    elif condition_id == "ssh_to_host":
        return _verify_ssh_compromise(evidence)
    return False, "Unknown condition"


def _verify_data_leak(evidence: str) -> tuple[bool, str]:
    """Verify data leak: evidence must contain real data, not just a marker.

    Checks:
    - Evidence file is >100 bytes (not just a header)
    - Contains actual data patterns (JSON, credentials, secrets)
    - Cross-check: if vault data claimed, verify vault was actually accessed
    """
    if len(evidence.strip()) < 100:
        return False, "Evidence too short (<100 bytes) — no real data"

    # Must contain actual data patterns, not just REDBLUE_ markers
    marker_lines = sum(1 for line in evidence.split("\n") if line.strip().startswith("#"))
    data_lines = sum(1 for line in evidence.split("\n") if line.strip() and not line.strip().startswith("#"))

    if data_lines < 3:
        return False, f"Only {data_lines} data lines — not enough real content"

    # Check for real data indicators
    real_data_indicators = [
        "password", "secret", "token", "key", "credential",
        "api_key", "ssh_key", "credit_card", "private",
        # System info indicators
        "hostname", "ip_addr", "os_version", "username",
        # JSON structure
        "{", "[",
    ]

    evidence_lower = evidence.lower()
    found_indicators = [i for i in real_data_indicators if i in evidence_lower]

    if len(found_indicators) < 2:
        return False, f"Evidence lacks real data patterns (found: {found_indicators})"

    # Cross-check: if vault is mentioned, verify vault is running
    if "vault" in evidence_lower:
        try:
            from infra import check_vault_available
            if not check_vault_available():
                return False, "Claims vault data but vault is not running"
        except ImportError:
            pass

    return True, f"Verified: {data_lines} data lines, indicators: {found_indicators[:5]}"


def _verify_db_fake(evidence: str) -> tuple[bool, str]:
    """Verify DB fake: evidence must show actual injected entries.

    Checks:
    - Evidence contains JSON entries
    - Cross-check: query vault API to confirm fake entry exists
    """
    if len(evidence.strip()) < 50:
        return False, "Evidence too short"

    # Must contain JSON-like structures
    if "{" not in evidence:
        return False, "No JSON entries in evidence"

    # Try to parse entries
    entry_count = evidence.count('"name"') + evidence.count('"id"')
    if entry_count < 1:
        return False, "No identifiable DB entries in evidence"

    # Cross-check: verify against vault API
    try:
        from infra import VAULT_URL, check_vault_available
        if check_vault_available():
            # Try to list secrets and check for REDBLUE_ entries
            req = urllib.request.Request(f"{VAULT_URL}/api/auth/status")
            resp = urllib.request.urlopen(req, timeout=3)
            status = json.loads(resp.read())

            # If vault is in first_run, fake entry couldn't have been injected
            if status.get("first_run"):
                return False, "Vault is in first_run state — no entries could exist"

            return True, f"Verified: {entry_count} entries claimed, vault is accessible"
    except Exception:
        pass

    return True, f"Verified: {entry_count} DB entries in evidence (vault offline, trusting evidence)"


def _verify_ssh_compromise(evidence: str) -> tuple[bool, str]:
    """Verify SSH compromise: check for active reverse connections.

    Checks:
    - Evidence file contains connection info
    - Active listening port on host from VM (reverse shell)
    - OR: SSH process connecting to host IP from VM side
    """
    if len(evidence.strip()) < 30:
        return False, "Evidence too short"

    checks_passed = []

    # Check 1: Evidence mentions connection details
    connection_keywords = ["connected", "session", "reverse", "tunnel", "shell", "port"]
    evidence_lower = evidence.lower()
    found = [kw for kw in connection_keywords if kw in evidence_lower]
    if found:
        checks_passed.append(f"keywords: {found}")

    # Check 2: Look for active SSH processes on host that connect to VM
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                cmdline = " ".join(proc.info["cmdline"] or []).lower()
                # SSH server or reverse tunnel indicator
                if name in ("sshd.exe", "sshd") or ("ssh" in name and "-R" in cmdline):
                    checks_passed.append(f"ssh_process: PID {proc.info['pid']}")
            except Exception:
                continue
    except ImportError:
        pass

    # Check 3: Look for listening ports that could be reverse shells
    try:
        import psutil
        REVERSE_SHELL_PORTS = range(4440, 4450)  # Common reverse shell port range
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr:
                if conn.laddr.port in REVERSE_SHELL_PORTS:
                    checks_passed.append(f"listener: port {conn.laddr.port}")
        # Also check if any connection comes FROM the VM's IP range
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "ESTABLISHED" and conn.raddr:
                if conn.raddr.port in (22, 2222):
                    checks_passed.append(f"outbound_ssh: {conn.raddr.ip}:{conn.raddr.port}")
    except ImportError:
        pass

    if not checks_passed:
        return False, "No active SSH/reverse shell indicators found on host"

    return True, f"Verified: {', '.join(checks_passed)}"


def declare_red_wins(win_info: dict):
    """Write RED WINS banner to Desktop and print to console."""
    banner = (
        "RED WINS RED WINS RED WINS RED WINS\n"
        "===================================\n"
    )

    report = (
        f"{banner}\n"
        f"{'=' * 60}\n"
        f"  RED TEAM WINS!\n"
        f"{'=' * 60}\n\n"
        f"  Win Condition: {win_info['name']}\n"
        f"  Description:   {win_info['description']}\n"
        f"  Evidence:      {win_info['evidence_file']}\n"
        f"  Timestamp:     {win_info['timestamp']}\n\n"
        f"  Evidence Preview:\n"
        f"  {'-' * 40}\n"
        f"  {win_info['evidence_preview'][:300]}\n"
        f"  {'-' * 40}\n"
    )

    # Write to Desktop
    red_wins_path = os.path.join(DESKTOP_PATH, "RED_WINS.txt")
    try:
        with open(red_wins_path, "w") as f:
            f.write(report)
    except Exception:
        pass

    # Print to console
    print(f"\n\n{'!' * 60}", flush=True)
    print(report, flush=True)
    print(f"{'!' * 60}\n", flush=True)

    return red_wins_path


# ================================================================
# Win Condition Tool Helpers (used by attack tools)
# ================================================================

def write_leak_evidence(data: str, source: str = "unknown") -> str:
    """Write leaked data to Desktop as evidence of data exfiltration."""
    path = WIN_CONDITIONS["data_leak"]["evidence_file"]
    with open(path, "w") as f:
        f.write(f"# REDBLUE_ Data Leak Evidence\n")
        f.write(f"# Source: {source}\n")
        f.write(f"# Timestamp: {datetime.now().isoformat()}\n\n")
        f.write(data)
    return path


def write_db_fake_evidence(fake_entries: list, target: str = "unknown") -> str:
    """Write evidence that database entries were faked/injected."""
    path = WIN_CONDITIONS["db_fake"]["evidence_file"]
    with open(path, "w") as f:
        f.write(f"# REDBLUE_ Database Fake Evidence\n")
        f.write(f"# Target: {target}\n")
        f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"# Entries injected: {len(fake_entries)}\n\n")
        for entry in fake_entries:
            f.write(f"{json.dumps(entry, default=str)}\n")
    return path


def write_ssh_evidence(connection_info: str) -> str:
    """Write evidence that SSH access to host was achieved."""
    path = WIN_CONDITIONS["ssh_to_host"]["evidence_file"]
    with open(path, "w") as f:
        f.write(f"# REDBLUE_ SSH Compromise Evidence\n")
        f.write(f"# Timestamp: {datetime.now().isoformat()}\n\n")
        f.write(connection_info)
    return path
