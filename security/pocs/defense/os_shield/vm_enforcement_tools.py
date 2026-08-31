"""
VM Enforcement Tools
=====================
6 async enforcement actions executed inside the MultiseatOS VM via SSH (plus one
HTTP action for Vault token rotation).  Each function accepts a params dict and
returns ``tuple[bool, str]`` — (success, details).

Actions:
  1. vm_kill_process        — kill -9 <pid> via sudo
  2. vm_remove_backdoor     — clean crontab, .bashrc, rogue systemd services
  3. vm_restart_service     — systemctl restart <service>, verify active
  4. vm_block_ip            — iptables DROP rule for an IP
  5. vm_rotate_vault_tokens — HTTP POST to Vault /api/auth/revoke-all
  6. vm_restore_logs        — restore empty/missing log files, restart rsyslog
"""

import asyncio
import logging
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone

import paramiko

# Suppress noisy paramiko logs
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "offense", "red_blue"))
from infra import (
    VM_SSH_HOST,
    VM_SSH_PORT,
    VM_SSH_USER,
    VM_SSH_PASS,
    VAULT_HOST,
    VAULT_PORT,
)


# ================================================================
# SSH Helpers
# ================================================================

def _ssh_connect() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        VM_SSH_HOST,
        port=VM_SSH_PORT,
        username=VM_SSH_USER,
        password=VM_SSH_PASS,
        timeout=10,
        banner_timeout=15,
    )
    return ssh


def _ssh_run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 10) -> tuple[str, str]:
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return (
        out.read().decode("utf-8", errors="replace").strip(),
        err.read().decode("utf-8", errors="replace").strip(),
    )


# ================================================================
# Action 1: vm_kill_process
# ================================================================

async def vm_kill_process(params: dict) -> tuple[bool, str]:
    """
    Kill a process by PID using ``sudo kill -9 <pid>``.

    Params:
        pid (int): The process ID to kill.
    """
    pid = params.get("pid")
    if pid is None:
        return False, "Missing required param: pid"

    def _sync() -> tuple[bool, str]:
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return False, f"SSH connect failed: {exc}"

        try:
            out, err = _ssh_run(ssh, f"sudo kill -9 {pid} 2>&1", timeout=10)
            # Verify the process is gone
            verify_out, _ = _ssh_run(ssh, f"ps -p {pid} 2>/dev/null | wc -l", timeout=5)
            process_gone = verify_out.strip() in ("", "0", "1")  # header line = 1 means no process
            try:
                lines = int(verify_out.strip())
                process_gone = lines <= 1  # ps output has header; 1 line = only header = gone
            except ValueError:
                process_gone = True
        finally:
            ssh.close()

        if err and "no such process" in err.lower():
            return False, f"Process {pid} not found: {err}"
        if err and "operation not permitted" in err.lower():
            return False, f"Permission denied killing pid {pid}: {err}"
        if process_gone:
            return True, f"Process {pid} killed successfully. kill output: '{out or '(none)'}'"
        return False, f"kill command ran but process {pid} may still be alive. Output: '{out}' Err: '{err}'"

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Action 2: vm_remove_backdoor
# ================================================================

async def vm_remove_backdoor(params: dict) -> tuple[bool, str]:
    """
    Remove persistence mechanisms from the VM:
      - Strip suspicious entries from crontab
      - Remove REDBLUE / reverse / backdoor lines from ~/.bashrc
      - Disable a rogue systemd service if ``service_name`` is provided
      - Always disable and stop ``redblue-backdoor`` service

    Params:
        service_name (str, optional): Extra rogue service name to disable.
    """
    service_name: str | None = params.get("service_name")

    def _sync() -> tuple[bool, str]:
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return False, f"SSH connect failed: {exc}"

        steps: list[str] = []
        errors: list[str] = []

        try:
            # --- Clean crontab ---
            suspicious_keywords = ["bash", "python", "curl", "wget", "nc ", "ncat", "/tmp", "b64", "base64"]
            crontab_out, _ = _ssh_run(ssh, "crontab -l 2>/dev/null || true")
            clean_lines = []
            removed_lines = []
            for line in crontab_out.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    clean_lines.append(line)
                    continue
                if any(kw in stripped.lower() for kw in suspicious_keywords):
                    removed_lines.append(stripped)
                else:
                    clean_lines.append(line)

            if removed_lines:
                new_crontab = "\n".join(clean_lines) + "\n"
                # Write cleaned crontab via stdin
                import io
                stdin_chan = ssh.get_transport().open_session()
                stdin_chan.exec_command("crontab -")
                stdin_chan.sendall(new_crontab.encode())
                stdin_chan.shutdown_write()
                stdin_chan.recv_exit_status()
                stdin_chan.close()
                steps.append(f"Crontab: removed {len(removed_lines)} suspicious entries: {removed_lines[:3]}")
            else:
                steps.append("Crontab: no suspicious entries found")

            # --- Clean .bashrc ---
            bashrc_keywords = ["REDBLUE", "reverse", "backdoor"]
            bashrc_raw, _ = _ssh_run(ssh, "cat ~/.bashrc 2>/dev/null || true")
            bashrc_lines = bashrc_raw.splitlines()
            clean_bashrc = []
            removed_bashrc = []
            for line in bashrc_lines:
                if any(kw.lower() in line.lower() for kw in bashrc_keywords):
                    removed_bashrc.append(line.strip())
                else:
                    clean_bashrc.append(line)

            if removed_bashrc:
                new_bashrc = "\n".join(clean_bashrc) + "\n"
                # Write via heredoc — escape single quotes in content
                escaped = new_bashrc.replace("'", "'\\''")
                write_out, write_err = _ssh_run(
                    ssh,
                    f"printf '%s' '{escaped}' > ~/.bashrc",
                    timeout=10,
                )
                if write_err:
                    errors.append(f".bashrc write error: {write_err}")
                else:
                    steps.append(f".bashrc: removed {len(removed_bashrc)} suspicious lines: {removed_bashrc[:3]}")
            else:
                steps.append(".bashrc: no suspicious lines found")

            # --- Disable redblue-backdoor (always) ---
            for svc in filter(None, ["redblue-backdoor", service_name]):
                stop_out, stop_err = _ssh_run(ssh, f"sudo systemctl stop {svc} 2>&1 || true", timeout=10)
                disable_out, disable_err = _ssh_run(ssh, f"sudo systemctl disable {svc} 2>&1 || true", timeout=10)
                if "not found" in (stop_out + stop_err + disable_out + disable_err).lower():
                    steps.append(f"Service '{svc}': not found (already clean)")
                else:
                    steps.append(
                        f"Service '{svc}': stop='{(stop_out or stop_err)[:100]}' "
                        f"disable='{(disable_out or disable_err)[:100]}'"
                    )

        except Exception as exc:
            errors.append(f"Unexpected error: {exc}")
        finally:
            ssh.close()

        detail = " | ".join(steps)
        if errors:
            detail += " | ERRORS: " + "; ".join(errors)
        success = len(errors) == 0
        return success, detail

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Action 3: vm_restart_service
# ================================================================

async def vm_restart_service(params: dict) -> tuple[bool, str]:
    """
    Restart a systemd service and verify it is active afterwards.

    Params:
        service_name (str): Name of the systemd service to restart.
    """
    service_name = params.get("service_name")
    if not service_name:
        return False, "Missing required param: service_name"

    def _sync() -> tuple[bool, str]:
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return False, f"SSH connect failed: {exc}"

        try:
            restart_out, restart_err = _ssh_run(
                ssh, f"sudo systemctl restart {service_name} 2>&1", timeout=15
            )
            status_out, _ = _ssh_run(
                ssh, f"systemctl is-active {service_name} 2>/dev/null || true", timeout=5
            )
            is_active = status_out.strip() == "active"
        finally:
            ssh.close()

        if is_active:
            return True, f"Service '{service_name}' restarted and is active."
        combined = (restart_out + " " + restart_err).strip()
        return False, (
            f"Service '{service_name}' restarted but status is '{status_out.strip()}'. "
            f"Restart output: '{combined[:300]}'"
        )

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Action 4: vm_block_ip
# ================================================================

async def vm_block_ip(params: dict) -> tuple[bool, str]:
    """
    Block an IP address using iptables: ``iptables -A INPUT -s <ip> -j DROP``.

    Params:
        ip (str): IPv4 address to block.
    """
    ip = params.get("ip")
    if not ip:
        return False, "Missing required param: ip"

    def _sync() -> tuple[bool, str]:
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return False, f"SSH connect failed: {exc}"

        try:
            out, err = _ssh_run(
                ssh, f"sudo iptables -A INPUT -s {ip} -j DROP 2>&1", timeout=10
            )
            # Verify the rule exists
            check_out, _ = _ssh_run(
                ssh,
                f"sudo iptables -C INPUT -s {ip} -j DROP 2>/dev/null && echo RULE_EXISTS || echo RULE_MISSING",
                timeout=5,
            )
            rule_confirmed = "RULE_EXISTS" in check_out
        finally:
            ssh.close()

        if err and "invalid" in err.lower():
            return False, f"iptables error for IP '{ip}': {err}"
        if rule_confirmed:
            return True, f"IP {ip} blocked via iptables INPUT DROP rule (confirmed)."
        combined = (out + " " + err).strip()
        return False, f"iptables command ran but rule not confirmed for {ip}. Output: '{combined[:300]}'"

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Action 5: vm_rotate_vault_tokens
# ================================================================

async def vm_rotate_vault_tokens(params: dict) -> tuple[bool, str]:
    """
    Revoke all Vault tokens via HTTP POST to /api/auth/revoke-all.
    No SSH required — communicates directly with the Vault container.

    Params: {} (no parameters needed)
    """

    def _sync() -> tuple[bool, str]:
        url = f"http://{VAULT_HOST}:{VAULT_PORT}/api/auth/revoke-all"
        try:
            req = urllib.request.Request(url, data=b"{}", method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                status = resp.status
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = {"raw": body[:300]}
            if status in (200, 201, 204):
                return True, f"Vault token revocation succeeded (HTTP {status}): {data}"
            return False, f"Vault revoke-all returned HTTP {status}: {data}"
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            return False, f"Vault HTTP error {exc.code}: {body}"
        except urllib.error.URLError as exc:
            return False, f"Vault unreachable at {url}: {exc.reason}"
        except Exception as exc:
            return False, f"Unexpected error rotating vault tokens: {exc}"

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Action 6: vm_restore_logs
# ================================================================

async def vm_restore_logs(params: dict) -> tuple[bool, str]:
    """
    Restore empty or missing log files on the VM, then restart rsyslog.

    For each of auth.log, syslog, and kern.log:
      - If the file is missing or empty, write a "Log restored at <date>" entry.
    Then restart rsyslog.

    Params: {} (no parameters needed)
    """
    LOG_FILES = [
        "/var/log/auth.log",
        "/var/log/syslog",
        "/var/log/kern.log",
    ]

    def _sync() -> tuple[bool, str]:
        try:
            ssh = _ssh_connect()
        except Exception as exc:
            return False, f"SSH connect failed: {exc}"

        steps: list[str] = []
        errors: list[str] = []

        try:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            for log_path in LOG_FILES:
                stat_out, _ = _ssh_run(
                    ssh,
                    f"stat -c '%s' {log_path} 2>/dev/null || echo MISSING",
                    timeout=5,
                )
                needs_restore = False
                if stat_out.strip() == "MISSING":
                    needs_restore = True
                    reason = "missing"
                else:
                    try:
                        size = int(stat_out.strip())
                        if size == 0:
                            needs_restore = True
                            reason = "empty (0 bytes)"
                        else:
                            reason = f"{size} bytes — ok"
                    except ValueError:
                        needs_restore = True
                        reason = "unreadable stat"

                if needs_restore:
                    restore_msg = f"Log restored at {now_str}"
                    write_out, write_err = _ssh_run(
                        ssh,
                        f"sudo sh -c 'echo \"{restore_msg}\" >> {log_path}'",
                        timeout=5,
                    )
                    if write_err and "permission denied" in write_err.lower():
                        errors.append(f"{log_path}: write permission denied")
                    else:
                        steps.append(f"{log_path}: restored ({reason})")
                else:
                    steps.append(f"{log_path}: {reason}")

            # --- Restart rsyslog ---
            rsyslog_out, rsyslog_err = _ssh_run(
                ssh, "sudo systemctl restart rsyslog 2>&1", timeout=15
            )
            rsyslog_status, _ = _ssh_run(
                ssh, "systemctl is-active rsyslog 2>/dev/null || true", timeout=5
            )
            if rsyslog_status.strip() == "active":
                steps.append("rsyslog restarted and active")
            else:
                combined = (rsyslog_out + " " + rsyslog_err).strip()
                errors.append(
                    f"rsyslog restart issue — status: '{rsyslog_status.strip()}' output: '{combined[:200]}'"
                )

        except Exception as exc:
            errors.append(f"Unexpected error: {exc}")
        finally:
            ssh.close()

        detail = " | ".join(steps)
        if errors:
            detail += " | ERRORS: " + "; ".join(errors)
        success = len(errors) == 0
        return success, detail

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


# ================================================================
# Dispatch table
# ================================================================

VM_ENFORCEMENT_DISPATCH: dict = {
    "vm_kill_process": vm_kill_process,
    "vm_remove_backdoor": vm_remove_backdoor,
    "vm_restart_service": vm_restart_service,
    "vm_block_ip": vm_block_ip,
    "vm_rotate_vault_tokens": vm_rotate_vault_tokens,
    "vm_restore_logs": vm_restore_logs,
}
