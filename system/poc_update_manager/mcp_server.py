"""
Update Manager — MCP Server
===============================
Windows Update status, history, pending updates.

Read-Only:
  - update_status: Recent hotfixes and patches
  - update_history: Full update history via COM
  - pending_updates: Updates waiting to install

Actions:
  - check_updates: Trigger update check
  - pause_updates: Pause updates for N days
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Update Manager",
    instructions=(
        "Windows Update management. Use 'update_status' for recent patches, "
        "'pending_updates' to check what's waiting, 'update_history' for full log. "
        "Actions may need admin."
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


@mcp.tool()
async def update_status():
    """Recent installed hotfixes and OS version info."""
    hotfixes = ps_json("""
        Get-HotFix | Sort-Object InstalledOn -Descending -ErrorAction SilentlyContinue | Select-Object -First 15 |
        ForEach-Object {
            @{
                HotFixID = $_.HotFixID
                Description = $_.Description
                InstalledOn = if ($_.InstalledOn) { $_.InstalledOn.ToString('yyyy-MM-dd') } else { $null }
                InstalledBy = $_.InstalledBy
            }
        }
    """)

    os_info = ps_json("""
        Get-CimInstance Win32_OperatingSystem | ForEach-Object {
            @{
                Caption = $_.Caption
                Version = $_.Version
                BuildNumber = $_.BuildNumber
                LastBootUp = $_.LastBootUpTime.ToString('yyyy-MM-dd HH:mm')
                InstallDate = $_.InstallDate.ToString('yyyy-MM-dd')
            }
        }
    """)

    results = hotfixes if isinstance(hotfixes, list) else [hotfixes] if hotfixes else []
    return json.dumps({"os": os_info, "recent_hotfixes": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def update_history(limit: int = 30):
    """
    Full Windows Update history via COM object.

    Args:
        limit: Max entries (default: 30)
    """
    history = ps_json(f"""
        $session = New-Object -ComObject Microsoft.Update.Session
        $searcher = $session.CreateUpdateSearcher()
        $count = $searcher.GetTotalHistoryCount()
        $max = [math]::Min($count, {limit})
        $searcher.QueryHistory(0, $max) | ForEach-Object {{
            @{{
                Title = $_.Title
                Date = $_.Date.ToString('yyyy-MM-dd HH:mm')
                Result = switch ($_.ResultCode) {{
                    0 {{ 'NotStarted' }}
                    1 {{ 'InProgress' }}
                    2 {{ 'Succeeded' }}
                    3 {{ 'SucceededWithErrors' }}
                    4 {{ 'Failed' }}
                    5 {{ 'Aborted' }}
                    default {{ $_.ResultCode }}
                }}
                Operation = switch ($_.Operation) {{
                    1 {{ 'Install' }}
                    2 {{ 'Uninstall' }}
                    default {{ $_.Operation }}
                }}
            }}
        }}
    """)

    results = history if isinstance(history, list) else [history] if history else []
    return json.dumps({"history": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def pending_updates():
    """Check for pending Windows updates that haven't been installed yet."""
    pending = ps_json("""
        $session = New-Object -ComObject Microsoft.Update.Session
        $searcher = $session.CreateUpdateSearcher()
        $results = $searcher.Search("IsInstalled=0")
        $results.Updates | ForEach-Object {
            @{
                Title = $_.Title
                KB = ($_.KBArticleIDs -join ',')
                Size_MB = [math]::Round($_.MaxDownloadSize / 1MB, 0)
                IsDownloaded = $_.IsDownloaded
                IsMandatory = $_.IsMandatory
                Severity = $_.MsrcSeverity
            }
        }
    """)

    results = pending if isinstance(pending, list) else [pending] if pending else []
    return json.dumps({"pending_updates": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def check_updates():
    """Trigger Windows to check for new updates. May need admin."""
    ps("(New-Object -ComObject Microsoft.Update.AutoUpdate).DetectNow()")
    return json.dumps({"action": "check_updates", "triggered": True, "note": "Check started — open Windows Update to see results"}, indent=2)


@mcp.tool()
async def pause_updates(days: int = 7):
    """
    Pause Windows updates for N days. Needs admin.

    Args:
        days: Number of days to pause (default: 7, max: 35)
    """
    if days > 35:
        return json.dumps({"error": "Maximum 35 days"})

    from datetime import datetime, timedelta
    pause_until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    ps(f"""
        $path = 'HKLM:\\SOFTWARE\\Microsoft\\WindowsUpdate\\UX\\Settings'
        Set-ItemProperty -Path $path -Name 'PauseUpdatesExpiryTime' -Value '{pause_until}' -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $path -Name 'PauseFeatureUpdatesStartTime' -Value (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ') -ErrorAction SilentlyContinue
    """)

    return json.dumps({"action": "pause_updates", "days": days, "until": pause_until, "note": "Needs admin privileges"}, indent=2)


if __name__ == "__main__":
    mcp.run()
