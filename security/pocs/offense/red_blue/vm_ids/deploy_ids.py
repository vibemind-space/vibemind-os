#!/usr/bin/env python3
"""
deploy_ids.py — Deploy both IDS components into the MultiseatOS VM.

Deploys:
  1. decoy_ids.py  -> /home/vibemind/vm-security-monitor/monitor.py
                     systemd: vm-security-monitor.service  (visible honeypot)
  2. stealth_ids.py -> /usr/lib/dbus-1.0/session-helper
                      systemd: dbus-session-helper.service  (hidden real IDS)

Run as a module:
    python -m vm_ids.deploy_ids
"""

import io
import sys
import time
import logging
from pathlib import Path

import paramiko

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# Import infra constants — works both as a package module and as a direct run
# ---------------------------------------------------------------------------
try:
    from infra import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from infra import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_PASS

# ---------------------------------------------------------------------------
# Local source files (sit next to this script)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent

DECOY_LOCAL   = _HERE / "decoy_ids.py"
STEALTH_LOCAL = _HERE / "stealth_ids.py"

# Remote destinations
DECOY_REMOTE_DIR    = "/home/vibemind/vm-security-monitor"
DECOY_REMOTE_PATH   = DECOY_REMOTE_DIR + "/monitor.py"
STEALTH_REMOTE_PATH = "/usr/lib/dbus-1.0/session-helper"

# Systemd unit names
DECOY_SERVICE   = "vm-security-monitor"
STEALTH_SERVICE = "dbus-session-helper"

# Stale state files to remove before fresh start
STALE_FILES = [
    "/var/lib/.cache/.metrics",
    "/var/lib/.cache/.decoy_killed",
    "/var/lib/.cache/.heartbeat",
]

# ---------------------------------------------------------------------------
# Systemd unit definitions
# ---------------------------------------------------------------------------

DECOY_UNIT = """\
[Unit]
Description=VM Security Monitor
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/vibemind/vm-security-monitor/monitor.py
ExecStopPost=/usr/bin/python3 /home/vibemind/vm-security-monitor/monitor.py --alarm
Restart=no
[Install]
WantedBy=multi-user.target
"""

STEALTH_UNIT = """\
[Unit]
Description=D-Bus Session Helper
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/lib/dbus-1.0/session-helper
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
"""

# ---------------------------------------------------------------------------
# SSH / SFTP helpers
# ---------------------------------------------------------------------------

def _ssh_exec(ssh: paramiko.SSHClient, cmd: str, timeout: int = 30) -> tuple:
    """Execute cmd on the remote host; return (rc, stdout_str, stderr_str)."""
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc  = stdout.channel.recv_exit_status()
    return rc, out, err


def _sudo_exec(ssh: paramiko.SSHClient, cmd: str, timeout: int = 30) -> tuple:
    """
    Run cmd with sudo by feeding the password through the channel's stdin.
    This avoids embedding credentials in a shell string.
    """
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.settimeout(timeout)
    chan.exec_command("sudo -S " + cmd)
    # Feed password to sudo's stdin prompt
    chan.sendall((VM_SSH_PASS + "\n").encode())
    chan.shutdown_write()
    out = b""
    err = b""
    while not chan.closed or chan.recv_ready() or chan.recv_stderr_ready():
        if chan.recv_ready():
            out += chan.recv(4096)
        if chan.recv_stderr_ready():
            err += chan.recv_stderr(4096)
        if chan.exit_status_ready():
            break
        time.sleep(0.05)
    rc = chan.recv_exit_status()
    chan.close()
    return rc, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


def _sftp_upload_file(ssh: paramiko.SSHClient, local_path: Path, remote_path: str) -> None:
    """Upload a local file to a user-writable remote path via SFTP."""
    sftp = ssh.open_sftp()
    try:
        sftp.put(str(local_path), remote_path)
    finally:
        sftp.close()


def _sftp_write_text(ssh: paramiko.SSHClient, content: str, remote_path: str) -> None:
    """Write a text string to a user-writable remote path via SFTP."""
    sftp = ssh.open_sftp()
    try:
        with sftp.file(remote_path, "w") as fh:
            fh.write(content)
    finally:
        sftp.close()


def _is_active(ssh: paramiko.SSHClient, service: str) -> bool:
    rc, _, _ = _ssh_exec(ssh, "systemctl is-active --quiet " + service)
    return rc == 0


# ---------------------------------------------------------------------------
# Deploy steps
# ---------------------------------------------------------------------------

def _deploy_decoy(ssh: paramiko.SSHClient) -> None:
    """Upload decoy_ids.py and install its systemd unit."""
    print("[IDS] Deploying decoy IDS (vm-security-monitor)...")

    # Create user-owned directory (no sudo needed)
    _ssh_exec(ssh, "mkdir -p " + DECOY_REMOTE_DIR)

    # Upload script via SFTP (user-writable path)
    _sftp_upload_file(ssh, DECOY_LOCAL, DECOY_REMOTE_PATH)
    _ssh_exec(ssh, "chmod 755 " + DECOY_REMOTE_PATH)

    # Write unit to /tmp (user-writable), then copy to /etc/systemd/system/ via sudo
    tmp_unit = "/tmp/vm-security-monitor.service"
    _sftp_write_text(ssh, DECOY_UNIT, tmp_unit)
    _sudo_exec(ssh, "cp " + tmp_unit + " /etc/systemd/system/" + DECOY_SERVICE + ".service")
    _sudo_exec(ssh, "chmod 644 /etc/systemd/system/" + DECOY_SERVICE + ".service")
    _ssh_exec(ssh, "rm -f " + tmp_unit)


def _deploy_stealth(ssh: paramiko.SSHClient) -> None:
    """Upload stealth_ids.py and install its systemd unit."""
    print("[IDS] Deploying stealth IDS (dbus-session-helper)...")

    stealth_dir = str(Path(STEALTH_REMOTE_PATH).parent)
    _sudo_exec(ssh, "mkdir -p " + stealth_dir)

    # Upload to /tmp first (user-writable), then move to root-owned path via sudo
    tmp_script = "/tmp/_stealth_ids_upload.py"
    _sftp_upload_file(ssh, STEALTH_LOCAL, tmp_script)
    _sudo_exec(ssh, "cp " + tmp_script + " " + STEALTH_REMOTE_PATH)
    _sudo_exec(ssh, "chmod 755 " + STEALTH_REMOTE_PATH)
    _ssh_exec(ssh, "rm -f " + tmp_script)

    # Write unit to /tmp, then copy via sudo
    tmp_unit = "/tmp/dbus-session-helper.service"
    _sftp_write_text(ssh, STEALTH_UNIT, tmp_unit)
    _sudo_exec(ssh, "cp " + tmp_unit + " /etc/systemd/system/" + STEALTH_SERVICE + ".service")
    _sudo_exec(ssh, "chmod 644 /etc/systemd/system/" + STEALTH_SERVICE + ".service")
    _ssh_exec(ssh, "rm -f " + tmp_unit)


def _reload_and_start(ssh: paramiko.SSHClient) -> None:
    """Reload systemd daemon, then enable and start both services."""
    print("[IDS] Reloading systemd and starting services...")

    _sudo_exec(ssh, "systemctl daemon-reload")

    for svc in (DECOY_SERVICE, STEALTH_SERVICE):
        _sudo_exec(ssh, "systemctl enable --now " + svc)
        time.sleep(1)
        # Restart in case a previous instance was already running
        _sudo_exec(ssh, "systemctl restart " + svc)


def _clear_stale_state(ssh: paramiko.SSHClient) -> None:
    """Remove old metrics and alert files so the new run starts clean."""
    print("[IDS] Clearing stale state files...")
    for path in STALE_FILES:
        _sudo_exec(ssh, "rm -f " + path)


def _verify_services(ssh: paramiko.SSHClient) -> bool:
    """Verify both services are active; return True only if both are running."""
    time.sleep(2)  # allow systemd to settle

    decoy_ok   = _is_active(ssh, DECOY_SERVICE)
    stealth_ok = _is_active(ssh, STEALTH_SERVICE)

    if decoy_ok:
        print("[IDS] Decoy: active")
    else:
        print("[IDS] Decoy: FAILED (not active)", file=sys.stderr)

    if stealth_ok:
        print("[IDS] Stealth: active")
    else:
        print("[IDS] Stealth: FAILED (not active)", file=sys.stderr)

    return decoy_ok and stealth_ok


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deploy() -> bool:
    """
    Connect to the VM via SSH and deploy both IDS services.

    Returns True on success, False if anything failed.
    """
    print("[IDS] Deploying...")

    # Verify source files exist before opening any connection
    for local in (DECOY_LOCAL, STEALTH_LOCAL):
        if not local.exists():
            print("[IDS] ERROR: source file not found: " + str(local), file=sys.stderr)
            return False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            VM_SSH_HOST,
            port=VM_SSH_PORT,
            username=VM_SSH_USER,
            password=VM_SSH_PASS,
            timeout=10,
            banner_timeout=15,
        )
    except Exception as exc:
        print("[IDS] ERROR: SSH connection failed: " + str(exc), file=sys.stderr)
        return False

    try:
        _deploy_decoy(ssh)
        _deploy_stealth(ssh)
        _reload_and_start(ssh)
        _clear_stale_state(ssh)
        ok = _verify_services(ssh)
        if ok:
            print("[IDS] Deployment complete.")
        else:
            print("[IDS] Deployment finished with errors.", file=sys.stderr)
        return ok
    except Exception as exc:
        print("[IDS] ERROR: deployment failed: " + str(exc), file=sys.stderr)
        return False
    finally:
        ssh.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    success = deploy()
    sys.exit(0 if success else 1)
