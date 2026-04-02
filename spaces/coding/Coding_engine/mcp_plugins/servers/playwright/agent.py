import asyncio
import json
import os
import sys
import threading
import time
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple, Optional
import base64
import re
import urllib.parse
import uuid
from datetime import datetime
from dataclasses import dataclass, field
import importlib.util

# Load .env for environment variables like OPENAI_API_KEY
try:
    import dotenv
    dotenv.load_dotenv()
except Exception:
    pass

# Import global LLM config
from src.llm_config import get_model

# ========== DIAGNOSTIC LOGGING: AutoGen Import Status ==========
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [PLAYWRIGHT-AGENT] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

logger.info("=" * 80)
logger.info("PLAYWRIGHT AGENT STARTUP - DIAGNOSTIC MODE")
logger.info("=" * 80)

# Autogen / MCP imports - Society of Mind pattern
try:
    logger.info("Attempting to import AutoGen dependencies...")
    from autogen_ext.models.openai import OpenAIChatCompletionClient
    logger.info("✓ autogen_ext.models.openai imported successfully")
    
    from autogen_ext.tools.mcp import McpWorkbench
    logger.info("✓ autogen_ext.tools.mcp.McpWorkbench imported successfully")
    
    from autogen_ext.tools.mcp import StdioServerParams, create_mcp_server_session, mcp_server_tools
    logger.info("✓ autogen_ext.tools.mcp utilities imported successfully")
    
    from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
    logger.info("✓ autogen_agentchat.agents imported successfully")
    
    from autogen_agentchat.teams import RoundRobinGroupChat
    logger.info("✓ autogen_agentchat.teams imported successfully")
    
    from autogen_agentchat.conditions import TextMentionTermination
    logger.info("✓ autogen_agentchat.conditions imported successfully")
    
    from autogen_core.tools import ImageResultContent
    from pydantic import BaseModel
    logger.info("✓ autogen_core.tools imported successfully")
    
    logger.info("✓✓✓ ALL AUTOGEN DEPENDENCIES IMPORTED SUCCESSFULLY ✓✓✓")
except ImportError as e:
    logger.error("=" * 80)
    logger.error("CRITICAL ERROR: AutoGen dependency import failed!")
    logger.error(f"Missing dependency: {e}")
    logger.error("Please install AutoGen: pip install 'autogen-agentchat>=0.4' 'autogen-ext[openai]>=0.4'")
    logger.error("=" * 80)
    sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected error during AutoGen import: {e}")
    sys.exit(1)

# Import event server and preview utilities from shared and local modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from conversation_logger import ConversationLogger, SenseCategory, ThinkingLog, ToolCall, ToolResult

from preview_utils import PreviewManager

# Event broadcasting for live GUI updates
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from model_init import init_model_client as shared_init_model_client

# Optional tools module for centralized config/prompt loading
try:
    from tools import get_system_prompt, get_task_prompt, load_servers_config  # noqa: F401
except Exception:
    # Fallback stubs if running without module resolution
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
            "args": ["--yes", "@playwright/mcp@latest", "--browser", "msedge"],
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

# ========== Agent System Prompts (Society of Mind) - Loaded from Python modules ==========
def load_prompt_from_module(module_name: str, default: str) -> str:
    """Load prompt from a Python module's PROMPT variable."""
    try:
        # Try to import the prompt module
        import importlib.util
        module_path = os.path.join(BASE_DIR, f"{module_name}.py")

        if os.path.exists(module_path):
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'PROMPT'):
                    return module.PROMPT
        return default
    except Exception as e:
        print(f"Warning: Failed to load prompt from {module_name}: {e}")
        return default

# Default prompts (used if modules don't exist or fail to load)
DEFAULT_BROWSER_OPERATOR_PROMPT = """ROLE: Browser Operator (Playwright MCP)
GOAL: Complete the task entirely in the browser (navigation, search, clicks, forms, scraping).
TOOLS: Use ONLY the available MCP Playwright tools (browser_navigate, browser_click, browser_fill, browser_wait_for_selector, browser_evaluate, browser_screenshot).
GUIDELINES:
- Be robust: wait for visible/clickable elements before interacting.
- Log steps briefly (bullet points).
- Extract only what's necessary (concise, structured).
- Do NOT enter sensitive data.
- When the task is fulfilled, provide a compact summary and signal completion clearly.
OUTPUT:
- Brief step log
- Relevant results (compact, JSON-like if appropriate)
- Completion signal: "READY_FOR_VALIDATION"
"""

DEFAULT_QA_VALIDATOR_PROMPT = """ROLE: QA Validator
GOAL: Verify that the user's task is completely and correctly fulfilled.
CHECK:
- Were the required information/actions precisely delivered?
- Are the results traceable (links/confirmations)?
RESPONSE:
- If everything is correct: respond ONLY with 'APPROVE' plus 1-2 bullet points (no long texts).
- If something is missing: name precisely 1-2 gaps (why/what is missing).
"""

# Load prompts from Python modules (executed once at module import)
PROMPT_BROWSER_OPERATOR = load_prompt_from_module("browser_operator_prompt", DEFAULT_BROWSER_OPERATOR_PROMPT)
PROMPT_QA_VALIDATOR = load_prompt_from_module("qa_validator_prompt", DEFAULT_QA_VALIDATOR_PROMPT)


def init_model_client(task: str = "") -> OpenAIChatCompletionClient:
    """Initialize OpenAI chat completion client with intelligent routing.

    Args:
        task: Task description (optional, used for model selection)

    Returns:
        OpenAIChatCompletionClient configured with appropriate model
    """
    # Use shared model initialization utility
    return shared_init_model_client("playwright", task)


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
    ui_bind_host = (ui_host or os.getenv("MCP_UI_HOST") or "127.0.0.1")
    env_port = int(os.getenv("MCP_UI_PORT", "0"))
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

    # Determine goal override from args/env and build final task
    goal_override = task_override or os.getenv("MCP_TASK") or os.getenv("TASK")
    if not goal_override or not goal_override.strip():
        goal_override = "Browse the web and complete the requested task."

    # Initialize model client with task-aware model selection
    # This allows intelligent routing based on task complexity
    try:
        # Operator needs Function Calling for MCP tools - force primary/balanced model
        operator_client = init_model_client(goal_override)
        
        # QA Validator doesn't need tools, can use reasoning model
        # But we'll use the same for consistency since o1 models have issues
        validator_client = init_model_client(goal_override)
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

    # Run Society of Mind multi-agent system with workbench
    async with McpWorkbench(params) as mcp:
        # Initialize MCP tools
        async with create_mcp_server_session(params) as session:
            await session.initialize()
            tools = await mcp_server_tools(server_params=params, session=session)
            tool_names = [getattr(t, "name", "") for t in tools]
            _broadcast(event_server, "status", f"Playwright tools: {tool_names}")

            # Heuristically pick a screenshot tool and tabs tool, if available
            screenshot_tool = next((n for n in tool_names if isinstance(n, str) and 'screenshot' in n.lower()), None)
            tabs_tool_name = next((n for n in tool_names if isinstance(n, str) and 'tabs' in n.lower()), 'browser_tabs')

        # Initialize PreviewManager with event streaming
        preview_mgr = PreviewManager(
            mcp=mcp,
            event_server=event_server,
            screenshot_tool=screenshot_tool,
            tabs_tool_name=tabs_tool_name,
        )

        _broadcast(event_server, "status", "Society of Mind: Browser Operator + QA Validator")

        # Create Browser Operator Agent with MCP tools
        browser_operator = AssistantAgent(
            "BrowserOperator",
            model_client=operator_client,
            workbench=mcp,
            system_message=PROMPT_BROWSER_OPERATOR,
            reflect_on_tool_use=True,
            model_client_stream=True,
        )

        # Create QA Validator Agent (no tools, pure evaluation)
        qa_validator = AssistantAgent(
            "QAValidator",
            model_client=validator_client,
            system_message=PROMPT_QA_VALIDATOR,
        )

        # Inner team termination: wait for "APPROVE" from QA Validator
        inner_termination = TextMentionTermination("APPROVE")
        inner_team = RoundRobinGroupChat(
            [browser_operator, qa_validator],
            termination_condition=inner_termination,
            max_turns=30,  # Safety limit to prevent infinite loops
        )

        # Society of Mind wrapper
        som_agent = SocietyOfMindAgent(
            "society_of_mind",
            team=inner_team,
            model_client=operator_client,  # Use operator client for coordination
        )

        # Outer team (just the SoM agent)
        team = RoundRobinGroupChat([som_agent], max_turns=1)

        _broadcast(event_server, "status", f"Starting task: {goal_override}")

        # Background task for preview updates during execution
        preview_stop = asyncio.Event()
        async def _preview_loop():
            try:
                while not preview_stop.is_set():
                    try:
                        await preview_mgr.maybe_capture_source()
                        await preview_mgr.maybe_capture_screenshot()
                    except Exception:
                        pass
                    await asyncio.sleep(2.5)
            except asyncio.CancelledError:
                pass

        preview_task = asyncio.create_task(_preview_loop())

        try:
            # Stream execution to UI
            async for message in team.run_stream(task=goal_override):
                try:
                    # Extract and broadcast message content
                    if hasattr(message, 'content'):
                        content = message.content
                        if isinstance(content, str):
                            event_server.broadcast("chunk", {"text": content})
                        else:
                            event_server.broadcast("chunk", {"text": str(content)})

                    # Capture screenshots after tool usage
                    msg_str = str(message).lower()
                    if 'browser_' in msg_str or 'tool' in msg_str:
                        try:
                            await preview_mgr.maybe_capture_screenshot()
                        except Exception:
                            pass
                except Exception as e:
                    _broadcast(event_server, "error", f"Message processing error: {e}")

            _broadcast(event_server, "status", "Society of Mind workflow completed")

            # Send final result event for modal display (Playwright uses iframe viewer, but we add this for consistency)
            try:
                event_server.broadcast("agent.completion", {
                    "status": "success",
                    "content": "Browser automation task completed successfully",
                    "tool": "playwright",
                    "timestamp": time.time()
                })
            except Exception:
                pass

            # Only close browser if NOT connecting to existing CDP session
            # Check if args contain --cdp-address (existing browser mode)
            is_cdp_mode = any('--cdp-address' in str(a) or '--cdp' in str(a) for a in args)
            if not is_cdp_mode:
                try:
                    await mcp.call_tool('browser_close', {})
                    _broadcast(event_server, "status", "Browser closed")
                except Exception as e:
                    _broadcast(event_server, "error", f"Failed to close browser: {e}")
            else:
                _broadcast(event_server, "status", "CDP mode: Browser kept open for reuse")

        except Exception as e:
            _broadcast(event_server, "error", f"Execution error: {e}")
            # Try to close browser even on error (unless in CDP mode)
            is_cdp_mode = any('--cdp-address' in str(a) or '--cdp' in str(a) for a in args)
            if not is_cdp_mode:
                try:
                    await mcp.call_tool('browser_close', {})
                except Exception:
                    pass
            raise
        finally:
            preview_stop.set()
            preview_task.cancel()

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
    parser.add_argument("--session-id", dest="session_id", help="Optional session identifier (default: random UUID4)")
    parser.add_argument("--name", dest="name", default="playwright-session", help="Agent session name")
    parser.add_argument("--model", dest="model", default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--system", dest="system", help="Override system prompt text (optional)")
    parser.add_argument("--ui-host", dest="ui_host", help="UI bind host (default: env MCP_UI_HOST or 127.0.0.1)")
    parser.add_argument("--ui-port", dest="ui_port", type=int, help="UI bind port (0 for dynamic; default: env MCP_UI_PORT or 8787)")
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