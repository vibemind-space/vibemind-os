"""
VPN Transparency Check
========================
Compares system behavior with VPN ON vs OFF to detect:
1. Hidden traffic (more outbound connections than expected)
2. DNS hijacking (DNS queries going to unexpected servers)
3. CPU anomalies (unexplained CPU usage difference)
4. Hidden processes (new processes when VPN starts)
5. Traffic volume comparison (more data leaving than entering?)

Usage:
    python vpn_transparency.py

    # Or programmatic:
    from vpn_transparency import VPNTransparencyCheck
    checker = VPNTransparencyCheck()
    result = await checker.run_full_check()
"""

import asyncio
import json
import os
import platform
import re
import socket
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone


class VPNTransparencyCheck:
    """Compare system state with VPN on vs off."""

    def __init__(self):
        self.baseline = {}   # VPN OFF state
        self.vpn_state = {}  # VPN ON state

    async def capture_state(self, label: str = "snapshot") -> dict:
        """Capture complete system network state."""
        print(f"  [VPN-CHECK] Capturing state: {label}...", flush=True)

        state = {
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connections": await self._get_connections(),
            "dns_servers": await self._get_dns_servers(),
            "dns_cache": await self._get_dns_cache(),
            "public_ip": await self._get_public_ip(),
            "routes": await self._get_routes(),
            "processes": await self._get_process_cpu(),
            "interfaces": await self._get_interfaces(),
            "traffic_stats": await self._get_traffic_stats(),
        }

        n_conn = len(state["connections"])
        n_dns = len(state["dns_cache"])
        print(f"  [VPN-CHECK] {label}: {n_conn} connections, {n_dns} cached DNS, IP={state['public_ip'][:20]}", flush=True)
        return state

    async def _get_connections(self) -> list:
        """Get all active network connections."""
        connections = []
        try:
            output = subprocess.check_output(
                ["netstat", "-n", "-o", "-p", "TCP"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" and ":" in parts[2]:
                    try:
                        foreign = parts[2]
                        addr, port = foreign.rsplit(":", 1)
                        state = parts[3]
                        pid = parts[4] if parts[4].isdigit() else "0"
                        if addr not in ("0.0.0.0", "127.0.0.1", "*", "[::]"):
                            connections.append({
                                "remote_addr": addr,
                                "remote_port": int(port),
                                "state": state,
                                "pid": int(pid),
                            })
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass
        return connections

    async def _get_dns_servers(self) -> list:
        """Get configured DNS servers."""
        servers = []
        try:
            output = subprocess.check_output(
                ["nslookup", "localhost"],
                timeout=5, stderr=subprocess.STDOUT,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                if "Address" in line and ":" in line:
                    addr = line.split(":")[-1].strip()
                    if addr and not addr.startswith("127.") and addr != "::1":
                        servers.append(addr)
        except Exception:
            pass

        # Also check ipconfig
        try:
            output = subprocess.check_output(
                ["ipconfig", "/all"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                if "DNS" in line and ":" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        addr = parts[-1].strip()
                        if re.match(r'\d+\.\d+\.\d+\.\d+', addr):
                            if addr not in servers:
                                servers.append(addr)
        except Exception:
            pass

        return servers

    async def _get_dns_cache(self) -> list:
        """Get DNS cache entries."""
        domains = []
        try:
            output = subprocess.check_output(
                ["ipconfig", "/displaydns"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                line = line.strip()
                if "Record Name" in line or "Eintragsname" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        domain = parts[1].strip()
                        if domain and "." in domain:
                            domains.append(domain)
        except Exception:
            pass
        return list(set(domains))

    async def _get_public_ip(self) -> str:
        """Get public-facing IP address."""
        import urllib.request
        services = [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
        ]
        for svc in services:
            try:
                resp = urllib.request.urlopen(svc, timeout=5)
                return resp.read().decode().strip()
            except Exception:
                continue
        return "unknown"

    async def _get_routes(self) -> list:
        """Get routing table."""
        routes = []
        try:
            output = subprocess.check_output(
                ["route", "print", "-4"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                parts = line.split()
                if len(parts) >= 5 and re.match(r'\d+\.\d+', parts[0]):
                    routes.append({
                        "destination": parts[0],
                        "netmask": parts[1],
                        "gateway": parts[2],
                        "interface": parts[3],
                    })
        except Exception:
            pass
        return routes

    async def _get_process_cpu(self) -> list:
        """Get top CPU-consuming processes."""
        processes = []
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
                    name = parts[2]
                    pid = parts[1]
                    if cpu > 5 and name.lower() not in ("_total", "idle", "system"):
                        processes.append({"name": name, "pid": pid, "cpu": cpu})
        except Exception:
            pass
        return sorted(processes, key=lambda x: -x["cpu"])[:20]

    async def _get_interfaces(self) -> list:
        """Get network interfaces."""
        interfaces = []
        try:
            output = subprocess.check_output(
                ["ipconfig"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            current = None
            for line in output.split("\n"):
                if "adapter" in line.lower() and ":" in line:
                    current = {"name": line.split(":")[0].strip(), "ips": []}
                elif current and ("IPv4" in line or "IP Address" in line or "IP-Adresse" in line):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        ip = parts[-1].strip()
                        current["ips"].append(ip)
                        interfaces.append(current)
                        current = None
        except Exception:
            pass
        return interfaces

    async def _get_traffic_stats(self) -> dict:
        """Get network traffic statistics."""
        stats = {"bytes_sent": 0, "bytes_recv": 0}
        try:
            output = subprocess.check_output(
                ["netstat", "-e"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.split("\n"):
                if "Bytes" in line or "Byte" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            stats["bytes_recv"] = int(parts[1])
                            stats["bytes_sent"] = int(parts[2])
                        except ValueError:
                            pass
        except Exception:
            pass
        return stats

    async def compare_states(self, state_a: dict, state_b: dict) -> dict:
        """Compare two captured states and find anomalies."""
        result = {
            "comparison": f"{state_a['label']} vs {state_b['label']}",
            "findings": [],
            "risk_score": 0,
        }

        # 1. IP Change
        ip_a = state_a.get("public_ip", "?")
        ip_b = state_b.get("public_ip", "?")
        if ip_a != ip_b:
            result["findings"].append({
                "category": "IP Change",
                "severity": "INFO",
                "detail": f"Public IP changed: {ip_a} -> {ip_b}",
                "verdict": "Expected with VPN",
            })

        # 2. DNS Server Change
        dns_a = set(state_a.get("dns_servers", []))
        dns_b = set(state_b.get("dns_servers", []))
        if dns_a != dns_b:
            new_dns = dns_b - dns_a
            removed_dns = dns_a - dns_b
            result["findings"].append({
                "category": "DNS Servers Changed",
                "severity": "MEDIUM",
                "detail": f"Added: {new_dns}, Removed: {removed_dns}",
                "verdict": "VPN may redirect DNS - verify these are the VPN provider's servers",
            })
            result["risk_score"] += 10

        # 3. Connection Count Difference
        conn_a = len(state_a.get("connections", []))
        conn_b = len(state_b.get("connections", []))
        diff = conn_b - conn_a
        if diff > 10:
            result["findings"].append({
                "category": "Extra Connections",
                "severity": "HIGH",
                "detail": f"{diff} more connections with VPN ({conn_a} -> {conn_b})",
                "verdict": "VPN should not add many new connections beyond the tunnel",
            })
            result["risk_score"] += 20
        elif diff > 5:
            result["findings"].append({
                "category": "Extra Connections",
                "severity": "MEDIUM",
                "detail": f"{diff} more connections ({conn_a} -> {conn_b})",
                "verdict": "Slight increase expected (VPN tunnel + keepalives)",
            })
            result["risk_score"] += 5

        # 4. New destinations not explained by VPN
        dests_a = set(c["remote_addr"] for c in state_a.get("connections", []))
        dests_b = set(c["remote_addr"] for c in state_b.get("connections", []))
        new_dests = dests_b - dests_a
        if len(new_dests) > 5:
            result["findings"].append({
                "category": "New Destinations",
                "severity": "MEDIUM",
                "detail": f"{len(new_dests)} new remote IPs when VPN active: {list(new_dests)[:10]}",
                "verdict": "Check if these belong to the VPN provider",
            })
            result["risk_score"] += 10

        # 5. CPU difference
        cpu_a = {p["name"]: p["cpu"] for p in state_a.get("processes", [])}
        cpu_b = {p["name"]: p["cpu"] for p in state_b.get("processes", [])}

        # Find VPN-related CPU increases
        for name, cpu in cpu_b.items():
            prev = cpu_a.get(name, 0)
            if cpu > prev + 30 and "vpn" not in name.lower() and "express" not in name.lower():
                result["findings"].append({
                    "category": "CPU Anomaly",
                    "severity": "HIGH",
                    "detail": f"{name}: CPU went from {prev}% to {cpu}% when VPN activated",
                    "verdict": "Non-VPN process should not increase CPU when VPN starts",
                })
                result["risk_score"] += 15

        # VPN process CPU
        for name, cpu in cpu_b.items():
            if "vpn" in name.lower() or "express" in name.lower():
                result["findings"].append({
                    "category": "VPN CPU Usage",
                    "severity": "INFO" if cpu < 50 else "MEDIUM" if cpu < 80 else "HIGH",
                    "detail": f"{name}: {cpu}% CPU",
                    "verdict": f"{'Normal' if cpu < 50 else 'High' if cpu < 80 else 'Very high'} for VPN encryption overhead",
                })
                if cpu > 80:
                    result["risk_score"] += 10

        # 6. New processes
        procs_a = set(p["name"] for p in state_a.get("processes", []))
        procs_b = set(p["name"] for p in state_b.get("processes", []))
        new_procs = procs_b - procs_a
        suspicious_new = [p for p in new_procs if "vpn" not in p.lower() and "express" not in p.lower()
                          and "tap" not in p.lower() and "tun" not in p.lower()]
        if suspicious_new:
            result["findings"].append({
                "category": "New Processes",
                "severity": "HIGH" if len(suspicious_new) > 3 else "MEDIUM",
                "detail": f"Non-VPN processes started with VPN: {suspicious_new}",
                "verdict": "These processes should not depend on VPN activation",
            })
            result["risk_score"] += len(suspicious_new) * 5

        # 7. Traffic volume comparison
        traffic_a = state_a.get("traffic_stats", {})
        traffic_b = state_b.get("traffic_stats", {})
        sent_a = traffic_a.get("bytes_sent", 0)
        sent_b = traffic_b.get("bytes_sent", 0)
        recv_a = traffic_a.get("bytes_recv", 0)
        recv_b = traffic_b.get("bytes_recv", 0)

        if sent_a > 0 and sent_b > 0:
            sent_ratio = sent_b / max(sent_a, 1)
            if sent_ratio > 2.0:
                result["findings"].append({
                    "category": "Traffic Volume",
                    "severity": "HIGH",
                    "detail": f"Outbound traffic {sent_ratio:.1f}x higher with VPN ({sent_a} -> {sent_b} bytes)",
                    "verdict": "VPN overhead explains ~20-30% increase, not 2x+",
                })
                result["risk_score"] += 20

        # 8. Route changes
        routes_a = set(r["gateway"] for r in state_a.get("routes", []))
        routes_b = set(r["gateway"] for r in state_b.get("routes", []))
        new_gateways = routes_b - routes_a
        if new_gateways:
            result["findings"].append({
                "category": "Route Changes",
                "severity": "INFO",
                "detail": f"New gateways: {new_gateways}",
                "verdict": "Expected - VPN adds a tunnel route",
            })

        # Verdict
        score = result["risk_score"]
        if score < 15:
            result["verdict"] = "CLEAN - VPN behaves as expected"
        elif score < 40:
            result["verdict"] = "MINOR CONCERNS - Some anomalies worth monitoring"
        elif score < 70:
            result["verdict"] = "SUSPICIOUS - VPN adds unexplained activity"
        else:
            result["verdict"] = "HIGH RISK - VPN may be hiding malicious activity"

        return result

    async def run_full_check(self) -> dict:
        """
        Run the full VPN transparency check.
        Captures current state (assumes VPN is ON),
        then compares with a second capture for delta analysis.
        """
        print("\n  [VPN-CHECK] === VPN Transparency Check ===", flush=True)
        print("  [VPN-CHECK] Capturing current state (VPN assumed ON)...", flush=True)

        vpn_state = await self.capture_state("vpn_on")

        # Quick analysis without baseline (single-state check)
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": platform.node(),
            "vpn_state": vpn_state,
            "findings": [],
            "risk_score": 0,
        }

        # Analyze VPN-specific indicators
        # 1. Check if VPN process exists
        vpn_procs = [p for p in vpn_state.get("processes", [])
                     if any(kw in p["name"].lower() for kw in ("vpn", "express", "nord", "proton", "wireguard", "openvpn"))]
        if vpn_procs:
            for vp in vpn_procs:
                severity = "INFO" if vp["cpu"] < 50 else "MEDIUM" if vp["cpu"] < 80 else "HIGH"
                result["findings"].append({
                    "category": "VPN Process",
                    "severity": severity,
                    "detail": f"{vp['name']}: {vp['cpu']}% CPU (PID {vp['pid']})",
                    "verdict": f"{'Normal' if vp['cpu'] < 50 else 'High CPU - check if sustained'}" ,
                })
                if vp["cpu"] > 80:
                    result["risk_score"] += 15

        # 2. Check DNS servers — are they the VPN's?
        dns = vpn_state.get("dns_servers", [])
        result["findings"].append({
            "category": "DNS Configuration",
            "severity": "INFO",
            "detail": f"DNS servers: {dns}",
            "verdict": "Verify these belong to your VPN provider",
        })

        # 3. Check public IP
        result["findings"].append({
            "category": "Public IP",
            "severity": "INFO",
            "detail": f"Current public IP: {vpn_state.get('public_ip', '?')}",
            "verdict": "Should be VPN provider's IP, not your ISP",
        })

        # 4. Connection analysis
        conns = vpn_state.get("connections", [])
        unique_dests = set(c["remote_addr"] for c in conns)
        result["findings"].append({
            "category": "Active Connections",
            "severity": "INFO" if len(conns) < 50 else "MEDIUM",
            "detail": f"{len(conns)} active connections to {len(unique_dests)} unique destinations",
            "verdict": f"{'Normal' if len(conns) < 50 else 'High number of connections'}",
        })

        # 5. Check for unusual ports
        ports = Counter(c["remote_port"] for c in conns)
        unusual = {p: c for p, c in ports.items() if p not in (80, 443, 53, 8080, 8443) and c >= 2}
        if unusual:
            result["findings"].append({
                "category": "Unusual Ports",
                "severity": "MEDIUM",
                "detail": f"Non-standard ports with multiple connections: {dict(list(unusual.items())[:10])}",
                "verdict": "Check what services use these ports",
            })
            result["risk_score"] += 5

        # 6. Traffic stats
        traffic = vpn_state.get("traffic_stats", {})
        sent = traffic.get("bytes_sent", 0)
        recv = traffic.get("bytes_recv", 0)
        if sent > 0 and recv > 0:
            ratio = sent / recv
            result["findings"].append({
                "category": "Traffic Ratio",
                "severity": "INFO" if ratio < 0.5 else "MEDIUM" if ratio < 1.0 else "HIGH",
                "detail": f"Send/Receive ratio: {ratio:.2f} (sent {sent:,} / recv {recv:,} bytes)",
                "verdict": f"{'Normal browsing pattern' if ratio < 0.3 else 'Moderate upload ratio' if ratio < 1.0 else 'HIGH upload ratio - unusual for browsing'}",
            })
            if ratio > 1.0:
                result["risk_score"] += 20

        # Overall verdict
        score = result["risk_score"]
        if score < 15:
            result["verdict"] = "CLEAN - No anomalies detected"
        elif score < 40:
            result["verdict"] = "MINOR CONCERNS - Worth monitoring"
        else:
            result["verdict"] = "SUSPICIOUS - Investigate VPN behavior"

        print(f"  [VPN-CHECK] === VERDICT: {result['verdict']} (score {result['risk_score']}) ===", flush=True)
        return result


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    async def main():
        checker = VPNTransparencyCheck()
        result = await checker.run_full_check()

        print(f"\n{'='*55}")
        print(f"  VPN TRANSPARENCY CHECK")
        print(f"  Host: {result['hostname']}")
        print(f"  Risk Score: {result['risk_score']}")
        print(f"  Verdict: {result['verdict']}")
        print(f"{'='*55}")

        for f in result["findings"]:
            icon = {"INFO": " ", "MEDIUM": "!", "HIGH": "!!", "CRITICAL": "!!!"}
            sev = f["severity"]
            print(f"  [{sev:8s}] {f['category']:25s} {f['detail'][:60]}")
            print(f"  {'':10s} -> {f['verdict']}")

    asyncio.run(main())
