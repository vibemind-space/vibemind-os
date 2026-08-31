"""
VM Detection Meta-Tool
=======================
A single meta-tool `scan_vm_threats` that runs 8 security detection checks
plus an IDS heartbeat check against the MultiseatOS VM via SSH, and returns
a consolidated JSON result.

Checks:
  1. _check_vm_backdoors              - Crontab, .bashrc, rogue systemd services
  2. _check_vm_suspicious_processes   - Known attacker tooling (nmap, hydra, etc.)
  3. _check_vm_credential_theft       - /etc/shadow mtime, ~/.ssh changes, tokens in /tmp
  4. _check_vm_network_anomalies      - Suspicious listening ports (4444, 5555, etc.)
  5. _check_vm_log_tampering          - auth.log / syslog zeroed or missing
  6. _check_vault_brute_force         - HTTP check of vault auth failure count
  7. _check_vm_file_changes           - Files newer than stealth baseline
  8. _check_vm_privilege_escalation   - SUID binary count, /etc/sudoers stat
  9. _check_ids_heartbeat             - IDS heartbeat age, decoy/stealth service status
"""

import asyncio
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

import paramiko

# Suppress noisy paramiko logs
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# Import infra constants — resolve path relative to this file's parent
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "offense", "red_blue"))
from infra import (
    VM_SSH_HOST,
    VM_SSH_PORT,
    VM_SSH_USER,
    VM_SSH_PASS,
    VAULT_HOST,
    VAULT_PORT,
)


# ================================================================
# SSH Helpers
# ================================================================

def _ssh_connect() -> paramiko.SSHClient:
    """Open an SSH connection to the VM."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        VM_SSH_HOST,
        port=VM_SSH_PORT,
        username=VM_SSH_USER,
        password=VM_SSH_PASS,
        timeout=10,
        banner_timeout=15,
    )
    return ssh


def _ssh_run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 10) -> str:
    """Run a command over SSH and return stdout as a string."""
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", errors="replace").strip()


# ================================================================
# Check 1: Backdoors
# ================================================================

def _check_vm_backdoors(ssh: paramiko.SSHClient) -> dict:
    """
    Check for persistence mechanisms:
      - crontab -l entries
      - .bashrc containing REDBLUE / reverse / backdoor keywords
      - Rogue systemd services (non-standard units in /etc/systemd/system)
    """
    alerts: list[dict] = []

    # --- crontab ---
    crontab_out = _ssh_run(ssh, "crontab -l 2>/dev/null || true")
    suspicious_cron_keywords = ["bash", "python", "curl", "wget", "nc ", "ncat", "/tmp", "b64", "base64"]
    for line in crontab_out.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if any(kw in stripped.lower() for kw in suspicious_cron_keywords):
            alerts.append({
                "type": "backdoor_crontab",
                "severity": "high",
                "message": f"Suspicious crontab entry: {stripped[:200]}",
            })

    # --- /etc/cron.d/ directory ---
    crond_out = _ssh_run(ssh, "ls /etc/cron.d/ 2>/dev/null || true")
    for entry in crond_out.splitlines():
        entry = entry.strip()
        if entry and entry not in ("e2scrub_all", ".placeholder", "popularity-contest"):
            content = _ssh_run(ssh, f"cat /etc/cron.d/{entry} 2>/dev/null | grep -v '^#' | grep -v '^$' || true")
            if content and any(kw in content.lower() for kw in suspicious_cron_keywords):
                alerts.append({
                    "type": "backdoor_crond",
                    "severity": "high",
                    "message": f"Suspicious /etc/cron.d/{entry}: {content[:200]}",
                })

    # --- .bashrc keywords ---
    bashrc_keywords = ["REDBLUE", "reverse", "backdoor", "nc ", "ncat", "python -c", "perl -e",
                       "base64 -d", "/dev/tcp", "bash -i", "exec "]
    for kw in bashrc_keywords:
        result = _ssh_run(ssh, f"grep -i '{kw}' ~/.bashrc 2>/dev/null || true")
        if result:
            alerts.append({
                "type": "backdoor_bashrc",
                "severity": "critical",
                "message": f"Keyword '{kw}' found in .bashrc: {result[:200]}",
            })

    # --- Rogue systemd services ---
    # List .service files in /etc/systemd/system that are not standard Ubuntu units
    systemd_out = _ssh_run(
        ssh,
        "ls /etc/systemd/system/*.service 2>/dev/null | xargs -I{} basename {} .service || true",
    )
    known_benign = {
        "multi-user", "getty@", "ssh", "cron", "rsyslog", "ufw",
        "snapd", "networkd-dispatcher", "systemd-resolved",
        "apport", "unattended-upgrades",
    }
    for svc in systemd_out.splitlines():
        svc = svc.strip()
        if not svc:
            continue
        if not any(svc.startswith(b) or svc == b for b in known_benign):
            # Check if it's enabled/active
            status = _ssh_run(ssh, f"systemctl is-active {svc} 2>/dev/null || true")
            if status in ("active", "activating"):
                alerts.append({
                    "type": "backdoor_systemd_service",
                    "severity": "high",
                    "message": f"Non-standard active systemd service: {svc}",
                })

    return {
        "check": "vm_backdoors",
        "crontab_raw": crontab_out[:500] if crontab_out else "(empty)",
        "alerts": alerts,
    }


# ================================================================
# Check 2: Suspicious Processes
# ================================================================

def _check_vm_suspicious_processes(ssh: paramiko.SSHClient) -> dict:
    """
    Run `ps aux` on the VM and flag known attacker tooling.
    """
    SUSPICIOUS_NAMES = [
        "nmap", "mimikatz", "lazagne", "procdump",
        "hydra", "john", "hashcat",
    ]

    alerts: list[dict] = []
    ps_out = _ssh_run(ssh, "ps aux --no-headers 2>/dev/null || ps aux", timeout=15)
    matched_processes = []

    for line in ps_out.splitlines():
        line_lower = line.lower()
        for name in SUSPICIOUS_NAMES:
            if name in line_lower:
                alerts.append({
                    "type": "suspicious_process",
                    "severity": "critical",
                    "message": f"Attacker tool detected in process list: '{name}' — {line.strip()[:200]}",
                })
                matched_processes.append(line.strip()[:200])
                break  # avoid duplicate alerts per line

    return {
        "check": "vm_suspicious_processes",
        "total_processes_scanned": len(ps_out.splitlines()),
        "matched_processes": matched_processes,
        "alerts": alerts,
    }


# ================================================================
# Check 3: Credential Theft
# ================================================================

def _check_vm_credential_theft(ssh: paramiko.SSHClient) -> dict:
    """
    - stat /etc/shadow for recent modification
    - Check ~/.ssh/ for unexpected files
    - Find token/secret/vault files in /tmp
    """
    alerts: list[dict] = []

    # --- /etc/shadow mtime ---
    shadow_stat = _ssh_run(ssh, "stat -c '%Y %n' /etc/shadow 2>/dev/null || true")
    if shadow_stat:
        parts = shadow_stat.split()
        if parts:
            try:
                mtime = int(parts[0])
                now = datetime.now(timezone.utc).timestamp()
                age_hours = (now - mtime) / 3600
                if age_hours < 24:
                    alerts.append({
                        "type": "credential_theft_shadow",
                        "severity": "critical",
                        "message": f"/etc/shadow modified {age_hours:.1f}h ago — possible password harvesting.",
                    })
            except ValueError:
                pass

    # --- ~/.ssh/ unexpected files ---
    ssh_files = _ssh_run(ssh, "ls -la ~/.ssh/ 2>/dev/null || true")
    expected_ssh_files = {"authorized_keys", "known_hosts", "id_rsa", "id_rsa.pub",
                          "id_ed25519", "id_ed25519.pub", "config", ".", ".."}
    for line in ssh_files.splitlines():
        parts = line.split()
        if not parts:
            continue
        fname = parts[-1]
        if fname in (".", "..") or fname in expected_ssh_files:
            continue
        # Any unexpected file in ~/.ssh is suspicious
        alerts.append({
            "type": "credential_theft_ssh_file",
            "severity": "high",
            "message": f"Unexpected file in ~/.ssh/: {fname}",
        })

    # --- token/secret/vault files in /tmp ---
    tmp_scan = _ssh_run(
        ssh,
        r"find /tmp -maxdepth 3 -type f \( -iname '*token*' -o -iname '*secret*' -o -iname '*vault*' -o -iname '*credential*' -o -iname '*password*' \) 2>/dev/null || true",
        timeout=15,
    )
    for fpath in tmp_scan.splitlines():
        fpath = fpath.strip()
        if fpath:
            alerts.append({
                "type": "credential_theft_tmp_file",
                "severity": "critical",
                "message": f"Sensitive file found in /tmp: {fpath}",
            })

    return {
        "check": "vm_credential_theft",
        "shadow_stat": shadow_stat[:200] if shadow_stat else "(unreadable)",
        "ssh_dir_listing": ssh_files[:500] if ssh_files else "(empty)",
        "tmp_sensitive_files": tmp_scan.splitlines() if tmp_scan else [],
        "alerts": alerts,
    }


# ================================================================
# Check 4: Network Anomalies
# ================================================================

def _check_vm_network_anomalies(ssh: paramiko.SSHClient) -> dict:
    """
    Run `ss -tlnp` and flag suspicious listening ports:
    4444, 5555, 1337, 6667, 8888, 9999
    """
    SUSPICIOUS_PORTS = {4444, 5555, 1337, 6667, 8888, 9999}
    alerts: list[dict] = []

    ss_out = _ssh_run(ssh, "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null || true", timeout=10)
    flagged_ports = []

    for line in ss_out.splitlines():
        for port in SUSPICIOUS_PORTS:
            if f":{port}" in line or f":{port} " in line:
                alerts.append({
                    "type": "network_anomaly_port",
                    "severity": "critical",
                    "message": f"Suspicious port {port} is listening: {line.strip()[:200]}",
                })
                flagged_ports.append(port)
                break

    return {
        "check": "vm_network_anomalies",
        "ss_output_lines": len(ss_out.splitlines()),
        "flagged_ports": list(set(flagged_ports)),
        "alerts": alerts,
    }


# ================================================================
# Check 5: Log Tampering
# ================================================================

def _check_vm_log_tampering(ssh: paramiko.SSHClient) -> dict:
    """
    Check if auth.log or syslog are 0 bytes or missing — classic sign of log clearing.
    """
    LOG_FILES = [
        "/var/log/auth.log",
        "/var/log/syslog",
        "/var/log/kern.log",
    ]
    alerts: list[dict] = []
    log_status = {}

    for log_path in LOG_FILES:
        stat_out = _ssh_run(ssh, f"stat -c '%s %n' {log_path} 2>/dev/null || echo 'MISSING {log_path}'")
        if stat_out.startswith("MISSING"):
            log_status[log_path] = "missing"
            alerts.append({
                "type": "log_tampering_missing",
                "severity": "critical",
                "message": f"Log file missing: {log_path}",
            })
        else:
            parts = stat_out.split()
            if parts:
                try:
                    size_bytes = int(parts[0])
                    log_status[log_path] = f"{size_bytes} bytes"
                    if size_bytes == 0:
                        alerts.append({
                            "type": "log_tampering_zeroed",
                            "severity": "critical",
                            "message": f"Log file is 0 bytes (wiped?): {log_path}",
                        })
                except ValueError:
                    log_status[log_path] = "unknown"

    return {
        "check": "vm_log_tampering",
        "log_status": log_status,
        "alerts": alerts,
    }


# ================================================================
# Check 6: Vault Brute Force
# ================================================================

def _check_vault_brute_force() -> dict:
    """
    HTTP GET http://{VAULT_HOST}:{VAULT_PORT}/api/auth/attempts
    Alert if failed_attempts > 5.
    """
    alerts: list[dict] = []
    url = f"http://{VAULT_HOST}:{VAULT_PORT}/api/auth/attempts"
    response_data: dict[str, Any] = {}

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            response_data = json.loads(body)
    except urllib.error.URLError as exc:
        return {
            "check": "vault_brute_force",
            "vault_reachable": False,
            "error": str(exc),
            "alerts": [],
        }
    except json.JSONDecodeError as exc:
        return {
            "check": "vault_brute_force",
            "vault_reachable": True,
            "error": f"JSON decode error: {exc}",
            "alerts": [],
        }
    except Exception as exc:
        return {
            "check": "vault_brute_force",
            "vault_reachable": False,
            "error": str(exc),
            "alerts": [],
        }

    failed = response_data.get("failed_attempts", response_data.get("failures", 0))
    try:
        failed = int(failed)
    except (TypeError, ValueError):
        failed = 0

    if failed > 5:
        alerts.append({
            "type": "vault_brute_force",
            "severity": "critical",
            "message": f"Vault has {failed} failed auth attempts — possible brute force attack.",
        })

    return {
        "check": "vault_brute_force",
        "vault_reachable": True,
        "failed_attempts": failed,
        "raw_response": response_data,
        "alerts": alerts,
    }


# ================================================================
# Check 7: File Changes
# ================================================================

def _check_vm_file_changes(ssh: paramiko.SSHClient) -> dict:
    """
    Find files in /etc and /home that are newer than the stealth baseline marker.
    """
    BASELINE_MARKER = "/var/lib/.cache/.stealth_baseline.json"
    alerts: list[dict] = []

    # Check whether the baseline file itself exists
    marker_check = _ssh_run(
        ssh,
        f"test -f {BASELINE_MARKER} && echo EXISTS || echo MISSING",
    )
    baseline_exists = marker_check.strip() == "EXISTS"

    changed_files: list[str] = []

    if baseline_exists:
        find_out = _ssh_run(
            ssh,
            f"find /etc /home -newer {BASELINE_MARKER} -type f 2>/dev/null || true",
            timeout=20,
        )
        for fpath in find_out.splitlines():
            fpath = fpath.strip()
            if fpath:
                changed_files.append(fpath)

        if changed_files:
            alerts.append({
                "type": "file_changes_detected",
                "severity": "high",
                "message": f"{len(changed_files)} file(s) modified after stealth baseline: {', '.join(changed_files[:5])}{'...' if len(changed_files) > 5 else ''}",
            })
    else:
        alerts.append({
            "type": "file_changes_no_baseline",
            "severity": "medium",
            "message": f"Stealth baseline marker not found at {BASELINE_MARKER} — cannot diff file changes.",
        })

    return {
        "check": "vm_file_changes",
        "baseline_exists": baseline_exists,
        "changed_files_count": len(changed_files),
        "changed_files": changed_files[:50],  # cap output
        "alerts": alerts,
    }


# ================================================================
# Check 8: Privilege Escalation
# ================================================================

def _check_vm_privilege_escalation(ssh: paramiko.SSHClient) -> dict:
    """
    - Count SUID binaries (flag if unusually high)
    - stat /etc/sudoers for recent modification
    """
    SUID_NORMAL_THRESHOLD = 30  # Baseline Ubuntu 24.04 has ~20-25 SUID binaries
    alerts: list[dict] = []

    # --- SUID count ---
    suid_count_raw = _ssh_run(
        ssh,
        "find / -perm -4000 -type f 2>/dev/null | wc -l",
        timeout=20,
    )
    try:
        suid_count = int(suid_count_raw.strip())
    except ValueError:
        suid_count = -1

    if suid_count > SUID_NORMAL_THRESHOLD:
        alerts.append({
            "type": "privilege_escalation_suid",
            "severity": "high",
            "message": f"Unusually high SUID binary count: {suid_count} (threshold: {SUID_NORMAL_THRESHOLD}). Possible SUID backdoor planted.",
        })

    # --- /etc/sudoers mtime ---
    sudoers_stat = _ssh_run(ssh, "stat -c '%Y %n' /etc/sudoers 2>/dev/null || true")
    sudoers_age_info = "(unreadable)"
    if sudoers_stat:
        parts = sudoers_stat.split()
        if parts:
            try:
                mtime = int(parts[0])
                now = datetime.now(timezone.utc).timestamp()
                age_hours = (now - mtime) / 3600
                sudoers_age_info = f"{age_hours:.1f}h ago"
                if age_hours < 24:
                    alerts.append({
                        "type": "privilege_escalation_sudoers",
                        "severity": "critical",
                        "message": f"/etc/sudoers modified {age_hours:.1f}h ago — possible privilege escalation.",
                    })
            except ValueError:
                pass

    return {
        "check": "vm_privilege_escalation",
        "suid_binary_count": suid_count,
        "sudoers_last_modified": sudoers_age_info,
        "alerts": alerts,
    }


# ================================================================
# Check 9: IDS Heartbeat
# ================================================================

def _check_ids_heartbeat(ssh: paramiko.SSHClient) -> dict:
    """
    - Read IDS heartbeat file age
    - Check decoy service and stealth service status
    - Read stealth .metrics for alert count
    """
    HEARTBEAT_FILE = "/var/lib/.cache/.ids_heartbeat"
    METRICS_FILE = "/var/lib/.cache/.stealth_metrics"
    HEARTBEAT_MAX_AGE_MINUTES = 5

    alerts: list[dict] = []
    heartbeat_info: dict[str, Any] = {}

    # --- Heartbeat file age ---
    hb_stat = _ssh_run(ssh, f"stat -c '%Y' {HEARTBEAT_FILE} 2>/dev/null || echo MISSING")
    if hb_stat.strip() == "MISSING":
        heartbeat_info["heartbeat_file"] = "missing"
        alerts.append({
            "type": "ids_heartbeat_missing",
            "severity": "critical",
            "message": f"IDS heartbeat file not found at {HEARTBEAT_FILE} — IDS may be down.",
        })
    else:
        try:
            mtime = int(hb_stat.strip())
            now = datetime.now(timezone.utc).timestamp()
            age_minutes = (now - mtime) / 60
            heartbeat_info["heartbeat_age_minutes"] = round(age_minutes, 1)
            if age_minutes > HEARTBEAT_MAX_AGE_MINUTES:
                alerts.append({
                    "type": "ids_heartbeat_stale",
                    "severity": "critical",
                    "message": f"IDS heartbeat is {age_minutes:.1f}m old (max {HEARTBEAT_MAX_AGE_MINUTES}m) — IDS may be stopped or killed.",
                })
        except ValueError:
            heartbeat_info["heartbeat_file"] = "stat_error"

    # --- Decoy service status ---
    decoy_status = _ssh_run(ssh, "systemctl is-active decoy-service 2>/dev/null || echo unknown")
    heartbeat_info["decoy_service_status"] = decoy_status.strip()
    if decoy_status.strip() not in ("active", "unknown"):
        alerts.append({
            "type": "ids_decoy_service_down",
            "severity": "high",
            "message": f"Decoy service is not active: {decoy_status.strip()}",
        })

    # --- Stealth service status ---
    stealth_status = _ssh_run(ssh, "systemctl is-active stealth-monitor 2>/dev/null || echo unknown")
    heartbeat_info["stealth_service_status"] = stealth_status.strip()
    if stealth_status.strip() not in ("active", "unknown"):
        alerts.append({
            "type": "ids_stealth_service_down",
            "severity": "critical",
            "message": f"Stealth monitor service is not active: {stealth_status.strip()}",
        })

    # --- Stealth metrics alerts ---
    metrics_raw = _ssh_run(ssh, f"cat {METRICS_FILE} 2>/dev/null || echo '{{}}'")
    try:
        metrics = json.loads(metrics_raw)
        heartbeat_info["metrics"] = metrics
        metric_alerts = metrics.get("alerts", [])
        if isinstance(metric_alerts, list) and metric_alerts:
            for ma in metric_alerts[:10]:  # cap
                alerts.append({
                    "type": "ids_stealth_metric_alert",
                    "severity": ma.get("severity", "medium") if isinstance(ma, dict) else "medium",
                    "message": str(ma)[:300],
                })
        elif isinstance(metric_alerts, int) and metric_alerts > 0:
            alerts.append({
                "type": "ids_stealth_metric_alert",
                "severity": "high",
                "message": f"Stealth metrics reports {metric_alerts} alert(s).",
            })
    except (json.JSONDecodeError, ValueError):
        heartbeat_info["metrics_raw"] = metrics_raw[:300]

    return {
        "check": "ids_heartbeat",
        "heartbeat_info": heartbeat_info,
        "alerts": alerts,
    }


# ================================================================
# Check 10: Auditd Alerts (bridges vm_hardening rules with detection)
# ================================================================

def _check_auditd_alerts(ssh: paramiko.SSHClient) -> dict:
    """Read recent auditd alerts for security-relevant events."""
    alerts: list[dict] = []
    audit_keys = {
        "crontab_mod": ("Crontab modification detected", "critical"),
        "shadow_access": ("/etc/shadow accessed", "critical"),
        "systemd_mod": ("Systemd service file changed", "high"),
        "bashrc_mod": (".bashrc modified", "high"),
        "ssh_key_access": ("SSH key accessed", "high"),
        "log_tamper": ("Log file tampered", "critical"),
        "suid_change": ("SUID permission changed", "high"),
        "sudoers_access": ("sudoers file accessed", "high"),
        "process_kill": ("Process killed with signal 9", "medium"),
    }
    for key, (msg, severity) in audit_keys.items():
        result = _ssh_run(ssh, f"echo 'logitech66' | sudo -S ausearch -k {key} --start recent 2>/dev/null | grep -c 'type=SYSCALL'")
        try:
            count = int(result.strip())
        except (ValueError, TypeError):
            count = 0
        if count > 0:
            alerts.append({
                "type": f"auditd_{key}",
                "severity": severity,
                "message": f"{msg}: {count} events",
                "count": count,
            })
    return {"check": "auditd_alerts", "alerts": alerts, "total_events": sum(a.get("count", 0) for a in alerts)}


# ================================================================
# Meta-Tool: scan_vm_threats
# ================================================================

async def scan_vm_threats(baseline_json: str = "") -> dict:
    """
    Run all VM detection checks. Returns consolidated JSON.

    Connects to the MultiseatOS VM via SSH once, runs all 8 detection
    checks plus the IDS heartbeat check, then returns a consolidated
    result dict with per-check results, total_alerts, critical_alerts,
    and an optional warning field.

    Args:
        baseline_json: Optional JSON string (reserved for future baseline comparisons).

    Returns:
        dict with keys:
            - vm_available (bool)
            - scan_timestamp (str ISO8601)
            - checks (dict of per-check results)
            - total_alerts (int)
            - critical_alerts (int)
            - warning (str | None)
            - error (str | None) — present only on SSH failure
    """

    def _sync() -> dict:
        scan_timestamp = datetime.now(timezone.utc).isoformat()

        # --- Try SSH connect ---
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return {
                "vm_available": False,
                "scan_timestamp": scan_timestamp,
                "checks": {},
                "total_alerts": 0,
                "critical_alerts": 0,
                "warning": "VM unreachable — scan aborted.",
                "error": str(exc),
            }

        checks: dict[str, dict] = {}

        try:
            checks["vm_backdoors"] = _check_vm_backdoors(ssh)
        except Exception as exc:
            checks["vm_backdoors"] = {"check": "vm_backdoors", "error": str(exc), "alerts": []}

        try:
            checks["vm_suspicious_processes"] = _check_vm_suspicious_processes(ssh)
        except Exception as exc:
            checks["vm_suspicious_processes"] = {"check": "vm_suspicious_processes", "error": str(exc), "alerts": []}

        try:
            checks["vm_credential_theft"] = _check_vm_credential_theft(ssh)
        except Exception as exc:
            checks["vm_credential_theft"] = {"check": "vm_credential_theft", "error": str(exc), "alerts": []}

        try:
            checks["vm_network_anomalies"] = _check_vm_network_anomalies(ssh)
        except Exception as exc:
            checks["vm_network_anomalies"] = {"check": "vm_network_anomalies", "error": str(exc), "alerts": []}

        try:
            checks["vm_log_tampering"] = _check_vm_log_tampering(ssh)
        except Exception as exc:
            checks["vm_log_tampering"] = {"check": "vm_log_tampering", "error": str(exc), "alerts": []}

        try:
            checks["vm_file_changes"] = _check_vm_file_changes(ssh)
        except Exception as exc:
            checks["vm_file_changes"] = {"check": "vm_file_changes", "error": str(exc), "alerts": []}

        try:
            checks["vm_privilege_escalation"] = _check_vm_privilege_escalation(ssh)
        except Exception as exc:
            checks["vm_privilege_escalation"] = {"check": "vm_privilege_escalation", "error": str(exc), "alerts": []}

        try:
            checks["ids_heartbeat"] = _check_ids_heartbeat(ssh)
        except Exception as exc:
            checks["ids_heartbeat"] = {"check": "ids_heartbeat", "error": str(exc), "alerts": []}

        ssh.close()

        # Vault brute force check (HTTP, no SSH needed)
        try:
            checks["vault_brute_force"] = _check_vault_brute_force()
        except Exception as exc:
            checks["vault_brute_force"] = {"check": "vault_brute_force", "error": str(exc), "alerts": []}

        # --- Aggregate alerts ---
        total_alerts = 0
        critical_alerts = 0
        for check_result in checks.values():
            for alert in check_result.get("alerts", []):
                total_alerts += 1
                if alert.get("severity") == "critical":
                    critical_alerts += 1

        warning: str | None = None
        if total_alerts > 0:
            warning = (
                f"{total_alerts} alert(s) detected across all VM checks "
                f"({critical_alerts} critical)."
            )

        return {
            "vm_available": True,
            "scan_timestamp": scan_timestamp,
            "checks": checks,
            "total_alerts": total_alerts,
            "critical_alerts": critical_alerts,
            "warning": warning,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)
