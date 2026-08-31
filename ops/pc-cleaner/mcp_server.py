"""
VibeMind PC Storage — MCP Server
=================================
Disk/storage inspection + safe cleanup for the local Windows machine.
Wraps the tosort/pc-cleaner scripts as structured MCP tools.

Tools (read-only):
- disk_usage            : Per-drive free/used/total (shutil.disk_usage)
- storage_scan          : Scan known cache/temp dirs, return sizes + safe flag
- dir_size              : Size of an arbitrary directory
- top_largest           : Top-N largest files under a path
- heavy_hitters_inspect : List Ollama models / pyenv versions / Android AVDs (opt-in cleanup info)
- memory_inspect        : Top RAM-consuming processes with friendly names (python:<module>)
- zombie_detect         : Find python/node processes that look idle/hung (preview only, no kill)
- pagefile_inspect      : Pagefile size + recommendation vs. installed RAM
- big_files_scan        : Largest single files on a drive, ignoring known cache dirs
- git_bloat_scan        : Find .git repos with oversized pack files
- dead_projects_scan    : Repos untouched > N days that still hold node_modules/.venv/target
- autostart_audit       : Inspect Windows startup commands + flag suspicious entries

Tools (mutating — require confirm=true):
- storage_clean         : Delete safe cache/temp dirs (run / nochrome variants)
- hibernate_disable     : Run 'powercfg /h off' — frees hiberfil.sys (~12 GB typical)
"""
import os
import re
import shutil
import string
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "VibeMind PC Storage",
    instructions=(
        "Local PC storage inspection + safe cache cleanup. "
        "Always call storage_scan first to preview. "
        "storage_clean requires confirm=true and will permanently delete cache files."
    ),
)

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
APPDATA = os.environ.get("APPDATA", "")
TEMP = os.environ.get("TEMP", "")
HOME = os.path.expanduser("~")


def _fmt(b: int) -> str:
    if b > 1024**3:
        return f"{b / 1024**3:.2f} GB"
    if b > 1024**2:
        return f"{b / 1024**2:.1f} MB"
    if b > 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b} B"


def _dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


PROGRAMDATA = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
WINDIR = os.environ.get("WINDIR", r"C:\Windows")


def _targets(include_chrome: bool = True) -> list[tuple[str, str, bool]]:
    t = [
        (TEMP, "Windows Temp", True),
        (os.path.join(LOCALAPPDATA, "Temp"), "User Temp", True),
        (os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "INetCache"), "IE/Edge Cache", True),
        # Python toolchain caches
        (os.path.join(LOCALAPPDATA, "pip", "cache"), "pip Cache", True),
        (os.path.join(LOCALAPPDATA, "uv", "cache"), "uv Cache", True),
        # Node toolchain caches
        (os.path.join(LOCALAPPDATA, "npm-cache"), "npm Cache", True),
        (os.path.join(APPDATA, "npm-cache"), "npm Cache (Roaming)", True),
        (os.path.join(LOCALAPPDATA, "pnpm", "store"), "pnpm Store", True),
        (os.path.join(LOCALAPPDATA, "yarn", "Cache"), "Yarn Cache", True),
        (os.path.join(LOCALAPPDATA, "NuGet", "Cache"), "NuGet Cache", True),
        # Rust toolchain
        (os.path.join(HOME, ".cargo", "registry", "cache"), "Cargo Registry Cache", True),
        (os.path.join(HOME, ".cargo", "registry", "src"), "Cargo Registry Src", True),
        # Browser test runners
        (os.path.join(LOCALAPPDATA, "ms-playwright"), "Playwright Browsers", True),
        # Generic / pyenv / VSCode
        (os.path.join(HOME, ".cache"), ".cache", True),
        (os.path.join(HOME, ".pyenv", "pyenv-win", "install_cache"), "pyenv Install Cache", True),
        (os.path.join(LOCALAPPDATA, "CrashDumps"), "Crash Dumps", True),
        (os.path.join(LOCALAPPDATA, "Temp", "vscode-stable-user-x64"), "VSCode Update Cache", True),
        (os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "Explorer"), "Thumbnail Cache", True),
        # Windows system-level remnants (often need admin; safe to remove)
        (os.path.join(WINDIR, "SoftwareDistribution", "Download"), "Windows Update Downloads", True),
        (os.path.join(WINDIR, "Logs", "CBS"), "CBS Logs", True),
        (os.path.join(PROGRAMDATA, "Microsoft", "Windows", "WER", "ReportQueue"), "WER ReportQueue", True),
        (os.path.join(PROGRAMDATA, "Microsoft", "Windows", "WER", "ReportArchive"), "WER ReportArchive", True),
        (os.path.join(WINDIR, "Installer", "$PatchCache$"), "Windows Patch Cache", True),
        # Risky / data-bearing — do not auto-delete
        (os.path.join(LOCALAPPDATA, "Docker", "wsl"), "Docker WSL Data", False),
        (os.path.join(LOCALAPPDATA, "Packages"), "UWP App Packages", False),
        (os.path.join(HOME, "Downloads"), "Downloads", False),
        # Heavy hitters — opt-in only (see heavy_hitters_inspect)
        (os.path.join(HOME, ".ollama", "models"), "Ollama Models (opt-in)", False),
        (os.path.join(HOME, ".android", "avd"), "Android AVDs (opt-in)", False),
        (os.path.join(HOME, ".pyenv", "pyenv-win", "versions"), "pyenv Python Versions (opt-in)", False),
    ]
    if include_chrome:
        t.extend([
            (os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data", "Default", "Cache"), "Chrome Cache", True),
            (os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data", "Default", "Code Cache"), "Chrome Code Cache", True),
            (os.path.join(LOCALAPPDATA, "Microsoft", "Edge", "User Data", "Default", "Cache"), "Edge Cache", True),
            (os.path.join(LOCALAPPDATA, "Microsoft", "Edge", "User Data", "Default", "Code Cache"), "Edge Code Cache", True),
        ])
    return t


def _is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _clean_dir(path: str) -> tuple[int, int]:
    freed = 0
    errors = 0
    try:
        items = os.listdir(path)
    except (PermissionError, OSError):
        return 0, 1
    for item in items:
        fp = os.path.join(path, item)
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                size = os.path.getsize(fp)
                os.remove(fp)
                freed += size
            elif os.path.isdir(fp):
                size = _dir_size(fp)
                shutil.rmtree(fp, ignore_errors=True)
                freed += size
        except (PermissionError, OSError):
            errors += 1
    return freed, errors


@mcp.tool()
def disk_usage() -> dict[str, Any]:
    """Report free/used/total bytes for each mounted drive (Windows)."""
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            try:
                u = shutil.disk_usage(root)
                drives.append({
                    "drive": root,
                    "total": u.total,
                    "used": u.used,
                    "free": u.free,
                    "total_h": _fmt(u.total),
                    "used_h": _fmt(u.used),
                    "free_h": _fmt(u.free),
                    "percent_used": round(u.used / u.total * 100, 1) if u.total else 0,
                })
            except OSError:
                pass
    return {"drives": drives}


@mcp.tool()
def storage_scan(min_mb: float = 1.0, include_chrome: bool = True) -> dict[str, Any]:
    """Scan known cache/temp dirs. Read-only. Returns per-target size + safe flag."""
    results = []
    total_safe = 0
    total_risky = 0
    for path, name, safe in _targets(include_chrome):
        if not os.path.exists(path):
            continue
        size = _dir_size(path)
        if size < min_mb * 1024 * 1024:
            continue
        results.append({
            "name": name,
            "path": path,
            "size": size,
            "size_h": _fmt(size),
            "safe_to_delete": safe,
        })
        if safe:
            total_safe += size
        else:
            total_risky += size
    results.sort(key=lambda x: x["size"], reverse=True)
    return {
        "targets": results,
        "total_safe": total_safe,
        "total_safe_h": _fmt(total_safe),
        "total_risky": total_risky,
        "total_risky_h": _fmt(total_risky),
    }


@mcp.tool()
def dir_size(path: str) -> dict[str, Any]:
    """Compute recursive size of an arbitrary directory."""
    if not os.path.exists(path):
        return {"error": f"path not found: {path}"}
    size = _dir_size(path)
    return {"path": path, "size": size, "size_h": _fmt(size)}


@mcp.tool()
def top_largest(path: str, n: int = 20) -> dict[str, Any]:
    """Return the top-N largest files under a path."""
    if not os.path.exists(path):
        return {"error": f"path not found: {path}"}
    files: list[tuple[int, str]] = []
    for root, _dirs, fs in os.walk(path):
        for f in fs:
            fp = os.path.join(root, f)
            try:
                files.append((os.path.getsize(fp), fp))
            except (PermissionError, OSError):
                pass
    files.sort(reverse=True)
    return {
        "path": path,
        "files": [{"size": s, "size_h": _fmt(s), "path": p} for s, p in files[:n]],
    }


@mcp.tool()
def storage_clean(
    confirm: bool = False,
    include_chrome: bool = True,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Delete safe cache/temp dirs. Requires confirm=true to actually delete.
    Set include_chrome=false if Chrome is running. Defaults to dry_run=true.
    """
    if not confirm and not dry_run:
        return {"error": "refusing to delete without confirm=true; set dry_run=false AND confirm=true"}
    results = []
    total_freed = 0
    total_errors = 0
    for path, name, safe in _targets(include_chrome):
        if not safe or not os.path.exists(path):
            continue
        if dry_run or not confirm:
            size = _dir_size(path)
            results.append({"name": name, "path": path, "would_free": size, "would_free_h": _fmt(size)})
            total_freed += size
        else:
            freed, errors = _clean_dir(path)
            total_freed += freed
            total_errors += errors
            results.append({"name": name, "path": path, "freed": freed, "freed_h": _fmt(freed), "locked": errors})
    return {
        "dry_run": dry_run or not confirm,
        "targets": results,
        "total_freed": total_freed,
        "total_freed_h": _fmt(total_freed),
        "locked_errors": total_errors,
    }


@mcp.tool()
def heavy_hitters_inspect() -> dict[str, Any]:
    """Inspect large opt-in folders (Ollama models, pyenv versions, Android AVDs).

    Reports per-item sizes + the manager command to remove them safely.
    Does NOT delete anything — caller decides via the manager's own CLI.
    """
    out: dict[str, Any] = {}

    # Ollama models — manager command: 'ollama rm <name>'
    ollama_root = os.path.join(HOME, ".ollama", "models", "manifests", "registry.ollama.ai")
    models = []
    if os.path.isdir(ollama_root):
        for root, _d, files in os.walk(ollama_root):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ollama_root)
                models.append(rel.replace("\\", "/"))
    blobs_path = os.path.join(HOME, ".ollama", "models", "blobs")
    out["ollama"] = {
        "path": os.path.join(HOME, ".ollama", "models"),
        "size": _dir_size(os.path.join(HOME, ".ollama", "models")),
        "size_h": _fmt(_dir_size(os.path.join(HOME, ".ollama", "models"))),
        "manifests": models,
        "blobs_size_h": _fmt(_dir_size(blobs_path)) if os.path.isdir(blobs_path) else "0 B",
        "remove_cmd": "ollama rm <model-name>",
        "list_cmd": "ollama list",
    }

    # pyenv versions — manager command: 'pyenv uninstall <version>'
    pyenv_root = os.path.join(HOME, ".pyenv", "pyenv-win", "versions")
    versions = []
    if os.path.isdir(pyenv_root):
        for d in sorted(os.listdir(pyenv_root)):
            full = os.path.join(pyenv_root, d)
            if os.path.isdir(full):
                size = _dir_size(full)
                versions.append({"version": d, "size": size, "size_h": _fmt(size)})
    out["pyenv"] = {
        "path": pyenv_root,
        "size_h": _fmt(sum(v["size"] for v in versions)),
        "versions": versions,
        "remove_cmd": "pyenv uninstall <version>",
    }

    # Android AVDs — manager command: 'avdmanager delete avd -n <name>'
    avd_root = os.path.join(HOME, ".android", "avd")
    avds = []
    if os.path.isdir(avd_root):
        for entry in sorted(os.listdir(avd_root)):
            full = os.path.join(avd_root, entry)
            if entry.endswith(".avd") and os.path.isdir(full):
                size = _dir_size(full)
                avds.append({"name": entry.replace(".avd", ""), "size": size, "size_h": _fmt(size)})
    out["android_avds"] = {
        "path": avd_root,
        "size_h": _fmt(sum(a["size"] for a in avds)),
        "avds": avds,
        "remove_cmd": "avdmanager delete avd -n <name>",
        "list_cmd": "avdmanager list avd",
    }

    return out


@mcp.tool()
def hibernate_disable(confirm: bool = False, dry_run: bool = True) -> dict[str, Any]:
    """Disable Windows hibernate (frees hiberfil.sys, typically ~RAM-sized).

    Runs 'powercfg /h off'. Normal shutdown still works; only the 'Ruhezustand'
    option goes away. Requires admin. Reversible with 'powercfg /h on'.
    """
    hiber = r"C:\hiberfil.sys"
    size = 0
    if os.path.exists(hiber):
        try:
            size = os.path.getsize(hiber)
        except OSError:
            pass

    if dry_run or not confirm:
        return {
            "dry_run": True,
            "hiberfile": hiber,
            "current_size": size,
            "current_size_h": _fmt(size),
            "would_run": "powercfg /h off",
            "is_admin": _is_admin(),
            "note": "Re-call with dry_run=false AND confirm=true to actually disable.",
        }

    if not _is_admin():
        return {
            "error": "needs admin",
            "hint": "Run this MCP server (or call this tool from a context) with admin rights.",
        }

    try:
        res = subprocess.run(
            ["powercfg", "/h", "off"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return {
            "executed": "powercfg /h off",
            "returncode": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
            "freed_estimate": size,
            "freed_estimate_h": _fmt(size),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Memory / process introspection
# ---------------------------------------------------------------------------

# Interpreter executables we want to "decode" rather than show as 'python.exe'.
_INTERPRETER_NAMES = {"python.exe", "pythonw.exe", "node.exe", "ruby.exe", "java.exe", "dotnet.exe"}


def _friendly_process_name(name: str, cmdline: str) -> str:
    """Turn 'python.exe' + a noisy command line into something like
    'python:web.brain_server:5000' or 'python:mcp_server.py'.

    Falls back to the raw executable name for non-interpreters.
    """
    if not name:
        return "?"
    base = name.lower()
    if base not in _INTERPRETER_NAMES:
        return name
    cmd = (cmdline or "").strip()
    if not cmd:
        return name

    # Tokenize while respecting quotes — good enough for Windows command lines.
    try:
        import shlex
        tokens = shlex.split(cmd, posix=False)
    except Exception:
        tokens = cmd.split()
    if not tokens:
        return name

    # Drop the interpreter itself (first token).
    args = tokens[1:]
    if not args:
        return name

    label = None
    port = None
    i = 0
    while i < len(args):
        a = args[i]
        # Skip flags that take a value
        if a in ("-c", "-X"):
            i += 2
            continue
        # -m <module>   →   pull module name
        if a == "-m" and i + 1 < len(args):
            label = args[i + 1].strip('"')
            i += 2
            continue
        # --port / -p <number>   →   capture port for the label
        if a in ("--port", "-p", "--listen-port") and i + 1 < len(args):
            try:
                port = int(args[i + 1].strip('"'))
            except ValueError:
                pass
            i += 2
            continue
        # First non-flag argument that looks like a script path
        if label is None and not a.startswith("-"):
            stripped = a.strip('"')
            # Take the basename for readability
            label = os.path.basename(stripped) or stripped
        i += 1

    short = label or name
    if port is not None:
        short = f"{short}:{port}"
    # Prefix with 'python'/'node' to keep the interpreter recognisable.
    interp = base.replace(".exe", "")
    return f"{interp}:{short}"


def _list_processes_with_cmdline() -> list[dict[str, Any]]:
    """Use WMIC/PowerShell to read PID + Name + CommandLine + WorkingSet + Private.

    Returns a list of dicts: pid, name, friendly, ws, priv, cmdline, started.
    """
    # PowerShell is the most reliable Win32 introspection from Python on modern Windows.
    ps_cmd = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId, Name, CommandLine, WorkingSetSize, PrivatePageCount, CreationDate | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return []
        import json
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            data = [data]
    except Exception:  # noqa: BLE001
        return []

    out = []
    for p in data:
        try:
            pid = int(p.get("ProcessId") or 0)
            name = p.get("Name") or ""
            cmd = p.get("CommandLine") or ""
            ws = int(p.get("WorkingSetSize") or 0)
            priv = int(p.get("PrivatePageCount") or 0)
            started = p.get("CreationDate")
            # CreationDate comes through as @{DateTime=...} in some shells — normalise.
            if isinstance(started, dict):
                started = started.get("DateTime") or started.get("value") or str(started)
            out.append({
                "pid": pid,
                "name": name,
                "friendly": _friendly_process_name(name, cmd),
                "ws": ws,
                "ws_h": _fmt(ws),
                "priv": priv,
                "priv_h": _fmt(priv),
                "cmdline": cmd,
                "started": started,
            })
        except (TypeError, ValueError):
            continue
    return out


@mcp.tool()
def memory_inspect(top: int = 15, sort_by: str = "priv") -> dict[str, Any]:
    """Show physical memory stats + top RAM-consuming processes.

    sort_by: 'priv' (Private bytes — committed memory incl. pagefile, default)
             or 'ws' (Working Set — what's actually resident).

    Process names are decoded: 'python.exe' running a -m module is shown as
    'python:<module>:<port>' so you can tell brain_server from an MCP server.
    """
    sort_by = "ws" if sort_by == "ws" else "priv"

    # Memory totals via PowerShell (shutil has no Windows RAM API).
    mem_cmd = (
        "$m = Get-CimInstance Win32_OperatingSystem; "
        "[PSCustomObject]@{ "
        "  TotalVisibleKB = $m.TotalVisibleMemorySize; "
        "  FreePhysicalKB = $m.FreePhysicalMemory; "
        "  FreeVirtualKB  = $m.FreeVirtualMemory; "
        "  TotalVirtualKB = $m.TotalVirtualMemorySize "
        "} | ConvertTo-Json -Compress"
    )
    totals: dict[str, Any] = {}
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", mem_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            import json
            t = json.loads(res.stdout)
            total = int(t.get("TotalVisibleKB") or 0) * 1024
            free = int(t.get("FreePhysicalKB") or 0) * 1024
            used = max(0, total - free)
            totals = {
                "total": total, "total_h": _fmt(total),
                "free": free, "free_h": _fmt(free),
                "used": used, "used_h": _fmt(used),
                "used_pct": round(used / total * 100, 1) if total else 0,
                "total_virtual": int(t.get("TotalVirtualKB") or 0) * 1024,
                "free_virtual": int(t.get("FreeVirtualKB") or 0) * 1024,
            }
    except Exception:  # noqa: BLE001
        pass

    procs = _list_processes_with_cmdline()
    procs.sort(key=lambda p: p[sort_by], reverse=True)
    top_n = procs[: max(1, int(top))]

    return {
        "memory": totals,
        "sort_by": sort_by,
        "top_processes": [
            {
                "pid": p["pid"],
                "friendly": p["friendly"],
                "name": p["name"],
                "ws_h": p["ws_h"],
                "priv_h": p["priv_h"],
                "started": p["started"],
            }
            for p in top_n
        ],
    }


@mcp.tool()
def zombie_detect(
    ws_threshold_mb: float = 5.0,
    min_age_minutes: int = 30,
    name_filter: str = "python.exe,node.exe",
) -> dict[str, Any]:
    """Preview list of interpreter processes that LOOK zombie/hung. No killing.

    Heuristic: process is in 'name_filter', older than min_age_minutes, and
    has a Working Set smaller than ws_threshold_mb (i.e. fully paged out, no
    activity). These often correspond to crashed background services.

    Returns the candidates with their friendly name + start time so you can
    decide manually (Task-Manager / Stop-Process) whether to terminate.
    """
    from datetime import datetime, timedelta

    wanted = {n.strip().lower() for n in name_filter.split(",") if n.strip()}
    procs = _list_processes_with_cmdline()
    cutoff = datetime.now() - timedelta(minutes=int(min_age_minutes))

    def _parse_started(s: Any) -> "datetime | None":
        if not s:
            return None
        if isinstance(s, datetime):
            return s
        if isinstance(s, str):
            # Try common formats — PowerShell often returns ISO or 'M/d/yyyy h:mm:ss tt'
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%m/%d/%Y %I:%M:%S %p",
                "%d.%m.%Y %H:%M:%S",
                "%Y%m%d%H%M%S.%f",
            ):
                try:
                    return datetime.strptime(s.split("+")[0].strip(), fmt)
                except ValueError:
                    continue
        return None

    candidates = []
    for p in procs:
        if p["name"].lower() not in wanted:
            continue
        if p["ws"] >= ws_threshold_mb * 1024 * 1024:
            continue
        started_dt = _parse_started(p["started"])
        if started_dt is None or started_dt > cutoff:
            continue
        candidates.append({
            "pid": p["pid"],
            "friendly": p["friendly"],
            "name": p["name"],
            "ws_h": p["ws_h"],
            "priv_h": p["priv_h"],
            "started": p["started"],
            "kill_cmd": f"Stop-Process -Id {p['pid']} -Force",
        })

    candidates.sort(key=lambda c: c["pid"])
    return {
        "criteria": {
            "name_filter": sorted(wanted),
            "ws_threshold_mb": ws_threshold_mb,
            "min_age_minutes": min_age_minutes,
        },
        "candidates": candidates,
        "count": len(candidates),
        "note": (
            "Read-only preview. ALL of these may be your active services that "
            "are simply idle and paged out. Verify before killing."
        ),
    }


@mcp.tool()
def pagefile_inspect() -> dict[str, Any]:
    """Show Pagefile config + recommendation relative to installed RAM."""
    ps_cmd = (
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "$pf = Get-CimInstance Win32_PageFileUsage; "
        "[PSCustomObject]@{ "
        "  TotalRamKB = $os.TotalVisibleMemorySize; "
        "  Pagefiles = @($pf | Select-Object Name, CurrentUsage, PeakUsage, AllocatedBaseSize) "
        "} | ConvertTo-Json -Compress -Depth 4"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return {"error": "powershell call failed", "stderr": res.stderr.strip()}
        import json
        data = json.loads(res.stdout)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

    ram_bytes = int(data.get("TotalRamKB") or 0) * 1024
    pf_raw = data.get("Pagefiles") or []
    if isinstance(pf_raw, dict):
        pf_raw = [pf_raw]

    pagefiles = []
    total_alloc = 0
    for entry in pf_raw:
        alloc_mb = int(entry.get("AllocatedBaseSize") or 0)
        cur_mb = int(entry.get("CurrentUsage") or 0)
        peak_mb = int(entry.get("PeakUsage") or 0)
        total_alloc += alloc_mb
        pagefiles.append({
            "path": entry.get("Name") or "?",
            "allocated_mb": alloc_mb,
            "current_use_mb": cur_mb,
            "peak_use_mb": peak_mb,
        })

    ram_gb = ram_bytes / 1024**3
    alloc_gb = total_alloc / 1024
    # Microsoft default rule of thumb: pagefile = 1.5x RAM is plenty,
    # 3x is wasteful unless you regularly produce crash dumps that need full RAM.
    rec_min_gb = max(4.0, ram_gb * 1.0)
    rec_max_gb = max(8.0, ram_gb * 1.5)

    if alloc_gb > ram_gb * 2.5:
        verdict = "oversized"
        note = (
            f"Pagefile {alloc_gb:.0f} GB vs. RAM {ram_gb:.0f} GB is far above the "
            f"1.5x rule of thumb. Recommend cap at ~{rec_max_gb:.0f} GB unless you "
            f"need full memory dumps."
        )
    elif alloc_gb < rec_min_gb:
        verdict = "undersized"
        note = f"Pagefile {alloc_gb:.0f} GB is below {rec_min_gb:.0f} GB — risk of allocation failures under pressure."
    else:
        verdict = "ok"
        note = "Pagefile size is within the recommended band."

    return {
        "ram_total_gb": round(ram_gb, 1),
        "pagefiles": pagefiles,
        "total_allocated_gb": round(alloc_gb, 1),
        "recommended_band_gb": [round(rec_min_gb, 1), round(rec_max_gb, 1)],
        "verdict": verdict,
        "note": note,
        "change_hint": (
            "Adjust via sysdm.cpl → Advanced → Performance Settings → "
            "Advanced → Virtual memory → Change. Requires admin + reboot."
        ),
    }


# ---------------------------------------------------------------------------
# Forensic scanners
# ---------------------------------------------------------------------------

# Subpath fragments we skip when hunting "non-cache" disk hogs.
_BIG_FILE_EXCLUDES = (
    r"\AppData\Local\Docker\\",
    r"\AppData\Local\Packages\\",
    r"\AppData\Local\Temp\\",
    r"\Windows\Installer\\",
    r"\Windows\WinSxS\\",
    r"\Windows\SoftwareDistribution\\",
    r"\$Recycle.Bin\\",
    r"\$Windows.~BT\\",
    r"\$Windows.~WS\\",
    r"\System Volume Information\\",
    r"\node_modules\\",
    r"\.venv\\",
    r"\.venv312\\",
    r"\.venv311\\",
    r"\target\debug\\",
    r"\target\release\\",
)


@mcp.tool()
def big_files_scan(
    root: str = "C:\\Users",
    min_gb: float = 0.5,
    top: int = 25,
) -> dict[str, Any]:
    """Largest single files under `root`, skipping known cache locations.

    Default skips Docker WSL VHDX, UWP Packages, Temp, WinSxS, Recycle Bin,
    node_modules, .venv*, Rust target/. Use this to find forgotten VMs,
    ISOs, downloaded model weights, oversize logs.
    """
    if not os.path.isdir(root):
        return {"error": f"root not found: {root}"}
    threshold = int(min_gb * 1024**3)
    hits: list[dict[str, Any]] = []
    for dirpath, _dirs, files in os.walk(root):
        # Quick prune: skip whole tree if path matches an exclude.
        low = dirpath + "\\"
        if any(ex.lower() in low.lower() for ex in _BIG_FILE_EXCLUDES):
            continue
        for f in files:
            full = os.path.join(dirpath, f)
            try:
                size = os.path.getsize(full)
            except (PermissionError, OSError):
                continue
            if size >= threshold:
                hits.append({"path": full, "size": size, "size_h": _fmt(size)})
    hits.sort(key=lambda h: h["size"], reverse=True)
    return {
        "root": root,
        "min_gb": min_gb,
        "count": len(hits),
        "files": hits[: max(1, int(top))],
    }


@mcp.tool()
def git_bloat_scan(root: str = "C:\\Users", min_gb: float = 1.0) -> dict[str, Any]:
    """Find .git/ pack files larger than `min_gb` — i.e. bloated repositories.

    Each hit is reported with the parent repo path and the recommended
    cleanup commands ('git gc --aggressive --prune=now' / shallow re-clone).
    """
    if not os.path.isdir(root):
        return {"error": f"root not found: {root}"}
    threshold = int(min_gb * 1024**3)
    repos: dict[str, dict[str, Any]] = {}
    for dirpath, dirs, files in os.walk(root):
        # Only descend into .git dirs explicitly.
        if not dirpath.lower().endswith(r"\.git\objects\pack") and r"\.git\objects\pack" not in dirpath.lower():
            continue
        for f in files:
            if not f.endswith(".pack"):
                continue
            full = os.path.join(dirpath, f)
            try:
                size = os.path.getsize(full)
            except (PermissionError, OSError):
                continue
            if size < threshold:
                continue
            # Walk up to the repo root (parent of .git).
            repo_root = dirpath.split(r"\.git\\")[0]
            if repo_root not in repos:
                repos[repo_root] = {"repo": repo_root, "packs": [], "total": 0}
            repos[repo_root]["packs"].append({"path": full, "size": size, "size_h": _fmt(size)})
            repos[repo_root]["total"] += size

    out = []
    for r in repos.values():
        r["total_h"] = _fmt(r["total"])
        r["cleanup_cmds"] = [
            f'cd "{r["repo"]}" && git gc --aggressive --prune=now',
            f'cd "{r["repo"]}" && git repack -ad --depth=250 --window=250',
            "# Or shallow re-clone: git clone --depth=1 <remote-url>",
        ]
        out.append(r)
    out.sort(key=lambda x: x["total"], reverse=True)
    return {"root": root, "min_gb": min_gb, "repos": out, "count": len(out)}


_DEAD_PROJECT_ARTIFACTS = ("node_modules", ".venv", ".venv311", ".venv312", "target", "build", "dist", ".next", ".nuxt")


@mcp.tool()
def dead_projects_scan(
    root: str = "C:\\Users\\User\\Desktop",
    days_idle: int = 90,
    min_artifact_gb: float = 0.1,
    top: int = 20,
) -> dict[str, Any]:
    """Find repos untouched > days_idle that still hold build artifacts.

    A project is 'dead' if its newest *.py/*.ts/*.js/*.rs/*.md file is older
    than days_idle. We then report which artifact folders it still keeps —
    those are the safe-to-delete reclaimables.
    """
    from datetime import datetime, timedelta
    if not os.path.isdir(root):
        return {"error": f"root not found: {root}"}
    cutoff = datetime.now() - timedelta(days=int(days_idle))
    threshold = int(min_artifact_gb * 1024**3)
    src_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".java", ".md"}

    candidates = []
    try:
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            if not os.path.isdir(full):
                continue
            # Find newest source file
            newest = 0.0
            has_artifact = False
            artifacts: list[dict[str, Any]] = []
            for dirpath, dirs, files in os.walk(full):
                base = os.path.basename(dirpath)
                if base in _DEAD_PROJECT_ARTIFACTS:
                    has_artifact = True
                    sz = 0
                    for r, _d, fs in os.walk(dirpath):
                        for ff in fs:
                            try:
                                sz += os.path.getsize(os.path.join(r, ff))
                            except (PermissionError, OSError):
                                pass
                    if sz >= threshold:
                        artifacts.append({"path": dirpath, "kind": base, "size": sz, "size_h": _fmt(sz)})
                    # Don't descend into artifact folders for the mtime check.
                    dirs[:] = []
                    continue
                # Prune deep hidden dirs
                if base.startswith(".") and base not in (".github",):
                    dirs[:] = []
                    continue
                for ff in files:
                    ext = os.path.splitext(ff)[1].lower()
                    if ext in src_exts:
                        try:
                            t = os.path.getmtime(os.path.join(dirpath, ff))
                        except (PermissionError, OSError):
                            continue
                        if t > newest:
                            newest = t
            if not has_artifact or not artifacts:
                continue
            newest_dt = datetime.fromtimestamp(newest) if newest else None
            if newest_dt is None or newest_dt > cutoff:
                continue
            total = sum(a["size"] for a in artifacts)
            candidates.append({
                "project": full,
                "newest_source": newest_dt.isoformat(timespec="seconds") if newest_dt else None,
                "artifacts": sorted(artifacts, key=lambda a: a["size"], reverse=True),
                "reclaimable": total,
                "reclaimable_h": _fmt(total),
            })
    except (PermissionError, OSError):
        pass

    candidates.sort(key=lambda c: c["reclaimable"], reverse=True)
    return {
        "root": root,
        "days_idle": days_idle,
        "min_artifact_gb": min_artifact_gb,
        "projects": candidates[: max(1, int(top))],
        "count": len(candidates),
    }


# Names that are usually safe to disable in autostart for desktop workflows.
_AUTOSTART_KNOWN_SAFE_DISABLE = {
    "spotify", "discord", "steam", "riotclient", "epic games launcher",
    "skype", "teams", "microsoftedgeautolaunch", "com.squirrel.teams.teams",
}
# Patterns we explicitly flag as suspicious.
_AUTOSTART_SUSPICIOUS = (
    (r"notepad\.exe", "Autostart launches notepad.exe — almost certainly a leftover PoC/test entry"),
    (r"powershell.*-(enc|encoded|nop)", "Encoded/no-profile PowerShell on boot — investigate"),
    (r"\\Temp\\", "Autostart points into a Temp directory — investigate"),
    (r"\\Downloads\\", "Autostart points into Downloads — investigate"),
)


@mcp.tool()
def autostart_audit() -> dict[str, Any]:
    """List Windows autostart entries with hints.

    Categories:
      - suspicious: matches a malware-ish or test-leftover pattern
      - heavy_optional: known apps that are typically fine to disable for faster boot
      - system: leave alone unless you know better
    """
    ps_cmd = (
        "Get-CimInstance Win32_StartupCommand | "
        "Select-Object Name, Command, Location, User | "
        "ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return {"error": "powershell call failed"}
        import json
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            data = [data]
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

    suspicious, heavy_optional, system = [], [], []
    for entry in data:
        name = (entry.get("Name") or "").strip()
        cmd = (entry.get("Command") or "").strip()
        loc = (entry.get("Location") or "").strip()
        user = (entry.get("User") or "").strip()
        item = {"name": name, "command": cmd, "location": loc, "user": user}

        # Suspicious check
        flagged = None
        for pat, reason in _AUTOSTART_SUSPICIOUS:
            if re.search(pat, cmd, re.IGNORECASE):
                flagged = reason
                break
        if flagged:
            item["why"] = flagged
            suspicious.append(item)
            continue

        # Known optional?
        low_name = name.lower()
        if any(k in low_name for k in _AUTOSTART_KNOWN_SAFE_DISABLE):
            heavy_optional.append(item)
            continue

        # System / vendor / unknown — leave to user judgement
        system.append(item)

    return {
        "summary": {
            "total": len(data),
            "suspicious": len(suspicious),
            "heavy_optional": len(heavy_optional),
            "system": len(system),
        },
        "suspicious": suspicious,
        "heavy_optional": heavy_optional,
        "system": system,
        "disable_hint": (
            "Disable via Task Manager → Startup tab, or "
            "settings.ms-settings:startupapps. "
            "Registry entries: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run."
        ),
    }


if __name__ == "__main__":
    mcp.run()
