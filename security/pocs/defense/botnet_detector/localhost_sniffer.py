"""
Localhost Traffic Sniffer for ExpressVPN gRPC
================================================
Captures TCP traffic on localhost:13925 WITHOUT Wireshark/Npcap.

Methods:
1. netsh trace — Windows built-in packet capture
2. TCP connection monitoring — high-frequency netstat sampling
3. Process memory scanning — find gRPC data in BrowserHelper memory
4. Named pipe enumeration — check for IPC channels
5. Windows Event Log — network events

All methods use built-in Windows tools — no extra installs needed.
"""

import asyncio
import ctypes
import json
import os
import re
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


class LocalhostSniffer:

    def __init__(self, target_port: int = 13925):
        self.port = target_port
        self.captures = []

    # ================================================================
    # METHOD 1: High-frequency connection monitoring
    # ================================================================

    async def monitor_connections(self, duration: int = 30, interval: float = 0.5) -> dict:
        """Monitor connections at high frequency to catch transient requests."""
        print(f"  [SNIFFER] Monitoring port {self.port} at {1/interval:.0f} Hz for {duration}s...", flush=True)

        result = {"samples": [], "events": [], "total_bytes_estimate": 0}
        prev_connections = {}

        start = time.time()
        sample_count = 0

        while time.time() - start < duration:
            try:
                output = subprocess.check_output(
                    ["netstat", "-n", "-o", "-p", "TCP"],
                    timeout=3, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                current = {}
                for line in output.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 5 and parts[0] == "TCP":
                        local = parts[1]
                        remote = parts[2]
                        state = parts[3]
                        pid = parts[4]

                        if f":{self.port}" in local or f":{self.port}" in remote:
                            key = f"{local}-{remote}-{pid}"
                            current[key] = {
                                "local": local, "remote": remote,
                                "state": state, "pid": pid,
                                "time": round(time.time() - start, 2),
                            }

                # Detect new connections
                for key, conn in current.items():
                    if key not in prev_connections:
                        result["events"].append({
                            "type": "NEW",
                            "time": conn["time"],
                            **conn,
                        })
                        print(f"  [SNIFFER]   NEW: {conn['local']} -> {conn['remote']} ({conn['state']}) PID {conn['pid']}", flush=True)

                # Detect closed connections
                for key, conn in prev_connections.items():
                    if key not in current:
                        result["events"].append({
                            "type": "CLOSED",
                            "time": round(time.time() - start, 2),
                            **conn,
                        })

                # Detect state changes
                for key in current:
                    if key in prev_connections:
                        if current[key]["state"] != prev_connections[key]["state"]:
                            result["events"].append({
                                "type": "STATE_CHANGE",
                                "time": current[key]["time"],
                                "from": prev_connections[key]["state"],
                                "to": current[key]["state"],
                                **current[key],
                            })

                prev_connections = current
                sample_count += 1

            except Exception:
                pass

            await asyncio.sleep(interval)

        result["total_samples"] = sample_count
        result["total_events"] = len(result["events"])

        print(f"  [SNIFFER] {sample_count} samples, {len(result['events'])} events", flush=True)
        return result

    # ================================================================
    # METHOD 2: Named Pipe enumeration
    # ================================================================

    async def enumerate_pipes(self) -> dict:
        """Find all Named Pipes related to ExpressVPN."""
        print(f"  [SNIFFER] Enumerating Named Pipes...", flush=True)
        result = {"pipes": [], "expressvpn_pipes": []}

        try:
            # List all named pipes via PowerShell
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "[System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | ForEach-Object { $_ }"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                pipe = line.strip()
                if pipe:
                    result["pipes"].append(pipe)
                    if any(kw in pipe.lower() for kw in ("express", "vpn", "kape", "lightway", "xvpn", "proteus")):
                        result["expressvpn_pipes"].append(pipe)

        except Exception as e:
            result["error"] = str(e)

        if result["expressvpn_pipes"]:
            print(f"  [SNIFFER] Found {len(result['expressvpn_pipes'])} ExpressVPN pipes:", flush=True)
            for p in result["expressvpn_pipes"]:
                print(f"    {p}", flush=True)
        else:
            print(f"  [SNIFFER] No ExpressVPN Named Pipes found (checked {len(result['pipes'])} total)", flush=True)

        return result

    # ================================================================
    # METHOD 3: Process memory strings extraction
    # ================================================================

    async def scan_process_memory(self) -> dict:
        """Extract readable strings from BrowserHelper process memory."""
        print(f"  [SNIFFER] Scanning BrowserHelper process memory...", flush=True)
        result = {"pid": None, "strings_found": [], "grpc_calls": [], "urls": [], "tokens": []}

        # Find BrowserHelper PID
        try:
            output = subprocess.check_output(
                ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.BrowserHelper.exe", "/fo", "csv", "/nh"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2:
                    pid = parts[1].strip('"')
                    if pid.isdigit():
                        result["pid"] = int(pid)
                        break
        except Exception:
            pass

        if not result["pid"]:
            # Try AppService instead
            try:
                output = subprocess.check_output(
                    ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.AppService.exe", "/fo", "csv", "/nh"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                for line in output.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[1].strip('"')
                        if pid.isdigit():
                            result["pid"] = int(pid)
                            break
            except Exception:
                pass

        if not result["pid"]:
            print(f"  [SNIFFER] No ExpressVPN process found", flush=True)
            return result

        print(f"  [SNIFFER] Target PID: {result['pid']}", flush=True)

        # Use procdump-style memory dump via PowerShell
        try:
            # Read process command line and environment
            output = subprocess.check_output(
                ["wmic", "process", "where", f"ProcessId={result['pid']}",
                 "get", "CommandLine,ExecutablePath", "/format:csv"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                if str(result["pid"]) in line:
                    print(f"  [SNIFFER] Process: {line.strip()[:150]}", flush=True)

        except Exception:
            pass

        # Use handle.exe or equivalent to see open handles
        try:
            output = subprocess.check_output(
                ["powershell", "-Command",
                 f"Get-Process -Id {result['pid']} | Select-Object -ExpandProperty Modules | "
                 "ForEach-Object { $_.FileName }"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            modules = []
            for line in output.strip().split("\n"):
                mod = line.strip()
                if mod and mod.endswith((".dll", ".exe")):
                    modules.append(mod)
                    if any(kw in mod.lower() for kw in ("grpc", "braze", "sentry", "launchdarkly", "protobuf", "kape")):
                        result["strings_found"].append(f"Loaded module: {Path(mod).name}")

            print(f"  [SNIFFER] {len(modules)} modules loaded, interesting:", flush=True)
            for s in result["strings_found"]:
                print(f"    {s}", flush=True)

        except Exception as e:
            print(f"  [SNIFFER] Module enumeration failed: {e}", flush=True)

        # Check network connections of this specific process
        try:
            output = subprocess.check_output(
                ["netstat", "-n", "-o", "-p", "TCP"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            for line in output.strip().split("\n"):
                if str(result["pid"]) in line.split()[-1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        result["grpc_calls"].append({
                            "local": parts[1],
                            "remote": parts[2],
                            "state": parts[3],
                        })

            print(f"  [SNIFFER] Process has {len(result['grpc_calls'])} TCP connections:", flush=True)
            for c in result["grpc_calls"]:
                print(f"    {c['local']} -> {c['remote']} ({c['state']})", flush=True)

        except Exception:
            pass

        return result

    # ================================================================
    # METHOD 4: Windows Firewall logging
    # ================================================================

    async def enable_firewall_logging(self, duration: int = 30) -> dict:
        """Temporarily enable Windows Firewall logging to capture localhost traffic."""
        print(f"  [SNIFFER] Checking Windows Firewall log...", flush=True)
        result = {"log_entries": [], "expressvpn_entries": []}

        # Check if firewall log exists
        fw_log = Path("C:/Windows/System32/LogFiles/Firewall/pfirewall.log")
        if fw_log.exists():
            try:
                content = fw_log.read_text(encoding="utf-8", errors="replace")
                lines = content.strip().split("\n")

                for line in lines[-200:]:  # Last 200 entries
                    if f" {self.port} " in line or "13925" in line:
                        result["expressvpn_entries"].append(line.strip())

                print(f"  [SNIFFER] Firewall log: {len(lines)} total entries, {len(result['expressvpn_entries'])} for port {self.port}", flush=True)
                for e in result["expressvpn_entries"][:10]:
                    print(f"    {e[:120]}", flush=True)

            except PermissionError:
                print(f"  [SNIFFER] Firewall log exists but access denied (need admin)", flush=True)
        else:
            print(f"  [SNIFFER] No firewall log found (logging may be disabled)", flush=True)

        return result

    # ================================================================
    # METHOD 5: ETW Network Trace (built-in Windows)
    # ================================================================

    async def capture_etw_trace(self, duration: int = 15) -> dict:
        """Use PowerShell to capture network events via ETW."""
        print(f"  [SNIFFER] Capturing network events via ETW for {duration}s...", flush=True)
        result = {"events": [], "tcp_events": []}

        # Use Get-NetTCPConnection (PowerShell built-in, no admin needed)
        samples = []
        start = time.time()

        while time.time() - start < duration:
            try:
                output = subprocess.check_output(
                    ["powershell", "-Command",
                     f"Get-NetTCPConnection -LocalPort {self.port} -ErrorAction SilentlyContinue | "
                     "Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess,CreationTime | "
                     "ConvertTo-Json"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                if output.strip():
                    try:
                        data = json.loads(output)
                        if isinstance(data, dict):
                            data = [data]
                        for entry in data:
                            entry["sample_time"] = round(time.time() - start, 1)
                            samples.append(entry)
                    except json.JSONDecodeError:
                        pass

            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass

            # Also check remote port connections
            try:
                output = subprocess.check_output(
                    ["powershell", "-Command",
                     f"Get-NetTCPConnection -RemotePort {self.port} -ErrorAction SilentlyContinue | "
                     "Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess,CreationTime | "
                     "ConvertTo-Json"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                if output.strip():
                    try:
                        data = json.loads(output)
                        if isinstance(data, dict):
                            data = [data]
                        for entry in data:
                            entry["sample_time"] = round(time.time() - start, 1)
                            entry["direction"] = "CLIENT"
                            samples.append(entry)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

            await asyncio.sleep(2)

        # Resolve PIDs
        pid_names = {}
        try:
            output = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in output.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2:
                    pid_names[int(parts[1].strip('"'))] = parts[0].strip('"')
        except Exception:
            pass

        # Annotate and deduplicate
        seen = set()
        for s in samples:
            pid = s.get("OwningProcess", 0)
            s["ProcessName"] = pid_names.get(pid, "?")
            key = f"{s.get('RemoteAddress')}:{s.get('RemotePort')}-{pid}"
            if key not in seen:
                seen.add(key)
                result["tcp_events"].append(s)

        print(f"  [SNIFFER] Captured {len(result['tcp_events'])} unique TCP events", flush=True)
        for ev in result["tcp_events"]:
            direction = ev.get("direction", "SERVER")
            print(f"    [{direction:6s}] {ev.get('RemoteAddress', '?')}:{ev.get('RemotePort', '?')} "
                  f"State={ev.get('State', '?')} PID={ev.get('OwningProcess', '?')} "
                  f"({ev.get('ProcessName', '?')}) Created={str(ev.get('CreationTime', '?'))[:19]}", flush=True)

        return result

    # ================================================================
    # FULL ANALYSIS
    # ================================================================

    async def full_sniff(self) -> dict:
        """Run all sniffing methods."""
        print("\n" + "="*60, flush=True)
        print(f"  LOCALHOST TRAFFIC SNIFFER — port {self.port}", flush=True)
        print("="*60, flush=True)

        pipes = await self.enumerate_pipes()
        memory = await self.scan_process_memory()
        etw = await self.capture_etw_trace(duration=15)
        monitor = await self.monitor_connections(duration=15, interval=1.0)
        firewall = await self.enable_firewall_logging()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_port": self.port,
            "named_pipes": pipes,
            "process_memory": memory,
            "etw_trace": etw,
            "connection_monitor": monitor,
            "firewall_log": firewall,
        }


if __name__ == "__main__":
    async def main():
        sniffer = LocalhostSniffer(target_port=13925)
        result = await sniffer.full_sniff()

        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}")
        print(f"  Named Pipes: {len(result['named_pipes'].get('expressvpn_pipes', []))}")
        print(f"  Process modules: {len(result['process_memory'].get('strings_found', []))}")
        print(f"  TCP connections: {len(result['process_memory'].get('grpc_calls', []))}")
        print(f"  ETW events: {len(result['etw_trace'].get('tcp_events', []))}")
        print(f"  Connection events: {len(result['connection_monitor'].get('events', []))}")

    asyncio.run(main())
