"""
VPN Botnet Probe
==================
Determines if a VPN application is secretly using your machine as part
of a botnet, residential proxy network, or crypto mining operation.

Tests:
1. IDLE TRAFFIC: Measure traffic when user is doing NOTHING
2. GHOST CONNECTIONS: Find connections that don't belong to the VPN tunnel
3. SHADOW PROCESSES: Detect child processes spawned by the VPN
4. DNS EXFIL: Check if VPN makes suspicious DNS queries
5. CPU PARASITE: Measure CPU with/without active browsing
6. BANDWIDTH THEFT: Detect if VPN is proxying third-party traffic through you
7. KAPE/CROSSRIDER CHECK: Look for known Kape Technologies indicators

Background: ExpressVPN is owned by Kape Technologies (formerly Crossrider),
a company with documented history in adware distribution. This probe checks
if the VPN software is doing more than just tunneling YOUR traffic.
"""

import asyncio
import json
import os
import platform
import re
import socket
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


class VPNBotnetProbe:

    def __init__(self):
        self.findings = []
        self.evidence = []

    def _finding(self, category, severity, detail, verdict="", evidence=None):
        self.findings.append({
            "category": category, "severity": severity,
            "detail": detail, "verdict": verdict,
        })
        if evidence:
            self.evidence.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "data": evidence,
            })

    # ================================================================
    # TEST 1: IDLE TRAFFIC — What happens when you do NOTHING?
    # ================================================================

    async def test_idle_traffic(self, idle_seconds: int = 30) -> dict:
        """
        Close all browsers, stop all downloads, then measure:
        - How much data is still being sent/received?
        - Which processes are responsible?
        """
        print(f"\n  [PROBE] TEST 1: IDLE TRAFFIC ({idle_seconds}s)", flush=True)
        print(f"  [PROBE] Measuring baseline traffic...", flush=True)

        result = {"samples": [], "total_sent": 0, "total_recv": 0}

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

        start_recv, start_sent = _get_bytes()
        start_time = time.time()

        # Sample every 5 seconds
        for i in range(idle_seconds // 5):
            await asyncio.sleep(5)
            recv, sent = _get_bytes()
            elapsed = time.time() - start_time
            delta_recv = recv - start_recv
            delta_sent = sent - start_sent
            rate_up = delta_sent / elapsed / 1024 if elapsed > 0 else 0
            rate_down = delta_recv / elapsed / 1024 if elapsed > 0 else 0
            result["samples"].append({
                "time_s": round(elapsed, 1),
                "sent_kb": round(delta_sent / 1024, 1),
                "recv_kb": round(delta_recv / 1024, 1),
                "rate_up_kbps": round(rate_up, 1),
                "rate_down_kbps": round(rate_down, 1),
            })
            print(f"  [PROBE]   {elapsed:.0f}s: UP {rate_up:.1f} KB/s | DOWN {rate_down:.1f} KB/s", flush=True)

        end_recv, end_sent = _get_bytes()
        total_time = time.time() - start_time
        result["total_sent"] = end_sent - start_sent
        result["total_recv"] = end_recv - start_recv
        result["avg_up_kbps"] = round(result["total_sent"] / 1024 / total_time, 1)
        result["avg_down_kbps"] = round(result["total_recv"] / 1024 / total_time, 1)

        # Verdict
        if result["avg_up_kbps"] > 50:
            self._finding("Idle Upload", "CRITICAL",
                f"Sending {result['avg_up_kbps']} KB/s while idle — {result['total_sent'] / 1024:.0f} KB in {total_time:.0f}s",
                "Your machine is sending significant data when you're not doing anything. "
                "This could indicate: residential proxy, data exfiltration, or P2P relay.",
                evidence=result)
        elif result["avg_up_kbps"] > 10:
            self._finding("Idle Upload", "HIGH",
                f"Sending {result['avg_up_kbps']} KB/s while idle",
                "Moderate idle upload. Could be background sync, telemetry, or suspicious activity.")
        elif result["avg_up_kbps"] > 2:
            self._finding("Idle Upload", "MEDIUM",
                f"Sending {result['avg_up_kbps']} KB/s while idle",
                "Low idle upload — likely OS telemetry, NTP, or VPN keepalives.")
        else:
            self._finding("Idle Upload", "INFO",
                f"Sending {result['avg_up_kbps']} KB/s while idle",
                "Minimal idle traffic — normal.")

        return result

    # ================================================================
    # TEST 2: GHOST CONNECTIONS — Connections NOT part of the VPN tunnel
    # ================================================================

    async def test_ghost_connections(self) -> dict:
        """
        Find connections from ExpressVPN processes that go to IPs
        OTHER than the VPN tunnel server.
        """
        print(f"\n  [PROBE] TEST 2: GHOST CONNECTIONS", flush=True)
        result = {"vpn_pids": [], "tunnel_ip": None, "ghost_connections": [], "total_vpn_connections": 0}

        # Step 1: Find ExpressVPN PIDs
        try:
            output = subprocess.check_output(
                ["tasklist", "/fi", "IMAGENAME eq ExpressVPN*", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    pid = parts[1].strip('"')
                    if pid.isdigit():
                        result["vpn_pids"].append(pid)
        except Exception:
            pass

        # Also check for Lightway (ExpressVPN's protocol)
        try:
            output = subprocess.check_output(
                ["tasklist", "/fi", "IMAGENAME eq Lightway*", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    pid = parts[1].strip('"')
                    if pid.isdigit():
                        result["vpn_pids"].append(pid)
        except Exception:
            pass

        print(f"  [PROBE] ExpressVPN PIDs: {result['vpn_pids']}", flush=True)

        # Step 2: Get ALL connections from those PIDs
        try:
            output = subprocess.check_output(
                ["netstat", "-n", "-o"], timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            vpn_connections = []
            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and parts[-1] in result["vpn_pids"]:
                    if ":" in parts[2]:
                        try:
                            addr, port = parts[2].rsplit(":", 1)
                            if addr not in ("0.0.0.0", "127.0.0.1", "*"):
                                vpn_connections.append({
                                    "addr": addr, "port": int(port),
                                    "state": parts[3], "pid": parts[-1],
                                })
                        except ValueError:
                            pass

            result["total_vpn_connections"] = len(vpn_connections)

            # Step 3: Identify the VPN tunnel (usually the connection on VPN ports)
            vpn_ports = {443, 1194, 1195, 4500, 500, 51820, 4433}
            tunnel_candidates = [c for c in vpn_connections if c["port"] in vpn_ports]
            if tunnel_candidates:
                result["tunnel_ip"] = tunnel_candidates[0]["addr"]

            # Step 4: Find GHOST connections (not to tunnel IP, not to localhost)
            tunnel_ip = result["tunnel_ip"]
            for conn in vpn_connections:
                if conn["addr"] != tunnel_ip and conn["addr"] not in ("127.0.0.1", "0.0.0.0"):
                    result["ghost_connections"].append(conn)

        except Exception as e:
            result["error"] = str(e)

        n_ghosts = len(result["ghost_connections"])
        if n_ghosts > 0:
            ghost_ips = set(c["addr"] for c in result["ghost_connections"])
            self._finding("Ghost Connections", "HIGH" if n_ghosts > 3 else "MEDIUM",
                f"{n_ghosts} connections from ExpressVPN to non-tunnel IPs: {list(ghost_ips)[:5]}",
                "VPN processes should ONLY connect to the tunnel server. "
                "Extra connections may indicate: telemetry, analytics, or residential proxy relay.",
                evidence=result["ghost_connections"])
        else:
            self._finding("Ghost Connections", "INFO",
                f"All {result['total_vpn_connections']} VPN connections go to tunnel IP {result['tunnel_ip']}",
                "Clean — no unexpected connections from VPN processes.")

        print(f"  [PROBE] Tunnel: {result['tunnel_ip']}, Ghosts: {n_ghosts}", flush=True)
        return result

    # ================================================================
    # TEST 3: SHADOW PROCESSES — What does ExpressVPN spawn?
    # ================================================================

    async def test_shadow_processes(self) -> dict:
        """Find ALL processes spawned by ExpressVPN (parent-child tree)."""
        print(f"\n  [PROBE] TEST 3: SHADOW PROCESSES", flush=True)
        result = {"vpn_process_tree": [], "suspicious_children": []}

        try:
            # Get parent-child relationships
            output = subprocess.check_output(
                ["wmic", "process", "get", "ProcessId,ParentProcessId,Name,ExecutablePath",
                 "/format:csv"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            processes = {}
            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    try:
                        pid = parts[3]
                        ppid = parts[2]
                        name = parts[1]
                        path = parts[4] if len(parts) > 4 else ""
                        if pid.isdigit():
                            processes[pid] = {"pid": pid, "ppid": ppid, "name": name, "path": path}
                    except (IndexError, ValueError):
                        pass

            # Find ExpressVPN root processes
            vpn_roots = []
            for pid, proc in processes.items():
                if any(kw in proc["name"].lower() for kw in ("expressvpn", "lightway")):
                    vpn_roots.append(pid)
                    result["vpn_process_tree"].append(proc)

            # Find ALL children of VPN processes (recursive)
            def find_children(parent_pid, depth=0):
                if depth > 5:
                    return
                for pid, proc in processes.items():
                    if proc["ppid"] == parent_pid:
                        proc["depth"] = depth
                        proc["parent_vpn"] = True
                        result["vpn_process_tree"].append(proc)

                        # Is this child suspicious?
                        name_lower = proc["name"].lower()
                        is_expected = any(kw in name_lower for kw in (
                            "expressvpn", "lightway", "conhost", "werfault",
                        ))
                        if not is_expected and name_lower not in ("", "system"):
                            result["suspicious_children"].append({
                                **proc,
                                "reason": f"unexpected child of VPN process (depth {depth})",
                            })

                        find_children(pid, depth + 1)

            for root_pid in vpn_roots:
                find_children(root_pid)

        except Exception as e:
            result["error"] = str(e)

        n_children = len(result["suspicious_children"])
        if n_children > 0:
            names = [c["name"] for c in result["suspicious_children"]]
            self._finding("Shadow Processes", "HIGH",
                f"ExpressVPN spawned {n_children} unexpected child processes: {names}",
                "VPN should not spawn arbitrary processes. This could indicate: "
                "proxy agent, mining subprocess, or data collection tool.",
                evidence=result["suspicious_children"])
        else:
            self._finding("Shadow Processes", "INFO",
                f"{len(result['vpn_process_tree'])} VPN processes, no suspicious children",
                "Clean process tree.")

        print(f"  [PROBE] VPN tree: {len(result['vpn_process_tree'])} processes, {n_children} suspicious", flush=True)
        return result

    # ================================================================
    # TEST 4: CPU PARASITE — Mining or proxying when idle?
    # ================================================================

    async def test_cpu_parasite(self, duration: int = 15) -> dict:
        """Measure ExpressVPN CPU over time. Mining = sustained high CPU."""
        print(f"\n  [PROBE] TEST 4: CPU PARASITE ({duration}s)", flush=True)
        result = {"samples": [], "avg_cpu": 0, "max_cpu": 0, "sustained_high": False}

        for i in range(duration // 3):
            try:
                output = subprocess.check_output(
                    ["wmic", "path", "Win32_PerfFormattedData_PerfProc_Process",
                     "get", "Name,PercentProcessorTime,IDProcess", "/format:csv"],
                    timeout=10, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                vpn_cpu = 0
                for line in output.strip().split("\n"):
                    parts = line.strip().split(",")
                    if len(parts) >= 4:
                        name = parts[2].lower()
                        if any(kw in name for kw in ("expressvpn", "lightway", "xvpn")):
                            try:
                                vpn_cpu += int(parts[3])
                            except ValueError:
                                pass

                result["samples"].append({"time_s": i * 3, "cpu": vpn_cpu})
                print(f"  [PROBE]   {i*3}s: ExpressVPN CPU = {vpn_cpu}%", flush=True)

            except Exception:
                pass

            await asyncio.sleep(3)

        if result["samples"]:
            cpus = [s["cpu"] for s in result["samples"]]
            result["avg_cpu"] = round(sum(cpus) / len(cpus), 1)
            result["max_cpu"] = max(cpus)
            # "Sustained high" = more than 60% of samples above 50%
            high_samples = sum(1 for c in cpus if c > 50)
            result["sustained_high"] = high_samples > len(cpus) * 0.6

        if result["sustained_high"]:
            self._finding("CPU Parasite", "CRITICAL",
                f"ExpressVPN sustains {result['avg_cpu']}% CPU (max {result['max_cpu']}%) over {duration}s",
                "Sustained high CPU without active traffic suggests: "
                "crypto mining, traffic proxying, or computational task.",
                evidence=result)
        elif result["avg_cpu"] > 30:
            self._finding("CPU Parasite", "HIGH",
                f"ExpressVPN averages {result['avg_cpu']}% CPU",
                "Higher than expected for VPN encryption. Monitor if this persists.")
        elif result["avg_cpu"] > 10:
            self._finding("CPU Parasite", "MEDIUM",
                f"ExpressVPN averages {result['avg_cpu']}% CPU",
                "Moderate — could be normal VPN overhead.")
        else:
            self._finding("CPU Parasite", "INFO",
                f"ExpressVPN averages {result['avg_cpu']}% CPU",
                "Normal CPU usage for VPN.")

        return result

    # ================================================================
    # TEST 5: KAPE/CROSSRIDER INDICATORS
    # ================================================================

    async def test_kape_indicators(self) -> dict:
        """Check for known Kape Technologies / Crossrider artifacts."""
        print(f"\n  [PROBE] TEST 5: KAPE/CROSSRIDER INDICATORS", flush=True)
        result = {"indicators": [], "kape_domains": [], "crossrider_artifacts": []}

        # Known Kape Technologies domains/IPs
        KAPE_DOMAINS = [
            "kape.com", "kapetechnologies.com", "crossrider.com",
            "crossrider.net", "installcore.com", "revizer.com",
            "reimage.com", "intego.com", "webselenese.com",
            "cyberghostvpn.com", "privateinterneta", "zenmate.com",
        ]

        # Check DNS cache for Kape domains
        try:
            output = subprocess.check_output(
                ["ipconfig", "/displaydns"], timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                lower = line.lower().strip()
                for kd in KAPE_DOMAINS:
                    if kd in lower:
                        result["kape_domains"].append(line.strip())
        except Exception:
            pass

        # Check for Crossrider/Kape files on disk
        search_dirs = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")),
            Path(os.environ.get("APPDATA", "")),
        ]

        CROSSRIDER_PATTERNS = ["crossrider", "installcore", "revizer", "reimage", "webselenese"]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            try:
                for entry in search_dir.iterdir():
                    if any(p in entry.name.lower() for p in CROSSRIDER_PATTERNS):
                        result["crossrider_artifacts"].append(str(entry))
            except PermissionError:
                pass

        # Check ExpressVPN binary for Kape/Crossrider strings
        evpn_paths = [
            Path(os.environ.get("PROGRAMFILES", "")) / "ExpressVPN",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "ExpressVPN",
        ]

        for evpn_path in evpn_paths:
            if not evpn_path.exists():
                continue
            try:
                for f in evpn_path.rglob("*.exe"):
                    try:
                        content = f.read_bytes()
                        for pattern in [b"crossrider", b"installcore", b"kape", b"revizer",
                                       b"residential", b"proxy.network", b"p2p.relay"]:
                            if pattern in content.lower():
                                result["indicators"].append({
                                    "file": str(f),
                                    "pattern": pattern.decode(),
                                    "severity": "CRITICAL",
                                })
                    except (PermissionError, OSError):
                        pass
                # Also check DLLs
                for f in evpn_path.rglob("*.dll"):
                    try:
                        content = f.read_bytes()
                        for pattern in [b"residential", b"proxy.network", b"p2p.relay",
                                       b"bandwidth.sharing", b"mining", b"coin"]:
                            if pattern in content.lower():
                                result["indicators"].append({
                                    "file": str(f),
                                    "pattern": pattern.decode(),
                                    "severity": "CRITICAL",
                                })
                    except (PermissionError, OSError):
                        pass
            except Exception:
                pass

        if result["indicators"]:
            self._finding("Kape/Crossrider Binary", "CRITICAL",
                f"Found {len(result['indicators'])} suspicious strings in VPN binaries",
                "ExpressVPN binaries contain references to residential proxy or P2P relay patterns.",
                evidence=result["indicators"])
        elif result["kape_domains"]:
            self._finding("Kape DNS", "MEDIUM",
                f"Found {len(result['kape_domains'])} Kape-related domains in DNS cache",
                "Your system has contacted Kape Technologies infrastructure.")
        elif result["crossrider_artifacts"]:
            self._finding("Crossrider Files", "HIGH",
                f"Found Crossrider/Kape artifacts: {result['crossrider_artifacts']}",
                "Legacy adware infrastructure detected on system.")
        else:
            self._finding("Kape/Crossrider", "INFO",
                "No Kape Technologies or Crossrider indicators found",
                "Clean — no known adware/proxy artifacts detected.")

        print(f"  [PROBE] Indicators: {len(result['indicators'])}, DNS: {len(result['kape_domains'])}, Files: {len(result['crossrider_artifacts'])}", flush=True)
        return result

    # ================================================================
    # TEST 6: BANDWIDTH THEFT — Is your machine a proxy?
    # ================================================================

    async def test_bandwidth_theft(self, duration: int = 20) -> dict:
        """
        Detect if VPN is using your bandwidth to proxy other people's traffic.
        Method: Compare traffic on VPN adapter vs total traffic.
        If VPN traffic >> your actual browsing, something else is going through.
        """
        print(f"\n  [PROBE] TEST 6: BANDWIDTH THEFT ({duration}s)", flush=True)
        result = {"listening_ports": [], "unexpected_listeners": []}

        # Check for listening ports owned by ExpressVPN
        try:
            output = subprocess.check_output(
                ["netstat", "-a", "-n", "-o", "-p", "TCP"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            # Get VPN PIDs first
            vpn_pids = set()
            try:
                tasklist = subprocess.check_output(
                    ["tasklist", "/fi", "IMAGENAME eq ExpressVPN*", "/fo", "csv", "/nh"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode()
                for line in tasklist.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[1].strip('"')
                        if pid.isdigit():
                            vpn_pids.add(pid)
            except Exception:
                pass

            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts[3]:
                    pid = parts[4]
                    local = parts[1]
                    if pid in vpn_pids:
                        result["listening_ports"].append({
                            "local_addr": local,
                            "pid": pid,
                        })
                        # Is it listening on non-localhost?
                        if not local.startswith("127.0.0.1") and not local.startswith("0.0.0.0:0"):
                            result["unexpected_listeners"].append({
                                "addr": local, "pid": pid,
                                "reason": "VPN is accepting connections from other machines",
                            })

        except Exception:
            pass

        if result["unexpected_listeners"]:
            self._finding("Bandwidth Theft", "CRITICAL",
                f"ExpressVPN is LISTENING for incoming connections on {len(result['unexpected_listeners'])} ports",
                "A VPN client should NOT accept incoming connections. "
                "This is a strong indicator of residential proxy / bandwidth sharing.",
                evidence=result["unexpected_listeners"])
        elif result["listening_ports"]:
            addrs = [p["local_addr"] for p in result["listening_ports"]]
            localhost_only = all("127.0.0.1" in a for a in addrs)
            self._finding("Listening Ports", "INFO" if localhost_only else "MEDIUM",
                f"ExpressVPN listening on: {addrs}",
                "Localhost-only listeners are normal (IPC)." if localhost_only else
                "Non-localhost listeners need investigation.")
        else:
            self._finding("Bandwidth Theft", "INFO",
                "ExpressVPN has no listening ports",
                "Clean — not accepting incoming connections.")

        print(f"  [PROBE] Listeners: {len(result['listening_ports'])}, Suspicious: {len(result['unexpected_listeners'])}", flush=True)
        return result

    # ================================================================
    # FULL PROBE
    # ================================================================

    async def run_full_probe(self) -> dict:
        """Run all botnet probe tests."""
        print("\n" + "=" * 60, flush=True)
        print("  EXPRESSVPN BOTNET PROBE", flush=True)
        print("  Is your VPN secretly using your machine?", flush=True)
        print("=" * 60, flush=True)

        idle = await self.test_idle_traffic(20)
        ghosts = await self.test_ghost_connections()
        shadows = await self.test_shadow_processes()
        cpu = await self.test_cpu_parasite(15)
        kape = await self.test_kape_indicators()
        bandwidth = await self.test_bandwidth_theft()

        # Overall verdict
        score = sum(
            {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 5, "LOW": 2, "INFO": 0}.get(f["severity"], 0)
            for f in self.findings
        )

        if score < 15:
            verdict = "CLEAN — No botnet indicators found"
        elif score < 40:
            verdict = "LOW RISK — Minor anomalies, likely benign"
        elif score < 70:
            verdict = "SUSPICIOUS — VPN shows unusual behavior, investigate"
        elif score < 100:
            verdict = "HIGH RISK — Strong indicators of hidden activity"
        else:
            verdict = "BOTNET LIKELY — Your machine appears to be used as a proxy/miner"

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": platform.node(),
            "verdict": verdict,
            "risk_score": score,
            "tests": {
                "idle_traffic": idle,
                "ghost_connections": ghosts,
                "shadow_processes": shadows,
                "cpu_parasite": cpu,
                "kape_indicators": kape,
                "bandwidth_theft": bandwidth,
            },
            "findings": self.findings,
            "evidence": self.evidence,
        }

        return result


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    async def main():
        probe = VPNBotnetProbe()
        result = await probe.run_full_probe()

        print(f"\n{'='*60}")
        print(f"  VERDICT: {result['verdict']}")
        print(f"  Risk Score: {result['risk_score']}")
        print(f"{'='*60}")

        for f in result["findings"]:
            sev = f["severity"]
            marker = {"INFO": "  ", "MEDIUM": "! ", "HIGH": "!!", "CRITICAL": "!!!"}.get(sev, "  ")
            print(f"\n  {marker} [{sev:8s}] {f['category']}")
            print(f"     {f['detail']}")
            if f.get("verdict"):
                print(f"     -> {f['verdict']}")

    asyncio.run(main())
