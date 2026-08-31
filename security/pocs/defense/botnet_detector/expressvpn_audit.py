"""
ExpressVPN Deep Audit
=======================
Focused analysis of what ExpressVPN is actually doing on this system:
1. All ExpressVPN processes + their resource usage
2. All network connections originating from ExpressVPN processes
3. DNS behavior — is ExpressVPN hijacking DNS?
4. File system footprint — what files does it install/modify?
5. Registry entries — persistence, config, certificates
6. Traffic analysis — what IPs is it talking to and how much data?
7. TUN/TAP adapter analysis
8. IP leak test — is VPN actually working?
"""

import asyncio
import json
import os
import platform
import re
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


class ExpressVPNAudit:

    def __init__(self):
        self.findings = []
        self.risk_score = 0

    def _add_finding(self, category, severity, detail, verdict=""):
        self.findings.append({
            "category": category,
            "severity": severity,
            "detail": detail,
            "verdict": verdict,
        })
        if severity == "CRITICAL":
            self.risk_score += 25
        elif severity == "HIGH":
            self.risk_score += 15
        elif severity == "MEDIUM":
            self.risk_score += 5

    async def audit_processes(self) -> dict:
        """Find ALL ExpressVPN-related processes and their resource usage."""
        print("  [EVPN] Scanning processes...", flush=True)
        result = {"processes": [], "total_cpu": 0, "total_memory_mb": 0}

        try:
            # Get all processes with full details
            output = subprocess.check_output(
                ["wmic", "process", "get",
                 "ProcessId,Name,ExecutablePath,CommandLine,WorkingSetSize,ThreadCount,HandleCount",
                 "/format:csv"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) < 6:
                    continue

                name = parts[3] if len(parts) > 3 else ""
                path = parts[2] if len(parts) > 2 else ""
                cmd = parts[1] if len(parts) > 1 else ""
                pid = parts[4] if len(parts) > 4 else ""

                combined = f"{name} {path} {cmd}".lower()
                if any(kw in combined for kw in ("expressvpn", "express vpn", "xvpn", "lightway")):
                    mem_bytes = int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else 0
                    threads = int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0
                    handles = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0

                    proc = {
                        "pid": pid,
                        "name": name,
                        "path": path,
                        "cmdline": cmd[:200],
                        "memory_mb": round(mem_bytes / 1024 / 1024, 1),
                        "threads": threads,
                        "handles": handles,
                    }
                    result["processes"].append(proc)
                    result["total_memory_mb"] += proc["memory_mb"]

        except Exception as e:
            result["error"] = str(e)

        # Get CPU per process
        try:
            output = subprocess.check_output(
                ["wmic", "path", "Win32_PerfFormattedData_PerfProc_Process",
                 "get", "Name,PercentProcessorTime,IDProcess", "/format:csv"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 4 and parts[3].isdigit():
                    cpu = int(parts[3])
                    name = parts[2].lower()
                    pid = parts[1]
                    if any(kw in name for kw in ("expressvpn", "xvpn", "lightway")):
                        for proc in result["processes"]:
                            if proc["pid"] == pid or proc["name"].lower().startswith(name[:10]):
                                proc["cpu_percent"] = cpu
                                result["total_cpu"] += cpu
        except Exception:
            pass

        n = len(result["processes"])
        self._add_finding("Processes", "INFO" if n <= 3 else "MEDIUM",
            f"{n} ExpressVPN processes, {result['total_cpu']}% total CPU, {result['total_memory_mb']:.0f} MB RAM",
            f"{'Normal' if n <= 3 and result['total_cpu'] < 50 else 'High resource usage'}")

        if result["total_cpu"] > 80:
            self._add_finding("CPU Usage", "HIGH",
                f"ExpressVPN consuming {result['total_cpu']}% CPU",
                "This is excessive for a VPN. Possible: crypto mining, traffic proxying, or software bug")

        print(f"  [EVPN] Found {n} processes, {result['total_cpu']}% CPU, {result['total_memory_mb']:.0f} MB", flush=True)
        return result

    async def audit_connections(self) -> dict:
        """Map ALL network connections from ExpressVPN processes."""
        print("  [EVPN] Mapping ExpressVPN connections...", flush=True)
        result = {"connections": [], "unique_destinations": set(), "by_port": Counter(), "by_country": []}

        # Get ExpressVPN PIDs
        evpn_pids = set()
        try:
            output = subprocess.check_output(
                ["wmic", "process", "where",
                 "Name like '%ExpressVPN%' or Name like '%xvpn%' or Name like '%Lightway%'",
                 "get", "ProcessId", "/format:csv"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 2 and parts[1].isdigit():
                    evpn_pids.add(parts[1])
        except Exception:
            pass

        # Get all connections with PIDs
        try:
            output = subprocess.check_output(
                ["netstat", "-n", "-o", "-p", "TCP"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" and ":" in parts[2]:
                    pid = parts[4]
                    foreign = parts[2]
                    state = parts[3]

                    try:
                        addr, port = foreign.rsplit(":", 1)
                        port = int(port)
                    except ValueError:
                        continue

                    if addr in ("0.0.0.0", "127.0.0.1", "*"):
                        continue

                    if pid in evpn_pids:
                        conn = {
                            "remote_addr": addr,
                            "remote_port": port,
                            "state": state,
                            "pid": pid,
                        }
                        result["connections"].append(conn)
                        result["unique_destinations"].add(addr)
                        result["by_port"][port] += 1

        except Exception:
            pass

        result["unique_destinations"] = list(result["unique_destinations"])
        result["by_port"] = dict(result["by_port"])

        n_conn = len(result["connections"])
        n_dest = len(result["unique_destinations"])

        if n_conn > 0:
            self._add_finding("VPN Connections", "INFO" if n_dest <= 5 else "MEDIUM",
                f"{n_conn} connections to {n_dest} unique IPs",
                f"{'Normal - VPN tunnel endpoints' if n_dest <= 5 else 'Many destinations - investigate'}")

            # Check for non-standard ports
            standard = {443, 1195, 1194, 500, 4500, 51820}  # HTTPS, OpenVPN, IPSec, WireGuard
            unusual_ports = {p: c for p, c in result["by_port"].items() if p not in standard}
            if unusual_ports:
                self._add_finding("Unusual Ports", "MEDIUM",
                    f"ExpressVPN using non-standard ports: {unusual_ports}",
                    "VPN should only use standard VPN/HTTPS ports")

        print(f"  [EVPN] {n_conn} connections to {n_dest} destinations", flush=True)
        return result

    async def audit_dns(self) -> dict:
        """Check if ExpressVPN is hijacking DNS."""
        print("  [EVPN] Checking DNS behavior...", flush=True)
        result = {"dns_servers": [], "dns_hijacked": False, "leak_test": {}}

        import urllib.request

        # Get current DNS servers
        try:
            output = subprocess.check_output(
                ["ipconfig", "/all"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            capture_next = False
            for line in output.split("\n"):
                if "DNS" in line and "Server" in line or "DNS" in line and "server" in line:
                    capture_next = True
                    parts = line.split(":")
                    if len(parts) >= 2:
                        addr = parts[-1].strip()
                        if re.match(r'\d+\.\d+\.\d+\.\d+', addr):
                            result["dns_servers"].append(addr)
                elif capture_next and re.match(r'\s+\d+\.\d+\.\d+\.\d+', line.strip()):
                    result["dns_servers"].append(line.strip())
                else:
                    capture_next = False
        except Exception:
            pass

        # DNS leak test — resolve a unique domain and check which DNS server handles it
        try:
            # Use a DNS leak test API
            resp = urllib.request.urlopen("https://ipleak.net/json/", timeout=10)
            data = json.loads(resp.read().decode())
            result["leak_test"] = {
                "public_ip": data.get("ip", "?"),
                "country": data.get("country_name", "?"),
                "city": data.get("city_name", "?"),
                "isp": data.get("isp_name", "?"),
            }

            isp = data.get("isp_name", "").lower()
            country = data.get("country_name", "")

            if any(kw in isp for kw in ("telekom", "vodafone", "o2", "1&1", "unitymedia", "kabel")):
                self._add_finding("IP Leak", "CRITICAL",
                    f"Your REAL ISP IP is exposed: {data.get('ip')} ({isp}, {country})",
                    "VPN is NOT hiding your IP! Your traffic may be unprotected")
                result["dns_hijacked"] = False  # Worse — VPN not working at all
            elif any(kw in isp for kw in ("express", "vpn", "kape", "stackpath")):
                self._add_finding("IP Protected", "INFO",
                    f"IP belongs to VPN provider: {data.get('ip')} ({isp}, {country})",
                    "VPN is working correctly — your real IP is hidden")
            else:
                self._add_finding("IP Unknown", "MEDIUM",
                    f"IP belongs to: {data.get('ip')} ({isp}, {country})",
                    "Verify this is your VPN provider's infrastructure")

        except Exception as e:
            result["leak_test"]["error"] = str(e)

        self._add_finding("DNS Servers", "INFO",
            f"Active DNS servers: {result['dns_servers']}",
            "Should be VPN provider's DNS, not your ISP's")

        print(f"  [EVPN] DNS servers: {result['dns_servers']}, IP: {result['leak_test'].get('public_ip', '?')}", flush=True)
        return result

    async def audit_filesystem(self) -> dict:
        """Check ExpressVPN's file system footprint."""
        print("  [EVPN] Scanning filesystem...", flush=True)
        result = {"install_dirs": [], "total_size_mb": 0, "suspicious_files": [], "log_files": [], "cert_files": []}

        search_paths = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "ExpressVPN",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "ExpressVPN",
            Path(os.environ.get("LOCALAPPDATA", "")) / "ExpressVPN",
            Path(os.environ.get("APPDATA", "")) / "ExpressVPN",
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "ExpressVPN",
        ]

        for sp in search_paths:
            if sp.exists():
                result["install_dirs"].append(str(sp))
                try:
                    for f in sp.rglob("*"):
                        if f.is_file():
                            size = f.stat().st_size
                            result["total_size_mb"] += size / 1024 / 1024

                            ext = f.suffix.lower()
                            name = f.name.lower()

                            # Categorize files
                            if ext in (".log", ".txt") and size > 0:
                                result["log_files"].append({
                                    "path": str(f),
                                    "size_kb": round(size / 1024, 1),
                                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()[:19],
                                })
                            elif ext in (".pem", ".crt", ".cer", ".key", ".p12"):
                                result["cert_files"].append({
                                    "path": str(f),
                                    "size_kb": round(size / 1024, 1),
                                })
                            elif ext in (".exe", ".dll") and "express" not in name and "lightway" not in name:
                                result["suspicious_files"].append({
                                    "path": str(f),
                                    "size_kb": round(size / 1024, 1),
                                    "reason": "unexpected executable in VPN directory",
                                })
                            elif ext in (".dat", ".db", ".sqlite") and size > 1024 * 1024:
                                result["suspicious_files"].append({
                                    "path": str(f),
                                    "size_kb": round(size / 1024, 1),
                                    "reason": f"large data file ({size / 1024 / 1024:.1f} MB)",
                                })
                except PermissionError:
                    pass

        result["total_size_mb"] = round(result["total_size_mb"], 1)

        if result["suspicious_files"]:
            self._add_finding("Suspicious Files", "MEDIUM",
                f"{len(result['suspicious_files'])} unexpected files in VPN directory",
                "Check these files manually")

        self._add_finding("Install Footprint", "INFO",
            f"{len(result['install_dirs'])} dirs, {result['total_size_mb']} MB total, "
            f"{len(result['log_files'])} logs, {len(result['cert_files'])} certs",
            "Normal VPN installation")

        print(f"  [EVPN] {len(result['install_dirs'])} dirs, {result['total_size_mb']} MB", flush=True)
        return result

    async def audit_registry(self) -> dict:
        """Check ExpressVPN registry entries."""
        print("  [EVPN] Checking registry...", flush=True)
        result = {"autorun_entries": [], "services": [], "drivers": [], "certificates": []}

        # Check autorun
        reg_keys = [
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        ]
        for key in reg_keys:
            try:
                output = subprocess.check_output(
                    ["reg", "query", key], timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                for line in output.split("\n"):
                    if "express" in line.lower() or "vpn" in line.lower():
                        result["autorun_entries"].append(line.strip())
            except Exception:
                pass

        # Check services
        try:
            output = subprocess.check_output(
                ["sc", "query", "type=", "service", "state=", "all"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            current_service = None
            for line in output.split("\n"):
                if "SERVICE_NAME" in line:
                    current_service = line.split(":")[-1].strip()
                elif current_service and any(kw in current_service.lower() for kw in ("express", "vpn", "lightway", "xvpn")):
                    if "STATE" in line:
                        state = line.split(":")[-1].strip() if ":" in line else line.strip()
                        result["services"].append({"name": current_service, "state": state})
                        current_service = None
        except Exception:
            pass

        # Check network drivers (TAP/TUN)
        try:
            output = subprocess.check_output(
                ["driverquery", "/v", "/fo", "csv"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                lower = line.lower()
                if any(kw in lower for kw in ("tap", "tun", "express", "lightway", "wintun")):
                    parts = line.strip().split(",")
                    if len(parts) >= 3:
                        result["drivers"].append({
                            "name": parts[0].strip('"'),
                            "display": parts[1].strip('"') if len(parts) > 1 else "",
                            "state": parts[3].strip('"') if len(parts) > 3 else "",
                        })
        except Exception:
            pass

        self._add_finding("Services", "INFO",
            f"{len(result['services'])} VPN services, {len(result['drivers'])} network drivers, {len(result['autorun_entries'])} autoruns",
            "Normal VPN installation")

        print(f"  [EVPN] {len(result['services'])} services, {len(result['drivers'])} drivers", flush=True)
        return result

    async def audit_traffic_volume(self, duration: int = 15) -> dict:
        """Measure actual traffic volume over time."""
        print(f"  [EVPN] Measuring traffic for {duration}s...", flush=True)
        result = {"samples": [], "total_sent": 0, "total_recv": 0, "rate_kbps_sent": 0, "rate_kbps_recv": 0}

        def _get_bytes():
            try:
                output = subprocess.check_output(
                    ["netstat", "-e"], timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                for line in output.split("\n"):
                    if "Bytes" in line or "Byte" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            return int(parts[1]), int(parts[2])
            except Exception:
                pass
            return 0, 0

        # Take samples
        start_recv, start_sent = _get_bytes()
        start_time = time.time()

        for i in range(duration // 3):
            await asyncio.sleep(3)
            recv, sent = _get_bytes()
            elapsed = time.time() - start_time
            result["samples"].append({
                "time": round(elapsed, 1),
                "recv_total": recv,
                "sent_total": sent,
                "recv_delta": recv - start_recv,
                "sent_delta": sent - start_sent,
            })

        end_recv, end_sent = _get_bytes()
        total_time = time.time() - start_time

        result["total_recv"] = end_recv - start_recv
        result["total_sent"] = end_sent - start_sent
        result["rate_kbps_recv"] = round((result["total_recv"] / 1024) / total_time, 1) if total_time > 0 else 0
        result["rate_kbps_sent"] = round((result["total_sent"] / 1024) / total_time, 1) if total_time > 0 else 0

        # Check send/receive ratio
        if result["total_recv"] > 0:
            ratio = result["total_sent"] / result["total_recv"]
            if ratio > 1.5:
                self._add_finding("Upload Anomaly", "HIGH",
                    f"Sending {ratio:.1f}x more than receiving ({result['rate_kbps_sent']} KB/s up vs {result['rate_kbps_recv']} KB/s down)",
                    "Unusual for browsing. VPN may be proxying traffic or exfiltrating data")
            elif ratio > 0.5:
                self._add_finding("Traffic Ratio", "MEDIUM",
                    f"Send/Recv ratio: {ratio:.2f} ({result['rate_kbps_sent']} KB/s up, {result['rate_kbps_recv']} KB/s down)",
                    "Slightly high upload — could be video calls, uploads, or VPN overhead")
            else:
                self._add_finding("Traffic Ratio", "INFO",
                    f"Send/Recv ratio: {ratio:.2f} ({result['rate_kbps_sent']} KB/s up, {result['rate_kbps_recv']} KB/s down)",
                    "Normal browsing pattern")

        print(f"  [EVPN] Traffic: {result['rate_kbps_sent']} KB/s up, {result['rate_kbps_recv']} KB/s down", flush=True)
        return result

    async def run_full_audit(self) -> dict:
        """Run complete ExpressVPN audit."""
        print("\n  [EVPN] ========================================", flush=True)
        print("  [EVPN]   ExpressVPN Deep Audit", flush=True)
        print("  [EVPN] ========================================\n", flush=True)

        procs = await self.audit_processes()
        conns = await self.audit_connections()
        dns = await self.audit_dns()
        files = await self.audit_filesystem()
        registry = await self.audit_registry()
        traffic = await self.audit_traffic_volume(15)

        # Overall verdict
        score = self.risk_score
        if score < 15:
            verdict = "CLEAN - ExpressVPN behaves normally"
        elif score < 40:
            verdict = "MINOR CONCERNS - Some anomalies, likely benign"
        elif score < 70:
            verdict = "SUSPICIOUS - ExpressVPN shows unusual behavior"
        else:
            verdict = "HIGH RISK - ExpressVPN may be doing more than VPN"

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": platform.node(),
            "verdict": verdict,
            "risk_score": score,
            "processes": procs,
            "connections": conns,
            "dns": dns,
            "filesystem": files,
            "registry": registry,
            "traffic": traffic,
            "findings": self.findings,
        }

        print(f"\n  [EVPN] === VERDICT: {verdict} (score {score}) ===", flush=True)
        return result


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    async def main():
        auditor = ExpressVPNAudit()
        result = await auditor.run_full_audit()

        print(f"\n{'='*60}")
        print(f"  EXPRESSVPN DEEP AUDIT")
        print(f"  Host: {result['hostname']}")
        print(f"  Score: {result['risk_score']}")
        print(f"  Verdict: {result['verdict']}")
        print(f"{'='*60}")

        for f in result["findings"]:
            sev = f["severity"]
            marker = {"INFO": "  ", "MEDIUM": "! ", "HIGH": "!!", "CRITICAL": "!!!"}.get(sev, "  ")
            print(f"  {marker} [{sev:8s}] {f['category']:25s}")
            print(f"     {f['detail'][:80]}")
            if f.get("verdict"):
                print(f"     -> {f['verdict']}")
            print()

        # Show ExpressVPN processes
        procs = result["processes"]["processes"]
        if procs:
            print(f"  --- ExpressVPN Processes ({len(procs)}) ---")
            for p in procs:
                cpu = p.get("cpu_percent", "?")
                print(f"    PID {p['pid']:6s} | {p['name']:40s} | CPU: {cpu}% | RAM: {p['memory_mb']} MB | Threads: {p['threads']}")

        # Show connections
        conns = result["connections"]["connections"]
        if conns:
            print(f"\n  --- ExpressVPN Connections ({len(conns)}) ---")
            seen = set()
            for c in conns:
                key = f"{c['remote_addr']}:{c['remote_port']}"
                if key not in seen:
                    seen.add(key)
                    print(f"    {c['remote_addr']:20s}:{c['remote_port']:<6d} {c['state']}")

        # IP leak result
        leak = result["dns"]["leak_test"]
        if leak:
            print(f"\n  --- IP Leak Test ---")
            print(f"    Public IP: {leak.get('public_ip', '?')}")
            print(f"    ISP:       {leak.get('isp', '?')}")
            print(f"    Location:  {leak.get('city', '?')}, {leak.get('country', '?')}")

    asyncio.run(main())
