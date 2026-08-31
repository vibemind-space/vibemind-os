"""
MCP Admin Helper
=================
Shared utilities for MCP servers that need elevated (admin) privileges.
Used by: poc_driver_manager, and potentially other system MCP servers.
"""

import ctypes
import json
import os
import subprocess
import sys
import tempfile


def is_admin() -> bool:
    """Check if the current process is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def admin_required_response(action: str) -> dict:
    """Return a standardized response when admin privileges are required."""
    return {
        "error": "admin_required",
        "message": f"Action '{action}' requires administrator privileges.",
        "hint": "Re-run the MCP server as Administrator, or use 'fix_driver' which will prompt UAC.",
    }


def run_elevated(command: str, timeout: int = 30) -> dict:
    """
    Run a PowerShell command with elevated privileges via UAC prompt.
    Returns dict with stdout, stderr, returncode.
    """
    if is_admin():
        # Already admin, run directly
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, timeout=timeout
            )
            return {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "timeout", "message": f"Command timed out after {timeout}s"}
    else:
        # Need elevation — write command to temp script and run via Start-Process -Verb RunAs
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False) as f:
                f.write(command)
                script_path = f.name

            result = subprocess.run(
                ["powershell", "-Command",
                 f"Start-Process powershell -Verb RunAs -Wait -ArgumentList '-File {script_path}' -PassThru"],
                capture_output=True, text=True, timeout=timeout + 30
            )
            os.unlink(script_path)
            return {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "elevated": True,
            }
        except subprocess.TimeoutExpired:
            return {"error": "timeout", "message": "UAC elevation timed out"}
        except Exception as e:
            return {"error": str(e)}


def run_elevated_json(command: str, timeout: int = 30) -> dict:
    """
    Run a PowerShell command that returns JSON, parse and return the result.
    Wraps run_elevated with JSON parsing.
    """
    result = run_elevated(command, timeout)
    if "error" in result:
        return result
    try:
        parsed = json.loads(result.get("stdout", "{}"))
        return parsed
    except json.JSONDecodeError:
        return result
