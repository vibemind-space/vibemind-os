import asyncio
import json
import os
import threading
import time
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple, Optional
import base64
import re
import urllib.parse
import uuid

# Load .env for environment variables like OPENAI_API_KEY
try:
    import dotenv
    dotenv.load_dotenv()
except Exception:
    pass

# Autogen / MCP imports
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench
from autogen_ext.tools.mcp import StdioServerParams, create_mcp_server_session, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import ImageResultContent
from event_task import EventServer, start_ui_server
from preview_utils import PreviewManager
# Optional tools module for centralized config/prompt loading
try:
    from tools import init_model_client, get_system_prompt, get_task_prompt, load_servers_config  # noqa: F401
except Exception:
    # Fallback stubs if running without module resolution
    init_model_client = None  # type: ignore
    get_system_prompt = None  # type: ignore
    get_task_prompt = None  # type: ignore
    load_servers_config = None  # type: ignore

# Optional: rich console for nicer logs
try:
    from rich.console import Console
    from rich.traceback import install
    install()
    console = Console()
except Exception:
    console = None

# ========== Constants ==========
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = int(os.getenv("MCP_UI_PORT", "8787"))

# ========== File helpers ==========
BASE_DIR = os.path.dirname(__file__)
SERVERS_DIR = os.path.dirname(BASE_DIR)  # .../servers
PLUGINS_DIR = os.path.dirname(SERVERS_DIR)  # .../MCP PLUGINS
MODELS_DIR = os.path.join(PLUGINS_DIR, "models")

SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "system_prompt.txt")
TASK_PROMPT_PATH = os.path.join(BASE_DIR, "task_prompt.txt")
SERVERS_CONFIG_PATH = os.path.join(SERVERS_DIR, "servers.json")
MODEL_CONFIG_PATH = os.path.join(MODELS_DIR, "model.json")

# ========== Defaults (written if missing) ==========
DEFAULT_SYSTEM_PROMPT = (
    "You are an AutoGen Assistant wired to an MCP server with browser automation tools (e.g., browser_*).\n"
    "Follow the TOOL USAGE contract strictly and call only the exposed tool names.\n"
    "Dynamic event hint: {MCP_EVENT}.\n"
    "For any browser-related task: navigate safely, wait for relevant selectors, avoid unnecessary actions, and minimize data extraction.\n"
)

DEFAULT_TASK_PROMPT = (
    "Use the available tools to accomplish the goal and stream your progress.\n"
    "For Playwright, prefer safe sources (e.g., Wikipedia) and extract minimal text/HTML.\n"
)

DEFAULT_SERVERS_JSON = {
    "servers": [
        {
            "name": "playwright",
            "active": True,
            "type": "stdio",
            "command": "npx",
            "args": ["--yes", "@playwright/mcp@latest", "--headless"],
            "read_timeout_seconds": 120
        }
    ]
}

DEFAULT_MODEL_JSON = {
    "model": os.getenv("OPENAI_MODEL") or os.getenv("MODEL") or (
        "llama3.1" if os.getenv("OPENAI_BASE_URL") else "gpt-4o"
    ),
    "base_url": os.getenv("OPENAI_BASE_URL"),
    "api_key_env": "OPENAI_API_KEY"
}

# Ensure directory structure exists
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(SERVERS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Create defaults if missing
if not os.path.exists(SYSTEM_PROMPT_PATH):
    with open(SYSTEM_PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(DEFAULT_SYSTEM_PROMPT)
if not os.path.exists(TASK_PROMPT_PATH):
    with open(TASK_PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(DEFAULT_TASK_PROMPT)
if not os.path.exists(SERVERS_CONFIG_PATH):
    with open(SERVERS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_SERVERS_JSON, f, indent=2)
if not os.path.exists(MODEL_CONFIG_PATH):
    with open(MODEL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_MODEL_JSON, f, indent=2)

# ========== Simple SSE UI + Event Server ==========
class _EventServer(ThreadingHTTPServer):
    """Threaded HTTP server with channel-aware event broadcasting and image storage.

    - Maintains a global increasing sequence for ordered events (seq)
    - Buffers recent events for polling fallback (/events.json)
    - Stores last image per channel for quick preview endpoints (/browser/*)
    """

    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.clients: List[queue.Queue] = []
        self._seq: int = 0
        self._buffer: List[str] = []  # JSON-serialized event objects
        self._buffer_limit: int = 500
        self._images_bytes: Dict[str, bytes] = {}
        self._images_mime: Dict[str, str] = {}
        self.last_source: str | None = None
        # DEBUG: Track browser open-state and rate-limit "screenshot skipped" logs
        self.browser_open_last_state: bool = False
        self.screenshot_skip_last_log_ts: float = 0.0
        # Hysteresis support: timestamp of last evidence that browser is open
        self.last_open_signal_ts: float = 0.0
        # Hysteresis support: timestamp of last image captured
        self.last_image_ts: float = 0.0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def broadcast(self, kind: str, payload: Dict[str, Any]):
        """Broadcast an event to all SSE clients and store it in buffer.

        Payload may include an optional 'channel' key. Defaults to 'default'.
        """
        try:
            channel = payload.pop("channel", "default") or "default"
        except Exception:
            channel = "default"
        seq = self.next_seq()
        msg_obj: Dict[str, Any] = {"type": kind, "seq": seq, "channel": channel}
        msg_obj.update(payload)
        try:
            msg = json.dumps(msg_obj, ensure_ascii=False)
        except Exception:
            # Fallback serialize
            msg = json.dumps({"type": kind, "seq": seq, "channel": channel, "message": str(payload)})
        # Buffer for polling fallback
        self._buffer.append(msg)
        if len(self._buffer) > self._buffer_limit:
            self._buffer = self._buffer[-self._buffer_limit:]
        # Fan out to clients
        for q in list(self.clients):
            try:
                q.put_nowait(msg)
            except Exception:
                pass

    def get_events_since(self, since: int) -> Tuple[List[str], int]:
        """Return buffered events with seq > since and the latest seq seen."""
        items: List[str] = []
        last = since
        for s in self._buffer:
            try:
                obj = json.loads(s)
                seq = int(obj.get("seq") or 0)
                if seq > since:
                    items.append(s)
                    if seq > last:
                        last = seq
            except Exception:
                continue
        return items, last

    def set_channel_image(self, img_bytes: bytes, mime: str = "image/png", channel: str = "default") -> None:
        """Store latest image bytes and mime for given channel."""
        try:
            self._images_bytes[channel] = img_bytes
            self._images_mime[channel] = mime or "image/png"
        except Exception:
            pass

    def get_channel_image(self, channel: str = "default") -> Tuple[bytes | None, str | None]:
        """Retrieve latest image bytes and mime for given channel."""
        try:
            return self._images_bytes.get(channel), self._images_mime.get(channel, "image/png")
        except Exception:
            return None, None


class _UIHandler(BaseHTTPRequestHandler):
    INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>MCP Live Viewer</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background:#0b0f12; color:#e6edf3; }
    header { padding: 12px 16px; background:#11181f; border-bottom:1px solid #26313a; }
    .row { display:flex; gap:12px; padding:12px; }
    .col { flex:1; background:#0f1419; border:1px solid #26313a; border-radius:8px; overflow:auto; min-height: 60vh; }
    .col h3 { margin: 0; padding:10px 12px; border-bottom:1px solid #26313a; background:#0b1116; position:sticky; top:0; }
    pre { white-space: pre-wrap; word-wrap: break-word; margin: 0; padding:10px 12px; }
    .foot { padding:8px 12px; color:#9fb3c8; font-size:12px; border-top:1px solid #26313a; }
    .ok { color:#5bd6a3; } .err { color:#ff7b72; } .tool { color:#91a7ff; }
    img.preview { max-width:100%; height:auto; display:block; border-radius:6px; border:1px solid #26313a; background:#0b1116; }
    .badge { display:inline-block; margin-left:10px; padding:2px 8px; font-size:12px; border-radius:999px; border:1px solid #26313a; background:#0b1116; color:#9fb3c8; }
    .badge-ok { color:#0fd88f; border-color:#155e42; background:#0b1512; }
    .badge-warn { color:#e0b400; border-color:#5a4a00; background:#141107; }
    .badge-err { color:#ff7b72; border-color:#5a1e1b; background:#190e0d; }
    .badge-info { color:#91a7ff; border-color:#2b3f63; background:#0b1116; }
    /* Placeholder styling for when the browser isn't open */
    .placeholder { display:block; color:#9fb3c8; font-size:14px; padding:12px; border:1px dashed #26313a; border-radius:6px; background:#0b1116; text-align:center; margin-bottom:10px; }
  </style>
</head>
<body>
  <header>
    <strong>MCP Live Viewer</strong>
    <span style="margin-left:10px; color:#9fb3c8">Server: Playwright</span>
    <span id="connstatus" class="badge" title="Connection Status">Connecting…</span>
    <span id="agentstatus" class="badge" title="Agent Status">Idle</span>
  </header>
  <div class="row">
    <div class="col" id="stream">
      <h3>Model Stream</h3>
      <pre id="streamlog"></pre>
    </div>
    <div class="col" id="events">
      <h3>Tool Events</h3>
      <pre id="eventlog"></pre>
    </div>
    <div class="col" id="browser">
      <h3>Browser Preview</h3>
      <div style="padding:10px 12px;">
        <div id="browserph" class="placeholder">No preview yet</div>
        <img id="browserimg" class="preview" alt="Live browser preview" />
      </div>
    </div>
  </div>
  <div class="foot">Live updates via SSE. This page auto-connects.</div>
  <script src="/app.js"></script>
</body>
</html>
"""

    # External JS served at /app.js to avoid inline parsing issues and allow easier debugging
    APP_JS = r"""
(function(){
  // --- DOM helpers ---
  function byId(id){ return document.getElementById(id); }
  var streamEl = byId('streamlog');
  var eventEl  = byId('eventlog');
  var browserImg = byId('browserimg');
  var statusEl = byId('connstatus');
  var agentStatusEl = byId('agentstatus');
  var browserPh = byId('browserph');
  // Aggregierter LLM-Response-Puffer (sammelt nur 'content'/'chunk')
  var aggText = '';
  var aggTimer = null;
  function flushAgg(){ try{ if(aggText){ appendSep(streamEl); appendLine(streamEl, aggText, ''); appendSep(streamEl); aggText=''; } }catch(_e){} }

  // Simple visueller Separator (ohne Zeitstempel)
  function appendSep(el){ try{ if(!el) return; el.appendChild(document.createTextNode('────────────────────────────────────────\n')); el.scrollTop = el.scrollHeight; }catch(_e){} }

  // Append a dedicated THINK block with dashed delimiters (no timestamp)
  function appendThink(el, text){
    try{
      if(!el) return;
      el.appendChild(document.createTextNode('-------------\n'));
      el.appendChild(document.createTextNode('think\n'));
      el.appendChild(document.createTextNode(String(text||'') + '\n'));
      el.appendChild(document.createTextNode('-------------\n'));
      el.scrollTop = el.scrollHeight;
    }catch(_e){}
  }

  // Set visual connection state badge
  function setStatus(text, cls){
    try{
      if(!statusEl) return;
      statusEl.textContent = String(text || '');
      statusEl.className = 'badge ' + String(cls || 'badge-info');
    }catch(_e){}
  }

  // Set agent activity status badge
  function setAgentStatus(text, cls){
    try{
      if(!agentStatusEl) return;
      agentStatusEl.textContent = String(text || '');
      agentStatusEl.className = 'badge ' + String(cls || 'badge-info');
    }catch(_e){}
  }

  // Hilfsfunktion: Toolnamen aus Text extrahieren (browser_*)
  function parseToolName(text){ try{ var m = String(text||'').match(/browser_[a-z_]+/i); return m? m[0] : null; }catch(_e){ return null; } }

  // Append a timestamped line into a <pre>
  function appendLine(el, text, cls){
    try{
      if(!el) return;
      var span = document.createElement('span');
      if (cls) span.className = cls;
      span.textContent = '[' + new Date().toLocaleTimeString() + '] ' + String(text || '');
      el.appendChild(span);
      // IMPORTANT: use explicit \n to avoid multiline string parsing issues
      el.appendChild(document.createTextNode('\n'));
      el.scrollTop = el.scrollHeight;
    }catch(_e){}
  }

  // Update browser preview image from different payload shapes
  function setBrowserImage(obj){
    try{
      if (!browserImg) return;
      var url = (obj && (obj.data_uri || obj.url)) || null;
      if (!url && obj && obj.data) {
        url = 'data:image/png;base64,' + String(obj.data);
      }
      if (url) {
        browserImg.src = url;
        try{ if (browserPh) browserPh.style.display = 'none'; }catch(__e){}
      }
    }catch(_e){}
  }

  // Render one message object
  function handleMsg(msg){
    try {
      var t = msg.type || 'status';
      var txt = msg.text || msg.message || '';
      var seq = Number(msg.seq || 0) || 0;
      if (seq > lastSeq) lastSeq = seq;
      if (t === 'chunk' || t === 'content') {
        // Nur LLM-Content sammelt sich in aggText
        aggText += (txt || '');
        setAgentStatus('Streaming...', 'badge-info');
      } else if (t === 'think') {
        // Denke-Blöcke separat anzeigen, nicht aggregieren
        flushAgg();
        appendThink(streamEl, txt);
        setAgentStatus('Thinking', 'badge-info');
      } else if (t === 'source') {
        appendLine(streamEl, txt || JSON.stringify(msg), '');
      } else if (t === 'tool') {
        appendLine(eventEl, txt || JSON.stringify(msg), 'tool');
        var name = parseToolName(txt);
        if (name) setAgentStatus('Tool: ' + name, 'badge-info');
      } else if (t === 'browser' || t === 'image') {
        setBrowserImage(msg);
        appendLine(eventEl, txt || 'Browser update', 'ok');
        setAgentStatus('Preview update', 'badge-ok');
      } else if (t === 'browser_state') {
        // Toggle placeholder visibility based on backend state
        try{
          var isOpen = !!msg.open;
          if (browserPh) browserPh.style.display = isOpen ? 'none' : 'block';
          // Do not clear browserImg.src on transient closes to avoid flicker
          // if (!isOpen && browserImg) browserImg.src = '';
        }catch(__e){}
        appendLine(eventEl, txt || (msg.open ? 'Browser open' : 'No preview yet'), msg.open ? 'ok' : '');
        setAgentStatus(msg.open ? 'Browser open' : 'No preview yet', msg.open ? 'badge-ok' : 'badge-warn');
      } else if (t === 'error') {
        appendLine(eventEl, txt || JSON.stringify(msg), 'err');
        setAgentStatus('Error', 'badge-err');
      } else if (t === 'status' && (txt || '').toLowerCase().includes('stream end')) {
        // Endmarker: Jetzt aggregierten LLM-Text einmalig ausgeben
        flushAgg();
        setAgentStatus('Idle', 'badge-info');
      } else if (t === 'status' && (txt || '').toLowerCase().includes('stream start')) {
        setAgentStatus('Streaming...', 'badge-info');
      } else {
        appendLine(eventEl, txt || JSON.stringify(msg), 'ok');
      }
    } catch(_e) {
      // Visualize raw on parse/display errors
      try { appendLine(eventEl, JSON.stringify(msg), ''); } catch(__e){}
    }
  }

  // --- Connection state + polling fallback ---
  var usePolling = false;           // toggled when SSE errors
  var pollTimer = null;             // interval handle
  var lastSeq = 0;                  // last seen event seq

  // Polling once for new events since lastSeq
  function pollOnce(){
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', '/events.json?since=' + String(lastSeq), true);
      xhr.onreadystatechange = function(){
        try {
          if (xhr.readyState === 4 && xhr.status === 200) {
            var data = JSON.parse(xhr.responseText || '{}');
            var items = Array.isArray(data.items) ? data.items : [];
            var since = Number(data.since || 0) || lastSeq;
            for (var i = 0; i < items.length; i++) {
              try {
                var obj = JSON.parse(String(items[i] || '{}'));
                handleMsg(obj);
              } catch(_e) {
                // If payload was not valid JSON, render raw
                appendLine(eventEl, String(items[i] || ''), '');
              }
            }
            if (since > lastSeq) lastSeq = since;
            // Wenn keine neuen Events kamen, flushen wir den Aggregat-Buffer
            try{ if(!items.length){ flushAgg(); } }catch(__e){}
          }
        } catch(_e) {}
      };
      xhr.onerror = function(){ setStatus('Disconnected. Polling…', 'badge-err'); flushAgg(); };
      xhr.send(null);
    } catch(_e){}
  }

  // Ensure a single polling loop is active
  function ensurePolling(){
    try {
      if (!usePolling) return;
      if (pollTimer) return;
      // Start lightweight polling loop
      pollTimer = setInterval(pollOnce, 1500);
      // Kick off immediately so user sees something without waiting
      pollOnce();
    } catch(_e){}
  }

  // Start an EventSource SSE connection, with fallback to polling on errors
  function startSSE(){
    try{
      var es = new EventSource('/events');
      es.onopen = function(){
        usePolling = false;
        if (pollTimer) { try { clearInterval(pollTimer); } catch(_e){}; pollTimer = null; }
        setStatus('Connected', 'badge-ok');
        // Flush-Timeout: wenn 1.5s keine neuen Chunks/Contents kommen, Ausgabe gesammelt
        try{ if(aggTimer) { clearTimeout(aggTimer); aggTimer=null; }
             aggTimer = setTimeout(flushAgg, 1500);
        }catch(__e){}
      };
      es.onmessage = function(ev){
        try{
          var msg = JSON.parse(String(ev.data || '{}'));
          handleMsg(msg);
          // Reset Flush-Timeout bei jeder Message
          try{ if(aggTimer) { clearTimeout(aggTimer); aggTimer=null; } aggTimer = setTimeout(flushAgg, 1200); }catch(__e){}
        }catch(_e){ appendLine(eventEl, String(ev.data || ''), ''); }
      };
      es.onerror = function(){
        setStatus('Reconnecting…', 'badge-warn');
        usePolling = true;
        ensurePolling();
        // Bei Fehlern den bis dahin aggregierten Text ausgeben
        flushAgg();
        setAgentStatus('Disconnected', 'badge-err');
      };
    }catch(_e){
      setStatus('Reconnecting…', 'badge-warn');
      usePolling = true;
      ensurePolling();
    }
  }

  // Boot
  setAgentStatus('Idle', 'badge-info');
  startSSE();

  // Periodic health ping
  try {
    setInterval(function(){
      try {
        fetch('/health', { cache: 'no-store' })
          .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); })
          .catch(function(e){ setStatus('Disconnected', 'badge-err'); setAgentStatus('Disconnected', 'badge-err'); });
      } catch(_e){}
    }, 8000);
  } catch(_e){}

  // Global error hook to help debugging syntax issues
  try {
    window.addEventListener('error', function(e){
      try { console.error('[ui]', e.message, 'at', e.lineno + ':' + e.colno); } catch(__e){}
    });
  } catch(_e){}
})();
"""

    def log_message(self, fmt: str, *args) -> None:
        # keep server console quiet
        pass

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        # Serve index
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, self.INDEX_HTML.encode("utf-8"))
            return

        # Serve external JS for UI
        if self.path == "/app.js" or self.path == "/public/app.js":
            # NOTE: application/javascript ensures correct parsing
            self._send(200, self.APP_JS.encode("utf-8"), content_type="application/javascript; charset=utf-8")
            return

        # Health endpoint for simple monitoring
        if self.path == "/health" or self.path == "/s/health":
            self._send(200, b"ok", content_type="text/plain; charset=utf-8")
            return

        # Simple test broadcast to verify UI piping
        if self.path == "/test" or self.path == "/s/test":
            try:
                self.server.broadcast("status", {"text": "Test event"})  # type: ignore[attr-defined]
                self.server.broadcast("tool", {"text": "[Tool] sample tool call"})  # type: ignore[attr-defined]
            except Exception:
                pass
            self._send(200, b"ok", content_type="text/plain; charset=utf-8")
            return

        # JSON polling fallback: /events.json?since=<seq>
        if self.path.startswith("/events.json"):
            try:
                qs = urllib.parse.urlparse(self.path).query
                qd = urllib.parse.parse_qs(qs)
                since = int((qd.get("since", ["0"]) or ["0"])[0])
            except Exception:
                since = 0
            try:
                items, last = self.server.get_events_since(since)  # type: ignore[attr-defined]
                body = json.dumps({"since": last, "items": items}).encode("utf-8")
                self._send(200, body, content_type="application/json; charset=utf-8")
            except Exception:
                self._send(500, b"{}", content_type="application/json; charset=utf-8")
            return

        # SSE stream
        if self.path == "/events":
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q: queue.Queue = queue.Queue()
                self.server.clients.append(q)  # type: ignore[attr-defined]
                try:
                    self.wfile.write(b":connected\n\n"); self.wfile.flush()
                except Exception:
                    return
                while True:
                    try:
                        msg = q.get(timeout=15)
                        payload = ("data: " + str(msg) + "\n\n").encode("utf-8")
                        self.wfile.write(payload)
                        self.wfile.flush()
                    except queue.Empty:
                        try:
                            self.wfile.write(b":keepalive\n\n"); self.wfile.flush()
                        except Exception:
                            break
                    except Exception:
                        break
            finally:
                try:
                    self.server.clients.remove(q)  # type: ignore[attr-defined]
                except Exception:
                    pass
            return

        # Browser preview: latest as raw image stream
        if self.path == "/browser/stream" or self.path == "/s/browser/stream":
            img_bytes, mime = self.server.get_channel_image("default")  # type: ignore[attr-defined]
            if not img_bytes:
                self._send(404, b"no image", content_type="text/plain; charset=utf-8")
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", mime or "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(img_bytes)))
                self.end_headers()
                self.wfile.write(img_bytes)
            except Exception:
                pass
            return

        # Browser preview: latest as JSON (base64)
        if self.path == "/browser/latest" or self.path == "/s/browser/latest":
            img_bytes, mime = self.server.get_channel_image("default")  # type: ignore[attr-defined]
            if not img_bytes:
                body = json.dumps({"mime": None, "data": None}).encode("utf-8")
                self._send(200, body, content_type="application/json; charset=utf-8")
                return
            try:
                b64 = base64.b64encode(img_bytes).decode("ascii")
            except Exception:
                b64 = None  # type: ignore[assignment]
            body = json.dumps({"mime": mime or "image/png", "data": b64}).encode("utf-8")
            self._send(200, body, content_type="application/json; charset=utf-8")
            return

        self._send(404, b"Not Found", content_type="text/plain; charset=utf-8")

# ========== Utility ==========
def _broadcast(server, kind: str, text: str):
    # Centralized text broadcast mapped to new UI types; value is plain text for simplicity
    mapped = "log" if kind == "status" else kind
    server.broadcast(mapped, text)
    if console:
        console.print(text)
    else:
        print(text)

async def run(
    task_override: Optional[str] = None,
    system_override: Optional[str] = None,
    ui_host: Optional[str] = None,
    ui_port: Optional[int] = None,
    session_id: Optional[str] = None,
    keepalive: bool = False,
):
    # Start UI early using new EventServer/start_ui_server so the user sees status even if model init fails
    event_server = EventServer()
    # Resolve UI bind parameters with safe defaults; allow dynamic port assignment via 0
    ui_bind_host = (ui_host or os.getenv("MCP_UI_HOST") or DEFAULT_UI_HOST)
    try:
        env_port = int(os.getenv("MCP_UI_PORT", str(DEFAULT_UI_PORT)))
    except Exception:
        env_port = DEFAULT_UI_PORT
    # Prefer dynamic port assignment when no explicit port is provided.
    # Using 0 lets the OS pick a free port, avoiding conflicts when starting multiple agents.
    env_port = int(os.getenv("MCP_UI_PORT", "0") or "0")
    ui_bind_port = int(ui_port) if isinstance(ui_port, int) else env_port
    # Generate a session identifier if not provided
    session_id = session_id or os.getenv("MCP_SESSION_ID") or str(uuid.uuid4())

    httpd, t, bound_host, bound_port = start_ui_server(event_server, ui_bind_host, ui_bind_port)

    preview_url = f"http://{bound_host}:{bound_port}/"
    # Announce session start via events and a machine-parseable stdout line
    _broadcast(event_server, "status", f"UI available at {preview_url}")
    try:
        event_server.broadcast("session.started", {
            "session_id": session_id,
            "ui_url": preview_url,
            "host": bound_host,
            "port": bound_port,
            "ts": time.time(),
        })
    except Exception:
        pass
    # One-line announce for orchestrators to parse easily
    try:
        print("SESSION_ANNOUNCE " + json.dumps({
            "session_id": session_id,
            "ui_url": preview_url,
            "host": bound_host,
            "port": bound_port,
        }))
    except Exception:
        print(f"Preview: {preview_url}")

    # Load configs
    try:
        with open(SERVERS_CONFIG_PATH, "r", encoding="utf-8") as f:
            servers_cfg = json.load(f)
    except Exception:
        servers_cfg = DEFAULT_SERVERS_JSON
    try:
        with open(MODEL_CONFIG_PATH, "r", encoding="utf-8") as f:
            model_cfg = json.load(f)
    except Exception:
        model_cfg = DEFAULT_MODEL_JSON

    # Resolve model client
    model = model_cfg.get("model")
    base_url = model_cfg.get("base_url")
    api_key_env = model_cfg.get("api_key_env") or "OPENAI_API_KEY"
    api_key = os.getenv(api_key_env)

    model_info = None
    if base_url:
        from autogen_core.models import ModelFamily
        model_info = {
            "vision": False,
            "function_calling": True,
            "json_output": False,
            "structured_output": False,
            "family": ModelFamily.UNKNOWN,
        }
        # Fallback: lokale Server (Ollama/LM Studio) benötigen i. d. R. keinen echten API-Key.
        # OpenAI-Client verlangt aber einen Wert, daher Dummy setzen, wenn nicht vorhanden.
        if not api_key:
            api_key = os.getenv("LOCAL_API_KEY", "not-needed")

    try:
        model_client = OpenAIChatCompletionClient(
            model=model,
            api_key=api_key,
            base_url=base_url,
            model_info=model_info,
        )
    except Exception as e:
        _broadcast(event_server, "error", f"LLM init failed: {e}")
        if keepalive:
            _broadcast(event_server, "status", "SSE UI will remain online. Set your API key or base_url and restart.")
            # Keep the UI running to allow preview even on failure
            while True:
                await asyncio.sleep(3600)
        else:
            try:
                event_server.broadcast("session.completed", {
                    "session_id": session_id,
                    "status": "failed",
                    "reason": "llm_init_failed",
                    "ts": time.time(),
                })
            except Exception:
                pass
            try:
                httpd.shutdown()
            except Exception:
                pass
            return

    # Pick active server (playwright for now)
    active = next((s for s in servers_cfg.get("servers", []) if s.get("name") == "playwright" and s.get("active")), None)
    if not active:
        raise RuntimeError("No active MCP server 'playwright' found in servers.json")

    # Build Playwright MCP CLI args and enforce per-session isolation
    # Clear comments for easy debug: we add --user-data-dir=<profiles>/<session_id> unless already present
    args = list(active.get("args", ["--yes", "@playwright/mcp@latest", "--headless"]))
    try:
        profile_base = os.getenv("MCP_USER_DATA_DIR_BASE") or os.path.join(BASE_DIR, "profiles")
        os.makedirs(profile_base, exist_ok=True)
        user_data_dir = os.path.join(profile_base, session_id)
        # Only add if not provided in servers.json to avoid duplicates
        if not any(str(a).startswith("--user-data-dir") for a in args):
            args.append(f"--user-data-dir={user_data_dir}")
    except Exception as _e:
        # If anything fails during profile dir setup, continue without persistent user data dir
        # This keeps the agent functional while logging can point to _e when needed
        pass

    params = StdioServerParams(
        command=active.get("command", "npx"),
        args=args,
        read_timeout_seconds=int(active.get("read_timeout_seconds", 120)),
    )

    # Initialize MCP and tools (also log names for the LLM)
    async with create_mcp_server_session(params) as session:
        await session.initialize()
        tools = await mcp_server_tools(server_params=params, session=session)
        tool_names = [getattr(t, "name", "") for t in tools]
        _broadcast(event_server, "status", f"Playwright tools: {tool_names}")

        # Heuristically pick a screenshot tool and tabs tool, if available
        screenshot_tool = next((n for n in tool_names if isinstance(n, str) and 'screenshot' in n.lower()), None)
        tabs_tool_name = next((n for n in tool_names if isinstance(n, str) and 'tabs' in n.lower()), 'browser_tabs')

        # expose to event_server for compatibility if needed
        event_server.screenshot_tool_name = screenshot_tool  # type: ignore
        event_server.tabs_tool_name = tabs_tool_name  # type: ignore

    # Compose dynamic system message (supports override via arg/env)
    # Clear comments for easy debug and maintenance
    try:
        # Highest priority: explicit override passed into run()
        sys_override_val = system_override
        # Next: environment-based overrides
        if not sys_override_val:
            sys_override_val = os.getenv("MCP_SYSTEM_PROMPT") or os.getenv("SYSTEM_PROMPT")
        if sys_override_val and isinstance(sys_override_val, str) and sys_override_val.strip():
            sys_tmpl = sys_override_val
        else:
            with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
                sys_tmpl = f.read()
    except Exception:
        sys_tmpl = DEFAULT_SYSTEM_PROMPT
    sys_msg = sys_tmpl.replace("{MCP_EVENT}", "playwright")

    # Compose task prompt (supports dynamic assignment via arg/env)
    try:
        with open(TASK_PROMPT_PATH, "r", encoding="utf-8") as f:
            task_msg = f.read()
    except Exception:
        task_msg = DEFAULT_TASK_PROMPT

    # Determine goal override from args/env and build final task
    goal_override = task_override or os.getenv("MCP_TASK") or os.getenv("TASK")
    if isinstance(goal_override, str) and goal_override.strip():
        # Combine generic task instructions with the dynamic user goal
        task = task_msg + "\nGoal: " + goal_override.strip()
    else:
        # No dynamic goal provided; use base task prompt only
        task = task_msg

    # Run agent with workbench
    async with McpWorkbench(params) as mcp:
        agent = AssistantAgent(
            name="playwright",
            model_client=model_client,
            workbench=mcp,
            reflect_on_tool_use=True,
            model_client_stream=True,
            system_message=sys_msg,
        )

        _broadcast(event_server, "status", "Agent started. Streaming...")

        # Heartbeat: send status regularly so the UI shows liveness
        stop_heartbeat = asyncio.Event()

        async def _heartbeat():
            try:
                while not stop_heartbeat.is_set():
                    event_server.broadcast("log", "heartbeat: running")
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass
            except Exception:
                # Heartbeat must not raise
                pass

        hb_task = asyncio.create_task(_heartbeat())

        # Initialize PreviewManager with MCP workbench, event server, and tool names
        # This modularizes screenshot/source capture logic and keeps consistent naming.
        preview_mgr = PreviewManager(
            mcp=mcp,
            event_server=event_server,
            screenshot_tool=screenshot_tool,
            tabs_tool_name=tabs_tool_name,
        )

        last_shot: float = 0.0

        async def maybe_capture_screenshot() -> None:
            """Thin wrapper delegating screenshot capture to PreviewManager for modularity."""
            try:
                await preview_mgr.maybe_capture_screenshot()
            except Exception as e:
                _broadcast(event_server, "error", f"Screenshot failed: {e}")

        async def maybe_capture_source():
            """Delegate to PreviewManager for source extraction and browser state broadcasting."""
            try:
                await preview_mgr.maybe_capture_source()
            except Exception as e:
                _broadcast(event_server, "error", f"Source capture failed: {e}")

        async def ensure_initial_preview():
            """Perform a safe initial navigation and screenshot to populate /preview.png.
            This helps GUI proxy consumers avoid 404 'No preview yet' on first load.
            """
            try:
                # If no screenshot tool is available, nothing to do.
                if not screenshot_tool:
                    return
                # Navigate to a safe, simple page to ensure the browser opens.
                try:
                    await mcp.call_tool('browser_navigate', { 'url': 'https://example.com' })
                    event_server.broadcast('log', 'Initial navigate: example.com')
                except Exception as e:
                    _broadcast(event_server, 'error', f'Initial navigate failed: {e}')
                # Give the page a moment to settle before capturing.
                try:
                    await asyncio.sleep(1.5)
                except Exception:
                    pass
                # Attempt an initial screenshot; PreviewManager will persist PNG bytes.
                try:
                    await preview_mgr.maybe_capture_screenshot()
                except Exception as e:
                    _broadcast(event_server, 'error', f'Initial screenshot failed: {e}')
            except Exception:
                # Never raise from bootstrap path.
                pass

        # Try initial preview
        try:
            asyncio.create_task(maybe_capture_screenshot())
            asyncio.create_task(ensure_initial_preview())
        except Exception:
            pass

        # Precompute tokens for detecting Playwright tool activity in streamed text
        try:
            tool_tokens = set(n.lower() for n in tool_names if n)
        except Exception:
            tool_tokens = set()

        # Continuous preview loop to keep the browser stream updating
        preview_stop = asyncio.Event()
        async def _preview_loop():
            try:
                while not preview_stop.is_set():
                    try:
                        await maybe_capture_source()
                    except Exception:
                        pass
                    try:
                        await maybe_capture_screenshot()
                    except Exception:
                        pass
                    await asyncio.sleep(2.5)
            except asyncio.CancelledError:
                pass

        preview_task = asyncio.create_task(_preview_loop())

        # Helper: coerce arbitrary value structures into text
        def _coerce_text_from_value(v):
            try:
                if v is None:
                    return ""
                if isinstance(v, str):
                    return v
                if isinstance(v, dict):
                    # Prefer common text-bearing keys first
                    for key in ("text", "content", "delta_text", "delta", "partial", "output_text", "value"):
                        if key in v:
                            t = _coerce_text_from_value(v[key])
                            if t:
                                return t
                    # Handle OpenAI-like streaming shapes
                    if "choices" in v and isinstance(v["choices"], list):
                        for ch in v["choices"]:
                            t = _coerce_text_from_value(ch)
                            if t:
                                return t
                    # Fallback: concatenate any nested text values
                    parts = []
                    for _k, _val in v.items():
                        t = _coerce_text_from_value(_val)
                        if t:
                            parts.append(t)
                    return "".join(parts)
                if isinstance(v, (list, tuple)):
                    parts = []
                    for item in v:
                        t = _coerce_text_from_value(item)
                        if t:
                            parts.append(t)
                    return "".join(parts)
                # Pydantic-like / dataclass-like objects
                if hasattr(v, "model_dump"):
                    return _coerce_text_from_value(v.model_dump())
                if hasattr(v, "__dict__"):
                    return _coerce_text_from_value(vars(v))
                return ""
            except Exception:
                return ""

        # Helper: robustly extract only the human-readable text from streaming chunks
        def _extract_human_text_from_chunk(chunk):
            try:
                # Fast-path: handle plain dict/list/tuple chunks by coercing to text directly
                # This covers cases where the streaming event is yielded as a raw mapping like
                # {"type": "content", "content": {"text": "..."}} or similar nested shapes.
                if isinstance(chunk, (dict, list, tuple)):
                    txt = _coerce_text_from_value(chunk)
                    if txt:
                        return txt

                # Direct attributes commonly used by streaming events
                if hasattr(chunk, "content"):
                    txt = _coerce_text_from_value(getattr(chunk, "content"))
                    if txt:
                        return txt
                if hasattr(chunk, "text") and isinstance(getattr(chunk, "text"), str):
                    t = getattr(chunk, "text")
                    if t:
                        return t
                if hasattr(chunk, "delta"):
                    txt = _coerce_text_from_value(getattr(chunk, "delta"))
                    if txt:
                        return txt
                # Dict-like conversions
                if hasattr(chunk, "model_dump"):
                    data = chunk.model_dump()
                    txt = _coerce_text_from_value(data)
                    if txt:
                        return txt
                if hasattr(chunk, "__dict__"):
                    data = vars(chunk)
                    txt = _coerce_text_from_value(data)
                    if txt:
                        return txt
                # Last resort: try to parse JSON from string repr or capture content=...
                s = str(chunk)
                try:
                    j = json.loads(s)
                    txt = _coerce_text_from_value(j)
                    if txt:
                        return txt
                except Exception:
                    try:
                        m = re.search(r"content=(?:'|\")(.+?)(?:'|\")", s, re.DOTALL)
                        if m:
                            return m.group(1)
                    except Exception:
                        pass
                return ""
            except Exception:
                try:
                    return str(getattr(chunk, "content", "")) or ""
                except Exception:
                    return ""

        # Parse and broadcast <think> blocks separately, while forwarding other content
        # Clear comments added for easy debug and maintenance
        think_open = False
        think_buf = ""
        try:
            async for chunk in agent.run_stream(task=task):
                # Extract only the human-readable content from the streaming chunk
                text = _extract_human_text_from_chunk(chunk)
                if not isinstance(text, str):
                    try:
                        text = str(text)
                    except Exception:
                        text = ""
                text = text or ""
                if not text.strip():
                    # Skip empty/whitespace-only payloads to keep UI clean
                    continue

                remaining = text
                normal_out: List[str] = []

                # Stream-safe THINK parser that handles:
                # - Inline <think>...</think> segments within a single chunk
                # - Open <think> tags that span across multiple chunks
                # - Multiple THINK segments within the same chunk
                try:
                    while remaining:
                        if think_open:
                            # Inside a THINK block — look for the closing tag
                            m_close = re.search(r'(?is)</think>', remaining)
                            if m_close:
                                # Append up to the closing tag to buffer
                                think_buf += remaining[:m_close.start()]
                                # Broadcast the THINK block (separated on UI)
                                event_server.broadcast("think", {"text": think_buf})
                                # Reset THINK state
                                think_buf = ""
                                think_open = False
                                # Continue parsing after the closing tag
                                remaining = remaining[m_close.end():]
                                continue
                            else:
                                # No closing tag yet — buffer everything and wait for next chunk
                                think_buf += remaining
                                remaining = ""
                                break
                        else:
                            # Not inside THINK — look for the next opening tag
                            m_open = re.search(r'(?is)<think>', remaining)
                            if m_open:
                                # Normal content before the THINK tag goes to output
                                before = remaining[:m_open.start()]
                                if before:
                                    normal_out.append(before)
                                # Enter THINK mode and continue parsing after the opening tag
                                remaining = remaining[m_open.end():]
                                think_open = True
                                continue
                            else:
                                # No more THINK tags — remaining is normal output
                                normal_out.append(remaining)
                                remaining = ""
                                break
                except Exception:
                    # If parser fails for any reason, forward the raw text as normal content
                    normal_out.append(text)

                # Broadcast any normal content (outside THINK)
                out_text = ("".join(normal_out)).strip()
                if out_text:
                    event_server.broadcast("chunk", {"text": out_text})

                # Surface tool call lines specially (based on original text to preserve detection)
                low = (text or "").lower()
                if (
                    "tool_call" in low
                    or "mcp_playwright_" in text
                    or "toolcallexecutionevent" in low
                    or "name='browser_" in text
                    or " browser_" in text
                    or any(tok and tok in low for tok in tool_tokens)
                ):
                    event_server.broadcast("tool", {"text": text})
                    # Opportunistically update preview and source on tool activity
                    try:
                        await maybe_capture_source()
                        await maybe_capture_screenshot()
                    except Exception:
                        pass
                    try:
                        await maybe_capture_source()
                    except Exception:
                        pass
            # On stream end, flush any pending THINK buffer
            if think_open and think_buf.strip():
                event_server.broadcast("think", {"text": think_buf})
                think_buf = ""
                think_open = False
            # Stream-Ende an UI melden
            event_server.broadcast("status", {"text": "stream end"})
        except Exception as e:
            _broadcast(event_server, "error", f"Agent error: {e}")
            raise
        finally:
            try:
                stop_heartbeat.set()
                hb_task.cancel()
            except Exception:
                pass
            try:
                preview_stop.set()
                preview_task.cancel()
            except Exception:
                pass

        # Emit session completed event and either exit or keep UI alive based on flag
        try:
            event_server.broadcast("session.completed", {
                "session_id": session_id,
                "status": "ok",
                "ts": time.time(),
            })
        except Exception:
            pass
        if keepalive:
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
        else:
            try:
                httpd.shutdown()
            except Exception:
                pass
            return

if __name__ == "__main__":
    # Support dynamic overrides from CLI for easy integration/testing
    import argparse
    parser = argparse.ArgumentParser(description="Playwright MCP Agent runner")
    parser.add_argument("--task", dest="task", help="Goal for the browser agent (e.g., 'Open example.com and read the title')")
    parser.add_argument("--system", dest="system", help="Override system prompt text (optional)")
    parser.add_argument("--ui-host", dest="ui_host", help="UI bind host (default: env MCP_UI_HOST or 127.0.0.1)")
    parser.add_argument("--ui-port", dest="ui_port", type=int, help="UI bind port (0 for dynamic; default: env MCP_UI_PORT or 8787)")
    parser.add_argument("--session-id", dest="session_id", help="Optional session identifier (default: random UUID4)")
    parser.add_argument("--keepalive", dest="keepalive", action="store_true", help="Keep UI alive after completion (debug mode)")
    args = parser.parse_args()
    asyncio.run(run(
        task_override=args.task,
        system_override=args.system,
        ui_host=args.ui_host,
        ui_port=args.ui_port,
        session_id=args.session_id,
        keepalive=bool(args.keepalive),
    ))