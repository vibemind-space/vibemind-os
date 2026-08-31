"""
Canary / Honeypot System
==========================
Deploys fake files (passwords.xlsx, backup.sql, etc.) in strategic locations.
Watches for any access and triggers immediate alerts.

Nutzung:
  python canary.py --deploy              # Place canary files
  python canary.py --watch               # Watch for access (runs forever)
  python canary.py --deploy --watch      # Deploy + Watch
  python canary.py --cleanup             # Remove all canary files
  python canary.py --status              # Show deployed canaries
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ================================================================
# CANARY DEFINITIONS
# ================================================================

CANARY_MARKER = "<!-- CANARY:OS_SHIELD -->"  # Hidden marker in files

CANARY_FILES = [
    {
        "name": "passwords.xlsx",
        "location": "Desktop",
        "content_type": "binary",
        "description": "Fake password spreadsheet",
    },
    {
        "name": "backup.sql",
        "location": "Documents",
        "content_type": "text",
        "content": f"-- Database Backup {datetime.now().strftime('%Y-%m-%d')}\n-- Server: db-prod-01.internal\n-- {CANARY_MARKER}\n\nCREATE TABLE users (\n  id INT PRIMARY KEY,\n  username VARCHAR(50),\n  password_hash VARCHAR(255),\n  email VARCHAR(100)\n);\n\nINSERT INTO users VALUES (1, 'admin', '$2b$12$FAKE_HASH_DO_NOT_USE', 'admin@company.internal');\nINSERT INTO users VALUES (2, 'root', '$2b$12$ANOTHER_FAKE_HASH', 'root@company.internal');\n",
    },
    {
        "name": "credentials.txt",
        "location": "Documents",
        "content_type": "text",
        "content": f"# Internal Credentials\n# {CANARY_MARKER}\n# DO NOT SHARE\n\nSSH root@192.168.1.10\n  user: admin\n  pass: CANARY_P@ssw0rd_2024\n\nDatabase (prod)\n  host: db-prod.internal:5432\n  user: dbadmin\n  pass: CANARY_Db_S3cret!\n\nAWS Console\n  user: ops@company.com\n  key: AKIAIOSFODNN7CANARY\n  secret: wJalrXUtnFEMI/K7MDENG/CANARY_KEY\n",
    },
    {
        "name": ".env.backup",
        "location": "home",
        "content_type": "text",
        "content": f"# Production Environment Backup\n# {CANARY_MARKER}\nDATABASE_URL=postgres://admin:CANARY_pass@db-prod:5432/main\nREDIS_URL=redis://CANARY:6379\nSECRET_KEY=canary-secret-key-do-not-use-12345\nAWS_ACCESS_KEY_ID=AKIAIOSFODNN7CANARY\nAWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/CANARY/bPxRfiCY\nSTRIPE_SECRET_KEY=sk_live_CANARY_4eC39HqLyjWDarjtT1zdp7dc\n",
    },
    {
        "name": "api_keys.json",
        "location": "Documents",
        "content_type": "text",
        "content": json.dumps({
            "_canary": CANARY_MARKER,
            "openai": "sk-CANARY-do-not-use-this-key-1234567890",
            "stripe": "sk_live_CANARY_fake_key",
            "sendgrid": "SG.CANARY_FAKE_KEY.not_real",
            "slack_webhook": "https://hooks.slack.com/services/CANARY/FAKE/WEBHOOK",
        }, indent=2),
    },
]

DEPLOY_STATE_FILE = Path(__file__).parent / "deployed_canaries.json"


# ================================================================
# DEPLOY
# ================================================================

def get_canary_path(canary: dict) -> Path:
    """Get the full path for a canary file."""
    user_home = Path.home()
    locations = {
        "Desktop": user_home / "Desktop",
        "Documents": user_home / "Documents",
        "Downloads": user_home / "Downloads",
        "home": user_home,
    }
    base = locations.get(canary["location"], user_home / "Documents")
    return base / canary["name"]


def deploy_canaries() -> list:
    """Deploy all canary files and record their state."""
    deployed = []

    for canary in CANARY_FILES:
        path = get_canary_path(canary)

        if path.exists():
            print(f"  [SKIP] {path} already exists")
            continue

        try:
            if canary.get("content_type") == "binary":
                # Create a minimal xlsx-like file (ZIP with marker)
                import zipfile
                import io
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w') as zf:
                    zf.writestr("canary.txt", CANARY_MARKER)
                    zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
                path.write_bytes(buf.getvalue())
            else:
                path.write_text(canary.get("content", CANARY_MARKER), encoding="utf-8")

            # Record hash and timestamp
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()

            deployed.append({
                "name": canary["name"],
                "path": str(path),
                "description": canary.get("description", ""),
                "deployed_at": datetime.now().isoformat(),
                "hash": file_hash,
                "location": canary["location"],
            })
            print(f"  [DEPLOYED] {path}")

        except Exception as e:
            print(f"  [ERROR] {path}: {e}")

    # Save state
    existing = []
    if DEPLOY_STATE_FILE.exists():
        existing = json.loads(DEPLOY_STATE_FILE.read_text())

    existing.extend(deployed)
    DEPLOY_STATE_FILE.write_text(json.dumps(existing, indent=2))

    return deployed


# ================================================================
# WATCH
# ================================================================

async def watch_canaries():
    """Watch deployed canary files for access."""
    if not DEPLOY_STATE_FILE.exists():
        print("  [ERROR] No canaries deployed. Run --deploy first.")
        return

    canaries = json.loads(DEPLOY_STATE_FILE.read_text())

    if not canaries:
        print("  [ERROR] No canaries in state file.")
        return

    print(f"  [WATCH] Monitoring {len(canaries)} canary file(s)...")
    print(f"  [WATCH] Press Ctrl+C to stop.\n")

    # Record initial state
    initial_state = {}
    for canary in canaries:
        path = Path(canary["path"])
        if path.exists():
            stat = path.stat()
            initial_state[canary["path"]] = {
                "mtime": stat.st_mtime,
                "atime": stat.st_atime,
                "size": stat.st_size,
            }
            print(f"  [OK] {canary['name']} ({canary['location']})")

    print()

    # Monitor loop
    try:
        while True:
            for canary in canaries:
                path = Path(canary["path"])

                if not path.exists():
                    # File was deleted!
                    print(f"\n  [ALERT] CANARY DELETED: {canary['name']}")
                    print(f"          Path: {canary['path']}")
                    print(f"          Time: {datetime.now().isoformat()}")
                    print(f"          This indicates an attacker or insider is active!\n")

                    # Try to send alert
                    try:
                        sys.path.insert(0, str(Path(__file__).parent.parent / "alerter"))
                        from alerter import send_alert
                        await send_alert(
                            "CRITICAL",
                            f"Canary file DELETED: {canary['name']}",
                            f"Path: {canary['path']}\nLocation: {canary['location']}\nTime: {datetime.now().isoformat()}",
                            source="Canary System",
                        )
                    except ImportError:
                        pass

                    continue

                stat = path.stat()
                prev = initial_state.get(canary["path"], {})

                # Check if accessed
                if stat.st_atime > prev.get("atime", 0):
                    print(f"\n  [ALERT] CANARY ACCESSED: {canary['name']}")
                    print(f"          Path: {canary['path']}")
                    print(f"          Access Time: {datetime.fromtimestamp(stat.st_atime).isoformat()}")
                    print(f"          Someone opened/read this file!\n")

                    # Update state
                    initial_state[canary["path"]]["atime"] = stat.st_atime

                    try:
                        sys.path.insert(0, str(Path(__file__).parent.parent / "alerter"))
                        from alerter import send_alert
                        await send_alert(
                            "HIGH",
                            f"Canary file ACCESSED: {canary['name']}",
                            f"Path: {canary['path']}\nAccess: {datetime.fromtimestamp(stat.st_atime).isoformat()}",
                            source="Canary System",
                        )
                    except ImportError:
                        pass

                # Check if modified
                if stat.st_mtime > prev.get("mtime", 0) and prev.get("mtime", 0) > 0:
                    print(f"\n  [ALERT] CANARY MODIFIED: {canary['name']}")
                    print(f"          Path: {canary['path']}")
                    print(f"          Modified: {datetime.fromtimestamp(stat.st_mtime).isoformat()}")
                    print(f"          File was changed — possible data exfiltration prep!\n")

                    initial_state[canary["path"]]["mtime"] = stat.st_mtime

                    try:
                        sys.path.insert(0, str(Path(__file__).parent.parent / "alerter"))
                        from alerter import send_alert
                        await send_alert(
                            "CRITICAL",
                            f"Canary file MODIFIED: {canary['name']}",
                            f"Path: {canary['path']}\nModified: {datetime.fromtimestamp(stat.st_mtime).isoformat()}",
                            source="Canary System",
                        )
                    except ImportError:
                        pass

            await asyncio.sleep(5)  # Check every 5 seconds

    except KeyboardInterrupt:
        print("\n  [WATCH] Stopped.")


# ================================================================
# CLEANUP
# ================================================================

def cleanup_canaries():
    """Remove all deployed canary files."""
    if not DEPLOY_STATE_FILE.exists():
        print("  No canaries deployed.")
        return

    canaries = json.loads(DEPLOY_STATE_FILE.read_text())

    for canary in canaries:
        path = Path(canary["path"])
        if path.exists():
            path.unlink()
            print(f"  [REMOVED] {path}")
        else:
            print(f"  [GONE] {path} (already deleted)")

    DEPLOY_STATE_FILE.unlink()
    print(f"\n  All canaries cleaned up.")


# ================================================================
# STATUS
# ================================================================

def show_status():
    """Show deployed canary status."""
    if not DEPLOY_STATE_FILE.exists():
        print("  No canaries deployed.")
        return

    canaries = json.loads(DEPLOY_STATE_FILE.read_text())
    print(f"  {len(canaries)} canary file(s) deployed:\n")

    for canary in canaries:
        path = Path(canary["path"])
        exists = path.exists()
        status = "OK" if exists else "DELETED!"

        accessed = ""
        if exists:
            stat = path.stat()
            accessed = datetime.fromtimestamp(stat.st_atime).strftime("%d.%m.%Y %H:%M")

        print(f"  [{status:>7}] {canary['name']}")
        print(f"           Path: {canary['path']}")
        print(f"           Deployed: {canary['deployed_at'][:16]}")
        if accessed:
            print(f"           Last Access: {accessed}")
        print()


# ================================================================
# MAIN
# ================================================================

async def main():
    parser = argparse.ArgumentParser(description="Canary / Honeypot System")
    parser.add_argument("--deploy", action="store_true", help="Deploy canary files")
    parser.add_argument("--watch", action="store_true", help="Watch for canary access")
    parser.add_argument("--cleanup", action="store_true", help="Remove all canaries")
    parser.add_argument("--status", action="store_true", help="Show canary status")
    args = parser.parse_args()

    if not any([args.deploy, args.watch, args.cleanup, args.status]):
        parser.print_help()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  CANARY SYSTEM")
    print("  Honeypot / Deception Defense")
    print("=" * 60 + "\n")

    if args.cleanup:
        cleanup_canaries()
        return

    if args.status:
        show_status()
        return

    if args.deploy:
        print("  Deploying canary files...\n")
        deployed = deploy_canaries()
        print(f"\n  {len(deployed)} new canary file(s) deployed.")
        print()

    if args.watch:
        await watch_canaries()


if __name__ == "__main__":
    asyncio.run(main())
