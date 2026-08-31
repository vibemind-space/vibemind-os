"""
MCP Server — JSON-RPC 2.0 Model Context Protocol server for The Brain.

Exposes brain state, bridge states, modulation factors, scenarios, and
Minibook status as MCP resources and tools. Other agents (including
Minibook participants) can query The Brain's cognitive state via MCP.

Runs as a lightweight HTTP server with JSON-RPC 2.0 endpoints.

Config in default.yaml:
    mcp_server:
        enabled: true
        host: "127.0.0.1"
        port: 8900

See: docs/plans/cached-brewing-swan.md (Phase 10, Tasks 10-11)
"""

import json
import logging
import time
import threading
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPResource:
    """An MCP resource (readable state)."""
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"


@dataclass
class MCPTool:
    """An MCP tool (callable function)."""
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPServer:
    """JSON-RPC 2.0 MCP Server for brain state exposure.

    Supports:
      - resources/list: List available brain state resources
      - resources/read: Read a specific resource
      - tools/list: List available tools
      - tools/call: Invoke a tool

    Parameters
    ----------
    brain_state_fn : callable
        Function returning current brain state dict.
    bridge_state_fn : callable
        Function(name) returning bridge state dict.
    scenario_fn : callable
        Function(name, ticks) running a scenario and returning results.
    minibook_status_fn : callable
        Function returning Minibook client status.
    host : str
        Server bind address.
    port : int
        Server bind port.
    """

    def __init__(
        self,
        brain_state_fn: Optional[Callable] = None,
        bridge_state_fn: Optional[Callable] = None,
        scenario_fn: Optional[Callable] = None,
        minibook_status_fn: Optional[Callable] = None,
        host: str = "127.0.0.1",
        port: int = 8900,
    ):
        self._brain_state_fn = brain_state_fn or (lambda: {})
        self._bridge_state_fn = bridge_state_fn or (lambda name: {})
        self._scenario_fn = scenario_fn
        self._minibook_status_fn = minibook_status_fn or (lambda: {"online": False})
        self._host = host
        self._port = port
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._request_count = 0
        self._start_time = 0.0

        # Register resources and tools
        self._resources = self._build_resources()
        self._tools = self._build_tools()
        self._tool_handlers: Dict[str, Callable] = self._build_tool_handlers()

    # ------------------------------------------------------------------
    # Resource and Tool Definitions
    # ------------------------------------------------------------------

    def _build_resources(self) -> List[MCPResource]:
        return [
            MCPResource(
                uri="brain://state",
                name="Brain State",
                description="Current cognitive state: consciousness, modulation factors, tick count",
            ),
            MCPResource(
                uri="brain://bridges",
                name="Bridge States",
                description="All 10 bridge states (neuromod, cortex, limbic, etc.)",
            ),
            MCPResource(
                uri="brain://modulation",
                name="Modulation Context",
                description="4 composite modulation factors + consciousness level",
            ),
            MCPResource(
                uri="brain://consciousness",
                name="Consciousness State",
                description="Consciousness loop: level, integration, DMN gating, Ring5 gain",
            ),
            MCPResource(
                uri="brain://minibook",
                name="Minibook Status",
                description="Minibook client connectivity and notification state",
            ),
        ]

    def _build_tools(self) -> List[MCPTool]:
        tools = [
            MCPTool(
                name="think",
                description="Send a prompt to The Brain for cognitive processing",
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Text prompt for The Brain to process",
                        }
                    },
                    "required": ["prompt"],
                },
            ),
            MCPTool(
                name="get_bridge_state",
                description="Get the current state of a specific bridge",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Bridge name (neuromod, cortex, limbic, sleep_wake, motor, defense, memory, integration, visceral, social)",
                        }
                    },
                    "required": ["name"],
                },
            ),
            MCPTool(
                name="get_minibook_status",
                description="Get Minibook client connection status",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]
        if self._scenario_fn is not None:
            tools.append(MCPTool(
                name="run_scenario",
                description="Run a named brain scenario (e.g., threat_while_sleepy, creative_exploration)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Scenario name",
                        },
                        "ticks": {
                            "type": "integer",
                            "description": "Number of ticks to simulate (default 30)",
                            "default": 30,
                        },
                    },
                    "required": ["name"],
                },
            ))
        return tools

    def _build_tool_handlers(self) -> Dict[str, Callable]:
        handlers = {
            "think": self._handle_think,
            "get_bridge_state": self._handle_get_bridge_state,
            "get_minibook_status": self._handle_get_minibook_status,
        }
        if self._scenario_fn is not None:
            handlers["run_scenario"] = self._handle_run_scenario
        return handlers

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 Request Handling
    # ------------------------------------------------------------------

    def handle_request(self, raw_request: str) -> str:
        """Process a JSON-RPC 2.0 request string, return response string."""
        self._request_count += 1
        try:
            request = json.loads(raw_request)
        except json.JSONDecodeError:
            return self._error_response(None, -32700, "Parse error")

        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "resources/list":
            return self._success_response(req_id, {
                "resources": [asdict(r) for r in self._resources]
            })

        elif method == "resources/read":
            uri = params.get("uri", "")
            return self._handle_resource_read(req_id, uri)

        elif method == "tools/list":
            return self._success_response(req_id, {
                "tools": [asdict(t) for t in self._tools]
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return self._handle_tool_call(req_id, tool_name, arguments)

        elif method == "ping":
            return self._success_response(req_id, {
                "status": "ok",
                "uptime": time.time() - self._start_time if self._start_time else 0,
                "requests_served": self._request_count,
            })

        else:
            return self._error_response(req_id, -32601, f"Method not found: {method}")

    def _handle_resource_read(self, req_id, uri: str) -> str:
        """Read a brain state resource by URI."""
        try:
            if uri == "brain://state":
                data = self._brain_state_fn()
            elif uri == "brain://bridges":
                data = {}
                for name in ["neuromod", "cortex", "limbic", "sleep_wake",
                             "motor", "defense", "memory", "integration",
                             "visceral", "social"]:
                    data[name] = self._bridge_state_fn(name)
            elif uri == "brain://modulation":
                state = self._brain_state_fn()
                data = {
                    k: state.get(k) for k in [
                        "attention_gain", "precision_boost",
                        "ffn_throughput", "threshold_mod",
                        "consciousness_level",
                    ] if k in state
                }
            elif uri == "brain://consciousness":
                state = self._brain_state_fn()
                data = state.get("consciousness", {})
            elif uri == "brain://minibook":
                data = self._minibook_status_fn()
            else:
                return self._error_response(req_id, -32602, f"Unknown resource: {uri}")

            return self._success_response(req_id, {
                "contents": [{"uri": uri, "text": json.dumps(data, default=str)}]
            })
        except Exception as e:
            return self._error_response(req_id, -32603, str(e))

    def _handle_tool_call(self, req_id, tool_name: str, arguments: Dict) -> str:
        """Invoke a tool by name."""
        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return self._error_response(req_id, -32602, f"Unknown tool: {tool_name}")

        try:
            result = handler(arguments)
            return self._success_response(req_id, {
                "content": [{"type": "text", "text": json.dumps(result, default=str)}]
            })
        except Exception as e:
            return self._error_response(req_id, -32603, str(e))

    # ------------------------------------------------------------------
    # Tool Handlers
    # ------------------------------------------------------------------

    def _handle_think(self, args: Dict) -> Dict:
        """Process a think request (stub — needs agent_loop integration)."""
        prompt = args.get("prompt", "")
        return {
            "status": "received",
            "prompt": prompt,
            "note": "Think tool requires agent_loop integration for live processing",
        }

    def _handle_get_bridge_state(self, args: Dict) -> Dict:
        """Get a specific bridge state."""
        name = args.get("name", "")
        return self._bridge_state_fn(name)

    def _handle_run_scenario(self, args: Dict) -> Dict:
        """Run a named scenario."""
        if self._scenario_fn is None:
            return {"error": "Scenario engine not available"}
        name = args.get("name", "")
        ticks = args.get("ticks", 30)
        return self._scenario_fn(name, ticks)

    def _handle_get_minibook_status(self, args: Dict) -> Dict:
        """Get Minibook connection status."""
        return self._minibook_status_fn()

    # ------------------------------------------------------------------
    # JSON-RPC Response Helpers
    # ------------------------------------------------------------------

    def _success_response(self, req_id, result: Any) -> str:
        return json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }, default=str)

    def _error_response(self, req_id, code: int, message: str) -> str:
        return json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        })

    # ------------------------------------------------------------------
    # HTTP Server (lightweight, for standalone use)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the MCP server in a background thread."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()

        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler

            server_ref = self

            class MCPHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode('utf-8')
                    response = server_ref.handle_request(body)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(response.encode('utf-8'))

                def log_message(self, format, *args):
                    pass  # Suppress default logging

            httpd = HTTPServer((self._host, self._port), MCPHandler)
            self._server_thread = threading.Thread(
                target=httpd.serve_forever, daemon=True
            )
            self._server_thread.start()
            logger.info("MCP Server started on %s:%d", self._host, self._port)
        except Exception as e:
            self._running = False
            logger.error("MCP Server failed to start: %s", e)

    def stop(self) -> None:
        """Stop the MCP server."""
        self._running = False
        logger.info("MCP Server stopped")

    def get_stats(self) -> Dict:
        """Get server statistics."""
        return {
            "running": self._running,
            "host": self._host,
            "port": self._port,
            "requests_served": self._request_count,
            "uptime": time.time() - self._start_time if self._start_time else 0,
            "resources": len(self._resources),
            "tools": len(self._tools),
        }
