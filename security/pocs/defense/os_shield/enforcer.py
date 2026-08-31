"""
EnforcerAgent - Executes Security Countermeasures
===================================================
Receives EnforceRequest messages, executes countermeasures
(kill process, firewall rule, quarantine, disable autorun).

Safety: CRITICAL actions always require confirmation, even in auto-mode.
"""

import asyncio
import json
import os
import shutil
import winreg

import psutil

from autogen_core import RoutedAgent, message_handler, MessageContext

from messages import EnforceRequest, EnforceResult
from config import AUTO_ENFORCE, QUARANTINE_DIR


class EnforcerAgent(RoutedAgent):

    def __init__(self, auto_enforce: bool = False):
        super().__init__("EnforcerAgent")
        self._auto_enforce = auto_enforce or AUTO_ENFORCE

    async def _confirm(self, action_type: str, params: dict, severity: str) -> bool:
        """Ask for user confirmation before taking action."""
        print(f"\n  {'='*50}", flush=True)
        print(f"  ENFORCEMENT ACTION REQUESTED", flush=True)
        print(f"  {'='*50}", flush=True)
        print(f"  Action:   {action_type}", flush=True)
        print(f"  Severity: {severity}", flush=True)
        print(f"  Params:   {json.dumps(params, indent=4)}", flush=True)
        print(f"  {'='*50}", flush=True)

        # CRITICAL always requires confirmation
        if severity == "CRITICAL" or not self._auto_enforce:
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("  Confirm? [y/N]: ")
                )
                return response.strip().lower() in ("y", "yes")
            except EOFError:
                print("  [SKIPPED] Non-interactive terminal — action logged but not executed.", flush=True)
                return False

        # Auto-enforce for non-critical
        print("  [AUTO-ENFORCE] Proceeding automatically.", flush=True)
        return True

    @message_handler
    async def handle_enforce(
        self, message: EnforceRequest, ctx: MessageContext
    ) -> EnforceResult:
        print(f"  [ENFORCER] Action: {message.action_type} (Severity: {message.severity})", flush=True)

        params = json.loads(message.parameters_json)

        # VM enforcement — bypass REDBLUE_ checks, dispatch via SSH
        if message.action_type.startswith("vm_"):
            try:
                from vm_enforcement_tools import VM_ENFORCEMENT_DISPATCH
                vm_fn = VM_ENFORCEMENT_DISPATCH.get(message.action_type)
                if vm_fn:
                    print(f"  [ENFORCER] VM action: {message.action_type}", flush=True)
                    success, details = await vm_fn(params)
                    return EnforceResult(
                        action_type=message.action_type,
                        success=success,
                        details=details,
                    )
                else:
                    return EnforceResult(
                        action_type=message.action_type,
                        success=False,
                        details=f"Unknown VM action: {message.action_type}",
                    )
            except ImportError:
                return EnforceResult(
                    action_type=message.action_type,
                    success=False,
                    details="VM enforcement tools not available",
                )

        # ============================================================
        # SMART SAFETY: Only enforce on confirmed Red Team artefacts
        # ============================================================
        # In Red vs Blue game mode, Red Team creates artefacts with
        # "REDBLUE_" prefix. The Enforcer should ONLY act on those.
        # Everything else is a real system process/file — hands off.

        is_redblue_target = False
        target_info = ""

        # Check 1: Is the file path a REDBLUE_ artefact?
        file_path = (params.get("file_path", "") or params.get("program", "")).lower()
        if "redblue_" in file_path:
            is_redblue_target = True
            target_info = file_path

        # Check 2: For kill_process, verify target is a REDBLUE_ artefact
        if message.action_type == "kill_process":
            pid = params.get("pid")
            if not pid:
                # No PID provided — try to find by process_name but ONLY if REDBLUE_
                proc_name_param = (params.get("process_name", "") or "").lower()
                if "redblue_" in proc_name_param:
                    # Find PID by name
                    for proc in psutil.process_iter(["pid", "name", "exe"]):
                        try:
                            if "redblue_" in (proc.info.get("name", "") or "").lower() or \
                               "redblue_" in (proc.info.get("exe", "") or "").lower():
                                pid = proc.info["pid"]
                                params["pid"] = pid
                                is_redblue_target = True
                                target_info = f"{proc.info.get('name', '')} (PID {pid})"
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    if not pid:
                        return EnforceResult(
                            action_type=message.action_type,
                            success=False,
                            details=f"REDBLUE_ process '{proc_name_param}' not found.",
                        )
                else:
                    # No PID and not a REDBLUE_ name — block
                    print(f"  [ENFORCER] SAFE-BLOCK: kill_process without PID for non-REDBLUE_ target '{proc_name_param}' — skipping", flush=True)
                    return EnforceResult(
                        action_type=message.action_type,
                        success=False,
                        details=f"Safe-blocked: No PID provided and '{proc_name_param}' is not a REDBLUE_ artefact.",
                    )
            else:
                # PID provided — verify it's a REDBLUE_ artefact
                try:
                    proc = psutil.Process(pid)
                    proc_name = proc.name().lower()
                    proc_exe = (proc.exe() or "").lower()
                    proc_cmdline = " ".join(proc.cmdline() or []).lower()

                    if "redblue_" in proc_name or "redblue_" in proc_exe or "redblue_" in proc_cmdline:
                        is_redblue_target = True
                        target_info = f"{proc_name} (PID {pid})"
                    else:
                        print(f"  [ENFORCER] SAFE-BLOCK: PID {pid} ({proc_name}) is NOT a REDBLUE_ artefact — skipping", flush=True)
                        return EnforceResult(
                            action_type=message.action_type,
                            success=False,
                            details=f"Safe-blocked: {proc_name} (PID {pid}) has no REDBLUE_ marker.",
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return EnforceResult(
                        action_type=message.action_type,
                        success=False,
                        details=f"Process {pid} not found or access denied.",
                    )

        # Check 3: For quarantine_file, verify REDBLUE_ in path
        if message.action_type == "quarantine_file":
            qpath = (params.get("file_path", "") or "").lower()
            if "redblue_" not in qpath:
                print(f"  [ENFORCER] SAFE-BLOCK: '{qpath}' has no REDBLUE_ marker — skipping quarantine", flush=True)
                return EnforceResult(
                    action_type=message.action_type,
                    success=False,
                    details=f"Safe-blocked: '{params.get('file_path', '')}' is not a REDBLUE_ artefact.",
                )
            is_redblue_target = True
            target_info = qpath

        # Check 4: For disable_autorun, verify REDBLUE_ in value name
        if message.action_type == "disable_autorun":
            value_name = (params.get("value_name", "") or "").lower()
            if "redblue_" not in value_name:
                print(f"  [ENFORCER] SAFE-BLOCK: autorun '{value_name}' has no REDBLUE_ marker — skipping", flush=True)
                return EnforceResult(
                    action_type=message.action_type,
                    success=False,
                    details=f"Safe-blocked: autorun '{params.get('value_name', '')}' is not a REDBLUE_ artefact.",
                )
            is_redblue_target = True
            target_info = value_name

        # Check 5: For firewall rules, always allow (they're reversible)
        if message.action_type == "add_firewall_rule":
            is_redblue_target = True
            target_info = params.get("name", "")

        if is_redblue_target:
            print(f"  [ENFORCER] REDBLUE target confirmed: {target_info}", flush=True)

        # Confirm if needed — skip confirmation for REDBLUE_ targets in auto mode
        if message.requires_confirmation:
            if is_redblue_target and self._auto_enforce:
                print(f"  [ENFORCER] AUTO-ENFORCE (REDBLUE_ target): {message.action_type}", flush=True)
            else:
                confirmed = await self._confirm(message.action_type, params, message.severity)
                if not confirmed:
                    return EnforceResult(
                        action_type=message.action_type,
                        success=False,
                        details="Action denied by user.",
                    )

        try:
            if message.action_type == "kill_process":
                return await self._kill_process(params)
            elif message.action_type == "add_firewall_rule":
                return await self._add_firewall_rule(params)
            elif message.action_type == "quarantine_file":
                return await self._quarantine_file(params)
            elif message.action_type == "disable_autorun":
                return await self._disable_autorun(params)
            else:
                return EnforceResult(
                    action_type=message.action_type,
                    success=False,
                    details=f"Unknown action: {message.action_type}",
                )

        except Exception as e:
            return EnforceResult(
                action_type=message.action_type,
                success=False,
                details=f"Error: {e}",
            )

    async def _kill_process(self, params: dict) -> EnforceResult:
        """Terminate a process by PID."""
        pid = params.get("pid")
        if not pid:
            return EnforceResult("kill_process", False, "No PID provided")

        def _sync():
            try:
                proc = psutil.Process(pid)
                name = proc.name()
                proc.kill()
                return EnforceResult(
                    "kill_process", True,
                    f"Killed process {name} (PID {pid})",
                )
            except psutil.NoSuchProcess:
                return EnforceResult(
                    "kill_process", False,
                    f"Process {pid} no longer exists",
                )
            except psutil.AccessDenied:
                return EnforceResult(
                    "kill_process", False,
                    f"Access denied killing PID {pid}. Need higher privileges.",
                )

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def _add_firewall_rule(self, params: dict) -> EnforceResult:
        """Add a Windows Firewall block rule."""
        import subprocess

        rule_name = params.get("rule_name", "OS_Shield_Block")
        remote_ip = params.get("remote_ip", "")
        program = params.get("program", "")
        direction = params.get("direction", "out")

        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={rule_name}",
            f"dir={direction}",
            "action=block",
        ]
        if remote_ip:
            cmd.append(f"remoteip={remote_ip}")
        if program:
            cmd.append(f"program={program}")

        def _sync():
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                return EnforceResult(
                    "add_firewall_rule", True,
                    f"Firewall rule '{rule_name}' added. Blocked: {remote_ip or program}",
                )
            else:
                return EnforceResult(
                    "add_firewall_rule", False,
                    f"Failed: {proc.stderr.strip() or proc.stdout.strip()}",
                )

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def _quarantine_file(self, params: dict) -> EnforceResult:
        """Move a suspicious file to quarantine directory."""
        file_path = params.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            return EnforceResult(
                "quarantine_file", False,
                f"File not found: {file_path}",
            )

        def _sync():
            os.makedirs(QUARANTINE_DIR, exist_ok=True)
            basename = os.path.basename(file_path)
            dest = os.path.join(QUARANTINE_DIR, f"{basename}.quarantined")

            try:
                shutil.move(file_path, dest)
                return EnforceResult(
                    "quarantine_file", True,
                    f"Moved {file_path} -> {dest}",
                )
            except PermissionError:
                return EnforceResult(
                    "quarantine_file", False,
                    f"Permission denied moving {file_path}",
                )

        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    async def _disable_autorun(self, params: dict) -> EnforceResult:
        """Remove an autorun registry entry."""
        hive_name = params.get("hive", "HKCU")
        key_path = params.get("key_path", "")
        value_name = params.get("value_name", "")

        if not key_path or not value_name:
            return EnforceResult(
                "disable_autorun", False,
                "key_path and value_name are required",
            )

        hive_map = {
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKCU": winreg.HKEY_CURRENT_USER,
        }
        hive = hive_map.get(hive_name)
        if not hive:
            return EnforceResult(
                "disable_autorun", False,
                f"Unknown hive: {hive_name}",
            )

        def _sync():
            try:
                key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, value_name)
                winreg.CloseKey(key)
                return EnforceResult(
                    "disable_autorun", True,
                    f"Removed autorun: {hive_name}\\{key_path}\\{value_name}",
                )
            except FileNotFoundError:
                return EnforceResult(
                    "disable_autorun", False,
                    f"Registry value not found: {value_name}",
                )
            except PermissionError:
                return EnforceResult(
                    "disable_autorun", False,
                    f"Permission denied. Need Admin for {hive_name}.",
                )

        return await asyncio.get_event_loop().run_in_executor(None, _sync)
