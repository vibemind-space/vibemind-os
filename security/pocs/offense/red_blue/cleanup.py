"""
Red vs Blue - Artifact Cleanup
==================================
Cleans up all REDBLUE_ artifacts after each round and session.
Three levels: per-artifact, per-round, and failsafe sweep.
"""

import json
import os
import shutil
import subprocess
import winreg

import psutil

from config import ARTIFACT_PREFIX, ARTIFACT_DIR, SAFE_REGISTRY_KEY


async def cleanup_artifact(artifact: dict) -> bool:
    """Clean up a single artifact. Returns True on success."""
    a_type = artifact.get("type", "")
    try:
        if a_type == "process":
            pid = artifact.get("pid")
            if pid:
                try:
                    proc = psutil.Process(pid)
                    proc.kill()
                    proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
            path = artifact.get("path", "")
            if path and os.path.exists(path) and ARTIFACT_PREFIX in path:
                os.remove(path)
            # Clean extra files
            for f in artifact.get("extra_files", []):
                if os.path.exists(f):
                    os.remove(f)

        elif a_type == "file":
            path = artifact.get("path", "")
            if path and os.path.exists(path) and os.path.isfile(path):
                os.remove(path)
            # Clean extra files (e.g. data destruction artifacts)
            for f in artifact.get("extra_files", []):
                if os.path.exists(f) and os.path.isfile(f):
                    os.remove(f)

        elif a_type == "encrypted_files":
            # Ransomware sim: delete all REDBLUE_ files in the directory
            dir_path = artifact.get("path", ARTIFACT_DIR)
            if os.path.isdir(dir_path):
                for f in os.listdir(dir_path):
                    if f.startswith(ARTIFACT_PREFIX):
                        try:
                            os.remove(os.path.join(dir_path, f))
                        except Exception:
                            pass

        elif a_type == "registry":
            hive_name = artifact.get("hive", "HKCU")
            key_path = artifact.get("key_path") or artifact.get("key", SAFE_REGISTRY_KEY)
            value_name = artifact.get("value_name", "")
            # Clean extra files if present (e.g. service exploitation dummy binaries)
            for f in artifact.get("extra_files", []):
                if os.path.exists(f) and os.path.isfile(f):
                    os.remove(f)
            if value_name and value_name.startswith(ARTIFACT_PREFIX):
                hive = winreg.HKEY_CURRENT_USER if hive_name == "HKCU" else None
                if hive:
                    try:
                        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
                        winreg.DeleteValue(key, value_name)
                        winreg.CloseKey(key)
                    except FileNotFoundError:
                        pass

        elif a_type == "scheduled_task":
            task_name = artifact.get("task_name", "")
            if task_name and task_name.startswith(ARTIFACT_PREFIX):
                subprocess.run(
                    ["schtasks.exe", "/delete", "/tn", task_name, "/f"],
                    capture_output=True, timeout=10,
                )

        elif a_type in ("socket", "beaconing", "exfiltration"):
            # Sockets are cleaned by reference — they may already be closed
            pass

        return True

    except Exception as e:
        print(f"  [CLEANUP] Warning: {a_type} cleanup failed: {e}", flush=True)
        return False


async def cleanup_round(artifacts_json: str):
    """Clean up all artifacts from a round."""
    try:
        artifacts = json.loads(artifacts_json)
    except (json.JSONDecodeError, TypeError):
        artifacts = []

    cleaned = 0
    for artifact in artifacts:
        if await cleanup_artifact(artifact):
            cleaned += 1

    print(f"  [CLEANUP] Round cleanup: {cleaned}/{len(artifacts)} artifacts removed.", flush=True)


async def cleanup_by_prefix():
    """Failsafe: sweep for ALL REDBLUE_ artifacts regardless of tracking.

    This runs at session end to catch anything missed.
    """
    print("  [CLEANUP] Running failsafe sweep...", flush=True)
    cleaned = 0

    # 1. Kill REDBLUE_ processes
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = proc.info.get("exe", "") or ""
            name = proc.info.get("name", "") or ""
            if ARTIFACT_PREFIX.lower() in exe.lower() or ARTIFACT_PREFIX.lower() in name.lower():
                proc.kill()
                cleaned += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 2. Delete artifact directory
    if os.path.exists(ARTIFACT_DIR):
        try:
            shutil.rmtree(ARTIFACT_DIR, ignore_errors=True)
            cleaned += 1
        except Exception:
            pass

    # 3. Clean REDBLUE_ registry entries
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, SAFE_REGISTRY_KEY,
            0, winreg.KEY_ALL_ACCESS,
        )
        i = 0
        to_delete = []
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                if name.startswith(ARTIFACT_PREFIX):
                    to_delete.append(name)
                i += 1
            except OSError:
                break
        for name in to_delete:
            try:
                winreg.DeleteValue(key, name)
                cleaned += 1
            except Exception:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

    # 4. Delete REDBLUE_ scheduled tasks
    try:
        result = subprocess.run(
            ["schtasks.exe", "/query", "/fo", "CSV", "/nh"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().strip('"').split('","')
            if parts and ARTIFACT_PREFIX in parts[0]:
                task_name = parts[0].strip('"').strip("\\")
                subprocess.run(
                    ["schtasks.exe", "/delete", "/tn", task_name, "/f"],
                    capture_output=True, timeout=10,
                )
                cleaned += 1
    except Exception:
        pass

    # 5. Clean Startup folder
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs\Startup",
    )
    if os.path.exists(startup_dir):
        for f in os.listdir(startup_dir):
            if f.startswith(ARTIFACT_PREFIX):
                try:
                    os.remove(os.path.join(startup_dir, f))
                    cleaned += 1
                except Exception:
                    pass

    print(f"  [CLEANUP] Failsafe sweep: {cleaned} items cleaned.", flush=True)
