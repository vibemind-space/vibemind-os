"""
Scheduled Tasks — MCP Server
================================
Windows Task Scheduler: list, inspect, create, manage tasks.

Read-Only:
  - list_tasks: All scheduled tasks with status
  - task_detail: Full detail for a specific task
  - task_history: Recent execution history

Actions:
  - create_task: Create new scheduled task
  - delete_task: Delete a task
  - enable_disable_task: Enable or disable a task
  - run_task: Manually trigger a task
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Scheduled Tasks",
    instructions=(
        "Windows Task Scheduler management. "
        "Use 'list_tasks' for overview (filters out Microsoft system tasks by default), "
        "'task_detail' for full info, 'run_task' to trigger manually. "
        "Actions may need admin for system-level tasks."
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
async def list_tasks(include_microsoft: bool = False):
    """
    List scheduled tasks with status, next run time, last result.

    Args:
        include_microsoft: Include Microsoft system tasks (default: false, shows only custom)
    """
    filter_clause = "" if include_microsoft else "| Where-Object { $_.TaskPath -notlike '\\\\Microsoft\\\\*' }"

    tasks = ps_json(f"""
        Get-ScheduledTask {filter_clause} |
        ForEach-Object {{
            $info = $_ | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
            @{{
                Name = $_.TaskName
                Path = $_.TaskPath
                State = $_.State.ToString()
                LastRun = if ($info.LastRunTime -and $info.LastRunTime.Year -gt 1999) {{ $info.LastRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
                NextRun = if ($info.NextRunTime -and $info.NextRunTime.Year -gt 1999) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
                LastResult = $info.LastTaskResult
            }}
        }}
    """)

    results = tasks if isinstance(tasks, list) else [tasks] if tasks else []
    return json.dumps({"tasks": results, "total": len(results), "include_microsoft": include_microsoft}, indent=2, default=str)


@mcp.tool()
async def task_detail(name: str):
    """
    Full detail for a scheduled task: triggers, actions, settings.

    Args:
        name: Task name (exact or partial match)
    """
    detail = ps_json(f"""
        $t = Get-ScheduledTask | Where-Object {{ $_.TaskName -like '*{name}*' }} | Select-Object -First 1
        if ($t) {{
            $info = $t | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
            $actions = $t.Actions | ForEach-Object {{ @{{ Execute = $_.Execute; Arguments = $_.Arguments; WorkingDir = $_.WorkingDirectory }} }}
            $triggers = $t.Triggers | ForEach-Object {{ @{{ Type = $_.CimClass.CimClassName; Enabled = $_.Enabled; StartBoundary = $_.StartBoundary; Repetition = $_.Repetition.Interval }} }}
            @{{
                Name = $t.TaskName
                Path = $t.TaskPath
                State = $t.State.ToString()
                Description = $t.Description
                Author = $t.Author
                RunAs = $t.Principal.UserId
                RunLevel = $t.Principal.RunLevel.ToString()
                Actions = $actions
                Triggers = $triggers
                LastRun = if ($info.LastRunTime.Year -gt 1999) {{ $info.LastRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
                NextRun = if ($info.NextRunTime.Year -gt 1999) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
                LastResult = $info.LastTaskResult
            }}
        }} else {{
            @{{ Error = "Task '{name}' not found" }}
        }}
    """)
    return json.dumps(detail, indent=2, default=str)


@mcp.tool()
async def task_history(name: str, limit: int = 10):
    """
    Recent execution history of a scheduled task.

    Args:
        name: Task name
        limit: Max entries (default: 10)
    """
    events = ps_json(f"""
        Get-WinEvent -FilterHashtable @{{
            LogName='Microsoft-Windows-TaskScheduler/Operational'
            Id=100,102,103,110,111,129,201,325
        }} -MaxEvents 200 -ErrorAction SilentlyContinue |
        Where-Object {{ $_.Message -like '*{name}*' }} |
        Select-Object -First {limit} |
        ForEach-Object {{
            @{{
                Time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                EventId = $_.Id
                Type = switch ($_.Id) {{
                    100 {{ 'Started' }}
                    102 {{ 'Completed' }}
                    103 {{ 'Failed to start' }}
                    110 {{ 'Triggered' }}
                    111 {{ 'Terminated' }}
                    129 {{ 'Created' }}
                    201 {{ 'Action completed' }}
                    325 {{ 'Launch request queued' }}
                }}
                Message = if ($_.Message.Length -gt 200) {{ $_.Message.Substring(0,200) + '...' }} else {{ $_.Message }}
            }}
        }}
    """)

    results = events if isinstance(events, list) else [events] if events else []
    return json.dumps({"task": name, "history": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def create_task(name: str, command: str, arguments: str = "", trigger_type: str = "daily", time: str = "08:00", interval_hours: int = 0):
    """
    Create a new scheduled task.

    Args:
        name: Task name
        command: Executable path (e.g. 'python')
        arguments: Command arguments
        trigger_type: 'daily', 'logon', or 'interval' (default: daily)
        time: Start time for daily trigger (HH:mm format)
        interval_hours: Repetition interval in hours (for trigger_type='interval')
    """
    PROTECTED_NAMES = ["PC_Storage_Manager"]

    if trigger_type == "daily":
        trigger_cmd = f"$trigger = New-ScheduledTaskTrigger -Daily -At '{time}'"
    elif trigger_type == "logon":
        trigger_cmd = "$trigger = New-ScheduledTaskTrigger -AtLogOn"
    elif trigger_type == "interval" and interval_hours > 0:
        trigger_cmd = f"""
$trigger = New-ScheduledTaskTrigger -Once -At '{time}' -RepetitionInterval (New-TimeSpan -Hours {interval_hours}) -RepetitionDuration (New-TimeSpan -Days 365)
"""
    else:
        return json.dumps({"error": f"Invalid trigger_type: {trigger_type}"})

    result = ps(f"""
{trigger_cmd}
$action = New-ScheduledTaskAction -Execute '{command}' -Argument '{arguments}'
Register-ScheduledTask -TaskName '{name}' -Trigger $trigger -Action $action -Description 'Created by PC MCP' -ErrorAction Stop
    """)

    verify = ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State")
    return json.dumps({"action": "create", "name": name, "state": verify, "success": bool(verify)}, indent=2)


@mcp.tool()
async def delete_task(name: str):
    """
    Delete a scheduled task.

    Args:
        name: Task name to delete
    """
    exists = ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).TaskName")
    if not exists:
        return json.dumps({"error": f"Task '{name}' not found"})

    ps(f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false")
    still_exists = ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).TaskName")

    return json.dumps({"action": "delete", "name": name, "success": not bool(still_exists)}, indent=2)


@mcp.tool()
async def enable_disable_task(name: str, enabled: bool):
    """
    Enable or disable a scheduled task.

    Args:
        name: Task name
        enabled: True to enable, False to disable
    """
    cmd = "Enable-ScheduledTask" if enabled else "Disable-ScheduledTask"
    ps(f"{cmd} -TaskName '{name}' -ErrorAction SilentlyContinue")
    state = ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State")

    return json.dumps({"action": "enable" if enabled else "disable", "name": name, "state": state}, indent=2)


@mcp.tool()
async def run_task(name: str):
    """
    Manually trigger a task to run now.

    Args:
        name: Task name to run
    """
    ps(f"Start-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue")
    state = ps(f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State")

    return json.dumps({"action": "run", "name": name, "state": state}, indent=2)


if __name__ == "__main__":
    mcp.run()
