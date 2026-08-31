"""
OS Shield - System Security Report Generator
===============================================
Runs all security checks and generates a professional HTML report.

Nutzung:
  python report_generator.py
  python report_generator.py --output my_report.html
"""

import asyncio
import json
import hashlib
import os
import re
import subprocess
import sys
import platform
import socket
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_client, get_model

import psutil
from tools import (
    list_processes, list_network_connections, check_registry_autoruns,
    detect_parent_child_anomalies, detect_encoded_commands,
    detect_suspicious_paths, detect_lsass_access,
    detect_beaconing, detect_data_exfiltration,
    list_usb_devices,
)
from config import OPENAI_API_KEY


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>OS Shield - System Security Report</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Tahoma, sans-serif; color: #1a1a2e; line-height: 1.6; background: #fff; font-size: 14px; }}

  .cover {{
    min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center;
    background: linear-gradient(135deg, #0a0a0a, #1a1a2e, #0f3460); color: #fff; text-align: center;
    padding: 60px 40px; page-break-after: always;
  }}
  .cover h1 {{ font-size: 42px; font-weight: 300; letter-spacing: 3px; margin-bottom: 5px; }}
  .cover .subtitle {{ font-size: 18px; opacity: 0.7; margin-bottom: 40px; }}
  .cover .host-box {{
    background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px; padding: 25px 50px; margin: 20px 0;
  }}
  .cover .hostname {{ font-size: 28px; font-weight: 600; }}
  .cover .meta {{ margin-top: 40px; font-size: 14px; opacity: 0.6; }}
  .cover .meta div {{ margin: 4px 0; }}

  .score-section {{ text-align: center; padding: 40px; page-break-after: always; }}
  .score-section h2 {{ font-size: 28px; margin-bottom: 30px; }}
  .score-ring {{
    width: 200px; height: 200px; border-radius: 50%; display: inline-flex;
    align-items: center; justify-content: center; font-size: 56px; font-weight: 700;
    margin: 20px; border: 8px solid;
  }}
  .score-ring.critical {{ border-color: #e74c3c; color: #e74c3c; background: #fdf2f2; }}
  .score-ring.warning {{ border-color: #f39c12; color: #f39c12; background: #fef9e7; }}
  .score-ring.good {{ border-color: #27ae60; color: #27ae60; background: #eafaf1; }}
  .score-label {{ font-size: 16px; color: #666; margin-top: 10px; }}
  .score-breakdown {{ display: flex; justify-content: center; gap: 30px; margin-top: 30px; flex-wrap: wrap; }}
  .score-stat {{ text-align: center; padding: 15px 25px; border-radius: 8px; background: #f8f9fa; }}
  .score-stat .num {{ font-size: 32px; font-weight: 700; }}
  .score-stat .label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-critical .num {{ color: #e74c3c; }}
  .stat-high .num {{ color: #e67e22; }}
  .stat-medium .num {{ color: #f39c12; }}
  .stat-low .num {{ color: #3498db; }}

  .page {{ padding: 40px; page-break-after: always; }}
  .page h2 {{ font-size: 24px; color: #1a1a2e; border-bottom: 3px solid #0f3460; padding-bottom: 10px; margin-bottom: 25px; }}
  .page h3 {{ font-size: 18px; color: #0f3460; margin: 20px 0 10px; }}

  .issue {{
    border-left: 4px solid; padding: 15px 20px; margin: 15px 0;
    background: #f8f9fa; border-radius: 0 8px 8px 0;
  }}
  .issue.critical {{ border-color: #e74c3c; background: #fdf2f2; }}
  .issue.high {{ border-color: #e67e22; background: #fef5e7; }}
  .issue.medium {{ border-color: #f39c12; background: #fef9e7; }}
  .issue.low {{ border-color: #3498db; background: #eef6fb; }}
  .issue .issue-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .issue .issue-title {{ font-weight: 600; font-size: 16px; }}
  .severity-badge {{
    padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; color: #fff;
  }}
  .severity-badge.critical {{ background: #e74c3c; }}
  .severity-badge.high {{ background: #e67e22; }}
  .severity-badge.medium {{ background: #f39c12; }}
  .severity-badge.low {{ background: #3498db; }}
  .severity-badge.info {{ background: #95a5a6; }}
  .issue .description {{ color: #555; margin-bottom: 8px; }}
  .code {{ background: #1a1a2e; color: #7bed9f; padding: 10px 15px; border-radius: 6px; font-family: Consolas, monospace; font-size: 13px; overflow-x: auto; white-space: pre-wrap; margin: 5px 0; }}

  .info-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
  .info-table th, .info-table td {{ padding: 10px 15px; text-align: left; border-bottom: 1px solid #eee; }}
  .info-table th {{ background: #f8f9fa; font-weight: 600; color: #0f3460; width: 220px; }}
  .status-ok {{ color: #27ae60; }}
  .status-warn {{ color: #f39c12; }}
  .status-bad {{ color: #e74c3c; }}

  .process-table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
  .process-table th {{ background: #0f3460; color: #fff; padding: 8px 10px; text-align: left; }}
  .process-table td {{ padding: 6px 10px; border-bottom: 1px solid #eee; }}
  .process-table tr:nth-child(even) {{ background: #f8f9fa; }}
  .process-table .highlight {{ background: #fdf2f2 !important; font-weight: 600; }}

  .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; border-top: 1px solid #eee; margin-top: 40px; }}

  @media print {{ body {{ font-size: 12px; }} .cover {{ min-height: auto; padding: 40px; }} }}
</style>
</head>
<body>

<div class="cover">
  <h1>OS SHIELD</h1>
  <div class="subtitle">System Security Report</div>
  <div class="host-box">
    <div class="hostname">{hostname}</div>
    <div style="opacity:0.7; margin-top:8px;">{os_info}</div>
  </div>
  <div class="meta">
    <div>Datum: {date}</div>
    <div>User: {username}</div>
    <div>Analyst: OS Shield Autonomous Security Scanner</div>
    <div>Klassifikation: VERTRAULICH</div>
  </div>
</div>

<div class="score-section page">
  <h2>Threat Score</h2>
  <div class="score-ring {score_class}">{severity}</div>
  <div class="score-label">{score_label}</div>
  <div class="score-breakdown">
    <div class="score-stat stat-critical"><div class="num">{critical_count}</div><div class="label">Critical</div></div>
    <div class="score-stat stat-high"><div class="num">{high_count}</div><div class="label">High</div></div>
    <div class="score-stat stat-medium"><div class="num">{medium_count}</div><div class="label">Medium</div></div>
    <div class="score-stat stat-low"><div class="num">{low_count}</div><div class="label">Low</div></div>
  </div>
</div>

<div class="page">
  <h2>1. System-Informationen</h2>
  {system_info_html}
</div>

<div class="page">
  <h2>2. Sicherheitsbefunde</h2>
  {findings_html}
</div>

<div class="page">
  <h2>3. Auto-Investigation</h2>
  <p>Findings wurden automatisch weiter untersucht (Signaturen, Hashes, bekannte Programme):</p>
  {investigation_html}
</div>

<div class="page">
  <h2>4. Prozess-Analyse</h2>
  {process_html}
</div>

<div class="page">
  <h2>4. Netzwerk-Analyse</h2>
  {network_html}
</div>

<div class="page">
  <h2>6. Persistence-Analyse (Autoruns)</h2>
  {autoruns_html}
</div>

<div class="page">
  <h2>7. KI-gestuetzte Tiefenanalyse</h2>
  {llm_analysis_html}
</div>

<div class="page">
  <h2>8. Empfehlungen</h2>
  {recommendations_html}
</div>

<div class="footer">
  OS Shield System Security Report | {hostname} | {date} | VERTRAULICH<br>
  Generiert durch OS Shield (LLM-Driven Autonomous Security)
</div>
</body></html>"""


async def generate_report(output_path: str = None):
    hostname = socket.gethostname()
    username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
    os_info = f"{platform.system()} {platform.version()}"
    date = datetime.now().strftime("%d.%m.%Y %H:%M")

    print(f"\n  OS SHIELD REPORT GENERATOR")
    print(f"  Host: {hostname}")
    print(f"  OS: {os_info}\n")

    # Run all checks
    print("  [1/4] Running all security checks...", flush=True)

    (proc_result, net_result, autoruns_result,
     parent_child_result, encoded_result, paths_result,
     lsass_result, usb_result) = await asyncio.gather(
        list_processes(),
        list_network_connections(),
        check_registry_autoruns(),
        detect_parent_child_anomalies(),
        detect_encoded_commands(),
        detect_suspicious_paths(),
        detect_lsass_access(),
        list_usb_devices(),
    )

    print("  [1b/4] Running monitoring checks...", flush=True)
    beacon_result, exfil_result = await asyncio.gather(
        detect_beaconing(interval_seconds=5, duration_seconds=15),
        detect_data_exfiltration(),
    )

    print("  [2/4] Collecting findings...", flush=True)

    # Collect all issues
    all_issues = []

    # Parent-child anomalies
    for anomaly in parent_child_result.get("anomalies", []):
        all_issues.append({
            "severity": "CRITICAL",
            "category": "Process Chain",
            "title": f"{anomaly['parent_name']} spawned {anomaly['child_name']}",
            "description": anomaly["reason"],
            "detail": f"Parent PID: {anomaly['parent_pid']}, Child PID: {anomaly['child_pid']}, CMD: {anomaly.get('child_cmdline', '')[:150]}",
        })

    # Encoded commands
    for cmd in encoded_result.get("suspicious_commands", []):
        all_issues.append({
            "severity": "HIGH",
            "category": "Obfuscation",
            "title": f"Encoded/obfuscated command: {cmd['name']}",
            "description": "; ".join(cmd["findings"]),
            "detail": f"PID: {cmd['pid']}, CMD: {cmd.get('cmdline_preview', '')[:150]}",
        })

    # Suspicious paths
    for p in paths_result.get("suspicious_processes", []):
        all_issues.append({
            "severity": "MEDIUM",
            "category": "Suspicious Path",
            "title": f"{p['name']} running from {p['suspicious_path']}",
            "description": f"Binary at: {p['exe']}",
            "detail": f"PID: {p['pid']}, CMD: {p.get('cmdline', '')[:150]}",
        })

    # LSASS access
    for access in lsass_result.get("suspicious_access", []):
        all_issues.append({
            "severity": "CRITICAL",
            "category": "Credential Theft",
            "title": f"LSASS access: {access['name']}",
            "description": access["reason"],
            "detail": f"PID: {access['pid']}, EXE: {access.get('exe', '')}",
        })

    # Beaconing
    for beacon in beacon_result.get("potential_beacons", []):
        if beacon.get("remote_port") not in (443, 80, 993, 995):
            all_issues.append({
                "severity": "MEDIUM",
                "category": "Beaconing",
                "title": f"Persistent connection: {beacon['process']} -> {beacon['remote']}",
                "description": f"Connection to {beacon['remote_ip']}:{beacon['remote_port']} present in all snapshots",
                "detail": f"PID: {beacon['pid']}",
            })

    # Data exfiltration
    for transfer in exfil_result.get("large_transfers", []):
        all_issues.append({
            "severity": "HIGH",
            "category": "Data Transfer",
            "title": f"Large upload: {transfer['name']} ({transfer['sent_mb_5s']}MB in 5s)",
            "description": f"Sent {transfer['sent_mb_5s']}MB, Received {transfer['recv_mb_5s']}MB in 5 seconds",
            "detail": f"PID: {transfer['pid']}",
        })

    # Suspicious processes
    for p in proc_result.get("suspicious_processes", []):
        all_issues.append({
            "severity": "CRITICAL",
            "category": "Known Threat",
            "title": f"Suspicious process: {p['name']}",
            "description": f"Known attack tool detected",
            "detail": f"PID: {p['pid']}, EXE: {p.get('exe', '')}",
        })

    # Suspicious network connections
    for c in net_result.get("suspicious", []):
        all_issues.append({
            "severity": "HIGH",
            "category": "Network",
            "title": f"Suspicious port: {c.get('suspicious_reason', '')}",
            "description": f"Process: {c.get('process_name', '?')}, Remote: {c.get('remote_addr', '?')}",
            "detail": f"PID: {c.get('pid', '?')}",
        })

    # USB devices
    usb_storage = [d for d in usb_result.get("devices", []) if any(
        kw in (d.get("name") or "").lower() for kw in ["mass storage", "disk", "flash", "thumb"]
    )]
    if usb_storage:
        names = ", ".join(d.get("name", "?") for d in usb_storage[:3])
        all_issues.append({
            "severity": "LOW",
            "category": "USB",
            "title": f"USB storage: {names}",
            "description": f"{len(usb_storage)} USB storage device(s) connected",
            "detail": "",
        })

    # Sort by severity
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    all_issues.sort(key=lambda x: sev_order.get(x.get("severity", "INFO"), 5))

    # Count
    critical = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    high = sum(1 for i in all_issues if i["severity"] == "HIGH")
    medium = sum(1 for i in all_issues if i["severity"] == "MEDIUM")
    low = sum(1 for i in all_issues if i["severity"] == "LOW")

    if critical > 0:
        severity_label = "CRITICAL"
        score_class = "critical"
    elif high > 0:
        severity_label = "HIGH"
        score_class = "warning"
    elif medium > 0:
        severity_label = "MEDIUM"
        score_class = "warning"
    else:
        severity_label = "LOW"
        score_class = "good"

    print(f"  Initial issues: {len(all_issues)} (C:{critical} H:{high} M:{medium} L:{low})", flush=True)

    # =====================================================
    # AUTO-INVESTIGATION PASS
    # =====================================================
    print("  [2b/4] Auto-Investigation — following up on findings...", flush=True)

    investigations = []

    # --- 1. Investigate parent-child anomalies ---
    for anomaly in parent_child_result.get("anomalies", []):
        child_exe = anomaly.get("child_exe", "")
        child_pid = anomaly.get("child_pid")
        parent_name = anomaly.get("parent_name", "")
        child_name = anomaly.get("child_name", "")

        inv = {
            "finding": f"{parent_name} -> {child_name}",
            "checks": [],
            "verdict": "UNKNOWN",
        }

        # Check 1: Is the child binary signed?
        if child_exe and os.path.exists(child_exe):
            from tools import check_binary_signature
            sig = await check_binary_signature(child_exe)
            inv["checks"].append({
                "check": "Binary Signature",
                "result": f"Signed: {sig.get('is_signed')}, Valid: {sig.get('is_valid')}, Status: {sig.get('status', '?')}",
            })

        # Check 2: Hash the binary
        if child_exe and os.path.exists(child_exe):
            try:
                with open(child_exe, "rb") as f:
                    sha = hashlib.sha256(f.read()).hexdigest()
                inv["checks"].append({
                    "check": "SHA256 Hash",
                    "result": sha,
                })
            except Exception:
                pass

        # Check 3: What did the child process cmdline contain?
        cmdline = anomaly.get("child_cmdline", "")
        if cmdline:
            inv["checks"].append({
                "check": "Command Line",
                "result": cmdline[:300],
            })

        # Check 4: Is this a known legitimate pattern?
        known_legit = False
        if "chrome" in parent_name and "native" in cmdline.lower():
            known_legit = True
            inv["verdict"] = "LIKELY BENIGN — Chrome Native Messaging Host (used by Claude, password managers, etc.)"
        elif "chrome" in parent_name and "update" in cmdline.lower():
            known_legit = True
            inv["verdict"] = "LIKELY BENIGN — Chrome auto-updater"

        if not known_legit:
            inv["verdict"] = "REQUIRES MANUAL REVIEW — unusual parent-child chain"

        investigations.append(inv)
        print(f"    Investigated: {parent_name} -> {child_name} => {inv['verdict'][:60]}", flush=True)

    # --- 2. Investigate encoded commands: classify each ---
    KNOWN_LEGIT_ENCODED = {
        "claude.exe": "Claude Desktop — legitimate AI assistant",
        "claude-code.exe": "Claude Code — legitimate AI coding tool",
        "discord.exe": "Discord — legitimate chat app",
        "wsl.exe": "Windows Subsystem for Linux — legitimate",
        "code.exe": "VS Code — legitimate IDE",
        "docker.exe": "Docker — legitimate container runtime",
        "com.docker.backend.exe": "Docker Backend — legitimate",
        "msedgewebview2.exe": "Edge WebView — legitimate browser component",
        "teams.exe": "Microsoft Teams — legitimate",
        "slack.exe": "Slack — legitimate chat app",
    }

    encoded_investigations = []
    real_threats = []
    false_positives = []

    for cmd in encoded_result.get("suspicious_commands", []):
        name = (cmd.get("name") or "").lower()
        if name in KNOWN_LEGIT_ENCODED:
            false_positives.append({
                "process": cmd["name"],
                "reason": KNOWN_LEGIT_ENCODED[name],
            })
        else:
            real_threats.append(cmd)

    if false_positives:
        investigations.append({
            "finding": f"{len(false_positives)} encoded command(s) classified as false positives",
            "checks": [{"check": f"{fp['process']}", "result": fp["reason"]} for fp in false_positives],
            "verdict": f"FALSE POSITIVE — {len(false_positives)} processes are legitimate apps using standard flags",
        })
        print(f"    Encoded commands: {len(false_positives)} false positives, {len(real_threats)} need review", flush=True)

    if real_threats:
        for cmd in real_threats:
            inv = {
                "finding": f"Encoded command: {cmd['name']}",
                "checks": [
                    {"check": "Findings", "result": "; ".join(cmd["findings"])},
                    {"check": "Command", "result": cmd.get("cmdline_preview", "")[:200]},
                ],
                "verdict": "REQUIRES REVIEW — unrecognized process with encoded/obfuscated commands",
            }
            # Try to check signature
            if cmd.get("exe") and os.path.exists(cmd["exe"]):
                from tools import check_binary_signature
                sig = await check_binary_signature(cmd["exe"])
                inv["checks"].append({
                    "check": "Binary Signature",
                    "result": f"Signed: {sig.get('is_signed')}, Valid: {sig.get('is_valid')}",
                })
                if sig.get("is_signed") and sig.get("is_valid"):
                    inv["verdict"] = "LIKELY BENIGN — binary is properly signed"

            investigations.append(inv)

    # --- 3. Investigate suspicious paths ---
    for p in paths_result.get("suspicious_processes", []):
        exe = p.get("exe", "")
        name = (p.get("name") or "").lower()

        inv = {
            "finding": f"{p['name']} from {p['suspicious_path']}",
            "checks": [],
            "verdict": "UNKNOWN",
        }

        # Known legitimate processes in ProgramData
        if "programdata" in (p.get("suspicious_path") or "").lower():
            known_programdata = ["msmpeng", "sqlwriter", "mssql", "defender", "windows defender"]
            if any(kw in name for kw in known_programdata):
                inv["verdict"] = "FALSE POSITIVE — system service in ProgramData (normal)"
                inv["checks"].append({"check": "Classification", "result": "Known system service"})
            else:
                inv["verdict"] = "REQUIRES REVIEW — unknown binary in ProgramData"
        elif "downloads" in (p.get("suspicious_path") or "").lower():
            inv["verdict"] = "SUSPICIOUS — binary running directly from Downloads folder"
        elif "temp" in (p.get("suspicious_path") or "").lower():
            inv["verdict"] = "SUSPICIOUS — binary running from Temp (common malware behavior)"

        if exe and os.path.exists(exe):
            from tools import check_binary_signature
            sig = await check_binary_signature(exe)
            inv["checks"].append({
                "check": "Binary Signature",
                "result": f"Signed: {sig.get('is_signed')}, Valid: {sig.get('is_valid')}",
            })
            if sig.get("is_signed") and sig.get("is_valid"):
                if "SUSPICIOUS" in inv["verdict"]:
                    inv["verdict"] = inv["verdict"].replace("SUSPICIOUS", "LIKELY BENIGN (signed)")

        investigations.append(inv)

    # --- 4. Check USB authorization ---
    if usb_storage:
        inv = {
            "finding": "USB storage devices connected",
            "checks": [],
            "verdict": "INFO — USB storage present, verify authorization",
        }
        for d in usb_storage:
            inv["checks"].append({
                "check": d.get("name", "?"),
                "result": f"Device ID: {d.get('device_id', '?')[:60]}, Status: {d.get('status', '?')}",
            })
        investigations.append(inv)

    # --- Update issues with investigation results ---
    # Downgrade false positives
    for issue in all_issues[:]:
        for inv in investigations:
            if "FALSE POSITIVE" in inv.get("verdict", ""):
                # Check if this investigation matches this issue
                if inv["finding"] in issue.get("title", "") or inv["finding"] in issue.get("description", ""):
                    issue["severity"] = "INFO"
                    issue["title"] += " [FALSE POSITIVE]"
                    issue["description"] += f" — Investigation: {inv['verdict']}"

    # Re-classify encoded commands
    for issue in all_issues[:]:
        if issue["category"] == "Obfuscation":
            proc_name = issue.get("title", "").replace("Encoded/obfuscated command: ", "").lower()
            if proc_name in KNOWN_LEGIT_ENCODED:
                issue["severity"] = "INFO"
                issue["title"] += " [FALSE POSITIVE]"
                issue["description"] = KNOWN_LEGIT_ENCODED[proc_name]

    # Recount after investigation
    all_issues.sort(key=lambda x: sev_order.get(x.get("severity", "INFO"), 5))
    critical = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    high = sum(1 for i in all_issues if i["severity"] == "HIGH")
    medium = sum(1 for i in all_issues if i["severity"] == "MEDIUM")
    low = sum(1 for i in all_issues if i["severity"] == "LOW")
    info = sum(1 for i in all_issues if i["severity"] == "INFO")

    if critical > 0:
        severity_label = "CRITICAL"
        score_class = "critical"
    elif high > 0:
        severity_label = "HIGH"
        score_class = "warning"
    elif medium > 0:
        severity_label = "MEDIUM"
        score_class = "warning"
    else:
        severity_label = "LOW"
        score_class = "good"

    print(f"  After investigation: {len(all_issues)} issues (C:{critical} H:{high} M:{medium} L:{low} I:{info})", flush=True)
    print(f"  {len(investigations)} auto-investigations completed", flush=True)

    # Build HTML sections
    # System info
    mem = psutil.virtual_memory()
    cpu_count = psutil.cpu_count()
    boot = datetime.fromtimestamp(psutil.boot_time())
    system_info_html = f"""
    <table class="info-table">
      <tr><th>Hostname</th><td>{hostname}</td></tr>
      <tr><th>Betriebssystem</th><td>{os_info}</td></tr>
      <tr><th>Benutzer</th><td>{username}</td></tr>
      <tr><th>CPU Kerne</th><td>{cpu_count}</td></tr>
      <tr><th>RAM</th><td>{mem.total / (1024**3):.1f} GB ({mem.percent}% belegt)</td></tr>
      <tr><th>Boot-Zeit</th><td>{boot.strftime('%d.%m.%Y %H:%M')}</td></tr>
      <tr><th>Laufende Prozesse</th><td>{proc_result.get('total_processes', '?')}</td></tr>
      <tr><th>Aktive Netzwerk-Verbindungen</th><td>{net_result.get('total_connections', '?')} ({net_result.get('established_count', '?')} established)</td></tr>
      <tr><th>Autorun-Eintraege</th><td>{autoruns_result.get('total_entries', '?')}</td></tr>
      <tr><th>USB-Geraete</th><td>{usb_result.get('device_count', '?')}</td></tr>
    </table>"""

    # Findings
    findings_html = ""
    for issue in all_issues:
        cls = issue["severity"].lower()
        findings_html += f"""
        <div class="issue {cls}">
          <div class="issue-header">
            <span class="issue-title">{issue['title']}</span>
            <span class="severity-badge {cls}">{issue['severity']}</span>
          </div>
          <div class="description">{issue['description']}</div>
          {'<div class="code">' + issue["detail"] + '</div>' if issue.get("detail") else ''}
        </div>"""

    if not all_issues:
        findings_html = '<div class="issue low"><div class="issue-title">Keine Befunde</div><div class="description">Keine Sicherheitsprobleme erkannt.</div></div>'

    # Top processes
    procs = proc_result.get("processes", [])[:30]
    process_html = '<table class="process-table"><tr><th>PID</th><th>Name</th><th>User</th><th>EXE</th><th>Status</th></tr>'
    suspicious_pids = {p["pid"] for p in proc_result.get("suspicious_processes", [])}
    suspicious_pids.update(p["pid"] for p in paths_result.get("suspicious_processes", []))
    for p in procs:
        cls = ' class="highlight"' if p["pid"] in suspicious_pids else ""
        exe = (p.get("exe") or "-")[:60]
        process_html += f'<tr{cls}><td>{p["pid"]}</td><td>{p["name"]}</td><td>{(p.get("username") or "-")[:20]}</td><td>{exe}</td><td>{p.get("status", "-")}</td></tr>'
    process_html += "</table>"

    # Network
    conns = net_result.get("connections", [])[:30]
    network_html = '<table class="process-table"><tr><th>PID</th><th>Process</th><th>Local</th><th>Remote</th><th>Status</th></tr>'
    for c in conns:
        network_html += f'<tr><td>{c.get("pid", "-")}</td><td>{c.get("process_name", "-")}</td><td>{c.get("local_addr", "-")}</td><td>{c.get("remote_addr", "-") or "-"}</td><td>{c.get("status", "-")}</td></tr>'
    network_html += "</table>"

    # Autoruns
    entries = autoruns_result.get("autorun_entries", [])
    autoruns_html = '<table class="process-table"><tr><th>Hive</th><th>Name</th><th>Wert</th></tr>'
    for e in entries:
        val = (e.get("value_data") or "")[:80]
        autoruns_html += f'<tr><td>{e.get("hive", "-")}</td><td>{e.get("value_name", "-")}</td><td>{val}</td></tr>'
    autoruns_html += "</table>"

    # Investigation HTML
    investigation_html = ""
    for inv in investigations:
        verdict = inv.get("verdict", "UNKNOWN")
        if "FALSE POSITIVE" in verdict:
            cls = "low"
        elif "BENIGN" in verdict:
            cls = "low"
        elif "SUSPICIOUS" in verdict or "REVIEW" in verdict:
            cls = "high"
        else:
            cls = "medium"

        checks_html = ""
        for chk in inv.get("checks", []):
            checks_html += f'<tr><td><strong>{chk["check"]}</strong></td><td>{chk["result"]}</td></tr>'

        investigation_html += f"""
        <div class="issue {cls}" style="margin-bottom:15px;">
          <div class="issue-header">
            <span class="issue-title">{inv['finding']}</span>
          </div>
          <table class="info-table" style="margin:10px 0;">
            {checks_html}
          </table>
          <div class="code">{verdict}</div>
        </div>"""

    if not investigations:
        investigation_html = "<p>Keine Findings erforderten weitere Untersuchung.</p>"

    # LLM Analysis
    print("  [3/4] LLM Tiefenanalyse...", flush=True)
    llm_client = get_client("report")

    all_data = {
        "issues": all_issues,
        "parent_child": parent_child_result.get("anomalies", []),
        "encoded_commands": len(encoded_result.get("suspicious_commands", [])),
        "suspicious_paths": len(paths_result.get("suspicious_processes", [])),
        "beacons": len(beacon_result.get("potential_beacons", [])),
        "large_transfers": exfil_result.get("large_transfers", []),
        "usb_storage": len(usb_storage),
        "process_count": proc_result.get("total_processes", 0),
        "connection_count": net_result.get("total_connections", 0),
    }

    llm_resp = await llm_client.chat.completions.create(
        model=get_model("report"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein Senior Security Analyst. Analysiere die Scan-Ergebnisse eines Windows-Systems.\n"
                    "Schreibe auf Deutsch. Formatiere in HTML (<p>, <ul>, <li>, <strong>, <h3>).\n\n"
                    "Erstelle:\n"
                    "1. Zusammenfassung (3-4 Saetze)\n"
                    "2. Detaillierte Analyse jedes Findings (ist es ein echtes Risiko oder False Positive?)\n"
                    "3. Priorisierte Empfehlungen\n\n"
                    "Sei ehrlich: Viele Findings koennten False Positives sein (z.B. Claude, Discord, VS Code). "
                    "Erklaere welche echt gefaehrlich sind und welche harmlos."
                ),
            },
            {"role": "user", "content": f"System: {hostname} ({os_info})\n\nScan-Ergebnisse:\n{json.dumps(all_data, indent=2, default=str)}"},
        ],
    )
    llm_text = llm_resp.choices[0].message.content.strip()

    # Split LLM text into analysis and recommendations
    llm_analysis_html = llm_text
    recommendations_html = ""
    if "Empfehlung" in llm_text:
        parts = llm_text.split("Empfehlung", 1)
        llm_analysis_html = parts[0]
        recommendations_html = "<h3>Empfehlung" + parts[1]

    if not recommendations_html:
        recommendations_html = "<p>Siehe Tiefenanalyse fuer Details.</p>"

    # Generate HTML
    print("  [4/4] Generating report...", flush=True)
    html = REPORT_TEMPLATE.format(
        hostname=hostname,
        os_info=os_info,
        date=date,
        username=username,
        severity=severity_label,
        score_class=score_class,
        score_label=f"{len(all_issues)} Findings",
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        system_info_html=system_info_html,
        findings_html=findings_html,
        investigation_html=investigation_html,
        process_html=process_html,
        network_html=network_html,
        autoruns_html=autoruns_html,
        llm_analysis_html=llm_analysis_html,
        recommendations_html=recommendations_html,
    )

    if not output_path:
        output_path = f"os_shield_report_{hostname}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  Report gespeichert: {output_path}")
    print(f"  Oeffne im Browser: Ctrl+P -> PDF\n")
    return output_path


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="OS Shield Report Generator")
    parser.add_argument("--output", "-o", help="Output HTML file")
    args = parser.parse_args()

    await generate_report(output_path=args.output)


if __name__ == "__main__":
    asyncio.run(main())
