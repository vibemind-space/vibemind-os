#!/usr/bin/env python3
"""
Stealth IDS - disguised as dbus-session-helper
Real monitoring service for the Red vs Blue security exercise.
Binary path: /usr/lib/dbus-1.0/session-helper
"""

import os
import sys
import json
import time
import socket
import hashlib
import logging
import subprocess
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROCESS_NAME   = "dbus-session-helper"
METRICS_LOG    = "/var/lib/.cache/.metrics"
HEARTBEAT_FILE = "/var/lib/.cache/.heartbeat"
DECOY_KILLED   = "/var/lib/.cache/.decoy_killed"
BASELINE_FILE  = "/var/lib/.cache/.stealth_baseline.json"

DECOY_SERVICE  = "vm-security-monitor"
CHECK_INTERVAL = 10  # seconds
HTTP_PORT      = 19091

SUSPICIOUS_PORTS = [4444, 5555, 1337, 6667, 8888, 9999]

LOG_FILES = ["/var/log/auth.log", "/var/log/syslog"]
CREDENTIAL_FILES = ["/etc/shadow", "/etc/sudoers"]
SSH_DIR = os.path.expanduser("~/.ssh")

# ---------------------------------------------------------------------------
# Logging (silent — no stdout noise)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.NullHandler()],
)

# ---------------------------------------------------------------------------
# Alert writer
# ---------------------------------------------------------------------------

def _ensure_cache_dir():
    cache_dir = os.path.dirname(METRICS_LOG)
    os.makedirs(cache_dir, exist_ok=True)


def write_alert(level: str, cat: str, msg: str, details: dict = None):
    """Append one JSON alert line to the metrics log."""
    _ensure_cache_dir()
    record = {
        "ts":      datetime.now(timezone.utc).isoformat(),
        "level":   level,
        "cat":     cat,
        "msg":     msg,
        "details": details or {},
    }
    try:
        with open(METRICS_LOG, "a") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception as exc:
        pass  # silently ignore write errors inside a stealth service


def write_heartbeat():
    _ensure_cache_dir()
    try:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(datetime.now(timezone.utc).isoformat())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Baseline capture
# ---------------------------------------------------------------------------

def _get_pids() -> list:
    try:
        result = subprocess.run(
            ["ps", "-e", "-o", "pid="],
            capture_output=True, text=True, timeout=5
        )
        return [p.strip() for p in result.stdout.splitlines() if p.strip()]
    except Exception:
        return []


def _get_crontab() -> str:
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except Exception:
        return ""


def _get_file_mtime(path: str):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def _hash_directory(dirpath: str) -> str:
    """Return a SHA-256 hash of all filenames + file contents in a directory."""
    h = hashlib.sha256()
    try:
        for root, dirs, files in os.walk(dirpath):
            dirs.sort()
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                h.update(fpath.encode())
                try:
                    with open(fpath, "rb") as fh:
                        h.update(fh.read())
                except Exception:
                    pass
    except Exception:
        pass
    return h.hexdigest()


def capture_baseline() -> dict:
    baseline = {
        "captured_at":   datetime.now(timezone.utc).isoformat(),
        "pids":          _get_pids(),
        "crontab":       _get_crontab(),
        "credential_mtimes": {
            path: _get_file_mtime(path) for path in CREDENTIAL_FILES
        },
        "ssh_hash":      _hash_directory(SSH_DIR),
    }
    return baseline


def save_baseline(baseline: dict):
    _ensure_cache_dir()
    try:
        with open(BASELINE_FILE, "w") as fh:
            json.dump(baseline, fh, indent=2)
    except Exception:
        pass


def load_baseline() -> dict:
    try:
        with open(BASELINE_FILE) as fh:
            return json.load(fh)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_decoy_service(state: dict):
    """CRITICAL if the decoy IDS service is no longer running."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", DECOY_SERVICE],
            timeout=5
        )
        running = (result.returncode == 0)
    except Exception:
        running = False

    was_running = state.get("decoy_was_running", True)

    if not running:
        if was_running:
            # First time we notice it's gone
            write_alert(
                level="CRITICAL",
                cat="decoy_killed",
                msg=f"Decoy service '{DECOY_SERVICE}' is no longer running",
                details={"service": DECOY_SERVICE},
            )
            _ensure_cache_dir()
            try:
                with open(DECOY_KILLED, "w") as fh:
                    fh.write(datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        state["decoy_was_running"] = False
    else:
        state["decoy_was_running"] = True


def check_process_changes(baseline: dict, state: dict):
    """HIGH alert if >20 new PIDs compared to baseline."""
    baseline_pids = set(baseline.get("pids", []))
    current_pids  = set(_get_pids())
    new_pids = current_pids - baseline_pids

    if len(new_pids) > 20:
        # Avoid alert storm: only alert if count changed significantly
        last_new_count = state.get("last_new_pid_count", 0)
        if len(new_pids) != last_new_count:
            write_alert(
                level="HIGH",
                cat="process_flood",
                msg=f"{len(new_pids)} new processes detected since baseline",
                details={"new_pid_count": len(new_pids), "sample": list(new_pids)[:20]},
            )
        state["last_new_pid_count"] = len(new_pids)
    else:
        state["last_new_pid_count"] = len(new_pids)


def check_crontab_changes(baseline: dict, state: dict):
    """CRITICAL if crontab contents differ from baseline."""
    baseline_cron = baseline.get("crontab", "")
    current_cron  = _get_crontab()

    if current_cron != baseline_cron:
        if not state.get("crontab_alerted"):
            write_alert(
                level="CRITICAL",
                cat="crontab_changed",
                msg="Crontab has been modified since baseline",
                details={
                    "baseline_lines": len(baseline_cron.splitlines()),
                    "current_lines":  len(current_cron.splitlines()),
                },
            )
            state["crontab_alerted"] = True
    else:
        state["crontab_alerted"] = False


def check_credential_access(baseline: dict, state: dict):
    """CRITICAL if /etc/shadow or /etc/sudoers mtime changed."""
    baseline_mtimes = baseline.get("credential_mtimes", {})
    for path in CREDENTIAL_FILES:
        current_mtime = _get_file_mtime(path)
        baseline_mtime = baseline_mtimes.get(path)
        key = f"cred_alerted_{path}"
        if baseline_mtime is not None and current_mtime != baseline_mtime:
            if not state.get(key):
                write_alert(
                    level="CRITICAL",
                    cat="credential_access",
                    msg=f"Credential file modified: {path}",
                    details={
                        "path":           path,
                        "baseline_mtime": baseline_mtime,
                        "current_mtime":  current_mtime,
                    },
                )
                state[key] = True
        else:
            state[key] = False


def check_ssh_key_changes(baseline: dict, state: dict):
    """HIGH alert if ~/.ssh contents changed."""
    baseline_hash = baseline.get("ssh_hash", "")
    current_hash  = _hash_directory(SSH_DIR)

    if current_hash != baseline_hash:
        if not state.get("ssh_alerted"):
            write_alert(
                level="HIGH",
                cat="ssh_keys_changed",
                msg="SSH keys or ~/.ssh directory contents changed",
                details={
                    "ssh_dir":       SSH_DIR,
                    "baseline_hash": baseline_hash,
                    "current_hash":  current_hash,
                },
            )
            state["ssh_alerted"] = True
    else:
        state["ssh_alerted"] = False


def check_log_tampering(state: dict):
    """CRITICAL if auth.log or syslog is 0 bytes or missing."""
    for path in LOG_FILES:
        key = f"log_tamper_alerted_{path}"
        try:
            size = os.path.getsize(path)
            if size == 0:
                if not state.get(key):
                    write_alert(
                        level="CRITICAL",
                        cat="log_tampered",
                        msg=f"Log file is empty (possible tampering): {path}",
                        details={"path": path, "size": size},
                    )
                    state[key] = True
            else:
                state[key] = False
        except FileNotFoundError:
            if not state.get(key):
                write_alert(
                    level="CRITICAL",
                    cat="log_tampered",
                    msg=f"Log file missing (possible tampering): {path}",
                    details={"path": path},
                )
                state[key] = True
        except Exception:
            state[key] = False


def check_suspicious_ports(state: dict):
    """HIGH alert for listeners on suspicious ports."""
    listening = []
    for port in SUSPICIOUS_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                result = s.connect_ex(("127.0.0.1", port))
                if result == 0:
                    listening.append(port)
            except Exception:
                pass

    prev_listening = set(state.get("suspicious_ports_seen", []))
    new_listening  = set(listening) - prev_listening

    for port in new_listening:
        write_alert(
            level="HIGH",
            cat="suspicious_listener",
            msg=f"Suspicious listener detected on port {port}",
            details={"port": port, "known_backdoor_ports": SUSPICIOUS_PORTS},
        )

    state["suspicious_ports_seen"] = list(set(listening))


# ---------------------------------------------------------------------------
# Monitoring loop
# ---------------------------------------------------------------------------

def monitoring_loop():
    # Capture and save baseline
    baseline = capture_baseline()
    save_baseline(baseline)

    write_alert(
        level="INFO",
        cat="startup",
        msg="Stealth IDS started",
        details={"pid": os.getpid(), "name": PROCESS_NAME},
    )

    state = {}

    while True:
        try:
            write_heartbeat()
            check_decoy_service(state)
            check_process_changes(baseline, state)
            check_crontab_changes(baseline, state)
            check_credential_access(baseline, state)
            check_ssh_key_changes(baseline, state)
            check_log_tampering(state)
            check_suspicious_ports(state)
        except Exception as exc:
            write_alert(
                level="ERROR",
                cat="monitor_error",
                msg=f"Monitoring loop error: {exc}",
                details={"exception": str(exc)},
            )

        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# HTTP metrics server
# ---------------------------------------------------------------------------

class MetricsHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler — disguised as a Prometheus metrics exporter."""

    def log_message(self, fmt, *args):
        # Suppress access log noise
        pass

    def do_GET(self):
        if self.path == "/metrics":
            self._serve_file(METRICS_LOG, "application/json")
        elif self.path == "/heartbeat":
            self._serve_file(HEARTBEAT_FILE, "text/plain")
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, path: str, content_type: str):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
        except Exception:
            self.send_response(500)
            self.end_headers()


def start_http_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Rename process title if possible (best-effort)
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        libc.prctl(15, PROCESS_NAME.encode(), 0, 0, 0)
    except Exception:
        pass

    # Also try setproctitle if available
    try:
        import setproctitle
        setproctitle.setproctitle(PROCESS_NAME)
    except ImportError:
        pass

    # Ensure cache directory exists and clear old metrics
    _ensure_cache_dir()
    try:
        open(METRICS_LOG, "w").close()
    except Exception:
        pass

    # Start HTTP server in background thread
    start_http_server()

    # Run monitoring loop (blocks forever)
    monitoring_loop()


if __name__ == "__main__":
    main()
