"""
Vulnerability Scanner - CVE Lookup for Installed Software
============================================================
Inventarisiert installierte Software und prueft gegen NIST NVD API.

Nutzung:
  python main.py --scan
  python main.py --scan --output vuln_report.html
"""

import asyncio
import json
import os
import re
import sys
import winreg
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


async def inventory_installed_software() -> list:
    """Get all installed software from Windows Registry."""
    software = []
    seen = set()

    UNINSTALL_KEYS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def _scan():
        for hive, key_path in UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        except FileNotFoundError:
                            i += 1
                            continue

                        version = ""
                        publisher = ""
                        try:
                            version = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                        except FileNotFoundError:
                            pass
                        try:
                            publisher = winreg.QueryValueEx(subkey, "Publisher")[0]
                        except FileNotFoundError:
                            pass

                        dedup_key = f"{name}|{version}"
                        if dedup_key not in seen and name:
                            seen.add(dedup_key)
                            software.append({
                                "name": name,
                                "version": version,
                                "publisher": publisher,
                            })

                        winreg.CloseKey(subkey)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except FileNotFoundError:
                continue

    await asyncio.get_event_loop().run_in_executor(None, _scan)
    software.sort(key=lambda s: s["name"].lower())
    return software


async def check_windows_updates() -> dict:
    """Check Windows Update status."""
    import subprocess

    result = {"patches": [], "last_update": None, "total_patches": 0}

    def _run():
        try:
            proc = subprocess.run(
                ["powershell", "-Command",
                 "Get-HotFix | Select-Object HotFixID, Description, InstalledOn | "
                 "Sort-Object InstalledOn -Descending | Select-Object -First 10 | "
                 "ConvertTo-Json"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.stdout.strip():
                data = json.loads(proc.stdout)
                if isinstance(data, dict):
                    data = [data]
                return data
        except Exception:
            pass
        return []

    patches = await asyncio.get_event_loop().run_in_executor(None, _run)
    result["patches"] = patches
    result["total_patches"] = len(patches)
    if patches:
        result["last_update"] = patches[0].get("InstalledOn", {}).get("DateTime") if isinstance(patches[0].get("InstalledOn"), dict) else str(patches[0].get("InstalledOn", ""))

    return result


async def lookup_cves(software_name: str, version: str) -> dict:
    """Lookup CVEs for a software+version via NIST NVD API."""
    import urllib.request
    import urllib.error

    result = {"software": software_name, "version": version, "cves": [], "total": 0}

    # Clean name for search
    search_term = re.sub(r'[^\w\s.-]', '', software_name).strip()
    if not search_term or not version:
        return result

    try:
        api_url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch={quote(search_term)}&resultsPerPage=5"
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "VibeMind-Security-Scanner",
        })

        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=15)
        )
        data = json.loads(resp.read().decode())

        for vuln in data.get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "?")
            descriptions = cve.get("descriptions", [])
            desc = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")

            # CVSS score
            cvss_score = None
            metrics = cve.get("metrics", {})
            for metric_key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                metric_list = metrics.get(metric_key, [])
                if metric_list:
                    cvss_score = metric_list[0].get("cvssData", {}).get("baseScore")
                    break

            result["cves"].append({
                "id": cve_id,
                "description": desc[:200],
                "cvss_score": cvss_score,
                "published": cve.get("published", ""),
            })

        result["total"] = data.get("totalResults", 0)

    except Exception as e:
        result["error"] = str(e)

    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vulnerability Scanner")
    parser.add_argument("--scan", action="store_true", help="Full vulnerability scan")
    parser.add_argument("--inventory", action="store_true", help="List installed software only")
    parser.add_argument("--lookup", type=str, help="Lookup CVEs for specific software (name:version)")
    args = parser.parse_args()

    if not any([args.scan, args.inventory, args.lookup]):
        parser.print_help()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  VULNERABILITY SCANNER")
    print("  CVE Lookup for Installed Software")
    print("=" * 60 + "\n")

    if args.inventory or args.scan:
        print("  [1/3] Inventarisiere Software...", flush=True)
        software = await inventory_installed_software()
        print(f"         {len(software)} Programme gefunden\n")

        if args.inventory:
            for s in software:
                print(f"    {s['name']:<50} {s['version']:<20} {s['publisher']}")
            return

    if args.scan:
        print("  [2/3] Pruefe Windows Updates...", flush=True)
        updates = await check_windows_updates()
        print(f"         {updates['total_patches']} Patches | Letztes Update: {updates.get('last_update', '?')}")

        print("  [3/3] CVE Lookup (Top 10 Software)...", flush=True)
        # Check top software with versions
        to_check = [s for s in software if s["version"]][:10]
        all_cves = []

        for s in to_check:
            cve_result = await lookup_cves(s["name"], s["version"])
            if cve_result["cves"]:
                print(f"         {s['name']} {s['version']}: {len(cve_result['cves'])} CVE(s)")
                all_cves.append(cve_result)
            # Rate limit
            await asyncio.sleep(1)

        print(f"\n  {'=' * 56}")
        print(f"  CVE RESULTS")
        print(f"  {'=' * 56}")
        if all_cves:
            for cve_result in all_cves:
                print(f"\n  {cve_result['software']} {cve_result['version']}:")
                for cve in cve_result["cves"]:
                    score = cve.get("cvss_score", "?")
                    print(f"    [{score:>4}] {cve['id']}: {cve['description'][:80]}")
        else:
            print("  No CVEs found for checked software.")

    if args.lookup:
        parts = args.lookup.split(":")
        name = parts[0]
        version = parts[1] if len(parts) > 1 else ""
        result = await lookup_cves(name, version)
        print(f"\n  {name} {version}: {result['total']} total CVEs")
        for cve in result["cves"]:
            print(f"    [{cve.get('cvss_score', '?'):>4}] {cve['id']}: {cve['description'][:100]}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
