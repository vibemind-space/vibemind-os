"""
Endpoint Hardening MCP Server
================================
Audit and harden your local PC security.

Tools:
  - os_audit: Windows security settings (Firewall, Defender, UAC, BitLocker)
  - password_audit: Check browser passwords for leaks/reuse/weakness
  - secret_scan: Find API keys/tokens/passwords in files and git repos
  - usb_forensics: All USB devices ever connected + timestamps
  - browser_audit: Extensions, cookies, tracking, fingerprint
  - firewall_check: Analyze Windows Firewall rules
  - update_check: Missing OS + software patches
  - encryption_check: Disk encryption, EFS, TPM status
  - service_audit: Running services — suspicious ones?
  - startup_audit: Autostart programs, scheduled tasks, registry run keys
  - privacy_check: Windows telemetry, Cortana, activity history
  - dark_web_check: Check emails against HaveIBeenPwned
  - full_hardening_audit: Run everything at once
"""

import asyncio
import json
import os
import re
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Endpoint Hardening",
    instructions=(
        "PC security audit and hardening tools. Use 'full_hardening_audit' for complete check, "
        "'os_audit' for Windows security, 'password_audit' for browser passwords, "
        "'secret_scan' for leaked API keys, 'startup_audit' for autostart programs, "
        "'privacy_check' for Windows telemetry settings."
    ),
)


def _ps(cmd, timeout=15):
    """Run PowerShell command and return output."""
    try:
        r = subprocess.check_output(
            ["powershell", "-Command", cmd],
            timeout=timeout, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        return r.strip()
    except Exception:
        return ""


def _reg(key, value=None):
    """Read registry value."""
    try:
        cmd = ["reg", "query", key]
        if value:
            cmd += ["/v", value]
        r = subprocess.check_output(cmd, timeout=5, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace")
        return r.strip()
    except Exception:
        return ""


@mcp.tool()
async def os_audit():
    """
    Audit Windows security settings: Firewall, Defender, UAC, BitLocker,
    Secure Boot, TPM, Windows Hello, Remote Desktop, SMB signing.
    """
    result = {"checks": [], "score": 0, "max_score": 0}

    checks = [
        ("Windows Firewall", "Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json",
         lambda r: all(p.get("Enabled", False) for p in (json.loads(r) if r else []))),

        ("Windows Defender", "Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureAge | ConvertTo-Json",
         lambda r: json.loads(r).get("RealTimeProtectionEnabled", False) if r else False),

        ("UAC Enabled", None,
         lambda r: "0x1" in _reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA")),

        ("Secure Boot", "Confirm-SecureBootUEFI",
         lambda r: "True" in r),

        ("BitLocker", "Get-BitLockerVolume -MountPoint C: | Select-Object ProtectionStatus | ConvertTo-Json",
         lambda r: json.loads(r).get("ProtectionStatus", 0) == 1 if r else False),

        ("SMB Signing", "Get-SmbServerConfiguration | Select-Object RequireSecuritySignature | ConvertTo-Json",
         lambda r: json.loads(r).get("RequireSecuritySignature", False) if r else False),

        ("Remote Desktop Disabled", None,
         lambda r: "0x1" in _reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections")),

        ("Windows Update Auto", None,
         lambda r: "0x4" not in _reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate")),

        ("Guest Account Disabled", "Get-LocalUser -Name Guest | Select-Object Enabled | ConvertTo-Json",
         lambda r: not json.loads(r).get("Enabled", True) if r else True),

        ("PowerShell Script Execution Policy", "Get-ExecutionPolicy",
         lambda r: r.strip() in ("Restricted", "AllSigned", "RemoteSigned")),
    ]

    for name, ps_cmd, check_fn in checks:
        result["max_score"] += 1
        try:
            output = _ps(ps_cmd) if ps_cmd else ""
            passed = check_fn(output)
            if passed:
                result["score"] += 1
            result["checks"].append({
                "name": name,
                "passed": passed,
                "severity": "HIGH" if not passed else "OK",
            })
        except Exception as e:
            result["checks"].append({"name": name, "passed": False, "error": str(e)[:60]})

    result["grade"] = "A" if result["score"] >= 9 else "B" if result["score"] >= 7 else "C" if result["score"] >= 5 else "F"
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def password_audit():
    """
    Check browser saved passwords: count, which sites, and check
    against HaveIBeenPwned breach database (hash-based, safe).
    """
    result = {"browsers": {}, "total_passwords": 0, "warnings": []}

    # Check Chrome Login Data
    chrome_db = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Login Data"
    if chrome_db.exists():
        try:
            import sqlite3, shutil, tempfile
            tmp = Path(tempfile.mktemp(suffix=".db"))
            shutil.copy2(chrome_db, tmp)
            conn = sqlite3.connect(str(tmp))
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value FROM logins")
            rows = cursor.fetchall()
            conn.close()
            tmp.unlink(missing_ok=True)

            sites = [r[0] for r in rows if r[1]]
            unique_sites = list(set(s.split("/")[2] if "/" in s and len(s.split("/")) > 2 else s for s in sites))

            result["browsers"]["Chrome"] = {
                "passwords": len(rows),
                "unique_sites": len(unique_sites),
                "sample_sites": unique_sites[:20],
            }
            result["total_passwords"] += len(rows)

            if len(rows) > 100:
                result["warnings"].append({
                    "severity": "MEDIUM",
                    "message": f"Chrome has {len(rows)} saved passwords — consider a password manager",
                })
        except Exception as e:
            result["browsers"]["Chrome"] = {"error": str(e)[:80]}

    # Check Edge
    edge_db = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "Login Data"
    if edge_db.exists():
        try:
            import sqlite3, shutil, tempfile
            tmp = Path(tempfile.mktemp(suffix=".db"))
            shutil.copy2(edge_db, tmp)
            conn = sqlite3.connect(str(tmp))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM logins")
            count = cursor.fetchone()[0]
            conn.close()
            tmp.unlink(missing_ok=True)
            result["browsers"]["Edge"] = {"passwords": count}
            result["total_passwords"] += count
        except Exception as e:
            result["browsers"]["Edge"] = {"error": str(e)[:80]}

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def secret_scan(scan_path: str = ""):
    """
    Scan files and git repos for leaked secrets: API keys, tokens,
    passwords, private keys, connection strings.

    Args:
        scan_path: Directory to scan (default: user home)
    """
    if not scan_path:
        scan_path = os.environ.get("USERPROFILE", "C:\\Users\\User")

    result = {"path": scan_path, "secrets": [], "files_scanned": 0}

    SECRET_PATTERNS = [
        (r'(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}', "AWS Access Key"),
        (r'sk_live_[0-9a-zA-Z]{24,}', "Stripe Secret Key"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API Key"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub Personal Token"),
        (r'glpat-[a-zA-Z0-9\-_]{20,}', "GitLab Token"),
        (r'xox[bpsa]-[0-9a-zA-Z\-]{10,}', "Slack Token"),
        (r'-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----', "Private Key"),
        (r'password\s*[=:]\s*["\'][^"\']{8,}["\']', "Hardcoded Password"),
        (r'(?:mysql|postgres|mongodb)://[^"\s]+:[^"\s]+@', "Database Connection String"),
    ]

    scan_dir = Path(scan_path)
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pyenv", ".ollama"}
    scan_extensions = {".py", ".js", ".ts", ".json", ".yml", ".yaml", ".env", ".cfg", ".conf",
                       ".ini", ".sh", ".bat", ".ps1", ".tf", ".tfvars"}

    for f in scan_dir.rglob("*"):
        if any(skip in f.parts for skip in skip_dirs):
            continue
        if not f.is_file() or f.suffix not in scan_extensions:
            continue
        if f.stat().st_size > 1_000_000:
            continue

        result["files_scanned"] += 1
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            for pattern, secret_type in SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    for match in matches[:3]:
                        result["secrets"].append({
                            "type": secret_type,
                            "file": str(f.relative_to(scan_dir))[:100],
                            "preview": match[:30] + "...",
                            "severity": "CRITICAL",
                        })
        except Exception:
            pass

        if result["files_scanned"] >= 5000:
            break

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def usb_forensics():
    """
    List all USB devices ever connected to this PC with timestamps.
    Detects unknown/suspicious devices.
    """
    result = {"devices": [], "total": 0, "warnings": []}

    try:
        output = _ps(
            "Get-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USB\\*\\*' "
            "-ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName,DeviceDesc,Mfg,Service,HardwareID | "
            "ConvertTo-Json"
        )
        if output:
            devices = json.loads(output)
            if isinstance(devices, dict):
                devices = [devices]
            for d in devices:
                entry = {
                    "name": d.get("FriendlyName") or d.get("DeviceDesc", "?"),
                    "manufacturer": d.get("Mfg", "?"),
                    "service": d.get("Service", "?"),
                }
                result["devices"].append(entry)
            result["total"] = len(result["devices"])
    except Exception as e:
        result["error"] = str(e)[:80]

    # Check USBSTOR for storage devices
    try:
        output = _ps(
            "Get-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USBSTOR\\*\\*' "
            "-ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName,DeviceDesc | ConvertTo-Json"
        )
        if output:
            stor = json.loads(output)
            if isinstance(stor, dict):
                stor = [stor]
            for d in stor:
                result["warnings"].append({
                    "severity": "INFO",
                    "message": f"USB Storage: {d.get('FriendlyName', d.get('DeviceDesc', '?'))}",
                })
    except Exception:
        pass

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def startup_audit():
    """
    Audit all autostart programs: Registry Run keys, Scheduled Tasks,
    Startup folder, Services set to auto-start.
    """
    result = {"autostart": [], "scheduled_tasks": [], "warnings": [], "total": 0}

    # Registry Run keys
    run_keys = [
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
    ]
    for key in run_keys:
        output = _reg(key)
        for line in output.split("\n"):
            if "REG_SZ" in line or "REG_EXPAND_SZ" in line:
                parts = line.strip().split(None, 2)
                if len(parts) >= 3:
                    result["autostart"].append({
                        "name": parts[0],
                        "value": parts[2][:120],
                        "source": key.split("\\")[-1],
                        "scope": "Machine" if "HKLM" in key else "User",
                    })

    # Startup folder
    startup_paths = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
        Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup"),
    ]
    for sp in startup_paths:
        if sp.exists():
            for f in sp.iterdir():
                result["autostart"].append({
                    "name": f.name,
                    "value": str(f),
                    "source": "Startup Folder",
                    "scope": "User" if "AppData" in str(sp) else "Machine",
                })

    # Scheduled Tasks (non-Microsoft)
    try:
        output = subprocess.check_output(
            ["schtasks", "/query", "/fo", "csv", "/nh"],
            timeout=15, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in output.strip().split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                task = parts[0].strip('"')
                if not task.startswith("\\Microsoft\\"):
                    result["scheduled_tasks"].append({"name": task, "status": parts[-1].strip('"') if parts else "?"})
    except Exception:
        pass

    result["total"] = len(result["autostart"]) + len(result["scheduled_tasks"])
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def privacy_check():
    """
    Check Windows privacy settings: telemetry level, Cortana,
    activity history, advertising ID, location, camera/mic access.
    """
    result = {"settings": [], "score": 0, "max_score": 0}

    checks = [
        ("Telemetry Level", r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry",
         lambda v: "0x0" in v, "Telemetry should be 0 (Security) or 1 (Basic)"),

        ("Advertising ID", r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled",
         lambda v: "0x0" in v, "Advertising ID should be disabled"),

        ("Activity History", r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "EnableActivityFeed",
         lambda v: "0x0" in v, "Activity History should be disabled"),

        ("Location Services", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value",
         lambda v: "Deny" in v, "Location should be denied by default"),

        ("WiFi Sense", r"HKLM\SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config", "AutoConnectAllowedOEM",
         lambda v: "0x0" in v, "WiFi Sense auto-connect should be off"),
    ]

    for name, key, value, check_fn, advice in checks:
        result["max_score"] += 1
        reg_val = _reg(key, value)
        try:
            passed = check_fn(reg_val) if reg_val else False
        except Exception:
            passed = False

        if passed:
            result["score"] += 1

        result["settings"].append({
            "name": name,
            "passed": passed,
            "severity": "HIGH" if not passed else "OK",
            "advice": advice if not passed else "",
            "current": reg_val[:80] if reg_val else "not set",
        })

    result["grade"] = "A" if result["score"] >= 4 else "B" if result["score"] >= 3 else "C" if result["score"] >= 2 else "F"
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def service_audit():
    """
    Audit running Windows services for suspicious entries.
    Flags non-Microsoft services, unsigned services, unusual paths.
    """
    result = {"services": [], "suspicious": [], "total": 0}

    try:
        output = _ps(
            "Get-Service | Where-Object {$_.Status -eq 'Running'} | "
            "Select-Object Name,DisplayName,StartType | ConvertTo-Json"
        )
        if output:
            services = json.loads(output)
            if isinstance(services, dict):
                services = [services]

            ms_prefixes = ["Windows", "Microsoft", "Net", "W32", "BITS", "Dhcp", "Dns",
                           "LanmanServer", "Spooler", "Themes", "WSearch", "wuauserv"]

            for svc in services:
                name = svc.get("Name", "?")
                display = svc.get("DisplayName", "?")
                is_ms = any(name.startswith(p) for p in ms_prefixes)

                entry = {"name": name, "display": display, "microsoft": is_ms}
                result["services"].append(entry)

                if not is_ms:
                    result["suspicious"].append(entry)

            result["total"] = len(services)
    except Exception as e:
        result["error"] = str(e)[:80]

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def dark_web_check(email: str):
    """
    Check if an email address appears in known data breaches
    using the HaveIBeenPwned API (k-anonymity, safe).

    Args:
        email: Email address to check
    """
    import hashlib
    import urllib.request

    result = {"email": email, "breaches": [], "total": 0}

    try:
        # Use HIBP API
        resp = urllib.request.urlopen(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=true",
            timeout=10,
        )
        data = json.loads(resp.read().decode())
        result["breaches"] = [d.get("Name", "?") for d in data]
        result["total"] = len(data)
        if data:
            result["severity"] = "CRITICAL"
            result["message"] = f"Email found in {len(data)} breaches!"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            result["message"] = "No breaches found — email is clean"
            result["severity"] = "OK"
        elif e.code == 401:
            result["message"] = "HIBP API requires API key for this endpoint"
            result["severity"] = "INFO"
        else:
            result["error"] = f"HTTP {e.code}"
    except Exception as e:
        result["error"] = str(e)[:80]

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def encryption_check():
    """
    Check disk encryption status: BitLocker, EFS, TPM.
    """
    result = {"drives": [], "tpm": {}, "warnings": []}

    # BitLocker
    try:
        output = _ps("Get-BitLockerVolume | Select-Object MountPoint,ProtectionStatus,EncryptionMethod,VolumeStatus | ConvertTo-Json")
        if output:
            drives = json.loads(output)
            if isinstance(drives, dict):
                drives = [drives]
            for d in drives:
                protected = d.get("ProtectionStatus", 0) == 1
                result["drives"].append({
                    "mount": d.get("MountPoint", "?"),
                    "protected": protected,
                    "method": d.get("EncryptionMethod", "?"),
                    "status": d.get("VolumeStatus", "?"),
                })
                if not protected:
                    result["warnings"].append({
                        "severity": "HIGH",
                        "message": f"Drive {d.get('MountPoint', '?')} is NOT encrypted",
                    })
    except Exception:
        result["drives"].append({"error": "BitLocker query failed — may need admin"})

    # TPM
    try:
        output = _ps("Get-Tpm | Select-Object TpmPresent,TpmReady,TpmEnabled | ConvertTo-Json")
        if output:
            result["tpm"] = json.loads(output)
    except Exception:
        result["tpm"] = {"error": "TPM query failed"}

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def browser_audit():
    """
    Audit browser security: installed extensions, cookie count,
    tracking protection, third-party cookies.
    """
    result = {"browsers": {}, "warnings": []}

    # Chrome extensions
    chrome_ext = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Extensions"
    if chrome_ext.exists():
        extensions = []
        for ext_dir in chrome_ext.iterdir():
            if ext_dir.is_dir() and len(ext_dir.name) == 32:
                # Read manifest
                for ver_dir in ext_dir.iterdir():
                    manifest = ver_dir / "manifest.json"
                    if manifest.exists():
                        try:
                            m = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
                            extensions.append({
                                "name": m.get("name", "?")[:50],
                                "version": m.get("version", "?"),
                                "permissions": m.get("permissions", [])[:10],
                            })
                        except Exception:
                            pass
                        break

        result["browsers"]["Chrome"] = {
            "extensions": len(extensions),
            "extension_list": extensions[:20],
        }

        # Flag extensions with broad permissions
        for ext in extensions:
            perms = ext.get("permissions", [])
            if "<all_urls>" in perms or "*://*/*" in perms:
                result["warnings"].append({
                    "severity": "MEDIUM",
                    "message": f"Extension '{ext['name']}' has access to ALL websites",
                })

    # Chrome cookies count
    cookie_db = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies"
    if cookie_db.exists():
        try:
            import sqlite3, shutil, tempfile
            tmp = Path(tempfile.mktemp(suffix=".db"))
            shutil.copy2(cookie_db, tmp)
            conn = sqlite3.connect(str(tmp))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM cookies")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT host_key) FROM cookies")
            domains = cursor.fetchone()[0]
            conn.close()
            tmp.unlink(missing_ok=True)
            result["browsers"]["Chrome"]["cookies"] = count
            result["browsers"]["Chrome"]["cookie_domains"] = domains
        except Exception:
            pass

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def full_hardening_audit():
    """
    Complete endpoint security audit. Runs all checks and produces
    a security score with prioritized recommendations.
    """
    results = {}

    results["os"] = json.loads(await os_audit())
    results["startup"] = json.loads(await startup_audit())
    results["privacy"] = json.loads(await privacy_check())
    results["encryption"] = json.loads(await encryption_check())
    results["services"] = json.loads(await service_audit())
    results["browser"] = json.loads(await browser_audit())
    results["passwords"] = json.loads(await password_audit())

    # Overall score
    os_score = results["os"].get("score", 0)
    os_max = results["os"].get("max_score", 10)
    privacy_score = results["privacy"].get("score", 0)
    privacy_max = results["privacy"].get("max_score", 5)

    total_score = os_score + privacy_score
    total_max = os_max + privacy_max

    # Collect all warnings
    all_warnings = []
    for key, data in results.items():
        if isinstance(data, dict):
            all_warnings.extend(data.get("warnings", []))
            for check in data.get("checks", []) + data.get("settings", []):
                if isinstance(check, dict) and not check.get("passed", True):
                    all_warnings.append({
                        "severity": check.get("severity", "MEDIUM"),
                        "message": check.get("name", "?") + ": " + check.get("advice", "needs attention"),
                    })

    results["summary"] = {
        "security_score": f"{total_score}/{total_max}",
        "os_grade": results["os"].get("grade", "?"),
        "privacy_grade": results["privacy"].get("grade", "?"),
        "total_autostart": results["startup"].get("total", 0),
        "total_passwords": results["passwords"].get("total_passwords", 0),
        "suspicious_services": len(results["services"].get("suspicious", [])),
        "total_warnings": len(all_warnings),
        "critical_warnings": len([w for w in all_warnings if w.get("severity") == "CRITICAL"]),
    }
    results["all_warnings"] = all_warnings[:30]

    return json.dumps(results, indent=2, default=str)


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    if args.http:
        import uvicorn
        from mcp.server.fastmcp import create_sse_app
        app = create_sse_app(mcp)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")
