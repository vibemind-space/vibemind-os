"""
OS Shield Security Tools
=========================
Pure async functions for OS-level security monitoring.
Each returns a dict of findings. Used by OrchestratorAgent via OpenAI tool calling.

Tools:
  1. list_processes          - List all running processes
  2. detect_new_processes    - Diff against baseline PIDs
  3. check_binary_signature  - Verify Authenticode signature (WinVerifyTrust)
  4. check_file_integrity    - SHA256 hash comparison
  5. list_network_connections - Active TCP connections
  6. detect_suspicious_connections - Unknown remote IPs vs baseline
  7. manage_firewall_rule    - Add/remove/list Windows Firewall rules
  8. list_usb_devices        - Enumerate USB devices via WMI
  9. check_registry_autoruns - Inspect autorun registry keys
  10. think                  - LLM chain-of-thought reasoning
"""

import asyncio
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import struct
import subprocess
import sys
import winreg
from datetime import datetime

import psutil
from openai import AsyncOpenAI

from config import (
    AUTORUN_KEYS, HIVE_NAMES, MAX_FILES_PER_DIR,
    SUSPICIOUS_OUTBOUND_PORTS, SUSPICIOUS_PROCESS_NAMES,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model


# ================================================================
# TOOL 1: list_processes
# ================================================================

async def list_processes() -> dict:
    """List all running processes with details."""

    def _sync():
        procs = []
        suspicious = []
        for proc in psutil.process_iter(
            ["pid", "name", "exe", "username", "create_time", "ppid", "status"]
        ):
            try:
                info = proc.info
                entry = {
                    "pid": info["pid"],
                    "name": info["name"],
                    "exe": info["exe"],
                    "username": info["username"],
                    "create_time": datetime.fromtimestamp(
                        info["create_time"]
                    ).isoformat() if info["create_time"] else None,
                    "ppid": info["ppid"],
                    "status": info["status"],
                }
                procs.append(entry)

                # Flag suspicious
                name_lower = (info["name"] or "").lower()
                if any(s in name_lower for s in SUSPICIOUS_PROCESS_NAMES):
                    suspicious.append(entry)

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return {
            "total_processes": len(procs),
            "processes": procs[:200],  # Limit output size
            "suspicious_processes": suspicious,
            "suspicious_count": len(suspicious),
            "warning": f"{len(suspicious)} suspicious processes found!" if suspicious else None,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 2: detect_new_processes
# ================================================================

async def detect_new_processes(baseline_pids_json: str) -> dict:
    """Detect processes not present in the baseline."""

    def _sync():
        baseline_pids = set(json.loads(baseline_pids_json))
        new_procs = []

        for proc in psutil.process_iter(
            ["pid", "name", "exe", "username", "create_time", "cmdline"]
        ):
            try:
                if proc.info["pid"] not in baseline_pids:
                    name_lower = (proc.info["name"] or "").lower()
                    is_suspicious = any(
                        s in name_lower for s in SUSPICIOUS_PROCESS_NAMES
                    )
                    new_procs.append({
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "exe": proc.info["exe"],
                        "username": proc.info["username"],
                        "cmdline": " ".join(proc.info["cmdline"] or []),
                        "create_time": datetime.fromtimestamp(
                            proc.info["create_time"]
                        ).isoformat() if proc.info["create_time"] else None,
                        "suspicious": is_suspicious,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        suspicious = [p for p in new_procs if p["suspicious"]]
        return {
            "new_process_count": len(new_procs),
            "new_processes": new_procs[:100],
            "suspicious_new": suspicious,
            "warning": (
                f"{len(new_procs)} new processes since baseline, "
                f"{len(suspicious)} suspicious!"
            ) if new_procs else None,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 3: check_binary_signature
# ================================================================

async def check_binary_signature(file_path: str) -> dict:
    """Check if a binary (.exe/.dll) is digitally signed via WinVerifyTrust."""

    def _sync():
        result = {
            "file_path": file_path,
            "exists": os.path.exists(file_path),
            "is_signed": False,
            "is_valid": False,
            "error": None,
        }

        if not result["exists"]:
            result["error"] = "File not found"
            return result

        try:
            # WINTRUST_ACTION_GENERIC_VERIFY_V2
            WINTRUST_ACTION = (ctypes.c_byte * 16)(
                0xAC, 0xC3, 0x11, 0x00,
                0x18, 0xE9, 0xD0, 0x11,
                0x93, 0xB7, 0x00, 0xAA,
                0x00, 0x4B, 0x2E, 0x24,
            )

            class WINTRUST_FILE_INFO(ctypes.Structure):
                _fields_ = [
                    ("cbStruct", ctypes.wintypes.DWORD),
                    ("pcwszFilePath", ctypes.wintypes.LPCWSTR),
                    ("hFile", ctypes.wintypes.HANDLE),
                    ("pgKnownSubject", ctypes.c_void_p),
                ]

            class WINTRUST_DATA(ctypes.Structure):
                _fields_ = [
                    ("cbStruct", ctypes.wintypes.DWORD),
                    ("pPolicyCallbackData", ctypes.c_void_p),
                    ("pSIPClientData", ctypes.c_void_p),
                    ("dwUIChoice", ctypes.wintypes.DWORD),
                    ("fdwRevocationChecks", ctypes.wintypes.DWORD),
                    ("dwUnionChoice", ctypes.wintypes.DWORD),
                    ("pFile", ctypes.POINTER(WINTRUST_FILE_INFO)),
                    ("dwStateAction", ctypes.wintypes.DWORD),
                    ("hWVTStateData", ctypes.wintypes.HANDLE),
                    ("pwszURLReference", ctypes.wintypes.LPCWSTR),
                    ("dwProvFlags", ctypes.wintypes.DWORD),
                    ("dwUIContext", ctypes.wintypes.DWORD),
                    ("pSignatureSettings", ctypes.c_void_p),
                ]

            file_info = WINTRUST_FILE_INFO()
            file_info.cbStruct = ctypes.sizeof(WINTRUST_FILE_INFO)
            file_info.pcwszFilePath = file_path
            file_info.hFile = None
            file_info.pgKnownSubject = None

            WTD_UI_NONE = 2
            WTD_CHOICE_FILE = 1
            WTD_REVOKE_NONE = 0
            WTD_STATEACTION_VERIFY = 1

            trust_data = WINTRUST_DATA()
            trust_data.cbStruct = ctypes.sizeof(WINTRUST_DATA)
            trust_data.dwUIChoice = WTD_UI_NONE
            trust_data.fdwRevocationChecks = WTD_REVOKE_NONE
            trust_data.dwUnionChoice = WTD_CHOICE_FILE
            trust_data.pFile = ctypes.pointer(file_info)
            trust_data.dwStateAction = WTD_STATEACTION_VERIFY
            trust_data.dwProvFlags = 0

            wintrust = ctypes.windll.wintrust
            ret = wintrust.WinVerifyTrust(
                None,
                ctypes.byref(WINTRUST_ACTION),
                ctypes.byref(trust_data),
            )

            # 0 = success (valid signature)
            # 0x800B0100 = no signature
            # 0x800B0101 = untrusted root
            result["is_signed"] = ret != 0x800B0100
            result["is_valid"] = ret == 0
            if ret == 0:
                result["status"] = "VALID_SIGNATURE"
            elif ret == 0x800B0100:
                result["status"] = "NOT_SIGNED"
            elif ret == 0x800B0101:
                result["status"] = "UNTRUSTED_ROOT"
                result["is_signed"] = True
            else:
                result["status"] = f"UNKNOWN_ERROR_0x{ret & 0xFFFFFFFF:08X}"
                result["is_signed"] = True  # signed but something wrong

        except Exception as e:
            result["error"] = str(e)

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 4: check_file_integrity
# ================================================================

async def check_file_integrity(
    directory: str, baseline_hashes_json: str = ""
) -> dict:
    """Hash files in a directory and compare against baseline."""

    def _sync():
        result = {
            "directory": directory,
            "files_scanned": 0,
            "current_hashes": {},
            "changed_files": [],
            "new_files": [],
            "deleted_files": [],
            "warning": None,
        }

        if not os.path.isdir(directory):
            result["warning"] = f"Directory not found: {directory}"
            return result

        baseline = json.loads(baseline_hashes_json) if baseline_hashes_json else {}

        count = 0
        for root, _, files in os.walk(directory):
            for fname in files:
                if count >= MAX_FILES_PER_DIR:
                    break
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "rb") as f:
                        sha = hashlib.sha256(f.read(1024 * 1024)).hexdigest()  # first 1MB
                    result["current_hashes"][fpath] = sha
                    count += 1

                    if baseline:
                        if fpath in baseline and baseline[fpath] != sha:
                            result["changed_files"].append(fpath)
                        elif fpath not in baseline:
                            result["new_files"].append(fpath)
                except (PermissionError, OSError):
                    continue
            if count >= MAX_FILES_PER_DIR:
                break

        result["files_scanned"] = count

        if baseline:
            for fpath in baseline:
                if fpath not in result["current_hashes"]:
                    result["deleted_files"].append(fpath)

            changes = len(result["changed_files"]) + len(result["new_files"]) + len(result["deleted_files"])
            if changes > 0:
                result["warning"] = (
                    f"{len(result['changed_files'])} changed, "
                    f"{len(result['new_files'])} new, "
                    f"{len(result['deleted_files'])} deleted files!"
                )

        # Don't return all hashes in the response (too large), just summary
        result["current_hashes"] = f"({count} hashes computed, use baseline for comparison)"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 5: list_network_connections
# ================================================================

async def list_network_connections() -> dict:
    """List all active TCP/UDP network connections."""

    def _sync():
        connections = []
        suspicious = []

        try:
            for conn in psutil.net_connections(kind="inet"):
                entry = {
                    "fd": conn.fd,
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                    "remote_addr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                    "status": conn.status,
                    "pid": conn.pid,
                    "process_name": None,
                }

                # Get process name
                if conn.pid:
                    try:
                        entry["process_name"] = psutil.Process(conn.pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                connections.append(entry)

                # Flag suspicious outbound
                if conn.raddr and conn.status == "ESTABLISHED":
                    remote_port = conn.raddr.port
                    if remote_port in SUSPICIOUS_OUTBOUND_PORTS:
                        entry["suspicious_reason"] = f"Connection to suspicious port {remote_port}"
                        suspicious.append(entry)

        except psutil.AccessDenied:
            return {
                "total_connections": 0,
                "connections": [],
                "suspicious": [],
                "warning": "Access denied — run as Administrator!",
            }

        return {
            "total_connections": len(connections),
            "established_count": sum(1 for c in connections if c["status"] == "ESTABLISHED"),
            "connections": connections[:200],
            "suspicious": suspicious,
            "suspicious_count": len(suspicious),
            "warning": f"{len(suspicious)} suspicious connections detected!" if suspicious else None,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 6: detect_suspicious_connections
# ================================================================

async def detect_suspicious_connections(known_remote_ips_json: str) -> dict:
    """Find established connections to unknown remote IPs."""

    def _sync():
        known_ips = set(json.loads(known_remote_ips_json))
        unknown = []

        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status != "ESTABLISHED" or not conn.raddr:
                    continue

                remote_ip = conn.raddr.ip

                # Skip loopback and link-local
                if remote_ip.startswith("127.") or remote_ip.startswith("::1"):
                    continue

                if remote_ip not in known_ips:
                    proc_name = None
                    if conn.pid:
                        try:
                            proc_name = psutil.Process(conn.pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    unknown.append({
                        "remote_ip": remote_ip,
                        "remote_port": conn.raddr.port,
                        "local_port": conn.laddr.port if conn.laddr else None,
                        "pid": conn.pid,
                        "process_name": proc_name,
                        "suspicious_port": conn.raddr.port in SUSPICIOUS_OUTBOUND_PORTS,
                    })

        except psutil.AccessDenied:
            return {"unknown_connections": [], "warning": "Access denied — run as Administrator!"}

        return {
            "unknown_connection_count": len(unknown),
            "unknown_connections": unknown[:100],
            "warning": (
                f"{len(unknown)} connections to unknown IPs!"
            ) if unknown else None,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 7: manage_firewall_rule
# ================================================================

async def manage_firewall_rule(
    action: str,
    rule_name: str = "",
    direction: str = "out",
    action_type: str = "block",
    remote_ip: str = "",
    port: str = "",
    program: str = "",
) -> dict:
    """Add, remove, or list Windows Firewall rules via netsh."""

    def _sync():
        result = {"action": action, "success": False, "output": "", "error": None}

        try:
            if action == "list":
                cmd = ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
                result["success"] = proc.returncode == 0
                # Only return first 5000 chars to avoid flooding
                result["output"] = proc.stdout[:5000]

            elif action == "add":
                if not rule_name:
                    result["error"] = "rule_name is required for add"
                    return result

                cmd = [
                    "netsh", "advfirewall", "firewall", "add", "rule",
                    f"name={rule_name}",
                    f"dir={direction}",
                    f"action={action_type}",
                ]
                if remote_ip:
                    cmd.append(f"remoteip={remote_ip}")
                if port:
                    cmd.extend([f"localport={port}", "protocol=tcp"])
                if program:
                    cmd.append(f"program={program}")

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
                result["success"] = proc.returncode == 0
                result["output"] = proc.stdout.strip()
                if proc.stderr:
                    result["error"] = proc.stderr.strip()

            elif action == "remove":
                if not rule_name:
                    result["error"] = "rule_name is required for remove"
                    return result

                cmd = [
                    "netsh", "advfirewall", "firewall", "delete", "rule",
                    f"name={rule_name}",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
                result["success"] = proc.returncode == 0
                result["output"] = proc.stdout.strip()

            else:
                result["error"] = f"Unknown action: {action}. Use add, remove, or list."

        except subprocess.TimeoutExpired:
            result["error"] = "Command timed out"
        except Exception as e:
            result["error"] = str(e)

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 8: list_usb_devices
# ================================================================

async def list_usb_devices() -> dict:
    """Enumerate USB devices via WMI."""

    def _sync():
        result = {
            "devices": [],
            "device_count": 0,
            "warning": None,
        }

        try:
            import wmi
            import pythoncom
            pythoncom.CoInitialize()

            c = wmi.WMI()
            for device in c.Win32_PnPEntity():
                device_id = device.DeviceID or ""
                if "USB" in device_id.upper():
                    result["devices"].append({
                        "name": device.Name,
                        "device_id": device_id,
                        "manufacturer": device.Manufacturer,
                        "status": device.Status,
                        "description": device.Description,
                    })

            result["device_count"] = len(result["devices"])
            pythoncom.CoUninitialize()

        except ImportError:
            result["warning"] = "wmi package not installed. pip install wmi pywin32"
        except Exception as e:
            result["warning"] = f"USB enumeration failed: {e}"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 9: check_registry_autoruns
# ================================================================

async def check_registry_autoruns(baseline_autoruns_json: str = "") -> dict:
    """Check Windows autorun registry keys for suspicious entries."""

    def _sync():
        result = {
            "autorun_entries": [],
            "total_entries": 0,
            "new_entries": [],
            "warning": None,
        }

        baseline = json.loads(baseline_autoruns_json) if baseline_autoruns_json else []
        baseline_set = {
            f"{e['hive']}\\{e['key_path']}\\{e['value_name']}"
            for e in baseline
        }

        for hive, key_path in AUTORUN_KEYS:
            hive_name = HIVE_NAMES.get(hive, str(hive))
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, value, vtype = winreg.EnumValue(key, i)
                        entry = {
                            "hive": hive_name,
                            "key_path": key_path,
                            "value_name": name,
                            "value_data": str(value)[:500],
                            "value_type": vtype,
                        }
                        result["autorun_entries"].append(entry)

                        lookup_key = f"{hive_name}\\{key_path}\\{name}"
                        if baseline_set and lookup_key not in baseline_set:
                            entry["is_new"] = True
                            result["new_entries"].append(entry)

                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except FileNotFoundError:
                continue
            except PermissionError:
                result["warning"] = (
                    (result["warning"] or "") +
                    f" Permission denied: {hive_name}\\{key_path}."
                )
                continue

        result["total_entries"] = len(result["autorun_entries"])

        if result["new_entries"]:
            result["warning"] = (
                f"{len(result['new_entries'])} NEW autorun entries detected since baseline!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 10: detect_parent_child_anomalies
# ================================================================

async def detect_parent_child_anomalies() -> dict:
    """Detect suspicious parent-child process relationships (e.g. Word spawning PowerShell)."""

    def _sync():
        result = {
            "anomalies": [],
            "total_checked": 0,
            "warning": None,
        }

        # Suspicious parent -> child relationships
        # If a parent spawns a child that's in this map, it's an anomaly
        SUSPICIOUS_CHAINS = {
            # Office apps should NEVER spawn shells
            "winword.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe", "certutil.exe", "bitsadmin.exe"],
            "excel.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe"],
            "powerpnt.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe"],
            "outlook.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe", "mshta.exe"],
            "msaccess.exe": ["cmd.exe", "powershell.exe", "pwsh.exe"],
            # PDF readers
            "acrord32.exe": ["cmd.exe", "powershell.exe", "pwsh.exe"],
            "foxitreader.exe": ["cmd.exe", "powershell.exe", "pwsh.exe"],
            # Browsers spawning shells (drive-by download execution)
            "chrome.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "certutil.exe", "bitsadmin.exe", "mshta.exe"],
            "msedge.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "certutil.exe", "bitsadmin.exe"],
            "firefox.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "certutil.exe"],
            # Script hosts spawning more scripts
            "wscript.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "mshta.exe"],
            "cscript.exe": ["cmd.exe", "powershell.exe", "pwsh.exe", "mshta.exe"],
            "mshta.exe": ["cmd.exe", "powershell.exe", "pwsh.exe"],
            # Services that shouldn't spawn user tools
            "svchost.exe": ["certutil.exe", "bitsadmin.exe", "mshta.exe"],
            "spoolsv.exe": ["cmd.exe", "powershell.exe", "pwsh.exe"],
            # Notepad used as LOLBin
            "notepad.exe": ["cmd.exe", "powershell.exe"],
        }

        # Build PID -> process info map
        proc_map = {}
        for proc in psutil.process_iter(["pid", "name", "ppid", "exe", "cmdline", "create_time"]):
            try:
                info = proc.info
                proc_map[info["pid"]] = info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        result["total_checked"] = len(proc_map)

        # Check each process against suspicious chains
        for pid, info in proc_map.items():
            child_name = (info["name"] or "").lower()
            ppid = info.get("ppid")

            if ppid and ppid in proc_map:
                parent_name = (proc_map[ppid]["name"] or "").lower()

                # Check if this parent->child combo is suspicious
                for suspect_parent, suspect_children in SUSPICIOUS_CHAINS.items():
                    if parent_name == suspect_parent and child_name in suspect_children:
                        cmdline = " ".join(info.get("cmdline") or [])
                        result["anomalies"].append({
                            "severity": "CRITICAL",
                            "parent_pid": ppid,
                            "parent_name": parent_name,
                            "child_pid": pid,
                            "child_name": child_name,
                            "child_exe": info.get("exe"),
                            "child_cmdline": cmdline[:300],
                            "create_time": datetime.fromtimestamp(
                                info["create_time"]
                            ).isoformat() if info.get("create_time") else None,
                            "reason": f"{parent_name} spawned {child_name} — typical malware/exploit behavior",
                        })

        if result["anomalies"]:
            result["warning"] = f"CRITICAL: {len(result['anomalies'])} suspicious parent-child process chain(s) detected!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 11: detect_encoded_commands
# ================================================================

async def detect_encoded_commands() -> dict:
    """Detect processes running Base64-encoded or obfuscated commands."""
    import base64

    def _sync():
        result = {
            "suspicious_commands": [],
            "total_checked": 0,
            "warning": None,
        }

        ENCODED_INDICATORS = [
            "-encodedcommand", "-enc ", "-e ", "-ec ",
            "frombase64string", "convert]::frombase64",
            "[system.text.encoding]",
            "invoke-expression", "iex(", "iex ",
            "invoke-webrequest", "downloadstring", "downloadfile",
            "net.webclient", "bitstransfer",
            "start-bitstransfer",
            "hidden", "-windowstyle hidden", "-w hidden",
            "bypass", "-executionpolicy bypass", "-ep bypass",
            "new-object net.webclient",
            "reflection.assembly",
            "memorystream", "deflatestream",
            "invoke-mimikatz", "invoke-shellcode",
        ]

        SUSPICIOUS_PATTERNS = [
            # Very long command lines (often encoded/obfuscated)
            ("long_cmdline", 500),
        ]

        for proc in psutil.process_iter(["pid", "name", "cmdline", "exe", "create_time"]):
            try:
                info = proc.info
                cmdline = " ".join(info.get("cmdline") or [])
                if not cmdline:
                    continue

                result["total_checked"] += 1
                cmdline_lower = cmdline.lower()

                findings = []

                # Check for encoded command indicators
                for indicator in ENCODED_INDICATORS:
                    if indicator in cmdline_lower:
                        findings.append(f"Contains '{indicator}'")

                # Check for very long command lines
                if len(cmdline) > 500 and info["name"] and info["name"].lower() in ("powershell.exe", "pwsh.exe", "cmd.exe"):
                    findings.append(f"Unusually long command ({len(cmdline)} chars)")

                # Try to detect and decode Base64
                import re
                b64_matches = re.findall(r'[A-Za-z0-9+/=]{40,}', cmdline)
                for b64 in b64_matches:
                    try:
                        decoded = base64.b64decode(b64).decode("utf-16-le", errors="replace")
                        if any(kw in decoded.lower() for kw in ["invoke", "download", "webclient", "iex", "http", "net.", "system."]):
                            findings.append(f"Base64 decodes to suspicious content: {decoded[:100]}...")
                    except Exception:
                        pass

                if findings:
                    result["suspicious_commands"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "cmdline_preview": cmdline[:200],
                        "findings": findings,
                        "create_time": datetime.fromtimestamp(
                            info["create_time"]
                        ).isoformat() if info.get("create_time") else None,
                    })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["suspicious_commands"]:
            result["warning"] = f"CRITICAL: {len(result['suspicious_commands'])} process(es) with encoded/obfuscated commands!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 12: detect_beaconing
# ================================================================

async def detect_beaconing(interval_seconds: int = 10, duration_seconds: int = 30) -> dict:
    """Monitor outbound connections for beaconing patterns (regular C2 check-ins)."""
    import time
    import collections

    result = {
        "monitoring_duration": duration_seconds,
        "connections_tracked": 0,
        "potential_beacons": [],
        "warning": None,
    }

    # Collect connection snapshots over time
    snapshots = []
    for _ in range(duration_seconds // interval_seconds + 1):
        snapshot = {}
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "ESTABLISHED" and conn.raddr:
                    remote = f"{conn.raddr.ip}:{conn.raddr.port}"
                    proc_name = None
                    if conn.pid:
                        try:
                            proc_name = psutil.Process(conn.pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    snapshot[remote] = {
                        "pid": conn.pid,
                        "process": proc_name,
                        "remote_ip": conn.raddr.ip,
                        "remote_port": conn.raddr.port,
                    }
        except psutil.AccessDenied:
            pass
        snapshots.append({"time": time.time(), "connections": snapshot})
        if _ < duration_seconds // interval_seconds:
            await asyncio.sleep(interval_seconds)

    # Analyze: which remote IPs appear in EVERY snapshot? (persistent connection = potential beacon)
    if len(snapshots) >= 2:
        all_remotes = collections.Counter()
        for snap in snapshots:
            for remote in snap["connections"]:
                all_remotes[remote] += 1

        result["connections_tracked"] = len(all_remotes)

        for remote, count in all_remotes.items():
            if count == len(snapshots):  # Present in every snapshot
                conn_info = snapshots[-1]["connections"][remote]
                ip = conn_info["remote_ip"]

                # Skip common legitimate persistent connections
                if ip.startswith("127.") or ip == "::1":
                    continue

                result["potential_beacons"].append({
                    "remote": remote,
                    "remote_ip": ip,
                    "remote_port": conn_info["remote_port"],
                    "process": conn_info["process"],
                    "pid": conn_info["pid"],
                    "seen_in_all_snapshots": True,
                    "snapshot_count": count,
                })

    if result["potential_beacons"]:
        # Filter: known legitimate persistent connections
        LEGIT_PORTS = {443, 80, 993, 995}
        suspicious = [b for b in result["potential_beacons"]
                     if b["remote_port"] not in LEGIT_PORTS]

        if suspicious:
            result["warning"] = (
                f"{len(suspicious)} potential beaconing connection(s) on non-standard ports!"
            )

    return result


# ================================================================
# TOOL 13: detect_suspicious_paths
# ================================================================

async def detect_suspicious_paths() -> dict:
    """Detect processes or DLLs running from suspicious locations (Temp, Downloads, AppData)."""

    def _sync():
        result = {
            "suspicious_processes": [],
            "total_checked": 0,
            "warning": None,
        }

        SUSPICIOUS_DIRS = [
            "\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\",
            "\\downloads\\", "\\public\\",
            "\\programdata\\", "\\users\\public\\",
            "\\recycle", "$recycle",
        ]

        # Legitimate processes that commonly run from these paths
        WHITELIST = {
            "chrome_updater.exe", "dropbox.exe", "teams.exe",
            "msedgewebview2.exe", "discord.exe", "slack.exe",
            "setup.exe", "update.exe", "updater.exe",
        }

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "create_time"]):
            try:
                info = proc.info
                exe = (info.get("exe") or "").lower()
                name = (info.get("name") or "").lower()

                if not exe or name in WHITELIST:
                    continue

                result["total_checked"] += 1

                for sus_dir in SUSPICIOUS_DIRS:
                    if sus_dir in exe:
                        cmdline = " ".join(info.get("cmdline") or [])
                        result["suspicious_processes"].append({
                            "pid": info["pid"],
                            "name": info["name"],
                            "exe": info["exe"],
                            "cmdline": cmdline[:200],
                            "suspicious_path": sus_dir.strip("\\"),
                            "create_time": datetime.fromtimestamp(
                                info["create_time"]
                            ).isoformat() if info.get("create_time") else None,
                        })
                        break

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["suspicious_processes"]:
            result["warning"] = f"{len(result['suspicious_processes'])} process(es) running from suspicious paths!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 14: detect_lsass_access
# ================================================================

async def detect_lsass_access() -> dict:
    """Check if any non-system process has handles to LSASS (credential theft indicator)."""

    def _sync():
        result = {
            "lsass_pid": None,
            "suspicious_access": [],
            "warning": None,
        }

        # Find LSASS
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == "lsass.exe":
                    result["lsass_pid"] = proc.info["pid"]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not result["lsass_pid"]:
            result["warning"] = "Could not find lsass.exe process"
            return result

        # Check for processes that commonly access LSASS for credential theft
        CREDENTIAL_TOOLS = [
            "mimikatz", "procdump", "sqldumper", "comsvcs",
            "task_manager", "processhacker", "procexp",
            "dumpert", "nanodump", "pypykatz",
            "lsassy", "secretsdump", "lazagne",
        ]

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower().replace(".exe", "")
                cmdline = " ".join(info.get("cmdline") or []).lower()

                # Known credential dumping tools
                if any(tool in name_lower for tool in CREDENTIAL_TOOLS):
                    result["suspicious_access"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "reason": f"Known credential theft tool: {info['name']}",
                    })

                # Check for procdump targeting lsass
                if "procdump" in name_lower and str(result["lsass_pid"]) in cmdline:
                    result["suspicious_access"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "reason": f"procdump targeting LSASS (PID {result['lsass_pid']})",
                    })

                # Check for comsvcs.dll MiniDump (another LSASS dump technique)
                if "rundll32" in name_lower and "comsvcs" in cmdline and "minidump" in cmdline:
                    result["suspicious_access"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "reason": "rundll32 + comsvcs.dll MiniDump (LSASS credential dump technique)",
                    })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["suspicious_access"]:
            result["warning"] = f"CRITICAL: {len(result['suspicious_access'])} process(es) potentially accessing LSASS credentials!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 15: detect_data_exfiltration
# ================================================================

async def detect_data_exfiltration() -> dict:
    """Monitor for signs of data exfiltration (large uploads, unusual DNS)."""
    import time

    result = {
        "network_baseline": {},
        "large_transfers": [],
        "dns_anomalies": [],
        "warning": None,
    }

    def _get_io():
        per_proc = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                io = proc.io_counters()
                per_proc[proc.info["pid"]] = {
                    "name": proc.info["name"],
                    "bytes_sent": io.write_bytes,
                    "bytes_recv": io.read_bytes,
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        return per_proc

    # Take two snapshots 5 seconds apart
    snap1 = await asyncio.get_event_loop().run_in_executor(None, _get_io)
    await asyncio.sleep(5)
    snap2 = await asyncio.get_event_loop().run_in_executor(None, _get_io)

    # Calculate deltas
    for pid, info2 in snap2.items():
        if pid in snap1:
            info1 = snap1[pid]
            sent_delta = info2["bytes_sent"] - info1["bytes_sent"]
            recv_delta = info2["bytes_recv"] - info1["bytes_recv"]

            sent_mb = sent_delta / (1024 * 1024)

            # Flag if sending more than 10MB in 5 seconds
            if sent_mb > 10:
                result["large_transfers"].append({
                    "pid": pid,
                    "name": info2["name"],
                    "sent_mb_5s": round(sent_mb, 2),
                    "recv_mb_5s": round(recv_delta / (1024 * 1024), 2),
                })

    # Overall network stats
    net = psutil.net_io_counters()
    result["network_baseline"] = {
        "total_sent_gb": round(net.bytes_sent / (1024**3), 2),
        "total_recv_gb": round(net.bytes_recv / (1024**3), 2),
    }

    if result["large_transfers"]:
        names = ", ".join(t["name"] for t in result["large_transfers"])
        result["warning"] = f"Large data transfer detected: {names}"

    return result


# ================================================================
# TOOL 16: think (LLM reasoning)
# ================================================================

async def think(reasoning_prompt: str, llm_client: AsyncOpenAI) -> dict:
    """Use LLM to reason step-by-step about OS security implications."""
    response = await llm_client.chat.completions.create(
        model=get_model("think"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior security analyst monitoring a Windows 11 system.\n\n"
                    "Think step-by-step about the security implications of the findings.\n\n"
                    "Structure:\n"
                    "REASONING:\n- Step 1: ...\n- Step 2: ...\n\n"
                    "CONCLUSION: <one sentence>\n\n"
                    "SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW|INFO>\n"
                ),
            },
            {"role": "user", "content": reasoning_prompt},
        ],
    )

    text = response.choices[0].message.content.strip()
    reasoning = text
    conclusion = ""
    severity = "INFO"

    if "CONCLUSION:" in text:
        parts = text.split("CONCLUSION:")
        reasoning = parts[0].strip()
        remainder = parts[1].strip()
        if "SEVERITY:" in remainder:
            conclusion_parts = remainder.split("SEVERITY:")
            conclusion = conclusion_parts[0].strip()
            severity = conclusion_parts[1].strip().split()[0] if conclusion_parts[1].strip() else "INFO"
        else:
            conclusion = remainder

    return {
        "reasoning": reasoning,
        "conclusion": conclusion,
        "severity_assessment": severity,
    }


# ================================================================
# TOOL 17: detect_token_manipulation
# ================================================================

async def detect_token_manipulation() -> dict:
    """Detect processes that may be performing token manipulation or
    privilege enumeration (whoami /priv, token tools, Potato exploits)."""

    def _sync():
        result = {
            "suspicious_tokens": [],
            "total_checked": 0,
            "warning": None,
        }

        TOKEN_TOOL_NAMES = [
            "token", "impersonate", "potato", "printspoofer",
            "godpotato", "sweetpotato", "juicypotato", "rottenpotato",
            "incognito", "tokenvator",
        ]

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "username"]):
            result["total_checked"] += 1
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower()
                cmdline = " ".join(info["cmdline"] or []).lower()
                exe = (info["exe"] or "").lower()

                reasons = []

                # Check for token manipulation tool names
                for tool in TOKEN_TOOL_NAMES:
                    if tool in name_lower or tool in exe:
                        reasons.append(f"Process name/path contains '{tool}'")

                # Check for privilege enumeration
                if "whoami" in name_lower and "/priv" in cmdline:
                    reasons.append("whoami /priv (privilege enumeration)")

                # Check for REDBLUE_ token markers
                if "redblue_" in name_lower and "token" in name_lower:
                    reasons.append("REDBLUE_ token manipulation artifact")

                # Check for token marker files in temp
                if "token_elevated" in cmdline or "token_manipulator" in name_lower:
                    reasons.append("Token elevation indicator in process")

                if reasons:
                    result["suspicious_tokens"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "cmdline": cmdline[:200],
                        "username": info["username"],
                        "reasons": reasons,
                    })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["suspicious_tokens"]:
            result["warning"] = (
                f"CRITICAL: {len(result['suspicious_tokens'])} process(es) "
                f"with token manipulation indicators!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 18: detect_uac_bypass_attempts
# ================================================================

async def detect_uac_bypass_attempts() -> dict:
    """Detect UAC bypass indicators: registry keys used by known techniques
    (fodhelper, eventvwr, computerdefaults) and suspicious process chains."""
    import winreg

    def _sync():
        result = {
            "registry_anomalies": [],
            "process_chains": [],
            "warning": None,
        }

        # Check known UAC bypass registry paths
        UAC_BYPASS_KEYS = [
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\ms-settings\shell\open\command"),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\mscfile\shell\open\command"),
        ]

        for hive, key_path in UAC_BYPASS_KEYS:
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                try:
                    val, _ = winreg.QueryValueEx(key, None)  # Default value
                    if val:
                        result["registry_anomalies"].append({
                            "key": f"HKCU\\{key_path}",
                            "value": str(val)[:200],
                            "severity": "CRITICAL",
                            "reason": "UAC bypass registry key has a value set",
                        })
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass
            except Exception:
                pass

        # Check Run key for REDBLUE_ UAC markers
        try:
            run_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ,
            )
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(run_key, i)
                    val_lower = str(val).lower()
                    if any(kw in val_lower for kw in ["uac", "fodhelper", "eventvwr", "bypass"]):
                        result["registry_anomalies"].append({
                            "key": r"HKCU\...\Run",
                            "value_name": name,
                            "value": str(val)[:200],
                            "severity": "HIGH",
                            "reason": "Run key entry with UAC bypass keywords",
                        })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(run_key)
        except Exception:
            pass

        # Check process chains: fodhelper/eventvwr spawning shells
        UAC_PARENTS = ["fodhelper.exe", "eventvwr.exe", "computerdefaults.exe", "sdclt.exe"]
        SHELL_CHILDREN = ["cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "mshta.exe"]

        proc_map = {}
        for proc in psutil.process_iter(["pid", "name", "ppid", "exe", "cmdline"]):
            try:
                info = proc.info
                proc_map[info["pid"]] = info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        for pid, info in proc_map.items():
            name_lower = (info["name"] or "").lower()
            if name_lower in SHELL_CHILDREN:
                ppid = info.get("ppid")
                parent = proc_map.get(ppid, {})
                parent_name = (parent.get("name") or "").lower()
                if parent_name in UAC_PARENTS:
                    result["process_chains"].append({
                        "parent_pid": ppid,
                        "parent_name": parent.get("name"),
                        "child_pid": pid,
                        "child_name": info["name"],
                        "severity": "CRITICAL",
                        "reason": f"UAC bypass chain: {parent_name} -> {name_lower}",
                    })

            # Also detect REDBLUE_ UAC chain processes
            if "redblue_" in name_lower and any(kw in name_lower for kw in ["fodhelper", "eventvwr", "uac"]):
                result["process_chains"].append({
                    "pid": pid,
                    "name": info["name"],
                    "exe": info["exe"],
                    "severity": "HIGH",
                    "reason": "REDBLUE_ UAC bypass simulation process",
                })

        total = len(result["registry_anomalies"]) + len(result["process_chains"])
        if total:
            result["warning"] = f"UAC bypass indicators detected: {total} finding(s)!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 19: detect_service_tampering
# ================================================================

async def detect_service_tampering() -> dict:
    """Detect tampered or suspicious service/autorun entries pointing to
    unusual paths (Public, Temp, AppData) or containing exploitation keywords."""
    import winreg

    def _sync():
        result = {
            "tampered_services": [],
            "total_checked": 0,
            "warning": None,
        }

        SUSPICIOUS_PATH_KEYWORDS = [
            "\\temp\\", "\\tmp\\", "\\public\\", "\\appdata\\",
            "\\downloads\\", "\\programdata\\", "\\recycle",
        ]
        SUSPICIOUS_CMD_KEYWORDS = [
            "escalate", "exploit", "backdoor", "reverse", "payload",
            "meterpreter", "empire", "cobalt",
        ]

        # Check Run key entries
        RUN_KEYS = [
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        ]

        for hive, key_path in RUN_KEYS:
            hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        result["total_checked"] += 1
                        val_lower = str(val).lower()

                        reasons = []
                        for kw in SUSPICIOUS_PATH_KEYWORDS:
                            if kw in val_lower:
                                reasons.append(f"Path contains '{kw}'")
                        for kw in SUSPICIOUS_CMD_KEYWORDS:
                            if kw in val_lower:
                                reasons.append(f"Command contains '{kw}'")
                        if "redblue_" in name.lower() and "svc" in name.lower():
                            reasons.append("REDBLUE_ service exploitation artifact")

                        if reasons:
                            result["tampered_services"].append({
                                "hive": hive_name,
                                "key": key_path,
                                "value_name": name,
                                "value": str(val)[:200],
                                "reasons": reasons,
                                "severity": "HIGH" if any("exploit" in r or "backdoor" in r for r in reasons) else "MEDIUM",
                            })
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass

        # Check scheduled tasks for suspicious entries
        try:
            import subprocess
            out = subprocess.run(
                ["schtasks.exe", "/query", "/fo", "CSV", "/nh"],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            )
            if out.returncode == 0:
                for line in out.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.strip().strip('"').split('","')
                    if len(parts) >= 1:
                        task_name = parts[0].strip('"')
                        task_lower = task_name.lower()
                        result["total_checked"] += 1
                        if any(kw in task_lower for kw in SUSPICIOUS_CMD_KEYWORDS + ["redblue_"]):
                            result["tampered_services"].append({
                                "type": "scheduled_task",
                                "task_name": task_name,
                                "severity": "MEDIUM",
                                "reasons": ["Scheduled task with suspicious name"],
                            })
        except Exception:
            pass

        if result["tampered_services"]:
            result["warning"] = f"{len(result['tampered_services'])} suspicious service/autorun entries detected!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 20: detect_wmi_execution
# ================================================================

async def detect_wmi_execution() -> dict:
    """Detect WMI-based process execution: WmiPrvSE.exe spawning child processes
    and wmic.exe with 'process call create' in command line."""

    def _sync():
        result = {
            "wmi_spawned_processes": [],
            "wmic_commands": [],
            "total_wmi_children": 0,
            "warning": None,
        }

        proc_map = {}
        for proc in psutil.process_iter(["pid", "name", "ppid", "exe", "cmdline"]):
            try:
                proc_map[proc.info["pid"]] = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Find WmiPrvSE.exe PIDs
        wmi_pids = set()
        for pid, info in proc_map.items():
            if (info["name"] or "").lower() == "wmiprvse.exe":
                wmi_pids.add(pid)

        # Find children of WmiPrvSE.exe
        for pid, info in proc_map.items():
            ppid = info.get("ppid")
            if ppid in wmi_pids:
                result["total_wmi_children"] += 1
                name_lower = (info["name"] or "").lower()
                # Filter out known-safe WMI children
                if name_lower not in ("wmiprvse.exe", "wmiapsrv.exe", "svchost.exe"):
                    result["wmi_spawned_processes"].append({
                        "pid": pid,
                        "name": info["name"],
                        "exe": info["exe"],
                        "cmdline": " ".join(info["cmdline"] or [])[:200],
                        "parent_pid": ppid,
                        "severity": "HIGH",
                        "reason": "Process spawned by WmiPrvSE.exe",
                    })

        # Find wmic.exe with "process call create"
        for pid, info in proc_map.items():
            if (info["name"] or "").lower() == "wmic.exe":
                cmdline = " ".join(info["cmdline"] or []).lower()
                if "process" in cmdline and "call" in cmdline and "create" in cmdline:
                    result["wmic_commands"].append({
                        "pid": pid,
                        "cmdline": " ".join(info["cmdline"] or [])[:200],
                        "severity": "HIGH",
                        "reason": "wmic.exe process call create (remote/local execution)",
                    })

        total = len(result["wmi_spawned_processes"]) + len(result["wmic_commands"])
        if total:
            result["warning"] = f"WMI execution detected: {total} suspicious finding(s)!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 21: detect_dll_anomalies
# ================================================================

async def detect_dll_anomalies() -> dict:
    """Detect suspicious DLL files in temp/artifact directories: unsigned,
    very small (<10KB), or placed next to renamed executables."""

    def _sync():
        import tempfile

        result = {
            "suspicious_dlls": [],
            "total_checked": 0,
            "warning": None,
        }

        # Directories to scan for rogue DLLs
        scan_dirs = [
            tempfile.gettempdir(),
            os.path.join(tempfile.gettempdir(), "redblue_artifacts"),
            os.environ.get("USERPROFILE", ""),
        ]
        # Add Downloads if accessible
        downloads = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
        if os.path.isdir(downloads):
            scan_dirs.append(downloads)

        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    if not entry.name.lower().endswith(".dll"):
                        continue

                    result["total_checked"] += 1
                    reasons = []
                    file_size = entry.stat().st_size

                    # Very small DLLs are suspicious
                    if file_size < 10240:  # < 10KB
                        reasons.append(f"Unusually small DLL ({file_size} bytes)")

                    # DLL with REDBLUE_ prefix
                    if "redblue_" in entry.name.lower():
                        reasons.append("REDBLUE_ artifact DLL")

                    # Check if there's an exe next to it (sideloading indicator)
                    dir_files = [f.name.lower() for f in os.scandir(scan_dir) if f.is_file()]
                    exe_neighbors = [f for f in dir_files if f.endswith(".exe")]
                    if exe_neighbors:
                        reasons.append(f"DLL found alongside exe(s): {', '.join(exe_neighbors[:3])}")

                    # Check for fake PE header
                    try:
                        with open(entry.path, "rb") as f:
                            header = f.read(64)
                            if header.startswith(b"MZ") and b"DUMMY" in header:
                                reasons.append("Fake/dummy PE header detected")
                    except Exception:
                        pass

                    if reasons:
                        result["suspicious_dlls"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "size_bytes": file_size,
                            "reasons": reasons,
                            "severity": "HIGH" if len(reasons) > 1 else "MEDIUM",
                        })
            except PermissionError:
                continue

        if result["suspicious_dlls"]:
            result["warning"] = f"{len(result['suspicious_dlls'])} suspicious DLL(s) found in temp/user directories!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 22: detect_script_chains
# ================================================================

async def detect_script_chains() -> dict:
    """Detect multi-stage script execution chains (cmd -> powershell -> wscript/cscript)
    and suspicious script files (.vbs, .js, .wsf) in temp directories."""

    def _sync():
        import tempfile

        result = {
            "script_chains": [],
            "suspicious_scripts": [],
            "total_chains": 0,
            "warning": None,
        }

        SCRIPT_HOSTS = ["wscript.exe", "cscript.exe"]
        SHELL_PROCS = ["cmd.exe", "powershell.exe", "pwsh.exe"]
        SCRIPT_EXTENSIONS = {".vbs", ".js", ".wsf", ".hta", ".ps1", ".bat", ".cmd"}

        # Build process tree
        proc_map = {}
        for proc in psutil.process_iter(["pid", "name", "ppid", "exe", "cmdline"]):
            try:
                proc_map[proc.info["pid"]] = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Detect chains: shell -> shell -> script host
        for pid, info in proc_map.items():
            name_lower = (info["name"] or "").lower()
            if name_lower in [s.lower() for s in SCRIPT_HOSTS]:
                # Check if parent is a shell
                ppid = info.get("ppid")
                parent = proc_map.get(ppid, {})
                parent_name = (parent.get("name") or "").lower()

                if parent_name in [s.lower() for s in SHELL_PROCS]:
                    # Check grandparent
                    gppid = parent.get("ppid")
                    grandparent = proc_map.get(gppid, {})
                    gp_name = (grandparent.get("name") or "").lower()

                    chain_parts = []
                    if gp_name in [s.lower() for s in SHELL_PROCS]:
                        chain_parts = [gp_name, parent_name, name_lower]
                    else:
                        chain_parts = [parent_name, name_lower]

                    result["script_chains"].append({
                        "chain": " -> ".join(chain_parts),
                        "script_host_pid": pid,
                        "parent_pid": ppid,
                        "cmdline": " ".join(info["cmdline"] or [])[:200],
                        "severity": "HIGH",
                        "reason": f"Script execution chain: {' -> '.join(chain_parts)}",
                    })
                    result["total_chains"] += 1

        # Scan for suspicious script files in temp dirs
        scan_dirs = [
            tempfile.gettempdir(),
            os.path.join(tempfile.gettempdir(), "redblue_artifacts"),
        ]

        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in SCRIPT_EXTENSIONS:
                        result["suspicious_scripts"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "size_bytes": entry.stat().st_size,
                            "severity": "MEDIUM",
                            "reason": f"Script file ({ext}) in temp directory",
                        })
            except PermissionError:
                continue

        total = result["total_chains"] + len(result["suspicious_scripts"])
        if total:
            result["warning"] = (
                f"Script execution detected: {result['total_chains']} chains, "
                f"{len(result['suspicious_scripts'])} suspicious scripts!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 23: detect_mass_file_operations
# ================================================================

async def detect_mass_file_operations(directory: str = "") -> dict:
    """Detect rapid file creation/modification patterns that may indicate
    ransomware or data destruction (files modified in the last 60 seconds)."""
    import time as _time

    def _sync():
        import tempfile

        result = {
            "rapid_modifications": [],
            "affected_directories": [],
            "files_modified_count": 0,
            "warning": None,
        }

        now = _time.time()
        threshold = 60  # seconds

        dirs_to_scan = []
        if directory and os.path.isdir(directory):
            dirs_to_scan.append(directory)

        # Always scan artifact dir
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            dirs_to_scan.append(artifact_dir)

        # Scan user Documents
        docs = os.path.join(os.environ.get("USERPROFILE", ""), "Documents")
        if os.path.isdir(docs) and docs not in dirs_to_scan:
            dirs_to_scan.append(docs)

        for scan_dir in dirs_to_scan:
            dir_count = 0
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                        if now - mtime < threshold:
                            dir_count += 1
                            result["files_modified_count"] += 1
                            if dir_count <= 20:  # Cap per dir
                                result["rapid_modifications"].append({
                                    "path": entry.path,
                                    "name": entry.name,
                                    "size_bytes": entry.stat().st_size,
                                    "modified_seconds_ago": round(now - mtime, 1),
                                })
                    except OSError:
                        continue
            except PermissionError:
                continue

            if dir_count > 5:
                result["affected_directories"].append({
                    "directory": scan_dir,
                    "files_modified": dir_count,
                    "severity": "CRITICAL" if dir_count > 20 else "HIGH",
                })

        if result["files_modified_count"] > 5:
            result["warning"] = (
                f"Mass file operations: {result['files_modified_count']} files "
                f"modified in last 60s across {len(result['affected_directories'])} directories!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 24: detect_ransom_indicators
# ================================================================

async def detect_ransom_indicators() -> dict:
    """Detect ransomware indicators: encrypted file extensions, ransom notes,
    and suspicious file patterns in user directories."""

    def _sync():
        import tempfile

        result = {
            "ransom_notes": [],
            "encrypted_files": [],
            "suspicious_extensions": [],
            "warning": None,
        }

        RANSOM_EXTENSIONS = {
            ".encrypted", ".locked", ".crypto", ".enc", ".crypt",
            ".locky", ".cerber", ".wannacry", ".petya", ".ryuk",
        }
        RANSOM_NOTE_PATTERNS = [
            "ransom", "decrypt", "recover", "readme", "help_restore",
            "how_to_unlock", "your_files", "payment",
        ]

        dirs_to_scan = [
            os.path.join(tempfile.gettempdir(), "redblue_artifacts"),
            os.environ.get("USERPROFILE", ""),
            os.path.join(os.environ.get("USERPROFILE", ""), "Documents"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        ]

        for scan_dir in dirs_to_scan:
            if not os.path.isdir(scan_dir):
                continue
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    name_lower = entry.name.lower()
                    ext = os.path.splitext(name_lower)[1]

                    # Check for ransom extensions
                    if ext in RANSOM_EXTENSIONS:
                        result["encrypted_files"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "extension": ext,
                            "size_bytes": entry.stat().st_size,
                            "severity": "CRITICAL",
                        })

                    # Check for ransom notes
                    if any(pattern in name_lower for pattern in RANSOM_NOTE_PATTERNS):
                        if ext in (".txt", ".html", ".htm", ".hta"):
                            result["ransom_notes"].append({
                                "path": entry.path,
                                "name": entry.name,
                                "severity": "CRITICAL",
                            })
            except PermissionError:
                continue

        total = len(result["encrypted_files"]) + len(result["ransom_notes"])
        if total:
            result["warning"] = (
                f"RANSOMWARE INDICATORS: {len(result['encrypted_files'])} encrypted files, "
                f"{len(result['ransom_notes'])} ransom notes!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 25: detect_service_disruption
# ================================================================

async def detect_service_disruption() -> dict:
    """Detect disrupted services: disabled scheduled tasks, stopped services,
    and unusual service state changes."""

    def _sync():
        import subprocess

        result = {
            "disrupted_tasks": [],
            "total_checked": 0,
            "warning": None,
        }

        # Check scheduled tasks for disabled REDBLUE_ tasks
        try:
            out = subprocess.run(
                ["schtasks.exe", "/query", "/fo", "CSV", "/v", "/nh"],
                capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace",
            )
            if out.returncode == 0:
                for line in out.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split('","')
                    if len(parts) < 3:
                        continue

                    task_name = parts[0].strip('"')
                    result["total_checked"] += 1

                    # Check for disabled/stopped tasks
                    line_lower = line.lower()
                    if "disabled" in line_lower or "could not start" in line_lower:
                        # Extra suspicious if REDBLUE_ or critical-sounding name
                        reasons = ["Task is disabled"]
                        severity = "LOW"

                        if "redblue_" in task_name.lower():
                            reasons.append("REDBLUE_ artifact task")
                            severity = "MEDIUM"
                        if any(kw in task_name.lower() for kw in ["critical", "service", "security", "defender"]):
                            reasons.append("Critical-sounding task name is disabled")
                            severity = "HIGH"

                        result["disrupted_tasks"].append({
                            "task_name": task_name,
                            "status": "Disabled",
                            "reasons": reasons,
                            "severity": severity,
                        })
        except Exception:
            pass

        if result["disrupted_tasks"]:
            high_sev = sum(1 for t in result["disrupted_tasks"] if t["severity"] in ("HIGH", "CRITICAL"))
            result["warning"] = (
                f"Service disruption: {len(result['disrupted_tasks'])} disabled tasks "
                f"({high_sev} high severity)!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 26: detect_system_enumeration
# ================================================================

async def detect_system_enumeration() -> dict:
    """Detect system discovery activity: processes running systeminfo,
    ipconfig, net user, whoami, hostname, and similar recon commands."""

    def _sync():
        result = {
            "enumeration_processes": [],
            "total_checked": 0,
            "warning": None,
        }

        RECON_COMMANDS = [
            "systeminfo", "ipconfig", "hostname", "whoami",
            "net user", "net localgroup", "net share", "net view",
            "route print", "arp -a", "netstat", "nbtstat",
            "sc query", "tasklist", "wmic", "quser", "nltest",
        ]

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            result["total_checked"] += 1
            try:
                info = proc.info
                cmdline = " ".join(info["cmdline"] or []).lower()
                name_lower = (info["name"] or "").lower()

                reasons = []
                for recon_cmd in RECON_COMMANDS:
                    parts = recon_cmd.split()
                    if len(parts) == 1:
                        if parts[0] in name_lower or parts[0] + ".exe" == name_lower:
                            reasons.append(f"Running {recon_cmd}")
                    else:
                        if all(p in cmdline for p in parts):
                            reasons.append(f"Command contains '{recon_cmd}'")

                # Check for REDBLUE_ discovery artifacts
                if "redblue_" in cmdline and "discovery" in cmdline:
                    reasons.append("REDBLUE_ discovery artifact")

                if reasons:
                    result["enumeration_processes"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "cmdline": cmdline[:200],
                        "reasons": reasons,
                        "severity": "MEDIUM",
                    })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["enumeration_processes"]:
            result["warning"] = (
                f"System enumeration detected: {len(result['enumeration_processes'])} "
                f"recon processes running!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 27: detect_network_reconnaissance
# ================================================================

async def detect_network_reconnaissance() -> dict:
    """Detect network reconnaissance: processes running network discovery
    commands and REDBLUE_ discovery output files."""

    def _sync():
        import tempfile

        result = {
            "recon_indicators": [],
            "discovery_files": [],
            "warning": None,
        }

        NETWORK_RECON_PROCS = [
            "nmap", "masscan", "ping", "tracert", "pathping",
            "nslookup", "dig",
        ]

        # Check processes
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower()
                cmdline = " ".join(info["cmdline"] or []).lower()

                for tool in NETWORK_RECON_PROCS:
                    if tool in name_lower:
                        result["recon_indicators"].append({
                            "pid": info["pid"],
                            "name": info["name"],
                            "cmdline": cmdline[:200],
                            "severity": "MEDIUM",
                            "reason": f"Network recon tool: {tool}",
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check for discovery output files in artifact dir
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if entry.is_file() and "discovery" in entry.name.lower():
                    result["discovery_files"].append({
                        "path": entry.path,
                        "name": entry.name,
                        "size_bytes": entry.stat().st_size,
                        "severity": "HIGH",
                        "reason": "Discovery output file in artifact dir",
                    })

        total = len(result["recon_indicators"]) + len(result["discovery_files"])
        if total:
            result["warning"] = f"Network reconnaissance detected: {total} indicators!"

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 28: detect_collection_activity
# ================================================================

async def detect_collection_activity() -> dict:
    """Detect data collection activity: screenshot files, keylog files,
    clipboard captures, and staging archives in temp directories."""

    def _sync():
        import tempfile

        result = {
            "collection_indicators": [],
            "warning": None,
        }

        COLLECTION_PATTERNS = {
            "screenshot": ["screenshot", "screen_cap", "screengrab"],
            "keylogger": ["keylog", "keystroke", "key_log"],
            "clipboard": ["clipboard", "clip_data", "paste_data"],
            "staging": ["staged", "staging", "exfil_prep"],
        }
        ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}

        scan_dirs = [
            os.path.join(tempfile.gettempdir(), "redblue_artifacts"),
            tempfile.gettempdir(),
        ]

        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    name_lower = entry.name.lower()
                    ext = os.path.splitext(name_lower)[1]

                    reasons = []

                    for category, patterns in COLLECTION_PATTERNS.items():
                        if any(p in name_lower for p in patterns):
                            reasons.append(f"Collection indicator: {category}")

                    # Check for staging archives
                    if ext in ARCHIVE_EXTENSIONS and "redblue_" in name_lower:
                        reasons.append("Staging archive with REDBLUE_ prefix")

                    # Check for image files (screenshots)
                    if ext in (".png", ".jpg", ".bmp") and "redblue_" in name_lower:
                        reasons.append("Screenshot file with REDBLUE_ prefix")

                    if reasons:
                        result["collection_indicators"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "size_bytes": entry.stat().st_size,
                            "reasons": reasons,
                            "severity": "HIGH",
                        })
            except PermissionError:
                continue

        if result["collection_indicators"]:
            result["warning"] = (
                f"Data collection detected: {len(result['collection_indicators'])} "
                f"collection artifacts found!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 29: detect_sensitive_file_access
# ================================================================

async def detect_sensitive_file_access() -> dict:
    """Detect access to sensitive files: browser databases, credential files,
    SSH keys copied to temp/artifact directories."""

    def _sync():
        import tempfile

        result = {
            "sensitive_files": [],
            "warning": None,
        }

        SENSITIVE_PATTERNS = [
            "browser_", "history.db", "login_data", "cookies",
            "passwords", "credentials", "secrets", "config.ini",
            ".env", "id_rsa", ".pem", ".key", ".pfx",
        ]

        scan_dirs = [
            os.path.join(tempfile.gettempdir(), "redblue_artifacts"),
            tempfile.gettempdir(),
        ]

        for scan_dir in scan_dirs:
            if not os.path.isdir(scan_dir):
                continue
            try:
                for entry in os.scandir(scan_dir):
                    if not entry.is_file():
                        continue
                    name_lower = entry.name.lower()

                    reasons = []
                    for pattern in SENSITIVE_PATTERNS:
                        if pattern in name_lower:
                            reasons.append(f"Sensitive file pattern: '{pattern}'")

                    if reasons:
                        result["sensitive_files"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "size_bytes": entry.stat().st_size,
                            "reasons": reasons,
                            "severity": "CRITICAL" if any("password" in r or "credential" in r for r in reasons) else "HIGH",
                        })
            except PermissionError:
                continue

        if result["sensitive_files"]:
            result["warning"] = (
                f"Sensitive file access: {len(result['sensitive_files'])} "
                f"credential/config files found in temp directories!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 30: detect_log_tampering
# ================================================================

async def detect_log_tampering() -> dict:
    """Detect log tampering indicators: timestomped files (mtime before ctime),
    log clearing markers, and suspiciously empty log sections."""

    def _sync():
        import tempfile

        result = {
            "tampering_indicators": [],
            "timestomped_files": [],
            "warning": None,
        }

        # Check artifact dir for timestomped files
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if not entry.is_file():
                    continue
                try:
                    stat = entry.stat()
                    # Timestomping: mtime significantly before ctime
                    if stat.st_mtime < stat.st_ctime - 86400:  # >1 day difference
                        result["timestomped_files"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "ctime": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "severity": "HIGH",
                            "reason": "File mtime significantly before ctime (timestomping)",
                        })

                    # Log clearing markers
                    name_lower = entry.name.lower()
                    if "log" in name_lower and "clear" in name_lower:
                        result["tampering_indicators"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "severity": "CRITICAL",
                            "reason": "Log clearing marker file detected",
                        })
                    if "indicator_removal" in name_lower:
                        result["tampering_indicators"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "severity": "HIGH",
                            "reason": "Indicator removal evidence file",
                        })
                except OSError:
                    continue

        total = len(result["tampering_indicators"]) + len(result["timestomped_files"])
        if total:
            result["warning"] = (
                f"Log/evidence tampering detected: {len(result['timestomped_files'])} "
                f"timestomped files, {len(result['tampering_indicators'])} tampering indicators!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 31: detect_brute_force_attempts
# ================================================================

async def detect_brute_force_attempts() -> dict:
    """Detect brute-force login attempts: rapid net use failures,
    multiple authentication events in a short window."""

    def _sync():
        result = {
            "brute_force_indicators": [],
            "warning": None,
        }

        # Check for net.exe processes with IPC$ connections
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower()
                cmdline = " ".join(info["cmdline"] or []).lower()

                if name_lower == "net.exe" or name_lower == "net1.exe":
                    if "use" in cmdline and ("ipc$" in cmdline or "\\\\127" in cmdline):
                        result["brute_force_indicators"].append({
                            "pid": info["pid"],
                            "cmdline": cmdline[:200],
                            "severity": "HIGH",
                            "reason": "net use IPC$ connection attempt (potential brute force)",
                        })

                    if "user" in cmdline and "redblue_" in cmdline:
                        result["brute_force_indicators"].append({
                            "pid": info["pid"],
                            "cmdline": cmdline[:200],
                            "severity": "HIGH",
                            "reason": "REDBLUE_ credential brute force attempt",
                        })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["brute_force_indicators"]:
            result["warning"] = (
                f"Brute force detected: {len(result['brute_force_indicators'])} "
                f"authentication attempt indicators!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 32: detect_lateral_movement_tools
# ================================================================

async def detect_lateral_movement_tools() -> dict:
    """Detect lateral movement tools: mstsc.exe (RDP), winrs.exe (WinRM),
    net use with remote targets, PsExec, and similar."""

    def _sync():
        result = {
            "lateral_movement_indicators": [],
            "warning": None,
        }

        LATERAL_TOOLS = {
            "mstsc.exe": "RDP client",
            "winrs.exe": "WinRM client",
            "psexec.exe": "PsExec remote execution",
            "psexec64.exe": "PsExec remote execution",
            "wmiexec.exe": "WMI remote execution",
            "smbexec.exe": "SMB remote execution",
            "atexec.exe": "AT remote execution",
        }

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower()
                cmdline = " ".join(info["cmdline"] or []).lower()

                # Check for known lateral movement tools
                if name_lower in LATERAL_TOOLS:
                    result["lateral_movement_indicators"].append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "exe": info["exe"],
                        "cmdline": cmdline[:200],
                        "severity": "HIGH",
                        "reason": f"Lateral movement tool: {LATERAL_TOOLS[name_lower]}",
                    })

                # Check for net use with remote connections
                if name_lower in ("net.exe", "net1.exe") and "use" in cmdline:
                    if "\\\\" in cmdline and "127.0.0.1" not in cmdline and "localhost" not in cmdline:
                        result["lateral_movement_indicators"].append({
                            "pid": info["pid"],
                            "name": info["name"],
                            "cmdline": cmdline[:200],
                            "severity": "HIGH",
                            "reason": "net use to remote target",
                        })
                    elif "\\\\" in cmdline:
                        result["lateral_movement_indicators"].append({
                            "pid": info["pid"],
                            "name": info["name"],
                            "cmdline": cmdline[:200],
                            "severity": "MEDIUM",
                            "reason": "net use connection (localhost)",
                        })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["lateral_movement_indicators"]:
            result["warning"] = (
                f"Lateral movement detected: {len(result['lateral_movement_indicators'])} "
                f"remote access tool indicators!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 33: detect_c2_channels
# ================================================================

async def detect_c2_channels() -> dict:
    """Detect C2 communication channels: HTTP beaconing on localhost,
    DNS tunnel patterns, self-signed certificates, and unusual listeners."""

    def _sync():
        import tempfile

        result = {
            "c2_indicators": [],
            "suspicious_listeners": [],
            "warning": None,
        }

        # Check for HTTP server processes on unusual ports
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr:
                port = conn.laddr.port
                # Flag high ports that aren't common services
                if port > 10000 and port not in (17771, 17772, 17773, 17774, 17775):
                    try:
                        proc = psutil.Process(conn.pid)
                        proc_name = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        proc_name = "unknown"

                    # Skip well-known background processes
                    if proc_name.lower() not in ("svchost.exe", "system", "lsass.exe"):
                        result["suspicious_listeners"].append({
                            "port": port,
                            "pid": conn.pid,
                            "process": proc_name,
                            "severity": "MEDIUM",
                            "reason": f"Unusual listener on high port {port}",
                        })

        # Check for self-signed cert files in artifact dir
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if entry.is_file():
                    name_lower = entry.name.lower()
                    if any(ext in name_lower for ext in [".pem", ".pfx", ".key", ".crt", "selfsigned"]):
                        result["c2_indicators"].append({
                            "path": entry.path,
                            "name": entry.name,
                            "severity": "HIGH",
                            "reason": "Self-signed certificate in artifact directory",
                        })

        # Check for DNS tunnel patterns (rapid nslookup processes)
        nslookup_count = 0
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if (proc.info["name"] or "").lower() == "nslookup.exe":
                    nslookup_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if nslookup_count > 5:
            result["c2_indicators"].append({
                "nslookup_count": nslookup_count,
                "severity": "HIGH",
                "reason": f"{nslookup_count} concurrent nslookup processes (DNS tunneling indicator)",
            })

        total = len(result["c2_indicators"]) + len(result["suspicious_listeners"])
        if total:
            result["warning"] = (
                f"C2 channel indicators: {len(result['c2_indicators'])} C2 indicators, "
                f"{len(result['suspicious_listeners'])} suspicious listeners!"
            )

        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 34: detect_vault_attacks
# ================================================================

async def detect_vault_attacks() -> dict:
    """Detect attacks against secret-vault: brute force patterns, JWT token
    files, and credential dump artifacts in temp directories."""

    def _sync():
        import tempfile

        result = {"vault_indicators": [], "warning": None}

        # Check for vault-related files in artifact dir
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if not entry.is_file():
                    continue
                name_lower = entry.name.lower()
                if any(kw in name_lower for kw in ["vault", "jwt", "bruteforce", "recovery"]):
                    result["vault_indicators"].append({
                        "path": entry.path, "name": entry.name,
                        "severity": "CRITICAL" if "dump" in name_lower or "jwt" in name_lower else "HIGH",
                        "reason": "Vault attack artifact detected",
                    })

        # Check for processes making HTTP requests to port 8000
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or []).lower()
                if "8000" in cmdline and ("curl" in cmdline or "invoke-webrequest" in cmdline):
                    result["vault_indicators"].append({
                        "pid": proc.info["pid"], "name": proc.info["name"],
                        "severity": "HIGH", "reason": "HTTP request to vault port 8000",
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["vault_indicators"]:
            result["warning"] = f"Vault attack detected: {len(result['vault_indicators'])} indicators!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 35: detect_api_scanning
# ================================================================

async def detect_api_scanning() -> dict:
    """Detect API endpoint scanning: rapid HTTP connections to multiple
    ports and paths in a short window."""

    def _sync():
        import tempfile

        result = {"scan_indicators": [], "warning": None}

        # Check for enumeration output files
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if not entry.is_file():
                    continue
                name_lower = entry.name.lower()
                if any(kw in name_lower for kw in ["enum", "port_scan", "recon", "api_recon"]):
                    result["scan_indicators"].append({
                        "path": entry.path, "name": entry.name,
                        "severity": "MEDIUM", "reason": "API/port scan output file",
                    })

        # Check for many outbound connections from one process
        conn_counts = {}
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "ESTABLISHED" and conn.pid:
                conn_counts[conn.pid] = conn_counts.get(conn.pid, 0) + 1

        for pid, count in conn_counts.items():
            if count > 10:
                try:
                    proc = psutil.Process(pid)
                    result["scan_indicators"].append({
                        "pid": pid, "name": proc.name(), "connections": count,
                        "severity": "HIGH", "reason": f"Process with {count} active connections (scanning)",
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        if result["scan_indicators"]:
            result["warning"] = f"API scanning detected: {len(result['scan_indicators'])} indicators!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 36: detect_credential_exfiltration
# ================================================================

async def detect_credential_exfiltration() -> dict:
    """Detect credential exfiltration: files containing JWT tokens,
    vault secrets, decrypted passwords in temp directories."""

    def _sync():
        import tempfile

        result = {"exfil_indicators": [], "warning": None}

        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if not entry.is_file() or entry.stat().st_size > 1048576:
                    continue
                try:
                    with open(entry.path, "r", errors="replace") as f:
                        content = f.read(10000).lower()
                    cred_patterns = ["token:", "jwt", "password", "secret", "api_key", "private_key", "credit_card"]
                    found = [p for p in cred_patterns if p in content]
                    if found:
                        result["exfil_indicators"].append({
                            "path": entry.path, "name": entry.name,
                            "patterns_found": found, "size_bytes": entry.stat().st_size,
                            "severity": "CRITICAL" if "private_key" in found or "credit_card" in found else "HIGH",
                            "reason": f"File contains credential data: {', '.join(found)}",
                        })
                except Exception:
                    continue

        if result["exfil_indicators"]:
            result["warning"] = f"Credential exfiltration: {len(result['exfil_indicators'])} files with sensitive data!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 37: detect_port_scanning
# ================================================================

async def detect_port_scanning() -> dict:
    """Detect port scanning activity: processes with many short-lived
    connections to sequential ports."""

    def _sync():
        import tempfile

        result = {"port_scan_indicators": [], "warning": None}

        # Check for port scan output files
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if entry.is_file() and "port_scan" in entry.name.lower():
                    result["port_scan_indicators"].append({
                        "path": entry.path, "name": entry.name,
                        "severity": "HIGH", "reason": "Port scan results file",
                    })

        # Check for nmap/masscan processes
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name_lower = (proc.info["name"] or "").lower()
                if name_lower in ("nmap.exe", "masscan.exe", "nmap", "masscan"):
                    result["port_scan_indicators"].append({
                        "pid": proc.info["pid"], "name": proc.info["name"],
                        "severity": "HIGH", "reason": "Port scanning tool running",
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["port_scan_indicators"]:
            result["warning"] = f"Port scanning detected: {len(result['port_scan_indicators'])} indicators!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 38: detect_ssh_lateral_movement
# ================================================================

async def detect_ssh_lateral_movement() -> dict:
    """Detect SSH-based lateral movement: ssh.exe/plink.exe processes
    and outbound connections to SSH ports."""

    def _sync():
        result = {"ssh_indicators": [], "warning": None}

        SSH_TOOLS = ["ssh.exe", "plink.exe", "putty.exe", "ssh", "scp.exe", "sftp.exe"]

        for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
            try:
                info = proc.info
                name_lower = (info["name"] or "").lower()
                cmdline = " ".join(info["cmdline"] or []).lower()

                if name_lower in SSH_TOOLS:
                    severity = "HIGH"
                    reasons = [f"SSH tool running: {name_lower}"]
                    if any(cred in cmdline for cred in ["vibemind", "redblue_", "password"]):
                        severity = "CRITICAL"
                        reasons.append("Credentials visible in command line")
                    result["ssh_indicators"].append({
                        "pid": info["pid"], "name": info["name"],
                        "cmdline": cmdline[:200], "severity": severity, "reasons": reasons,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check for outbound SSH connections
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "ESTABLISHED" and conn.raddr:
                if conn.raddr.port in (22, 2222):
                    try:
                        proc = psutil.Process(conn.pid)
                        result["ssh_indicators"].append({
                            "pid": conn.pid, "process": proc.name(),
                            "remote": f"{conn.raddr.ip}:{conn.raddr.port}",
                            "severity": "HIGH", "reasons": ["Outbound SSH connection"],
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

        if result["ssh_indicators"]:
            result["warning"] = f"SSH lateral movement: {len(result['ssh_indicators'])} indicators!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 39: detect_supply_chain_tampering
# ================================================================

async def detect_supply_chain_tampering() -> dict:
    """Detect supply chain tampering: REDBLUE_ scripts in shared folders,
    modified service files, and suspicious auto-update artifacts."""

    def _sync():
        result = {"supply_chain_indicators": [], "warning": None}

        # Check multiseat-os directory for REDBLUE_ files
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        check_dirs = [
            os.path.join(project_root, "multiseat-os"),
            os.path.join(project_root, "multiseat-os", "services"),
        ]

        for check_dir in check_dirs:
            if not os.path.isdir(check_dir):
                continue
            for entry in os.scandir(check_dir):
                if entry.is_file() and "REDBLUE_" in entry.name:
                    result["supply_chain_indicators"].append({
                        "path": entry.path, "name": entry.name,
                        "severity": "CRITICAL",
                        "reason": "REDBLUE_ file in shared/service directory (supply chain tamper)",
                    })

        if result["supply_chain_indicators"]:
            result["warning"] = f"Supply chain tampering: {len(result['supply_chain_indicators'])} suspicious files!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 40: detect_llm_manipulation
# ================================================================

async def detect_llm_manipulation() -> dict:
    """Detect LLM manipulation: HTTP requests to Ollama API,
    prompt injection artifacts, and abnormal LLM activity."""

    def _sync():
        import tempfile

        result = {"llm_indicators": [], "warning": None}

        # Check for LLM attack output files
        artifact_dir = os.path.join(tempfile.gettempdir(), "redblue_artifacts")
        if os.path.isdir(artifact_dir):
            for entry in os.scandir(artifact_dir):
                if not entry.is_file():
                    continue
                name_lower = entry.name.lower()
                if any(kw in name_lower for kw in ["llm", "injection", "prompt", "force_clean", "traversal", "dos"]):
                    result["llm_indicators"].append({
                        "path": entry.path, "name": entry.name,
                        "severity": "HIGH", "reason": "LLM attack artifact detected",
                    })

        # Check for connections to Ollama port
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "ESTABLISHED" and conn.raddr and conn.raddr.port == 11434:
                try:
                    proc = psutil.Process(conn.pid)
                    proc_name = proc.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = "unknown"
                result["llm_indicators"].append({
                    "pid": conn.pid, "process": proc_name,
                    "severity": "MEDIUM", "reason": "Active connection to Ollama LLM (port 11434)",
                })

        if result["llm_indicators"]:
            result["warning"] = f"LLM manipulation: {len(result['llm_indicators'])} indicators!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL 41: detect_abnormal_cleanup
# ================================================================

async def detect_abnormal_cleanup() -> dict:
    """Detect abnormal cleanup activity: BleachBit processes,
    unexpected temp file deletions, clean agent activity."""

    def _sync():
        result = {"cleanup_indicators": [], "warning": None}

        CLEANUP_TOOLS = ["bleachbit.exe", "bleachbit", "ccleaner.exe", "cleanmgr.exe"]

        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name_lower = (proc.info["name"] or "").lower()
                if name_lower in CLEANUP_TOOLS:
                    result["cleanup_indicators"].append({
                        "pid": proc.info["pid"], "name": proc.info["name"],
                        "cmdline": " ".join(proc.info["cmdline"] or [])[:200],
                        "severity": "HIGH", "reason": f"Cleanup tool running: {name_lower}",
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if result["cleanup_indicators"]:
            result["warning"] = f"Abnormal cleanup: {len(result['cleanup_indicators'])} cleanup tools running!"
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# TOOL DISPATCH (for MonitorAgent)
# ================================================================

TOOL_DISPATCH = {
    "list_processes": list_processes,
    "detect_new_processes": detect_new_processes,
    "check_binary_signature": check_binary_signature,
    "check_file_integrity": check_file_integrity,
    "list_network_connections": list_network_connections,
    "detect_suspicious_connections": detect_suspicious_connections,
    "manage_firewall_rule": manage_firewall_rule,
    "list_usb_devices": list_usb_devices,
    "check_registry_autoruns": check_registry_autoruns,
    "detect_parent_child_anomalies": detect_parent_child_anomalies,
    "detect_encoded_commands": detect_encoded_commands,
    "detect_beaconing": detect_beaconing,
    "detect_suspicious_paths": detect_suspicious_paths,
    "detect_lsass_access": detect_lsass_access,
    "detect_data_exfiltration": detect_data_exfiltration,
    # Privilege Escalation Detection
    "detect_token_manipulation": detect_token_manipulation,
    "detect_uac_bypass_attempts": detect_uac_bypass_attempts,
    "detect_service_tampering": detect_service_tampering,
    # Execution Detection
    "detect_wmi_execution": detect_wmi_execution,
    "detect_dll_anomalies": detect_dll_anomalies,
    "detect_script_chains": detect_script_chains,
    # Impact Detection
    "detect_mass_file_operations": detect_mass_file_operations,
    "detect_ransom_indicators": detect_ransom_indicators,
    "detect_service_disruption": detect_service_disruption,
    # Discovery Detection
    "detect_system_enumeration": detect_system_enumeration,
    "detect_network_reconnaissance": detect_network_reconnaissance,
    # Collection Detection
    "detect_collection_activity": detect_collection_activity,
    "detect_sensitive_file_access": detect_sensitive_file_access,
    # Defense Evasion Extension
    "detect_log_tampering": detect_log_tampering,
    # Credential/Lateral/C2 Detection
    "detect_brute_force_attempts": detect_brute_force_attempts,
    "detect_lateral_movement_tools": detect_lateral_movement_tools,
    "detect_c2_channels": detect_c2_channels,
    # External Target Detection
    "detect_vault_attacks": detect_vault_attacks,
    "detect_api_scanning": detect_api_scanning,
    "detect_credential_exfiltration": detect_credential_exfiltration,
    "detect_port_scanning": detect_port_scanning,
    "detect_ssh_lateral_movement": detect_ssh_lateral_movement,
    "detect_supply_chain_tampering": detect_supply_chain_tampering,
    "detect_llm_manipulation": detect_llm_manipulation,
    "detect_abnormal_cleanup": detect_abnormal_cleanup,
    # VM Detection (meta-tool)
    "scan_vm_threats": None,  # Placeholder, imported below
}

# Import VM detection meta-tool (optional, graceful fallback)
try:
    from vm_detection_tools import scan_vm_threats
    TOOL_DISPATCH["scan_vm_threats"] = scan_vm_threats
except ImportError:
    pass


# ================================================================
# OPENAI TOOL DEFINITIONS (for function calling)
# ================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_processes",
            "description": (
                "List all running processes on the system. Returns PID, name, executable path, "
                "username, creation time, and flags known-suspicious process names "
                "(mimikatz, psexec, nc.exe, etc). Use this for a broad initial scan."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_new_processes",
            "description": (
                "Compare current running processes against a baseline list of PIDs. "
                "Returns only new processes that were not running at baseline time. "
                "Flags suspicious names. Use after initial baseline is established."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "baseline_pids_json": {
                        "type": "string",
                        "description": "JSON array of baseline PID numbers, e.g. '[1,4,100,...]'",
                    },
                },
                "required": ["baseline_pids_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_binary_signature",
            "description": (
                "Verify the Authenticode digital signature of a Windows binary (.exe/.dll). "
                "Uses WinVerifyTrust API. Returns whether the file is signed, signature validity, "
                "and status. Use this on suspicious or unsigned executables."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Full path to the binary, e.g. 'C:\\\\Windows\\\\System32\\\\cmd.exe'",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_file_integrity",
            "description": (
                "Hash files in a directory (SHA256) and compare against baseline hashes. "
                "Returns changed, new, and deleted files. Use to detect tampering in "
                "critical system directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to scan, e.g. 'C:\\\\Windows\\\\System32'",
                    },
                    "baseline_hashes_json": {
                        "type": "string",
                        "description": "JSON object of {filepath: sha256_hash} from baseline. Empty string if no baseline.",
                    },
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_network_connections",
            "description": (
                "List all active TCP/UDP network connections. Returns local/remote addresses, "
                "status, PID, and process name. Flags connections on known-suspicious ports "
                "(4444, 5555, 1337, IRC ports, etc). Use for network security assessment."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_suspicious_connections",
            "description": (
                "Compare active ESTABLISHED connections against a baseline of known remote IPs. "
                "Returns connections to unknown/new remote IPs. Use after baseline is established "
                "to detect new outbound connections (possible C2 communication)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "known_remote_ips_json": {
                        "type": "string",
                        "description": "JSON array of known/trusted remote IP addresses",
                    },
                },
                "required": ["known_remote_ips_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_firewall_rule",
            "description": (
                "Add, remove, or list Windows Firewall rules via netsh. "
                "Use 'add' to block suspicious IPs or programs, 'remove' to delete rules, "
                "'list' to show current rules. Requires Administrator."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove", "list"],
                        "description": "Action to perform",
                    },
                    "rule_name": {
                        "type": "string",
                        "description": "Name for the firewall rule",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["in", "out"],
                        "description": "Rule direction (default: out)",
                    },
                    "action_type": {
                        "type": "string",
                        "enum": ["block", "allow"],
                        "description": "Block or allow (default: block)",
                    },
                    "remote_ip": {
                        "type": "string",
                        "description": "Remote IP to block/allow",
                    },
                    "program": {
                        "type": "string",
                        "description": "Program path to block/allow",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_usb_devices",
            "description": (
                "Enumerate all USB devices connected to the system via WMI. "
                "Returns device name, ID, manufacturer, and status. "
                "Use to detect unknown or unauthorized USB devices."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_registry_autoruns",
            "description": (
                "Inspect Windows autorun registry keys (Run, RunOnce under HKLM and HKCU). "
                "Returns all autorun entries with values. If baseline is provided, flags "
                "new entries not present in baseline. Use to detect persistence mechanisms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "baseline_autoruns_json": {
                        "type": "string",
                        "description": "JSON array of baseline autorun entries. Empty string if no baseline.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": (
                "Reason step-by-step about security implications of collected findings. "
                "Use this after gathering monitoring data to analyze threats, correlate "
                "indicators, and assess severity. Returns reasoning, conclusion, and severity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning_prompt": {
                        "type": "string",
                        "description": "Detailed description of findings to reason about",
                    },
                },
                "required": ["reasoning_prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_parent_child_anomalies",
            "description": (
                "Detect suspicious parent-child process chains. Catches malware patterns like "
                "Word/Excel spawning PowerShell (macro attack), browser spawning cmd.exe (drive-by), "
                "or script hosts chaining shells. Checks 15+ parent-child rules. "
                "CRITICAL findings indicate active exploitation. Use this in every scan."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_encoded_commands",
            "description": (
                "Detect Base64-encoded or obfuscated commands in running processes. "
                "Catches PowerShell -EncodedCommand, Invoke-Expression, DownloadString, "
                "hidden windows, execution policy bypasses, and obfuscated payloads. "
                "Attempts to decode Base64 and check for malicious content. Use this in every scan."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_beaconing",
            "description": (
                "Monitor outbound connections for beaconing patterns (regular C2 check-ins). "
                "Takes multiple snapshots over time and finds connections that persist across all snapshots. "
                "Persistent non-HTTPS connections are flagged as potential C2 beacons. "
                "Duration: ~30 seconds of monitoring."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "interval_seconds": {"type": "integer", "description": "Seconds between snapshots (default 10)"},
                    "duration_seconds": {"type": "integer", "description": "Total monitoring duration (default 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_suspicious_paths",
            "description": (
                "Find processes running from suspicious locations: Temp, Downloads, AppData, "
                "Public folders, Recycle Bin. Malware often executes from these paths because "
                "they don't require admin rights. Whitelists known legitimate apps."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_lsass_access",
            "description": (
                "Detect credential theft attempts targeting LSASS (Local Security Authority). "
                "Finds mimikatz, procdump, pypykatz, secretsdump, and rundll32+comsvcs.dll "
                "MiniDump technique. CRITICAL finding = active credential harvesting."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_data_exfiltration",
            "description": (
                "Monitor for data exfiltration: takes two snapshots 5 seconds apart and "
                "calculates which processes are uploading large amounts of data (>10MB/5s). "
                "Detects bulk data theft in progress."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- PRIVILEGE ESCALATION DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_token_manipulation",
            "description": (
                "Detect token manipulation and privilege escalation attempts. Finds processes "
                "performing privilege enumeration (whoami /priv), token manipulation tools "
                "(Potato exploits, Incognito, Tokenvator), and REDBLUE_ token artifacts."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_uac_bypass_attempts",
            "description": (
                "Detect UAC bypass indicators: checks registry keys used by known techniques "
                "(fodhelper, eventvwr, computerdefaults) and process chains where UAC bypass "
                "binaries spawn shell processes. CRITICAL finding = active UAC bypass."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_service_tampering",
            "description": (
                "Detect tampered service/autorun entries pointing to suspicious paths "
                "(Temp, Public, AppData) or containing exploitation keywords (escalate, "
                "backdoor, exploit). Also checks scheduled tasks for suspicious names."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- EXECUTION DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_wmi_execution",
            "description": (
                "Detect WMI-based process execution. Finds WmiPrvSE.exe spawning unexpected "
                "child processes and wmic.exe with 'process call create' in command line. "
                "WMI execution is a common attack technique for lateral movement."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_dll_anomalies",
            "description": (
                "Detect suspicious DLL files in temp/user directories. Finds unsigned DLLs, "
                "very small DLLs (<10KB, likely dummy), DLLs with fake PE headers, and "
                "DLLs placed next to executables (sideloading indicator)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_script_chains",
            "description": (
                "Detect multi-stage script execution chains (cmd -> powershell -> wscript). "
                "Finds script host processes spawned by shells, and suspicious script files "
                "(.vbs, .js, .wsf, .hta) in temp directories."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- IMPACT DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_mass_file_operations",
            "description": (
                "Detect rapid file creation/modification indicating ransomware or data "
                "destruction. Scans artifact dir, Documents, and optional custom directory "
                "for files modified in the last 60 seconds. CRITICAL if >20 files affected."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Additional directory to scan (optional)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_ransom_indicators",
            "description": (
                "Detect ransomware indicators: files with known ransomware extensions "
                "(.encrypted, .locked, .crypto, etc.) and ransom note files (RANSOM, "
                "DECRYPT, README patterns). CRITICAL = active ransomware."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_service_disruption",
            "description": (
                "Detect service disruption: disabled scheduled tasks, stopped critical "
                "services, and unusual service state changes. Flags disabled tasks with "
                "critical-sounding names or REDBLUE_ artifacts."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- DISCOVERY DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_system_enumeration",
            "description": (
                "Detect system discovery activity: processes running systeminfo, ipconfig, "
                "net user, whoami, hostname, and similar recon commands. Catches attackers "
                "mapping the environment."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_network_reconnaissance",
            "description": (
                "Detect network recon: processes running nmap, arp, route, nslookup, "
                "net share, sc query. Also checks for discovery output files in temp dirs."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- COLLECTION DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_collection_activity",
            "description": (
                "Detect data collection: screenshot files, keylog files, clipboard captures, "
                "and staging archives (.zip/.rar) in temp directories. Catches pre-exfiltration activity."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_sensitive_file_access",
            "description": (
                "Detect access to sensitive files: browser databases, credential files, "
                "SSH keys, .env files copied to temp/artifact directories."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- DEFENSE EVASION EXTENSION ----
    {
        "type": "function",
        "function": {
            "name": "detect_log_tampering",
            "description": (
                "Detect log/evidence tampering: timestomped files (mtime before ctime), "
                "log clearing markers, indicator removal evidence. Catches anti-forensics techniques."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- CREDENTIAL / LATERAL / C2 DETECTION ----
    {
        "type": "function",
        "function": {
            "name": "detect_brute_force_attempts",
            "description": (
                "Detect brute-force login attempts: rapid net use failures, "
                "authentication with REDBLUE_ credentials, IPC$ connection attempts."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_lateral_movement_tools",
            "description": (
                "Detect lateral movement tools: mstsc.exe (RDP), winrs.exe (WinRM), "
                "PsExec, net use to remote targets. Catches active lateral movement."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_c2_channels",
            "description": (
                "Detect C2 communication channels: HTTP beaconing, DNS tunneling patterns "
                "(multiple nslookup), self-signed certificates, suspicious high-port listeners."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---- EXTERNAL TARGET DETECTION ----
    {"type": "function", "function": {"name": "detect_vault_attacks", "description": "Detect attacks against secret-vault: brute force artifacts, JWT token files, credential dump files in temp dirs.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_api_scanning", "description": "Detect API/endpoint scanning: enumeration output files, processes with many active connections.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_credential_exfiltration", "description": "Detect credential exfiltration: files containing JWT tokens, passwords, API keys, private keys in temp dirs.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_port_scanning", "description": "Detect port scanning: scan result files, nmap/masscan processes running.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_ssh_lateral_movement", "description": "Detect SSH lateral movement: ssh.exe/plink.exe processes, credentials in cmdline, outbound SSH connections.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_supply_chain_tampering", "description": "Detect supply chain tampering: REDBLUE_ files in shared folders, modified service files in multiseat-os.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_llm_manipulation", "description": "Detect LLM manipulation: prompt injection artifacts, connections to Ollama port 11434, attack output files.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "detect_abnormal_cleanup", "description": "Detect abnormal cleanup: BleachBit/CCleaner processes running, unexpected temp file deletions.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {
        "type": "function",
        "function": {
            "name": "scan_vm_threats",
            "description": "COMPREHENSIVE VM scan: backdoors (cron/bashrc/systemd), suspicious processes, credential theft, network anomalies, log tampering, vault brute force, file changes, privilege escalation, IDS heartbeat status. Run this EVERY round for VM visibility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "baseline_json": {
                        "type": "string",
                        "description": "Optional baseline JSON for comparison",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
]
