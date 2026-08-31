"""
PC Storage Manager — MCP Server
=================================
Exposes all storage management tools as MCP tools for Claude Code.
Each tool call goes through Claude's permission system — the user
approves/denies every action directly in the chat.

Tools (Read-Only / Safe):
  - storage_status:     Drive status + quick overview
  - storage_doctor:     Full health check + recommendations
  - scan_caches:        Show all cleanable caches with sizes
  - scan_projects:      Project activity report (active/idle/archiv)
  - scan_disk:          Full C: breakdown by folder
  - find_duplicates:    Find duplicate files by hash
  - find_big_files:     Largest individual files on C:
  - docker_analyze:     Docker disk usage analysis
  - git_analyze:        Git repo sizes (.git folders)
  - python_versions:    Pyenv installed versions + usage
  - win_system_info:    Windows system files (pagefile, hiberfil, updates)
  - startup_info:       Autostart programs + top RAM processes
  - wsl_info:           WSL2 vhdx sizes
  - perf_check:         CPU/RAM/Disk performance snapshot
  - storage_history:    Trend over time

Tools (Actions — user approves each one):
  - clean_caches:       Delete safe caches (Temp, pip, npm...)
  - deep_clean:         Aggressive cache cleanup (uv, playwright...)
  - archive_project:    Move specific idle project to E: with junction
  - delete_dependency:  Delete venv/node_modules in idle project
  - git_gc_all:         Run git gc on all repos
  - install_watchdog:   Install scheduled task (every 2h)
"""

import asyncio
import json
import os
import sys
import stat
import shutil
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Reuse logic from storage manager
sys.path.insert(0, str(Path(__file__).parent))

mcp = FastMCP(
    "PC Storage Manager",
    instructions=(
        "PC storage optimization and monitoring tools. "
        "Use 'storage_status' for a quick overview, 'storage_doctor' for full analysis. "
        "Read-only tools are safe to run anytime. "
        "Action tools (clean, archive, delete) will ask user for permission. "
        "IMPORTANT: Docker, .ollama, .pyenv, IDEs stay on SSD (C:). "
        "Only idle projects (>90 days) go to HDD (E:)."
    ),
)

# ── Config ──────────────────────────────────────────────────

HOME = os.path.expanduser("~")
DESKTOP = os.path.join(HOME, "Desktop")
LA = os.environ.get("LOCALAPPDATA", "")
RA = os.environ.get("APPDATA", "")
DATA_DIR = os.path.join(HOME, ".pc_storage_manager")
HISTORY_FILE = os.path.join(DATA_DIR, "history.jsonl")
E_PROJECTS = "E:\\Projects"

RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

SAFE_CACHES = [
    (os.path.join(LA, "Temp"), "User Temp"),
    (os.path.join(LA, "pip", "cache"), "pip Cache"),
    (os.path.join(LA, "npm-cache"), "npm Cache"),
    (os.path.join(LA, "pnpm", "store"), "pnpm Store"),
    (os.path.join(LA, "yarn", "Cache"), "Yarn Cache"),
    (os.path.join(LA, "NuGet", "Cache"), "NuGet Cache"),
    (os.path.join(HOME, ".cache"), ".cache"),
    (os.path.join(HOME, ".pyenv", "pyenv-win", "install_cache"), "pyenv Install Cache"),
    (os.path.join(LA, "CrashDumps"), "Crash Dumps"),
    (os.path.join(LA, "Microsoft", "Windows", "Explorer"), "Thumbnail Cache"),
    (os.path.join(LA, "Microsoft", "Windows", "INetCache"), "IE/Edge Cache"),
]

DEEP_CACHES = [
    (os.path.join(LA, "uv", "cache"), "uv Cache"),
    (os.path.join(LA, "SquirrelTemp"), "SquirrelTemp"),
    (os.path.join(LA, "pypoetry", "Cache"), "pypoetry Cache"),
    (os.path.join(LA, "electron", "Cache"), "electron Cache"),
    (os.path.join(LA, "Docker Desktop Installer"), "Docker Installer"),
    (os.path.join(LA, "llama_index"), "llama_index Cache"),
    (os.path.join(HOME, ".chromium-browser-snapshots"), "Chromium Snapshots"),
    (os.path.join(LA, "claude-cli-nodejs"), "Claude CLI Cache"),
]

SSD_ONLY = ["Docker", ".docker", ".ollama", ".pyenv", ".vscode", ".cursor", ".rustup", ".cargo"]


# ── Helpers ─────────────────────────────────────────────────

def fmt(b):
    if b > 1024**3: return f"{b / 1024**3:.1f} GB"
    if b > 1024**2: return f"{b / 1024**2:.0f} MB"
    return f"{b / 1024:.0f} KB"


def dir_size(path):
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try: total += os.path.getsize(os.path.join(root, f))
                except: pass
    except: pass
    return total


def force_rmtree(path):
    def on_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            func(fpath)
        except: pass
    shutil.rmtree(path, onerror=on_error)


def is_reserved(name):
    return name.split(".")[0].lower() in RESERVED_NAMES


def save_snapshot(drives, freed, action):
    os.makedirs(DATA_DIR, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "drives": drives,
        "freed_mb": round(freed / 1024**2),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_drives():
    result = {}
    for d in ["C:\\", "E:\\"]:
        try:
            u = shutil.disk_usage(d)
            result[d] = {
                "total_gb": round(u.total / 1024**3, 1),
                "used_gb": round(u.used / 1024**3, 1),
                "free_gb": round(u.free / 1024**3, 1),
                "used_pct": round(u.used / u.total * 100, 1),
            }
        except: pass
    return result


def get_project_activity(path):
    if os.path.exists(os.path.join(path, ".git")):
        try:
            r = subprocess.run(
                ["git", "-C", path, "log", "-1", "--format=%aI"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace"
            )
            if r.returncode == 0 and r.stdout and r.stdout.strip():
                return datetime.fromisoformat(r.stdout.strip()), "git"
        except: pass

    newest = 0
    try:
        for root, dirs, files in os.walk(path):
            bn = os.path.basename(root)
            if bn in ("node_modules", ".git", "__pycache__", "venv", ".venv"):
                dirs.clear()
                continue
            for f in files:
                try:
                    mt = os.stat(os.path.join(root, f)).st_mtime
                    if mt > newest: newest = mt
                except: pass
    except: pass
    if newest > 0:
        return datetime.fromtimestamp(newest), "file"
    return None, None


# ═══════════════════════════════════════════════════════════
#  READ-ONLY TOOLS
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def storage_status():
    """Quick drive status overview. Shows C: and E: usage, free space, and health indicator."""
    drives = get_drives()
    c = drives.get("C:\\", {})
    e = drives.get("E:\\", {})

    status = "OK"
    if c.get("used_pct", 0) >= 93: status = "CRITICAL"
    elif c.get("used_pct", 0) >= 85: status = "WARNING"

    return json.dumps({
        "status": status,
        "drives": drives,
        "note": "C: = Samsung SSD 870 EVO 1TB, E: = Toshiba HDD 2TB"
    }, indent=2)


@mcp.tool()
async def storage_doctor():
    """
    Full health check: drives, caches, idle projects, bloated deps, system files, Docker.
    Returns comprehensive analysis with specific recommendations and estimated GB savings.
    """
    drives = get_drives()

    # Caches
    caches = []
    for cache_list in [SAFE_CACHES, DEEP_CACHES]:
        for path, name in cache_list:
            if os.path.exists(path):
                size = dir_size(path)
                if size > 1024 * 1024:
                    caches.append({"name": name, "size": fmt(size), "bytes": size})
    caches.sort(key=lambda x: -x["bytes"])
    total_cache = sum(c["bytes"] for c in caches)

    # Projects
    idle_projects = []
    bloated_deps = []
    for item in sorted(os.listdir(DESKTOP)):
        fp = os.path.join(DESKTOP, item)
        if not os.path.isdir(fp) or item.startswith(".") or item.startswith("$"):
            continue
        size = dir_size(fp)
        if size < 50 * 1024 * 1024: continue

        last, src = get_project_activity(fp)
        days = (datetime.now() - last.replace(tzinfo=None)).days if last else None

        if days and days > 90 and not os.path.islink(fp):
            idle_projects.append({
                "name": item, "size": fmt(size), "bytes": size,
                "days_idle": days, "is_junction": os.path.islink(fp),
            })

        if days and days > 60:
            for dep in ["venv", ".venv", "node_modules"]:
                dp = os.path.join(fp, dep)
                if os.path.exists(dp):
                    ds = dir_size(dp)
                    if ds > 100 * 1024 * 1024:
                        bloated_deps.append({
                            "project": item, "dep": dep,
                            "size": fmt(ds), "bytes": ds, "days_idle": days,
                        })

    total_idle = sum(p["bytes"] for p in idle_projects)
    total_deps = sum(d["bytes"] for d in bloated_deps)

    # System files
    sys_files = {}
    for name, path in [("pagefile", "C:\\pagefile.sys"), ("hiberfil", "C:\\hiberfil.sys")]:
        try:
            if os.path.exists(path):
                sys_files[name] = fmt(os.path.getsize(path))
        except: pass
    wbt = "C:\\$Windows.~BT"
    if os.path.exists(wbt):
        sys_files["windows_old_update"] = fmt(dir_size(wbt))

    # Docker
    docker_size = 0
    dw = os.path.join(LA, "Docker", "wsl")
    if os.path.exists(dw):
        docker_size = dir_size(dw)

    recommendations = []
    if total_cache > 500 * 1024**2:
        recommendations.append(f"Clean caches: {fmt(total_cache)} — use clean_caches or deep_clean tool")
    if idle_projects:
        recommendations.append(f"Archive {len(idle_projects)} idle projects: {fmt(total_idle)} — use archive_project tool")
    if bloated_deps:
        recommendations.append(f"Delete deps in idle projects: {fmt(total_deps)} — use delete_dependency tool")
    if os.path.exists(wbt):
        recommendations.append("Run Windows Disk Cleanup to remove $Windows.~BT")

    save_snapshot(drives, 0, "doctor")

    return json.dumps({
        "drives": drives,
        "caches": {"items": caches[:15], "total": fmt(total_cache)},
        "idle_projects": idle_projects,
        "bloated_deps": bloated_deps,
        "system_files": sys_files,
        "docker_gb": f"{docker_size / 1024**3:.1f} GB (stays on SSD)",
        "recommendations": recommendations,
        "total_potential_gb": round((total_cache + total_idle + total_deps) / 1024**3, 1),
    }, indent=2)


@mcp.tool()
async def scan_caches(include_deep: bool = True):
    """
    List all cleanable cache directories with their sizes.

    Args:
        include_deep: Include aggressive caches like uv, electron, playwright (default true)
    """
    result = []
    cache_list = SAFE_CACHES + (DEEP_CACHES if include_deep else [])
    for path, name in cache_list:
        if os.path.exists(path):
            size = dir_size(path)
            if size > 1024 * 1024:
                result.append({"name": name, "path": path, "size": fmt(size), "bytes": size})
    result.sort(key=lambda x: -x["bytes"])
    total = sum(r["bytes"] for r in result)
    return json.dumps({"caches": result, "total": fmt(total), "total_bytes": total}, indent=2)


@mcp.tool()
async def scan_projects():
    """Scan Desktop projects: activity dates, sizes, categories (AKTIV/RECENT/IDLE/ARCHIV)."""
    projects = []
    for item in sorted(os.listdir(DESKTOP)):
        fp = os.path.join(DESKTOP, item)
        if not os.path.isdir(fp) or item.startswith(".") or item.startswith("$"):
            continue
        size = dir_size(fp)
        if size < 50 * 1024 * 1024: continue

        last, src = get_project_activity(fp)
        days = (datetime.now() - last.replace(tzinfo=None)).days if last else None

        if days is None: cat = "UNKNOWN"
        elif days <= 7: cat = "ACTIVE"
        elif days <= 30: cat = "RECENT"
        elif days <= 90: cat = "IDLE"
        else: cat = "ARCHIVE"

        deps = []
        for dep in ["venv", ".venv", "node_modules"]:
            dp = os.path.join(fp, dep)
            if os.path.exists(dp):
                ds = dir_size(dp)
                if ds > 100 * 1024 * 1024:
                    deps.append({"name": dep, "size": fmt(ds)})

        projects.append({
            "name": item, "size": fmt(size), "bytes": size,
            "days_idle": days, "category": cat,
            "last_activity": last.strftime("%Y-%m-%d") if last else None,
            "source": src, "is_junction": os.path.islink(fp),
            "deps": deps,
        })

    projects.sort(key=lambda x: (
        {"ACTIVE": 0, "RECENT": 1, "IDLE": 2, "ARCHIVE": 3}.get(x["category"], 4),
        -x["bytes"]
    ))
    return json.dumps({"projects": projects, "total": len(projects)}, indent=2)


@mcp.tool()
async def find_duplicates():
    """Find duplicate files (>1MB) by size + partial hash across Desktop and Downloads."""
    scan_dirs = [DESKTOP, os.path.join(HOME, "Downloads"), os.path.join(HOME, "Documents")]
    size_groups = {}

    for sd in scan_dirs:
        if not os.path.exists(sd): continue
        for root, dirs, files in os.walk(sd):
            bn = os.path.basename(root)
            if bn in ("node_modules", ".git", "__pycache__", "venv", ".venv", ".cache"):
                dirs.clear()
                continue
            for f in files:
                fp = os.path.join(root, f)
                try:
                    size = os.path.getsize(fp)
                    if size > 1024 * 1024:
                        size_groups.setdefault(size, []).append(fp)
                except: pass

    duplicates = []
    for size, paths in sorted(size_groups.items(), reverse=True):
        if len(paths) < 2: continue
        hashes = {}
        for p in paths:
            try:
                h = hashlib.md5()
                with open(p, "rb") as f: h.update(f.read(65536))
                hashes.setdefault(h.hexdigest(), []).append(p)
            except: pass
        for h, group in hashes.items():
            if len(group) > 1:
                duplicates.append({
                    "size": fmt(size), "bytes": size,
                    "copies": len(group), "wasted": fmt(size * (len(group) - 1)),
                    "files": group,
                })

    total_waste = sum(d["bytes"] * (d["copies"] - 1) for d in duplicates)
    return json.dumps({
        "duplicates": duplicates[:30],
        "total_groups": len(duplicates),
        "total_wasted": fmt(total_waste),
    }, indent=2)


@mcp.tool()
async def find_big_files():
    """Find the largest individual files (>100MB) in user profile."""
    big = []
    for root, dirs, files in os.walk(HOME):
        bn = os.path.basename(root)
        if bn in ("node_modules", ".git", "wsl"):
            dirs.clear()
            continue
        for f in files:
            fp = os.path.join(root, f)
            try:
                size = os.path.getsize(fp)
                if size > 100 * 1024 * 1024:
                    big.append({"path": fp, "size": fmt(size), "bytes": size, "ext": os.path.splitext(f)[1].lower()})
            except: pass

    big.sort(key=lambda x: -x["bytes"])
    return json.dumps({"files": big[:30], "total": len(big)}, indent=2)


@mcp.tool()
async def docker_analyze():
    """Analyze Docker disk usage: images, containers, volumes, build cache."""
    results = {}
    for cmd_name, cmd in [
        ("system_df", ["docker", "system", "df"]),
        ("images", ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"]),
        ("stopped", ["docker", "ps", "-a", "-f", "status=exited", "--format", "{{.Names}}\t{{.Image}}\t{{.Size}}"]),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
            results[cmd_name] = r.stdout.strip() if r.returncode == 0 else f"Error: {r.stderr.strip()}"
        except Exception as e:
            results[cmd_name] = f"Error: {e}"

    docker_wsl = os.path.join(LA, "Docker", "wsl")
    if os.path.exists(docker_wsl):
        results["wsl_size"] = fmt(dir_size(docker_wsl))

    results["note"] = "Docker stays on SSD for performance. Use 'docker system prune -a' to clean unused images."
    return json.dumps(results, indent=2)


@mcp.tool()
async def python_versions():
    """List installed pyenv Python versions, their sizes, and which are used in projects."""
    pyenv_dir = os.path.join(HOME, ".pyenv", "pyenv-win", "versions")
    if not os.path.exists(pyenv_dir):
        return json.dumps({"error": "pyenv not found"})

    versions = []
    for item in os.listdir(pyenv_dir):
        fp = os.path.join(pyenv_dir, item)
        if os.path.isdir(fp):
            versions.append({"version": item, "size": fmt(dir_size(fp))})

    used = {}
    for sd in [DESKTOP, E_PROJECTS]:
        if not os.path.exists(sd): continue
        for item in os.listdir(sd):
            pv = os.path.join(sd, item, ".python-version")
            if os.path.exists(pv):
                try:
                    with open(pv) as f: used[f.read().strip()] = item
                except: pass

    return json.dumps({"versions": versions, "used_in_projects": used, "total_size": fmt(dir_size(pyenv_dir))}, indent=2)


@mcp.tool()
async def win_system_info():
    """Show Windows system files (pagefile, hiberfil, $Windows.~BT) and cleanup options."""
    info = {}
    for name, path in [("pagefile_sys", "C:\\pagefile.sys"), ("hiberfil_sys", "C:\\hiberfil.sys")]:
        try:
            if os.path.exists(path): info[name] = fmt(os.path.getsize(path))
        except: pass

    wbt = "C:\\$Windows.~BT"
    if os.path.exists(wbt): info["windows_old_update"] = fmt(dir_size(wbt))

    info["recommendations"] = [
        "cleanmgr /d C: — removes $Windows.~BT via Disk Cleanup",
        "powercfg /h off — disables hibernate (removes hiberfil.sys)",
        "System > Advanced > Virtual Memory — reduce pagefile to 8-16 GB",
        "dism /Online /Cleanup-Image /StartComponentCleanup — as Admin",
    ]
    return json.dumps(info, indent=2)


@mcp.tool()
async def startup_info():
    """Show autostart programs and top 10 RAM-consuming processes."""
    result = {}
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 | ForEach-Object { @{Name=$_.ProcessName; RAM_MB=[math]::Round($_.WorkingSet64/1MB)} } | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0: result["top_ram_processes"] = json.loads(r.stdout)
    except: pass

    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_OperatingSystem | ForEach-Object { @{TotalRAM_GB=[math]::Round($_.TotalVisibleMemorySize/1MB,1); FreeRAM_GB=[math]::Round($_.FreePhysicalMemory/1MB,1)} } | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0: result["ram_info"] = json.loads(r.stdout)
    except: pass

    return json.dumps(result, indent=2)


@mcp.tool()
async def perf_check():
    """Quick system performance snapshot: CPU, RAM, disk health, uptime."""
    info = {}
    try:
        r = subprocess.run(
            ["powershell", "-Command", """
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor).LoadPercentage
$boot = $os.LastBootUpTime
@{
    CPU_Percent = $cpu
    RAM_Total_GB = [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
    RAM_Free_GB = [math]::Round($os.FreePhysicalMemory/1MB, 1)
    RAM_Used_Pct = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100, 0)
    Uptime_Days = ((Get-Date) - $boot).Days
    Last_Boot = $boot.ToString('yyyy-MM-dd HH:mm')
} | ConvertTo-Json"""],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0: info["system"] = json.loads(r.stdout)
    except: pass

    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0: info["disks"] = json.loads(r.stdout)
    except: pass

    info["drives"] = get_drives()
    return json.dumps(info, indent=2)


@mcp.tool()
async def storage_history():
    """Show storage trend history (last 30 snapshots)."""
    if not os.path.exists(HISTORY_FILE):
        return json.dumps({"error": "No history yet. Run storage_doctor first."})

    entries = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: entries.append(json.loads(line.strip()))
                except: pass

    return json.dumps({"entries": entries[-30:], "total_entries": len(entries)}, indent=2)


@mcp.tool()
async def wsl_info():
    """Show WSL2 vhdx virtual disk sizes and compaction instructions."""
    vhdx = []
    for d in [os.path.join(LA, "Docker", "wsl"), os.path.join(LA, "Packages")]:
        if not os.path.exists(d): continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".vhdx"):
                    fp = os.path.join(root, f)
                    try: vhdx.append({"path": fp, "size": fmt(os.path.getsize(fp))})
                    except: pass

    return json.dumps({
        "vhdx_files": vhdx,
        "compact_instructions": [
            "wsl --shutdown",
            "diskpart > select vdisk file=<path> > compact vdisk",
            "Or: Optimize-VHD -Path <path> -Mode Full (Hyper-V PowerShell, as Admin)"
        ]
    }, indent=2)


@mcp.tool()
async def git_analyze():
    """Analyze .git folder sizes across all repos on Desktop and E:\\Projects."""
    repos = []
    for base in [DESKTOP, E_PROJECTS]:
        if not os.path.exists(base): continue
        for item in os.listdir(base):
            git_dir = os.path.join(base, item, ".git")
            if os.path.exists(git_dir):
                size = dir_size(git_dir)
                if size > 10 * 1024 * 1024:
                    repos.append({"repo": item, "git_size": fmt(size), "bytes": size, "location": base})
    repos.sort(key=lambda x: -x["bytes"])
    return json.dumps({"repos": repos, "total": fmt(sum(r["bytes"] for r in repos))}, indent=2)


# ═══════════════════════════════════════════════════════════
#  ACTION TOOLS (modify filesystem — user approves each)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def clean_caches():
    """
    Delete safe cache directories: User Temp, pip, npm, pnpm, yarn, CrashDumps, Thumbnails.
    Does NOT touch Chrome (may be running) or deep caches (uv, playwright).
    Returns total bytes freed.
    """
    total = 0
    results = []
    for path, name in SAFE_CACHES:
        if not os.path.exists(path): continue
        freed = 0
        errors = 0
        try:
            for item in os.listdir(path):
                fp = os.path.join(path, item)
                try:
                    if os.path.isfile(fp) or os.path.islink(fp):
                        s = os.path.getsize(fp)
                        os.chmod(fp, stat.S_IWRITE)
                        os.remove(fp)
                        freed += s
                    elif os.path.isdir(fp):
                        s = dir_size(fp)
                        force_rmtree(fp)
                        freed += s
                except: errors += 1
        except: errors += 1
        if freed > 0:
            results.append({"name": name, "freed": fmt(freed), "errors": errors})
        total += freed

    save_snapshot(get_drives(), total, "clean")
    return json.dumps({"cleaned": results, "total_freed": fmt(total)}, indent=2)


@mcp.tool()
async def deep_clean():
    """
    Aggressive cache cleanup: everything in clean_caches PLUS uv cache, SquirrelTemp,
    pypoetry, electron, llama_index, Chromium snapshots, Docker installer.
    Returns total bytes freed.
    """
    total = 0
    results = []
    for path, name in SAFE_CACHES + DEEP_CACHES:
        if not os.path.exists(path): continue
        freed = 0
        errors = 0
        try:
            for item in os.listdir(path):
                fp = os.path.join(path, item)
                try:
                    if os.path.isfile(fp) or os.path.islink(fp):
                        s = os.path.getsize(fp)
                        os.chmod(fp, stat.S_IWRITE)
                        os.remove(fp)
                        freed += s
                    elif os.path.isdir(fp):
                        s = dir_size(fp)
                        force_rmtree(fp)
                        freed += s
                except: errors += 1
        except: errors += 1
        if freed > 0:
            results.append({"name": name, "freed": fmt(freed), "errors": errors})
        total += freed

    save_snapshot(get_drives(), total, "deep-clean")
    return json.dumps({"cleaned": results, "total_freed": fmt(total)}, indent=2)


@mcp.tool()
async def archive_project(project_name: str):
    """
    Move a specific project from Desktop to E:\\Projects with a junction link back.
    The project will still appear on Desktop but data lives on HDD.
    Only use for idle/archive projects (>90 days inactive).

    Args:
        project_name: Name of the folder on Desktop to archive
    """
    src = os.path.join(DESKTOP, project_name)
    dst = os.path.join(E_PROJECTS, project_name)

    if not os.path.exists(src):
        return json.dumps({"error": f"'{project_name}' not found on Desktop"})
    if os.path.islink(src):
        return json.dumps({"error": f"'{project_name}' is already a junction (already on E:)"})
    if os.path.exists(dst):
        return json.dumps({"error": f"'{project_name}' already exists in E:\\Projects"})

    # Safety: check SSD-only rule
    if any(s in project_name for s in SSD_ONLY):
        return json.dumps({"error": f"'{project_name}' matches SSD-only rule — stays on C:"})

    size = dir_size(src)
    os.makedirs(E_PROJECTS, exist_ok=True)

    skipped = []
    def copy_safe(s, d):
        os.makedirs(d, exist_ok=True)
        for item in os.listdir(s):
            sp, dp = os.path.join(s, item), os.path.join(d, item)
            if is_reserved(item):
                skipped.append(sp); continue
            try:
                if os.path.isdir(sp) and not os.path.islink(sp):
                    copy_safe(sp, dp)
                else:
                    try: os.chmod(sp, stat.S_IWRITE | stat.S_IREAD)
                    except: pass
                    shutil.copy2(sp, dp)
            except: skipped.append(sp)

    copy_safe(src, dst)
    dst_size = dir_size(dst)

    if dst_size > size * 0.8:
        # Delete source
        for root, dirs, files in os.walk(src, topdown=False):
            for f in files:
                fp = os.path.join(root, f)
                try: os.chmod(fp, stat.S_IWRITE); os.remove(fp)
                except: pass
            for d in dirs:
                try: os.rmdir(os.path.join(root, d))
                except: pass
        try: os.rmdir(src)
        except: shutil.rmtree(src, ignore_errors=True)

        # Create junction
        if not os.path.exists(src):
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", src, dst],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            save_snapshot(get_drives(), size, f"archive:{project_name}")
            return json.dumps({
                "status": "success",
                "project": project_name,
                "moved": fmt(size),
                "junction": f"{src} -> {dst}",
                "skipped_files": len(skipped),
            }, indent=2)

    return json.dumps({"status": "partial", "moved": fmt(dst_size), "remaining_on_c": fmt(size - dst_size)})


@mcp.tool()
async def delete_dependency(project_name: str, dep_name: str):
    """
    Delete a venv or node_modules directory from an idle project.
    Can be recreated anytime with pip install / npm install.

    Args:
        project_name: Project folder name (e.g. 'klotskipuzzle')
        dep_name: Dependency folder (e.g. 'venv', '.venv', 'node_modules')
    """
    if dep_name not in ("venv", ".venv", "node_modules"):
        return json.dumps({"error": f"Only venv/.venv/node_modules allowed, not '{dep_name}'"})

    # Check both Desktop and E:\Projects
    for base in [DESKTOP, E_PROJECTS]:
        path = os.path.join(base, project_name, dep_name)
        if os.path.exists(path):
            size = dir_size(path)
            force_rmtree(path)
            if not os.path.exists(path):
                save_snapshot(get_drives(), size, f"rm-dep:{project_name}/{dep_name}")
                return json.dumps({
                    "status": "deleted",
                    "path": path,
                    "freed": fmt(size),
                    "restore": f"cd {os.path.join(base, project_name)} && pip install -r requirements.txt" if dep_name != "node_modules" else f"cd {os.path.join(base, project_name)} && npm install"
                }, indent=2)

    return json.dumps({"error": f"'{project_name}/{dep_name}' not found"})


@mcp.tool()
async def git_gc_all():
    """Run git gc --aggressive --prune=now on all repos. Compresses git history, frees space."""
    results = []
    for base in [DESKTOP, E_PROJECTS]:
        if not os.path.exists(base): continue
        for item in os.listdir(base):
            git_dir = os.path.join(base, item, ".git")
            if not os.path.exists(git_dir): continue
            git_size = dir_size(git_dir)
            if git_size < 10 * 1024 * 1024: continue

            try:
                subprocess.run(
                    ["git", "-C", os.path.join(base, item), "gc", "--aggressive", "--prune=now"],
                    capture_output=True, timeout=120, encoding="utf-8", errors="replace"
                )
                new_size = dir_size(git_dir)
                saved = git_size - new_size
                results.append({"repo": item, "before": fmt(git_size), "after": fmt(new_size), "saved": fmt(max(0, saved))})
            except: results.append({"repo": item, "error": "timeout or failed"})

    return json.dumps({"repos": results, "total_saved": fmt(sum(max(0, r.get("saved_bytes", 0)) for r in results))}, indent=2)


@mcp.tool()
async def install_watchdog():
    """Install PC Storage Manager as Windows Scheduled Task (runs every 2 hours + at login)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc_storage_manager.py")
    python = sys.executable

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <Repetition><Interval>PT2H</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T08:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><Delay>PT5M</Delay></LogonTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
  </Settings>
  <Actions><Exec><Command>{python}</Command><Arguments>"{script}" auto</Arguments></Exec></Actions>
</Task>'''

    os.makedirs(DATA_DIR, exist_ok=True)
    xml_path = os.path.join(DATA_DIR, "task.xml")
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)

    r = subprocess.run(
        ["schtasks", "/Create", "/TN", "PC_Storage_Manager", "/XML", xml_path, "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if r.returncode == 0:
        return json.dumps({"status": "installed", "interval": "every 2h + at login", "action": "auto-clean when C: > 93%"})
    return json.dumps({"status": "failed", "error": r.stderr.strip(), "hint": "May need admin privileges"})


# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
