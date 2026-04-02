"""
Registry — MCP Server
=========================
Windows Registry: search, read, startup entries, installed programs.

Read-Only:
  - reg_search: Search registry by pattern
  - reg_read: Read specific key and values
  - startup_entries: All autostart programs
  - installed_programs: All installed software

Actions:
  - reg_set: Set a registry value (User scope, with safety blocklist)
  - reg_export: Export registry key to .reg file
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Registry",
    instructions=(
        "Windows Registry tools. Use 'startup_entries' for autostart programs, "
        "'installed_programs' for software list, 'reg_read' for specific keys, "
        "'reg_search' to find values. "
        "reg_set only works on HKCU (user scope) with safety blocklist."
    ),
)

BLOCKED_PATHS = [
    "HKLM:\\SYSTEM", "HKLM:\\SAM", "HKLM:\\SECURITY",
    "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies",
    "HKLM:\\SOFTWARE\\Microsoft\\Windows NT",
]


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
async def reg_read(path: str):
    """
    Read a specific registry key and all its values.

    Args:
        path: Registry path (e.g. 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run')
    """
    values = ps_json(f"""
        $key = Get-ItemProperty -Path '{path}' -ErrorAction SilentlyContinue
        if ($key) {{
            $key.PSObject.Properties | Where-Object {{ $_.Name -notlike 'PS*' }} |
            ForEach-Object {{ @{{ Name = $_.Name; Value = $_.Value.ToString().Substring(0, [math]::Min(500, $_.Value.ToString().Length)); Type = $_.TypeNameOfValue }} }}
        }}
    """)

    subkeys = ps_json(f"""
        Get-ChildItem -Path '{path}' -ErrorAction SilentlyContinue |
        ForEach-Object {{ @{{ Name = $_.PSChildName; Path = $_.Name }} }}
    """)

    results_vals = values if isinstance(values, list) else [values] if values else []
    results_keys = subkeys if isinstance(subkeys, list) else [subkeys] if subkeys else []

    return json.dumps({"path": path, "values": results_vals, "subkeys": results_keys}, indent=2, default=str)


@mcp.tool()
async def reg_search(path: str, pattern: str, max_depth: int = 2):
    """
    Search registry for a pattern in key names or values.

    Args:
        path: Root path to search (e.g. 'HKCU:\\SOFTWARE')
        pattern: Pattern to search for (wildcard, e.g. '*python*')
        max_depth: Max recursion depth (default: 2, to avoid slowness)
    """
    results = ps_json(f"""
        $found = @()
        Get-ChildItem -Path '{path}' -Recurse -Depth {max_depth} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            $key = $_
            if ($key.PSChildName -like '{pattern}') {{
                $found += @{{ Type = 'Key'; Path = $key.Name }}
            }}
            $key | Get-ItemProperty -ErrorAction SilentlyContinue |
            ForEach-Object {{
                $_.PSObject.Properties | Where-Object {{ $_.Name -notlike 'PS*' -and ($_.Name -like '{pattern}' -or $_.Value -like '{pattern}') }} |
                ForEach-Object {{
                    $found += @{{ Type = 'Value'; Path = $key.Name; Name = $_.Name; Value = $_.Value.ToString().Substring(0, [math]::Min(200, $_.Value.ToString().Length)) }}
                }}
            }}
        }}
        $found | Select-Object -First 30
    """)

    results_list = results if isinstance(results, list) else [results] if results else []
    return json.dumps({"search": {"path": path, "pattern": pattern}, "results": results_list, "total": len(results_list)}, indent=2, default=str)


@mcp.tool()
async def startup_entries():
    """All autostart programs from Registry Run keys and startup folders."""
    entries = ps_json("""
        $all = @()
        $paths = @(
            'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run',
            'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce',
            'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run',
            'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce'
        )
        foreach ($p in $paths) {
            $props = Get-ItemProperty -Path $p -ErrorAction SilentlyContinue
            if ($props) {
                $props.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } |
                ForEach-Object {
                    $all += @{ Source = $p; Name = $_.Name; Command = $_.Value.ToString().Substring(0, [math]::Min(300, $_.Value.ToString().Length)) }
                }
            }
        }
        # WMI startup commands
        Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | ForEach-Object {
            $all += @{ Source = $_.Location; Name = $_.Name; Command = $_.Command; User = $_.User }
        }
        $all
    """)

    results = entries if isinstance(entries, list) else [entries] if entries else []
    return json.dumps({"startup_entries": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def installed_programs():
    """All installed programs from registry uninstall keys."""
    programs = ps_json("""
        $paths = @(
            'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
            'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
            'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
        )
        $paths | ForEach-Object {
            Get-ItemProperty $_ -ErrorAction SilentlyContinue
        } | Where-Object { $_.DisplayName } |
        Sort-Object DisplayName |
        ForEach-Object {
            @{
                Name = $_.DisplayName
                Version = $_.DisplayVersion
                Publisher = $_.Publisher
                InstallDate = $_.InstallDate
                Size_MB = if ($_.EstimatedSize) { [math]::Round($_.EstimatedSize / 1024, 0) } else { $null }
            }
        }
    """)

    results = programs if isinstance(programs, list) else [programs] if programs else []
    return json.dumps({"programs": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def reg_set(path: str, name: str, value: str, reg_type: str = "String"):
    """
    Set a registry value. Only HKCU (user scope) allowed.

    Args:
        path: Registry path (must start with HKCU)
        name: Value name
        value: Value data
        reg_type: String, DWord, QWord, ExpandString, MultiString (default: String)
    """
    if not path.upper().startswith("HKCU"):
        return json.dumps({"error": "Only HKCU (user scope) writes allowed for safety"})

    for blocked in BLOCKED_PATHS:
        if path.upper().startswith(blocked.upper()):
            return json.dumps({"error": f"Blocked path: {path}"})

    type_map = {"string": "String", "dword": "DWord", "qword": "QWord", "expandstring": "ExpandString"}
    ps_type = type_map.get(reg_type.lower(), "String")

    before = ps(f"(Get-ItemProperty -Path '{path}' -Name '{name}' -ErrorAction SilentlyContinue).'{name}'")

    ps(f"""
        if (-not (Test-Path '{path}')) {{ New-Item -Path '{path}' -Force | Out-Null }}
        Set-ItemProperty -Path '{path}' -Name '{name}' -Value '{value}' -Type {ps_type}
    """)

    after = ps(f"(Get-ItemProperty -Path '{path}' -Name '{name}' -ErrorAction SilentlyContinue).'{name}'")

    return json.dumps({"action": "reg_set", "path": path, "name": name, "before": before, "after": after, "success": after == value}, indent=2)


@mcp.tool()
async def reg_export(path: str, filename: str = ""):
    """
    Export a registry key to a .reg file.

    Args:
        path: Registry path to export (e.g. 'HKCU\\SOFTWARE\\MyApp')
        filename: Output filename (default: auto-generated in Desktop)
    """
    if not filename:
        safe_name = path.replace("\\", "_").replace(":", "").replace("/", "_")
        filename = os.path.join(os.path.expanduser("~"), "Desktop", f"reg_export_{safe_name}.reg")

    # reg export needs non-PowerShell format
    reg_path = path.replace("HKCU:\\", "HKCU\\").replace("HKLM:\\", "HKLM\\")

    result = subprocess.run(
        ["reg", "export", reg_path, filename, "/y"],
        capture_output=True, text=True, timeout=15,
        encoding="utf-8", errors="replace"
    )

    success = result.returncode == 0
    return json.dumps({"action": "reg_export", "path": path, "file": filename, "success": success}, indent=2)


if __name__ == "__main__":
    mcp.run()
