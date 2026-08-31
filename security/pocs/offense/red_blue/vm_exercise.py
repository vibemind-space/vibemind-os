"""
VM Exercise Launcher — Host-Side Only Script
=================================================
This is the ONLY script that runs on your Windows PC.
Everything else runs INSIDE the VM.

Usage:
  python vm_exercise.py --rounds 3
  python vm_exercise.py --rounds 5 --deploy   # Force re-deploy
  python vm_exercise.py --fetch-reports        # Only fetch reports

Flow:
  1. Start VM (VBoxManage)
  2. Wait for SSH
  3. Deploy exercise code into VM (SFTP)
  4. Install dependencies in VM (pip)
  5. Run exercise inside VM (SSH)
  6. Fetch reports back to host (SFTP)
  7. Run Issue Agent on host (needs gh CLI)
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# ================================================================
# Config
# ================================================================

VBOX = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
VM_NAME = "MultiseatOS"
VM_HOST = "127.0.0.1"
VM_PORT = 2222
VM_USER = "vibemind"
VM_PASS = "logitech66"

# Shared llm_client.py / llm_config.yml / .env live at the security/ root.
PROJECT_ROOT = Path(__file__).parents[3]
RED_BLUE_DIR = Path(__file__).parent
VM_EXERCISE_DIR = "/home/vibemind/exercise"
VM_REPORTS_DIR = f"{VM_EXERCISE_DIR}/reports"

# Directories to deploy into VM, as (local source, flat VM name). os_shield now
# lives under security/pocs/defense/; the VM keeps the flat poc_* names the runner
# script expects.
DEPLOY_DIRS = [
    (str(Path(__file__).parent), "poc_red_blue"),
    (str(Path(__file__).parents[2] / "defense" / "os_shield"), "poc_os_shield"),
]
DEPLOY_FILES = [
    "llm_config.yml",
    "llm_client.py",
    ".env",
    "requirements.txt",
]

# Port forwarding (host:vm)
PORT_FORWARDS = [
    ("ssh", "2222", "22"),
    ("vault", "18000", "8000"),
    ("api", "19090", "9090"),
    ("ids", "19091", "19091"),
]


# ================================================================
# Helpers
# ================================================================

def vm_state():
    r = subprocess.run([VBOX, "showvminfo", VM_NAME, "--machinereadable"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        if line.startswith("VMState="):
            return line.split("=")[1].strip('"')
    return "unknown"


def ssh_connect(retries=20, delay=5):
    for i in range(retries):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(VM_HOST, port=VM_PORT, username=VM_USER,
                        password=VM_PASS, timeout=10, banner_timeout=15)
            return ssh
        except Exception:
            if i < retries - 1:
                print(".", end="", flush=True)
                time.sleep(delay)
    raise ConnectionError("SSH not reachable after retries")


def ssh_run(ssh, cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", errors="replace").strip()
    e = err.read().decode("utf-8", errors="replace").strip()
    rc = out.channel.recv_exit_status()
    return o, e, rc


def sudo(ssh, cmd, timeout=30):
    return ssh_run(ssh, f"echo '{VM_PASS}' | sudo -S bash -c '{cmd}'", timeout=timeout)


def upload_dir(sftp, local_dir, remote_dir):
    """Recursively upload a directory via SFTP."""
    for root, dirs, files in os.walk(local_dir):
        # Skip __pycache__, .git, node_modules, .venv
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", ".venv", ".claude")]

        rel_root = os.path.relpath(root, local_dir)
        remote_root = f"{remote_dir}/{rel_root}".replace("\\", "/").replace("/.", "")
        if rel_root == ".":
            remote_root = remote_dir

        try:
            sftp.stat(remote_root)
        except FileNotFoundError:
            sftp.mkdir(remote_root)

        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            local_path = os.path.join(root, f)
            remote_path = f"{remote_root}/{f}"
            try:
                sftp.put(local_path, remote_path)
            except Exception as e:
                print(f"    WARN: {remote_path}: {e}")


# ================================================================
# Phase 1: Start VM
# ================================================================

def phase1_start_vm():
    print("[1/7] VM Check...", flush=True)
    state = vm_state()
    if state == "running":
        print(f"  VM laeuft bereits")
    else:
        print(f"  VM ist {state}. Starte mit GUI...")
        subprocess.run([VBOX, "startvm", VM_NAME], capture_output=True, timeout=30)
        print(f"  Warte 30s auf Boot...", end="", flush=True)
        time.sleep(30)
        print(" OK")

    # Ensure port forwarding
    for name, host_port, vm_port in PORT_FORWARDS:
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", "delete", name],
                       capture_output=True, timeout=5)
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", f"{name},tcp,,{host_port},,{vm_port}"],
                       capture_output=True, timeout=5)
    print()


# ================================================================
# Phase 2: Wait for SSH
# ================================================================

def phase2_ssh():
    print("[2/7] SSH Verbindung...", end="", flush=True)
    ssh = ssh_connect()
    print(f" OK")
    return ssh


# ================================================================
# Phase 3: Deploy code into VM
# ================================================================

def phase3_deploy(ssh, force=False):
    print("[3/7] Code in VM deployen...", flush=True)

    # Check if already deployed
    marker, _, _ = ssh_run(ssh, f"cat {VM_EXERCISE_DIR}/.deployed 2>/dev/null")
    if marker and not force:
        print(f"  Bereits deployed ({marker}). --deploy zum Erzwingen.")
        return

    # Clean old deployment
    ssh_run(ssh, f"rm -rf {VM_EXERCISE_DIR}")
    ssh_run(ssh, f"mkdir -p {VM_EXERCISE_DIR}")
    ssh_run(ssh, f"mkdir -p {VM_REPORTS_DIR}")

    sftp = ssh.open_sftp()

    # Upload directories
    for local, remote_name in DEPLOY_DIRS:
        if os.path.isdir(local):
            remote = f"{VM_EXERCISE_DIR}/{remote_name}"
            print(f"  Uploading {remote_name}/...", end="", flush=True)
            try:
                sftp.stat(remote)
            except FileNotFoundError:
                sftp.mkdir(remote)
            upload_dir(sftp, local, remote)
            print(" OK")

    # Upload root files
    for filename in DEPLOY_FILES:
        local = os.path.join(PROJECT_ROOT, filename)
        if os.path.isfile(local):
            remote = f"{VM_EXERCISE_DIR}/{filename}"
            sftp.put(local, remote)
            print(f"  Uploaded {filename}")

    # Create VM-side runner script
    runner_script = '''#!/usr/bin/env python3
"""VM-side exercise runner — runs INSIDE the VM."""
import os, sys, argparse

# Set up paths
EXERCISE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXERCISE_DIR)
sys.path.insert(0, os.path.join(EXERCISE_DIR, "poc_red_blue"))
sys.path.insert(0, os.path.join(EXERCISE_DIR, "poc_os_shield"))

# Override infra to use localhost (we're inside the VM now)
os.environ["VM_MODE"] = "local"

# Change to exercise dir
os.chdir(os.path.join(EXERCISE_DIR, "poc_red_blue"))

# Run main
from main import main as exercise_main
import asyncio

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    sys.argv = ["main.py", "--rounds", str(args.rounds)]
    asyncio.run(exercise_main())
'''
    with sftp.file(f"{VM_EXERCISE_DIR}/run_exercise.py", "w") as f:
        f.write(runner_script)

    # Write deployment marker
    from datetime import datetime
    with sftp.file(f"{VM_EXERCISE_DIR}/.deployed", "w") as f:
        f.write(datetime.now().isoformat())

    sftp.close()
    print(f"  Deployment complete.")
    print()


# ================================================================
# Phase 4: Install dependencies in VM
# ================================================================

def phase4_install(ssh):
    print("[4/7] Dependencies installieren...", flush=True)

    # Check if already installed
    out, _, rc = ssh_run(ssh, "python3 -c 'import openai, paramiko, psutil; print(\"OK\")' 2>/dev/null")
    if "OK" in out:
        print(f"  Bereits installiert.")
        return

    print(f"  pip install...", end="", flush=True)
    ssh_run(ssh, f"cd {VM_EXERCISE_DIR} && pip3 install --user -q -r requirements.txt 2>/dev/null", timeout=120)

    # Verify
    out2, _, _ = ssh_run(ssh, "python3 -c 'import openai; print(\"OK\")' 2>/dev/null")
    if "OK" in out2:
        print(" OK")
    else:
        print(" Installing with sudo...")
        sudo(ssh, f"pip3 install -q openai paramiko psutil python-dotenv autogen-core pyyaml", timeout=120)
    print()


# ================================================================
# Phase 5: Start services in VM
# ================================================================

def phase5_services(ssh):
    print("[5/7] VM Services starten...", flush=True)
    services = ["secret-vault", "system-monitor", "vm-security-monitor", "dbus-session-helper", "rsyslog", "cron"]
    for svc in services:
        sudo(ssh, f"systemctl restart {svc} 2>/dev/null")

    time.sleep(2)

    for svc in services:
        out, _, _ = ssh_run(ssh, f"systemctl is-active {svc} 2>/dev/null")
        icon = "OK" if "active" == out.strip() else "!!"
        print(f"  [{icon}] {svc}")
    print()


# ================================================================
# Phase 6: Run exercise INSIDE VM
# ================================================================

def phase6_run(ssh, rounds):
    print(f"[6/7] Exercise starten ({rounds} Runden, laeuft IN der VM)...", flush=True)
    print(f"  Alles ab jetzt passiert NUR in der VM.", flush=True)
    print(f"  Dein Windows PC wird NICHT beruehrt.", flush=True)
    print()

    # Run the exercise inside the VM
    cmd = f"cd {VM_EXERCISE_DIR}/poc_red_blue && python3 {VM_EXERCISE_DIR}/run_exercise.py --rounds {rounds} 2>&1"

    # Stream output in real-time
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(cmd)

    while True:
        if channel.recv_ready():
            data = channel.recv(4096).decode("utf-8", errors="replace")
            print(data, end="", flush=True)
        if channel.exit_status_ready():
            # Drain remaining
            while channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="replace")
                print(data, end="", flush=True)
            break
        time.sleep(0.1)

    rc = channel.recv_exit_status()
    print()
    if rc != 0:
        print(f"  Exercise beendet mit Exit Code {rc}")
    else:
        print(f"  Exercise erfolgreich beendet.")
    print()
    return rc


# ================================================================
# Phase 7: Fetch reports back to host
# ================================================================

def phase7_fetch(ssh):
    print("[7/7] Reports zurueckholen...", flush=True)

    local_reports = os.path.join(RED_BLUE_DIR, "reports")
    os.makedirs(local_reports, exist_ok=True)

    sftp = ssh.open_sftp()

    # List remote reports
    try:
        remote_files = sftp.listdir(f"{VM_EXERCISE_DIR}/poc_red_blue/reports")
    except FileNotFoundError:
        print("  Keine Reports gefunden.")
        sftp.close()
        return

    fetched = 0
    for f in remote_files:
        if f.endswith(".json") and not f.startswith("."):
            remote = f"{VM_EXERCISE_DIR}/poc_red_blue/reports/{f}"
            local = os.path.join(local_reports, f)
            sftp.get(remote, local)
            fetched += 1
            print(f"  {f}")

    sftp.close()
    print(f"  {fetched} Reports geholt -> {local_reports}")
    print()


# ================================================================
# Main
# ================================================================

def main():
    parser = argparse.ArgumentParser(description="VM Exercise Launcher")
    parser.add_argument("--rounds", type=int, default=3, help="Anzahl Runden")
    parser.add_argument("--deploy", action="store_true", help="Force re-deploy")
    parser.add_argument("--fetch-reports", action="store_true", help="Nur Reports holen")
    args = parser.parse_args()

    print()
    print("=" * 62)
    print("  VM EXERCISE LAUNCHER")
    print("  Alles laeuft IN der VM — dein PC bleibt sicher")
    print("=" * 62)
    print()

    # Phase 1: Start VM
    phase1_start_vm()

    # Phase 2: SSH
    ssh = phase2_ssh()

    if args.fetch_reports:
        phase7_fetch(ssh)
        ssh.close()
        return

    # Phase 3: Deploy
    phase3_deploy(ssh, force=args.deploy)

    # Phase 4: Install deps
    phase4_install(ssh)

    # Phase 5: Services
    phase5_services(ssh)

    # Phase 6: Run exercise IN VM
    rc = phase6_run(ssh, args.rounds)

    # Phase 7: Fetch reports
    phase7_fetch(ssh)

    ssh.close()

    # Run Issue Agent on host (needs gh CLI)
    print("=" * 62)
    print("  Issue Agent (Host-Side, braucht gh CLI)...")
    print("=" * 62)
    subprocess.call(
        [sys.executable, os.path.join(RED_BLUE_DIR, "issue_agent.py"), "--force"],
        cwd=str(RED_BLUE_DIR),
    )

    print()
    print("=" * 62)
    print("  FERTIG")
    print("=" * 62)
    print(f"  Reports: poc_red_blue/reports/")
    print(f"  Issues:  https://github.com/Flissel/vibemind-os/issues")
    print(f"  VM laeuft noch (manuell stoppen wenn gewuenscht)")
    print()


if __name__ == "__main__":
    main()
