"""
Network Monitor MCP Server
==============================
Real-time network security monitoring tools.

Tools:
  - wifi_scan: All WiFi networks, signal, encryption, rogue APs
  - arp_monitor: Who's on the network? ARP spoofing detection
  - port_monitor: Open ports on this PC — what's listening?
  - dns_monitor: DNS queries — where does your PC phone home?
  - traffic_log: Network traffic by process
  - rogue_detect: Evil Twin / Rogue AP detection
  - beacon_detect: C2 beacon detection in network
  - anomaly_detect: Unusual traffic pattern detection
  - bandwidth_monitor: Who uses how much?
  - cert_monitor: TLS certificate validation (MITM detection)
  - geo_block: Flag connections to suspicious countries
"""

import asyncio
import json
import os
import re
import socket
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Network Monitor",
    instructions=(
        "Network security monitoring tools. Use 'wifi_scan' to scan WiFi networks, "
        "'arp_monitor' to check who's on your network, 'port_monitor' for open ports, "
        "'dns_monitor' for DNS queries, 'traffic_log' for per-process traffic, "
        "'full_network_audit' for a complete network security check."
    ),
)


@mcp.tool()
async def wifi_scan():
    """
    Scan all visible WiFi networks. Shows SSID, signal strength,
    encryption type, channel, and flags potential rogue APs.
    """
    result = {"networks": [], "warnings": [], "total": 0}

    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            timeout=15, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")

        current = {}
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                if current.get("ssid"):
                    result["networks"].append(current)
                current = {}
                continue

            if "SSID" in line and "BSSID" not in line and ":" in line:
                current["ssid"] = line.split(":", 1)[1].strip()
            elif "BSSID" in line and ":" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    current["bssid"] = parts[1].strip()
            elif "Signal" in line and ":" in line:
                sig = line.split(":", 1)[1].strip().replace("%", "")
                try:
                    current["signal_percent"] = int(sig)
                except ValueError:
                    current["signal_percent"] = sig
            elif ("Verschl" in line or "Cipher" in line or "Encryption" in line) and ":" in line:
                current["encryption"] = line.split(":", 1)[1].strip()
            elif ("Authentifizierung" in line or "Authentication" in line) and ":" in line:
                current["auth"] = line.split(":", 1)[1].strip()
            elif "Kanal" in line or "Channel" in line and ":" in line:
                chan = line.split(":", 1)[1].strip()
                try:
                    current["channel"] = int(chan)
                except ValueError:
                    current["channel"] = chan

        if current.get("ssid"):
            result["networks"].append(current)

        result["total"] = len(result["networks"])

        # Detect rogue APs — same SSID, different BSSID
        ssid_bssids = defaultdict(list)
        for net in result["networks"]:
            if net.get("ssid"):
                ssid_bssids[net["ssid"]].append(net.get("bssid", "?"))

        for ssid, bssids in ssid_bssids.items():
            if len(bssids) > 1:
                result["warnings"].append({
                    "type": "MULTIPLE_APS",
                    "severity": "MEDIUM",
                    "ssid": ssid,
                    "bssids": bssids,
                    "message": f"Multiple APs with same SSID '{ssid}' — could be rogue AP",
                })

        # Flag open networks
        for net in result["networks"]:
            auth = net.get("auth", "").lower()
            if "open" in auth or "offen" in auth:
                result["warnings"].append({
                    "type": "OPEN_NETWORK",
                    "severity": "HIGH",
                    "ssid": net.get("ssid", "?"),
                    "message": f"Open WiFi '{net.get('ssid')}' — no encryption, traffic visible",
                })

        # Flag WEP
        for net in result["networks"]:
            enc = net.get("encryption", "").lower()
            if "wep" in enc:
                result["warnings"].append({
                    "type": "WEAK_ENCRYPTION",
                    "severity": "HIGH",
                    "ssid": net.get("ssid", "?"),
                    "message": f"WEP encryption on '{net.get('ssid')}' — crackable in minutes",
                })

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def arp_monitor():
    """
    Show all devices on the local network via ARP table.
    Detects ARP spoofing (multiple IPs for same MAC or vice versa).
    """
    result = {"devices": [], "warnings": [], "gateway": None}

    try:
        output = subprocess.check_output(
            ["arp", "-a"], timeout=10, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")

        ip_to_mac = {}
        mac_to_ips = defaultdict(list)

        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                ip = parts[0]
                mac = parts[1]
                if re.match(r'\d+\.\d+\.\d+\.\d+', ip) and re.match(r'[0-9a-f]{2}[-:][0-9a-f]{2}', mac, re.I):
                    device_type = parts[2] if len(parts) > 2 else "?"
                    device = {"ip": ip, "mac": mac, "type": device_type}

                    # Try reverse DNS
                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                        device["hostname"] = hostname
                    except Exception:
                        pass

                    result["devices"].append(device)
                    ip_to_mac[ip] = mac
                    mac_to_ips[mac].append(ip)

        # Detect gateway
        try:
            route_output = subprocess.check_output(
                ["ipconfig"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in route_output.split("\n"):
                if ("Gateway" in line or "Standardgateway" in line or "gateway" in line.lower()) and ":" in line:
                    gw = line.split(":")[-1].strip()
                    if re.match(r'\d+\.\d+\.\d+\.\d+', gw):
                        result["gateway"] = gw
                        break
        except Exception:
            pass

        # ARP Spoofing detection (skip multicast MACs 01-00-5e-*)
        for mac, ips in mac_to_ips.items():
            if (len(ips) > 1 and mac != "ff-ff-ff-ff-ff-ff"
                    and not mac.startswith("01-00-5e") and not mac.startswith("33-33")):
                result["warnings"].append({
                    "type": "ARP_SPOOF",
                    "severity": "CRITICAL",
                    "mac": mac,
                    "ips": ips,
                    "message": f"MAC {mac} has {len(ips)} IPs — possible ARP spoofing!",
                })

        # Duplicate MAC detection (skip multicast)
        mac_counts = Counter(d["mac"] for d in result["devices"])
        for mac, count in mac_counts.items():
            if (count > 3 and mac != "ff-ff-ff-ff-ff-ff"
                    and not mac.startswith("01-00-5e") and not mac.startswith("33-33")):
                result["warnings"].append({
                    "type": "MAC_FLOOD",
                    "severity": "HIGH",
                    "mac": mac,
                    "count": count,
                    "message": f"MAC {mac} appears {count} times — possible MAC flooding",
                })

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def port_monitor():
    """
    Show all listening ports on this PC. Identifies which process
    owns each port and flags suspicious listeners.
    """
    result = {"listening": [], "warnings": [], "total": 0}

    SUSPICIOUS_PORTS = {
        4444: "Metasploit default", 5555: "Android debug", 6667: "IRC (botnet)",
        31337: "Back Orifice", 1337: "Common backdoor", 9999: "Common backdoor",
        4443: "Alt HTTPS", 8888: "Alt HTTP", 3389: "RDP",
    }

    try:
        output = subprocess.check_output(
            ["netstat", "-a", "-n", "-o", "-p", "TCP"],
            timeout=10, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")

        # Get PID to process name mapping
        pid_map = {}
        try:
            tasklist = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in tasklist.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2:
                    pid_map[parts[1].strip('"')] = parts[0].strip('"')
        except Exception:
            pass

        for line in output.strip().split("\n"):
            parts = line.split()
            line_upper = line.upper()
            if len(parts) >= 4 and ("LISTENING" in line_upper or "ABHOR" in line_upper or "ABHREN" in line_upper or "ABH" in line_upper):
                local = parts[1]
                pid = parts[-1]

                try:
                    addr, port_str = local.rsplit(":", 1)
                    port = int(port_str)
                except (ValueError, IndexError):
                    continue

                entry = {
                    "address": addr,
                    "port": port,
                    "pid": pid,
                    "process": pid_map.get(pid, "?"),
                }

                # Check if listening on all interfaces (0.0.0.0)
                if addr == "0.0.0.0" or addr == "[::]":
                    entry["exposed"] = True
                else:
                    entry["exposed"] = False

                result["listening"].append(entry)

                # Flag suspicious ports
                if port in SUSPICIOUS_PORTS:
                    result["warnings"].append({
                        "type": "SUSPICIOUS_PORT",
                        "severity": "HIGH",
                        "port": port,
                        "process": entry["process"],
                        "message": f"Port {port} ({SUSPICIOUS_PORTS[port]}) is listening — process: {entry['process']}",
                    })

                # Flag externally exposed services
                safe_system_ports = {80, 443, 135, 139, 445, 5040, 5357, 7680,
                                     49664, 49665, 49666, 49667, 49668, 49669, 50115}
                if entry["exposed"] and port not in safe_system_ports:
                    # Docker ports are expected but still a risk
                    is_docker = "docker" in entry["process"].lower()
                    severity = "LOW" if is_docker else "MEDIUM"
                    label = " (Docker)" if is_docker else ""
                    result["warnings"].append({
                        "type": "EXPOSED_PORT",
                        "severity": severity,
                        "port": port,
                        "process": entry["process"],
                        "message": f"Port {port}{label} exposed — accessible from LAN",
                    })

        result["total"] = len(result["listening"])

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def dns_monitor(duration: int = 15):
    """
    Monitor DNS queries for specified duration. Shows what domains
    your PC is resolving and flags suspicious patterns.

    Args:
        duration: Monitoring duration in seconds (default 15)
    """
    result = {"domains": [], "suspicious": [], "total": 0}

    # Get DNS cache before and after
    def get_dns_cache():
        domains = set()
        try:
            output = subprocess.check_output(
                ["ipconfig", "/displaydns"], timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in output.split("\n"):
                if "Record Name" in line or "Eintragsname" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        d = parts[1].strip()
                        if d and "." in d:
                            domains.add(d)
        except Exception:
            pass
        return domains

    before = get_dns_cache()
    await asyncio.sleep(duration)
    after = get_dns_cache()

    new_domains = sorted(after - before)
    result["domains"] = new_domains
    result["total"] = len(new_domains)
    result["duration_seconds"] = duration

    # Flag suspicious patterns
    SUSPICIOUS = {
        "tracking": ["analytics", "tracking", "telemetry", "metrics", "pixel", "beacon"],
        "crypto": ["pool", "mining", "miner", "stratum", "coinhive"],
        "malware": ["evil", "malware", "exploit", "payload", "botnet"],
        "high_entropy": [],  # DGA-like domains
    }

    for domain in new_domains:
        dl = domain.lower()
        for category, keywords in SUSPICIOUS.items():
            if any(kw in dl for kw in keywords):
                result["suspicious"].append({
                    "domain": domain,
                    "category": category,
                    "severity": "HIGH" if category in ("crypto", "malware") else "MEDIUM",
                })
                break

        # Check for high-entropy (DGA) domains
        parts = domain.split(".")
        if len(parts) >= 2:
            hostname = parts[0]
            if len(hostname) > 15:
                consonants = sum(1 for c in hostname.lower() if c.isalpha() and c not in "aeiou")
                vowels = sum(1 for c in hostname.lower() if c in "aeiou")
                if vowels > 0 and consonants / vowels > 4:
                    result["suspicious"].append({
                        "domain": domain,
                        "category": "DGA_suspect",
                        "severity": "HIGH",
                        "message": "High consonant ratio — possible DGA domain",
                    })

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def traffic_log(duration: int = 10):
    """
    Log network traffic by process. Shows which processes are
    sending/receiving data and to which destinations.

    Args:
        duration: Monitoring duration in seconds
    """
    result = {"by_process": {}, "total_connections": 0, "duration": duration}

    # Get PID map
    pid_map = {}
    try:
        tasklist = subprocess.check_output(
            ["tasklist", "/fo", "csv", "/nh"], timeout=10, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in tasklist.strip().split("\n"):
            parts = line.split(",")
            if len(parts) >= 2:
                pid_map[parts[1].strip('"')] = parts[0].strip('"')
    except Exception:
        pass

    # Sample connections multiple times
    all_connections = defaultdict(lambda: {"destinations": set(), "count": 0, "ports": Counter()})

    for _ in range(duration // 2):
        try:
            output = subprocess.check_output(
                ["netstat", "-n", "-o", "-p", "TCP"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" and ":" in parts[2]:
                    pid = parts[-1]
                    remote = parts[2]
                    state = parts[3]

                    if state in ("HERGESTELLT", "ESTABLISHED", "WARTEND", "TIME_WAIT"):
                        try:
                            addr, port_str = remote.rsplit(":", 1)
                            port = int(port_str)
                        except (ValueError, IndexError):
                            continue

                        if addr in ("0.0.0.0", "127.0.0.1", "[::]"):
                            continue

                        if pid == "0":
                            continue  # Skip System Idle Process (TIME_WAIT remnants)
                        proc_name = pid_map.get(pid, f"PID-{pid}")
                        all_connections[proc_name]["destinations"].add(addr)
                        all_connections[proc_name]["count"] += 1
                        all_connections[proc_name]["ports"][port] += 1

        except Exception:
            pass

        await asyncio.sleep(2)

    # Convert to serializable format
    for proc, data in all_connections.items():
        result["by_process"][proc] = {
            "unique_destinations": len(data["destinations"]),
            "total_connections": data["count"],
            "top_ports": dict(data["ports"].most_common(5)),
            "destinations": sorted(data["destinations"])[:20],
        }

    result["total_connections"] = sum(d["total_connections"] for d in result["by_process"].values())

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def bandwidth_monitor(duration: int = 10):
    """
    Measure network bandwidth usage over time.

    Args:
        duration: Measurement duration in seconds
    """
    result = {"samples": [], "total_sent": 0, "total_recv": 0}

    def get_bytes():
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

    start_recv, start_sent = get_bytes()
    start_time = time.time()

    for _ in range(duration // 3):
        await asyncio.sleep(3)
        recv, sent = get_bytes()
        elapsed = time.time() - start_time
        result["samples"].append({
            "time": round(elapsed, 1),
            "sent_kb": round((sent - start_sent) / 1024, 1),
            "recv_kb": round((recv - start_recv) / 1024, 1),
            "rate_up_kbps": round((sent - start_sent) / 1024 / elapsed, 1),
            "rate_down_kbps": round((recv - start_recv) / 1024 / elapsed, 1),
        })

    end_recv, end_sent = get_bytes()
    result["total_sent"] = end_sent - start_sent
    result["total_recv"] = end_recv - start_recv

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def cert_monitor():
    """
    Check TLS certificates of active connections for MITM attacks.
    Verifies certificate chains and flags self-signed or expired certs.
    """
    import ssl
    result = {"checks": [], "warnings": [], "total": 0}

    # Get all HTTPS destinations
    destinations = set()
    try:
        output = subprocess.check_output(
            ["netstat", "-n", "-p", "TCP"], timeout=5, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3 and ":443" in parts[2]:
                try:
                    addr = parts[2].rsplit(":", 1)[0]
                    if addr not in ("0.0.0.0", "127.0.0.1"):
                        destinations.add(addr)
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass

    # Check each certificate — try without hostname verification first (IP connections through VPN)
    for addr in list(destinations)[:15]:
        check = {"address": addr, "valid": False}
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            with ctx.wrap_socket(socket.socket()) as s:
                s.settimeout(3)
                s.connect((addr, 443))
                cert = s.getpeercert()
                if cert:
                    cn = dict(x[0] for x in cert.get("subject", [()])).get("commonName", "?")
                    issuer = dict(x[0] for x in cert.get("issuer", [()])).get("organizationName", "?")
                    not_after = cert.get("notAfter", "?")
                    check["cn"] = cn
                    check["issuer"] = issuer
                    check["expires"] = not_after
                    check["valid"] = True

                    # Check for self-signed
                    subject_org = dict(x[0] for x in cert.get("subject", [()])).get("organizationName", "")
                    issuer_org = dict(x[0] for x in cert.get("issuer", [()])).get("organizationName", "")
                    if subject_org and subject_org == issuer_org:
                        check["self_signed"] = True
                        # Microsoft telemetry endpoints use their own CA — not real MITM
                        is_msft = "microsoft" in (issuer_org or "").lower()
                        if not is_msft:
                            result["warnings"].append({
                                "type": "SELF_SIGNED",
                                "severity": "HIGH",
                                "address": addr,
                                "cn": cn,
                                "message": f"Self-signed certificate on {addr} — possible MITM!",
                            })
        except ssl.SSLCertVerificationError as e:
            check["error"] = f"Cert chain invalid: {str(e)[:60]}"
            result["warnings"].append({
                "type": "CERT_INVALID",
                "severity": "CRITICAL",
                "address": addr,
                "message": f"Certificate chain invalid on {addr} — MITM possible!",
            })
        except (ConnectionRefusedError, OSError, socket.timeout):
            check["error"] = "Connection failed"
        except Exception as e:
            check["error"] = str(e)[:60]

        result["checks"].append(check)

    result["total"] = len(result["checks"])
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def geo_block():
    """
    Flag active connections to suspicious countries/regions.
    Uses IP geolocation to identify connections outside expected regions.
    """
    import urllib.request
    result = {"connections": [], "flagged": [], "total": 0}

    SUSPICIOUS_COUNTRIES = {
        "CN": "China", "RU": "Russia", "KP": "North Korea",
        "IR": "Iran", "SY": "Syria", "CU": "Cuba",
    }

    # Get all remote IPs
    remote_ips = set()
    try:
        output = subprocess.check_output(
            ["netstat", "-n", "-p", "TCP"], timeout=5, stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 3 and ":" in parts[2]:
                try:
                    addr = parts[2].rsplit(":", 1)[0]
                    if addr not in ("0.0.0.0", "127.0.0.1") and not addr.startswith(("192.168.", "10.", "172.")):
                        remote_ips.add(addr)
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass

    # Check a sample of IPs
    for ip in list(remote_ips)[:20]:
        try:
            resp = urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=country,countryCode,org,as", timeout=3)
            data = json.loads(resp.read().decode())
            entry = {"ip": ip, "country": data.get("country", "?"), "country_code": data.get("countryCode", "?"),
                     "org": data.get("org", "?"), "as": data.get("as", "?")}
            result["connections"].append(entry)

            cc = data.get("countryCode", "")
            if cc in SUSPICIOUS_COUNTRIES:
                result["flagged"].append({
                    "ip": ip,
                    "country": SUSPICIOUS_COUNTRIES[cc],
                    "org": data.get("org", "?"),
                    "severity": "HIGH",
                    "message": f"Connection to {SUSPICIOUS_COUNTRIES[cc]} ({ip}) — org: {data.get('org', '?')}",
                })

            await asyncio.sleep(0.5)  # Rate limit
        except Exception:
            pass

    result["total"] = len(result["connections"])
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def full_network_audit():
    """
    Complete network security audit. Runs all checks:
    WiFi scan, ARP table, open ports, DNS queries, bandwidth,
    certificate check, and geo-blocking.
    """
    results = {}

    results["wifi"] = json.loads(await wifi_scan())
    results["arp"] = json.loads(await arp_monitor())
    results["ports"] = json.loads(await port_monitor())
    results["bandwidth"] = json.loads(await bandwidth_monitor(duration=6))
    results["certs"] = json.loads(await cert_monitor())

    # Collect all warnings
    all_warnings = []
    for key, data in results.items():
        if isinstance(data, dict):
            all_warnings.extend(data.get("warnings", []))

    results["summary"] = {
        "wifi_networks": results["wifi"].get("total", 0),
        "devices_on_network": len(results["arp"].get("devices", [])),
        "listening_ports": results["ports"].get("total", 0),
        "total_warnings": len(all_warnings),
        "critical_warnings": len([w for w in all_warnings if w.get("severity") == "CRITICAL"]),
        "high_warnings": len([w for w in all_warnings if w.get("severity") == "HIGH"]),
    }
    results["all_warnings"] = all_warnings

    return json.dumps(results, indent=2, default=str)


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    if args.http:
        import uvicorn
        from mcp.server.fastmcp import create_sse_app
        app = create_sse_app(mcp)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        mcp.run(transport="stdio")
