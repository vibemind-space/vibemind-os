"""
Botnet / Zombie PC Detector
==============================
Detects compromised machines in a network by analyzing:
1. DNS queries for DGA (Domain Generation Algorithm) patterns
2. Network beacons (periodic C2 callbacks)
3. Local endpoint anomalies (suspicious processes, connections, autoruns)

Usage:
    from detector import BotnetDetector
    d = BotnetDetector()

    # Check this machine
    result = await d.check_local()

    # Monitor network DNS
    result = await d.analyze_dns()

    # Full scan
    result = await d.full_scan()
"""

import asyncio
import ctypes
import json
import math
import os
import platform
import re
import socket
import struct
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ================================================================
# DNS DGA DETECTOR — Entropy-based domain analysis
# ================================================================

class DGADetector:
    """
    Detect Domain Generation Algorithm (DGA) domains by analyzing:
    - Shannon entropy of domain names (random = high entropy)
    - Character distribution (DGA domains have unusual char distributions)
    - Consonant/vowel ratio (DGA domains lack natural language patterns)
    - Known DGA patterns (hex strings, base64-like)
    - Domain length anomalies
    """

    # Known legit high-entropy domains (CDNs, cloud services)
    WHITELIST = {
        "cloudflare.com", "amazonaws.com", "cloudfront.net", "akamaized.net",
        "fastly.net", "googleusercontent.com", "googlevideo.com", "fbcdn.net",
        "gstatic.com", "googleapis.com", "microsoft.com", "azure.com",
        "windows.net", "office365.com", "live.com", "outlook.com",
        "apple.com", "icloud.com", "cdn.jsdelivr.net", "unpkg.com",
    }

    # Known malware TLDs (frequently abused)
    SUSPICIOUS_TLDS = {".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".xyz", ".pw", ".cc", ".su", ".biz"}

    def __init__(self):
        self.analyzed = []
        self.suspicious = []

    @staticmethod
    def _shannon_entropy(s: str) -> float:
        """Calculate Shannon entropy of a string."""
        if not s:
            return 0.0
        freq = Counter(s)
        length = len(s)
        return -sum((count / length) * math.log2(count / length) for count in freq.values())

    @staticmethod
    def _consonant_vowel_ratio(s: str) -> float:
        """Calculate consonant to vowel ratio. Natural language ~1.5-2.0, DGA ~3-10."""
        vowels = sum(1 for c in s.lower() if c in "aeiou")
        consonants = sum(1 for c in s.lower() if c.isalpha() and c not in "aeiou")
        if vowels == 0:
            return 99.0
        return consonants / vowels

    @staticmethod
    def _digit_ratio(s: str) -> float:
        """Ratio of digits in the string."""
        if not s:
            return 0.0
        return sum(1 for c in s if c.isdigit()) / len(s)

    @staticmethod
    def _has_hex_pattern(s: str) -> bool:
        """Check if domain looks like a hex string."""
        return bool(re.match(r'^[0-9a-f]{8,}$', s.lower()))

    def analyze_domain(self, domain: str) -> dict:
        """Analyze a single domain for DGA indicators."""
        # Extract the registrable domain (remove TLD)
        parts = domain.lower().strip(".").split(".")
        if len(parts) < 2:
            return {"domain": domain, "score": 0, "suspicious": False, "entropy": 0, "reasons": []}

        # Skip reverse DNS and whitelisted domains
        if "in-addr.arpa" in domain.lower() or "ip6.arpa" in domain.lower():
            return {"domain": domain, "score": 0, "suspicious": False, "entropy": 0, "reasons": ["reverse DNS"]}

        registered = ".".join(parts[-2:])
        if registered in self.WHITELIST or any(wl in domain.lower() for wl in self.WHITELIST):
            return {"domain": domain, "score": 0, "suspicious": False, "entropy": 0, "reasons": ["whitelisted"]}

        # Analyze the subdomain/hostname part (most indicative)
        hostname = parts[0] if len(parts) > 2 else parts[0]
        tld = "." + parts[-1]

        entropy = self._shannon_entropy(hostname)
        cv_ratio = self._consonant_vowel_ratio(hostname)
        digit_ratio = self._digit_ratio(hostname)
        is_hex = self._has_hex_pattern(hostname)
        length = len(hostname)

        # Scoring: 0-100 (higher = more likely DGA)
        score = 0
        reasons = []

        # Entropy check (natural domains: 2.5-3.5, DGA: 3.5-4.5)
        if entropy > 4.0:
            score += 35
            reasons.append(f"very high entropy ({entropy:.2f})")
        elif entropy > 3.5:
            score += 20
            reasons.append(f"high entropy ({entropy:.2f})")

        # Length check (DGA domains tend to be longer)
        if length > 20:
            score += 20
            reasons.append(f"very long hostname ({length} chars)")
        elif length > 12:
            score += 10
            reasons.append(f"long hostname ({length} chars)")

        # Consonant/vowel ratio
        if cv_ratio > 5.0:
            score += 20
            reasons.append(f"unnatural consonant ratio ({cv_ratio:.1f})")
        elif cv_ratio > 3.0:
            score += 10
            reasons.append(f"high consonant ratio ({cv_ratio:.1f})")

        # Digit ratio
        if digit_ratio > 0.5:
            score += 15
            reasons.append(f"mostly digits ({digit_ratio:.0%})")
        elif digit_ratio > 0.3:
            score += 8
            reasons.append(f"many digits ({digit_ratio:.0%})")

        # Hex pattern
        if is_hex:
            score += 25
            reasons.append("hex string pattern")

        # Suspicious TLD
        if tld in self.SUSPICIOUS_TLDS:
            score += 15
            reasons.append(f"suspicious TLD ({tld})")

        # No vowels at all
        if cv_ratio > 50:
            score += 15
            reasons.append("no vowels")

        suspicious = score >= 50

        result = {
            "domain": domain,
            "hostname": hostname,
            "score": min(score, 100),
            "suspicious": suspicious,
            "entropy": round(entropy, 2),
            "cv_ratio": round(cv_ratio, 2),
            "digit_ratio": round(digit_ratio, 2),
            "length": length,
            "reasons": reasons,
        }

        self.analyzed.append(result)
        if suspicious:
            self.suspicious.append(result)

        return result

    def analyze_batch(self, domains: list) -> dict:
        """Analyze a batch of domains and return summary."""
        results = [self.analyze_domain(d) for d in domains]
        suspicious = [r for r in results if r["suspicious"]]

        return {
            "total_analyzed": len(results),
            "suspicious_count": len(suspicious),
            "suspicious_domains": suspicious,
            "avg_entropy": round(sum(r["entropy"] for r in results) / len(results), 2) if results else 0,
            "top_scores": sorted(results, key=lambda x: -x["score"])[:10],
        }


# ================================================================
# BEACON DETECTOR — Timing analysis of outbound connections
# ================================================================

class BeaconDetector:
    """
    Detect C2 beacons by analyzing outbound connection patterns:
    - Periodic connections to the same host (fixed interval +/- jitter)
    - Consistent packet sizes (C2 heartbeats are uniform)
    - Connections to unusual ports
    - Connections to IP addresses (not domains) — C2 often uses raw IPs
    """

    # Common legitimate periodic connections to ignore
    LEGIT_DESTINATIONS = {
        "time.windows.com", "time.google.com", "ntp.ubuntu.com",
        "update.microsoft.com", "download.windowsupdate.com",
        "ocsp.digicert.com", "ctldl.windowsupdate.com",
        "settings-win.data.microsoft.com",
    }

    # Known CDN/Cloud IP ranges (first two octets) to reduce false positives
    LEGIT_IP_PREFIXES = {
        "54.230.", "54.231.", "54.239.",     # CloudFront
        "162.159.", "104.16.", "104.17.", "104.18.", "104.19.", "104.20.",
        "104.21.", "104.22.", "104.23.", "104.24.", "104.25.", "104.26.",
        "172.64.", "172.65.", "172.66.", "172.67.",  # Cloudflare
        "13.107.", "204.79.", "40.126.",     # Microsoft
        "142.250.", "172.217.", "216.58.",   # Google
        "157.240.", "31.13.",               # Facebook/Meta
        "151.101.",                          # Fastly/Reddit
        "185.199.",                          # GitHub
    }

    SUSPICIOUS_PORTS = {
        4444, 5555, 6666, 6667, 6668, 6669,  # Metasploit, IRC
        8888, 9999, 1337, 31337,               # Common backdoor ports
        4443, 8443, 8080, 8081,                # Alt HTTPS/HTTP
        53,                                     # DNS (unusual for direct connection)
    }

    def __init__(self):
        self.connections = []
        self.beacons = []

    async def capture_connections(self, duration_seconds: int = 30) -> list:
        """Capture outbound connections over a time period."""
        print(f"  [BEACON] Capturing connections for {duration_seconds}s...", flush=True)

        snapshots = []
        start = time.time()

        while time.time() - start < duration_seconds:
            try:
                if platform.system() == "Windows":
                    output = subprocess.check_output(
                        ["netstat", "-n", "-o"], timeout=5,
                        stderr=subprocess.DEVNULL,
                    ).decode("utf-8", errors="replace")
                else:
                    output = subprocess.check_output(
                        ["ss", "-tunp"], timeout=5,
                        stderr=subprocess.DEVNULL,
                    ).decode("utf-8", errors="replace")

                timestamp = time.time()
                connections = self._parse_netstat(output)
                snapshots.append({"time": timestamp, "connections": connections})

            except Exception:
                pass

            await asyncio.sleep(5)  # Sample every 5 seconds

        self.connections = snapshots
        print(f"  [BEACON] Captured {len(snapshots)} snapshots", flush=True)
        return snapshots

    def _parse_netstat(self, output: str) -> list:
        """Parse netstat output into structured connections."""
        connections = []
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) < 4:
                continue

            # Windows netstat format: Proto LocalAddress ForeignAddress State PID
            if parts[0] in ("TCP", "UDP") and ":" in parts[2]:
                try:
                    foreign = parts[2]
                    # Split address:port
                    if foreign.count(":") == 1:
                        addr, port = foreign.rsplit(":", 1)
                    else:
                        continue  # IPv6 or weird format

                    port = int(port)
                    pid = int(parts[-1]) if parts[-1].isdigit() else 0
                    state = parts[3] if len(parts) > 3 and parts[3] in ("ESTABLISHED", "TIME_WAIT", "SYN_SENT", "CLOSE_WAIT") else ""

                    if addr not in ("0.0.0.0", "127.0.0.1", "*", "[::]", "[::1]"):
                        connections.append({
                            "remote_addr": addr,
                            "remote_port": port,
                            "state": state,
                            "pid": pid,
                        })
                except (ValueError, IndexError):
                    continue

        return connections

    def analyze_beacons(self) -> dict:
        """Analyze captured connections for beacon patterns."""
        if not self.connections:
            return {"error": "No connections captured. Run capture_connections() first."}

        # Group connections by destination (addr:port)
        dest_timeline = defaultdict(list)
        for snapshot in self.connections:
            for conn in snapshot["connections"]:
                key = f"{conn['remote_addr']}:{conn['remote_port']}"
                dest_timeline[key].append(snapshot["time"])

        # Analyze each destination for periodicity
        results = []
        for dest, timestamps in dest_timeline.items():
            if len(timestamps) < 3:
                continue  # Need at least 3 data points

            # Calculate intervals between connections
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]
            avg_interval = sum(intervals) / len(intervals)
            std_dev = (sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5

            addr, port_str = dest.rsplit(":", 1)
            port = int(port_str)

            # Beacon score
            score = 0
            reasons = []

            # Low jitter = high periodicity (beacon signature)
            if avg_interval > 0 and std_dev / avg_interval < 0.1:
                score += 40
                reasons.append(f"very regular interval ({avg_interval:.0f}s +/- {std_dev:.1f}s)")
            elif avg_interval > 0 and std_dev / avg_interval < 0.3:
                score += 20
                reasons.append(f"regular interval ({avg_interval:.0f}s)")

            # Seen in every snapshot = persistent connection
            if len(timestamps) >= len(self.connections) * 0.8:
                score += 20
                reasons.append(f"persistent ({len(timestamps)}/{len(self.connections)} snapshots)")

            # Suspicious port
            if port in self.SUSPICIOUS_PORTS:
                score += 25
                reasons.append(f"suspicious port ({port})")

            # Raw IP address (no DNS = suspicious)
            try:
                socket.inet_aton(addr)
                is_ip = True
            except socket.error:
                is_ip = False

            if is_ip:
                score += 10
                reasons.append("direct IP (no DNS)")

                # Private IP talking to external = very suspicious
                if not addr.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
                    "192.168.", "127.")):
                    score += 5
                    reasons.append("external IP")

            # Check against legit destinations and CDN IPs
            is_legit = any(legit in addr.lower() for legit in self.LEGIT_DESTINATIONS)
            is_cdn = any(addr.startswith(pfx) for pfx in self.LEGIT_IP_PREFIXES)
            if is_legit or is_cdn:
                score = max(score - 40, 0)
                reasons.append("known legit/CDN destination")

            # Filter sampling artifacts: if interval matches our capture rate, it's not a real beacon
            if abs(avg_interval - 5.0) < 1.0 and len(timestamps) <= 4:
                score = max(score - 30, 0)
                reasons.append("likely sampling artifact")

            # Local DNS resolver (gateway) on port 53 is normal
            if port == 53 and addr.startswith(("192.168.", "10.", "172.16.")):
                score = max(score - 40, 0)
                reasons.append("local DNS resolver")

            if score >= 30:
                results.append({
                    "destination": dest,
                    "addr": addr,
                    "port": port,
                    "score": min(score, 100),
                    "beacon_interval_seconds": round(avg_interval, 1),
                    "jitter_seconds": round(std_dev, 1),
                    "seen_count": len(timestamps),
                    "reasons": reasons,
                })

        self.beacons = sorted(results, key=lambda x: -x["score"])

        return {
            "snapshots_analyzed": len(self.connections),
            "unique_destinations": len(dest_timeline),
            "potential_beacons": len(self.beacons),
            "beacons": self.beacons[:20],
        }


# ================================================================
# ENDPOINT ZOMBIE CHECKER — Local machine analysis
# ================================================================

class EndpointChecker:
    """
    Check the local machine for signs of compromise:
    - Suspicious processes (unknown, high CPU, network-heavy)
    - Unusual outbound connections
    - Suspicious autostart entries (Registry, Scheduled Tasks)
    - Crypto-mining indicators
    - Known malware process names
    """

    KNOWN_MALWARE_NAMES = {
        "coinhive", "cryptonight", "xmrig", "minergate", "nicehash",
        "cgminer", "bfgminer", "ethminer", "phoenix.miner", "lolminer",
        "ncat.exe", "netcat",
        "mimikatz", "lazagne", "procdump",
        "psexec", "paexec",
        "cobalt", "meterpreter", "reverse_tcp",
        "botnet", "keylog", "stealer",
    }

    # Legitimate processes to never flag
    LEGIT_PROCESSES = {
        "bash.exe", "sh.exe", "cmd.exe", "python.exe", "python3.exe",
        "pwsh.exe", "powershell.exe", "node.exe", "git.exe", "code.exe",
        "conhost.exe", "wsl.exe", "wslhost.exe", "msedge.exe",
        "chrome.exe", "firefox.exe", "discord.exe", "spotify.exe",
        "teams.exe", "slack.exe", "explorer.exe", "svchost.exe",
        "csrss.exe", "lsass.exe", "winlogon.exe", "services.exe",
        "taskhostw.exe", "sihost.exe", "ctfmon.exe", "dllhost.exe",
        "armorycrate.service.exe", "armorycrate.usersessionhelper.exe",
        "wmireg", "sentinel", "sentry",
    }

    SUSPICIOUS_PATHS = [
        r"\\Temp\\", r"\\tmp\\", r"\\AppData\\Local\\Temp",
        r"\\Users\\Public\\",
        r"\\Windows\\Temp\\",
    ]

    async def check_processes(self) -> dict:
        """Analyze running processes for suspicious indicators."""
        result = {
            "total_processes": 0,
            "suspicious_processes": [],
            "high_cpu_processes": [],
            "network_processes": [],
        }

        if platform.system() != "Windows":
            return result

        try:
            # Get process list with details
            output = subprocess.check_output(
                ["wmic", "process", "get",
                 "ProcessId,Name,ExecutablePath,CommandLine,WorkingSetSize",
                 "/format:csv"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) < 5 or parts[1] == "CommandLine":
                    continue

                result["total_processes"] += 1
                cmd = parts[1].lower()
                name = parts[3].lower()
                path = parts[2].lower()
                pid = parts[4] if len(parts) > 4 else "?"

                # Skip known legit processes
                if any(legit in name for legit in self.LEGIT_PROCESSES):
                    continue

                # Check for known malware names
                for mal in self.KNOWN_MALWARE_NAMES:
                    if mal in name or mal in cmd:
                        result["suspicious_processes"].append({
                            "pid": pid, "name": parts[3], "path": parts[2],
                            "reason": f"matches known malware pattern: {mal}",
                            "severity": "CRITICAL",
                        })
                        break

                # Check for suspicious paths
                for sus_path in self.SUSPICIOUS_PATHS:
                    if sus_path.lower() in path and name not in ("setup.exe", "installer.exe"):
                        # Check if it's a common temp process
                        if not any(legit in name for legit in ("chrome", "firefox", "edge", "update", "setup")):
                            result["suspicious_processes"].append({
                                "pid": pid, "name": parts[3], "path": parts[2],
                                "reason": f"running from suspicious path: {sus_path}",
                                "severity": "MEDIUM",
                            })
                            break

        except Exception as e:
            result["error"] = str(e)

        # Get network-using processes
        try:
            output = subprocess.check_output(
                ["netstat", "-b", "-n"], timeout=10,
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            current_process = None
            for line in output.strip().split("\n"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_process = line[1:-1]
                elif "ESTABLISHED" in line and current_process:
                    parts = line.split()
                    if len(parts) >= 3:
                        result["network_processes"].append({
                            "process": current_process,
                            "remote": parts[2],
                        })
        except Exception:
            pass

        return result

    async def check_autoruns(self) -> dict:
        """Check autostart entries for suspicious items."""
        result = {
            "registry_autoruns": [],
            "scheduled_tasks": [],
            "startup_folder": [],
            "suspicious_autoruns": [],
        }

        if platform.system() != "Windows":
            return result

        # Check Registry Run keys
        REG_KEYS = [
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
            r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        ]

        for key in REG_KEYS:
            try:
                output = subprocess.check_output(
                    ["reg", "query", key], timeout=5,
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                for line in output.strip().split("\n"):
                    line = line.strip()
                    if "REG_SZ" in line or "REG_EXPAND_SZ" in line:
                        parts = line.split(None, 2)
                        if len(parts) >= 3:
                            name = parts[0]
                            value = parts[2] if len(parts) > 2 else ""
                            entry = {"key": key, "name": name, "value": value}
                            result["registry_autoruns"].append(entry)

                            # Check if suspicious
                            value_lower = value.lower()
                            if any(p.lower() in value_lower for p in self.SUSPICIOUS_PATHS):
                                entry["suspicious"] = True
                                entry["reason"] = "runs from suspicious path"
                                result["suspicious_autoruns"].append(entry)
                            elif any(m in value_lower for m in self.KNOWN_MALWARE_NAMES):
                                entry["suspicious"] = True
                                entry["reason"] = "matches malware pattern"
                                result["suspicious_autoruns"].append(entry)

            except Exception:
                pass

        # Check Scheduled Tasks
        try:
            output = subprocess.check_output(
                ["schtasks", "/query", "/fo", "csv", "/nh"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 3:
                    task_name = parts[0].strip('"')
                    # Skip system tasks
                    if task_name.startswith("\\Microsoft\\"):
                        continue
                    result["scheduled_tasks"].append({
                        "name": task_name,
                        "status": parts[2].strip('"') if len(parts) > 2 else "?",
                    })
        except Exception:
            pass

        # Check Startup folder
        startup_paths = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
            Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup"),
        ]

        for sp in startup_paths:
            if sp.exists():
                for f in sp.iterdir():
                    entry = {"path": str(f), "name": f.name, "size": f.stat().st_size if f.is_file() else 0}
                    result["startup_folder"].append(entry)
                    if f.suffix.lower() in (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js"):
                        entry["suspicious"] = True
                        entry["reason"] = f"executable in startup folder ({f.suffix})"
                        result["suspicious_autoruns"].append(entry)

        return result

    async def check_crypto_mining(self) -> dict:
        """Detect crypto-mining activity."""
        result = {"mining_detected": False, "indicators": []}

        if platform.system() != "Windows":
            return result

        # Check for high CPU processes
        try:
            output = subprocess.check_output(
                ["wmic", "path", "Win32_PerfFormattedData_PerfProc_Process",
                 "get", "Name,PercentProcessorTime", "/format:csv"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 3 and parts[2].isdigit():
                    cpu = int(parts[2])
                    name = parts[1]
                    if cpu > 80 and name.lower() not in ("_total", "idle", "system"):
                        result["indicators"].append({
                            "type": "high_cpu",
                            "process": name,
                            "cpu_percent": cpu,
                        })
        except Exception:
            pass

        # Check for known mining process names
        try:
            output = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            mining_keywords = ["miner", "xmrig", "nicehash", "cgminer", "ethminer",
                              "phoenix", "lolminer", "nbminer", "trex", "gminer"]

            for line in output.strip().split("\n"):
                name = line.split(",")[0].strip('"').lower()
                for kw in mining_keywords:
                    if kw in name:
                        result["mining_detected"] = True
                        result["indicators"].append({
                            "type": "mining_process",
                            "process": name,
                            "keyword": kw,
                        })
        except Exception:
            pass

        return result


# ================================================================
# MAIN DETECTOR — Orchestrates all checks
# ================================================================

class BotnetDetector:
    """Main detector that runs all checks and produces a report."""

    def __init__(self):
        self.dga = DGADetector()
        self.beacon = BeaconDetector()
        self.endpoint = EndpointChecker()

    async def check_local(self) -> dict:
        """Full local machine check."""
        print("  [BOTNET] Starting local machine check...", flush=True)

        proc_r, autorun_r, mining_r = await asyncio.gather(
            self.endpoint.check_processes(),
            self.endpoint.check_autoruns(),
            self.endpoint.check_crypto_mining(),
        )

        issues = []

        # Process findings
        for p in proc_r.get("suspicious_processes", []):
            issues.append({
                "severity": p.get("severity", "MEDIUM"),
                "category": "Suspicious Process",
                "title": f"Suspicious process: {p['name']} (PID {p['pid']})",
                "description": p.get("reason", ""),
            })

        # Autorun findings
        for a in autorun_r.get("suspicious_autoruns", []):
            issues.append({
                "severity": "HIGH",
                "category": "Suspicious Autorun",
                "title": f"Suspicious autorun: {a.get('name', '?')}",
                "description": a.get("reason", ""),
            })

        # Mining
        if mining_r.get("mining_detected"):
            issues.append({
                "severity": "CRITICAL",
                "category": "Crypto Mining",
                "title": "Crypto mining process detected",
                "description": f"Mining indicators: {json.dumps(mining_r['indicators'][:3])}",
            })

        for ind in mining_r.get("indicators", []):
            if ind["type"] == "high_cpu":
                issues.append({
                    "severity": "MEDIUM",
                    "category": "High CPU",
                    "title": f"High CPU: {ind['process']} ({ind['cpu_percent']}%)",
                    "description": "Sustained high CPU may indicate mining or malware.",
                })

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "processes": proc_r,
            "autoruns": autorun_r,
            "mining": mining_r,
            "issues": issues,
            "zombie_score": min(len(issues) * 15, 100),
        }

        print(f"  [BOTNET] Local check done: {len(issues)} issues, zombie_score={result['zombie_score']}", flush=True)
        return result

    async def analyze_dns(self, domains: list = None) -> dict:
        """Analyze DNS queries for DGA patterns."""
        print("  [BOTNET] Analyzing DNS...", flush=True)

        if not domains:
            # Try to extract recent DNS from system cache
            domains = await self._get_dns_cache()

        dns_result = self.dga.analyze_batch(domains)

        issues = []
        for d in dns_result.get("suspicious_domains", []):
            issues.append({
                "severity": "HIGH" if d["score"] >= 70 else "MEDIUM",
                "category": "DGA Domain",
                "title": f"Suspicious domain: {d['domain']} (score {d['score']})",
                "description": f"Reasons: {', '.join(d['reasons'])}",
            })

        dns_result["issues"] = issues
        print(f"  [BOTNET] DNS analysis done: {dns_result['suspicious_count']} suspicious of {dns_result['total_analyzed']}", flush=True)
        return dns_result

    async def analyze_beacons(self, duration: int = 30) -> dict:
        """Monitor network for C2 beacons."""
        print(f"  [BOTNET] Monitoring beacons for {duration}s...", flush=True)

        await self.beacon.capture_connections(duration)
        beacon_result = self.beacon.analyze_beacons()

        issues = []
        for b in beacon_result.get("beacons", []):
            if b["score"] >= 50:
                issues.append({
                    "severity": "CRITICAL" if b["score"] >= 70 else "HIGH",
                    "category": "C2 Beacon",
                    "title": f"Potential C2 beacon: {b['destination']} (every {b['beacon_interval_seconds']}s)",
                    "description": f"Reasons: {', '.join(b['reasons'])}",
                })

        beacon_result["issues"] = issues
        print(f"  [BOTNET] Beacon analysis done: {beacon_result['potential_beacons']} potential beacons", flush=True)
        return beacon_result

    async def full_scan(self, beacon_duration: int = 30) -> dict:
        """Complete botnet detection scan."""
        print("\n  [BOTNET] === Full Botnet Detection Scan ===", flush=True)

        local_r = await self.check_local()
        dns_r = await self.analyze_dns()
        beacon_r = await self.analyze_beacons(beacon_duration)

        all_issues = local_r.get("issues", []) + dns_r.get("issues", []) + beacon_r.get("issues", [])

        # Overall zombie probability
        zombie_score = 0
        if local_r.get("mining", {}).get("mining_detected"):
            zombie_score += 40
        zombie_score += len(local_r.get("processes", {}).get("suspicious_processes", [])) * 15
        zombie_score += len(local_r.get("autoruns", {}).get("suspicious_autoruns", [])) * 10
        zombie_score += dns_r.get("suspicious_count", 0) * 10
        zombie_score += sum(1 for b in beacon_r.get("beacons", []) if b["score"] >= 50) * 20
        zombie_score = min(zombie_score, 100)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": platform.node(),
            "zombie_score": zombie_score,
            "zombie_verdict": "CLEAN" if zombie_score < 20 else "SUSPICIOUS" if zombie_score < 50 else "LIKELY COMPROMISED",
            "local": local_r,
            "dns": dns_r,
            "beacons": beacon_r,
            "issues": all_issues,
            "summary": {
                "suspicious_processes": len(local_r.get("processes", {}).get("suspicious_processes", [])),
                "suspicious_autoruns": len(local_r.get("autoruns", {}).get("suspicious_autoruns", [])),
                "mining_detected": local_r.get("mining", {}).get("mining_detected", False),
                "dga_domains": dns_r.get("suspicious_count", 0),
                "c2_beacons": sum(1 for b in beacon_r.get("beacons", []) if b["score"] >= 50),
                "total_issues": len(all_issues),
            },
        }

        print(f"\n  [BOTNET] === VERDICT: {result['zombie_verdict']} (score {zombie_score}/100) ===", flush=True)
        return result

    async def _get_dns_cache(self) -> list:
        """Extract domains from Windows DNS cache."""
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
                        if domain and "." in domain and not domain.startswith("_"):
                            domains.append(domain)
        except Exception:
            pass

        return list(set(domains))
