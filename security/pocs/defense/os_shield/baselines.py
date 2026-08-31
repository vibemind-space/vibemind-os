"""
Baseline State Capture
=======================
Captures the "known good" system state so the LLM can detect deviations.
Baselines are stored as JSON and passed to tools for comparison.
"""

import asyncio
import json
import os
from datetime import datetime

import psutil

from config import AUTORUN_KEYS, HIVE_NAMES


async def capture_baseline() -> dict:
    """Capture current system state as baseline."""
    print("  [BASELINE] Capturing system state...", flush=True)

    baseline = {
        "timestamp": datetime.now().isoformat(),
        "process_pids": [],
        "known_remote_ips": [],
        "autorun_entries": [],
        "usb_device_ids": [],
    }

    # 1. Process PIDs
    for proc in psutil.process_iter(["pid"]):
        try:
            baseline["process_pids"].append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    print(f"    Processes: {len(baseline['process_pids'])}", flush=True)

    # 2. Known remote IPs (currently connected)
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.raddr and conn.status == "ESTABLISHED":
                ip = conn.raddr.ip
                if not ip.startswith("127.") and ip != "::1":
                    if ip not in baseline["known_remote_ips"]:
                        baseline["known_remote_ips"].append(ip)
    except psutil.AccessDenied:
        print("    Network: Access denied (run as Admin)", flush=True)
    print(f"    Known Remote IPs: {len(baseline['known_remote_ips'])}", flush=True)

    # 3. Autorun entries
    import winreg
    for hive, key_path in AUTORUN_KEYS:
        hive_name = HIVE_NAMES.get(hive, str(hive))
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, value, vtype = winreg.EnumValue(key, i)
                    baseline["autorun_entries"].append({
                        "hive": hive_name,
                        "key_path": key_path,
                        "value_name": name,
                        "value_data": str(value)[:500],
                    })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (FileNotFoundError, PermissionError):
            continue
    print(f"    Autorun entries: {len(baseline['autorun_entries'])}", flush=True)

    # 4. USB device IDs
    try:
        import wmi
        import pythoncom
        pythoncom.CoInitialize()
        c = wmi.WMI()
        for device in c.Win32_PnPEntity():
            did = device.DeviceID or ""
            if "USB" in did.upper():
                baseline["usb_device_ids"].append(did)
        pythoncom.CoUninitialize()
    except ImportError:
        print("    USB: wmi not installed, skipping", flush=True)
    except Exception as e:
        print(f"    USB: {e}", flush=True)
    print(f"    USB devices: {len(baseline['usb_device_ids'])}", flush=True)

    print("  [BASELINE] Capture complete.", flush=True)
    return baseline


async def save_baseline(baseline: dict, path: str) -> None:
    """Save baseline to JSON file."""
    def _write():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)

    await asyncio.get_event_loop().run_in_executor(None, _write)
    print(f"  [BASELINE] Saved to {path}", flush=True)


async def load_baseline(path: str) -> dict | None:
    """Load baseline from JSON file, return None if not found."""
    if not os.path.exists(path):
        return None

    def _read():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    baseline = await asyncio.get_event_loop().run_in_executor(None, _read)
    print(f"  [BASELINE] Loaded from {path} ({baseline['timestamp']})", flush=True)
    return baseline
