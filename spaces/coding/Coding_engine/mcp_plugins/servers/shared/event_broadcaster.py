# -*- coding: utf-8 -*-
"""
event_broadcaster.py
Shared event broadcasting module for all MCP agents.
Provides SSE (Server-Sent Events) for real-time Society of Mind dialogue display.
"""
import base64
import json
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread, Lock
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs


# ---------- EventServer ----------

@dataclass
class Event:
    type: str
    value: Any
    seq: int = 0


class EventServer:
    """Event broadcast server for MCP agents with SSE endpoint.

    Broadcasts events like:
    - "agent.message": Operator/QA Validator dialogue
    - "tool.call": Tool invocations
    - "session.status": Session lifecycle events
    - "log": General logging
    """

    def __init__(self):
        self._buffer: List[Event] = []
        self._max_buffer = 200
        self._clients: List = []
        self._lock = Lock()
        self._seq: int = 0

    def broadcast(self, type_: str, value: Any) -> None:
        """Broadcast an event to all connected clients and buffer it."""
        # Normalize text-centric event values to strings
        text_types = {"log", "tool.call", "agent.message", "error", "session.status"}
        try:
            value_out = value
            if type_ in text_types and not isinstance(value_out, str):
                if isinstance(value_out, (dict, list)):
                    value_out = json.dumps(value_out, ensure_ascii=False)
                else:
                    value_out = str(value_out)
        except Exception:
            value_out = str(value)

        with self._lock:
            self._seq += 1
            evt = Event(type=type_, value=value_out, seq=self._seq)

            # Buffer maintenance
            self._buffer.append(evt)
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer:]

            # Write to all clients; drop broken ones
            stale = []
            payload = f"data: {json.dumps({'type': type_, 'value': value_out}, ensure_ascii=False)}\n\n".encode("utf-8")
            for w in list(self._clients):
                try:
                    w.write(payload)
                    w.flush()
                except Exception:
                    stale.append(w)

            # Cleanup stale
            for s in stale:
                try:
                    self._clients.remove(s)
                except ValueError:
                    pass

    def get_events_since(self, since: int) -> Tuple[int, List[Dict[str, Any]]]:
        """Return (last_seq, items) where items are events with seq > since."""
        with self._lock:
            last_seq = self._seq
            items: List[Dict[str, Any]] = []
            for e in self._buffer:
                if e.seq > since:
                    items.append({"type": e.type, "payload": e.value, "seq": e.seq})
            return last_seq, items

    def _register_client(self, wfile) -> None:
        self._clients.append(wfile)


# ---------- UI Handler ----------

class EventHandler(BaseHTTPRequestHandler):
    """HTTP handler for SSE events endpoint."""
    server_version = "MCPEventServer/1.0"
    event_server: EventServer = None  # type: ignore

    def _set_headers(self, code: int = 200, content_type: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/events":
            return self._serve_events()
        if path == "/events.json":
            return self._serve_events_json(parsed.query)
        if path == "/health":
            self._set_headers(200, "text/plain")
            try:
                self.wfile.write(b"ok")
            except Exception:
                pass
            return

        self._set_headers(404, "text/plain")
        try:
            self.wfile.write(b"Not Found")
        except Exception:
            pass

    def _serve_events(self) -> None:
        """SSE endpoint for real-time events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.event_server._register_client(self.wfile)

    def _serve_events_json(self, query_str: str) -> None:
        """Polling fallback endpoint."""
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
            self._set_headers(500, "application/json; charset=utf-8")
            try:
                self.wfile.write(json.dumps({"error": f"events.json failed: {e}"}).encode("utf-8"))
            except Exception:
                pass

    def log_message(self, format, *args):
        """Suppress default HTTP logging to reduce noise."""
        pass


# ---------- Server startup ----------

def start_event_server(event_server: EventServer, host: str = "127.0.0.1", port: int = 0) -> Tuple[ThreadingHTTPServer, Thread, str, int]:
    """Start the event server in a thread and return (server, thread, bound_host, bound_port).

    - port=0 allows OS to pick an available port dynamically
    - Uses ThreadingHTTPServer for concurrent SSE connections
    """
    class _Handler(EventHandler):
        pass
    _Handler.event_server = event_server

    httpd = ThreadingHTTPServer((host, port), _Handler)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    t = Thread(target=httpd.serve_forever, name="mcp-event-server", daemon=True)
    t.start()
    return httpd, t, bound_host, bound_port
