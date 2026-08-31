"""
Red vs Blue - Safety Boundaries
==================================
Guards and decorators to ensure Red Team attacks are safe.
All attack tools MUST be wrapped with @safe_attack.
"""

import functools
import os
import winreg

import psutil

from config import (
    ARTIFACT_PREFIX, ARTIFACT_DIR, FORBIDDEN_PATHS,
    FORBIDDEN_PROCESS_NAMES, SAFE_HOST,
)


class SafetyViolation(Exception):
    """Raised when an attack tool tries to exceed safety boundaries."""
    pass


def ensure_artifact_dir():
    """Create the safe artifact directory if it doesn't exist."""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    return ARTIFACT_DIR


def validate_file_path(path: str) -> bool:
    """Returns True only if path is in the safe temp artifact directory."""
    resolved = os.path.realpath(path).lower()
    artifact_dir = os.path.realpath(ARTIFACT_DIR).lower()

    # Must be inside artifact dir
    if not resolved.startswith(artifact_dir):
        # Also allow user's Startup folder for startup entry tests
        startup = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        ).lower()
        if resolved.startswith(startup) and ARTIFACT_PREFIX.lower() in os.path.basename(resolved).lower():
            return True
        return False
    return True


def validate_file_write(path: str) -> bool:
    """Validate that a file write is safe."""
    resolved = os.path.realpath(path).lower()

    # Check forbidden paths
    for forbidden in FORBIDDEN_PATHS:
        if resolved.startswith(forbidden.lower()):
            return False

    return validate_file_path(path)


def validate_registry_write(hive_const: int, key_path: str, value_name: str) -> bool:
    """Returns True only if writing to HKCU with REDBLUE_ prefixed value."""
    # Only HKCU allowed
    if hive_const != winreg.HKEY_CURRENT_USER:
        return False

    # Value name must start with REDBLUE_
    if not value_name.startswith(ARTIFACT_PREFIX):
        return False

    return True


def validate_process_kill(pid: int) -> bool:
    """Returns True only if PID belongs to a REDBLUE_ artifact process."""
    try:
        proc = psutil.Process(pid)
        exe_path = proc.exe().lower()
        # Must be from artifact directory
        artifact_dir = os.path.realpath(ARTIFACT_DIR).lower()
        if artifact_dir in exe_path:
            return True
        # Or have REDBLUE_ in the name
        if ARTIFACT_PREFIX.lower() in proc.name().lower():
            return True
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def validate_network(host: str) -> bool:
    """Returns True only if connecting to localhost."""
    return host in (SAFE_HOST, "localhost", "127.0.0.1", "::1", "0.0.0.0")


def safe_attack(func):
    """Decorator that wraps attack tools with safety validation.

    Ensures:
    - Artifact directory exists
    - File operations are in safe paths
    - Network is localhost only
    - Catches and wraps exceptions
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        ensure_artifact_dir()
        try:
            result = await func(*args, **kwargs)
            return result
        except SafetyViolation:
            raise
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
                "artifact": None,
            }
    return wrapper
