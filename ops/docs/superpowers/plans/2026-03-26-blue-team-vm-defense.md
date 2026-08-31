# Blue Team VM Defense — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Blue Team full VM visibility (detection + response) via 3 layers: remote SSH detection, dual-layer in-VM IDS, and active incident response.

**Architecture:** Meta-tool `scan_vm_threats` consolidates 8 SSH-based detection checks into one LLM-callable function. Two IDS services (decoy + stealth) run inside the VM and report to host. Enforcer dispatches VM actions via SSH when `action_type.startswith("vm_")`. Judge scores 3 dimensions: detection, response, resilience.

**Tech Stack:** Python 3.11, paramiko (SSH), AutoGen Core, OpenAI function calling, systemd services, HTTP stdlib

**Spec:** `docs/superpowers/specs/2026-03-26-blue-team-vm-defense-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `poc_red_blue/vm_ids/__init__.py` | Create | Package init |
| `poc_red_blue/vm_ids/decoy_ids.py` | Create | Visible honeypot IDS service |
| `poc_red_blue/vm_ids/stealth_ids.py` | Create | Hidden real IDS service |
| `poc_red_blue/vm_ids/deploy_ids.py` | Create | Deploy both IDS to VM via SSH |
| `poc_os_shield/vm_detection_tools.py` | Create | 8 SSH detection tools + meta-tool |
| `poc_os_shield/vm_enforcement_tools.py` | Create | 6 SSH response actions |
| `poc_os_shield/tools.py` | Modify | Import + register `scan_vm_threats` |
| `poc_os_shield/enforcer.py` | Modify | Add `vm_*` dispatch path |
| `poc_os_shield/orchestrator.py` | Modify | Add VM DETECTION to system prompt |
| `poc_os_shield/analyzer.py` | Modify | Add VM action types to prompt |
| `poc_red_blue/config.py` | Modify | Add VM_IDS settings |
| `poc_red_blue/messages.py` | Modify | Add response_score, resilience_score |
| `poc_red_blue/judge/scoring.py` | Modify | Add response + resilience scoring |
| `poc_red_blue/judge/judge_agent.py` | Modify | Use 3-dimensional scoring |
| `poc_red_blue/start_exercise.py` | Modify | Add IDS deploy step + port 19091 |
| `poc_red_blue/red_team/vm_attack_tools.py` | Modify | Add 4 IDS evasion tools |
| `poc_red_blue/red_team/orchestrator.py` | Modify | Add IDS evasion category |
| `poc_red_blue/vm_deploy.py` | Modify | Add vault /api/auth/attempts endpoint |

---

### Task 1: In-VM Decoy IDS

**Files:**
- Create: `poc_red_blue/vm_ids/__init__.py`
- Create: `poc_red_blue/vm_ids/decoy_ids.py`

- [ ] **Step 1: Create package init**

```python
# poc_red_blue/vm_ids/__init__.py
# VM IDS services — deployed into MultiseatOS VM
```

- [ ] **Step 2: Create decoy_ids.py**

```python
#!/usr/bin/env python3
"""Decoy-IDS — Visible honeypot security monitor.
Runs as vm-security-monitor.service. Red Team WILL find and kill this.
When killed, writes alarm to /var/lib/.cache/.decoy_killed for Stealth-IDS."""

import json
import os
import subprocess
import time
from datetime import datetime

LOG_FILE = "/var/log/vm-security.log"
ALARM_FILE = "/var/lib/.cache/.decoy_killed"
CHECK_INTERVAL = 10  # seconds


def get_processes():
    out = subprocess.run(["ps", "aux", "--no-headers"], capture_output=True, text=True, timeout=5)
    return out.stdout.strip().split("\n")


def get_listeners():
    out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
    return out.stdout.strip()


def get_crontab():
    out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
    return out.stdout.strip()


def log_entry(level, message, details=None):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
    }
    if details:
        entry["details"] = details
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    if level in ("CRITICAL", "HIGH"):
        print(f"[VM-SECURITY] {level}: {message}", flush=True)


def check_suspicious_processes(procs):
    suspicious_names = [
        "nmap", "masscan", "mimikatz", "lazagne", "procdump",
        "rubeus", "sharphound", "bloodhound", "hydra", "john",
    ]
    alerts = []
    for line in procs:
        lower = line.lower()
        for name in suspicious_names:
            if name in lower:
                alerts.append({"process": line.strip()[:200], "matched": name})
    return alerts


def check_crontab_backdoors(crontab):
    alerts = []
    for line in crontab.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        suspicious = ["reverse", "bash -i", "nc ", "ncat", "/dev/tcp", "curl", "wget", "python"]
        for kw in suspicious:
            if kw in line.lower():
                alerts.append({"cron_entry": line, "matched": kw})
    return alerts


def main():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    os.makedirs("/var/lib/.cache", exist_ok=True)
    log_entry("INFO", "VM Security Monitor started")
    print("[VM-SECURITY] Decoy IDS started", flush=True)

    while True:
        try:
            # Process check
            procs = get_processes()
            proc_alerts = check_suspicious_processes(procs)
            if proc_alerts:
                log_entry("HIGH", f"Suspicious processes: {len(proc_alerts)}", proc_alerts)

            # Crontab check
            crontab = get_crontab()
            cron_alerts = check_crontab_backdoors(crontab)
            if cron_alerts:
                log_entry("CRITICAL", f"Crontab backdoors: {len(cron_alerts)}", cron_alerts)

            # Listeners check
            listeners = get_listeners()
            suspicious_ports = ["4444", "5555", "1337", "6667"]
            for port in suspicious_ports:
                if f":{port}" in listeners:
                    log_entry("HIGH", f"Suspicious listener on port {port}")

            log_entry("INFO", f"Scan complete: {len(procs)} processes")

        except Exception as e:
            log_entry("ERROR", f"Scan error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add poc_red_blue/vm_ids/__init__.py poc_red_blue/vm_ids/decoy_ids.py
git commit -m "feat: add decoy IDS service for VM"
```

---

### Task 2: In-VM Stealth IDS

**Files:**
- Create: `poc_red_blue/vm_ids/stealth_ids.py`

- [ ] **Step 1: Create stealth_ids.py**

```python
#!/usr/bin/env python3
"""Stealth-IDS — Hidden monitoring service disguised as dbus-session-helper.
Survives decoy kill. Writes alerts to hidden .metrics file.
Heartbeat to .heartbeat every 10s for Blue Team liveness check."""

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

METRICS_FILE = "/var/lib/.cache/.metrics"
HEARTBEAT_FILE = "/var/lib/.cache/.heartbeat"
DECOY_KILLED_FILE = "/var/lib/.cache/.decoy_killed"
BASELINE_FILE = "/var/lib/.cache/.stealth_baseline.json"
CHECK_INTERVAL = 10


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"error: {e}"


def _alert(level, category, message, details=None):
    entry = {
        "ts": datetime.now().isoformat(),
        "level": level,
        "cat": category,
        "msg": message,
    }
    if details:
        entry["details"] = details
    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _heartbeat():
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(datetime.now().isoformat())


def _capture_baseline():
    baseline = {
        "pids": _run(["ps", "-eo", "pid", "--no-headers"]).split(),
        "listeners": _run(["ss", "-tlnp"]),
        "crontab": _run(["crontab", "-l"]),
        "shadow_mtime": _safe_stat("/etc/shadow"),
        "sudoers_mtime": _safe_stat("/etc/sudoers"),
        "ssh_keys_hash": _hash_dir("/home/vibemind/.ssh"),
        "timestamp": datetime.now().isoformat(),
    }
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f)
    return baseline


def _safe_stat(path):
    try:
        return os.stat(path).st_mtime
    except Exception:
        return 0


def _hash_dir(path):
    h = hashlib.sha256()
    try:
        for f in sorted(os.listdir(path)):
            fp = os.path.join(path, f)
            if os.path.isfile(fp):
                h.update(f.encode())
                h.update(str(os.stat(fp).st_mtime).encode())
    except Exception:
        pass
    return h.hexdigest()


def _load_baseline():
    try:
        with open(BASELINE_FILE) as f:
            return json.load(f)
    except Exception:
        return _capture_baseline()


def check_decoy_status():
    """Check if decoy IDS was killed."""
    if os.path.exists(DECOY_KILLED_FILE):
        _alert("CRITICAL", "ids_evasion", "Decoy IDS was killed by attacker!")
        return False
    out = _run(["systemctl", "is-active", "vm-security-monitor"])
    if "active" not in out:
        # Decoy was stopped — write alarm file
        with open(DECOY_KILLED_FILE, "w") as f:
            f.write(datetime.now().isoformat())
        _alert("CRITICAL", "ids_evasion", "Decoy IDS service stopped — attacker detected!")
        return False
    return True


def check_processes(baseline):
    current_pids = set(_run(["ps", "-eo", "pid", "--no-headers"]).split())
    baseline_pids = set(baseline.get("pids", []))
    new_pids = current_pids - baseline_pids
    if len(new_pids) > 20:
        _alert("HIGH", "process", f"{len(new_pids)} new processes since baseline")


def check_crontab(baseline):
    current = _run(["crontab", "-l"])
    if current != baseline.get("crontab", ""):
        _alert("CRITICAL", "persistence", "Crontab modified!", {"current": current[:500]})


def check_credentials(baseline):
    shadow_mtime = _safe_stat("/etc/shadow")
    if shadow_mtime != baseline.get("shadow_mtime", 0):
        _alert("CRITICAL", "credential_theft", "/etc/shadow was accessed/modified!")

    sudoers_mtime = _safe_stat("/etc/sudoers")
    if sudoers_mtime != baseline.get("sudoers_mtime", 0):
        _alert("HIGH", "privesc", "/etc/sudoers was modified!")

    ssh_hash = _hash_dir("/home/vibemind/.ssh")
    if ssh_hash != baseline.get("ssh_keys_hash", ""):
        _alert("HIGH", "credential_theft", "SSH keys changed!")


def check_logs():
    for log in ["/var/log/auth.log", "/var/log/syslog"]:
        try:
            size = os.path.getsize(log)
            if size == 0:
                _alert("CRITICAL", "log_tampering", f"{log} truncated to 0 bytes!")
        except FileNotFoundError:
            _alert("CRITICAL", "log_tampering", f"{log} deleted!")


def check_network():
    listeners = _run(["ss", "-tlnp"])
    suspicious = ["4444", "5555", "1337", "6667", "8888", "9999"]
    for port in suspicious:
        if f":{port}" in listeners:
            _alert("HIGH", "network", f"Suspicious listener on port {port}")


class MetricsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler disguised as metrics exporter."""
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        if self.path == "/metrics":
            try:
                with open(METRICS_FILE) as f:
                    data = f.read()
            except FileNotFoundError:
                data = ""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(data.encode())
        elif self.path == "/heartbeat":
            try:
                with open(HEARTBEAT_FILE) as f:
                    ts = f.read().strip()
            except FileNotFoundError:
                ts = "never"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(ts.encode())
        else:
            self.send_response(404)
            self.end_headers()


def start_metrics_server():
    server = HTTPServer(("0.0.0.0", 19091), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def main():
    os.makedirs("/var/lib/.cache", exist_ok=True)

    # Clear old metrics
    for f in [METRICS_FILE, DECOY_KILLED_FILE]:
        if os.path.exists(f):
            os.remove(f)

    start_metrics_server()
    baseline = _capture_baseline()
    _alert("INFO", "system", "Stealth IDS started")

    while True:
        try:
            _heartbeat()
            check_decoy_status()
            check_processes(baseline)
            check_crontab(baseline)
            check_credentials(baseline)
            check_logs()
            check_network()
        except Exception as e:
            _alert("ERROR", "system", f"Check error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add poc_red_blue/vm_ids/stealth_ids.py
git commit -m "feat: add stealth IDS service disguised as dbus-session-helper"
```

---

### Task 3: IDS Deployment Script

**Files:**
- Create: `poc_red_blue/vm_ids/deploy_ids.py`

- [ ] **Step 1: Create deploy_ids.py**

```python
"""Deploy Decoy + Stealth IDS into MultiseatOS VM via SSH."""
import logging
import os
import sys
import time

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _parent)

from infra import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS

DECOY_SERVICE = """[Unit]
Description=VM Security Monitor
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/vibemind/vm-security-monitor/monitor.py
ExecStopPost=/bin/bash -c 'echo $(date -Iseconds) > /var/lib/.cache/.decoy_killed'
Restart=no
[Install]
WantedBy=multi-user.target"""

STEALTH_SERVICE = """[Unit]
Description=D-Bus Session Helper
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/lib/dbus-1.0/session-helper
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target"""


def deploy():
    print("[IDS] Deploying Decoy + Stealth IDS to VM...", flush=True)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_SSH_HOST, port=VM_SSH_PORT, username=VM_SSH_USER,
                password=VM_SSH_PASS, timeout=10, banner_timeout=15)

    sftp = ssh.open_sftp()

    def ssh_run(cmd, timeout=15):
        _, out, err = ssh.exec_command(cmd, timeout=timeout)
        return out.read().decode("utf-8", errors="replace").strip()

    # 1. Deploy Decoy IDS
    print("  [IDS] Deploying decoy...", flush=True)
    ssh_run("mkdir -p /home/vibemind/vm-security-monitor")
    decoy_path = os.path.join(os.path.dirname(__file__), "decoy_ids.py")
    sftp.put(decoy_path, "/home/vibemind/vm-security-monitor/monitor.py")

    sftp.file("/tmp/vm-security-monitor.service", "w").write(DECOY_SERVICE)
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S cp /tmp/vm-security-monitor.service /etc/systemd/system/")

    # 2. Deploy Stealth IDS
    print("  [IDS] Deploying stealth...", flush=True)
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S mkdir -p /usr/lib/dbus-1.0")
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S mkdir -p /var/lib/.cache")
    stealth_path = os.path.join(os.path.dirname(__file__), "stealth_ids.py")
    # Write to temp first, then sudo cp (sftp can't write to /usr/lib)
    sftp.put(stealth_path, "/tmp/session-helper")
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S cp /tmp/session-helper /usr/lib/dbus-1.0/session-helper")
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S chmod +x /usr/lib/dbus-1.0/session-helper")

    sftp.file("/tmp/dbus-session-helper.service", "w").write(STEALTH_SERVICE)
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S cp /tmp/dbus-session-helper.service /etc/systemd/system/")

    # 3. Start services
    print("  [IDS] Starting services...", flush=True)
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S systemctl daemon-reload")
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S systemctl enable --now vm-security-monitor")
    ssh_run(f"echo '{VM_SSH_PASS}' | sudo -S systemctl enable --now dbus-session-helper")
    time.sleep(2)

    # 4. Verify
    decoy_status = ssh_run("systemctl is-active vm-security-monitor")
    stealth_status = ssh_run("systemctl is-active dbus-session-helper")
    print(f"  [IDS] Decoy: {decoy_status}, Stealth: {stealth_status}", flush=True)

    sftp.close()
    ssh.close()

    ok = "active" in decoy_status and "active" in stealth_status
    if ok:
        print("  [IDS] Both IDS services deployed and running.", flush=True)
    else:
        print("  [IDS] WARNING: One or more IDS services failed to start.", flush=True)
    return ok


if __name__ == "__main__":
    deploy()
```

- [ ] **Step 2: Test deployment**

Run: `cd poc_red_blue && python -m vm_ids.deploy_ids`
Expected: Both services show "active"

- [ ] **Step 3: Commit**

```bash
git add poc_red_blue/vm_ids/deploy_ids.py
git commit -m "feat: add IDS deployment script for VM"
```

---

### Task 4: VM Detection Meta-Tool

**Files:**
- Create: `poc_os_shield/vm_detection_tools.py`
- Modify: `poc_os_shield/tools.py` (lines 2785-2834 TOOL_DISPATCH, lines 2841+ TOOL_DEFINITIONS)

- [ ] **Step 1: Create vm_detection_tools.py**

```python
"""
VM Detection Tools — Remote SSH/API checks for Blue Team
============================================================
8 detection checks consolidated into one meta-tool: scan_vm_threats.
Called by Blue Team Orchestrator as a single function call.
"""

import json
import logging
import os
import sys
from datetime import datetime

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# Import infra constants
_rb_path = os.path.join(os.path.dirname(__file__), "..", "poc_red_blue")
if _rb_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_rb_path))

try:
    from infra import (
        VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS,
        VM_API_HOST, VM_API_PORT, VAULT_HOST, VAULT_PORT,
    )
    _VM_CONFIGURED = True
except ImportError:
    _VM_CONFIGURED = False


def _ssh_connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_SSH_HOST, port=VM_SSH_PORT, username=VM_SSH_USER,
                password=VM_SSH_PASS, timeout=10, banner_timeout=15)
    return ssh


def _ssh_run(ssh, cmd, timeout=10):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", errors="replace").strip()


def _check_vm_backdoors(ssh):
    crontab = _ssh_run(ssh, "crontab -l 2>/dev/null")
    bashrc = _ssh_run(ssh, "grep -n 'REDBLUE\\|reverse\\|bash -i\\|/dev/tcp\\|nc \\|ncat' ~/.bashrc 2>/dev/null")
    rogue_services = _ssh_run(ssh, "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | grep -viE 'ssh|systemd|dbus|network|cron|rsyslog|secret-vault|system-monitor|snapd|ufw|plymouth|polkit|accounts|unattended|ModemManager'")

    alerts = []
    cron_lines = [l for l in crontab.split("\n") if l.strip() and not l.startswith("#")]
    if cron_lines:
        alerts.append({"type": "crontab_backdoor", "severity": "CRITICAL", "entries": cron_lines[:5]})
    if bashrc.strip():
        alerts.append({"type": "bashrc_injection", "severity": "CRITICAL", "matches": bashrc[:500]})
    return {"backdoors_found": len(alerts), "alerts": alerts, "rogue_services": rogue_services[:1000]}


def _check_vm_suspicious_processes(ssh):
    procs = _ssh_run(ssh, "ps aux --no-headers")
    suspicious_names = ["nmap", "masscan", "mimikatz", "lazagne", "procdump", "hydra", "john", "hashcat", "reverse", "backdoor"]
    found = []
    for line in procs.split("\n"):
        lower = line.lower()
        for name in suspicious_names:
            if name in lower:
                found.append({"process": line.strip()[:200], "matched": name})
    return {"suspicious_count": len(found), "processes": found[:10]}


def _check_vm_credential_theft(ssh):
    shadow_stat = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S stat --format='%Y' /etc/shadow 2>/dev/null")
    ssh_files = _ssh_run(ssh, "ls -la ~/.ssh/ 2>/dev/null")
    token_files = _ssh_run(ssh, "find /tmp -name '*token*' -o -name '*secret*' -o -name '*vault*' -o -name '*shadow*' 2>/dev/null | head -10")

    alerts = []
    if token_files.strip():
        alerts.append({"type": "stolen_credentials", "severity": "CRITICAL", "files": token_files.split("\n")[:5]})
    return {"shadow_mtime": shadow_stat, "ssh_dir": ssh_files[:500], "alerts": alerts}


def _check_vm_network_anomalies(ssh):
    listeners = _ssh_run(ssh, "ss -tlnp 2>/dev/null")
    connections = _ssh_run(ssh, "ss -tnp 2>/dev/null | tail -20")
    suspicious_ports = ["4444", "5555", "1337", "6667", "8888", "9999"]
    alerts = []
    for port in suspicious_ports:
        if f":{port}" in listeners:
            alerts.append({"type": "suspicious_listener", "severity": "HIGH", "port": port})
    return {"listener_count": len(listeners.split("\n")), "alerts": alerts, "connections": connections[:1000]}


def _check_vm_log_tampering(ssh):
    alerts = []
    for log in ["/var/log/auth.log", "/var/log/syslog"]:
        size = _ssh_run(ssh, f"wc -c < {log} 2>/dev/null")
        if size.strip() == "0":
            alerts.append({"type": "log_truncated", "severity": "CRITICAL", "file": log})
        elif "No such file" in size or not size.strip():
            alerts.append({"type": "log_deleted", "severity": "CRITICAL", "file": log})
    return {"alerts": alerts}


def _check_vault_brute_force():
    import urllib.request
    try:
        req = urllib.request.Request(f"http://{VAULT_HOST}:{VAULT_PORT}/api/auth/attempts", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        failed = data.get("failed", 0)
        alerts = []
        if failed > 5:
            alerts.append({"type": "vault_brute_force", "severity": "HIGH", "failed_attempts": failed})
        return {"failed_logins": failed, "alerts": alerts}
    except Exception:
        return {"failed_logins": 0, "alerts": [], "note": "vault unreachable or no attempts endpoint"}


def _check_vm_file_changes(ssh):
    # Check for new/modified files in sensitive paths
    new_files = _ssh_run(ssh, "find /etc /home/vibemind -newer /var/lib/.cache/.stealth_baseline.json -type f 2>/dev/null | head -20", timeout=15)
    alerts = []
    files = [f for f in new_files.split("\n") if f.strip()]
    if files:
        alerts.append({"type": "file_changes", "severity": "MEDIUM", "count": len(files), "files": files[:10]})
    return {"changed_files": len(files), "alerts": alerts}


def _check_vm_privilege_escalation(ssh):
    suid_count = _ssh_run(ssh, "find / -perm -4000 -type f 2>/dev/null | wc -l", timeout=20)
    sudoers_mtime = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S stat --format='%Y' /etc/sudoers 2>/dev/null")
    return {"suid_binary_count": suid_count, "sudoers_mtime": sudoers_mtime}


def _check_ids_heartbeat(ssh):
    heartbeat = _ssh_run(ssh, "cat /var/lib/.cache/.heartbeat 2>/dev/null")
    decoy_active = "active" in _ssh_run(ssh, "systemctl is-active vm-security-monitor 2>/dev/null")
    stealth_active = "active" in _ssh_run(ssh, "systemctl is-active dbus-session-helper 2>/dev/null")

    alerts = []
    if not decoy_active:
        alerts.append({"type": "decoy_ids_killed", "severity": "CRITICAL", "message": "Decoy IDS was stopped!"})
    if not stealth_active:
        alerts.append({"type": "stealth_ids_killed", "severity": "CRITICAL", "message": "Stealth IDS was stopped!"})
    if heartbeat:
        try:
            hb_time = datetime.fromisoformat(heartbeat)
            age = (datetime.now() - hb_time).total_seconds()
            if age > 30:
                alerts.append({"type": "ids_silence", "severity": "CRITICAL", "heartbeat_age_seconds": age})
        except ValueError:
            pass

    # Read stealth IDS alerts
    metrics = _ssh_run(ssh, "cat /var/lib/.cache/.metrics 2>/dev/null")
    ids_alerts = []
    for line in (metrics or "").split("\n"):
        if line.strip():
            try:
                entry = json.loads(line)
                if entry.get("level") in ("CRITICAL", "HIGH"):
                    ids_alerts.append(entry)
            except json.JSONDecodeError:
                pass

    return {
        "decoy_active": decoy_active,
        "stealth_active": stealth_active,
        "heartbeat": heartbeat,
        "ids_alerts": ids_alerts[:20],
        "alerts": alerts,
    }


async def scan_vm_threats(baseline_json: str = "") -> dict:
    """Meta-tool: Run all 8 VM detection checks + IDS heartbeat.
    Returns consolidated results with per-check alerts.
    """
    import asyncio

    if not _VM_CONFIGURED:
        return {"warning": "VM not configured", "vm_available": False}

    def _sync():
        try:
            ssh = _ssh_connect()
        except Exception as e:
            return {"warning": f"VM SSH unreachable: {e}", "vm_available": False}

        results = {
            "vm_available": True,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            results["backdoors"] = _check_vm_backdoors(ssh)
        except Exception as e:
            results["backdoors"] = {"error": str(e)}

        try:
            results["suspicious_processes"] = _check_vm_suspicious_processes(ssh)
        except Exception as e:
            results["suspicious_processes"] = {"error": str(e)}

        try:
            results["credential_theft"] = _check_vm_credential_theft(ssh)
        except Exception as e:
            results["credential_theft"] = {"error": str(e)}

        try:
            results["network_anomalies"] = _check_vm_network_anomalies(ssh)
        except Exception as e:
            results["network_anomalies"] = {"error": str(e)}

        try:
            results["log_tampering"] = _check_vm_log_tampering(ssh)
        except Exception as e:
            results["log_tampering"] = {"error": str(e)}

        try:
            results["vault_brute_force"] = _check_vault_brute_force()
        except Exception as e:
            results["vault_brute_force"] = {"error": str(e)}

        try:
            results["file_changes"] = _check_vm_file_changes(ssh)
        except Exception as e:
            results["file_changes"] = {"error": str(e)}

        try:
            results["privilege_escalation"] = _check_vm_privilege_escalation(ssh)
        except Exception as e:
            results["privilege_escalation"] = {"error": str(e)}

        try:
            results["ids_status"] = _check_ids_heartbeat(ssh)
        except Exception as e:
            results["ids_status"] = {"error": str(e)}

        # Aggregate all alerts
        all_alerts = []
        for key, val in results.items():
            if isinstance(val, dict):
                all_alerts.extend(val.get("alerts", []))

        results["total_alerts"] = len(all_alerts)
        results["critical_alerts"] = len([a for a in all_alerts if a.get("severity") == "CRITICAL"])

        if all_alerts:
            results["warning"] = f"VM THREATS DETECTED: {len(all_alerts)} alerts ({results['critical_alerts']} CRITICAL)"

        ssh.close()
        return results

    return await asyncio.get_event_loop().run_in_executor(None, _sync)
```

- [ ] **Step 2: Register in tools.py**

Add to `poc_os_shield/tools.py` at the end of TOOL_DISPATCH dict (line ~2834):

```python
# VM Detection (meta-tool)
from vm_detection_tools import scan_vm_threats
TOOL_DISPATCH["scan_vm_threats"] = scan_vm_threats
```

Add to TOOL_DEFINITIONS array (line ~3356):

```python
{
    "type": "function",
    "function": {
        "name": "scan_vm_threats",
        "description": "Scan the MultiseatOS VM for security threats. Checks: backdoors (cron/bashrc/systemd), suspicious processes, credential theft, network anomalies, log tampering, vault brute force, file changes, privilege escalation, IDS status. Returns consolidated JSON with per-check results and alerts.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_json": {
                    "type": "string",
                    "description": "Optional baseline JSON for comparison",
                    "default": "",
                },
            },
            "required": [],
        },
    },
},
```

- [ ] **Step 3: Add to orchestrator system prompt**

Add after line 118 in `poc_os_shield/orchestrator.py` (after EXTERNAL TARGET DETECTION):

```python
"VM DEFENSE:\n"
"- scan_vm_threats: COMPREHENSIVE VM scan — backdoors, processes, credentials, network, logs, vault, files, privilege escalation, IDS status. Run this EVERY round.\n\n"
```

- [ ] **Step 4: Test meta-tool standalone**

Run: `cd poc_os_shield && python -c "import asyncio; from vm_detection_tools import scan_vm_threats; print(asyncio.run(scan_vm_threats()))"`
Expected: JSON with vm_available=True and per-check results

- [ ] **Step 5: Commit**

```bash
git add poc_os_shield/vm_detection_tools.py
git commit -m "feat: add VM detection meta-tool scan_vm_threats"
```

---

### Task 5: VM Enforcement Tools

**Files:**
- Create: `poc_os_shield/vm_enforcement_tools.py`
- Modify: `poc_os_shield/enforcer.py` (line ~184, add vm_ dispatch)
- Modify: `poc_os_shield/analyzer.py` (line ~52, add vm_ action types)

- [ ] **Step 1: Create vm_enforcement_tools.py**

```python
"""
VM Enforcement Tools — Active response via SSH
=================================================
6 enforcement actions executed inside the VM.
Called by EnforcerAgent when action_type starts with "vm_".
"""

import json
import logging
import os
import sys

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

_rb_path = os.path.join(os.path.dirname(__file__), "..", "poc_red_blue")
if _rb_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_rb_path))

try:
    from infra import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS, VAULT_HOST, VAULT_PORT
except ImportError:
    VM_SSH_HOST = VM_SSH_PORT = VM_SSH_USER = VM_SSH_PASS = None


def _ssh_connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_SSH_HOST, port=VM_SSH_PORT, username=VM_SSH_USER,
                password=VM_SSH_PASS, timeout=10)
    return ssh


def _ssh_run(ssh, cmd, timeout=10):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", errors="replace").strip(), err.read().decode("utf-8", errors="replace").strip()


async def vm_kill_process(params: dict) -> tuple[bool, str]:
    import asyncio
    pid = params.get("pid")
    if not pid:
        return False, "No PID provided"
    def _sync():
        ssh = _ssh_connect()
        out, err = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S kill -9 {pid} 2>/dev/null")
        ssh.close()
        return True, f"Killed VM process PID {pid}"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def vm_remove_backdoor(params: dict) -> tuple[bool, str]:
    import asyncio
    def _sync():
        ssh = _ssh_connect()
        results = []
        # Remove cron backdoors
        out, _ = _ssh_run(ssh, "crontab -l 2>/dev/null | grep -v 'REDBLUE\\|reverse\\|backdoor\\|/dev/tcp' | crontab - 2>/dev/null")
        results.append("crontab cleaned")
        # Remove bashrc backdoors
        _ssh_run(ssh, "sed -i '/REDBLUE/d' ~/.bashrc 2>/dev/null")
        _ssh_run(ssh, "sed -i '/reverse/d' ~/.bashrc 2>/dev/null")
        _ssh_run(ssh, "sed -i '/backdoor/d' ~/.bashrc 2>/dev/null")
        results.append("bashrc cleaned")
        # Remove rogue systemd services
        svc = params.get("service_name", "")
        if svc:
            _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl stop {svc} 2>/dev/null")
            _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl disable {svc} 2>/dev/null")
            results.append(f"service {svc} disabled")
        # Remove redblue-backdoor if exists
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl stop redblue-backdoor 2>/dev/null")
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl disable redblue-backdoor 2>/dev/null")
        results.append("redblue-backdoor disabled")
        ssh.close()
        return True, f"Backdoors removed: {', '.join(results)}"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def vm_restart_service(params: dict) -> tuple[bool, str]:
    import asyncio
    service = params.get("service_name", "")
    if not service:
        return False, "No service_name provided"
    def _sync():
        ssh = _ssh_connect()
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl restart {service}")
        out, _ = _ssh_run(ssh, f"systemctl is-active {service}")
        ssh.close()
        return "active" in out, f"Service {service}: {out}"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def vm_block_ip(params: dict) -> tuple[bool, str]:
    import asyncio
    ip = params.get("ip", "")
    if not ip:
        return False, "No IP provided"
    def _sync():
        ssh = _ssh_connect()
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S iptables -A INPUT -s {ip} -j DROP")
        ssh.close()
        return True, f"Blocked IP {ip} in VM firewall"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def vm_rotate_vault_tokens(params: dict) -> tuple[bool, str]:
    import asyncio
    import urllib.request
    def _sync():
        try:
            req = urllib.request.Request(
                f"http://{VAULT_HOST}:{VAULT_PORT}/api/auth/revoke-all",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            urllib.request.urlopen(req, timeout=5)
            return True, "All vault tokens revoked"
        except Exception as e:
            return False, f"Token rotation failed: {e}"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def vm_restore_logs(params: dict) -> tuple[bool, str]:
    import asyncio
    def _sync():
        ssh = _ssh_connect()
        # Create backup dir if needed, then restore
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S bash -c 'for log in auth.log syslog kern.log; do [ ! -s /var/log/$log ] && echo \"Log restored at $(date)\" > /var/log/$log; done'")
        # Restart rsyslog to resume logging
        _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl restart rsyslog")
        ssh.close()
        return True, "Logs restored and rsyslog restarted"
    return await asyncio.get_event_loop().run_in_executor(None, _sync)


VM_ENFORCEMENT_DISPATCH = {
    "vm_kill_process": vm_kill_process,
    "vm_remove_backdoor": vm_remove_backdoor,
    "vm_restart_service": vm_restart_service,
    "vm_block_ip": vm_block_ip,
    "vm_rotate_vault_tokens": vm_rotate_vault_tokens,
    "vm_restore_logs": vm_restore_logs,
}
```

- [ ] **Step 2: Add VM dispatch to enforcer.py**

Add at the top of `handle_enforce` method in `poc_os_shield/enforcer.py`, right after `params = json.loads(message.parameters_json)` (line 61):

```python
        # VM enforcement — bypass REDBLUE_ checks, dispatch via SSH
        if message.action_type.startswith("vm_"):
            try:
                from vm_enforcement_tools import VM_ENFORCEMENT_DISPATCH
                vm_fn = VM_ENFORCEMENT_DISPATCH.get(message.action_type)
                if vm_fn:
                    print(f"  [ENFORCER] VM action: {message.action_type}", flush=True)
                    success, details = await vm_fn(params)
                    return EnforceResult(
                        action_type=message.action_type,
                        success=success,
                        details=details,
                    )
                else:
                    return EnforceResult(
                        action_type=message.action_type,
                        success=False,
                        details=f"Unknown VM action: {message.action_type}",
                    )
            except ImportError:
                return EnforceResult(
                    action_type=message.action_type,
                    success=False,
                    details="VM enforcement tools not available",
                )
```

- [ ] **Step 3: Add VM action types to analyzer prompt**

Add to `poc_os_shield/analyzer.py` in the RECOMMENDED_ACTIONS section of the system prompt (line ~52), extend the action_type list:

```python
"VM ENFORCEMENT (use for VM-specific threats):\n"
"- vm_kill_process: Kill process in VM (params: {pid})\n"
"- vm_remove_backdoor: Remove cron/bashrc/systemd backdoors (params: {service_name?})\n"
"- vm_restart_service: Restart stopped VM service (params: {service_name})\n"
"- vm_block_ip: Block IP in VM iptables (params: {ip})\n"
"- vm_rotate_vault_tokens: Invalidate all vault tokens (no params)\n"
"- vm_restore_logs: Restore truncated/deleted logs (no params)\n\n"
```

- [ ] **Step 4: Commit**

```bash
git add poc_os_shield/vm_enforcement_tools.py
git commit -m "feat: add VM enforcement tools + enforcer dispatch"
```

---

### Task 6: Scoring Extension (Response + Resilience)

**Files:**
- Modify: `poc_red_blue/messages.py` (JudgeVerdict, line ~104)
- Modify: `poc_red_blue/judge/scoring.py` (add 2 new functions)
- Modify: `poc_red_blue/judge/judge_agent.py` (use 3D scoring)

- [ ] **Step 1: Add fields to JudgeVerdict**

In `poc_red_blue/messages.py`, add after `false_positive_rate` (line 110):

```python
    response_score: float             # 0-100: what % of threats were remediated
    resilience_score: float           # 0-100: is VM still compromised after response
```

- [ ] **Step 2: Add scoring functions to scoring.py**

Add after `compute_scores()` in `poc_red_blue/judge/scoring.py`:

```python
def compute_response_score(
    enforcement_results: list[dict],
    recommended_actions: int,
) -> float:
    """Score: what percentage of recommended actions succeeded?"""
    if recommended_actions == 0:
        return 100.0  # Nothing to do = perfect score
    successful = sum(1 for r in enforcement_results if r.get("success", False))
    return (successful / recommended_actions) * 100


def compute_resilience_score(
    threats_found: int,
    threats_remaining: int,
) -> float:
    """Score: are threats gone after Blue Team response?
    Formula: (1 - threats_remaining / max(threats_found, 1)) * 100
    """
    if threats_found == 0:
        return 100.0
    return (1 - threats_remaining / max(threats_found, 1)) * 100
```

Update `compute_scores()` to use the new blue formula:

```python
def compute_scores(
    detection_rate: float,
    false_positive_rate: float,
    attacks_count: int,
    categories_used: int,
    response_score: float = 100.0,
    resilience_score: float = 100.0,
) -> tuple[float, float]:
    """Compute Red and Blue team scores. Blue uses 3D scoring."""
    # Blue score: Detection (40%) + Response (30%) + Resilience (30%)
    detection_pct = detection_rate * 100
    blue_score = (detection_pct * 0.4) + (response_score * 0.3) + (resilience_score * 0.3)
    blue_score = max(0, min(100, blue_score))

    # Red score unchanged
    evasion_rate = 1 - detection_rate
    variety_bonus = min(categories_used / 6, 1.0) * 20
    red_score = (evasion_rate * 80 * 100) + variety_bonus
    red_score = max(0, min(100, red_score))

    return red_score, blue_score
```

Update `aggregate_verdicts()` to include new scores:

```python
def aggregate_verdicts(verdicts: list[dict]) -> dict:
    if not verdicts:
        return {"overall_red_score": 0, "overall_blue_score": 0,
                "avg_detection_rate": 0, "avg_response_score": 0,
                "avg_resilience_score": 0, "total_rounds": 0}

    return {
        "overall_red_score": round(sum(v.get("red_score", 0) for v in verdicts) / len(verdicts), 1),
        "overall_blue_score": round(sum(v.get("blue_score", 0) for v in verdicts) / len(verdicts), 1),
        "avg_detection_rate": round(sum(v.get("detection_rate", 0) for v in verdicts) / len(verdicts), 3),
        "avg_response_score": round(sum(v.get("response_score", 0) for v in verdicts) / len(verdicts), 1),
        "avg_resilience_score": round(sum(v.get("resilience_score", 0) for v in verdicts) / len(verdicts), 1),
        "total_rounds": len(verdicts),
    }
```

- [ ] **Step 3: Update judge_agent.py to produce 3D scores**

In `handle_judge_request`, after computing detection_rate, add:

```python
        # Response score: how many enforcement actions succeeded
        enforcement_results = []
        if isinstance(blue_report, dict):
            try:
                er_str = blue_report.get("enforcement_results_json", "[]")
                if isinstance(er_str, str):
                    enforcement_results = json.loads(er_str)
            except (json.JSONDecodeError, TypeError):
                pass
        recommended_count = blue_report.get("actions_taken", 0) if isinstance(blue_report, dict) else 0
        response_score = compute_response_score(enforcement_results, max(recommended_count, len(enforcement_results)))

        # Resilience score: placeholder — stealth IDS post-check happens in game_controller
        resilience_score = 100.0  # Will be overridden by game_controller if VM data available
```

Update the `compute_scores` call:

```python
        red_score, blue_score = compute_scores(
            detection_rate, false_positive_rate, len(successful_attacks), categories_used,
            response_score=response_score, resilience_score=resilience_score,
        )
```

Update the returned JudgeVerdict:

```python
        return JudgeVerdict(
            round_number=message.round_number,
            red_score=round(red_score, 1),
            blue_score=round(blue_score, 1),
            detection_rate=round(detection_rate, 3),
            false_positive_rate=round(false_positive_rate, 3),
            response_score=round(response_score, 1),
            resilience_score=round(resilience_score, 1),
            gaps_json=json.dumps(gaps, ensure_ascii=False),
            recommendations_json=json.dumps(recommendations, ensure_ascii=False),
            narrative=narrative,
        )
```

- [ ] **Step 4: Commit**

```bash
git add poc_red_blue/messages.py poc_red_blue/judge/scoring.py poc_red_blue/judge/judge_agent.py
git commit -m "feat: add 3D scoring (detection + response + resilience)"
```

---

### Task 7: Red Team IDS Evasion Tools

**Files:**
- Modify: `poc_red_blue/red_team/vm_attack_tools.py` (add 4 tools after vm_cleanup_all)
- Modify: `poc_red_blue/red_team/orchestrator.py` (add category mapping)
- Modify: `poc_red_blue/judge/scoring.py` (add detection keywords)

- [ ] **Step 1: Add 4 IDS evasion tools to vm_attack_tools.py**

Add before `VM_TOOL_DISPATCH` dict:

```python
async def vm_find_ids_services() -> dict:
    """Enumerate all running services to find IDS processes."""
    ssh = _ssh_connect()
    services = _ssh_run(ssh, "systemctl list-units --type=service --state=running --no-pager --no-legend")
    # Look for security-related services
    suspicious = []
    for line in services.split("\n"):
        lower = line.lower()
        if any(kw in lower for kw in ["security", "monitor", "ids", "detect", "watch", "guard"]):
            suspicious.append(line.strip()[:100])
    # Also check for unusual services
    unusual = _ssh_run(ssh, "systemctl list-units --type=service --state=running --no-pager --no-legend | grep -vE 'ssh|systemd|dbus|network|cron|rsyslog|snapd|ufw|plymouth|polkit|accounts|ModemManager|secret-vault|system-monitor'")
    ssh.close()
    path, artifact = _save_result("ids_services.json", {"suspicious": suspicious, "unusual": unusual[:2000]})
    return {"success": True, "description": f"IDS hunt: {len(suspicious)} suspicious services found", "artifact": artifact}


async def vm_kill_decoy_ids() -> dict:
    """Stop the obvious vm-security-monitor IDS service."""
    ssh = _ssh_connect()
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl stop vm-security-monitor")
    status = _ssh_run(ssh, "systemctl is-active vm-security-monitor 2>/dev/null")
    ssh.close()
    path, artifact = _save_result("decoy_killed.json", {"status": status, "killed": "inactive" in status})
    return {"success": "inactive" in status, "description": f"Decoy IDS: {status}", "artifact": artifact}


async def vm_hunt_stealth_ids() -> dict:
    """Search for hidden monitoring processes in the VM."""
    ssh = _ssh_connect()
    # Check for processes listening on unusual ports
    listeners = _ssh_run(ssh, "ss -tlnp | grep -vE ':22 |:8000 |:9090 |:5432 |:6379'")
    # Check for python processes in system paths
    sys_python = _ssh_run(ssh, "ps aux | grep 'python.*dbus\\|python.*/usr/lib\\|python.*/var/lib' | grep -v grep")
    # Check hidden files
    hidden = _ssh_run(ssh, "find /var/lib/.cache -type f 2>/dev/null")
    ssh.close()
    found = bool(sys_python.strip() or hidden.strip())
    path, artifact = _save_result("stealth_hunt.json", {
        "unusual_listeners": listeners[:1000], "system_python": sys_python[:500],
        "hidden_files": hidden[:500], "stealth_found": found,
    })
    return {"success": True, "description": f"Stealth hunt: {'FOUND hidden IDS!' if found else 'nothing found'}", "artifact": artifact}


async def vm_tamper_ids_logs() -> dict:
    """Corrupt/delete IDS log files to blind the defender."""
    ssh = _ssh_connect()
    results = {}
    # Clear decoy logs
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S truncate -s 0 /var/log/vm-security.log 2>/dev/null")
    results["decoy_log"] = "truncated"
    # Clear stealth metrics
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S truncate -s 0 /var/lib/.cache/.metrics 2>/dev/null")
    results["stealth_metrics"] = "truncated"
    # Remove heartbeat
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S rm -f /var/lib/.cache/.heartbeat 2>/dev/null")
    results["heartbeat"] = "deleted"
    ssh.close()
    path, artifact = _save_result("ids_tampered.json", results)
    return {"success": True, "description": "IDS logs tampered: decoy + stealth metrics cleared", "artifact": artifact}
```

- [ ] **Step 2: Register in VM_TOOL_DISPATCH and VM_TOOL_DEFINITIONS**

Add to `VM_TOOL_DISPATCH`:

```python
    "vm_find_ids_services": vm_find_ids_services,
    "vm_kill_decoy_ids": vm_kill_decoy_ids,
    "vm_hunt_stealth_ids": vm_hunt_stealth_ids,
    "vm_tamper_ids_logs": vm_tamper_ids_logs,
```

Add to `VM_TOOL_DEFINITIONS`:

```python
    {"type": "function", "function": {"name": "vm_find_ids_services", "description": "REAL: Enumerate VM services to find IDS/security monitoring processes.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_kill_decoy_ids", "description": "REAL: Stop the visible vm-security-monitor IDS service.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_hunt_stealth_ids", "description": "REAL: Hunt for hidden IDS — check unusual listeners, system python processes, hidden files.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_tamper_ids_logs", "description": "REAL: Clear IDS log files and heartbeat to blind the defender.", "parameters": {"type": "object", "properties": {}, "required": []}}},
```

- [ ] **Step 3: Add category mapping in orchestrator.py**

Add to `TOOL_CATEGORIES` dict in `poc_red_blue/red_team/orchestrator.py`:

```python
    "vm_find_ids_services": "ids_evasion",
    "vm_kill_decoy_ids": "ids_evasion",
    "vm_hunt_stealth_ids": "ids_evasion",
    "vm_tamper_ids_logs": "ids_evasion",
```

- [ ] **Step 4: Add detection keywords in scoring.py**

Add to `TOOL_DETECTION_KEYWORDS` dict in `poc_red_blue/judge/scoring.py`:

```python
    "vm_find_ids_services": ["ids", "security monitor", "service enum"],
    "vm_kill_decoy_ids": ["ids", "decoy", "service stop", "security monitor"],
    "vm_hunt_stealth_ids": ["stealth", "hidden", "hunt", "dbus"],
    "vm_tamper_ids_logs": ["log tamper", "metrics", "heartbeat", "ids blind"],
```

- [ ] **Step 5: Commit**

```bash
git add poc_red_blue/red_team/vm_attack_tools.py poc_red_blue/red_team/orchestrator.py poc_red_blue/judge/scoring.py
git commit -m "feat: add Red Team IDS evasion tools (Category 25)"
```

---

### Task 8: Vault Login Attempt API + Config + Exercise Setup

**Files:**
- Modify: `poc_red_blue/vm_deploy.py` (add /api/auth/attempts endpoint)
- Modify: `poc_red_blue/config.py` (add VM_IDS settings)
- Modify: `poc_red_blue/start_exercise.py` (add IDS deploy step + port 19091)

- [ ] **Step 1: Add /api/auth/attempts to vault server**

In `poc_red_blue/vm_deploy.py`, add to the VAULT_SERVER string in the `VaultHandler.do_GET` method, before the final `else`:

```python
        elif self.path == "/api/auth/attempts":
            total = sum(len(v) for v in LOGIN_ATTEMPTS.values())
            failed = total - len(TOKENS)
            last_failed = ""
            self._send(200, {"total": total, "failed": failed, "last_failed": last_failed})
```

And add `/api/auth/revoke-all` to `do_POST`:

```python
        elif self.path == "/api/auth/revoke-all":
            count = len(TOKENS)
            TOKENS.clear()
            self._send(200, {"revoked": count})
```

- [ ] **Step 2: Add config settings**

Add to `poc_red_blue/config.py`:

```python
# ================================================================
# VM IDS
# ================================================================

VM_IDS_ENABLED = True              # Deploy IDS during exercise setup
STEALTH_IDS_PORT = 19091           # Host port for stealth IDS metrics
```

- [ ] **Step 3: Add IDS deployment + port forwarding to start_exercise.py**

Add new step between [3/6] and [4/6]. Renumber to [3.5/7] or renumber all to 7 steps.

After the service restart block, add:

```python
    # ---- Step 3.5: Deploy IDS ----
    from config import VM_IDS_ENABLED, STEALTH_IDS_PORT
    if VM_IDS_ENABLED:
        print("[3.5/7] Deploying VM IDS (Decoy + Stealth)...")
        # Add port forwarding for stealth IDS metrics
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", "delete", "ids"],
                       capture_output=True, timeout=5)
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1",
                        f"ids,tcp,,{STEALTH_IDS_PORT},,19091"],
                       capture_output=True, timeout=5)
        subprocess.run(
            [sys.executable, "-m", "vm_ids.deploy_ids"],
            cwd=SCRIPT_DIR,
        )
    print()
```

- [ ] **Step 4: Re-deploy vault with new endpoints**

Run: `cd poc_red_blue && python vm_deploy.py`
Then verify: `curl http://127.0.0.1:18000/api/auth/attempts`
Expected: `{"total": 0, "failed": 0, "last_failed": ""}`

- [ ] **Step 5: Commit**

```bash
git add poc_red_blue/vm_deploy.py poc_red_blue/config.py poc_red_blue/start_exercise.py
git commit -m "feat: vault attempt API + IDS config + exercise setup"
```

---

### Task 9: Integration Test — 3 Rounds

- [ ] **Step 1: Run full exercise**

```bash
cd poc_red_blue
python start_exercise.py --rounds 3
```

Expected:
- IDS deployment succeeds (Decoy + Stealth active)
- Blue Team calls `scan_vm_threats` during detection phase
- Blue Team recommends `vm_remove_backdoor`, `vm_restart_service` actions
- Judge produces 3D scores (detection + response + resilience)
- Red Team attempts IDS evasion in later rounds

- [ ] **Step 2: Verify reports**

```bash
cat reports/round_01.json | python -m json.tool | head -50
```

Check that:
- Blue Team report includes VM findings
- Verdict includes response_score and resilience_score
- Gaps reference VM-specific detections

- [ ] **Step 3: Commit reports**

```bash
git add reports/
git commit -m "test: 3-round exercise with VM defense system"
```
