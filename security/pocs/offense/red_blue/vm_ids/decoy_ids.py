#!/usr/bin/env python3
"""
decoy_ids.py — Decoy IDS (Honeypot Security Monitor)

Runs as vm-security-monitor.service inside the VM. This process is
intentionally visible so that the Red Team will find and kill it.
Killing the systemd service triggers an alarm written to disk by the
service's ExecStopPost hook.

Systemd unit snippet (for reference, deployed separately):
    [Service]
    ExecStart=/usr/bin/python3 /opt/vm-ids/decoy_ids.py
    ExecStopPost=/usr/bin/python3 /opt/vm-ids/decoy_ids.py --alarm
    Restart=no

Log format: one JSON object per line at /var/log/vm-security.log
Alarm file: /var/lib/.cache/.decoy_killed
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_PATH = "/var/log/vm-security.log"
ALARM_PATH = "/var/lib/.cache/.decoy_killed"
CHECK_INTERVAL = 10  # seconds

# Process names that look suspicious in this environment.
SUSPICIOUS_PROCESS_PATTERNS = [
    r"\bnc\b",
    r"\bnetcat\b",
    r"\bncat\b",
    r"\bsocat\b",
    r"\bmsfconsole\b",
    r"\bmsfvenom\b",
    r"\bmetasploit\b",
    r"\bcobalt\b",
    r"\bempire\b",
    r"\bsliver\b",
    r"\bbindshell\b",
    r"\brevshell\b",
    r"\bxterm\b.*-display",
    r"\bpython[23]?\b.*-c.*socket",
    r"\bbash\b.*-i.*>&",
    r"\bsh\b.*-i.*>&",
]

# Crontab content patterns that suggest a backdoor.
BACKDOOR_CRON_PATTERNS = [
    r"nc\s+-",
    r"ncat\s",
    r"socat\s",
    r"bash\s+-i",
    r"/dev/tcp/",
    r"/dev/udp/",
    r"curl\s.*\|\s*bash",
    r"wget\s.*\|\s*bash",
    r"curl\s.*\|\s*sh",
    r"wget\s.*\|\s*sh",
    r"python\s+-c",
    r"python3\s+-c",
    r"perl\s+-e",
    r"ruby\s+-e",
    r"chmod\s.*\+x",
    r"base64\s+--decode",
    r"base64\s+-d",
]

# Ports that are suspicious when listening unexpectedly.
SUSPICIOUS_PORTS = {4444, 5555, 1337, 6667}


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _ensure_log_dir() -> None:
    log_dir = os.path.dirname(LOG_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


def write_log(level: str, message: str, details: dict | None = None) -> None:
    """Append a single JSON log entry to LOG_PATH."""
    entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    if details:
        entry["details"] = details

    line = json.dumps(entry)

    try:
        _ensure_log_dir()
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        # Fall back to stderr so systemd journal still captures it.
        print(f"[decoy_ids] failed to write log: {exc} — entry: {line}",
              file=sys.stderr)

    # Also mirror to stdout so journalctl shows structured output.
    print(line, flush=True)


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
    except OSError as exc:
        return -1, "", str(exc)


def check_processes() -> list[dict]:
    """Return a list of alert dicts for suspicious running processes."""
    alerts = []
    rc, stdout, _ = _run(["ps", "aux"])
    if rc != 0:
        return alerts

    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in SUSPICIOUS_PROCESS_PATTERNS]

    for line in stdout.splitlines()[1:]:  # skip header
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        cmdline = parts[10]
        pid = parts[1]
        user = parts[0]
        for pattern_str, regex in compiled:
            if regex.search(cmdline):
                alerts.append({
                    "pid": pid,
                    "user": user,
                    "cmdline": cmdline,
                    "matched_pattern": pattern_str,
                })
                break  # one alert per process

    return alerts


def check_crontab() -> list[dict]:
    """Return a list of alert dicts for suspicious crontab entries."""
    alerts = []
    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in BACKDOOR_CRON_PATTERNS]

    # Check system-wide crontab locations.
    cron_sources: list[tuple[str, list[str]]] = [
        ("crontab -l (root)", ["crontab", "-l"]),
    ]

    # Also scan /etc/cron* files directly.
    cron_dirs = [
        "/etc/crontab",
        "/etc/cron.d",
        "/var/spool/cron/crontabs",
    ]

    def _scan_content(source: str, content: str) -> None:
        for lineno, raw_line in enumerate(content.splitlines(), 1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for pattern_str, regex in compiled:
                if regex.search(stripped):
                    alerts.append({
                        "source": source,
                        "line": lineno,
                        "content": stripped,
                        "matched_pattern": pattern_str,
                    })
                    break

    # crontab -l for root
    for label, cmd in cron_sources:
        rc, stdout, _ = _run(cmd)
        if rc == 0 and stdout:
            _scan_content(label, stdout)

    # Walk cron directories / files
    for path in cron_dirs:
        if os.path.isfile(path):
            try:
                _scan_content(path, open(path, encoding="utf-8", errors="replace").read())
            except OSError:
                pass
        elif os.path.isdir(path):
            try:
                for fname in os.listdir(path):
                    fpath = os.path.join(path, fname)
                    if os.path.isfile(fpath):
                        try:
                            _scan_content(
                                fpath,
                                open(fpath, encoding="utf-8", errors="replace").read(),
                            )
                        except OSError:
                            pass
            except OSError:
                pass

    return alerts


def check_network_listeners() -> list[dict]:
    """Return a list of alert dicts for suspicious listening ports."""
    alerts = []

    # Try ss first, fall back to netstat.
    rc, stdout, _ = _run(["ss", "-tlnup"])
    if rc != 0:
        rc, stdout, _ = _run(["netstat", "-tlnup"])
    if rc != 0:
        return alerts

    # Match lines that contain a local address with a port number.
    port_re = re.compile(r"[:\s](\d+)\s")

    seen_ports: set[int] = set()
    for line in stdout.splitlines():
        for match in port_re.finditer(line):
            try:
                port = int(match.group(1))
            except ValueError:
                continue
            if port in SUSPICIOUS_PORTS and port not in seen_ports:
                seen_ports.add(port)
                alerts.append({
                    "port": port,
                    "raw_line": line.strip(),
                })

    return alerts


# ---------------------------------------------------------------------------
# Main monitoring loop
# ---------------------------------------------------------------------------

def run_monitor() -> None:
    write_log("INFO", "Decoy IDS starting", {"interval_seconds": CHECK_INTERVAL,
                                              "log_path": LOG_PATH})

    iteration = 0
    while True:
        iteration += 1
        write_log("INFO", f"Security check #{iteration} started")

        # --- Process check ---
        try:
            proc_alerts = check_processes()
            if proc_alerts:
                write_log(
                    "HIGH",
                    f"Suspicious process(es) detected ({len(proc_alerts)} match(es))",
                    {"alerts": proc_alerts},
                )
            else:
                write_log("INFO", "Process check: no suspicious processes found")
        except Exception as exc:
            write_log("ERROR", "Process check failed", {"error": str(exc)})

        # --- Crontab check ---
        try:
            cron_alerts = check_crontab()
            if cron_alerts:
                write_log(
                    "CRITICAL",
                    f"Suspicious crontab entry/entries detected ({len(cron_alerts)} match(es))",
                    {"alerts": cron_alerts},
                )
            else:
                write_log("INFO", "Crontab check: no suspicious entries found")
        except Exception as exc:
            write_log("ERROR", "Crontab check failed", {"error": str(exc)})

        # --- Network listener check ---
        try:
            net_alerts = check_network_listeners()
            if net_alerts:
                write_log(
                    "CRITICAL",
                    f"Suspicious listening port(s) detected ({len(net_alerts)} match(es))",
                    {"alerts": net_alerts},
                )
            else:
                write_log("INFO", "Network check: no suspicious listeners found")
        except Exception as exc:
            write_log("ERROR", "Network check failed", {"error": str(exc)})

        write_log("INFO", f"Security check #{iteration} complete — sleeping {CHECK_INTERVAL}s")
        time.sleep(CHECK_INTERVAL)


# ---------------------------------------------------------------------------
# Alarm mode  (called by ExecStopPost in the systemd unit)
# ---------------------------------------------------------------------------

def write_alarm() -> None:
    """
    Called when the systemd service is stopped or killed.
    Writes a timestamped alarm marker so the Blue Team controller can detect
    that the decoy was tampered with.
    """
    ts = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({
        "timestamp": ts,
        "event": "DECOY_IDS_KILLED",
        "message": (
            "The vm-security-monitor service was stopped or killed. "
            "Red Team may have silenced the decoy IDS."
        ),
    })

    # Ensure directory exists (hidden path to make it less obvious).
    alarm_dir = os.path.dirname(ALARM_PATH)
    try:
        os.makedirs(alarm_dir, exist_ok=True)
        with open(ALARM_PATH, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    except OSError as exc:
        print(f"[decoy_ids] ALARM: could not write alarm file: {exc}", file=sys.stderr)

    # Always log to the security log and stderr regardless.
    write_log("CRITICAL", "DECOY IDS KILLED — ALARM TRIGGERED", {
        "alarm_file": ALARM_PATH,
        "timestamp": ts,
    })
    print(f"[decoy_ids] ALARM written to {ALARM_PATH}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decoy IDS — runs as vm-security-monitor.service"
    )
    parser.add_argument(
        "--alarm",
        action="store_true",
        help="Alarm mode: write the kill-marker and exit (used by ExecStopPost).",
    )
    args = parser.parse_args()

    if args.alarm:
        write_alarm()
        sys.exit(0)
    else:
        try:
            run_monitor()
        except KeyboardInterrupt:
            write_log("INFO", "Decoy IDS stopped by keyboard interrupt")
            sys.exit(0)


if __name__ == "__main__":
    main()
