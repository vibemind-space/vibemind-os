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

    result = run_elevated(script, timeout=60)
    output = result.get("stdout", "")
    error = result.get("stderr", "") or result.get("error", "")

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

    result = run_elevated(script, timeout=90)
    output = result.get("stdout", "")
    error = result.get("stderr", "") or result.get("error", "")

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

    result = run_elevated(script, timeout=30)
    output = result.get("stdout", "")
    error = result.get("stderr", "") or result.get("error", "")

    return json.dumps({
        "action": "disable_device",
        "device": device_name,
        "output": output,
        "error": error,
    }, indent=2, default=str)


# ===========================================================================
# Driver identification — map Device IDs to vendor-specific driver bundles
# ===========================================================================

# Intel Raptor Lake / Z790 chipset device IDs (VEN_8086)
# Source: Intel PCH datasheets + pci.ids
INTEL_CHIPSET_DEVICES = {
    "7A23": ("SMBus Controller", "chipset"),
    "7A24": ("SPI Controller", "chipset"),
    "7A4C": ("Serial IO I2C Host Controller", "chipset"),
    "7A4D": ("Serial IO I2C Host Controller", "chipset"),
    "7A4E": ("Serial IO I2C Host Controller", "chipset"),
    "7A50": ("PCI Express Root Port", "chipset"),
    "7A60": ("USB 3.2 xHCI Controller", "chipset"),
    "7AA7": ("Management Engine Interface", "mei"),
    "A77F": ("Volume Management Device (VMD) / RST", "rst"),
    "7A30": ("Thermal Subsystem", "chipset"),
}

DRIVER_BUNDLES = {
    "chipset": {
        "name": "Intel Chipset Device Software (INF Utility)",
        "intel_url": "https://www.intel.com/content/www/us/en/download/19347/intel-chipset-device-software-inf-utility.html",
        "notes": "Covers SMBus, PCIe root ports, Serial IO, thermal. Install FIRST before other drivers.",
    },
    "mei": {
        "name": "Intel Management Engine Interface (MEI) Driver",
        "intel_url": "https://www.intel.com/content/www/us/en/download/19187/intel-management-engine-driver-for-windows.html",
        "notes": "Required for CPU/PCH management features. Install after Chipset.",
    },
    "rst": {
        "name": "Intel Rapid Storage Technology (RST) / VMD Driver",
        "intel_url": "https://www.intel.com/content/www/us/en/download/19512/intel-rapid-storage-technology-driver-installation-software-with-intel-optane-memory.html",
        "notes": "Required for RAID/VMD storage controllers. Install after Chipset.",
    },
    "nvidia_gpu": {
        "name": "NVIDIA GeForce Game Ready Driver",
        "intel_url": "https://www.nvidia.com/Download/index.aspx",
        "notes": "Use DDU in Safe Mode before fresh install for clean reset.",
    },
    "realtek_audio": {
        "name": "Realtek High Definition Audio Driver",
        "intel_url": "https://www.realtek.com/en/component/zoo/category/pc-audio-codecs-high-definition-audio-codecs-software",
        "notes": "Board manufacturer often ships customized version — prefer ASUS/MSI download.",
    },
}


def _parse_device_id(device_id: str):
    """Extract VEN_XXXX and DEV_XXXX from a device ID string."""
    ven, dev = None, None
    parts = device_id.upper().replace("\\", "&").split("&")
    for p in parts:
        if p.startswith("VEN_"):
            ven = p[4:8]
        elif p.startswith("DEV_"):
            dev = p[4:8]
    return ven, dev


def _get_board_info():
    """Return motherboard vendor + model for vendor-specific download links."""
    data = ps_json('Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product')
    if not data:
        return "", ""
    return data.get("Manufacturer", "") or "", data.get("Product", "") or ""


@mcp.tool()
async def find_driver_for_device(device_id: str):
    """
    Identify vendor, category, and download link for a specific device ID.

    Maps the Device Instance ID (from driver_conflicts) to the correct driver
    bundle from Intel / NVIDIA / vendor sites. Does NOT download — only returns
    the link and install guidance.

    Args:
        device_id: Device Instance ID, e.g. 'PCI\\VEN_8086&DEV_7A23&SUBSYS_...'
    """
    ven, dev = _parse_device_id(device_id)
    if not ven:
        return json.dumps({"error": "Could not parse VEN_ from device_id", "device_id": device_id}, indent=2)

    board_mfr, board_model = _get_board_info()

    # Intel
    if ven == "8086":
        if dev and dev in INTEL_CHIPSET_DEVICES:
            part_name, category = INTEL_CHIPSET_DEVICES[dev]
        else:
            part_name, category = "Unknown Intel component", "chipset"
        bundle = DRIVER_BUNDLES[category]
        return json.dumps({
            "device_id": device_id,
            "vendor": "Intel",
            "part_name": part_name,
            "bundle": bundle["name"],
            "category": category,
            "download_url": bundle["intel_url"],
            "board_specific_url": f"https://www.google.com/search?q={board_mfr}+{board_model}+support+driver+download".replace(" ", "+"),
            "install_notes": bundle["notes"],
            "board": f"{board_mfr} {board_model}",
        }, indent=2)

    # NVIDIA
    if ven == "10DE":
        bundle = DRIVER_BUNDLES["nvidia_gpu"]
        return json.dumps({
            "device_id": device_id,
            "vendor": "NVIDIA",
            "bundle": bundle["name"],
            "category": "nvidia_gpu",
            "download_url": bundle["intel_url"],
            "install_notes": bundle["notes"],
        }, indent=2)

    # Realtek
    if ven == "10EC":
        bundle = DRIVER_BUNDLES["realtek_audio"]
        return json.dumps({
            "device_id": device_id,
            "vendor": "Realtek",
            "bundle": bundle["name"],
            "category": "realtek_audio",
            "download_url": bundle["intel_url"],
            "board_specific_url": f"https://www.google.com/search?q={board_mfr}+{board_model}+realtek+audio+download".replace(" ", "+"),
            "install_notes": bundle["notes"],
        }, indent=2)

    # Unknown vendor
    return json.dumps({
        "device_id": device_id,
        "vendor": f"Unknown (VEN_{ven})",
        "device": f"DEV_{dev}" if dev else "Unknown",
        "suggestion": "Search PCI ID database: https://pci-ids.ucw.cz/read/PC/" + (ven.lower() if ven else ""),
        "board_specific_url": f"https://www.google.com/search?q={board_mfr}+{board_model}+driver+VEN_{ven}".replace(" ", "+"),
    }, indent=2)


@mcp.tool()
async def suggest_fixes():
    """
    Analyze all problem devices and group them by driver bundle.

    Runs driver_conflicts internally, then maps each problem device to its
    correct driver bundle. Groups devices that share the same bundle so the
    user can install ONE package to fix multiple problems at once.
    """
    # Gather current problems directly via PowerShell (avoid calling the async tool fn)
    parsed = ps_json(
        'Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | '
        'Select-Object Name, DeviceID, ConfigManagerErrorCode, Manufacturer',
        timeout=20,
    )
    if parsed is None:
        return json.dumps({"problems": 0, "message": "No problem devices found"}, indent=2)
    if isinstance(parsed, dict):
        parsed = [parsed]

    board_mfr, board_model = _get_board_info()

    # Group by bundle category
    groups = {}
    unresolved = []

    for prob in parsed:
        device_id = prob.get("DeviceID", "")
        ven, dev = _parse_device_id(device_id)

        category = None
        vendor_name = None

        if ven == "8086":
            vendor_name = "Intel"
            if dev and dev in INTEL_CHIPSET_DEVICES:
                _, category = INTEL_CHIPSET_DEVICES[dev]
            else:
                category = "chipset"
        elif ven == "10DE":
            vendor_name = "NVIDIA"
            category = "nvidia_gpu"
        elif ven == "10EC":
            vendor_name = "Realtek"
            category = "realtek_audio"

        entry = {
            "device": prob.get("Name", "Unknown"),
            "device_id": device_id,
            "error_code": prob.get("ConfigManagerErrorCode"),
        }

        if category:
            groups.setdefault(category, {
                "bundle": DRIVER_BUNDLES[category]["name"],
                "vendor": vendor_name,
                "download_url": DRIVER_BUNDLES[category]["intel_url"],
                "install_notes": DRIVER_BUNDLES[category]["notes"],
                "devices": [],
            })
            groups[category]["devices"].append(entry)
        else:
            unresolved.append({**entry, "vendor": f"VEN_{ven}" if ven else "unknown"})

    # Install order — chipset must come first
    install_order = ["chipset", "mei", "rst", "nvidia_gpu", "realtek_audio"]
    ordered_groups = []
    for cat in install_order:
        if cat in groups:
            ordered_groups.append({"category": cat, **groups[cat]})
    for cat, data in groups.items():
        if cat not in install_order:
            ordered_groups.append({"category": cat, **data})

    return json.dumps({
        "total_problems": len(parsed),
        "board": f"{board_mfr} {board_model}",
        "bundles_to_install": ordered_groups,
        "unresolved_devices": unresolved,
        "note": "Install bundles in the order listed. Reboot after each. "
                "For ASUS/MSI boards, prefer board-vendor download page over raw Intel page "
                "(board vendors ship tested driver versions).",
    }, indent=2, default=str)


@mcp.tool()
async def open_driver_downloads(categories: str = ""):
    """
    Open driver download pages in the default browser for the given categories.

    If no categories given, runs suggest_fixes logic and opens pages for every
    bundle currently needed. Otherwise opens only the requested categories.

    Args:
        categories: Comma-separated bundle categories (e.g. "chipset,rst").
                    Valid: chipset, mei, rst, nvidia_gpu, realtek_audio.
                    Empty string = auto-detect from current problem devices.
    """
    import webbrowser

    # Determine which categories to open
    if categories.strip():
        cats = [c.strip() for c in categories.split(",") if c.strip()]
    else:
        # Auto-detect from current conflicts
        parsed = ps_json(
            'Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | '
            'Select-Object DeviceID',
            timeout=20,
        )
        if parsed is None:
            return json.dumps({"opened": 0, "message": "No problem devices found"}, indent=2)
        if isinstance(parsed, dict):
            parsed = [parsed]

        detected = set()
        for prob in parsed:
            ven, dev = _parse_device_id(prob.get("DeviceID", ""))
            if ven == "8086":
                if dev and dev in INTEL_CHIPSET_DEVICES:
                    detected.add(INTEL_CHIPSET_DEVICES[dev][1])
                else:
                    detected.add("chipset")
            elif ven == "10DE":
                detected.add("nvidia_gpu")
            elif ven == "10EC":
                detected.add("realtek_audio")
        cats = sorted(detected, key=lambda c: ["chipset", "mei", "rst", "nvidia_gpu", "realtek_audio"].index(c)
                      if c in ["chipset", "mei", "rst", "nvidia_gpu", "realtek_audio"] else 99)

    # Open each URL + include ASUS board-specific page when relevant
    board_mfr, board_model = _get_board_info()
    is_asus = "ASUS" in (board_mfr or "").upper()
    asus_url = None
    if is_asus and "Z790-H" in (board_model or ""):
        asus_url = "https://www.asus.com/motherboards-components/motherboards/rog-strix/rog-strix-z790-h-gaming-wifi/helpdesk_download"

    opened = []
    errors = []

    # Open ASUS page first (preferred for Intel chipset/rst/mei)
    needs_board_page = any(c in cats for c in ("chipset", "mei", "rst"))
    if asus_url and needs_board_page:
        try:
            webbrowser.open(asus_url)
            opened.append({"url": asus_url, "why": "Board-vendor page (preferred for Intel chipset/RST/MEI)"})
        except Exception as e:
            errors.append(f"ASUS page: {e}")

    for cat in cats:
        if cat not in DRIVER_BUNDLES:
            errors.append(f"Unknown category: {cat}")
            continue
        url = DRIVER_BUNDLES[cat]["intel_url"]
        try:
            webbrowser.open(url)
            opened.append({
                "category": cat,
                "bundle": DRIVER_BUNDLES[cat]["name"],
                "url": url,
                "install_notes": DRIVER_BUNDLES[cat]["notes"],
            })
        except Exception as e:
            errors.append(f"{cat}: {e}")

    return json.dumps({
        "opened_count": len(opened),
        "categories_requested": cats,
        "board": f"{board_mfr} {board_model}",
        "opened": opened,
        "errors": errors,
        "next_steps": [
            "1. Download the driver from each opened page (prefer ASUS page if available)",
            "2. Install in order: chipset -> reboot -> mei -> reboot -> rst -> reboot",
            "3. Run driver_conflicts afterwards to verify fixes",
        ],
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
