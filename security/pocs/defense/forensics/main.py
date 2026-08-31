"""
Forensics Timeline - System Activity Reconstruction
======================================================
Parses Prefetch, Browser History, Recycle Bin, PowerShell History,
USB History, and Recent Files to reconstruct what happened on the system.

Nutzung:
  python main.py --scan
  python main.py --scan --hours 72
  python main.py --browser-history
  python main.py --powershell-history
  python main.py --usb-history
"""

import asyncio
import json
import os
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


async def parse_prefetch() -> dict:
    """Parse Windows Prefetch files to see what was executed recently."""
    result = {"entries": [], "total": 0, "warning": None}

    prefetch_dir = Path(r"C:\Windows\Prefetch")

    def _scan():
        if not prefetch_dir.exists():
            result["warning"] = "Prefetch directory not found (may need admin)"
            return

        for pf_file in sorted(prefetch_dir.glob("*.pf"), key=lambda f: f.stat().st_mtime, reverse=True)[:50]:
            try:
                stat = pf_file.stat()
                # Extract program name from filename (NAME-HASH.pf)
                name = pf_file.stem.rsplit("-", 1)[0] if "-" in pf_file.stem else pf_file.stem

                result["entries"].append({
                    "program": name,
                    "file": pf_file.name,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size_kb": round(stat.st_size / 1024, 1),
                })
            except (PermissionError, OSError):
                continue

        result["total"] = len(result["entries"])

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    return result


async def parse_browser_history() -> dict:
    """Parse Chrome and Edge browser history (SQLite databases)."""
    result = {"browsers": {}, "total_entries": 0, "warning": None}

    user_dir = Path(os.environ.get("LOCALAPPDATA", ""))

    BROWSER_PATHS = {
        "Chrome": user_dir / "Google" / "Chrome" / "User Data" / "Default" / "History",
        "Edge": user_dir / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
    }

    def _scan_browser(name, db_path):
        entries = []
        if not db_path.exists():
            return entries

        # Copy DB to temp (browser locks it)
        tmp = Path(tempfile.mktemp(suffix=".db"))
        try:
            shutil.copy2(db_path, tmp)
            conn = sqlite3.connect(str(tmp))
            cursor = conn.execute(
                "SELECT url, title, visit_count, last_visit_time FROM urls "
                "ORDER BY last_visit_time DESC LIMIT 50"
            )
            for row in cursor:
                url, title, visit_count, chrome_time = row
                # Chrome timestamps: microseconds since 1601-01-01
                if chrome_time:
                    try:
                        epoch = (chrome_time / 1000000) - 11644473600
                        visit_time = datetime.fromtimestamp(max(0, epoch)).isoformat()
                    except (ValueError, OSError):
                        visit_time = "?"
                else:
                    visit_time = "?"

                entries.append({
                    "url": (url or "")[:200],
                    "title": (title or "")[:100],
                    "visit_count": visit_count,
                    "last_visit": visit_time,
                })
            conn.close()
        except Exception as e:
            result["warning"] = f"{name}: {e}"
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass

        return entries

    for browser_name, db_path in BROWSER_PATHS.items():
        entries = await asyncio.get_event_loop().run_in_executor(
            None, _scan_browser, browser_name, db_path
        )
        if entries:
            result["browsers"][browser_name] = entries
            result["total_entries"] += len(entries)

    return result


async def parse_powershell_history() -> dict:
    """Parse PowerShell command history."""
    result = {"commands": [], "total": 0, "warning": None}

    history_path = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt"

    def _scan():
        if not history_path.exists():
            result["warning"] = "PowerShell history not found"
            return

        try:
            with open(history_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Last 100 commands
            for line in lines[-100:]:
                cmd = line.strip()
                if cmd:
                    result["commands"].append(cmd)

            result["total"] = len(result["commands"])
        except Exception as e:
            result["warning"] = str(e)

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    return result


async def parse_recycle_bin() -> dict:
    """List recently deleted files from Recycle Bin."""
    result = {"deleted_files": [], "total": 0, "warning": None}

    def _scan():
        recycle_paths = list(Path("C:\\").glob("$Recycle.Bin\\*"))
        for user_bin in recycle_paths:
            try:
                for item in sorted(user_bin.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:30]:
                    try:
                        stat = item.stat()
                        result["deleted_files"].append({
                            "file": item.name,
                            "size_kb": round(stat.st_size / 1024, 1),
                            "deleted_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue

        result["total"] = len(result["deleted_files"])

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    return result


async def parse_usb_history() -> dict:
    """List USB devices that were ever connected (from Registry)."""
    import winreg

    result = {"devices": [], "total": 0, "warning": None}

    def _scan():
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\USBSTOR")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    j = 0
                    while True:
                        try:
                            serial = winreg.EnumKey(subkey, j)
                            result["devices"].append({
                                "device": subkey_name,
                                "serial": serial,
                            })
                            j += 1
                        except OSError:
                            break
                    winreg.CloseKey(subkey)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (FileNotFoundError, PermissionError) as e:
            result["warning"] = str(e)

        result["total"] = len(result["devices"])

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    return result


async def parse_recent_files() -> dict:
    """List recently opened files (from Recent folder)."""
    result = {"files": [], "total": 0}

    recent_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Recent"

    def _scan():
        if not recent_dir.exists():
            return
        for item in sorted(recent_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:50]:
            try:
                stat = item.stat()
                result["files"].append({
                    "name": item.name.replace(".lnk", ""),
                    "accessed": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except (PermissionError, OSError):
                continue
        result["total"] = len(result["files"])

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Forensics Timeline")
    parser.add_argument("--scan", action="store_true", help="Full forensics scan")
    parser.add_argument("--browser-history", action="store_true")
    parser.add_argument("--powershell-history", action="store_true")
    parser.add_argument("--usb-history", action="store_true")
    parser.add_argument("--prefetch", action="store_true")
    args = parser.parse_args()

    if not any([args.scan, args.browser_history, args.powershell_history, args.usb_history, args.prefetch]):
        parser.print_help()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  FORENSICS TIMELINE")
    print("  System Activity Reconstruction")
    print("=" * 60 + "\n")

    if args.scan:
        print("  [1/6] Prefetch (recently executed programs)...", flush=True)
        pf = await parse_prefetch()
        print(f"         {pf['total']} programs found")
        for e in pf["entries"][:10]:
            print(f"           {e['last_modified'][:16]}  {e['program']}")

        print("\n  [2/6] Browser History...", flush=True)
        bh = await parse_browser_history()
        print(f"         {bh['total_entries']} entries")
        for browser, entries in bh["browsers"].items():
            print(f"         {browser}: {len(entries)} entries")
            for e in entries[:5]:
                print(f"           {e['last_visit'][:16]}  {e['title'][:50]}  {e['url'][:60]}")

        print("\n  [3/6] PowerShell History...", flush=True)
        ps = await parse_powershell_history()
        print(f"         {ps['total']} commands")
        for cmd in ps["commands"][-10:]:
            print(f"           > {cmd[:80]}")

        print("\n  [4/6] Recycle Bin...", flush=True)
        rb = await parse_recycle_bin()
        print(f"         {rb['total']} deleted files")
        for f in rb["deleted_files"][:10]:
            print(f"           {f['deleted_at'][:16]}  {f['file'][:50]}  ({f['size_kb']}KB)")

        print("\n  [5/6] USB Device History...", flush=True)
        usb = await parse_usb_history()
        print(f"         {usb['total']} devices ever connected")
        for d in usb["devices"][:10]:
            print(f"           {d['device'][:60]}  SN: {d['serial'][:20]}")

        print("\n  [6/6] Recent Files...", flush=True)
        rf = await parse_recent_files()
        print(f"         {rf['total']} recent files")
        for f in rf["files"][:10]:
            print(f"           {f['accessed'][:16]}  {f['name'][:60]}")

    elif args.browser_history:
        bh = await parse_browser_history()
        for browser, entries in bh["browsers"].items():
            print(f"  {browser} ({len(entries)} entries):")
            for e in entries:
                print(f"    {e['last_visit'][:16]}  {e['title'][:40]}  {e['url'][:80]}")

    elif args.powershell_history:
        ps = await parse_powershell_history()
        for cmd in ps["commands"]:
            print(f"  > {cmd}")

    elif args.usb_history:
        usb = await parse_usb_history()
        for d in usb["devices"]:
            print(f"  {d['device']}  SN: {d['serial']}")

    elif args.prefetch:
        pf = await parse_prefetch()
        for e in pf["entries"]:
            print(f"  {e['last_modified'][:16]}  {e['program']:<40}  {e['size_kb']}KB")

    print()


if __name__ == "__main__":
    asyncio.run(main())
