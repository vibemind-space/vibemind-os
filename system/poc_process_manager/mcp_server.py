"""
Process Manager — MCP Server
================================
Process monitoring, management, and diagnostics.

Tools (Read-Only):
  - process_list:       All processes with CPU/RAM/GPU usage
  - process_find:       Find process by name
  - process_detail:     Detailed info for a specific process (threads, handles, DLLs)
  - process_tree:       Parent-child process tree
  - memory_leaks:       Detect processes with growing memory usage
  - handle_count:       Processes with most open handles (leak indicator)
  - zombie_processes:   Hung/not-responding processes
  - service_list:       Windows services with status

Tools (Actions — user approves):
  - process_kill:       Kill a process by name or PID
  - process_priority:   Set process priority (realtime, high, normal, low, idle)
  - process_affinity:   Set CPU core affinity for a process
  - service_control:    Start/stop/restart a Windows service
"""

import asyncio
import json
import os
import sys
import subprocess
import time
import tempfile
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Process Manager",
    instructions=(
        "Process monitoring and management tools. "
        "Use 'process_list' for overview, 'process_find' to search by name, "
        "'memory_leaks' to find leaking processes, 'zombie_processes' for hung apps. "
        "Action tools (kill, priority, affinity) require user approval. "
        "All read-only tools are safe to run anytime."
    ),
)


# ── Helpers ─────────────────────────────────────────────────

def ps(cmd, timeout=15):
    """Run PowerShell via temp script file."""
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + cmd.strip()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        try:
            os.unlink(path)
        except:
            pass
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
        return None
    except:
        return None


def ps_json(cmd, timeout=15):
    """Run PowerShell returning JSON."""
    stripped = cmd.strip()
    script = f"& {{\n{stripped}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try:
            return json.loads(raw)
        except:
            pass
    return None


# ═══════════════════════════════════════════════════════════
#  READ-ONLY TOOLS
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def process_list(sort_by: str = "ram", limit: int = 30):
    """
    List running processes sorted by resource usage.

    Args:
        sort_by: Sort by 'ram', 'cpu', 'handles', or 'threads' (default: ram)
        limit: Max number of processes to return (default: 30)
    """
    sort_map = {
        "ram": "WorkingSet64",
        "cpu": "CPU",
        "handles": "HandleCount",
        "threads": "Threads",
    }
    sort_prop = sort_map.get(sort_by, "WorkingSet64")

    procs = ps_json(f"""
        Get-Process | Where-Object {{ $_.{sort_prop} -gt 0 }} |
        Sort-Object {sort_prop} -Descending | Select-Object -First {limit} |
        ForEach-Object {{
            @{{
                Name = $_.ProcessName
                PID = $_.Id
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                Private_MB = [math]::Round($_.PrivateMemorySize64 / 1MB, 0)
                CPU_Seconds = [math]::Round($_.CPU, 1)
                Threads = $_.Threads.Count
                Handles = $_.HandleCount
                Responding = $_.Responding
                StartTime = if ($_.StartTime) {{ $_.StartTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
            }}
        }}
    """)

    total_ram = ps("(Get-Process | Measure-Object WorkingSet64 -Sum).Sum / 1GB | ForEach-Object { [math]::Round($_, 1) }")
    total_count = ps("(Get-Process).Count")

    def safe_float(s):
        if not s: return 0
        return float(s.replace(",", "."))

    return json.dumps({
        "processes": procs if isinstance(procs, list) else [procs] if procs else [],
        "sorted_by": sort_by,
        "total_processes": int(total_count) if total_count else 0,
        "total_ram_gb": safe_float(total_ram),
    }, indent=2, default=str)


@mcp.tool()
async def process_find(name: str):
    """
    Find all processes matching a name (partial match).

    Args:
        name: Process name to search for (e.g. 'chrome', 'code', 'snip')
    """
    procs = ps_json(f"""
        Get-Process | Where-Object {{ $_.ProcessName -like '*{name}*' }} |
        Sort-Object WorkingSet64 -Descending |
        ForEach-Object {{
            @{{
                Name = $_.ProcessName
                PID = $_.Id
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                CPU_Seconds = [math]::Round($_.CPU, 1)
                Threads = $_.Threads.Count
                Handles = $_.HandleCount
                Responding = $_.Responding
                WindowTitle = $_.MainWindowTitle
                Path = $_.Path
                StartTime = if ($_.StartTime) {{ $_.StartTime.ToString('yyyy-MM-dd HH:mm') }} else {{ $null }}
            }}
        }}
    """)

    results = procs if isinstance(procs, list) else [procs] if procs else []
    total_ram = sum(p.get("RAM_MB", 0) for p in results if isinstance(p, dict))

    return json.dumps({
        "query": name,
        "matches": len(results),
        "total_ram_mb": total_ram,
        "processes": results,
    }, indent=2, default=str)


@mcp.tool()
async def process_detail(pid: int):
    """
    Detailed information about a specific process: threads, modules, handles, path, command line.

    Args:
        pid: Process ID
    """
    info = ps_json(f"""
        $p = Get-Process -Id {pid} -ErrorAction SilentlyContinue
        if ($p) {{
            @{{
                Name = $p.ProcessName
                PID = $p.Id
                RAM_MB = [math]::Round($p.WorkingSet64 / 1MB, 0)
                Private_MB = [math]::Round($p.PrivateMemorySize64 / 1MB, 0)
                Virtual_MB = [math]::Round($p.VirtualMemorySize64 / 1MB, 0)
                PagedMem_MB = [math]::Round($p.PagedMemorySize64 / 1MB, 0)
                CPU_Seconds = [math]::Round($p.CPU, 1)
                Threads = $p.Threads.Count
                Handles = $p.HandleCount
                Responding = $p.Responding
                Priority = $p.PriorityClass.ToString()
                Path = $p.Path
                WindowTitle = $p.MainWindowTitle
                StartTime = if ($p.StartTime) {{ $p.StartTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ $null }}
            }}
        }} else {{
            @{{ Error = "Process {pid} not found" }}
        }}
    """)

    # Get command line via WMI
    cmdline = ps(f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine")

    # Get loaded modules count
    modules = ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Modules.Count")

    if isinstance(info, dict):
        info["CommandLine"] = cmdline
        info["ModuleCount"] = int(modules) if modules else None

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def process_tree():
    """
    Show parent-child process tree. Useful for understanding which process spawned which.
    """
    tree = ps_json("""
        Get-CimInstance Win32_Process | ForEach-Object {
            @{
                Name = $_.Name
                PID = $_.ProcessId
                ParentPID = $_.ParentProcessId
                RAM_KB = [math]::Round($_.WorkingSetSize / 1KB, 0)
                CommandLine = if ($_.CommandLine.Length -gt 120) { $_.CommandLine.Substring(0, 120) + '...' } else { $_.CommandLine }
            }
        }
    """)

    if not tree:
        return json.dumps({"error": "Could not read process tree"})

    procs = tree if isinstance(tree, list) else [tree]

    # Build tree structure
    by_pid = {p["PID"]: p for p in procs if isinstance(p, dict)}
    roots = []
    for p in procs:
        if not isinstance(p, dict):
            continue
        parent = p.get("ParentPID")
        if parent not in by_pid:
            p["children_count"] = sum(1 for c in procs if isinstance(c, dict) and c.get("ParentPID") == p["PID"])
            roots.append(p)

    # Sort by RAM
    roots.sort(key=lambda x: -x.get("RAM_KB", 0))

    return json.dumps({
        "total_processes": len(procs),
        "root_processes": len(roots),
        "top_trees": roots[:20],
    }, indent=2, default=str)


@mcp.tool()
async def memory_leaks(sample_seconds: int = 10):
    """
    Detect processes with growing memory usage by sampling twice.
    Flags processes whose RAM increased between samples.

    Args:
        sample_seconds: Time between samples in seconds (default: 10)
    """
    # Sample 1
    sample1 = ps_json("""
        Get-Process | Where-Object { $_.WorkingSet64 -gt 50MB } |
        ForEach-Object {
            @{ Name = $_.ProcessName; PID = $_.Id; RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0) }
        }
    """)

    if not sample1:
        return json.dumps({"error": "Could not read processes"})

    s1 = {p["PID"]: p for p in (sample1 if isinstance(sample1, list) else [sample1]) if isinstance(p, dict)}

    await asyncio.sleep(sample_seconds)

    # Sample 2
    sample2 = ps_json("""
        Get-Process | Where-Object { $_.WorkingSet64 -gt 50MB } |
        ForEach-Object {
            @{ Name = $_.ProcessName; PID = $_.Id; RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0) }
        }
    """)

    s2 = {p["PID"]: p for p in (sample2 if isinstance(sample2, list) else [sample2]) if isinstance(p, dict)}

    # Compare
    growing = []
    for pid, p2 in s2.items():
        if pid in s1:
            diff = p2["RAM_MB"] - s1[pid]["RAM_MB"]
            if diff > 5:  # >5MB growth
                growing.append({
                    "name": p2["Name"],
                    "pid": pid,
                    "before_mb": s1[pid]["RAM_MB"],
                    "after_mb": p2["RAM_MB"],
                    "growth_mb": diff,
                    "growth_pct": round(diff / max(s1[pid]["RAM_MB"], 1) * 100, 1),
                })

    growing.sort(key=lambda x: -x["growth_mb"])

    return json.dumps({
        "sample_duration_seconds": sample_seconds,
        "growing_processes": growing,
        "total_growing": len(growing),
        "note": "Processes that gained >5MB RAM between samples" if growing else "No significant memory growth detected",
    }, indent=2, default=str)


@mcp.tool()
async def handle_count(limit: int = 20):
    """
    Processes with most open handles — high handle counts can indicate resource leaks.

    Args:
        limit: Number of top processes to show (default: 20)
    """
    procs = ps_json(f"""
        Get-Process | Sort-Object HandleCount -Descending | Select-Object -First {limit} |
        ForEach-Object {{
            @{{
                Name = $_.ProcessName
                PID = $_.Id
                Handles = $_.HandleCount
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                Threads = $_.Threads.Count
            }}
        }}
    """)

    results = procs if isinstance(procs, list) else [procs] if procs else []

    # Flag suspicious handle counts
    warnings = []
    for p in results:
        if isinstance(p, dict) and p.get("Handles", 0) > 10000:
            warnings.append(f"{p['Name']} (PID {p['PID']}) has {p['Handles']} handles — potential leak")

    return json.dumps({
        "processes": results,
        "warnings": warnings,
    }, indent=2, default=str)


@mcp.tool()
async def zombie_processes():
    """
    Find hung/not-responding processes that may need to be killed.
    """
    zombies = ps_json("""
        Get-Process | Where-Object { $_.Responding -eq $false -and $_.MainWindowHandle -ne 0 } |
        ForEach-Object {
            @{
                Name = $_.ProcessName
                PID = $_.Id
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                WindowTitle = $_.MainWindowTitle
                Responding = $_.Responding
                StartTime = if ($_.StartTime) { $_.StartTime.ToString('yyyy-MM-dd HH:mm') } else { $null }
            }
        }
    """)

    results = zombies if isinstance(zombies, list) else [zombies] if zombies else []
    # Filter out nulls
    results = [r for r in results if isinstance(r, dict) and r.get("Name")]

    return json.dumps({
        "hung_processes": results,
        "total": len(results),
        "note": "These processes have windows but are not responding" if results else "All windowed processes are responding",
    }, indent=2, default=str)


@mcp.tool()
async def service_list(filter: str = "running"):
    """
    List Windows services.

    Args:
        filter: 'running', 'stopped', 'auto', or 'all' (default: running)
    """
    if filter == "running":
        where = "Where-Object { $_.Status -eq 'Running' }"
    elif filter == "stopped":
        where = "Where-Object { $_.Status -eq 'Stopped' }"
    elif filter == "auto":
        where = "Where-Object { $_.StartType -eq 'Automatic' }"
    else:
        where = ""

    pipe = f" | {where}" if where else ""

    services = ps_json(f"""
        Get-Service{pipe} | Sort-Object DisplayName |
        ForEach-Object {{
            @{{
                Name = $_.Name
                DisplayName = $_.DisplayName
                Status = $_.Status.ToString()
                StartType = $_.StartType.ToString()
            }}
        }}
    """)

    results = services if isinstance(services, list) else [services] if services else []

    return json.dumps({
        "filter": filter,
        "services": results,
        "total": len(results),
    }, indent=2, default=str)


# ═══════════════════════════════════════════════════════════
#  ACTION TOOLS
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def process_kill(target: str, force: bool = False):
    """
    Kill a process by name or PID. Use with caution!

    Args:
        target: Process name (e.g. 'notepad') or PID (e.g. '12345')
        force: Force kill even if process is busy (default: false)
    """
    PROTECTED = ["System", "csrss", "wininit", "winlogon", "services", "lsass",
                 "smss", "svchost", "explorer", "dwm", "RuntimeBroker"]

    # Check if target is PID or name
    try:
        pid = int(target)
        is_pid = True
    except ValueError:
        pid = None
        is_pid = False

    # Safety check
    if not is_pid and target.lower() in [p.lower() for p in PROTECTED]:
        return json.dumps({"error": f"'{target}' is a protected system process — cannot kill"})

    # Find the process first
    if is_pid:
        info = ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName")
        if not info:
            return json.dumps({"error": f"PID {pid} not found"})
        if info.lower() in [p.lower() for p in PROTECTED]:
            return json.dumps({"error": f"PID {pid} ({info}) is a protected system process"})
        proc_name = info
    else:
        count = ps(f"(Get-Process -Name '{target}' -ErrorAction SilentlyContinue).Count")
        if not count or count == "0":
            return json.dumps({"error": f"No process named '{target}' found"})
        proc_name = target

    # Kill
    force_flag = "-Force" if force else ""
    if is_pid:
        result = ps(f"Stop-Process -Id {pid} {force_flag} -ErrorAction SilentlyContinue -PassThru | Select-Object ProcessName, Id")
    else:
        result = ps(f"Stop-Process -Name '{target}' {force_flag} -ErrorAction SilentlyContinue -PassThru | Select-Object ProcessName, Id")

    # Verify
    await asyncio.sleep(0.5)
    if is_pid:
        still_alive = ps(f"Get-Process -Id {pid} -ErrorAction SilentlyContinue")
    else:
        still_alive = ps(f"Get-Process -Name '{target}' -ErrorAction SilentlyContinue")

    return json.dumps({
        "action": "kill",
        "target": target,
        "process_name": proc_name,
        "force": force,
        "success": not bool(still_alive),
        "note": f"Process '{proc_name}' killed" if not still_alive else f"Process may still be running",
    }, indent=2, default=str)


@mcp.tool()
async def process_priority(pid: int, priority: str):
    """
    Set process priority class.

    Args:
        pid: Process ID
        priority: One of 'realtime', 'high', 'above_normal', 'normal', 'below_normal', 'idle'
    """
    PRIORITY_MAP = {
        "realtime": "RealTime",
        "high": "High",
        "above_normal": "AboveNormal",
        "normal": "Normal",
        "below_normal": "BelowNormal",
        "idle": "Idle",
    }

    if priority.lower() not in PRIORITY_MAP:
        return json.dumps({"error": f"Invalid priority '{priority}'. Use: {', '.join(PRIORITY_MAP.keys())}"})

    ps_priority = PRIORITY_MAP[priority.lower()]

    # Get current info
    before = ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).PriorityClass")
    if not before:
        return json.dumps({"error": f"PID {pid} not found"})

    proc_name = ps(f"(Get-Process -Id {pid}).ProcessName")

    # Set priority
    ps(f"(Get-Process -Id {pid}).PriorityClass = [System.Diagnostics.ProcessPriorityClass]::'{ps_priority}'")

    after = ps(f"(Get-Process -Id {pid}).PriorityClass")

    return json.dumps({
        "action": "set_priority",
        "pid": pid,
        "process": proc_name,
        "before": before,
        "after": after,
        "requested": priority,
        "success": after == ps_priority if after else False,
    }, indent=2, default=str)


@mcp.tool()
async def process_affinity(pid: int, cores: str):
    """
    Set CPU core affinity for a process.

    Args:
        pid: Process ID
        cores: Comma-separated core numbers (e.g. '0,1,2,3') or 'all'
    """
    proc_name = ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName")
    if not proc_name:
        return json.dumps({"error": f"PID {pid} not found"})

    total_cores = ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors")
    total = int(total_cores) if total_cores else 32

    if cores.lower() == "all":
        mask = (1 << total) - 1
    else:
        try:
            core_list = [int(c.strip()) for c in cores.split(",")]
            mask = sum(1 << c for c in core_list if 0 <= c < total)
        except ValueError:
            return json.dumps({"error": f"Invalid cores format: '{cores}'. Use '0,1,2,3' or 'all'"})

    before = ps(f"(Get-Process -Id {pid}).ProcessorAffinity")
    ps(f"(Get-Process -Id {pid}).ProcessorAffinity = {mask}")
    after = ps(f"(Get-Process -Id {pid}).ProcessorAffinity")

    return json.dumps({
        "action": "set_affinity",
        "pid": pid,
        "process": proc_name,
        "cores_requested": cores,
        "mask": mask,
        "before": before,
        "after": after,
        "total_logical_cores": total,
    }, indent=2, default=str)


@mcp.tool()
async def service_control(service_name: str, action: str):
    """
    Start, stop, or restart a Windows service.

    Args:
        service_name: Service name (e.g. 'Spooler', 'wuauserv')
        action: One of 'start', 'stop', 'restart'
    """
    if action not in ("start", "stop", "restart"):
        return json.dumps({"error": f"Invalid action '{action}'. Use: start, stop, restart"})

    # Check service exists
    status_before = ps(f"(Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue).Status")
    if not status_before:
        return json.dumps({"error": f"Service '{service_name}' not found"})

    display_name = ps(f"(Get-Service -Name '{service_name}').DisplayName")

    # Execute action
    if action == "restart":
        ps(f"Restart-Service -Name '{service_name}' -Force -ErrorAction SilentlyContinue")
    elif action == "start":
        ps(f"Start-Service -Name '{service_name}' -ErrorAction SilentlyContinue")
    elif action == "stop":
        ps(f"Stop-Service -Name '{service_name}' -Force -ErrorAction SilentlyContinue")

    await asyncio.sleep(1)
    status_after = ps(f"(Get-Service -Name '{service_name}').Status")

    return json.dumps({
        "action": action,
        "service": service_name,
        "display_name": display_name,
        "status_before": status_before,
        "status_after": status_after,
        "note": "May need admin privileges for some services",
    }, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
