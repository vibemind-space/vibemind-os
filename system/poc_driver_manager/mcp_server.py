"""
Driver Manager — MCP Server
===============================
Windows driver analysis and repair.

Read-Only:
  - list_drivers: All installed drivers with version, manufacturer
  - driver_conflicts: Devices with error codes or missing drivers
  - driver_detail: Full detail for a specific driver/device
  - unsigned_drivers: Security check — unsigned/untrusted drivers

Actions (Admin Required — user confirms UAC):
  - fix_driver: Reinstall/update a problem driver
  - scan_for_drivers: Trigger Windows driver scan
  - disable_device: Disable a problematic device
"""

import asyncio
import json
import os
import sys
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mcp_admin_helper import run_elevated, run_elevated_json, admin_required_response, is_admin

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Driver Manager",
    instructions=(
        "Windows driver analysis tools. All read-only. "
        "Use 'list_drivers' for overview, 'driver_conflicts' for problem devices, "
        "'unsigned_drivers' for security concerns."
    ),
)


def ps(cmd, timeout=15):
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + cmd.strip()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, timeout=timeout, encoding="utf-8", errors="replace"
        )
        try: os.unlink(path)
        except: pass
        return r.stdout.strip() if r.returncode == 0 and r.stdout else None
    except: return None


def ps_json(cmd, timeout=15):
    script = f"& {{\n{cmd.strip()}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try: return json.loads(raw)
        except: pass
    return None


@mcp.tool()
async def list_drivers(limit: int = 50):
    """
    List installed drivers with version, manufacturer, and date.

    Args:
        limit: Max number of drivers to return (default: 50)
    """
    drivers = ps_json(f"""
        Get-CimInstance Win32_PnPSignedDriver |
        Where-Object {{ $_.DeviceName -ne $null }} |
        Sort-Object DeviceName |
        Select-Object -First {limit} |
        ForEach-Object {{
            @{{
                Device = $_.DeviceName
                Manufacturer = $_.Manufacturer
                DriverVersion = $_.DriverVersion
                DriverDate = if ($_.DriverDate) {{ $_.DriverDate.ToString('yyyy-MM-dd') }} else {{ $null }}
                Signed = $_.IsSigned
                DeviceClass = $_.DeviceClass
                InfName = $_.InfName
            }}
        }}
    """)

    results = drivers if isinstance(drivers, list) else [drivers] if drivers else []
    return json.dumps({"drivers": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def driver_conflicts():
    """Find devices with problems: error codes, missing drivers, disabled devices."""
    problems = ps_json("""
        Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.ConfigManagerErrorCode -ne 0 } |
        ForEach-Object {
            @{
                Device = $_.Name
                DeviceID = $_.DeviceID
                ErrorCode = $_.ConfigManagerErrorCode
                Status = $_.Status
                Manufacturer = $_.Manufacturer
                Description = switch ($_.ConfigManagerErrorCode) {
                    1  { 'Not configured correctly' }
                    3  { 'Driver corrupted' }
                    10 { 'Device cannot start' }
                    12 { 'Cannot find enough free resources' }
                    14 { 'Restart required' }
                    16 { 'Not fully recognized' }
                    22 { 'Device is disabled' }
                    28 { 'Drivers not installed' }
                    31 { 'Device is not working properly' }
                    default { 'Error code ' + $_.ConfigManagerErrorCode }
                }
            }
        }
    """)

    results = problems if isinstance(problems, list) else [problems] if problems else []
    results = [r for r in results if isinstance(r, dict) and r.get("Device")]

    return json.dumps({
        "problems": results,
        "total": len(results),
        "note": "No device problems found" if not results else f"{len(results)} devices with issues",
    }, indent=2, default=str)


@mcp.tool()
async def driver_detail(name: str):
    """
    Detailed info for a specific driver/device (partial name match).

    Args:
        name: Device name to search for (e.g. 'NVIDIA', 'Realtek', 'USB')
    """
    detail = ps_json(f"""
        Get-CimInstance Win32_PnPSignedDriver |
        Where-Object {{ $_.DeviceName -like '*{name}*' }} |
        ForEach-Object {{
            @{{
                Device = $_.DeviceName
                Manufacturer = $_.Manufacturer
                DriverVersion = $_.DriverVersion
                DriverDate = if ($_.DriverDate) {{ $_.DriverDate.ToString('yyyy-MM-dd') }} else {{ $null }}
                Signed = $_.IsSigned
                Signer = $_.Signer
                DeviceClass = $_.DeviceClass
                DeviceID = $_.DeviceID
                InfName = $_.InfName
                Location = $_.Location
                DriverProviderName = $_.DriverProviderName
            }}
        }}
    """)

    results = detail if isinstance(detail, list) else [detail] if detail else []
    return json.dumps({"query": name, "matches": len(results), "drivers": results}, indent=2, default=str)


@mcp.tool()
async def unsigned_drivers():
    """List all unsigned/untrusted drivers — potential security concern."""
    unsigned = ps_json("""
        Get-CimInstance Win32_PnPSignedDriver |
        Where-Object { $_.IsSigned -eq $false -and $_.DeviceName -ne $null } |
        ForEach-Object {
            @{
                Device = $_.DeviceName
                Manufacturer = $_.Manufacturer
                DriverVersion = $_.DriverVersion
                InfName = $_.InfName
                DeviceClass = $_.DeviceClass
            }
        }
    """)

    results = unsigned if isinstance(unsigned, list) else [unsigned] if unsigned else []
    results = [r for r in results if isinstance(r, dict) and r.get("Device")]

    return json.dumps({
        "unsigned_drivers": results,
        "total": len(results),
        "severity": "HIGH" if len(results) > 0 else "OK",
        "note": "Unsigned drivers could be modified/malicious" if results else "All drivers are signed",
    }, indent=2, default=str)


# ═══════════════════════════════════════════════════════════
#  ADMIN ACTION TOOLS
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def fix_driver(device_id: str, confirm: bool = False):
    """
    Reinstall/update a problem driver. Requires admin (UAC popup).

    First call without confirm=true to see what will happen.
    Then call with confirm=true to execute.

    Args:
        device_id: Device Instance ID (from driver_conflicts output)
        confirm: Set to true to actually execute (triggers UAC)
    """
    # Lookup device info first (no admin needed)
    info = ps_json(f"""
        Get-CimInstance Win32_PnPEntity |
        Where-Object {{ $_.DeviceID -eq '{device_id}' }} |
        ForEach-Object {{
            @{{
                Name = $_.Name
                DeviceID = $_.DeviceID
                Status = $_.Status
                ErrorCode = $_.ConfigManagerErrorCode
                Manufacturer = $_.Manufacturer
            }}
        }}
    """)

    if not info:
        return json.dumps({{"error": f"Device not found: {device_id}"}})

    device_name = info.get("Name", "Unknown") if isinstance(info, dict) else "Unknown"

    if not confirm:
        return json.dumps({
            "needs_admin": True,
            "action": "fix_driver",
            "device": device_name,
            "device_id": device_id,
            "description": f"Treiber fuer '{device_name}' neu installieren",
            "steps": [
                "1. Aktuellen fehlerhaften Treiber deinstallieren",
                "2. Windows nach neuem Treiber suchen lassen (pnputil /scan-devices)",
                "3. Optional: Windows Update nach Treiber durchsuchen",
            ],
            "message": "Rufe fix_driver erneut auf mit confirm=true um fortzufahren (UAC-Popup erscheint)",
        }, indent=2)

    # Execute with admin
    script = f"""
Write-Output "Fixing driver for: {device_name}"
Write-Output "Device ID: {device_id}"
Write-Output ""

# Step 1: Remove current broken driver
Write-Output "Step 1: Removing broken driver..."
pnputil /remove-device "{device_id}" 2>&1 | ForEach-Object {{ Write-Output $_ }}
Write-Output ""

# Step 2: Scan for new driver
Write-Output "Step 2: Scanning for drivers..."
pnputil /scan-devices 2>&1 | ForEach-Object {{ Write-Output $_ }}
Write-Output ""

# Step 3: Check if fixed
Start-Sleep -Seconds 3
$device = Get-CimInstance Win32_PnPEntity | Where-Object {{ $_.DeviceID -eq '{device_id}' }}
if ($device) {{
    $code = $device.ConfigManagerErrorCode
    if ($code -eq 0) {{
        Write-Output "SUCCESS: Device is now working correctly"
    }} else {{
        Write-Output "STILL BROKEN: Error code $code"
        Write-Output "Try Windows Update > Optional Updates for this driver"
    }}
}} else {{
    Write-Output "Device removed — will reappear on next scan if hardware present"
}}
"""

    output, error = run_elevated(script, timeout=60)

    return json.dumps({
        "action": "fix_driver",
        "device": device_name,
        "device_id": device_id,
        "output": output,
        "error": error,
    }, indent=2, default=str)


@mcp.tool()
async def scan_for_drivers(confirm: bool = False):
    """
    Trigger Windows to scan for and install missing drivers. Requires admin.

    Args:
        confirm: Set to true to execute (triggers UAC)
    """
    if not confirm:
        return json.dumps({
            "needs_admin": True,
            "action": "scan_for_drivers",
            "description": "Windows nach fehlenden Treibern suchen lassen + Optional Updates pruefen",
            "message": "Rufe scan_for_drivers mit confirm=true auf (UAC-Popup erscheint)",
        }, indent=2)

    script = """
Write-Output "=== Scanning for missing drivers ==="
pnputil /scan-devices 2>&1 | ForEach-Object { Write-Output $_ }
Write-Output ""

Write-Output "=== Checking Windows Update for driver updates ==="
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$criteria = "IsInstalled=0 and Type='Driver'"
try {
    $results = $searcher.Search($criteria)
    if ($results.Updates.Count -gt 0) {
        Write-Output "Found $($results.Updates.Count) driver updates:"
        foreach ($u in $results.Updates) {
            Write-Output "  - $($u.Title)"
        }
    } else {
        Write-Output "No driver updates available via Windows Update"
    }
} catch {
    Write-Output "Could not search Windows Update: $_"
}
Write-Output ""

Write-Output "=== Current problem devices ==="
pnputil /enum-devices /problem 2>&1 | ForEach-Object { Write-Output $_ }
"""

    output, error = run_elevated(script, timeout=90)

    return json.dumps({
        "action": "scan_for_drivers",
        "output": output,
        "error": error,
    }, indent=2, default=str)


@mcp.tool()
async def disable_device(device_id: str, confirm: bool = False):
    """
    Disable a problematic device (e.g. old Realtek BT when Intel BT is preferred).
    Requires admin.

    Args:
        device_id: Device Instance ID
        confirm: Set to true to execute (triggers UAC)
    """
    info = ps_json(f"""
        Get-CimInstance Win32_PnPEntity |
        Where-Object {{ $_.DeviceID -eq '{device_id}' }} |
        ForEach-Object {{
            @{{ Name = $_.Name; Status = $_.Status; Manufacturer = $_.Manufacturer }}
        }}
    """)

    device_name = info.get("Name", "Unknown") if isinstance(info, dict) else "Unknown"

    if not confirm:
        return json.dumps({
            "needs_admin": True,
            "action": "disable_device",
            "device": device_name,
            "device_id": device_id,
            "description": f"Geraet '{device_name}' deaktivieren",
            "message": "Rufe disable_device mit confirm=true auf (UAC-Popup erscheint)",
        }, indent=2)

    script = f"""
Write-Output "Disabling device: {device_name}"
pnputil /disable-device "{device_id}" 2>&1 | ForEach-Object {{ Write-Output $_ }}
Write-Output ""
$d = Get-CimInstance Win32_PnPEntity | Where-Object {{ $_.DeviceID -eq '{device_id}' }}
Write-Output "New status: $($d.Status) (Error: $($d.ConfigManagerErrorCode))"
"""

    output, error = run_elevated(script, timeout=30)

    return json.dumps({
        "action": "disable_device",
        "device": device_name,
        "output": output,
        "error": error,
    }, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
