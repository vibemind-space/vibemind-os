"""
VM Live Dashboard — Read-Only Monitoring
============================================
Zeigt live den Zustand der MultiseatOS VM waehrend des Red/Blue Exercise.
Nur lesende Befehle (ps, ss, systemctl, cat). Aendert NICHTS.

SSH Key Pinning: Speichert den Host-Key beim ersten Connect und
verifiziert ihn bei jedem weiteren — MITM/Key-Swap wird erkannt.

Usage:
  python vm_dashboard.py              # Standard (refresh alle 3s)
  python vm_dashboard.py --interval 5 # Alle 5 Sekunden
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime

import paramiko

# Connection
VM_HOST = "127.0.0.1"
VM_PORT = 2222
VM_USER = "vibemind"
VM_PASS = "logitech66"

# Key pinning file (host-side, not in VM)
KEY_PIN_FILE = os.path.join(os.path.dirname(__file__), ".vm_host_key_pin.json")

# Shared Folder Guard integration
GUARD_ALERT_LOG = os.path.join(
    r"C:\Users\User\Stephane\multiseat-os", ".guard", ".alerts.json"
)


class HostKeyPinner(paramiko.MissingHostKeyPolicy):
    """SSH Host Key Pinning — prevents MITM and key swap attacks.

    First connect: saves the host key fingerprint.
    Subsequent connects: rejects if key changed (= attacker swapped it).
    """

    def missing_host_key(self, client, hostname, key):
        current_fp = hashlib.sha256(key.asbytes()).hexdigest()
        current_type = key.get_name()

        if os.path.exists(KEY_PIN_FILE):
            with open(KEY_PIN_FILE) as f:
                pinned = json.load(f)
            pinned_fp = pinned.get("fingerprint", "")

            if pinned_fp != current_fp:
                raise paramiko.SSHException(
                    f"\n{'!'*60}\n"
                    f"  SSH HOST KEY CHANGED — POSSIBLE ATTACK!\n"
                    f"  Pinned:  {pinned_fp[:32]}...\n"
                    f"  Current: {current_fp[:32]}...\n"
                    f"  Someone may have replaced the VM SSH key!\n"
                    f"  Delete {KEY_PIN_FILE} to re-pin if intentional.\n"
                    f"{'!'*60}"
                )
        else:
            # First connect — pin the key
            pin_data = {
                "fingerprint": current_fp,
                "key_type": current_type,
                "pinned_at": datetime.now().isoformat(),
                "hostname": hostname,
            }
            with open(KEY_PIN_FILE, "w") as f:
                json.dump(pin_data, f, indent=2)
            print(f"  [KEY PIN] Host key pinned: {current_fp[:32]}...")


def ssh_connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(HostKeyPinner())
    ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER, password=VM_PASS, timeout=5)
    return ssh


def ssh_read(ssh, cmd, timeout=5):
    """Execute read-only command. Returns stdout string."""
    try:
        _, stdout, _ = ssh.exec_command(cmd, timeout=timeout)
        return stdout.read().decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"[error: {e}]"


def get_guard_alerts():
    """Read shared folder guard alerts (host-side)."""
    try:
        if os.path.exists(GUARD_ALERT_LOG):
            with open(GUARD_ALERT_LOG) as f:
                alerts = json.load(f)
            return [a for a in alerts if a.get("type") not in ("HONEYPOT_ACCESSED",)]
        return []
    except Exception:
        return []


def clear_screen():
    subprocess.run(["cmd", "/c", "cls"], shell=False)


def render_dashboard(ssh, cycle, start_time):
    """Collect data and render dashboard."""
    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    # ---- Collect data (all read-only) ----
    proc_count = ssh_read(ssh, "ps aux --no-headers | wc -l")
    suspicious_procs = ssh_read(ssh, (
        "ps aux --no-headers | grep -iE 'REDBLUE|mimikatz|beacon|backdoor|lazagne|procdump|nmap|masscan' "
        "| grep -v grep | head -8"
    ))

    listeners = ssh_read(ssh, "ss -tlnp 2>/dev/null | tail -n +2 | wc -l")
    connections = ssh_read(ssh, "ss -tnp 2>/dev/null | tail -n +2 | wc -l")
    suspicious_ports = ssh_read(ssh, (
        "ss -tlnp 2>/dev/null | grep -E ':4444|:5555|:1337|:6667|:8888|:9999' | head -5"
    ))

    vault_status = ssh_read(ssh, "systemctl is-active secret-vault 2>/dev/null")
    monitor_status = ssh_read(ssh, "systemctl is-active system-monitor 2>/dev/null")
    cron_status = ssh_read(ssh, "systemctl is-active cron 2>/dev/null")
    rsyslog_status = ssh_read(ssh, "systemctl is-active rsyslog 2>/dev/null")

    crontab = ssh_read(ssh, "crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$'")
    bashrc_backdoor = ssh_read(ssh, "grep -c 'REDBLUE' ~/.bashrc 2>/dev/null")
    systemd_backdoor = ssh_read(ssh, "systemctl is-enabled redblue-backdoor 2>/dev/null")

    auth_log_size = ssh_read(ssh, "wc -c < /var/log/auth.log 2>/dev/null")
    syslog_size = ssh_read(ssh, "wc -c < /var/log/syslog 2>/dev/null")

    temp_redblue = ssh_read(ssh, "find /tmp -name '*REDBLUE*' -o -name '*redblue*' 2>/dev/null | head -5")

    # SSH key integrity check (did someone regenerate host keys?)
    ssh_key_hash = ssh_read(ssh, "sha256sum /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null | cut -d' ' -f1")

    guard_alerts = get_guard_alerts()

    # ---- Render ----
    clear_screen()

    R = "\033[91m"  # red
    G = "\033[92m"  # green
    Y = "\033[93m"  # yellow
    B = "\033[1m"   # bold
    D = "\033[90m"  # dim
    X = "\033[0m"   # reset

    def svc(status):
        s = status.strip()
        if s == "active": return f"{G}RUNNING{X}"
        if s in ("inactive", "dead"): return f"{R}DOWN{X}"
        return f"{Y}{s[:12]}{X}"

    print(f"{B}{'=' * 62}{X}")
    print(f"{B}  VM LIVE DASHBOARD  |  Cycle {cycle}  |  {mins:02d}:{secs:02d}  |  {datetime.now().strftime('%H:%M:%S')}{X}")
    print(f"{B}{'=' * 62}{X}")
    print()

    # Services
    print(f"  {B}SERVICES:{X}")
    print(f"    secret-vault:    {svc(vault_status)}")
    print(f"    system-monitor:  {svc(monitor_status)}")
    print(f"    cron:            {svc(cron_status)}")
    print(f"    rsyslog:         {svc(rsyslog_status)}")
    print()

    # Processes
    print(f"  {B}PROCESSES:{X} {proc_count} running")
    if suspicious_procs:
        for line in suspicious_procs.split("\n")[:5]:
            parts = line.split()
            if len(parts) >= 11:
                print(f"    {R}!!{X} PID {parts[1]:>6}  {' '.join(parts[10:])[:55]}")
    else:
        print(f"    {G}(keine verdaechtigen Prozesse){X}")
    print()

    # Network
    print(f"  {B}NETWORK:{X} {listeners} listeners, {connections} connections")
    if suspicious_ports:
        for line in suspicious_ports.split("\n")[:3]:
            print(f"    {R}!!{X} {line.strip()[:65]}")
    print()

    # Persistence
    print(f"  {B}PERSISTENCE:{X}")
    cron_lines = [l for l in (crontab or "").split("\n") if l.strip()]
    if cron_lines:
        for l in cron_lines[:3]:
            print(f"    {R}CRON{X} {l[:55]}")
    else:
        print(f"    {G}crontab: clean{X}")
    bc = int(bashrc_backdoor) if bashrc_backdoor.isdigit() else 0
    if bc > 0:
        print(f"    {R}.bashrc: {bc} REDBLUE entries!{X}")
    else:
        print(f"    {G}.bashrc: clean{X}")
    if "enabled" in systemd_backdoor:
        print(f"    {R}systemd backdoor: ENABLED!{X}")
    else:
        print(f"    {G}systemd backdoor: none{X}")
    print()

    # Logs
    print(f"  {B}LOGS:{X}")
    ab = int(auth_log_size) if auth_log_size.strip().isdigit() else -1
    sb = int(syslog_size) if syslog_size.strip().isdigit() else -1
    if ab == 0:
        print(f"    {R}auth.log: TRUNCATED (0 bytes)!{X}")
    elif ab > 0:
        print(f"    auth.log: {ab:,} bytes")
    if sb == 0:
        print(f"    {R}syslog: TRUNCATED (0 bytes)!{X}")
    elif sb > 0:
        print(f"    syslog: {sb:,} bytes")
    print()

    # SSH Key Integrity
    if ssh_key_hash and "error" not in ssh_key_hash.lower():
        print(f"  {B}SSH KEY:{X} {D}{ssh_key_hash[:32]}...{X}")
    print()

    # Attack Artifacts
    if temp_redblue:
        print(f"  {B}ATTACK ARTIFACTS:{X}")
        for f in temp_redblue.split("\n")[:5]:
            print(f"    {R}FILE{X} {f.strip()}")
        print()

    # Shared Folder Guard
    if guard_alerts:
        print(f"  {R}{B}{'!' * 50}{X}")
        print(f"  {R}{B}SHARED FOLDER: {len(guard_alerts)} ALERTS!{X}")
        for a in guard_alerts[:3]:
            print(f"    {R}{a.get('type', '')}: {a.get('file', '')}{X}")
        print(f"  {R}{B}{'!' * 50}{X}")
        print()

    print(f"{D}  Ctrl+C to stop  |  Read-only  |  SSH Key Pinned{X}")
    print(f"{B}{'=' * 62}{X}")


def main():
    parser = argparse.ArgumentParser(description="VM Live Dashboard")
    parser.add_argument("--interval", type=int, default=3, help="Refresh interval")
    args = parser.parse_args()

    print("Connecting to VM (with host key pinning)...")
    ssh = None
    start_time = time.time()
    cycle = 0

    try:
        while True:
            cycle += 1
            try:
                if ssh is None or not ssh.get_transport() or not ssh.get_transport().is_active():
                    ssh = ssh_connect()
                render_dashboard(ssh, cycle, start_time)
            except paramiko.SSHException as e:
                clear_screen()
                print(f"\n  {str(e)}")
                print(f"\n  Dashboard stopped — SSH key mismatch!")
                break
            except Exception as e:
                clear_screen()
                print(f"\n  VM Dashboard — Connection Error: {e}")
                print(f"  Retrying in {args.interval}s...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\n  Dashboard stopped.")
    finally:
        if ssh:
            ssh.close()


if __name__ == "__main__":
    main()
