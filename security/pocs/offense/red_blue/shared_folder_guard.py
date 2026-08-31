"""
Shared Folder Guard — Honeypot + Tripwire + Cryptographic Protection
=========================================================================
Schuetzt den Shared Folder (C:\\Users\\User\\Stephane\\multiseat-os)
der zwischen Host und VM geteilt wird.

3 Schichten:
1. TRIPWIRE: Erstellt Canary-Dateien mit HMAC. Jede Aenderung wird erkannt.
2. HONEYPOT: Platziert verlockende Fake-Dateien (passwords.txt etc.)
   Zugriff = Alarm.
3. MONITOR: Ueberwacht den Ordner auf neue/geaenderte/geloeschte Dateien.

Nutzung:
  python shared_folder_guard.py setup     # Tripwire + Honeypot installieren
  python shared_folder_guard.py check     # Integritaet pruefen
  python shared_folder_guard.py monitor   # Live-Ueberwachung starten
  python shared_folder_guard.py cleanup   # Guard-Dateien entfernen
"""

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path


SHARED_FOLDER = r"C:\Users\User\Stephane\multiseat-os"
SKIP_DIRS = {".guard", "downloads", "node_modules", ".git"}
GUARD_DIR = os.path.join(SHARED_FOLDER, ".guard")
GUARD_KEY_FILE = os.path.join(GUARD_DIR, ".hmac_key")
TRIPWIRE_DB = os.path.join(GUARD_DIR, ".tripwire.json")
ALERT_LOG = os.path.join(GUARD_DIR, ".alerts.json")


def _get_or_create_key() -> bytes:
    """Get or create HMAC key for tripwire signatures."""
    os.makedirs(GUARD_DIR, exist_ok=True)
    if os.path.exists(GUARD_KEY_FILE):
        with open(GUARD_KEY_FILE, "rb") as f:
            return f.read()
    key = secrets.token_bytes(32)
    with open(GUARD_KEY_FILE, "wb") as f:
        f.write(key)
    # Hide the guard directory on Windows
    try:
        import subprocess
        subprocess.run(["attrib", "+H", GUARD_DIR], capture_output=True)
    except Exception:
        pass
    return key


def _hmac_file(filepath: str, key: bytes) -> str:
    """Compute HMAC-SHA256 of a file."""
    h = hmac.new(key, digestmod=hashlib.sha256)
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, FileNotFoundError):
        return "UNREADABLE"


def _hmac_string(data: str, key: bytes) -> str:
    """Compute HMAC-SHA256 of a string."""
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()


def setup_tripwire():
    """Scan all files and create integrity database with HMAC signatures."""
    print("[GUARD] Setting up tripwire...")
    key = _get_or_create_key()

    entries = {}
    for root, dirs, files in os.walk(SHARED_FOLDER):
        # Skip large/irrelevant directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(s in root for s in SKIP_DIRS):
            continue
        for fname in files:
            filepath = os.path.join(root, fname)
            rel = os.path.relpath(filepath, SHARED_FOLDER)
            stat = os.stat(filepath)
            entries[rel] = {
                "hmac": _hmac_file(filepath, key),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "recorded_at": datetime.now().isoformat(),
            }

    with open(TRIPWIRE_DB, "w") as f:
        json.dump(entries, f, indent=2)

    print(f"  Tripwire: {len(entries)} files recorded")
    return entries


def setup_honeypot():
    """Place enticing fake files that trigger alerts when accessed."""
    print("[GUARD] Setting up honeypot files...")
    key = _get_or_create_key()

    honeypots = {
        "credentials.txt": (
            "# Internal Credentials\n"
            "admin_password=SuperSecret123!\n"
            "db_root=mysql_r00t_pw\n"
            "api_key=sk-FAKE-HONEYPOT-KEY-DO-NOT-USE\n"
            "aws_secret=AKIAIFAKEHONEYPOTKEY\n"
        ),
        ".env.backup": (
            "OPENAI_API_KEY=sk-FAKE-honeypot-not-real\n"
            "DATABASE_URL=postgresql://admin:FAKE@localhost/prod\n"
            "JWT_SECRET=FAKE_honeypot_jwt_secret\n"
        ),
        "id_rsa": (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "HONEYPOT-THIS-IS-NOT-A-REAL-KEY\n"
            "IF-YOU-SEE-THIS-THE-ATTACKER-ACCESSED-THE-FILE\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        ),
        "backup_passwords.csv": (
            "service,username,password\n"
            "vault,admin,FAKE_honeypot_password\n"
            "ssh,root,FAKE_not_real_password\n"
            "database,dba,FAKE_honeypot_db_pw\n"
        ),
    }

    created = []
    for filename, content in honeypots.items():
        filepath = os.path.join(SHARED_FOLDER, filename)
        with open(filepath, "w") as f:
            f.write(content)
        # Record HMAC for integrity check
        file_hmac = _hmac_file(filepath, key)
        created.append({"file": filename, "hmac": file_hmac})
        print(f"  Honeypot: {filename}")

    # Save honeypot registry
    honeypot_db = os.path.join(GUARD_DIR, ".honeypots.json")
    with open(honeypot_db, "w") as f:
        json.dump(created, f, indent=2)

    print(f"  {len(created)} honeypot files placed")
    return created


def check_integrity() -> dict:
    """Check all files against tripwire database. Returns alert report."""
    print("[GUARD] Checking integrity...")
    key = _get_or_create_key()

    if not os.path.exists(TRIPWIRE_DB):
        print("  ERROR: No tripwire database. Run 'setup' first.")
        return {"error": "no tripwire database"}

    with open(TRIPWIRE_DB) as f:
        baseline = json.load(f)

    alerts = []
    checked = 0

    # Check existing files
    for rel_path, record in baseline.items():
        filepath = os.path.join(SHARED_FOLDER, rel_path)
        if not os.path.exists(filepath):
            alerts.append({
                "type": "DELETED",
                "severity": "HIGH",
                "file": rel_path,
                "time": datetime.now().isoformat(),
            })
            continue

        current_hmac = _hmac_file(filepath, key)
        if current_hmac != record["hmac"]:
            alerts.append({
                "type": "MODIFIED",
                "severity": "CRITICAL",
                "file": rel_path,
                "expected_hmac": record["hmac"][:16] + "...",
                "actual_hmac": current_hmac[:16] + "...",
                "time": datetime.now().isoformat(),
            })
        checked += 1

    # Check for new files
    for root, dirs, files in os.walk(SHARED_FOLDER):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(s in root for s in SKIP_DIRS):
            continue
        for fname in files:
            filepath = os.path.join(root, fname)
            rel = os.path.relpath(filepath, SHARED_FOLDER)
            if rel not in baseline:
                alerts.append({
                    "type": "NEW_FILE",
                    "severity": "HIGH",
                    "file": rel,
                    "size": os.path.getsize(filepath),
                    "time": datetime.now().isoformat(),
                })

    # Check honeypots
    honeypot_db = os.path.join(GUARD_DIR, ".honeypots.json")
    if os.path.exists(honeypot_db):
        with open(honeypot_db) as f:
            honeypots = json.load(f)
        for hp in honeypots:
            filepath = os.path.join(SHARED_FOLDER, hp["file"])
            if not os.path.exists(filepath):
                alerts.append({
                    "type": "HONEYPOT_DELETED",
                    "severity": "CRITICAL",
                    "file": hp["file"],
                    "time": datetime.now().isoformat(),
                    "message": "Attacker deleted honeypot file!",
                })
            else:
                current_hmac = _hmac_file(filepath, key)
                if current_hmac != hp["hmac"]:
                    alerts.append({
                        "type": "HONEYPOT_MODIFIED",
                        "severity": "CRITICAL",
                        "file": hp["file"],
                        "time": datetime.now().isoformat(),
                        "message": "Attacker modified honeypot file!",
                    })
                # Check access time
                stat = os.stat(filepath)
                if stat.st_atime > stat.st_mtime + 1:
                    alerts.append({
                        "type": "HONEYPOT_ACCESSED",
                        "severity": "HIGH",
                        "file": hp["file"],
                        "access_time": datetime.fromtimestamp(stat.st_atime).isoformat(),
                        "message": "Honeypot file was read!",
                    })

    # Save alerts
    if alerts:
        with open(ALERT_LOG, "w") as f:
            json.dump(alerts, f, indent=2)

    # Print results
    if alerts:
        print(f"\n  {'!'*50}")
        print(f"  ALERT: {len(alerts)} integrity violations detected!")
        print(f"  {'!'*50}")
        for a in alerts:
            sev = a["severity"]
            icon = "!!!" if sev == "CRITICAL" else "! " if sev == "HIGH" else ". "
            print(f"  [{icon}] {a['type']}: {a['file']}")
            if a.get("message"):
                print(f"        {a['message']}")
    else:
        print(f"  OK: {checked} files checked, no violations.")

    return {"checked": checked, "alerts": alerts, "alert_count": len(alerts)}


def monitor_loop(interval: int = 5, auto_kill: bool = True):
    """Continuously monitor shared folder. Auto-kills VM on CRITICAL breach.

    Args:
        interval: Seconds between checks
        auto_kill: If True, poweroff VM on CRITICAL breach
    """
    print(f"[GUARD] Live monitoring (every {interval}s). Ctrl+C to stop.")
    print(f"  Watching: {SHARED_FOLDER}")
    print(f"  Auto-Kill VM on breach: {'YES' if auto_kill else 'NO'}\n")

    cycle = 0
    while True:
        cycle += 1
        if auto_kill:
            result = check_and_respond()
        else:
            result = check_integrity()

        alerts = result.get("alerts", [])
        KILL_TYPES = {"MODIFIED", "HONEYPOT_MODIFIED", "HONEYPOT_DELETED", "DELETED"}
        kill_alerts = [a for a in alerts if a.get("type") in KILL_TYPES]

        if kill_alerts and auto_kill:
            print(f"\n  VM KILLED after {cycle} cycles. Monitor stopping.")
            break

        # Show non-noise alerts
        real_alerts = [a for a in alerts if a["type"] not in ("HONEYPOT_ACCESSED",)]
        if real_alerts:
            print(f"\n  === CYCLE {cycle}: {len(real_alerts)} ALERTS ===")
            for a in real_alerts:
                print(f"    {a['type']}: {a.get('file', '')}")
            print()
        else:
            print(f"  [cycle {cycle}] clean", end="\r")
        time.sleep(interval)


def cleanup():
    """Remove all guard files and honeypots."""
    print("[GUARD] Cleaning up...")
    import shutil

    # Remove honeypots
    honeypot_db = os.path.join(GUARD_DIR, ".honeypots.json")
    if os.path.exists(honeypot_db):
        with open(honeypot_db) as f:
            honeypots = json.load(f)
        for hp in honeypots:
            filepath = os.path.join(SHARED_FOLDER, hp["file"])
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"  Removed honeypot: {hp['file']}")

    # Remove guard directory
    if os.path.exists(GUARD_DIR):
        shutil.rmtree(GUARD_DIR)
        print("  Removed .guard directory")

    print("  Cleanup complete.")


def emergency_vm_kill():
    """EMERGENCY: Sofort die VM herunterfahren wenn Shared Folder kompromittiert."""
    import subprocess
    print("\n  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("  EMERGENCY: Shared Folder breach detected!")
    print("  Shutting down VM immediately...")
    print("  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

    vboxmanage = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

    # 1. Poweroff VM (instant, wie Stecker ziehen)
    result = subprocess.run(
        [vboxmanage, "controlvm", "MultiseatOS", "poweroff"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        print("  [KILL] VM powered off successfully.")
    else:
        print(f"  [KILL] Poweroff failed: {result.stderr.strip()}")
        # Fallback: ACPI shutdown
        subprocess.run(
            [vboxmanage, "controlvm", "MultiseatOS", "acpipowerbutton"],
            capture_output=True, timeout=10,
        )
        print("  [KILL] Sent ACPI shutdown signal.")

    # 2. Log the kill event
    kill_log = {
        "event": "EMERGENCY_VM_KILL",
        "time": datetime.now().isoformat(),
        "reason": "Shared folder integrity breach",
    }
    kill_log_path = os.path.join(GUARD_DIR, ".kill_log.json")
    with open(kill_log_path, "w") as f:
        json.dump(kill_log, f, indent=2)

    print(f"  [KILL] Event logged to {kill_log_path}")
    return True


def check_and_respond() -> dict:
    """Check integrity and auto-respond to breaches.

    Returns alert report. Kills VM only on REAL critical breaches:
    - MODIFIED (existing file changed)
    - HONEYPOT_MODIFIED (honeypot tampered)
    - HONEYPOT_DELETED (honeypot removed)

    Does NOT kill for:
    - HONEYPOT_ACCESSED (read-only access, Windows access-time noise)
    - NEW_FILE (suspicious but not destructive)
    """
    result = check_integrity()
    alerts = result.get("alerts", [])

    # Only kill-worthy alert types
    KILL_TYPES = {"MODIFIED", "HONEYPOT_MODIFIED", "HONEYPOT_DELETED", "DELETED"}
    kill_alerts = [a for a in alerts if a.get("type") in KILL_TYPES]

    if kill_alerts:
        print(f"\n  CRITICAL BREACH: {len(kill_alerts)} violations!")
        for a in kill_alerts:
            print(f"    -> {a['type']}: {a.get('file', '')}")
        emergency_vm_kill()

    return result


def get_alert_report() -> dict:
    """Get current alert state — used by Blue Team detection tools."""
    if os.path.exists(ALERT_LOG):
        with open(ALERT_LOG) as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python shared_folder_guard.py [setup|check|monitor|cleanup]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "setup":
        setup_tripwire()
        setup_honeypot()
        print("\n  Guard active. Run 'check' to verify or 'monitor' for live watch.")
    elif cmd == "check":
        check_integrity()
    elif cmd == "monitor":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        try:
            monitor_loop(interval, auto_kill=True)
        except KeyboardInterrupt:
            print("\n  Monitor stopped.")
    elif cmd == "kill":
        emergency_vm_kill()
    elif cmd == "cleanup":
        cleanup()
    else:
        print(f"Usage: python shared_folder_guard.py [setup|check|monitor|kill|cleanup]")
