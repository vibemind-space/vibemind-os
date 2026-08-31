"""
ExpressVPN gRPC Localhost Sniffer
===================================
Intercepts and logs all gRPC communication between:
  - ExpressVPN.BrowserHelper.exe
  - ExpressVPN.AppService.exe (localhost:13925)

Methods:
1. Port discovery — find the actual gRPC port
2. TCP proxy — sit between BrowserHelper and AppService
3. Raw packet capture — log all data flowing through
4. Proto decode — attempt to decode protobuf messages

This is YOUR localhost traffic on YOUR machine — fully legal.
"""

import asyncio
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


class GRPCSniffer:
    """Sniff gRPC traffic between ExpressVPN components on localhost."""

    def __init__(self):
        self.captured_messages = []
        self.port = None
        self.running = False

    # ================================================================
    # 1. DISCOVER — Find ExpressVPN's gRPC port
    # ================================================================

    async def discover_port(self) -> int:
        """Find the actual gRPC port ExpressVPN uses."""
        print("  [SNIFF] Discovering ExpressVPN gRPC port...", flush=True)

        # Method 1: Read from config file
        port_file = Path(os.environ.get("PROGRAMDATA", "")) / "ExpressVPN" / "Ports" / "ExpressVPN.AppService.port.json"
        if port_file.exists():
            try:
                data = json.loads(port_file.read_text())
                port = data.get("Port")
                if port:
                    print(f"  [SNIFF] Found in config: localhost:{port}", flush=True)
                    self.port = port
                    return port
            except Exception:
                pass

        # Method 2: Find listening ports of ExpressVPN processes
        try:
            output = subprocess.check_output(
                ["netstat", "-a", "-n", "-o", "-p", "TCP"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")

            # Get ExpressVPN PIDs
            pids = set()
            try:
                tasklist = subprocess.check_output(
                    ["tasklist", "/fi", "IMAGENAME eq ExpressVPN.AppService.exe", "/fo", "csv", "/nh"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode()
                for line in tasklist.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        pid = parts[1].strip('"')
                        if pid.isdigit():
                            pids.add(pid)
            except Exception:
                pass

            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in line:
                    pid = parts[-1]
                    local = parts[1]
                    if pid in pids and "127.0.0.1" in local:
                        port = int(local.split(":")[-1])
                        print(f"  [SNIFF] Found via netstat: localhost:{port} (PID {pid})", flush=True)
                        self.port = port
                        return port
        except Exception:
            pass

        print("  [SNIFF] Could not find gRPC port", flush=True)
        return 0

    # ================================================================
    # 2. PROBE — Connect and see what the gRPC service exposes
    # ================================================================

    async def probe_service(self) -> dict:
        """Connect to the gRPC port and probe what services are available."""
        if not self.port:
            await self.discover_port()

        if not self.port:
            return {"error": "Could not find gRPC port"}

        print(f"  [SNIFF] Probing gRPC service on localhost:{self.port}...", flush=True)
        result = {
            "port": self.port,
            "connectable": False,
            "http2": False,
            "services": [],
            "raw_response": "",
        }

        # Try HTTP/2 connection (gRPC uses HTTP/2)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.port),
                timeout=5.0,
            )
            result["connectable"] = True
            print(f"  [SNIFF] Connected to localhost:{self.port}", flush=True)

            # Send HTTP/2 connection preface
            h2_preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
            # SETTINGS frame (empty)
            settings_frame = struct.pack(">I", 0)[1:]  # length = 0 (3 bytes)
            settings_frame += struct.pack("B", 0x04)     # type = SETTINGS
            settings_frame += struct.pack("B", 0x00)     # flags
            settings_frame += struct.pack(">I", 0)       # stream id = 0

            writer.write(h2_preface + settings_frame)
            await writer.drain()

            # Read response
            try:
                response = await asyncio.wait_for(reader.read(4096), timeout=3.0)
                result["raw_response"] = response.hex()[:200]
                result["http2"] = len(response) > 0
                print(f"  [SNIFF] Got {len(response)} bytes response", flush=True)

                # Parse response for frame types
                if len(response) >= 9:
                    frame_len = struct.unpack(">I", b'\x00' + response[:3])[0]
                    frame_type = response[3]
                    frame_types = {0: "DATA", 1: "HEADERS", 2: "PRIORITY", 3: "RST_STREAM",
                                   4: "SETTINGS", 5: "PUSH_PROMISE", 6: "PING", 7: "GOAWAY",
                                   8: "WINDOW_UPDATE", 9: "CONTINUATION"}
                    result["first_frame"] = {
                        "length": frame_len,
                        "type": frame_types.get(frame_type, f"UNKNOWN({frame_type})"),
                        "type_id": frame_type,
                    }
                    print(f"  [SNIFF] First frame: {result['first_frame']}", flush=True)

            except asyncio.TimeoutError:
                print(f"  [SNIFF] No response (server may require TLS)", flush=True)
                result["note"] = "Server did not respond — may require mTLS or specific client cert"

            writer.close()
            await writer.wait_closed()

        except ConnectionRefusedError:
            print(f"  [SNIFF] Connection refused on port {self.port}", flush=True)
            result["note"] = "Connection refused — port may have changed"
        except Exception as e:
            print(f"  [SNIFF] Connection error: {e}", flush=True)
            result["error"] = str(e)

        # Try gRPC reflection (if available)
        try:
            import grpc
            channel = grpc.insecure_channel(f"127.0.0.1:{self.port}")
            try:
                from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
                stub = reflection_pb2_grpc.ServerReflectionStub(channel)
                # List services
                request = reflection_pb2.ServerReflectionRequest(list_services="")
                responses = stub.ServerReflectionInfo(iter([request]))
                for resp in responses:
                    if resp.HasField("list_services_response"):
                        for svc in resp.list_services_response.service:
                            result["services"].append(svc.name)
                            print(f"  [SNIFF] gRPC service: {svc.name}", flush=True)
            except ImportError:
                result["note_grpc"] = "grpc_reflection not installed — install with: pip install grpcio-reflection"
            except Exception as e:
                result["note_grpc"] = f"gRPC reflection failed: {e}"
            channel.close()
        except ImportError:
            result["note_grpc"] = "grpcio not installed — install with: pip install grpcio"
        except Exception as e:
            result["note_grpc"] = f"gRPC connection failed: {e}"

        return result

    # ================================================================
    # 3. MONITOR — Watch all connections to/from the gRPC port
    # ================================================================

    async def monitor_traffic(self, duration: int = 30) -> dict:
        """Monitor all TCP traffic to/from the gRPC port."""
        if not self.port:
            await self.discover_port()

        if not self.port:
            return {"error": "Could not find gRPC port"}

        print(f"\n  [SNIFF] Monitoring traffic on port {self.port} for {duration}s...", flush=True)
        result = {
            "port": self.port,
            "duration": duration,
            "snapshots": [],
            "unique_clients": set(),
            "total_connections": 0,
            "data_volume": {"sent": 0, "recv": 0},
        }

        start = time.time()
        while time.time() - start < duration:
            try:
                output = subprocess.check_output(
                    ["netstat", "-n", "-o", "-p", "TCP"],
                    timeout=5, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")

                connections = []
                for line in output.strip().split("\n"):
                    parts = line.split()
                    if len(parts) >= 5 and parts[0] == "TCP":
                        local = parts[1]
                        remote = parts[2]

                        # Connections TO our port (clients calling AppService)
                        if f":{self.port}" in local and "127.0.0.1" in local:
                            connections.append({
                                "direction": "INBOUND",
                                "client": remote,
                                "state": parts[3],
                                "pid": parts[4],
                            })
                            result["unique_clients"].add(remote)

                        # Connections FROM our port (AppService calling out)
                        elif f":{self.port}" in remote:
                            connections.append({
                                "direction": "OUTBOUND",
                                "target": remote,
                                "state": parts[3],
                                "pid": parts[4],
                            })

                if connections:
                    result["snapshots"].append({
                        "time": round(time.time() - start, 1),
                        "connections": connections,
                    })
                    result["total_connections"] = max(result["total_connections"], len(connections))

                elapsed = time.time() - start
                print(f"  [SNIFF]   {elapsed:.0f}s: {len(connections)} active connections", flush=True)

            except Exception:
                pass

            await asyncio.sleep(3)

        result["unique_clients"] = list(result["unique_clients"])

        # Resolve PIDs to process names
        pid_names = {}
        try:
            output = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                timeout=10, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            for line in output.strip().split("\n"):
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip('"')
                    pid = parts[1].strip('"')
                    pid_names[pid] = name
        except Exception:
            pass

        # Annotate connections with process names
        client_processes = {}
        for snapshot in result["snapshots"]:
            for conn in snapshot["connections"]:
                pid = conn.get("pid", "")
                if pid in pid_names:
                    conn["process"] = pid_names[pid]
                    if conn["direction"] == "INBOUND":
                        client_processes[pid] = pid_names[pid]

        result["client_processes"] = client_processes

        print(f"\n  [SNIFF] Monitoring complete:", flush=True)
        print(f"    Total connections: {result['total_connections']}", flush=True)
        print(f"    Unique clients: {len(result['unique_clients'])}", flush=True)
        print(f"    Client processes: {result['client_processes']}", flush=True)

        return result

    # ================================================================
    # 4. INTERCEPT — TCP proxy to log actual data
    # ================================================================

    async def intercept(self, listen_port: int = 13900, duration: int = 60) -> dict:
        """
        Start a TCP proxy that sits between BrowserHelper and AppService.
        Logs all data passing through in both directions.

        WARNING: This may break the VPN connection temporarily.
        """
        if not self.port:
            await self.discover_port()

        if not self.port:
            return {"error": "Could not find gRPC port"}

        target_port = self.port
        print(f"\n  [SNIFF] Starting TCP interceptor:", flush=True)
        print(f"    Listen: localhost:{listen_port}", flush=True)
        print(f"    Forward to: localhost:{target_port}", flush=True)
        print(f"    Duration: {duration}s", flush=True)

        result = {
            "listen_port": listen_port,
            "target_port": target_port,
            "intercepted_messages": [],
            "total_bytes_client": 0,
            "total_bytes_server": 0,
        }

        async def handle_client(client_reader, client_writer):
            """Proxy a single connection."""
            try:
                server_reader, server_writer = await asyncio.open_connection(
                    "127.0.0.1", target_port)

                async def forward(src, dst, label):
                    try:
                        while True:
                            data = await asyncio.wait_for(src.read(8192), timeout=5.0)
                            if not data:
                                break

                            msg = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "direction": label,
                                "size": len(data),
                                "hex_preview": data[:100].hex(),
                                "ascii_preview": "".join(
                                    chr(b) if 32 <= b < 127 else "."
                                    for b in data[:200]
                                ),
                            }

                            # Try to find gRPC method names in the data
                            methods = re.findall(rb'/[a-zA-Z0-9_.]+/[A-Za-z]+', data)
                            if methods:
                                msg["grpc_methods"] = [m.decode() for m in methods]

                            # Look for protobuf strings
                            strings = []
                            current = []
                            for byte in data:
                                if 32 <= byte < 127:
                                    current.append(chr(byte))
                                else:
                                    if len(current) >= 4:
                                        strings.append("".join(current))
                                    current = []
                            if strings:
                                msg["strings"] = strings[:20]

                            result["intercepted_messages"].append(msg)

                            if label == "CLIENT->SERVER":
                                result["total_bytes_client"] += len(data)
                            else:
                                result["total_bytes_server"] += len(data)

                            print(f"  [SNIFF] {label}: {len(data)} bytes"
                                  f"{' methods=' + str(msg.get('grpc_methods', '')) if msg.get('grpc_methods') else ''}", flush=True)

                            dst.write(data)
                            await dst.drain()
                    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
                        pass
                    finally:
                        try:
                            dst.close()
                        except Exception:
                            pass

                await asyncio.gather(
                    forward(client_reader, server_writer, "CLIENT->SERVER"),
                    forward(server_reader, client_writer, "SERVER->CLIENT"),
                )

            except Exception as e:
                print(f"  [SNIFF] Proxy error: {e}", flush=True)

        try:
            server = await asyncio.start_server(handle_client, "127.0.0.1", listen_port)
            print(f"  [SNIFF] Interceptor running. Point BrowserHelper to port {listen_port}", flush=True)
            print(f"  [SNIFF] Waiting for connections...", flush=True)

            # Run for duration
            await asyncio.sleep(duration)

            server.close()
            await server.wait_closed()

        except OSError as e:
            result["error"] = f"Could not start interceptor: {e}"
            print(f"  [SNIFF] Error: {e}", flush=True)

        print(f"\n  [SNIFF] Interceptor stopped:", flush=True)
        print(f"    Messages: {len(result['intercepted_messages'])}", flush=True)
        print(f"    Client bytes: {result['total_bytes_client']}", flush=True)
        print(f"    Server bytes: {result['total_bytes_server']}", flush=True)

        return result

    # ================================================================
    # 5. FULL ANALYSIS — Run everything
    # ================================================================

    async def full_analysis(self) -> dict:
        """Run port discovery, service probe, and traffic monitoring."""
        print("\n" + "="*60, flush=True)
        print("  EXPRESSVPN gRPC SNIFFER", flush=True)
        print("="*60, flush=True)

        port = await self.discover_port()
        probe = await self.probe_service()
        monitor = await self.monitor_traffic(duration=20)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "port": port,
            "probe": probe,
            "monitor": monitor,
        }


# ================================================================
# CLI
# ================================================================

if __name__ == "__main__":
    async def main():
        sniffer = GRPCSniffer()

        if len(sys.argv) > 1 and sys.argv[1] == "intercept":
            # Active interception mode
            result = await sniffer.discover_port()
            if result:
                intercept_result = await sniffer.intercept(duration=60)
                print(f"\n  Intercepted {len(intercept_result.get('intercepted_messages', []))} messages")
                for msg in intercept_result.get("intercepted_messages", [])[:20]:
                    print(f"    [{msg['direction']:15s}] {msg['size']:5d} bytes"
                          f"  {msg.get('grpc_methods', [''])[0] if msg.get('grpc_methods') else ''}")
                    if msg.get("strings"):
                        print(f"      Strings: {msg['strings'][:5]}")
        else:
            # Passive analysis mode
            result = await sniffer.full_analysis()

            print(f"\n{'='*60}")
            print(f"  gRPC PORT: {result['port']}")
            print(f"{'='*60}")

            probe = result["probe"]
            print(f"  Connectable: {probe.get('connectable')}")
            print(f"  HTTP/2: {probe.get('http2')}")
            if probe.get("first_frame"):
                print(f"  First frame: {probe['first_frame']}")
            if probe.get("services"):
                print(f"  Services: {probe['services']}")
            if probe.get("note"):
                print(f"  Note: {probe['note']}")

            monitor = result["monitor"]
            print(f"\n  Traffic ({monitor.get('duration', 0)}s):")
            print(f"    Max connections: {monitor.get('total_connections', 0)}")
            print(f"    Client processes: {monitor.get('client_processes', {})}")

    asyncio.run(main())
