"""
Backup & Sync — MCP Server
==============================
System restore points, folder sync/backup between C: and E:.

Read-Only:
  - restore_points: List system restore points
  - backup_status: Backup locations on E:
  - diff_folders: Compare two folders

Actions:
  - create_restore_point: Create system restore point (admin)
  - sync_folder: Robocopy sync between folders
  - backup_folder: Copy folder to E:\\Backups with timestamp
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Backup & Sync",
    instructions=(
        "Backup and folder sync tools. Use 'restore_points' to see system restore points, "
        "'backup_status' for E:\\Backups overview, 'diff_folders' to compare. "
        "'backup_folder' copies to E:\\Backups, 'sync_folder' uses robocopy."
    ),
)

BACKUP_DIR = "E:\\Backups"


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


def dir_size(path):
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try: total += os.path.getsize(os.path.join(root, f))
                except: pass
    except: pass
    return total


def fmt(b):
    if b > 1024**3: return f"{b/1024**3:.1f} GB"
    if b > 1024**2: return f"{b/1024**2:.0f} MB"
    return f"{b/1024:.0f} KB"


@mcp.tool()
async def restore_points():
    """List all system restore points with dates and descriptions."""
    points = ps_json("""
        Get-ComputerRestorePoint -ErrorAction SilentlyContinue | ForEach-Object {
            @{
                SequenceNumber = $_.SequenceNumber
                Description = $_.Description
                CreationTime = $_.ConvertToDateTime($_.CreationTime).ToString('yyyy-MM-dd HH:mm')
                RestorePointType = switch ($_.RestorePointType) {
                    0 { 'ApplicationInstall' }
                    1 { 'ApplicationUninstall' }
                    10 { 'DeviceDriverInstall' }
                    12 { 'ModifySettings' }
                    13 { 'CancelledOperation' }
                    default { $_.RestorePointType }
                }
            }
        }
    """)

    results = points if isinstance(points, list) else [points] if points else []
    return json.dumps({"restore_points": results, "total": len(results)}, indent=2, default=str)


@mcp.tool()
async def backup_status():
    """Overview of backups on E:\\Backups — sizes, dates, disk space."""
    result = {"backups": [], "disk": {}}

    try:
        u = shutil.disk_usage("E:\\")
        result["disk"] = {"total_gb": round(u.total/1024**3, 1), "free_gb": round(u.free/1024**3, 1), "used_pct": round(u.used/u.total*100, 1)}
    except: pass

    if os.path.exists(BACKUP_DIR):
        for item in sorted(os.listdir(BACKUP_DIR)):
            fp = os.path.join(BACKUP_DIR, item)
            if os.path.isdir(fp):
                size = dir_size(fp)
                mtime = os.path.getmtime(fp)
                result["backups"].append({
                    "name": item,
                    "size": fmt(size),
                    "modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                })
    else:
        result["note"] = "E:\\Backups does not exist yet"

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def diff_folders(src: str, dst: str):
    """
    Compare two folders — show added, removed, and modified files.

    Args:
        src: Source folder path
        dst: Destination folder path
    """
    if not os.path.exists(src):
        return json.dumps({"error": f"Source not found: {src}"})
    if not os.path.exists(dst):
        return json.dumps({"error": f"Destination not found: {dst}"})

    diff = ps_json(f"""
        $src = Get-ChildItem -Path '{src}' -Recurse -File | Select-Object @{{N='RelPath';E={{$_.FullName.Substring({len(src)})}}}}, Length, LastWriteTime
        $dst = Get-ChildItem -Path '{dst}' -Recurse -File | Select-Object @{{N='RelPath';E={{$_.FullName.Substring({len(dst)})}}}}, Length, LastWriteTime
        $cmp = Compare-Object $src $dst -Property RelPath, Length -PassThru -IncludeEqual
        $added = @($cmp | Where-Object {{ $_.SideIndicator -eq '=>' }}).Count
        $removed = @($cmp | Where-Object {{ $_.SideIndicator -eq '<=' }}).Count
        $equal = @($cmp | Where-Object {{ $_.SideIndicator -eq '==' }}).Count
        @{{
            Added = $added
            Removed = $removed
            Equal = $equal
            SrcFiles = @($src).Count
            DstFiles = @($dst).Count
        }}
    """)

    return json.dumps({"src": src, "dst": dst, "diff": diff}, indent=2, default=str)


@mcp.tool()
async def create_restore_point(description: str = "MCP Backup"):
    """
    Create a system restore point. Needs admin.

    Args:
        description: Description for the restore point
    """
    result = ps(f"Checkpoint-Computer -Description '{description}' -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop")
    # Verify
    latest = ps("(Get-ComputerRestorePoint | Sort-Object SequenceNumber -Descending | Select-Object -First 1).Description")

    return json.dumps({"action": "create_restore_point", "description": description, "latest": latest, "note": "Needs admin"}, indent=2)


@mcp.tool()
async def sync_folder(src: str, dst: str, mirror: bool = False):
    """
    Sync folders using robocopy.

    Args:
        src: Source folder
        dst: Destination folder
        mirror: True = mirror (delete extras in dst), False = incremental copy
    """
    if not os.path.exists(src):
        return json.dumps({"error": f"Source not found: {src}"})

    mode = "/MIR" if mirror else "/E"
    result = subprocess.run(
        ["robocopy", src, dst, mode, "/XJ", "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/NJH", "/NJS"],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace"
    )

    # Robocopy exit codes 0-7 = success
    success = result.returncode < 8

    return json.dumps({
        "action": "sync",
        "src": src, "dst": dst,
        "mirror": mirror,
        "success": success,
        "exit_code": result.returncode,
    }, indent=2)


@mcp.tool()
async def backup_folder(path: str, name: str = ""):
    """
    Copy a folder to E:\\Backups with timestamp.

    Args:
        path: Folder to backup
        name: Backup name (default: folder name)
    """
    if not os.path.exists(path):
        return json.dumps({"error": f"Path not found: {path}"})

    if not name:
        name = os.path.basename(path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    dst = os.path.join(BACKUP_DIR, f"{name}_{timestamp}")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    result = subprocess.run(
        ["robocopy", path, dst, "/E", "/XJ", "/R:1", "/W:1", "/NP", "/NFL", "/NDL", "/NJH", "/NJS"],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace"
    )

    success = result.returncode < 8
    size = dir_size(dst) if os.path.exists(dst) else 0

    return json.dumps({
        "action": "backup",
        "source": path,
        "destination": dst,
        "size": fmt(size),
        "success": success,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
