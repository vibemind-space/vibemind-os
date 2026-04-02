# -*- coding: utf-8 -*-
"""
Shared event broadcasting server for all MCP plugins.
Extracted from playwright/event_task.py for reuse across all MCP server plugins.

Provides:
- EventServer: Thread-safe event broadcasting with SSE support
- UIHandler: Generic HTTP handler for UI endpoints
- start_ui_server: Helper to start UI server with dynamic port assignment

Clear comments for easy debugging and maintenance.
"""
import base64
import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

# NO imports from constants to avoid name collision with plugin-level constants.py files
# Default values defined inline instead


@dataclass
class Event:
    """Event data structure for broadcasting."""
    type: str
    value: Any
    seq: int = 0


class EventServer:
    """Minimal event broadcast server with SSE endpoint and image cache.

    Thread-safe event broadcasting for UI updates with:
    - Server-Sent Events (SSE) streaming
    - JSON polling fallback (/events.json?since=N)
    - Event buffering for late subscribers
    - Image preview caching
    - Session-based conversation logging

    Compatible with legacy agent expectations by exposing simple state fields.
    """

    def __init__(self, session_id: Optional[str] = None, tool_name: Optional[str] = None):
        # Session identification (for Society of Mind agents)
        self.session_id = session_id
        self.tool_name = tool_name

        # Last N events for late subscribers
        self._buffer: List[Event] = []
        self._max_buffer = 200
        self._clients: List = []  # list of wfile objects
        self._latest_preview_png_b64: Optional[str] = None
        self._lock = threading.Lock()
        # Global increasing sequence for events
        self._seq: int = 0
        # --- Compatibility state (used by legacy agent code) ---
        self.browser_open_last_state: Optional[bool] = None
        self.screenshot_skip_last_log_ts: float = 0.0
        self.last_image_ts: float = 0.0
        self.last_source: Optional[str] = None
        self.last_open_signal_ts: float = 0.0
        self._port: Optional[int] = None  # Will be set when server starts

        # Session logging setup
        self._session_logger: Optional[Any] = None
        if session_id and tool_name:
            self._setup_session_logger()

    def _setup_session_logger(self) -> None:
        """Setup session-based file logger for conversation logging."""
        try:
            import logging
            import sys
            import os
            from datetime import datetime

            # Find gui/config.py relative to shared/ directory
            shared_dir = os.path.dirname(__file__)
            plugins_dir = os.path.dirname(shared_dir)  # ../servers
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(plugins_dir)))  # project root

            # Try to import setup_session_logging from gui.config
            sys.path.insert(0, os.path.join(root_dir, 'src', 'gui'))
            from config import setup_session_logging

            # Setup logger for this session
            self._session_logger = setup_session_logging(self.session_id, self.tool_name)
        except Exception as e:
            # Fallback: create basic logger
            import logging
            self._session_logger = logging.getLogger(f'mcp.session.{self.session_id}')
            # Silently continue - logging is optional

    def _log_to_session(self, type_: str, value: Any) -> None:
        """Log event to session log file.

        Args:
            type_: Event type
            value: Event payload
        """
        if not self._session_logger:
            return

        try:
            # Format the log message based on event type
            if isinstance(value, dict):
                # Agent messages with special structure
                if 'agent' in value and 'content' in value:
                    msg = f"[{value.get('agent', 'Agent')}] {value.get('content', '')[:500]}"
                else:
                    msg = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, str):
                msg = value
            else:
                msg = str(value)

            # Log at appropriate level based on event type
            if type_ == 'error':
                self._session_logger.error(msg)
            elif type_ in ('agent.message', 'log', 'tool', 'think'):
                self._session_logger.info(msg)
            elif type_ == 'status':
                self._session_logger.debug(msg)
            else:
                self._session_logger.debug(f"[{type_}] {msg}")
        except Exception:
            # Silently ignore logging errors
            pass

    def broadcast(self, type_: str, value: Any) -> None:
        """Broadcast an event to all connected clients and buffer it (synchronous).

        Uses a simple lock for thread-safety. Normalizes text-centric event values
        to strings to avoid "[object Object]" in UI.

        Also logs conversation events to session-based log files.

        Args:
            type_: Event type (e.g., 'log', 'tool', 'think', 'error', 'status', 'agent.message')
            value: Event payload (will be converted to string for text types)
        """
        # Normalize text-centric event values to strings
        text_types = {"log", "tool", "think", "error", "url", "replace_last", "status"}
        try:
            value_out = value
            if type_ in text_types and not isinstance(value_out, str):
                if isinstance(value_out, (dict, list)):
                    value_out = json.dumps(value_out, ensure_ascii=False)
                else:
                    value_out = str(value_out)
        except Exception:
            value_out = str(value)

        # Log to session file
        self._log_to_session(type_, value_out if type_ in text_types else value)

        with self._lock:
            # assign next sequence id
            self._seq += 1
            evt = Event(type=type_, value=value_out, seq=self._seq)
            # buffer maintenance
            self._buffer.append(evt)
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer :]
            # write to all clients; drop broken ones
            stale = []
            payload = f"data: {json.dumps({'type': type_, 'value': value_out}, ensure_ascii=False)}\n\n".encode("utf-8")
            for w in list(self._clients):
                try:
                    w.write(payload)
                    w.flush()
                except Exception:
                    stale.append(w)
            # cleanup stale
            for s in stale:
                try:
                    self._clients.remove(s)
                except ValueError:
                    pass

    def get_events_since(self, since: int) -> Tuple[int, List[Dict[str, Any]]]:
        """Return (last_seq, items) where items are events with seq > since.
        
        Items are shaped for polling UI: {type, payload, seq}.
        
        Args:
            since: Sequence number to query from
            
        Returns:
            Tuple of (latest_sequence_number, list_of_events)
        """
        with self._lock:
            last_seq = self._seq
            items: List[Dict[str, Any]] = []
            for e in self._buffer:
                if e.seq > since:
                    items.append({"type": e.type, "payload": e.value, "seq": e.seq})
            return last_seq, items

    def set_preview_png(self, png_b64: str) -> None:
        """Set preview image as base64-encoded PNG."""
        self._latest_preview_png_b64 = png_b64

    def get_preview_png(self) -> Optional[str]:
        """Get preview image as base64-encoded PNG."""
        return self._latest_preview_png_b64

    def set_channel_image(self, img_bytes: bytes, mime: str = "image/png", channel: str = "default") -> None:
        """Compatibility shim for legacy agent: store preview from raw bytes."""
        try:
            self._latest_preview_png_b64 = base64.b64encode(img_bytes).decode("ascii")
        except Exception:
            # Keep previous preview if conversion fails
            pass

    def _register_client(self, wfile) -> None:
        """Register a new SSE client."""
        self._clients.append(wfile)

    # === Async Methods for Society of Mind Agents ===

    async def start(self) -> int:
        """
        Start the event server and return the port number.

        For Society of Mind agents, this returns a dynamic port that the
        agent will announce via SESSION_ANNOUNCE event.

        Returns:
            Port number (0 for dynamic assignment by OS)
        """
        # For now, return 0 to indicate dynamic port assignment
        # The actual port will be determined when the HTTP server starts
        self._port = 0
        return self._port

    async def send_event(self, event_data: Dict[str, Any]) -> None:
        """
        Send an event (async version for Society of Mind agents).

        Args:
            event_data: Dictionary containing event data
                Required keys: 'type'
                Optional keys: 'message', 'error', 'result', 'status', 'timestamp', etc.
        """
        # Convert dict event to broadcast format
        event_type = event_data.get('type', 'message')

        # Broadcast as a composite event
        self.broadcast(event_type, event_data)

    async def stop(self) -> None:
        """
        Stop the event server (async version).

        Cleanup method for graceful shutdown.
        """
        # Clear client connections
        with self._lock:
            self._clients.clear()
            self._buffer.clear()


class UIHandler(BaseHTTPRequestHandler):
    """Generic UI handler for MCP agents.
    
    Provides endpoints:
    - GET /           : HTML UI with live updates
    - GET /events     : SSE stream for real-time events
    - GET /events.json: JSON polling fallback
    - GET /preview.png: Latest preview image
    - GET /health     : Health check endpoint
    """
    
    server_version = "MCPServer/1.0"

    # injected at wiring time
    event_server: EventServer = None  # type: ignore
    tool_name: str = "MCP"  # Override with specific tool name

    def _set_headers(self, code: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        """Set standard response headers."""
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        """Handle GET requests."""
        # Parse the URL to ignore query strings for route matching
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self._serve_index()
        if path == "/events":
            return self._serve_events()
        if path == "/events.json":
            return self._serve_events_json(parsed.query)
        if path == "/preview.png":
            return self._serve_preview_png()
        if path == "/health":
            # simple health check used by tooling; 200 if server alive
            self._set_headers(200, "text/plain")
            try:
                self.wfile.write(b"ok")
            except Exception:
                # Client might have closed the connection prematurely; ignore
                pass
            return
        self._set_headers(404, "text/plain")
        try:
            self.wfile.write(b"Not Found")
        except Exception:
            # Client might have closed the connection;avoid noisy stack traces
            pass

    def _serve_index(self) -> None:
        """Serve the main UI HTML page."""
        self._set_headers(200, "text/html; charset=utf-8")
        # Use double curly braces for JavaScript to escape f-string syntax
        html = f"""
<!doctype html>
<html><head><meta charset="utf-8"/><title>MCP Live Viewer</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 0; background: #0b1020; color: #f1f5f9; }}
#header {{ display:flex; gap:12px; align-items:center; padding: 10px 14px; background:#111827; border-bottom:1px solid #1f2937; }}
.badge {{ font-size:12px; background:#10b981; color:#052e2b; padding:2px 6px; border-radius: 999px; }}
#stream {{ white-space: pre-wrap; padding: 12px; line-height:1.45; }}
#previewWrap {{ position: fixed; right: 10px; top: 56px; width: 400px; background:#0f172a; border:1px solid #1f2937; border-radius:8px; overflow:hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.35); }}
#previewWrap header{{ display:flex; justify-content:space-between; align-items:center; padding:6px 8px; background:#0b1220; color:#93c5fd; font-size: 12px; }}
#preview {{ width: 100%; display:block; }}
.label{{ opacity:.6; margin-right:6px; }}
.tool{{ color:#60a5fa; }}
.think{{ color:#a78bfa; background:rgba(167,139,250,.08); border-left:3px solid #a78bfa; padding-left:8px; margin:6px 0; }}
.err{{ color:#fca5a5; }}
</style>
</head>
<body>
<div id="header"><span class="badge">MCP</span><strong>{self.tool_name}</strong></div>
<div id="stream"></div>
<div id="previewWrap"><header><span>Preview</span><small id="url"></small></header><img id="preview" src="/preview.png"/></div>
<script>
const streamEl = document.getElementById('stream');
const urlEl = document.getElementById('url');

function append(text, cls) {{
  const div = document.createElement('div');
  if(cls) div.className = cls;
  try {{
    if (text && typeof text === 'object') {{
      div.textContent = JSON.stringify(text);
    }} else {{
      div.textContent = String(text || '');
    }}
  }}catch(_e){{div.textContent = String(text || ''); }}
  streamEl.appendChild(div);
  window.scrollTo(0, document.body.scrollHeight);
}}

function connect() {{
  const es = new EventSource('/events');
  es.onmessage = (e) => {{
    try {{
      const evt = JSON.parse(e.data);
      const v = evt.value;
      const valStr = (v && typeof v === 'object') ? JSON.stringify(v) : String(v || '');
      if(evt.type === 'log') append(valStr, '');
      if(evt.type === 'tool') append('TOOL: '+valStr, 'tool');
      if(evt.type === 'think') append(valStr, 'think');
      if(evt.type === 'error') append('ERROR: '+valStr, 'err');
      if(evt.type === 'url') urlEl.textContent = valStr;
      if(evt.type === 'status') append('STATUS: '+valStr, '');
      if(evt.type === 'replace_last') {{
         streamEl.lastChild && (streamEl.lastChild.textContent = valStr);
      }}
    }}catch(err){{ console.error(err); }}
  }};
  es.onerror = () => setTimeout(()=>{{ es.close(); connect(); }}, 1500);
}}

connect();
setInterval(()=>{{ const img=document.getElementById('preview'); img.src='/preview.png?'+Date.now(); }}, 2000);
</script>
</body></html>
"""
        try:
            self.wfile.write(html.encode("utf-8"))
        except Exception:
            # Client disconnected mid-write; ignore to avoid noisy logs
            pass

    def _serve_events(self) -> None:
        """Serve SSE event stream."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        # register client and replay buffer
        self.event_server._register_client(self.wfile)

    def _serve_events_json(self, query_str: str) -> None:
        """Polling fallback endpoint: returns JSON events since a sequence ID.
        
        Response shape: { since: <last_seq>, items: [ {type, payload, seq}, ... ] }
        """
        try:
            qs = parse_qs(query_str or "")
            raw = (qs.get("since", ["0"]) or ["0"])[0]
            try:
                since = int(raw)
            except Exception:
                since = 0
            last_seq, items = self.event_server.get_events_since(max(0, since))
            body = {"since": last_seq, "items": items}
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self._set_headers(200, "application/json; charset=utf-8")
            try:
                self.wfile.write(data)
            except Exception:
                pass
        except Exception as e:
            # Ensure robust error handling for easier debugging
            self._set_headers(500, "application/json; charset=utf-8")
            try:
                self.wfile.write(json.dumps({"error": f"events.json failed: {e}"}).encode("utf-8"))
            except Exception:
                pass

    def _serve_preview_png(self) -> None:
        """Serve the latest preview image."""
        png_b64 = self.event_server.get_preview_png()
        if not png_b64:
            self._set_headers(404, "text/plain")
            try:
                self.wfile.write(b"No preview yet")
            except Exception:
                # Client might have closed the connection; ignore
                pass
            return
        try:
            raw = base64.b64decode(png_b64)
        except Exception:
            self._set_headers(500, "text/plain")
            try:
                self.wfile.write(b"Invalid preview data")
            except Exception:
                pass
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except Exception:
            # Client disconnected while reading image; ignore
            pass

    def log_message(self, fmt: str, *args) -> None:
        """Suppress default logging to avoid noisy console output."""
        pass


def start_ui_server(
    event_server: EventServer,
    host: str = "127.0.0.1",  # DEFAULT_UI_HOST inline
    port: int = 0,  # DEFAULT_UI_PORT inline (0 = dynamic)
    tool_name: str = "MCP Agent"
) -> Tuple[ThreadingHTTPServer, threading.Thread, str, int]:
    """Start the lightweight UI server in a thread and return (server, thread, bound_host, bound_port).
    
    Args:
        event_server: EventServer instance for broadcasting
        host: Host to bind to (default: 127.0.0.1)
        port: Port to bind to (0 for dynamic OS-assigned port)
        tool_name: Display name for the tool in UI
        
    Returns:
        Tuple of (httpd, thread, bound_host, bound_port)
        
    Features:
    - Supports dynamic port assignment via port=0 (Windows-friendly)
    - Uses ThreadingHTTPServer so long-lived SSE (/events) won't block other routes
    - Daemon thread for automatic cleanup on process exit
    """
    class _Handler(UIHandler):
        pass
    
    _Handler.event_server = event_server  # inject instance
    _Handler.tool_name = tool_name  # inject tool name

    # Switch to ThreadingHTTPServer for concurrent handling of /events and /preview.png
    httpd = ThreadingHTTPServer((host, port), _Handler)
    # Effective address after binding (port may be 0 -> OS picks an available one)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, name="mcp-ui", daemon=True)
    t.start()
    return httpd, t, bound_host, bound_port