"""
Power Manager — MCP Server
==============================
Power plans, sleep settings, energy consumption.

Read-Only:
  - power_plan: Active plan + all available plans
  - battery_report: Power supply info
  - sleep_settings: Sleep/hibernate/screen-off timeouts
  - power_events: Recent sleep/wake/shutdown events

Actions:
  - set_power_plan: Switch active power plan
  - set_sleep_timeout: Set sleep/screen-off timeout
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Power Manager",
    instructions=(
        "Power plan and energy management tools. "
        "Use 'power_plan' to see current plan, 'sleep_settings' for timeouts, "
        "'power_events' for sleep/wake history. "
        "Actions 'set_power_plan' and 'set_sleep_timeout' may need admin."
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


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except: return None


@mcp.tool()
async def power_plan():
    """Show active power plan and list all available plans with GUIDs."""
    active = run_cmd(["powercfg", "/getactivescheme"])
    plans_raw = run_cmd(["powercfg", "/list"])

    plans = []
    if plans_raw:
        import re
        for line in plans_raw.splitlines():
            match = re.search(r'([0-9a-f-]{36})\s+\((.+?)\)', line, re.I)
            if match:
                guid, name = match.group(1), match.group(2)
                is_active = "*" in line
                plans.append({"guid": guid, "name": name, "active": is_active})

    return json.dumps({"active_scheme": active, "plans": plans}, indent=2, default=str)


@mcp.tool()
async def battery_report():
    """Power supply and battery info (desktop: PSU; laptop: battery health)."""
    info = {}

    psu = ps_json("""
        Get-CimInstance CIM_PowerSupply | ForEach-Object {
            @{ Name = $_.Name; Status = $_.Status; Description = $_.Description }
        }
    """)
    info["power_supply"] = psu

    battery = ps_json("""
        Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | ForEach-Object {
            @{
                Name = $_.Name
                Status = $_.BatteryStatus
                EstimatedCharge = $_.EstimatedChargeRemaining
                EstimatedRunTime = $_.EstimatedRunTime
            }
        }
    """)
    info["battery"] = battery

    # Power config info
    info["power_capabilities"] = ps("powercfg /availablesleepstates")

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def sleep_settings():
    """Current sleep, hibernate, and screen-off timeout settings."""
    settings = {}

    for sub, name in [("SUB_SLEEP", "sleep"), ("SUB_VIDEO", "display")]:
        raw = run_cmd(["powercfg", "/query", "SCHEME_CURRENT", sub])
        if raw:
            settings[name] = raw

    # Parse structured
    parsed = {}
    for key in ["standby-timeout-ac", "standby-timeout-dc", "monitor-timeout-ac", "monitor-timeout-dc", "hibernate-timeout-ac", "hibernate-timeout-dc"]:
        val = run_cmd(["powercfg", "/query", "SCHEME_CURRENT", "/q"])

    # Simpler approach: use powercfg /query parsed
    timeouts = ps_json("""
        $result = @{}
        $cfg = powercfg /query SCHEME_CURRENT SUB_SLEEP 2>$null
        if ($cfg) {
            $lines = $cfg -split "`n"
            for ($i=0; $i -lt $lines.Length; $i++) {
                if ($lines[$i] -match 'Aktuelle AC-Energieeinstellung|Current AC Power Setting') {
                    $val = ($lines[$i] -split ':\s*')[1].Trim() -replace '0x',''
                    $sec = [convert]::ToInt32($val, 16)
                    $result['sleep_ac_minutes'] = $sec / 60
                }
                if ($lines[$i] -match 'Aktuelle DC-Energieeinstellung|Current DC Power Setting') {
                    $val = ($lines[$i] -split ':\s*')[1].Trim() -replace '0x',''
                    $sec = [convert]::ToInt32($val, 16)
                    $result['sleep_dc_minutes'] = $sec / 60
                }
            }
        }
        $result
    """)

    return json.dumps({
        "timeouts": timeouts,
        "raw_sleep": settings.get("sleep", "")[:500] if settings.get("sleep") else None,
        "raw_display": settings.get("display", "")[:500] if settings.get("display") else None,
    }, indent=2, default=str)


@mcp.tool()
async def power_events(limit: int = 20):
    """
    Recent power events: sleep, wake, shutdown, unexpected power loss.

    Args:
        limit: Max events to return (default: 20)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{
            LogName='System'
            ProviderName='Microsoft-Windows-Kernel-Power','Microsoft-Windows-Power-Troubleshooter','EventLog'
        }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Id = $_.Id
                Level = $_.LevelDisplayName
                Provider = $_.ProviderName
                Message = if ($_.Message.Length -gt 200) {{ $_.Message.Substring(0,200) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)

    results = events if isinstance(events, list) else [events] if events else []
    return json.dumps({"events": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def set_power_plan(plan_name: str):
    """
    Switch to a different power plan.

    Args:
        plan_name: Plan name or GUID (e.g. 'Balanced', 'High performance', or a GUID)
    """
    # Get available plans
    plans_raw = run_cmd(["powercfg", "/list"])
    if not plans_raw:
        return json.dumps({"error": "Could not list power plans"})

    import re
    target_guid = None
    for line in plans_raw.splitlines():
        match = re.search(r'([0-9a-f-]{36})\s+\((.+?)\)', line, re.I)
        if match:
            guid, name = match.group(1), match.group(2)
            if plan_name.lower() in name.lower() or plan_name == guid:
                target_guid = guid
                break

    if not target_guid:
        return json.dumps({"error": f"Plan '{plan_name}' not found", "available": plans_raw})

    result = run_cmd(["powercfg", "/setactive", target_guid])
    active = run_cmd(["powercfg", "/getactivescheme"])

    return json.dumps({"action": "set_power_plan", "requested": plan_name, "guid": target_guid, "active_now": active}, indent=2)


@mcp.tool()
async def set_sleep_timeout(ac_minutes: int = 30, screen_ac_minutes: int = 15):
    """
    Set sleep and screen-off timeouts (AC power).

    Args:
        ac_minutes: Minutes until sleep on AC (0 = never)
        screen_ac_minutes: Minutes until screen off on AC (0 = never)
    """
    r1 = run_cmd(["powercfg", "/change", "standby-timeout-ac", str(ac_minutes)])
    r2 = run_cmd(["powercfg", "/change", "monitor-timeout-ac", str(screen_ac_minutes)])

    return json.dumps({
        "action": "set_sleep_timeout",
        "sleep_ac_minutes": ac_minutes,
        "screen_ac_minutes": screen_ac_minutes,
        "note": "May need admin privileges",
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
