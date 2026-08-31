"""
PC Hardware Monitor — MCP Server
==================================
Real-time hardware monitoring: CPU, RAM, GPU, Disk I/O, Network, Temps.

Tools:
  - system_overview:    Full snapshot: CPU, RAM, GPU, Disk, Network
  - gpu_status:         NVIDIA GPU: VRAM, utilization, temp, power, processes
  - ram_status:         RAM: total/used/free, top consumers, committed memory
  - cpu_status:         CPU: load, cores, top processes, frequency
  - disk_io:            Disk I/O rates per drive (SSD vs HDD)
  - network_status:     Network: connections, bandwidth, DNS
  - process_top:        Top processes by CPU, RAM, or GPU
  - temps:              Temperatures: CPU, GPU, Disk SMART
  - health_check:       Overall system health score with warnings
  - bottleneck:         Detect current performance bottleneck
"""

import asyncio
import json
import os
import sys
import subprocess
import shutil
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "PC Hardware Monitor",
    instructions=(
        "Real-time hardware monitoring for CPU, RAM, GPU (RTX 3060), Disk I/O, Network. "
        "Use 'system_overview' for a full snapshot, 'bottleneck' to find performance issues, "
        "'gpu_status' for NVIDIA details, 'process_top' for resource hogs. "
        "All tools are read-only — they only measure, never modify anything."
    ),
)

HOME = os.path.expanduser("~")
LA = os.environ.get("LOCALAPPDATA", "")


# ── Helpers ─────────────────────────────────────────────────

def ps(cmd, timeout=15):
    """Run PowerShell command and return output via temp script file."""
    import tempfile
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + cmd.strip()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(script)
            script_path = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        try:
            os.unlink(script_path)
        except:
            pass
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()
        return None
    except:
        return None


def ps_json(cmd, timeout=15):
    """Run PowerShell command returning JSON via temp script file."""
    stripped = cmd.strip()
    # Wrap entire script in a ScriptBlock to capture output, then pipe to JSON
    script = f"& {{\n{stripped}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try:
            return json.loads(raw)
        except:
            pass
    return None


def nvidia_smi(query, fmt="csv,noheader,nounits"):
    """Query nvidia-smi."""
    try:
        r = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", f"--format={fmt}"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except:
        pass
    return None


def nvidia_smi_processes():
    """Get GPU process list."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,name,used_gpu_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        if r.returncode == 0 and r.stdout.strip():
            procs = []
            for line in r.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    procs.append({"pid": parts[0], "name": parts[1], "vram_mb": int(parts[2])})
            return procs
    except:
        pass
    return []


# ═══════════════════════════════════════════════════════════
#  TOOLS
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def system_overview():
    """
    Full system snapshot: CPU, RAM, GPU, Disk, Network — all in one call.
    Use this for a quick health overview.
    """
    result = {"timestamp": datetime.now().isoformat()}

    # CPU
    cpu = ps_json("""
        $cpu = Get-CimInstance Win32_Processor
        @{
            Name = $cpu.Name
            Cores = $cpu.NumberOfCores
            Threads = $cpu.NumberOfLogicalProcessors
            Load_Pct = $cpu.LoadPercentage
            MaxClock_MHz = $cpu.MaxClockSpeed
        }
    """)
    result["cpu"] = cpu

    # RAM
    ram = ps_json("""
        $os = Get-CimInstance Win32_OperatingSystem
        $total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        $free = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
        @{
            Total_GB = $total
            Used_GB = [math]::Round($total - $free, 1)
            Free_GB = $free
            Used_Pct = [math]::Round(($total - $free) / $total * 100, 0)
        }
    """)
    result["ram"] = ram

    # GPU (NVIDIA)
    gpu_raw = nvidia_smi("name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit,fan.speed,clocks.gr,clocks.mem")
    if gpu_raw:
        parts = [p.strip() for p in gpu_raw.split(",")]
        if len(parts) >= 12:
            result["gpu"] = {
                "name": parts[0],
                "vram_total_mb": int(parts[1]),
                "vram_used_mb": int(parts[2]),
                "vram_free_mb": int(parts[3]),
                "gpu_util_pct": int(parts[4]),
                "mem_util_pct": int(parts[5]),
                "temp_c": int(parts[6]),
                "power_w": float(parts[7]),
                "power_limit_w": float(parts[8]),
                "fan_pct": parts[9],
                "clock_gpu_mhz": int(parts[10]),
                "clock_mem_mhz": int(parts[11]),
            }
    result["gpu_processes"] = nvidia_smi_processes()

    # Disks
    drives = {}
    for d in ["C:\\", "E:\\"]:
        try:
            u = shutil.disk_usage(d)
            drives[d] = {
                "total_gb": round(u.total / 1024**3, 1),
                "free_gb": round(u.free / 1024**3, 1),
                "used_pct": round(u.used / u.total * 100, 1),
            }
        except:
            pass
    result["drives"] = drives

    # Disk types
    disks = ps_json("Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,@{N='Size_GB';E={[math]::Round($_.Size/1GB)}}")
    result["physical_disks"] = disks

    # Network
    net = ps_json("""
        $adapters = Get-NetAdapter | Where-Object Status -eq Up | Select-Object Name,InterfaceDescription,LinkSpeed,@{N='RxGB';E={[math]::Round($_.ReceivedBytes/1GB,2)}},@{N='TxGB';E={[math]::Round($_.SentBytes/1GB,2)}}
        $adapters
    """)
    result["network"] = net

    # Uptime
    uptime = ps_json("""
        $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
        $up = (Get-Date) - $boot
        @{ Last_Boot = $boot.ToString('yyyy-MM-dd HH:mm'); Uptime = '{0}d {1}h {2}m' -f $up.Days,$up.Hours,$up.Minutes }
    """)
    result["uptime"] = uptime

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def gpu_status():
    """
    Detailed NVIDIA GPU status: VRAM usage, utilization, temperature, power draw,
    clock speeds, fan speed, and which processes are using the GPU.
    """
    result = {}

    # Query each field separately to avoid CSV parsing issues with GPU name containing commas
    queries = {
        "name": "name",
        "driver": "driver_version",
        "vram_total_mb": "memory.total",
        "vram_used_mb": "memory.used",
        "vram_free_mb": "memory.free",
        "gpu_util_pct": "utilization.gpu",
        "mem_util_pct": "utilization.memory",
        "temp_c": "temperature.gpu",
        "power_w": "power.draw",
        "power_limit_w": "power.limit",
        "clock_graphics_mhz": "clocks.gr",
        "clock_memory_mhz": "clocks.mem",
        "fan_pct": "fan.speed",
        "perf_state": "pstate",
    }
    for key, query in queries.items():
        val = nvidia_smi(query)
        if val and val != "[N/A]":
            try:
                if "mb" in key or "mhz" in key: val = int(val)
                elif "pct" in key or "_c" in key: val = int(val)
                elif "_w" in key: val = float(val)
            except: pass
            result[key] = val

    # GPU processes
    result["processes"] = nvidia_smi_processes()

    # VRAM health indicator
    if "vram_used_mb" in result and "vram_total_mb" in result:
        pct = result["vram_used_mb"] / result["vram_total_mb"] * 100
        result["vram_used_pct"] = round(pct, 1)
        if pct > 90: result["vram_status"] = "CRITICAL"
        elif pct > 70: result["vram_status"] = "HIGH"
        else: result["vram_status"] = "OK"

    return json.dumps(result, indent=2)


@mcp.tool()
async def ram_status():
    """
    Detailed RAM status: physical/virtual/committed memory, page file usage,
    and top 15 RAM-consuming processes with their working set sizes.
    """
    info = {}

    mem = ps_json("""
        $os = Get-CimInstance Win32_OperatingSystem
        $perf = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
        $total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        $free = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        @{
            Physical_Total_GB = $total
            Physical_Used_GB = [math]::Round($total - $free, 2)
            Physical_Free_GB = $free
            Physical_Used_Pct = [math]::Round(($total - $free) / $total * 100, 0)
            Committed_Bytes_GB = [math]::Round($perf.CommittedBytes / 1GB, 2)
            Commit_Limit_GB = [math]::Round($perf.CommitLimit / 1GB, 2)
            Cache_GB = [math]::Round($perf.CacheBytes / 1GB, 2)
            Pool_Paged_MB = [math]::Round($perf.PoolPagedBytes / 1MB, 0)
            Pool_NonPaged_MB = [math]::Round($perf.PoolNonpagedBytes / 1MB, 0)
            Page_Faults_Sec = $perf.PageFaultsPersec
            Available_GB = [math]::Round($perf.AvailableMBytes / 1024, 2)
        }
    """)
    info["memory"] = mem

    # Top RAM consumers
    procs = ps_json("""
        Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 |
        ForEach-Object {
            @{
                Name = $_.ProcessName
                PID = $_.Id
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                Private_MB = [math]::Round($_.PrivateMemorySize64 / 1MB, 0)
                Virtual_MB = [math]::Round($_.VirtualMemorySize64 / 1MB, 0)
                Handles = $_.HandleCount
                Threads = $_.Threads.Count
            }
        }
    """)
    info["top_processes"] = procs

    # RAM hardware info
    hw = ps_json("""
        Get-CimInstance Win32_PhysicalMemory | ForEach-Object {
            @{
                Capacity_GB = [math]::Round($_.Capacity / 1GB, 0)
                Speed_MHz = $_.Speed
                Manufacturer = $_.Manufacturer
                FormFactor = $_.FormFactor
            }
        }
    """)
    info["hardware"] = hw

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def cpu_status():
    """
    Detailed CPU status: per-core load, frequency, top CPU-consuming processes,
    and system/user/idle breakdown.
    """
    info = {}

    cpu = ps_json("""
        $p = Get-CimInstance Win32_Processor
        @{
            Name = $p.Name
            Cores = $p.NumberOfCores
            Threads = $p.NumberOfLogicalProcessors
            Load_Pct = $p.LoadPercentage
            CurrentClock_MHz = $p.CurrentClockSpeed
            MaxClock_MHz = $p.MaxClockSpeed
            Architecture = $p.Architecture
            L2Cache_KB = $p.L2CacheSize
            L3Cache_KB = $p.L3CacheSize
        }
    """)
    info["cpu"] = cpu

    # Top CPU processes
    procs = ps_json("""
        Get-Process | Where-Object { $_.CPU -gt 0 } | Sort-Object CPU -Descending | Select-Object -First 15 |
        ForEach-Object {
            @{
                Name = $_.ProcessName
                PID = $_.Id
                CPU_Seconds = [math]::Round($_.CPU, 1)
                RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                Threads = $_.Threads.Count
            }
        }
    """)
    info["top_processes"] = procs

    # System uptime + context switches
    perf = ps_json("""
        $sys = Get-CimInstance Win32_PerfFormattedData_PerfOS_System
        @{
            Context_Switches_Sec = $sys.ContextSwitchesPersec
            Processes = $sys.Processes
            Threads = $sys.Threads
            System_Calls_Sec = $sys.SystemCallsPersec
        }
    """)
    info["system_perf"] = perf

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def disk_io():
    """
    Disk I/O rates per physical disk: read/write bytes per second,
    queue length, response time. Compares SSD vs HDD performance.
    """
    io = ps_json("""
        Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk |
        Where-Object { $_.Name -ne '_Total' } |
        ForEach-Object {
            @{
                Disk = $_.Name
                Read_MBps = [math]::Round($_.DiskReadBytesPersec / 1MB, 2)
                Write_MBps = [math]::Round($_.DiskWriteBytesPersec / 1MB, 2)
                Busy_Pct = $_.PercentDiskTime
                Queue = $_.CurrentDiskQueueLength
                Avg_Read_ms = [math]::Round($_.AvgDisksecPerRead * 1000, 2)
                Avg_Write_ms = [math]::Round($_.AvgDisksecPerWrite * 1000, 2)
                IOPS_Read = $_.DiskReadsPersec
                IOPS_Write = $_.DiskWritesPersec
            }
        }
    """)

    drives = {}
    for d in ["C:\\", "E:\\"]:
        try:
            u = shutil.disk_usage(d)
            drives[d] = {"free_gb": round(u.free / 1024**3, 1), "used_pct": round(u.used / u.total * 100, 1)}
        except: pass

    return json.dumps({
        "io_stats": io,
        "drives": drives,
        "note": "C: = Samsung SSD 870 EVO (SATA, ~550MB/s), E: = Toshiba HDD (SATA, ~150MB/s)"
    }, indent=2, default=str)


@mcp.tool()
async def network_status():
    """Network status: active adapters, bandwidth, open connections, DNS cache stats."""
    info = {}

    adapters = ps_json("""
        Get-NetAdapter | Where-Object Status -eq Up |
        ForEach-Object {
            @{
                Name = $_.Name
                Description = $_.InterfaceDescription
                Speed = $_.LinkSpeed
                MAC = $_.MacAddress
                Status = $_.Status
            }
        }
    """)
    info["adapters"] = adapters

    # Connection stats
    conn = ps_json("""
        $tcp = Get-NetTCPConnection | Group-Object State | ForEach-Object {
            @{ State = $_.Name; Count = $_.Count }
        }
        $tcp
    """)
    info["tcp_connections"] = conn

    # Top connections by remote
    top_conn = ps_json("""
        Get-NetTCPConnection -State Established |
        Group-Object RemoteAddress | Sort-Object Count -Descending | Select-Object -First 10 |
        ForEach-Object { @{ RemoteIP = $_.Name; Connections = $_.Count } }
    """)
    info["top_remote_ips"] = top_conn

    # Network throughput
    throughput = ps_json("""
        Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface |
        Where-Object { $_.BytesReceivedPersec -gt 0 -or $_.BytesSentPersec -gt 0 } |
        ForEach-Object {
            @{
                Interface = $_.Name
                Recv_KBps = [math]::Round($_.BytesReceivedPersec / 1KB, 1)
                Sent_KBps = [math]::Round($_.BytesSentPersec / 1KB, 1)
                Bandwidth_Mbps = [math]::Round($_.CurrentBandwidth / 1MB, 0)
            }
        }
    """)
    info["throughput"] = throughput

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def process_top(sort_by: str = "ram"):
    """
    Top processes sorted by resource usage.

    Args:
        sort_by: Sort by 'ram', 'cpu', or 'gpu' (default: ram)
    """
    result = {}

    if sort_by == "gpu":
        result["gpu_processes"] = nvidia_smi_processes()
    else:
        sort_prop = "WorkingSet64" if sort_by == "ram" else "CPU"
        procs = ps_json(f"""
            Get-Process | Where-Object {{ $_.{sort_prop} -gt 0 }} |
            Sort-Object {sort_prop} -Descending | Select-Object -First 20 |
            ForEach-Object {{
                @{{
                    Name = $_.ProcessName
                    PID = $_.Id
                    RAM_MB = [math]::Round($_.WorkingSet64 / 1MB, 0)
                    CPU_Seconds = [math]::Round($_.CPU, 1)
                    Threads = $_.Threads.Count
                    Handles = $_.HandleCount
                }}
            }}
        """)
        result["processes"] = procs
        result["sorted_by"] = sort_by

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def temps():
    """
    Temperature readings: GPU temp (via nvidia-smi), disk SMART health status.
    Note: CPU temp requires admin/third-party tools on most Windows systems.
    """
    info = {}

    # GPU temp
    gpu_raw = nvidia_smi("temperature.gpu,temperature.gpu_tlimit,fan.speed,power.draw")
    if gpu_raw:
        parts = [p.strip() for p in gpu_raw.split(",")]
        if len(parts) >= 4:
            info["gpu"] = {
                "temp_c": int(parts[0]),
                "throttle_temp_c": int(parts[1]) if parts[1] != "N/A" else None,
                "fan_pct": parts[2],
                "power_w": float(parts[3]),
            }

    # Disk SMART
    disks = ps_json("""
        Get-PhysicalDisk | ForEach-Object {
            @{
                Name = $_.FriendlyName
                Type = $_.MediaType.ToString()
                Health = $_.HealthStatus.ToString()
                Operational = $_.OperationalStatus.ToString()
                Size_GB = [math]::Round($_.Size / 1GB, 0)
                Wear = if ($_.Wear) { $_.Wear } else { 'N/A' }
            }
        }
    """)
    info["disks"] = disks

    # CPU temp (best effort — often requires admin)
    info["cpu_temp_note"] = "CPU temp requires admin privileges or tools like HWiNFO/OpenHardwareMonitor"

    return json.dumps(info, indent=2, default=str)


@mcp.tool()
async def health_check():
    """
    Overall system health score (0-100) with specific warnings.
    Checks: CPU load, RAM pressure, GPU temp, disk space, disk health.
    """
    score = 100
    warnings = []
    status = {}

    # CPU
    cpu_load = ps("(Get-CimInstance Win32_Processor).LoadPercentage")
    if cpu_load:
        cpu_pct = int(cpu_load)
        status["cpu_load_pct"] = cpu_pct
        if cpu_pct > 90:
            score -= 20; warnings.append(f"CPU at {cpu_pct}% — heavy load")
        elif cpu_pct > 70:
            score -= 10; warnings.append(f"CPU at {cpu_pct}% — moderate load")

    # RAM
    ram_info = ps_json("""
        $os = Get-CimInstance Win32_OperatingSystem
        $total = $os.TotalVisibleMemorySize / 1MB
        $free = $os.FreePhysicalMemory / 1MB
        @{ used_pct = [math]::Round(($total - $free) / $total * 100, 0); free_gb = [math]::Round($free, 1) }
    """)
    if ram_info:
        status["ram"] = ram_info
        if ram_info["used_pct"] > 95:
            score -= 25; warnings.append(f"RAM critical: {ram_info['used_pct']}% used, only {ram_info['free_gb']} GB free")
        elif ram_info["used_pct"] > 85:
            score -= 10; warnings.append(f"RAM high: {ram_info['used_pct']}%")

    # GPU
    gpu_raw = nvidia_smi("temperature.gpu,utilization.gpu,memory.used,memory.total")
    if gpu_raw:
        parts = [p.strip() for p in gpu_raw.split(",")]
        if len(parts) >= 4:
            temp = int(parts[0])
            gpu_util = int(parts[1])
            vram_pct = int(parts[2]) / int(parts[3]) * 100
            status["gpu"] = {"temp_c": temp, "util_pct": gpu_util, "vram_pct": round(vram_pct, 1)}
            if temp > 85:
                score -= 20; warnings.append(f"GPU temp critical: {temp}C")
            elif temp > 75:
                score -= 5; warnings.append(f"GPU temp elevated: {temp}C")
            if vram_pct > 95:
                score -= 15; warnings.append(f"VRAM nearly full: {vram_pct:.0f}%")

    # Disk space
    for d in ["C:\\", "E:\\"]:
        try:
            u = shutil.disk_usage(d)
            pct = u.used / u.total * 100
            free_gb = u.free / 1024**3
            status[f"disk_{d[0]}"] = {"used_pct": round(pct, 1), "free_gb": round(free_gb, 1)}
            if pct > 95:
                score -= 20; warnings.append(f"{d} critical: {pct:.0f}% full, {free_gb:.1f} GB free")
            elif pct > 90:
                score -= 10; warnings.append(f"{d} high: {pct:.0f}% full")
        except:
            pass

    # Disk health
    disk_health = ps_json("Get-PhysicalDisk | Select-Object FriendlyName,HealthStatus")
    if disk_health:
        disks = disk_health if isinstance(disk_health, list) else [disk_health]
        for disk in disks:
            if isinstance(disk, dict) and disk.get("HealthStatus") != "Healthy":
                score -= 30; warnings.append(f"Disk {disk['FriendlyName']}: {disk['HealthStatus']}")

    health = "EXCELLENT" if score >= 90 else "GOOD" if score >= 70 else "WARNING" if score >= 50 else "CRITICAL"

    return json.dumps({
        "health_score": max(0, score),
        "health_status": health,
        "warnings": warnings,
        "details": status,
    }, indent=2, default=str)


@mcp.tool()
async def bottleneck():
    """
    Detect the current system bottleneck: CPU, RAM, GPU, Disk I/O, or Network.
    Returns what's limiting performance right now with specific details.
    """
    scores = {}

    # CPU
    cpu_load = ps("(Get-CimInstance Win32_Processor).LoadPercentage")
    scores["cpu"] = {"load_pct": int(cpu_load) if cpu_load else 0}

    # RAM
    ram = ps_json("""
        $os = Get-CimInstance Win32_OperatingSystem
        @{ used_pct = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 0) }
    """)
    scores["ram"] = {"used_pct": ram["used_pct"] if ram else 0}

    # GPU
    gpu_raw = nvidia_smi("utilization.gpu,memory.used,memory.total")
    if gpu_raw:
        parts = [p.strip() for p in gpu_raw.split(",")]
        if len(parts) >= 3:
            scores["gpu"] = {"util_pct": int(parts[0]), "vram_pct": round(int(parts[1]) / int(parts[2]) * 100, 1)}

    # Disk
    disk_busy = ps("(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object {$_.Name -eq '0 C:'}).PercentDiskTime")
    scores["disk"] = {"busy_pct": int(disk_busy) if disk_busy else 0}

    # Find bottleneck
    pressures = {
        "CPU": scores.get("cpu", {}).get("load_pct", 0),
        "RAM": scores.get("ram", {}).get("used_pct", 0),
        "GPU": scores.get("gpu", {}).get("util_pct", 0),
        "Disk": scores.get("disk", {}).get("busy_pct", 0),
    }

    bottleneck_name = max(pressures, key=pressures.get)
    bottleneck_val = pressures[bottleneck_name]

    if bottleneck_val < 30:
        assessment = "System is idle — no bottleneck detected"
    elif bottleneck_val < 60:
        assessment = f"Light load — {bottleneck_name} is most active at {bottleneck_val}%"
    elif bottleneck_val < 85:
        assessment = f"Moderate load — {bottleneck_name} at {bottleneck_val}%"
    else:
        assessment = f"BOTTLENECK: {bottleneck_name} at {bottleneck_val}% — this is limiting performance"

    return json.dumps({
        "bottleneck": bottleneck_name,
        "assessment": assessment,
        "pressures": pressures,
        "details": scores,
    }, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
