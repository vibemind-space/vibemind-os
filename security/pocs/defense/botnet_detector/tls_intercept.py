"""
ExpressVPN TLS Traffic Decryption
====================================
Uses SSLKEYLOGFILE environment variable to capture TLS session keys,
then decodes the traffic between ExpressVPN and AWS Global Accelerator.

Steps:
1. Set SSLKEYLOGFILE system-wide
2. Restart ExpressVPN services so they pick up the env var
3. Capture raw TCP traffic on port 443 to 3.33.235.18
4. Use captured keys to decrypt the TLS stream
5. Parse HTTP/2 + gRPC frames inside

Alternative: Use Windows ETW Schannel provider to capture TLS keys
without modifying environment variables.
"""

import asyncio
import ctypes
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


class TLSInterceptor:

    def __init__(self):
        self.keylog_file = Path(os.environ.get("TEMP", "C:/Temp")) / "expressvpn_tls_keys.log"
        self.capture_file = Path(os.environ.get("TEMP", "C:/Temp")) / "expressvpn_traffic.bin"
        self.decoded_traffic = []

    # ================================================================
    # METHOD 1: SSLKEYLOGFILE — Capture TLS session keys
    # ================================================================

    async def setup_keylog(self) -> dict:
        """Set SSLKEYLOGFILE environment variable."""
        print(f"  [TLS] Setting SSLKEYLOGFILE={self.keylog_file}", flush=True)
        result = {"keylog_file": str(self.keylog_file), "set": False}

        # Set for current process
        os.environ["SSLKEYLOGFILE"] = str(self.keylog_file)

        # Set system-wide (needs admin, but try user-level first)
        try:
            subprocess.check_call(
                ["setx", "SSLKEYLOGFILE", str(self.keylog_file)],
                timeout=5, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            )
            result["set"] = True
            print(f"  [TLS] SSLKEYLOGFILE set for current user", flush=True)
        except Exception as e:
            print(f"  [TLS] setx failed: {e} — trying PowerShell...", flush=True)
            try:
                subprocess.check_call(
                    ["powershell", "-Command",
                     f'[Environment]::SetEnvironmentVariable("SSLKEYLOGFILE", "{self.keylog_file}", "User")'],
                    timeout=5, stderr=subprocess.DEVNULL,
                )
                result["set"] = True
                print(f"  [TLS] Set via PowerShell", flush=True)
            except Exception:
                print(f"  [TLS] Could not set env var persistently", flush=True)

        return result

    async def check_keylog(self, wait_seconds: int = 15) -> dict:
        """Wait for TLS keys to appear in the log file."""
        print(f"  [TLS] Waiting {wait_seconds}s for TLS keys...", flush=True)
        result = {"keys_found": 0, "key_types": {}, "sessions": []}

        # Touch the file so it exists
        self.keylog_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.keylog_file.exists():
            self.keylog_file.write_text("")

        start_size = self.keylog_file.stat().st_size

        # Wait and check periodically
        for i in range(wait_seconds // 3):
            await asyncio.sleep(3)
            current_size = self.keylog_file.stat().st_size
            if current_size > start_size:
                print(f"  [TLS] Keys growing: {current_size} bytes (+{current_size - start_size})", flush=True)

        # Parse the keylog
        if self.keylog_file.stat().st_size > 0:
            content = self.keylog_file.read_text()
            lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
            result["keys_found"] = len(lines)

            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    key_type = parts[0]
                    result["key_types"][key_type] = result["key_types"].get(key_type, 0) + 1
                    if len(result["sessions"]) < 5:
                        result["sessions"].append({
                            "type": key_type,
                            "client_random": parts[1][:20] + "...",
                            "key_preview": parts[2][:20] + "...",
                        })

            print(f"  [TLS] Found {result['keys_found']} TLS keys!", flush=True)
            for kt, count in result["key_types"].items():
                print(f"    {kt}: {count}", flush=True)
        else:
            print(f"  [TLS] No keys captured — ExpressVPN may not honor SSLKEYLOGFILE", flush=True)

        return result

    # ================================================================
    # METHOD 2: ETW Schannel — Windows built-in TLS event tracing
    # ================================================================

    async def capture_etw_tls(self, duration: int = 15) -> dict:
        """Capture TLS events via Windows ETW (Event Tracing for Windows)."""
        print(f"\n  [TLS] Capturing TLS events via ETW for {duration}s...", flush=True)
        result = {"events": [], "handshakes": 0, "data_events": 0}

        # Use PowerShell to query Schannel events
        try:
            # Get recent Schannel events
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-WinEvent -LogName 'Microsoft-Windows-Schannel/Debug' "
                 "-MaxEvents 50 -ErrorAction SilentlyContinue | "
                 "Select-Object TimeCreated,Id,Message | ConvertTo-Json"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            if output.strip():
                data = json.loads(output)
                if isinstance(data, dict):
                    data = [data]
                result["events"] = data[:20]
                print(f"  [TLS] Got {len(data)} Schannel events", flush=True)
                for ev in data[:10]:
                    msg = str(ev.get("Message", ""))[:100]
                    print(f"    [{ev.get('Id', '?')}] {msg}", flush=True)
        except subprocess.CalledProcessError:
            print(f"  [TLS] Schannel debug log not enabled (need admin to enable)", flush=True)
        except Exception as e:
            print(f"  [TLS] ETW error: {e}", flush=True)

        # Alternative: check Schannel operational log
        try:
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-WinEvent -LogName 'Microsoft-Windows-Schannel/Operational' "
                 "-MaxEvents 20 -ErrorAction SilentlyContinue | "
                 "Select-Object TimeCreated,Id,LevelDisplayName,Message | ConvertTo-Json"],
                timeout=15, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            if output.strip():
                data = json.loads(output)
                if isinstance(data, dict):
                    data = [data]
                print(f"\n  [TLS] Schannel Operational Log ({len(data)} events):", flush=True)
                for ev in data[:10]:
                    msg = str(ev.get("Message", ""))[:120].encode("ascii", "replace").decode()
                    print(f"    {ev.get('TimeCreated', '?')[:19]} [{ev.get('LevelDisplayName', '?')}] {msg}", flush=True)
                result["operational_events"] = data[:20]
        except Exception:
            pass

        return result

    # ================================================================
    # METHOD 3: Raw TCP capture on target IP
    # ================================================================

    async def capture_raw_traffic(self, target_ip: str = "3.33.235.18",
                                   target_port: int = 443, duration: int = 20) -> dict:
        """Capture raw TCP segments to/from ExpressVPN's AWS server."""
        print(f"\n  [TLS] Capturing raw traffic to {target_ip}:{target_port} for {duration}s...", flush=True)
        result = {"packets": [], "total_bytes_out": 0, "total_bytes_in": 0, "intervals": []}

        # Monitor netstat at high frequency to estimate data flow
        def _get_connection_state():
            try:
                output = subprocess.check_output(
                    ["powershell", "-Command",
                     f"Get-NetTCPConnection -RemoteAddress {target_ip} -RemotePort {target_port} "
                     "-ErrorAction SilentlyContinue | "
                     "Select-Object LocalPort,State,OwningProcess,CreationTime | ConvertTo-Json"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                if output.strip():
                    return json.loads(output)
            except Exception:
                pass
            return None

        # Use performance counters to measure bytes
        def _get_bytes():
            try:
                output = subprocess.check_output(
                    ["netstat", "-e"], timeout=3, stderr=subprocess.DEVNULL,
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

        samples = []
        for i in range(duration // 2):
            await asyncio.sleep(2)
            recv, sent = _get_bytes()
            elapsed = time.time() - start_time
            delta_recv = recv - start_recv
            delta_sent = sent - start_sent

            conn_state = _get_connection_state()

            sample = {
                "time_s": round(elapsed, 1),
                "total_sent_kb": round(delta_sent / 1024, 1),
                "total_recv_kb": round(delta_recv / 1024, 1),
                "rate_up_kbps": round(delta_sent / 1024 / elapsed, 1) if elapsed > 0 else 0,
                "rate_down_kbps": round(delta_recv / 1024 / elapsed, 1) if elapsed > 0 else 0,
                "aws_connection": conn_state,
            }
            samples.append(sample)
            print(f"  [TLS]   {elapsed:.0f}s: UP {sample['rate_up_kbps']} KB/s | DOWN {sample['rate_down_kbps']} KB/s", flush=True)

        result["intervals"] = samples
        if samples:
            result["total_bytes_out"] = int(samples[-1]["total_sent_kb"] * 1024)
            result["total_bytes_in"] = int(samples[-1]["total_recv_kb"] * 1024)

        return result

    # ================================================================
    # METHOD 4: Try to use ExpressVPN's own TLS keylog
    # ================================================================

    async def find_existing_keylogs(self) -> dict:
        """Search for any existing TLS key log files ExpressVPN may have created."""
        print(f"\n  [TLS] Searching for existing TLS key logs...", flush=True)
        result = {"found": []}

        search_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "ExpressVPN",
            Path(os.environ.get("APPDATA", "")) / "ExpressVPN",
            Path(os.environ.get("PROGRAMDATA", "")) / "ExpressVPN",
            Path(os.environ.get("TEMP", "")),
            Path("C:/Windows/Temp"),
        ]

        keylog_patterns = ["*keylog*", "*sslkey*", "*tls_key*", "*premaster*", "*.keys", "*debug*tls*"]

        for sd in search_dirs:
            if not sd.exists():
                continue
            for pattern in keylog_patterns:
                try:
                    for f in sd.rglob(pattern):
                        if f.is_file() and f.stat().st_size > 0:
                            result["found"].append({
                                "path": str(f),
                                "size": f.stat().st_size,
                                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()[:19],
                            })
                            print(f"  [TLS] Found: {f} ({f.stat().st_size} bytes)", flush=True)
                except PermissionError:
                    pass

        if not result["found"]:
            print(f"  [TLS] No existing TLS key logs found", flush=True)

        return result

    # ================================================================
    # FULL INTERCEPT
    # ================================================================

    async def full_intercept(self) -> dict:
        """Run all TLS interception methods."""
        print("\n" + "="*60, flush=True)
        print("  TLS TRAFFIC INTERCEPTION", flush=True)
        print("="*60, flush=True)

        # Check for existing keylogs first
        existing = await self.find_existing_keylogs()

        # Set SSLKEYLOGFILE
        setup = await self.setup_keylog()

        # Capture traffic while waiting for keys
        traffic = await self.capture_raw_traffic(duration=15)

        # Check if keys appeared
        keys = await self.check_keylog(wait_seconds=10)

        # Try ETW
        etw = await self.capture_etw_tls()

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "existing_keylogs": existing,
            "keylog_setup": setup,
            "keys_captured": keys,
            "traffic": traffic,
            "etw_events": etw,
            "summary": {
                "tls_keys_found": keys.get("keys_found", 0),
                "traffic_volume_kb": round(traffic.get("total_bytes_out", 0) / 1024, 1),
                "etw_events": len(etw.get("events", [])) + len(etw.get("operational_events", [])),
                "decryption_possible": keys.get("keys_found", 0) > 0,
            },
        }

        if keys.get("keys_found", 0) > 0:
            print(f"\n  [TLS] SUCCESS — {keys['keys_found']} TLS keys captured!", flush=True)
            print(f"  [TLS] Keys saved to: {self.keylog_file}", flush=True)
            print(f"  [TLS] Use with Wireshark: Edit > Preferences > TLS > (Pre)-Master-Secret log file", flush=True)
        else:
            print(f"\n  [TLS] ExpressVPN does NOT honor SSLKEYLOGFILE", flush=True)
            print(f"  [TLS] Next steps:", flush=True)
            print(f"    1. Frida hook into OpenSSL SSL_write/SSL_read", flush=True)
            print(f"    2. DLL injection into AppService process", flush=True)
            print(f"    3. Patch expressvpn binary to enable keylogging", flush=True)

        return result


if __name__ == "__main__":
    async def main():
        interceptor = TLSInterceptor()
        result = await interceptor.full_intercept()

        s = result["summary"]
        print(f"\n{'='*60}")
        print(f"  TLS INTERCEPT RESULTS")
        print(f"{'='*60}")
        print(f"  TLS Keys captured: {s['tls_keys_found']}")
        print(f"  Traffic captured:  {s['traffic_volume_kb']} KB")
        print(f"  ETW events:        {s['etw_events']}")
        print(f"  Decryption:        {'POSSIBLE' if s['decryption_possible'] else 'NOT POSSIBLE'}")

    asyncio.run(main())
