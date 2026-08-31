#!/usr/bin/env python3
"""
Windows Core MCP Server
Essential Windows operations with <30 tools (well under OpenAI's 128-tool limit)

Categories:
- File Operations (10 tools)
- Process Management (8 tools)
- System Information (7 tools)
"""

import os
import subprocess
import platform
import json
import shutil
import psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("windows-core")

# ============================================================================
# FILE OPERATIONS (10 tools)
# ============================================================================

@mcp.tool()
def file_read(file_path: str) -> str:
    """Read contents of a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool()
def file_write(file_path: str, content: str) -> str:
    """Write content to a file (overwrites existing)."""
    try:
        os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@mcp.tool()
def file_append(file_path: str, content: str) -> str:
    """Append content to an existing file."""
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully appended to {file_path}"
    except Exception as e:
        return f"Error appending to file: {str(e)}"

@mcp.tool()
def file_delete(file_path: str) -> str:
    """Delete a file."""
    try:
        os.remove(file_path)
        return f"Successfully deleted {file_path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"

@mcp.tool()
def file_exists(file_path: str) -> bool:
    """Check if a file exists."""
    return os.path.isfile(file_path)

@mcp.tool()
def folder_create(folder_path: str) -> str:
    """Create a new folder (creates parent directories if needed)."""
    try:
        os.makedirs(folder_path, exist_ok=True)
        return f"Successfully created folder: {folder_path}"
    except Exception as e:
        return f"Error creating folder: {str(e)}"

@mcp.tool()
def folder_list(folder_path: str = ".") -> List[Dict[str, Any]]:
    """List files and folders in a directory."""
    try:
        items = []
        for item in os.listdir(folder_path):
            full_path = os.path.join(folder_path, item)
            is_dir = os.path.isdir(full_path)
            size = os.path.getsize(full_path) if not is_dir else 0
            items.append({
                "name": item,
                "type": "folder" if is_dir else "file",
                "size": size,
                "path": full_path
            })
        return items
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def folder_delete(folder_path: str) -> str:
    """Delete a folder and all its contents."""
    try:
        shutil.rmtree(folder_path)
        return f"Successfully deleted folder: {folder_path}"
    except Exception as e:
        return f"Error deleting folder: {str(e)}"

@mcp.tool()
def file_copy(source: str, destination: str) -> str:
    """Copy a file from source to destination."""
    try:
        shutil.copy2(source, destination)
        return f"Successfully copied {source} to {destination}"
    except Exception as e:
        return f"Error copying file: {str(e)}"

@mcp.tool()
def file_move(source: str, destination: str) -> str:
    """Move a file from source to destination."""
    try:
        shutil.move(source, destination)
        return f"Successfully moved {source} to {destination}"
    except Exception as e:
        return f"Error moving file: {str(e)}"

# ============================================================================
# PROCESS MANAGEMENT (8 tools)
# ============================================================================

@mcp.tool()
def process_list() -> List[Dict[str, Any]]:
    """List all running processes."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return processes
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def process_info(pid: int) -> Dict[str, Any]:
    """Get detailed information about a specific process."""
    try:
        proc = psutil.Process(pid)
        return {
            "pid": proc.pid,
            "name": proc.name(),
            "status": proc.status(),
            "cpu_percent": proc.cpu_percent(interval=0.1),
            "memory_percent": proc.memory_percent(),
            "create_time": datetime.fromtimestamp(proc.create_time()).isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def process_kill(pid: int) -> str:
    """Kill a process by PID."""
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        proc.wait(timeout=3)
        return f"Successfully terminated process {pid}"
    except psutil.TimeoutExpired:
        proc.kill()
        return f"Force killed process {pid}"
    except Exception as e:
        return f"Error killing process: {str(e)}"

@mcp.tool()
def process_start(program_path: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Start a new process."""
    try:
        cmd = [program_path] + (args or [])
        result = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return {
            "pid": result.pid,
            "command": " ".join(cmd),
            "status": "started"
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def process_count() -> int:
    """Get total number of running processes."""
    return len(list(psutil.process_iter()))

@mcp.tool()
def process_search(name: str) -> List[Dict[str, Any]]:
    """Search for processes by name."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if name.lower() in proc.info['name'].lower():
                    processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return processes
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def run_command(command: str) -> Dict[str, Any]:
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "command": command
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 30 seconds"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def open_file(file_path: str) -> str:
    """Open a file with the default application."""
    try:
        if platform.system() == 'Windows':
            os.startfile(file_path)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', file_path])
        else:  # Linux
            subprocess.run(['xdg-open', file_path])
        return f"Opened {file_path}"
    except Exception as e:
        return f"Error opening file: {str(e)}"

# ============================================================================
# SYSTEM INFORMATION (7 tools)
# ============================================================================

@mcp.tool()
def system_info() -> Dict[str, Any]:
    """Get basic system information."""
    try:
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "python_version": platform.python_version()
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def cpu_info() -> Dict[str, Any]:
    """Get CPU usage information."""
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "cpu_count": psutil.cpu_count(),
            "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def memory_info() -> Dict[str, Any]:
    """Get memory usage information."""
    try:
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2)
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def disk_info() -> List[Dict[str, Any]]:
    """Get disk usage information for all partitions."""
    try:
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                })
            except PermissionError:
                continue
        return disks
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def network_info() -> List[Dict[str, Any]]:
    """Get network interface information."""
    try:
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == 2:  # IPv4
                    interfaces.append({
                        "interface": name,
                        "address": addr.address,
                        "netmask": addr.netmask
                    })
        return interfaces
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def current_directory() -> str:
    """Get the current working directory."""
    return os.getcwd()

@mcp.tool()
def change_directory(path: str) -> str:
    """Change the current working directory."""
    try:
        os.chdir(path)
        return f"Changed directory to: {os.getcwd()}"
    except Exception as e:
        return f"Error changing directory: {str(e)}"

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    mcp.run()
