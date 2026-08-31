"""
Named Pipe Sniffer — Read ExpressVpnService pipe traffic
==========================================================
Connects to \\.\pipe\ExpressVpnService and logs all data flowing through.
"""

import asyncio
import ctypes
import json
import struct
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

# Windows API constants
PIPE_ACCESS_DUPLEX = 0x00000003
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.windll.kernel32


class PipeSniffer:

    def __init__(self):
        self.captured = []

    async def try_read_pipe(self, pipe_name: str, duration: int = 30) -> dict:
        """Try to connect to and read from a named pipe."""
        result = {
            "pipe": pipe_name,
            "connected": False,
            "messages": [],
            "error": None,
        }

        print(f"  [PIPE] Connecting to {pipe_name}...", flush=True)

        try:
            # Try to open the pipe as a client
            handle = kernel32.CreateFileW(
                pipe_name,
                GENERIC_READ,  # Read only
                0,  # No sharing
                None,  # Default security
                OPEN_EXISTING,
                0,  # Normal attributes
                None,
            )

            if handle == INVALID_HANDLE_VALUE:
                err = ctypes.get_last_error()
                error_msg = f"CreateFile failed: error {err}"

                # Try common error codes
                if err == 5:
                    error_msg = "Access denied — need admin rights"
                elif err == 2:
                    error_msg = "Pipe not found"
                elif err == 231:
                    error_msg = "All pipe instances are busy — pipe is in use"

                result["error"] = error_msg
                print(f"  [PIPE] {error_msg}", flush=True)

                # If busy, try to peek instead
                if err == 231:
                    return await self.peek_pipe(pipe_name, duration)

                return result

            result["connected"] = True
            print(f"  [PIPE] Connected! Reading for {duration}s...", flush=True)

            # Read data
            buf = ctypes.create_string_buffer(8192)
            bytes_read = wintypes.DWORD(0)
            start = time.time()

            while time.time() - start < duration:
                success = kernel32.ReadFile(
                    handle,
                    buf,
                    8192,
                    ctypes.byref(bytes_read),
                    None,
                )

                if success and bytes_read.value > 0:
                    data = buf.raw[:bytes_read.value]
                    elapsed = round(time.time() - start, 1)

                    # Try to decode
                    text = ""
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        text = data.hex()

                    msg = {
                        "time": elapsed,
                        "size": bytes_read.value,
                        "hex": data.hex()[:200],
                        "text": text[:300],
                        "strings": self._extract_strings(data),
                    }
                    result["messages"].append(msg)
                    self.captured.append(msg)

                    safe = text[:100].encode("ascii", "replace").decode()
                    print(f"  [PIPE] {elapsed:5.1f}s: {bytes_read.value} bytes — {safe}", flush=True)

                else:
                    await asyncio.sleep(0.5)

            kernel32.CloseHandle(handle)

        except Exception as e:
            result["error"] = str(e)
            print(f"  [PIPE] Error: {e}", flush=True)

        print(f"  [PIPE] Done: {len(result['messages'])} messages", flush=True)
        return result

    async def peek_pipe(self, pipe_name: str, duration: int = 30) -> dict:
        """If pipe is busy, try PeekNamedPipe to see pending data."""
        result = {
            "pipe": pipe_name,
            "connected": False,
            "peek_results": [],
            "error": None,
        }

        print(f"  [PIPE] Pipe busy — trying PeekNamedPipe...", flush=True)

        try:
            handle = kernel32.CreateFileW(
                pipe_name,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING, 0, None,
            )

            if handle == INVALID_HANDLE_VALUE:
                # Try read-only
                handle = kernel32.CreateFileW(
                    pipe_name,
                    GENERIC_READ,
                    0, None, OPEN_EXISTING, 0, None,
                )

            if handle == INVALID_HANDLE_VALUE:
                result["error"] = f"Cannot open pipe (error {ctypes.get_last_error()})"
                return result

            buf = ctypes.create_string_buffer(4096)
            bytes_read = wintypes.DWORD(0)
            total_avail = wintypes.DWORD(0)
            msg_left = wintypes.DWORD(0)

            start = time.time()
            while time.time() - start < duration:
                success = kernel32.PeekNamedPipe(
                    handle,
                    buf, 4096,
                    ctypes.byref(bytes_read),
                    ctypes.byref(total_avail),
                    ctypes.byref(msg_left),
                )

                if success and total_avail.value > 0:
                    data = buf.raw[:bytes_read.value]
                    elapsed = round(time.time() - start, 1)
                    result["peek_results"].append({
                        "time": elapsed,
                        "available": total_avail.value,
                        "peeked": bytes_read.value,
                        "hex": data.hex()[:200],
                        "strings": self._extract_strings(data),
                    })
                    print(f"  [PIPE] {elapsed:.1f}s: {total_avail.value} bytes available", flush=True)

                await asyncio.sleep(1)

            kernel32.CloseHandle(handle)

        except Exception as e:
            result["error"] = str(e)

        return result

    async def monitor_pipe_activity(self, duration: int = 30) -> dict:
        """Monitor pipe creation/deletion to see communication patterns."""
        import subprocess

        result = {"snapshots": [], "activity": []}
        print(f"  [PIPE] Monitoring pipe activity for {duration}s...", flush=True)

        prev_pipes = set()
        start = time.time()

        while time.time() - start < duration:
            try:
                output = subprocess.check_output(
                    ["powershell", "-Command",
                     "[System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | "
                     "Where-Object { $_ -match 'express|vpn|kape|xvca|crashpad_.*WUGHO' } | "
                     "ForEach-Object { $_ }"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                current = set(line.strip() for line in output.strip().split("\n") if line.strip())

                new_pipes = current - prev_pipes
                gone_pipes = prev_pipes - current

                for p in new_pipes:
                    elapsed = round(time.time() - start, 1)
                    result["activity"].append({"time": elapsed, "event": "CREATED", "pipe": p})
                    print(f"  [PIPE] {elapsed:.1f}s: NEW {p}", flush=True)

                for p in gone_pipes:
                    elapsed = round(time.time() - start, 1)
                    result["activity"].append({"time": elapsed, "event": "CLOSED", "pipe": p})
                    print(f"  [PIPE] {elapsed:.1f}s: GONE {p}", flush=True)

                prev_pipes = current

            except Exception:
                pass

            await asyncio.sleep(2)

        return result

    def _extract_strings(self, data: bytes) -> list:
        strings = []
        current = []
        for b in data:
            if 32 <= b < 127:
                current.append(chr(b))
            else:
                if len(current) >= 4:
                    strings.append("".join(current))
                current = []
        if len(current) >= 4:
            strings.append("".join(current))
        return strings[:20]

    async def full_sniff(self) -> dict:
        """Run all pipe sniffing methods."""
        print("\n" + "="*60, flush=True)
        print("  NAMED PIPE SNIFFER — ExpressVPN", flush=True)
        print("="*60, flush=True)

        # 1. Try to read the main service pipe
        service = await self.try_read_pipe(r"\\.\pipe\ExpressVpnService", duration=15)

        # 2. Monitor pipe activity
        activity = await self.monitor_pipe_activity(duration=15)

        # 3. Try crashpad pipe
        crashpad = await self.try_read_pipe(r"\\.\pipe\crashpad_6148_VZNFITZUBGZZMDUE", duration=5)

        result = {
            "timestamp": datetime.now().isoformat(),
            "service_pipe": service,
            "activity": activity,
            "crashpad_pipe": crashpad,
            "total_captured": len(self.captured),
        }

        # Save captured data
        out = Path("expressvpn_pipe_captured.json")
        out.write_text(json.dumps(result, indent=2, ensure_ascii=True))
        print(f"\n  Saved to {out}", flush=True)

        return result


if __name__ == "__main__":
    async def main():
        sniffer = PipeSniffer()
        result = await sniffer.full_sniff()

        print(f"\n{'='*60}")
        print(f"  RESULTS")
        print(f"{'='*60}")
        print(f"  Service pipe: {result['service_pipe'].get('error', 'connected')}")
        print(f"  Messages captured: {result['total_captured']}")
        print(f"  Pipe activity events: {len(result['activity'].get('activity', []))}")

    asyncio.run(main())
