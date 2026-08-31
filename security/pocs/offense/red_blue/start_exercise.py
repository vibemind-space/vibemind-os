"""
Red vs Blue — Exercise Launcher
====================================
Startet alles in der richtigen Reihenfolge:
  1. VM hochfahren (GUI)
  2. Warten bis SSH + Services bereit
  3. Shared Folder Guard aufsetzen
  4. Shared Folder Monitor starten (Background)
  5. VM Dashboard starten (Background)
  6. Infra-Check
  7. Bereit fuer main.py

Usage:
  python start_exercise.py              # Standard (7 Runden)
  python start_exercise.py --rounds 3   # 3 Runden
  python start_exercise.py --no-attack  # Nur Setup, kein Angriff starten
"""

import argparse
import logging
import os
import subprocess
import sys
import time

# Suppress paramiko SSH banner noise during boot wait
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
logging.getLogger("paramiko.transport").setLevel(logging.CRITICAL)

VBOX = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
VM_NAME = "MultiseatOS"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd, desc, timeout=30):
    print(f"  {desc}...", end="", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode == 0:
        print(" OK")
    else:
        print(f" WARN ({result.stderr.strip()[:60]})")
    return result


def vm_state():
    r = subprocess.run([VBOX, "showvminfo", VM_NAME, "--machinereadable"],
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        if line.startswith("VMState="):
            return line.split("=")[1].strip('"')
    return "unknown"


def wait_ssh(max_wait=120):
    """Wait for SSH to be ready."""
    import paramiko
    import logging
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)
    print(f"  Warte auf SSH (max {max_wait}s)", end="", flush=True)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect("127.0.0.1", port=2222, username="vibemind",
                        password="logitech66", timeout=5, banner_timeout=10)
            ssh.close()
            elapsed = int(time.time() - start)
            print(f" OK ({elapsed}s)")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(5)
    print(" TIMEOUT")
    return False


def wait_services(max_wait=90):
    """Wait for vault + monitor API."""
    import urllib.request
    print(f"  Warte auf Services (max {max_wait}s)", end="", flush=True)
    start = time.time()
    vault_ok = False
    api_ok = False
    while time.time() - start < max_wait:
        try:
            if not vault_ok:
                r = urllib.request.urlopen("http://127.0.0.1:18000/api/health", timeout=3)
                if r.status == 200:
                    vault_ok = True
                    print(f" vault", end="", flush=True)
        except Exception:
            pass
        try:
            if not api_ok:
                r = urllib.request.urlopen("http://127.0.0.1:19090/api/health", timeout=3)
                if r.status == 200:
                    api_ok = True
                    print(f" monitor", end="", flush=True)
        except Exception:
            pass
        if vault_ok and api_ok:
            elapsed = int(time.time() - start)
            print(f" OK ({elapsed}s)")
            return True
        print(".", end="", flush=True)
        time.sleep(3)
    print(f"\n  PARTIAL (vault={'OK' if vault_ok else 'FAIL'}, api={'OK' if api_ok else 'FAIL'})")
    return vault_ok or api_ok


def main():
    parser = argparse.ArgumentParser(description="Red vs Blue Exercise Launcher")
    parser.add_argument("--rounds", type=int, default=7, help="Anzahl Runden (default: 7)")
    parser.add_argument("--no-attack", action="store_true", help="Nur Setup, kein Angriff")
    args = parser.parse_args()

    print()
    print("=" * 62)
    print("  RED vs BLUE — Exercise Setup")
    print("=" * 62)
    print()

    # ---- Step 1: VM starten ----
    print("[1/6] VM Check...")
    state = vm_state()
    if state == "running":
        print(f"  VM laeuft bereits (GUI)")
        # Re-apply port forwarding (may be lost after kill, use non-Docker ports)
        forwarding = [
            ("vault", "18000", "8000"),   # Host 18000 -> VM 8000 (Docker uses 8000)
            ("api", "19090", "9090"),      # Host 19090 -> VM 9090 (Docker uses 9090)
            ("ws", "9091", "9091"),
        ]
        for name, host_port, vm_port in forwarding:
            subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", "delete", name],
                           capture_output=True, timeout=5)
            subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", f"{name},tcp,,{host_port},,{vm_port}"],
                           capture_output=True, timeout=5)
        print(f"  Port-Forwarding aktualisiert (18000->8000, 19090->9090, 9091)")
    elif state in ("poweroff", "aborted", "saved"):
        print(f"  VM ist {state}. Starte mit GUI...")
        run([VBOX, "startvm", VM_NAME], "VM starten", timeout=30)
        print(f"  Warte 30s auf VM Boot...", end="", flush=True)
        time.sleep(30)
        print(" OK")
    else:
        print(f"  VM Status: {state}. Versuche Start...")
        run([VBOX, "startvm", VM_NAME], "VM starten", timeout=30)
        print(f"  Warte 30s auf VM Boot...", end="", flush=True)
        time.sleep(30)
        print(" OK")
    print()

    # ---- Step 2: Warten auf SSH ----
    print("[2/6] SSH Verbindung...")
    if not wait_ssh(max_wait=90):
        print("\n  FEHLER: SSH nicht erreichbar. VM evtl. nicht gestartet?")
        print("  Pruefe VirtualBox GUI Fenster.")
        sys.exit(1)
    print()

    # ---- Step 3: Services starten + warten ----
    print("[3/6] VM Services starten...")
    import paramiko as _pm
    try:
        _ssh = _pm.SSHClient()
        _ssh.set_missing_host_key_policy(_pm.AutoAddPolicy())
        _ssh.connect("127.0.0.1", port=2222, username="vibemind",
                     password="logitech66", timeout=10, banner_timeout=15)
        _ssh.exec_command("echo 'logitech66' | sudo -S systemctl restart secret-vault system-monitor", timeout=15)
        time.sleep(3)
        _, out, _ = _ssh.exec_command("systemctl is-active secret-vault system-monitor", timeout=5)
        statuses = out.read().decode().strip()
        print(f"  Services restarted: {statuses.replace(chr(10), ', ')}")
        _ssh.close()
    except Exception as e:
        print(f"  Service restart via SSH failed: {e}")

    print("  Warte auf Port-Forwarding...")
    wait_services(max_wait=90)
    print()

    # ---- Step 3b: IDS Deployment ----
    from config import VM_IDS_ENABLED
    if VM_IDS_ENABLED:
        print("[3b/6] IDS Deployment...")
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", "delete", "ids"],
                       capture_output=True, timeout=5)
        subprocess.run([VBOX, "controlvm", VM_NAME, "natpf1", "ids,tcp,,19091,,19091"],
                       capture_output=True, timeout=5)
        print("  Port-Forwarding: 19091->19091 (stealth IDS)")
        subprocess.run(
            [sys.executable, "-m", "vm_ids.deploy_ids"],
            cwd=SCRIPT_DIR,
        )
        print()

    # ---- Step 4: Shared Folder Guard ----
    print("[4/6] Shared Folder Guard...")
    subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "shared_folder_guard.py"), "setup"],
        cwd=SCRIPT_DIR,
    )
    # Clear old alerts
    alert_file = os.path.join(
        r"C:\Users\User\Stephane\multiseat-os", ".guard", ".alerts.json"
    )
    if os.path.exists(alert_file):
        os.remove(alert_file)
        print("  Alert-Log gecleared.")
    print()

    # ---- Step 5: Background Prozesse starten ----
    print("[5/6] Background Monitors starten...")

    # Shared Folder Monitor
    guard_proc = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPT_DIR, "shared_folder_guard.py"), "monitor"],
        cwd=SCRIPT_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print(f"  Shared Folder Guard: PID {guard_proc.pid} (neues Fenster)")

    # VM Dashboard
    dash_proc = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPT_DIR, "vm_dashboard.py")],
        cwd=SCRIPT_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print(f"  VM Dashboard: PID {dash_proc.pid} (neues Fenster)")
    print()

    # ---- Step 6: Infra Check ----
    print("[6/6] Infrastruktur-Check...")
    subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "verify_infra.py")],
        cwd=SCRIPT_DIR,
    )
    print()

    # ---- Ready ----
    print("=" * 62)
    print("  SETUP COMPLETE")
    print("=" * 62)
    print()
    print("  Fenster:")
    print("    [1] VirtualBox GUI     — VM Desktop sichtbar")
    print("    [2] Shared Folder Guard — Tripwire + Kill-Switch")
    print("    [3] VM Dashboard        — Live System-Status")
    print()

    if args.no_attack:
        print("  --no-attack: Setup fertig. Starte manuell:")
        print(f"    cd poc_red_blue && python main.py --rounds {args.rounds}")
        print()
        return

    print(f"  Starte Adversarial Exercise ({args.rounds} Runden)...")
    print(f"  Druecke ENTER zum Starten oder Ctrl+C zum Abbrechen.")
    print()

    try:
        input("  >>> ENTER zum Starten ")
    except KeyboardInterrupt:
        print("\n  Abgebrochen.")
        return

    print()
    print("=" * 62)
    print(f"  EXERCISE START — {args.rounds} Runden")
    print("=" * 62)
    print()

    # Start main.py in this terminal
    exit_code = subprocess.call(
        [sys.executable, os.path.join(SCRIPT_DIR, "main.py"), "--rounds", str(args.rounds)],
        cwd=SCRIPT_DIR,
    )

    print()
    print("=" * 62)
    print("  EXERCISE BEENDET — Issue Agent startet...")
    print("=" * 62)
    print()

    # Auto-run Issue Agent to create GitHub Issues from reports
    print("  [ISSUE AGENT] Analysiere Reports und erstelle GitHub Issues...")
    subprocess.call(
        [sys.executable, os.path.join(SCRIPT_DIR, "issue_agent.py")],
        cwd=SCRIPT_DIR,
    )

    print()
    print("  Reports in: poc_red_blue/reports/")
    print("  Issues in:  https://github.com/Flissel/vibemind-os/issues")
    print("  Guard + Dashboard laufen noch (Fenster schliessen zum Beenden)")
    print()


if __name__ == "__main__":
    main()
