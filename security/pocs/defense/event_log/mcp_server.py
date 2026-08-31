"""
Event Log — MCP Server
==========================
Windows Event Logs: errors, BSODs, crashes, login audit, security events.
All tools are read-only.

Tools:
  - recent_errors: Recent error events from System + Application
  - recent_warnings: Recent warning events
  - bsod_history: Blue screen crash history
  - app_crashes: Application crash/hang events
  - login_audit: Login attempts (success + failure)
  - security_events: Privilege escalation, account changes
  - event_search: Search events by keyword, log, time range
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Event Log",
    instructions=(
        "Windows Event Log analysis tools. All read-only. "
        "Use 'recent_errors' for quick error overview, 'bsod_history' for blue screens, "
        "'app_crashes' for application problems, 'login_audit' for security, "
        "'event_search' for flexible queries. Security log may need admin."
    ),
)


def ps(cmd, timeout=30):
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


def ps_json(cmd, timeout=30):
    script = f"& {{\n{cmd.strip()}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try: return json.loads(raw)
        except: pass
    return None


def format_events(events):
    if not events: return []
    return events if isinstance(events, list) else [events]


@mcp.tool()
async def recent_errors(limit: int = 20):
    """
    Recent Error-level events from System and Application logs.

    Args:
        limit: Max events (default: 20)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='System','Application'; Level=2 }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Log = $_.LogName
                Source = $_.ProviderName
                Id = $_.Id
                Message = if ($_.Message.Length -gt 300) {{ $_.Message.Substring(0,300) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)
    results = format_events(events)
    return json.dumps({"errors": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def recent_warnings(limit: int = 20):
    """
    Recent Warning-level events from System and Application logs.

    Args:
        limit: Max events (default: 20)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='System','Application'; Level=3 }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Log = $_.LogName
                Source = $_.ProviderName
                Id = $_.Id
                Message = if ($_.Message.Length -gt 300) {{ $_.Message.Substring(0,300) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)
    results = format_events(events)
    return json.dumps({"warnings": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def bsod_history():
    """Blue Screen of Death (BSOD) history — crash events with bugcheck codes."""
    events = ps_json("""
        $bsod = @()
        $bsod += Get-WinEvent -FilterHashtable @{ LogName='System'; Id=41 } -MaxEvents 10 -ErrorAction SilentlyContinue |
            ForEach-Object {
                @{ Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'); Type = 'UnexpectedShutdown'; Id = 41; Message = $_.Message.Substring(0, [math]::Min(300, $_.Message.Length)) }
            }
        $bsod += Get-WinEvent -FilterHashtable @{ LogName='System'; Id=1001; ProviderName='Microsoft-Windows-WER-SystemErrorReporting' } -MaxEvents 10 -ErrorAction SilentlyContinue |
            ForEach-Object {
                @{ Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'); Type = 'BugCheck'; Id = 1001; Message = $_.Message.Substring(0, [math]::Min(300, $_.Message.Length)) }
            }
        $bsod | Sort-Object Time -Descending
    """)
    results = format_events(events)
    return json.dumps({"bsod_events": results, "total": len(results), "note": "Empty = no BSODs recorded" if not results else None}, indent=2, default=str)


@mcp.tool()
async def app_crashes(limit: int = 20):
    """
    Application crash and hang events.

    Args:
        limit: Max events (default: 20)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='Application'; ProviderName='Application Error','Application Hang','Windows Error Reporting' }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Source = $_.ProviderName
                Id = $_.Id
                Message = if ($_.Message.Length -gt 300) {{ $_.Message.Substring(0,300) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)
    results = format_events(events)
    return json.dumps({"crashes": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def login_audit(limit: int = 30):
    """
    Login attempts — successful and failed. Requires admin for Security log.

    Args:
        limit: Max events (default: 30)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='Security'; Id=4624,4625 }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            $type = if ($_.Id -eq 4624) {{ 'SUCCESS' }} else {{ 'FAILED' }}
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Type = $type
                EventId = $_.Id
                Message = if ($_.Message.Length -gt 200) {{ $_.Message.Substring(0,200) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)
    results = format_events(events)
    if not results:
        return json.dumps({"note": "Security log requires admin privileges or audit policy enabled", "events": []})
    return json.dumps({"login_events": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def security_events(limit: int = 20):
    """
    Security-relevant events: privilege escalation, account changes. Needs admin.

    Args:
        limit: Max events (default: 20)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{ LogName='Security'; Id=4672,4720,4722,4725,4726,4732,4738,4740,4767 }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                EventId = $_.Id
                Description = switch ($_.Id) {{
                    4672 {{ 'Special privileges assigned' }}
                    4720 {{ 'User account created' }}
                    4722 {{ 'User account enabled' }}
                    4725 {{ 'User account disabled' }}
                    4726 {{ 'User account deleted' }}
                    4732 {{ 'Member added to security group' }}
                    4738 {{ 'User account changed' }}
                    4740 {{ 'User account locked out' }}
                    4767 {{ 'User account unlocked' }}
                }}
                Message = if ($_.Message.Length -gt 200) {{ $_.Message.Substring(0,200) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)
    results = format_events(events)
    if not results:
        return json.dumps({"note": "Security log requires admin privileges", "events": []})
    return json.dumps({"security_events": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def event_search(keyword: str = "", log: str = "System", hours: int = 24, level: str = "all"):
    """
    Search events with flexible filters.

    Args:
        keyword: Text to search in event messages (empty = all)
        log: Log name: System, Application, Security (default: System)
        hours: Look back N hours (default: 24)
        level: 'error', 'warning', 'info', or 'all' (default: all)
    """
    level_filter = ""
    if level == "error": level_filter = "Level=2;"
    elif level == "warning": level_filter = "Level=3;"
    elif level == "info": level_filter = "Level=4;"

    keyword_filter = f"| Where-Object {{ $_.Message -like '*{keyword}*' }}" if keyword else ""

    events = ps_json(f"""
        $start = (Get-Date).AddHours(-{hours})
        Get-WinEvent -FilterHashtable @{{ LogName='{log}'; {level_filter} StartTime=$start }} -MaxEvents 50 -ErrorAction SilentlyContinue {keyword_filter} |
        Select-Object -First 30 |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                Level = $_.LevelDisplayName
                Source = $_.ProviderName
                Id = $_.Id
                Message = if ($_.Message.Length -gt 300) {{ $_.Message.Substring(0,300) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)

    results = format_events(events)
    return json.dumps({
        "query": {"keyword": keyword, "log": log, "hours": hours, "level": level},
        "events": results,
        "total": len(results),
    }, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
