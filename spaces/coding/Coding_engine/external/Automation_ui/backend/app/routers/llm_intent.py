"""LLM Intent Router - Agentic Desktop Automation via Claude Opus 4.6

Provides a POST /intent endpoint that:
1. Receives natural language text from IntentChatPanel
2. Sends to Claude Opus 4.6 via OpenRouter with MCP tool definitions
3. Runs an agentic loop: LLM → tool_call → execute → result → LLM → ...
4. Returns final summary with executed steps

Uses the same MCP handlers from mcp_server_handoff.py for tool execution.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

import aiohttp
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.ui_memory import (
    cache_element, lookup_element, invalidate_element,
    confirm_element, deny_element, is_trusted,
    get_cache_stats, build_ascii_layout, ocr_text_to_elements,
    get_screen_resolution
)
from app.services.video_agent import video_agent, capture_current_frame, SKIP_TOOLS as VA_SKIP_TOOLS

logger = logging.getLogger(__name__)

# Action tools that execute fire-and-forget (no blocking await in SSE stream)
# These tools dispatch via asyncio.create_task and return instant result.
FIRE_AND_FORGET_TOOLS = {
    "action_click", "action_press", "action_hotkey",
    "action_scroll", "mouse_move",
}

# Background task results for fire-and-forget (latest result per tool)
_ff_background_tasks: Dict[str, asyncio.Task] = {}


# ============================================
# Utility: Quick Screen Hash (no OCR, just pixels)
# ============================================

def _quick_screen_hash() -> Optional[str]:
    """Fast hash of current screen state for change detection. No OCR."""
    try:
        import hashlib
        from app.config import get_settings
        if get_settings().execution_mode == "remote":
            # Remote mode: hash latest frame from StreamFrameCache
            from moire_agents.stream_frame_cache import StreamFrameCache
            frame = StreamFrameCache.get_fresh_frame(monitor_id=0, max_age_ms=3000)
            if frame and frame.data:
                return hashlib.md5(frame.data[:5000].encode()).hexdigest()
            return None
        else:
            import pyautogui
            screenshot = pyautogui.screenshot()
            # Sample every 200th byte for speed (~50KB instead of 6MB)
            data = screenshot.tobytes()
            return hashlib.md5(data[::200]).hexdigest()
    except Exception:
        return None


# ============================================
# Session Task Storage (in-memory, per conversation)
# ============================================

_session_tasks: Dict[str, List[Dict[str, Any]]] = {}

# ============================================
# Intervention System: Pause/Resume/Cancel/Feedback during execution
# ============================================
# _pending_interventions: queued actions per conversation (cancel, feedback, skip_task)
# _execution_state: asyncio.Event per conversation (set=running, clear=paused)

_pending_interventions: Dict[str, List[Dict[str, Any]]] = {}
_execution_state: Dict[str, asyncio.Event] = {}

# Click-Confirmation: tracks last recall_element result per conversation
# Used to correlate action_click with a cached element for user confirmation
_last_recall: Dict[str, Dict[str, Any]] = {}


def _extract_element_from_prompt(prompt: str) -> Optional[str]:
    """Try to extract a UI element name from a vision/find prompt.
    Used for recall-first optimization in vision_analyze."""
    import re
    prompt_lower = prompt.lower()
    # Patterns like "find the Save button", "where is the File menu", "click OK"
    patterns = [
        r'(?:find|finde|wo ist|where is|locate|suche)\s+(?:the |den |die |das )?["\']?(.+?)["\']?\s*(?:button|knopf|menu|menü|icon|tab|link|feld|field)?$',
        r'(?:klick|click)\s+(?:on |auf )?(?:the |den |die |das )?["\']?(.+?)["\']?$',
        r'["\'](.+?)["\']',  # Anything in quotes
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt_lower, re.IGNORECASE)
        if match:
            element = match.group(1).strip()
            if 2 < len(element) < 50:  # Reasonable element name length
                return element
    return None

router = APIRouter()

# Load .env
_env_file = Path(__file__).parent.parent.parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        pass

# Explicitly load mcp_server_handoff from backend/moire_agents (NOT moire_tracker)
import importlib.util
MCP_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "moire_agents"
))
_handoff_path = os.path.join(MCP_PATH, "mcp_server_handoff.py")
_spec = importlib.util.spec_from_file_location("mcp_server_handoff_local", _handoff_path)
_handoff_mod = importlib.util.module_from_spec(_spec)
# Add moire_agents to sys.path for its own imports
if MCP_PATH not in sys.path:
    sys.path.insert(0, MCP_PATH)
try:
    _spec.loader.exec_module(_handoff_mod)
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning(f"mcp_server_handoff not available: {_e}")
    _handoff_mod = None

# ============================================
# Config
# ============================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_ITERATIONS = 50

def _get_llm_model() -> str:
    try:
        from app.config import get_settings
        return get_settings().llm_model
    except Exception:
        return "anthropic/claude-opus-4"

def _get_compaction_model() -> str:
    try:
        from app.config import get_settings
        return get_settings().compaction_model
    except Exception:
        return "anthropic/claude-sonnet-4"

# ============================================
# Conversation Memory Store (Persistent + Rolling Compaction)
# ============================================
# Two-tier memory like Claude Code:
#   - "summary": Rolling compressed summary of the entire conversation so far
#   - "recent": Last N verbatim exchanges (user + assistant)
# When recent grows beyond COMPACT_THRESHOLD, older entries get compressed
# into the summary by the LLM. This allows infinite-length sessions.
#
# Persisted to disk as JSON so conversations survive server restarts.

MEMORY_DIR = Path(__file__).parent.parent.parent / "conversation_memory"
MEMORY_DIR.mkdir(exist_ok=True)

RECENT_KEEP = 6       # Keep last 6 exchanges verbatim (user+assistant pairs)
COMPACT_THRESHOLD = 10 # Trigger compaction when recent exceeds this
MAX_SUMMARY_CHARS = 4000  # Max chars for the rolling summary
MAX_RECENT_CHARS = 6000   # Max chars for recent messages block


def _memory_path(conversation_id: str) -> Path:
    """Get the file path for a conversation's memory."""
    safe_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in conversation_id)
    return MEMORY_DIR / f"{safe_id}.json"


def load_conversation(conversation_id: str) -> Dict[str, Any]:
    """Load conversation from disk. Returns {summary: str, recent: list}."""
    path = _memory_path(conversation_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "summary": data.get("summary", ""),
                "recent": data.get("recent", []),
                "turn_count": data.get("turn_count", 0),
            }
        except (json.JSONDecodeError, OSError):
            pass
    return {"summary": "", "recent": [], "turn_count": 0}


def save_conversation(conversation_id: str, data: Dict[str, Any]) -> None:
    """Save conversation to disk."""
    path = _memory_path(conversation_id)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to save conversation {conversation_id}: {e}")


async def compact_conversation(conversation_id: str) -> None:
    """Compress older recent messages into the rolling summary using the LLM.
    This is the key to infinite-length sessions."""
    data = load_conversation(conversation_id)
    recent = data["recent"]

    if len(recent) <= COMPACT_THRESHOLD:
        return  # Nothing to compact

    # Split: older messages to compress, recent to keep
    to_compress = recent[:-RECENT_KEEP]
    to_keep = recent[-RECENT_KEEP:]

    # Build the text to summarize
    old_summary = data["summary"]
    compress_lines = []
    for entry in to_compress:
        compress_lines.append(f"[{entry['role'].upper()}]: {entry['content']}")
    compress_text = "\n".join(compress_lines)

    # Ask a fast model to create the compressed summary
    prompt = f"""Fasse den folgenden Gespraechsverlauf in eine knappe Zusammenfassung zusammen.
Behalte alle wichtigen Fakten, Entscheidungen, Nutzerpraeferenzen und den aktuellen Aufgabenstatus.
Maximal 2000 Zeichen. Schreib auf Deutsch.

{"BISHERIGE ZUSAMMENFASSUNG:" + chr(10) + old_summary + chr(10) + chr(10) if old_summary else ""}NEUE NACHRICHTEN ZUM KOMPRIMIEREN:
{compress_text}

ZUSAMMENFASSUNG:"""

    try:
        response = await call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model=_get_compaction_model(),  # Configurable via COMPACTION_MODEL
            max_tokens=1024
        )
        new_summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if new_summary:
            # Truncate if needed
            if len(new_summary) > MAX_SUMMARY_CHARS:
                new_summary = new_summary[:MAX_SUMMARY_CHARS] + "..."
            data["summary"] = new_summary
            data["recent"] = to_keep
            save_conversation(conversation_id, data)
            logger.info(f"[Memory] Compacted conversation {conversation_id}: "
                        f"{len(to_compress)} entries -> summary ({len(new_summary)} chars), "
                        f"{len(to_keep)} recent kept")
    except Exception as e:
        logger.error(f"[Memory] Compaction failed for {conversation_id}: {e}")
        # Fallback: just truncate without LLM summarization
        fallback_summary = old_summary
        for entry in to_compress:
            line = f"- {entry['role']}: {entry['content'][:100]}"
            if len(fallback_summary) + len(line) < MAX_SUMMARY_CHARS:
                fallback_summary += "\n" + line
        data["summary"] = fallback_summary
        data["recent"] = to_keep
        save_conversation(conversation_id, data)

SYSTEM_PROMPT = """Du bist ein Desktop-Automations-Agent auf einem Windows-PC.

WICHTIGSTE REGEL - Immer diese Pipeline befolgen:
1. OBSERVE: Starte mit screen_layout (schnell!) oder vision_analyze (genau) um den Bildschirm zu sehen
2. PLAN: Erstelle einen Plan basierend auf dem was du TATSAECHLICH siehst
3. EXECUTE: Fuehre den Plan Schritt fuer Schritt aus
4. VERIFY: Prüfe ob die Aktion geklappt hat (action_click meldet automatisch wenn nichts passiert!)
5. CORRECT: Falls nicht → erkenne was schiefging und korrigiere

TASK-LISTE - Zeige dem User was du tust:
  Bei mehrstufigen Aufgaben: Rufe update_tasks am Anfang auf um die Task-Liste zu erstellen.
  Aktualisiere den Status nach jedem Schritt. Der User sieht Live-Fortschritt!
  Beispiel: Aufgabe "Notepad oeffnen und Hello schreiben":
    1. update_tasks([{id:1, title:"Notepad öffnen", status:"in_progress"}, {id:2, title:"Hello schreiben", status:"pending"}])
    2. ... Notepad öffnen ...
    3. update_tasks([{id:1, title:"Notepad öffnen", status:"done"}, {id:2, title:"Hello schreiben", status:"in_progress"}])
    4. ... Hello schreiben ...
    5. update_tasks([{id:1, ..., status:"done"}, {id:2, ..., status:"done"}])

GEDAECHTNIS-SYSTEM (UI Memory) - Evolutionaeres Lernen:
  Du hast ein persistentes Gedaechtnis fuer UI-Element-Positionen!
  Buttons, Menues und andere Elemente sind auf dem gleichen PC IMMER an der gleichen Stelle.
  - recall_element: Schaut im Gedaechtnis nach → SOFORT, kein OCR noetig! Immer ZUERST probieren.
  - screen_layout: ASCII-Karte des Bildschirms (100x30 Zeichen) → viel billiger als screenshot/vision
  - memory_stats: Zeigt was im Gedaechtnis gecached ist
  - vision_analyze: Prueft automatisch das Gedaechtnis BEVOR es Gemini Vision aufruft!

  EVOLUTION: Je mehr du arbeitest, desto schneller wirst du:
  - Jeder screen_find speichert gefundene Elemente + generiert ASCII-Layout
  - Jeder vision_analyze-Aufruf prueft zuerst den Cache → spart Gemini-Kosten
  - Jeder action_click meldet ob sich der Bildschirm veraendert hat → schlechte Coords werden erkannt
  - Nach 50+ Befehlen kennt das System fast alle Elemente auf diesem PC!

  Reihenfolge bei "klick auf X":
  1. recall_element("X") → wenn Cache-Hit: direkt action_click(x,y) → FERTIG (2 Calls statt 4!)
  2. Falls Cache-Miss: screen_layout → finde X in der ASCII-Karte → action_click
  3. Nur wenn beides versagt: screen_find("X") oder vision_analyze (teuer!)

CLICK-WARNUNG: action_click meldet automatisch wenn sich der Bildschirm NICHT veraendert hat!
  Wenn screen_changed=false: Die Koordinaten waren falsch. Nutze screen_find/vision_analyze um
  die richtigen Koordinaten zu finden. NICHT einfach nochmal klicken!

PROGRESSIVE SUCHE - Viewport Narrowing:
  Wenn du ein Element NICHT findest oder unsicher bist:
  1. vision_analyze(prompt="Finde X", mode="element_detection") → grobe Position
  2. vision_analyze(prompt="Finde X praezise", viewport={x:..., y:..., width:400, height:400}) → genau reinzoomen
  3. mouse_move(x, y) zum erkannten Ziel → Video Agent validiert automatisch
  4. Falls noch unsicher: viewport weiter verkleinern (200x200) und nochmal vision_analyze
  5. action_click erst wenn du sicher bist (confidence > 0.8)
  Viewport-Koordinaten sind absolute Bildschirm-Pixel. Die Analyse gibt absolute Koordinaten zurueck.

STUFE 1 - Direkte Aktionen (fuer einfache, klare Aufgaben):
  recall_element, screen_layout, screen_read, screen_find, action_click, action_type, action_press,
  action_hotkey, action_scroll, get_focus, shell_exec, wait, update_tasks

STUFE 2 - Intelligente Agenten (fuer komplexe, mehrstufige Aufgaben):
  - plan_task: Erstellt einen durchdachten Plan mit Planner+Critic Debatte
  - execute_plan: Fuehrt einen Plan Schritt fuer Schritt aus
  - vision_analyze: Analysiert den Bildschirm mit KI-Vision (teuer! Prueft erst Cache!)
  - full_task: Fuehrt eine komplexe Aufgabe vollautomatisch aus

KOMMUNIKATION - Clawdbot-System:
  - send_message, search_contacts, get_contact_info: Nachrichten ueber WhatsApp, Telegram, Discord, Signal
  - browser_open, browser_search, browser_read_page: URLs oeffnen, Websuche, Seiteninhalte lesen
  - report_findings: Ergebnisse an Kontakt senden oder als Callback zurueckgeben

Entscheidungshilfe:
- "klick auf Speichern" → recall_element("Speichern") → action_click (2 Calls, sofort!)
- "was ist auf dem Bildschirm?" → screen_layout (schnell) oder vision_analyze (detailliert)
- "oeffne Notepad und schreib Hello" → update_tasks (2 Tasks) → shell_exec → action_type → update_tasks (done)
- "installiere Python" → update_tasks → vision_analyze → full_task (autonom) → update_tasks
- "schick Peter eine Nachricht" → send_message (Kommunikation)

Regeln:
- IMMER recall_element ZUERST probieren fuer bekannte UI-Elemente (Buttons, Menues, Icons)
- Bei mehrstufigen Aufgaben IMMER update_tasks aufrufen fuer Live-Fortschritt
- screen_layout statt screen_read/vision_analyze wenn nur Orientierung noetig
- vision_analyze NUR wenn wirklich visuelle Analyse noetig (Farben, Icons, komplexes Layout)
- Wenn action_click screen_changed=false meldet → Koordinaten korrigieren, NICHT blind wiederholen
- Plane basierend auf dem tatsaechlichen Bildschirminhalt, nicht auf Annahmen
- Wenn eine App einen Startbildschirm/Splash zeigt, erkenne das und handle es
- Antworte kurz und praezise auf Deutsch
- Bei Nachrichten-Intents nutze IMMER send_message statt Desktop-Automation
- Bei Browser-Intents nutze browser_open/browser_search statt Desktop-Automation"""


# ============================================
# Request/Response Models
# ============================================

class IntentRequest(BaseModel):
    """Request for LLM intent processing."""
    text: str = Field(..., description="Natural language command")
    conversation_id: Optional[str] = Field(None, description="Session ID for context")
    video_agent: Optional[bool] = Field(None, description="Enable video agent (None=use config default)")


class IntentStep(BaseModel):
    """A single step executed by the agent."""
    tool: str
    params: Dict[str, Any] = {}
    result: Dict[str, Any] = {}
    success: bool = False


class IntentResponse(BaseModel):
    """Response from LLM intent processing."""
    success: bool
    summary: str
    steps: List[IntentStep] = []
    duration_ms: float = 0
    model: str = "configurable"
    iterations: int = 0
    error: Optional[str] = None


class InterventionRequest(BaseModel):
    """Request for user intervention during agent execution."""
    conversation_id: str = Field(..., description="Active conversation/session ID")
    action: str = Field(..., description="pause, resume, cancel, skip_task, feedback")
    data: Optional[Dict[str, Any]] = Field(None, description="Extra data, e.g. {message: 'klick lieber auf X'}")


# ============================================
# Tool Definitions (OpenAI/OpenRouter format)
# ============================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "screen_read",
            "description": "Capture screenshot and read all visible text from screen using OCR. Returns the text content visible on screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monitor_id": {
                        "type": "integer",
                        "description": "Monitor index (0=primary, 1=secondary). Default: 0"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screen_find",
            "description": "Find a UI element on screen by text or description. Returns coordinates if found.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Element to find (e.g., 'Submit button', 'Yes', 'File menu')"
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "action_click",
            "description": "Click at specific screen coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button. Default: left"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "action_type",
            "description": "Type text at current cursor position (uses clipboard paste for reliability).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "action_press",
            "description": "Press a keyboard key (enter, tab, escape, backspace, delete, up, down, left, right, f1-f12, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key to press (e.g., 'enter', 'tab', 'escape', 'f5')"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "action_hotkey",
            "description": "Press a keyboard shortcut/combination (e.g., ctrl+c, alt+tab, ctrl+shift+s, win+r).",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Key combination (e.g., 'ctrl+c', 'alt+f4', 'win+r')"}
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "action_scroll",
            "description": "Scroll mouse wheel up or down at current or specified position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
                    "amount": {"type": "integer", "description": "Scroll clicks (default: 3)"},
                    "x": {"type": "integer", "description": "Optional X coordinate"},
                    "y": {"type": "integer", "description": "Optional Y coordinate"}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_move",
            "description": "Move the mouse cursor smoothly to a position without clicking. Use to hover, preview, or navigate visually before clicking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Target X coordinate"},
                    "y": {"type": "integer", "description": "Target Y coordinate"},
                    "duration": {"type": "number", "description": "Movement duration in seconds (default: 0.5, max: 2.0)"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_focus",
            "description": "Get the currently active/focused window. Returns window title and process info.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_focus",
            "description": "Bring a window to the foreground by its title (partial match). Use to restore focus after UI interruptions or to switch between apps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title or partial match (e.g., 'Word', 'Chrome', 'Explorer')"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "List all visible windows with their titles. Use to find the correct window title before set_focus.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Execute a shell command (PowerShell on Windows). Returns stdout, stderr, exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait/sleep for a specified duration before next action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Duration to wait in seconds"}
                },
                "required": ["seconds"]
            }
        }
    },
    # Clawdbot Messaging Tools
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to a contact via messaging platform (WhatsApp, Telegram, Discord, Signal, etc.). "
                           "Resolves contact names with fuzzy matching. Use this instead of desktop automation for messaging.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Contact name, alias, or key (e.g., 'Peter', 'boss', 'mama'). Supports fuzzy matching."},
                    "message": {"type": "string", "description": "Message text to send"},
                    "platform": {
                        "type": "string",
                        "enum": ["whatsapp", "telegram", "discord", "signal", "imessage", "email"],
                        "description": "Messaging platform. If omitted, uses the first available platform for the contact."
                    }
                },
                "required": ["recipient", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search contacts by name or alias with fuzzy matching. Returns matching contacts with their available platforms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (name, alias, or partial match)"},
                    "limit": {"type": "integer", "description": "Max results (default: 5)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact_info",
            "description": "Get detailed information about a specific contact including all messaging platform IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Contact name, alias, or key"},
                    "platform": {"type": "string", "description": "Optional: specific platform to resolve recipient ID for"}
                },
                "required": ["name"]
            }
        }
    },
    # Clawdbot Browser Tools
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "Open a URL in the browser. Use this instead of Win+R for opening websites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open (e.g., 'https://google.com', 'github.com')"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "Search the web for a query. Opens a Google search with the given terms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'weather Berlin', 'Python documentation')"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_read_page",
            "description": "Read the content/text of the currently open browser page using OCR. Returns visible text on screen.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    # Clawdbot Reporting Tool
    {
        "type": "function",
        "function": {
            "name": "report_findings",
            "description": "Report/send findings, results, or gathered information to a contact via messaging or as callback. "
                           "Use this after browser searches, page reads, or any operation where you want to communicate the results. "
                           "If no recipient is specified, the findings are sent back via the Clawdbot callback channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "string",
                        "description": "The information/results to report (text summary of what was found)"
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Optional: contact name to send findings to (e.g., 'Peter', 'boss'). If omitted, sends via callback."
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["whatsapp", "telegram", "discord", "signal", "email"],
                        "description": "Optional: messaging platform. If omitted, uses first available for contact."
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional: short title/subject for the report (e.g., 'Wetter Berlin', 'Suchergebnis')"
                    }
                },
                "required": ["findings"]
            }
        }
    },
    # Moire Agents - High-Level Tools
    {
        "type": "function",
        "function": {
            "name": "plan_task",
            "description": "Create an intelligent plan for a complex multi-step desktop task. Uses Planner+Critic debate to produce a validated action plan. Use this for tasks that require multiple steps, opening apps, navigating UIs, or any non-trivial workflow. Returns a list of steps with confidence score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "What to accomplish (e.g., 'Open Notepad, type Hello World, save as test.txt')"},
                    "context": {"type": "object", "description": "Optional context like current window, user preferences"}
                },
                "required": ["goal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_plan",
            "description": "Execute a plan (list of action steps) on the desktop. Each step can be: hotkey, sleep, write, press, click, find_and_click. Use after plan_task to execute the generated plan, or provide your own steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["hotkey", "sleep", "write", "press", "click", "find_and_click"]},
                                "description": {"type": "string"},
                                "keys": {"type": "string"},
                                "text": {"type": "string"},
                                "key": {"type": "string"},
                                "x": {"type": "integer"},
                                "y": {"type": "integer"},
                                "target": {"type": "string"},
                                "duration": {"type": "number"}
                            },
                            "required": ["type", "description"]
                        },
                        "description": "List of action steps to execute"
                    }
                },
                "required": ["plan"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vision_analyze",
            "description": "Analyze the current screen using Vision AI. Supports viewport cropping for progressive search - start with full screen, then narrow down to find elements precisely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "What to analyze (e.g., 'What apps are open?', 'Is there an error dialog?', 'Find the save button')"},
                    "mode": {
                        "type": "string",
                        "enum": ["element_detection", "state_analysis", "task_planning", "custom"],
                        "description": "Analysis mode. element_detection=find UI elements, state_analysis=understand current state, task_planning=suggest actions, custom=answer your prompt. Default: custom"
                    },
                    "monitor_id": {"type": "integer", "description": "Monitor to analyze (0=primary, 1=secondary). Default: 0"},
                    "viewport": {
                        "type": "object",
                        "description": "Restrict analysis to a screen region for precise element finding. Coordinates are absolute screen pixels. Returned element positions are already in absolute coordinates.",
                        "properties": {
                            "x": {"type": "integer", "description": "Left edge X"},
                            "y": {"type": "integer", "description": "Top edge Y"},
                            "width": {"type": "integer", "description": "Viewport width"},
                            "height": {"type": "integer", "description": "Viewport height"}
                        },
                        "required": ["x", "y", "width", "height"]
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "full_task",
            "description": "Execute a complex desktop task with automatic planning, execution, visual verification, and re-planning if needed. Uses the full Moire Agent reflection loop. Best for complex multi-step tasks where you want autonomous execution with self-correction. WARNING: This runs autonomously for up to 3 rounds - use for complex tasks only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Complete task description (e.g., 'Open Chrome, go to github.com, search for python repos')"},
                    "max_rounds": {"type": "integer", "description": "Max reflection rounds (default: 3). Each round = plan + execute + verify."},
                    "actions_per_round": {"type": "integer", "description": "Max actions per round (default: 3)"}
                },
                "required": ["goal"]
            }
        }
    },
    # UI Memory Tools - Cache + ASCII Layout (reduce vision/OCR calls)
    {
        "type": "function",
        "function": {
            "name": "recall_element",
            "description": "Look up a UI element position from memory cache. FAST - no OCR needed! "
                           "Elements like 'Save button' in Word are always at the same pixel coordinates on the same PC. "
                           "Returns cached {x, y} if known, or falls back to screen_find if not cached yet. "
                           "ALWAYS try this BEFORE screen_find for known UI elements (buttons, menus, icons).",
            "parameters": {
                "type": "object",
                "properties": {
                    "element": {
                        "type": "string",
                        "description": "Element to find (e.g., 'Save button', 'File menu', 'Close button', 'OK button')"
                    }
                },
                "required": ["element"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screen_layout",
            "description": "Get a compact ASCII map of the current screen layout. "
                           "Much cheaper and faster than screen_read or vision_analyze! "
                           "Returns an 100x30 character grid showing where UI elements and text are positioned. "
                           "Each character represents ~19x36 pixels. Use this for quick orientation before clicking. "
                           "Also caches all found element positions automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monitor_id": {
                        "type": "integer",
                        "description": "Monitor index (0=primary). Default: 0"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_stats",
            "description": "Show UI element cache statistics - how many elements are cached, which apps, total cache hits. "
                           "Useful to understand what the agent remembers about this PC's UI layout.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    # Session Task List Tool
    {
        "type": "function",
        "function": {
            "name": "update_tasks",
            "description": "Create or update the task list for the current session. "
                           "Use this to show the user what you're doing step by step. "
                           "Call at the START of a multi-step task to create the list, "
                           "then call again as each task completes. The user sees live progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer", "description": "Task number (1, 2, 3...)"},
                                "title": {"type": "string", "description": "Short task description"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "done", "failed"],
                                    "description": "Current status"
                                }
                            },
                            "required": ["id", "title", "status"]
                        },
                        "description": "Full task list with current statuses"
                    }
                },
                "required": ["tasks"]
            }
        }
    }
]


# ============================================
# Clawdbot Tool Execution (Messaging + Browser)
# ============================================

CLAWDBOT_API_BASE = "http://localhost:8007/api/clawdbot"


async def _execute_browser_open(url: str) -> Dict[str, Any]:
    """Open a URL in the browser via Clawdbot."""
    try:
        # Ensure URL has scheme
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CLAWDBOT_API_BASE}/command",
                json={
                    "command": f"open {url}",
                    "user_id": "llm_agent",
                    "platform": "browser"
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()

        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "url": url
        }
    except Exception as e:
        logger.error(f"Browser open error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_browser_search(query: str) -> Dict[str, Any]:
    """Search the web via Clawdbot."""
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CLAWDBOT_API_BASE}/command",
                json={
                    "command": f"open {search_url}",
                    "user_id": "llm_agent",
                    "platform": "browser"
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()

        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "query": query,
            "url": search_url
        }
    except Exception as e:
        logger.error(f"Browser search error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_browser_read_page() -> Dict[str, Any]:
    """Read the current browser page content via screen OCR."""
    try:
        result = await _handoff_mod.handle_read_screen(monitor_id=0)
        result.pop("screenshot_base64", None)
        return {
            "success": result.get("success", False),
            "text": result.get("text", ""),
            "text_length": result.get("text_length", 0),
            "source": "screen_ocr"
        }
    except Exception as e:
        logger.error(f"Browser read page error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_clawdbot_send(
    recipient: str,
    message: str,
    platform: Optional[str] = None
) -> Dict[str, Any]:
    """Send a message via Clawdbot. Calls the existing REST API."""
    try:
        async with aiohttp.ClientSession() as session:
            # Resolve contact first
            params = {}
            if platform:
                params["platform"] = platform

            async with session.post(
                f"{CLAWDBOT_API_BASE}/contacts/{recipient}/resolve",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 404:
                    return {
                        "success": False,
                        "error": f"Contact '{recipient}' not found. Use search_contacts to find contacts."
                    }
                resolve_data = await resp.json()

            if not resolve_data.get("found"):
                suggestions = resolve_data.get("suggestions", [])
                return {
                    "success": False,
                    "error": f"Contact '{recipient}' not found.",
                    "suggestions": suggestions
                }

            contact = resolve_data["contact"]
            contact_name = contact.get("name", recipient)

            # Determine target platform
            target_platform = platform
            recipient_id = None

            if platform:
                recipient_id = contact.get(platform.lower())

            if not recipient_id:
                for p in ["whatsapp", "telegram", "discord", "signal", "imessage", "email"]:
                    if contact.get(p):
                        target_platform = p
                        recipient_id = contact[p]
                        break

            if not recipient_id:
                available = [p for p in ["whatsapp", "telegram", "discord", "email", "signal"]
                           if contact.get(p)]
                return {
                    "success": False,
                    "error": f"Contact '{contact_name}' has no messaging platform configured.",
                    "available_platforms": available
                }

            # Send via the command endpoint
            async with session.post(
                f"{CLAWDBOT_API_BASE}/command",
                json={
                    "command": f"send to {recipient} {message}",
                    "user_id": "llm_agent",
                    "platform": target_platform
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()

            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "recipient": contact_name,
                "platform": target_platform,
                "recipient_id": recipient_id
            }

    except Exception as e:
        logger.error(f"Clawdbot send error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_clawdbot_search(
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    """Search contacts via Clawdbot API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CLAWDBOT_API_BASE}/contacts/search",
                params={"q": query, "limit": limit},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"API error: {resp.status}"}
                data = await resp.json()

        return {
            "success": True,
            "query": query,
            "results": data.get("results", data)
        }

    except Exception as e:
        logger.error(f"Clawdbot search error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_report_findings(
    findings: str,
    recipient: Optional[str] = None,
    platform: Optional[str] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    """Report findings via Clawdbot - either to a contact or via callback."""
    try:
        # Format the report message
        report_msg = ""
        if title:
            report_msg = f"📋 {title}\n\n"
        report_msg += findings

        # Truncate if too long for messaging (most platforms have limits)
        if len(report_msg) > 4000:
            report_msg = report_msg[:3950] + "\n\n... [gekürzt]"

        if recipient:
            # Send to a specific contact via send_message
            result = await _execute_clawdbot_send(
                recipient=recipient,
                message=report_msg,
                platform=platform
            )
            result["report_type"] = "contact_message"
            return result
        else:
            # Send via Clawdbot callback (to the requesting user/system)
            async with aiohttp.ClientSession() as session:
                callback_payload = {
                    "user_id": "llm_agent",
                    "platform": platform or "api",
                    "success": True,
                    "message": report_msg,
                    "data": {
                        "type": "findings_report",
                        "title": title,
                        "findings_length": len(findings)
                    }
                }

                # Try Clawdbot Gateway callback
                try:
                    async with session.post(
                        "http://localhost:18789/plugins/automation-ui/results",
                        json=callback_payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            return {
                                "success": True,
                                "message": "Ergebnisse über Clawdbot-Callback gesendet",
                                "report_type": "callback",
                                "findings_length": len(findings)
                            }
                except Exception:
                    pass  # Callback endpoint not available

                # Fallback: publish via Redis PubSub
                try:
                    async with session.post(
                        f"{CLAWDBOT_API_BASE}/notify",
                        params={
                            "user_id": "llm_agent",
                            "platform": platform or "api",
                            "message": report_msg,
                            "notification_type": "info"
                        },
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            return {
                                "success": True,
                                "message": "Ergebnisse als Notification gesendet",
                                "report_type": "notification",
                                "findings_length": len(findings)
                            }
                except Exception:
                    pass

                # Final fallback: just confirm the findings are available
                return {
                    "success": True,
                    "message": "Ergebnisse erfasst (kein Callback-Endpoint verfügbar)",
                    "report_type": "local",
                    "findings_preview": findings[:500],
                    "findings_length": len(findings)
                }

    except Exception as e:
        logger.error(f"Report findings error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_clawdbot_contact_info(
    name: str,
    platform: Optional[str] = None
) -> Dict[str, Any]:
    """Get contact info via Clawdbot API."""
    try:
        async with aiohttp.ClientSession() as session:
            params = {}
            if platform:
                params["platform"] = platform

            async with session.post(
                f"{CLAWDBOT_API_BASE}/contacts/{name}/resolve",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 404:
                    return {"success": False, "error": f"Contact '{name}' not found"}
                data = await resp.json()

        if data.get("found"):
            return {
                "success": True,
                "contact": data["contact"],
                "query": name,
                "platform": data.get("platform"),
                "recipient_id": data.get("recipient_id")
            }
        else:
            return {
                "success": False,
                "error": f"Contact '{name}' not found",
                "suggestions": data.get("suggestions", [])
            }

    except Exception as e:
        logger.error(f"Clawdbot contact info error: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# Moire Agent Tool Execution (High-Level)
# ============================================

async def _execute_plan_task(goal: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """Create a plan via Moire PlanningTeam (Planner+Critic debate)."""
    try:
        result = await _handoff_mod.handle_plan(goal=goal, context=context)
        return result
    except Exception as e:
        logger.error(f"plan_task error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_execute_plan(plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute plan steps via Moire (hotkey, sleep, write, press, click, find_and_click)."""
    try:
        result = await _handoff_mod.handle_execute(plan=plan)
        return result
    except Exception as e:
        logger.error(f"execute_plan error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_vision_analyze(
    prompt: str, mode: str = "custom", monitor_id: int = 0,
    viewport: dict = None
) -> Dict[str, Any]:
    """Analyze screen with Gemini Vision AI."""
    try:
        result = await _handoff_mod.handle_vision_analyze(
            prompt=prompt, mode=mode, json_output=True,
            monitor_id=monitor_id, viewport=viewport
        )
        return result
    except Exception as e:
        logger.error(f"vision_analyze error: {e}")
        return {"success": False, "error": str(e)}


async def _execute_full_task(
    goal: str, max_rounds: int = 3, actions_per_round: int = 3
) -> Dict[str, Any]:
    """Execute task with OrchestratorV2 reflection loop (plan → execute → vision verify → replan)."""
    try:
        orch_mod = importlib.import_module("agents.orchestrator_v2")
        orchestrator = orch_mod.get_orchestrator_v2()

        if not getattr(orchestrator, '_started', False):
            await orchestrator.start()

        result = await orchestrator.execute_task_with_reflection(
            goal=goal,
            max_reflection_rounds=max_rounds,
            actions_per_round=actions_per_round
        )
        return result
    except Exception as e:
        logger.error(f"full_task error: {e}")
        return {"success": False, "error": str(e)}


# ============================================
# Streaming Action Type - Real-time typing visibility
# ============================================

async def _stream_action_type(text: str, chunk_size: int = 5) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Type text in chunks, yielding SSE-ready events for each chunk.
    The user sees text appearing in real-time in the UI.

    Uses clipboard paste per chunk for reliability (same as normal action_type).
    Yields dicts with type="typing_stream" for each chunk typed.
    Final yield has type="typing_done" with full summary.
    """
    import pyautogui
    import pyperclip

    if not text:
        yield {"type": "typing_done", "text": "", "total_chars": 0, "chunks_typed": 0}
        return

    # Split text into lines first, then words within lines
    lines = text.split("\n")
    chunks = []
    for line_idx, line in enumerate(lines):
        if not line.strip():
            # Preserve empty lines
            chunks.append("\n")
            continue
        words = line.split(" ")
        # Group words into chunks
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            # Add newline after each line except the last
            if i + chunk_size >= len(words) and line_idx < len(lines) - 1:
                chunk_text += "\n"
            chunks.append(chunk_text)

    # If text is very short (single chunk), just type it all at once
    if len(chunks) <= 1:
        try:
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            yield {
                "type": "typing_stream",
                "chunk": text,
                "typed_so_far": text,
                "progress": 1.0,
                "chunk_index": 0,
                "total_chunks": 1
            }
            yield {
                "type": "typing_done",
                "text": text,
                "total_chars": len(text),
                "chunks_typed": 1,
                "success": True
            }
        except Exception as e:
            yield {"type": "typing_done", "text": text, "success": False, "error": str(e)}
        return

    # Type chunk by chunk
    typed_so_far = ""
    for idx, chunk in enumerate(chunks):
        try:
            pyperclip.copy(chunk)
            pyautogui.hotkey('ctrl', 'v')
            typed_so_far += chunk
            progress = (idx + 1) / len(chunks)

            yield {
                "type": "typing_stream",
                "chunk": chunk,
                "typed_so_far": typed_so_far,
                "progress": round(progress, 2),
                "chunk_index": idx,
                "total_chunks": len(chunks)
            }

            # Small delay between chunks so UI can update and desktop can process
            if idx < len(chunks) - 1:
                await asyncio.sleep(0.08)

        except Exception as e:
            yield {
                "type": "typing_done",
                "text": text,
                "typed_so_far": typed_so_far,
                "success": False,
                "error": str(e),
                "chunks_typed": idx
            }
            return

    yield {
        "type": "typing_done",
        "text": text,
        "total_chars": len(text),
        "chunks_typed": len(chunks),
        "success": True
    }


# ============================================
# Tool Execution
# ============================================

def _shell_exec_local(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell command locally using Popen. GUI apps launch without blocking."""
    import subprocess
    cmd = arguments.get("command", "")
    timeout = arguments.get("timeout", 30)
    try:
        proc = subprocess.Popen(
            ["powershell", "-Command", cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        try:
            stdout, stderr = proc.communicate(timeout=min(timeout, 10))
            return {
                "success": proc.returncode == 0,
                "stdout": stdout[:2000] if stdout else "",
                "stderr": stderr[:500] if stderr else "",
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            # Process still running — likely a GUI app, that's OK
            return {
                "success": True,
                "pid": proc.pid,
                "message": f"Process launched (PID {proc.pid}), still running",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _execute_approved_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an APPROVAL tool after user approved it. Bypasses ActionRouter pre-check."""
    if name == "shell_exec":
        # In remote mode: delegate to desktop client after approval
        from app.services.action_router import action_router
        if action_router.is_remote:
            return await action_router._execute_remote(name, arguments)
        # Local mode: use Popen so GUI apps can launch
        return _shell_exec_local(arguments)
    elif name == "send_message":
        return await _execute_clawdbot_send(
            recipient=arguments.get("recipient", ""),
            message=arguments.get("message", ""),
            platform=arguments.get("platform")
        )
    elif name == "report_findings":
        return await _execute_report_findings(
            findings=arguments.get("findings", ""),
            recipient=arguments.get("recipient"),
            platform=arguments.get("platform"),
            title=arguments.get("title")
        )
    return {"success": False, "error": f"Unknown approval tool: {name}"}


async def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool and return the result."""
    try:
        # Remote mode: delegate DELEGATED/APPROVAL tools to desktop client
        from app.services.action_router import action_router
        if action_router.is_remote:
            from app.services.tool_safety import ToolRisk
            risk = action_router.get_risk(name)
            if risk == ToolRisk.DELEGATED:
                result = await action_router.execute(name, arguments)
                if result.get("_route") != "local":
                    return result
            elif risk == ToolRisk.APPROVAL:
                return {
                    "_approval_required": True,
                    "tool": name,
                    "arguments": arguments,
                    "message": f"Tool '{name}' requires user approval in remote mode",
                }

        if name == "screen_read":
            result = await _handoff_mod.handle_read_screen(
                monitor_id=arguments.get("monitor_id", 0)
            )
            # Strip base64 screenshot from result to save tokens
            result.pop("screenshot_base64", None)
            return result

        elif name == "screen_find":
            target = arguments.get("target", "")
            result = await _handoff_mod.handle_validate(target=target)
            # Auto-cache successful screen_find results
            app_ctx = "unknown"
            if result.get("success") and result.get("element_location"):
                try:
                    focus = await _handoff_mod.handle_get_focus()
                    app_ctx = focus.get("title", "") or focus.get("process", "unknown")
                    loc = result["element_location"]
                    cache_element(app_ctx, target, loc.get("x", 0), loc.get("y", 0),
                                  result.get("overall_confidence", 0.8))
                except Exception:
                    pass

            # Also build ASCII layout from current screen (leverages the screenshot already taken)
            try:
                screen_data = await _handoff_mod.handle_read_screen(monitor_id=0)
                ocr_text = screen_data.get("text", "")
                ss = screen_data.get("screenshot_size", {})
                sw, sh = ss.get("width", 1920), ss.get("height", 1080)
                if ocr_text:
                    elements = ocr_text_to_elements(ocr_text, sw, sh)
                    ascii_map = build_ascii_layout(elements, sw, sh, app_ctx)
                    result["ascii_layout"] = ascii_map
                    result["layout_elements_count"] = len(elements)
            except Exception as e:
                logger.debug(f"[screen_find] ASCII layout generation failed: {e}")

            return result

        elif name == "action_click":
            # Fire-and-forget: execute click, no blocking change detection
            result = await _handoff_mod.handle_action("click", {
                "x": arguments.get("x", 0),
                "y": arguments.get("y", 0),
                "button": arguments.get("button", "left")
            })
            return result

        elif name == "action_type":
            return await _handoff_mod.handle_action("type", {
                "text": arguments.get("text", "")
            })

        elif name == "action_press":
            return await _handoff_mod.handle_action("press", {
                "key": arguments.get("key", "enter")
            })

        elif name == "action_hotkey":
            return await _handoff_mod.handle_action("hotkey", {
                "keys": arguments.get("keys", "")
            })

        elif name == "action_scroll":
            return await _handoff_mod.handle_scroll(
                direction=arguments.get("direction", "down"),
                amount=arguments.get("amount", 3),
                x=arguments.get("x"),
                y=arguments.get("y")
            )

        elif name == "get_focus":
            return await _handoff_mod.handle_get_focus()

        elif name == "set_focus":
            return await _handoff_mod.handle_set_focus(
                window_title=arguments.get("title", "")
            )

        elif name == "list_windows":
            return await _handoff_mod.handle_list_windows()

        elif name == "mouse_move":
            return await _handoff_mod.handle_mouse_move(
                x=arguments.get("x", 0),
                y=arguments.get("y", 0),
                duration=arguments.get("duration", 0.5)
            )

        elif name == "shell_exec":
            return _shell_exec_local(arguments)

        elif name == "wait":
            seconds = arguments.get("seconds", 1)
            actual = float(seconds) * 0.25  # reduced to 0.5s for 2s waits
            await asyncio.sleep(actual)
            return {"success": True, "waited": seconds, "actual": actual}

        # Clawdbot Messaging Tools
        elif name == "send_message":
            return await _execute_clawdbot_send(
                recipient=arguments.get("recipient", ""),
                message=arguments.get("message", ""),
                platform=arguments.get("platform")
            )

        elif name == "search_contacts":
            return await _execute_clawdbot_search(
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 5)
            )

        elif name == "get_contact_info":
            return await _execute_clawdbot_contact_info(
                name=arguments.get("name", ""),
                platform=arguments.get("platform")
            )

        # Clawdbot Browser Tools
        elif name == "browser_open":
            return await _execute_browser_open(
                url=arguments.get("url", "")
            )

        elif name == "browser_search":
            return await _execute_browser_search(
                query=arguments.get("query", "")
            )

        elif name == "browser_read_page":
            return await _execute_browser_read_page()

        elif name == "report_findings":
            return await _execute_report_findings(
                findings=arguments.get("findings", ""),
                recipient=arguments.get("recipient"),
                platform=arguments.get("platform"),
                title=arguments.get("title")
            )

        # Moire Agent Tools (Stufe 2)
        elif name == "plan_task":
            return await _execute_plan_task(
                goal=arguments.get("goal", ""),
                context=arguments.get("context")
            )

        elif name == "execute_plan":
            return await _execute_execute_plan(
                plan=arguments.get("plan", [])
            )

        elif name == "vision_analyze":
            prompt = arguments.get("prompt", "")
            mode = arguments.get("mode", "custom")

            # Evolutionary learning: try recall FIRST for element-detection prompts
            if mode in ("element_detection", "custom"):
                element_name = _extract_element_from_prompt(prompt)
                if element_name:
                    try:
                        focus_result = await _handoff_mod.handle_get_focus()
                        app_context = focus_result.get("title", "") or focus_result.get("process", "unknown")
                        cached = lookup_element(app_context, element_name)
                        if cached:
                            logger.info(f"[Vision→Recall] Cache HIT for '{element_name}' - skipping Gemini Vision!")
                            return {
                                "success": True,
                                "source": "memory_cache_shortcut",
                                "element_found": True,
                                "element": element_name,
                                "x": cached["x"],
                                "y": cached["y"],
                                "confidence": cached["confidence"],
                                "hits": cached["hits"],
                                "message": f"Element '{element_name}' aus Gedaechtnis gefunden: ({cached['x']},{cached['y']}) - "
                                           f"Vision-Analyse uebersprungen (Cache-Hit #{cached['hits']})",
                                "saved_cost": "Gemini Vision API call avoided"
                            }
                    except Exception:
                        pass  # Fall through to normal vision

            # Normal vision analysis (expensive - Gemini API)
            result = await _execute_vision_analyze(
                prompt=prompt,
                mode=mode,
                monitor_id=arguments.get("monitor_id", 0),
                viewport=arguments.get("viewport")
            )

            # Evolutionary learning: cache any elements detected by vision
            if result.get("success") and result.get("elements"):
                try:
                    focus_result = await _handoff_mod.handle_get_focus()
                    app_context = focus_result.get("title", "") or focus_result.get("process", "unknown")
                    for elem in result.get("elements", []):
                        elem_text = elem.get("text") or elem.get("label") or elem.get("name", "")
                        elem_x = elem.get("x") or elem.get("center_x", 0)
                        elem_y = elem.get("y") or elem.get("center_y", 0)
                        if elem_text and elem_x and elem_y:
                            cache_element(app_context, elem_text, int(elem_x), int(elem_y), 0.85)
                except Exception:
                    pass

            return result

        elif name == "full_task":
            return await _execute_full_task(
                goal=arguments.get("goal", ""),
                max_rounds=arguments.get("max_rounds", 3),
                actions_per_round=arguments.get("actions_per_round", 3)
            )

        # UI Memory Tools
        elif name == "recall_element":
            element_desc = arguments.get("element", "")
            conv_id = arguments.pop("_conversation_id", None)
            # Get current app context from focused window
            try:
                focus_result = await _handoff_mod.handle_get_focus()
                app_context = focus_result.get("title", "") or focus_result.get("process", "unknown")
            except Exception:
                app_context = "unknown"

            # Try cache lookup first (instant, no OCR)
            cached = lookup_element(app_context, element_desc)
            if cached:
                logger.info(f"[UIMemory] Cache HIT: '{element_desc}' in '{app_context}' -> ({cached['x']},{cached['y']}) hits={cached['hits']} trusted={cached.get('trusted')}")
                # Track for click-confirmation (if click follows)
                if conv_id:
                    _last_recall[conv_id] = {
                        "element": element_desc,
                        "app": app_context,
                        "x": cached["x"],
                        "y": cached["y"],
                        "trusted": cached.get("trusted", False),
                        "user_confirmed": cached.get("user_confirmed", 0),
                    }
                return {
                    "success": True,
                    "found": True,
                    "x": cached["x"],
                    "y": cached["y"],
                    "confidence": cached["confidence"],
                    "source": "memory_cache",
                    "hits": cached["hits"],
                    "trusted": cached.get("trusted", False),
                    "message": f"Element '{element_desc}' aus Gedaechtnis: ({cached['x']},{cached['y']}) - {cached['hits']}x bestaetigt"
                }

            # Cache miss - fall back to screen_find (OCR)
            logger.info(f"[UIMemory] Cache MISS: '{element_desc}' in '{app_context}' - falling back to screen_find")
            result = await _handoff_mod.handle_validate(target=element_desc)

            # Cache successful result for next time
            if result.get("success") and result.get("element_location"):
                loc = result["element_location"]
                x, y = loc.get("x", 0), loc.get("y", 0)
                conf = result.get("overall_confidence", 0.8)
                cache_element(app_context, element_desc, x, y, conf)
                # Track for click-confirmation (newly found → not trusted)
                if conv_id:
                    _last_recall[conv_id] = {
                        "element": element_desc,
                        "app": app_context,
                        "x": x, "y": y,
                        "trusted": False,
                        "user_confirmed": 0,
                    }
                return {
                    "success": True,
                    "found": True,
                    "x": x,
                    "y": y,
                    "confidence": conf,
                    "source": "ocr_then_cached",
                    "message": f"Element '{element_desc}' gefunden und im Gedaechtnis gespeichert: ({x},{y})"
                }
            else:
                return {
                    "success": False,
                    "found": False,
                    "source": "ocr_miss",
                    "message": f"Element '{element_desc}' nicht gefunden - weder im Cache noch per OCR"
                }

        elif name == "screen_layout":
            monitor_id = arguments.get("monitor_id", 0)
            try:
                # Get OCR text from screen
                result = await _handoff_mod.handle_read_screen(monitor_id=monitor_id)
                ocr_text = result.get("text", "")
                screen_size = result.get("screenshot_size", {})
                sw = screen_size.get("width", 1920)
                sh = screen_size.get("height", 1080)

                # Get window title for context
                try:
                    focus = await _handoff_mod.handle_get_focus()
                    window_title = focus.get("title", "")
                except Exception:
                    window_title = ""

                # Try to get structured elements from MoireServer
                elements = []
                try:
                    from moire_agents.bridge.websocket_client import MoireWebSocketClient
                    client = MoireWebSocketClient()
                    await client.connect()
                    capture = await client.capture_and_wait_for_complete(timeout=15)
                    if capture.success and capture.ui_context:
                        for elem in capture.ui_context.elements:
                            elements.append({
                                "text": elem.text or "",
                                "x": elem.bounds.get("x", 0) if isinstance(elem.bounds, dict) else getattr(elem.bounds, "x", 0),
                                "y": elem.bounds.get("y", 0) if isinstance(elem.bounds, dict) else getattr(elem.bounds, "y", 0),
                                "width": elem.bounds.get("width", 0) if isinstance(elem.bounds, dict) else getattr(elem.bounds, "width", 0),
                                "height": elem.bounds.get("height", 0) if isinstance(elem.bounds, dict) else getattr(elem.bounds, "height", 0),
                            })
                        # Auto-cache all elements with text
                        for elem in capture.ui_context.elements:
                            if elem.text and elem.text.strip():
                                center = elem.center if hasattr(elem, 'center') else None
                                if center:
                                    cx = center.get("x", 0) if isinstance(center, dict) else getattr(center, "x", 0)
                                    cy = center.get("y", 0) if isinstance(center, dict) else getattr(center, "y", 0)
                                    conf = elem.confidence if hasattr(elem, 'confidence') else 0.8
                                    cache_element(window_title, elem.text.strip(), cx, cy, conf)
                    await client.disconnect()
                except Exception as e:
                    logger.debug(f"[screen_layout] MoireServer unavailable, using OCR text: {e}")

                # Fall back to OCR text if no structured elements
                if not elements and ocr_text:
                    elements = ocr_text_to_elements(ocr_text, sw, sh)

                # Build ASCII layout
                ascii_map = build_ascii_layout(elements, sw, sh, window_title)
                result.pop("screenshot_base64", None)

                return {
                    "success": True,
                    "layout": ascii_map,
                    "elements_count": len(elements),
                    "screen_size": f"{sw}x{sh}",
                    "window": window_title
                }
            except Exception as e:
                logger.error(f"screen_layout error: {e}")
                return {"success": False, "error": str(e)}

        elif name == "memory_stats":
            stats = get_cache_stats()
            return {
                "success": True,
                **stats,
                "message": f"UI-Gedaechtnis: {stats['total_elements']} Elemente gecached, "
                           f"{stats['total_hits']} Cache-Hits, "
                           f"Resolution: {stats['resolution']}, "
                           f"Apps: {', '.join(stats['apps'][:10]) if stats['apps'] else 'keine'}"
            }

        elif name == "update_tasks":
            tasks = arguments.get("tasks", [])
            # Store tasks in session (keyed by conversation_id from outer scope)
            # The conversation_id is not directly available here, so we use a module-level dict
            # and pass it via a special _conversation_id key in arguments (set by the streaming loop)
            conv_id = arguments.get("_conversation_id", "default")
            _session_tasks[conv_id] = tasks
            # Count statuses
            counts = {}
            for t in tasks:
                s = t.get("status", "pending")
                counts[s] = counts.get(s, 0) + 1
            return {
                "success": True,
                "tasks": tasks,
                "counts": counts,
                "message": f"Task-Liste aktualisiert: {len(tasks)} Tasks "
                           f"({counts.get('done', 0)} erledigt, {counts.get('in_progress', 0)} aktiv, "
                           f"{counts.get('pending', 0)} offen)"
            }

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        logger.error(f"Tool execution error ({name}): {e}")
        return {"success": False, "error": str(e)}


# ============================================
# OpenRouter API Client
# ============================================

async def call_openrouter(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: str = None,
    max_tokens: int = 4096
) -> Dict[str, Any]:
    """Call OpenRouter API with tool support."""
    model = model or _get_llm_model()
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://automation-ui.local",
        "X-Title": "Automation UI Intent Processor"
    }

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "max_tokens": max_tokens,
        "temperature": 0.2
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=500)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"OpenRouter error {response.status}: {error_text}")
                raise Exception(f"OpenRouter API error {response.status}: {error_text[:200]}")

            return await response.json()


# ============================================
# Intervention Check (called inside agentic loop)
# ============================================

async def _check_interventions(
    conversation_id: str,
    messages: list,
) -> AsyncGenerator[str, None]:
    """Check and handle pending interventions. Yields SSE events.

    Returns by yielding SSE events. If a 'cancelled' event is yielded,
    the caller should abort the loop.
    """
    if not conversation_id:
        return

    # Initialize execution state if needed
    if conversation_id not in _execution_state:
        _execution_state[conversation_id] = asyncio.Event()
        _execution_state[conversation_id].set()  # Running by default

    # Handle pause: wait until resumed
    if not _execution_state[conversation_id].is_set():
        yield _sse({"type": "paused", "message": "Ausfuehrung pausiert - warte auf Resume..."})
        await _execution_state[conversation_id].wait()
        yield _sse({"type": "resumed", "message": "Fortgesetzt"})

    # Process pending interventions
    pending = _pending_interventions.pop(conversation_id, [])
    for intervention in pending:
        action = intervention["action"]
        data = intervention.get("data", {})

        if action == "cancel":
            yield _sse({"type": "cancelled", "message": "Vom User abgebrochen"})
            return  # Caller checks for 'cancelled' in yielded events

        elif action == "feedback":
            feedback_text = data.get("message", "")
            if feedback_text:
                messages.append({"role": "user", "content": f"[USER INTERVENTION]: {feedback_text}"})
                yield _sse({"type": "user_feedback", "message": feedback_text})

        elif action == "skip_task":
            task_id = data.get("task_id")
            yield _sse({"type": "task_skipped", "task_id": task_id})
            # Update task list
            if conversation_id in _session_tasks:
                for t in _session_tasks[conversation_id]:
                    if t.get("id") == task_id:
                        t["status"] = "skipped"


# ============================================
# Agentic Loop
# ============================================

async def run_agentic_loop(
    text: str,
    conversation_id: Optional[str] = None
) -> IntentResponse:
    """Run the agentic loop: LLM → tool_call → execute → LLM → ... → final answer."""
    start_time = time.time()
    steps: List[IntentStep] = []

    # Build messages with persistent conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_id:
        conv = load_conversation(conversation_id)
        context_parts = []
        if conv["summary"]:
            context_parts.append(f"[ZUSAMMENFASSUNG BISHERIGES GESPRAECH:]\n{conv['summary']}")
        if conv["recent"]:
            recent_lines = [f"[{e['role'].upper()}]: {e['content']}" for e in conv["recent"]]
            context_parts.append(f"[LETZTE NACHRICHTEN:]\n" + "\n".join(recent_lines))
        if context_parts:
            messages.append({
                "role": "user",
                "content": "\n\n".join(context_parts) + "\n[ENDE KONTEXT]"
            })
            messages.append({
                "role": "assistant",
                "content": "Verstanden, ich habe den Kontext aus unserem bisherigen Gespraech. Was moechtest du als naechstes?"
            })

    messages.append({"role": "user", "content": text})

    for iteration in range(MAX_ITERATIONS):
        try:
            response = await call_openrouter(messages, TOOLS)
        except Exception as e:
            return IntentResponse(
                success=False,
                summary=f"LLM-Fehler: {str(e)}",
                steps=steps,
                duration_ms=(time.time() - start_time) * 1000,
                iterations=iteration + 1,
                error=str(e)
            )

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # Check for tool calls
        tool_calls = message.get("tool_calls", [])

        if tool_calls:
            # Append assistant message with tool calls
            messages.append(message)

            # Execute each tool call
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                tc_id = tc.get("id", f"call_{uuid4().hex[:8]}")

                logger.info(f"[LLM Intent] Tool: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]})")

                # Execute the tool
                result = await execute_tool(tool_name, tool_args)

                # Handle approval-required tools in remote mode
                if result.get("_approval_required"):
                    result = {
                        "success": False,
                        "pending_approval": True,
                        "message": f"Tool '{tool_name}' requires user approval in remote mode."
                    }

                step = IntentStep(
                    tool=tool_name,
                    params=tool_args,
                    result=result,
                    success=result.get("success", False)
                )
                steps.append(step)

                # Append tool result to messages
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                # Truncate very long results
                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "... [truncated]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str
                })

        else:
            # No tool calls = final answer
            summary = message.get("content", "Befehl ausgeführt.")
            all_success = all(s.success for s in steps) if steps else True

            # Save to persistent conversation memory + trigger compaction
            if conversation_id:
                conv = load_conversation(conversation_id)
                conv["recent"].append({"role": "user", "content": text})
                summary_condensed = summary[:500] if len(summary) > 500 else summary
                conv["recent"].append({"role": "assistant", "content": summary_condensed})
                conv["turn_count"] = conv.get("turn_count", 0) + 1
                save_conversation(conversation_id, conv)
                # Compact in background if needed
                if len(conv["recent"]) > COMPACT_THRESHOLD:
                    asyncio.create_task(compact_conversation(conversation_id))

            return IntentResponse(
                success=all_success,
                summary=summary,
                steps=steps,
                duration_ms=(time.time() - start_time) * 1000,
                iterations=iteration + 1
            )

    # Max iterations reached
    if conversation_id:
        conv = load_conversation(conversation_id)
        conv["recent"].append({"role": "user", "content": text})
        conv["recent"].append({"role": "assistant", "content": "Aufgabe unvollstaendig (max iterations)"})
        conv["turn_count"] = conv.get("turn_count", 0) + 1
        save_conversation(conversation_id, conv)

    return IntentResponse(
        success=False,
        summary="Maximale Iterationen erreicht. Aufgabe moeglicherweise unvollstaendig.",
        steps=steps,
        duration_ms=(time.time() - start_time) * 1000,
        iterations=MAX_ITERATIONS,
        error="max_iterations_reached"
    )


# ============================================
# SSE Streaming Agentic Loop
# ============================================

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def run_agentic_loop_stream(
    text: str,
    conversation_id: Optional[str] = None,
    video_agent_enabled: bool = False
) -> AsyncGenerator[str, None]:
    """Run the agentic loop, yielding SSE events for each step."""
    start_time = time.time()
    steps: List[IntentStep] = []
    step_index = 0

    # Build messages with persistent conversation history (tiered: summary + recent)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_id:
        conv = load_conversation(conversation_id)
        context_parts = []
        if conv["summary"]:
            context_parts.append(f"[ZUSAMMENFASSUNG BISHERIGES GESPRAECH:]\n{conv['summary']}")
        if conv["recent"]:
            recent_lines = [f"[{e['role'].upper()}]: {e['content']}" for e in conv["recent"]]
            context_parts.append(f"[LETZTE NACHRICHTEN:]\n" + "\n".join(recent_lines))
        if context_parts:
            turn_count = conv.get("turn_count", 0)
            messages.append({
                "role": "user",
                "content": "\n\n".join(context_parts) + f"\n[ENDE KONTEXT - Turn {turn_count + 1}]"
            })
            messages.append({
                "role": "assistant",
                "content": "Verstanden, ich habe den Kontext aus unserem bisherigen Gespraech. Was moechtest du als naechstes?"
            })

    messages.append({"role": "user", "content": text})

    # Initialize intervention state for this conversation
    if conversation_id:
        _execution_state[conversation_id] = asyncio.Event()
        _execution_state[conversation_id].set()  # Running by default

    for iteration in range(MAX_ITERATIONS):
        # Call LLM
        try:
            response = await call_openrouter(messages, TOOLS)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e), "iteration": iteration + 1})
            yield _sse({"type": "done", "success": False, "total_steps": len(steps),
                        "iterations": iteration + 1,
                        "duration_ms": (time.time() - start_time) * 1000})
            # Cleanup intervention state
            _pending_interventions.pop(conversation_id, None)
            _execution_state.pop(conversation_id, None)
            return

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])

        # Emit thinking event
        yield _sse({
            "type": "thinking",
            "iteration": iteration + 1,
            "content": message.get("content", "") or "",
            "has_tool_calls": bool(tool_calls)
        })

        if tool_calls:
            messages.append(message)

            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                tc_id = tc.get("id", f"call_{uuid4().hex[:8]}")

                # Inject conversation_id for tools that need it
                if tool_name in ("update_tasks", "recall_element") and conversation_id:
                    tool_args["_conversation_id"] = conversation_id

                # ★ CHECK INTERVENTIONS BEFORE EACH TOOL
                cancelled = False
                async for event in _check_interventions(conversation_id, messages):
                    yield event
                    if '"cancelled"' in event:
                        cancelled = True
                        break
                if cancelled:
                    yield _sse({"type": "done", "success": False, "total_steps": len(steps),
                                "iterations": iteration + 1,
                                "duration_ms": (time.time() - start_time) * 1000,
                                "conversation_id": conversation_id, "reason": "user_cancelled"})
                    # Cleanup intervention state
                    _pending_interventions.pop(conversation_id, None)
                    _execution_state.pop(conversation_id, None)
                    return

                # Emit tool_start
                yield _sse({
                    "type": "tool_start",
                    "iteration": iteration + 1,
                    "tool": tool_name,
                    "params": {k: v for k, v in tool_args.items() if not k.startswith("_")},
                    "step_index": step_index
                })

                # Emit action_visual for coordinate-based tools (overlay on live stream)
                if tool_name in ("action_click", "mouse_move", "action_scroll") and tool_args.get("x") is not None:
                    yield _sse({
                        "type": "action_visual",
                        "action": tool_name,
                        "x": tool_args.get("x"),
                        "y": tool_args.get("y"),
                        "tool": tool_name,
                        "iteration": iteration + 1
                    })

                # Execute tool (with streaming for action_type)
                if tool_name == "action_type":
                    # ★ STREAMING: Type text chunk by chunk with live SSE events
                    typing_text = tool_args.get("text", "")
                    typing_result = {"success": False, "action": "type", "text_length": len(typing_text)}
                    async for typing_event in _stream_action_type(typing_text):
                        if typing_event["type"] == "typing_stream":
                            yield _sse({
                                "type": "typing_stream",
                                "chunk": typing_event["chunk"],
                                "typed_so_far": typing_event["typed_so_far"],
                                "progress": typing_event["progress"],
                                "chunk_index": typing_event["chunk_index"],
                                "total_chunks": typing_event["total_chunks"],
                                "iteration": iteration + 1
                            })
                        elif typing_event["type"] == "typing_done":
                            typing_result = {
                                "success": typing_event.get("success", True),
                                "action": "type",
                                "text_length": typing_event.get("total_chars", len(typing_text)),
                                "chunks_typed": typing_event.get("chunks_typed", 1),
                                "streamed": True
                            }
                            if not typing_event.get("success", True):
                                typing_result["error"] = typing_event.get("error", "Unknown error")
                    result = typing_result
                elif tool_name in FIRE_AND_FORGET_TOOLS:
                    # ★ FIRE-AND-FORGET: dispatch action in background, return instant result
                    async def _ff_execute(tn, ta):
                        try:
                            return await execute_tool(tn, ta)
                        except Exception as e:
                            logger.error(f"[FF] Background {tn} failed: {e}")
                            return {"success": False, "error": str(e)}

                    task = asyncio.create_task(_ff_execute(tool_name, tool_args))
                    _ff_background_tasks[f"{tool_name}_{id(task)}"] = task
                    # Wait briefly (50ms) to let pyautogui fire, then move on
                    await asyncio.sleep(0.05)
                    result = {
                        "success": True,
                        "dispatched": True,
                        "action": tool_name,
                        "x": tool_args.get("x"),
                        "y": tool_args.get("y"),
                    }
                    # Clean up completed background tasks
                    done_keys = [k for k, t in _ff_background_tasks.items() if t.done()]
                    for k in done_keys:
                        _ff_background_tasks.pop(k, None)
                else:
                    result = await execute_tool(tool_name, tool_args)

                # Handle approval-required tools in remote mode
                if result.get("_approval_required"):
                    yield _sse({
                        "type": "approval_required",
                        "tool": tool_name,
                        "params": {k: v for k, v in tool_args.items() if not k.startswith("_")},
                        "message": result.get("message", f"Tool '{tool_name}' requires approval"),
                        "conversation_id": conversation_id,
                        "iteration": iteration + 1
                    })
                    # Pause and wait for user approval via intervention system
                    if conversation_id and conversation_id in _execution_state:
                        _execution_state[conversation_id].clear()  # Pause
                        yield _sse({"type": "waiting_approval", "tool": tool_name})
                        await _execution_state[conversation_id].wait()  # Block until approve/deny

                        # Check what the user decided
                        pending = _pending_interventions.pop(conversation_id, [])
                        approved = False
                        for intervention in pending:
                            if intervention["action"] == "approve_tool":
                                approved = True
                            elif intervention["action"] == "cancel":
                                yield _sse({"type": "cancelled", "message": "Vom User abgebrochen"})
                                return

                        if approved:
                            yield _sse({"type": "tool_approved", "tool": tool_name})
                            # Execute the tool now (locally - APPROVAL tools run in container)
                            result = await execute_tool.__wrapped__(tool_name, tool_args) if hasattr(execute_tool, '__wrapped__') else await _execute_approved_tool(tool_name, tool_args)
                        else:
                            result = {
                                "success": False,
                                "denied": True,
                                "message": f"Tool '{tool_name}' was denied by user."
                            }
                            yield _sse({"type": "tool_denied", "tool": tool_name})
                    else:
                        result = {
                            "success": False,
                            "pending_approval": True,
                            "message": f"Tool '{tool_name}' requires user approval. No conversation context."
                        }

                step = IntentStep(
                    tool=tool_name, params=tool_args,
                    result=result, success=result.get("success", False)
                )
                steps.append(step)

                # Emit task_update SSE event for update_tasks
                if tool_name == "update_tasks" and result.get("success"):
                    yield _sse({
                        "type": "task_update",
                        "tasks": result.get("tasks", []),
                        "counts": result.get("counts", {}),
                        "iteration": iteration + 1
                    })

                # Emit click_warning SSE event if click had no effect
                if tool_name == "action_click" and result.get("screen_changed") is False:
                    yield _sse({
                        "type": "click_warning",
                        "message": result.get("warning", "Click hatte keine Wirkung"),
                        "x": tool_args.get("x"),
                        "y": tool_args.get("y"),
                        "iteration": iteration + 1
                    })

                # ★ CLICK CONFIRMATION: Ask user if click was correct (if from recall_element and not yet trusted)
                if tool_name == "action_click" and conversation_id and conversation_id in _last_recall:
                    lr = _last_recall.pop(conversation_id)
                    click_x, click_y = tool_args.get("x"), tool_args.get("y")
                    # Only ask if coords match the recalled element AND not yet trusted
                    if lr["x"] == click_x and lr["y"] == click_y and not lr["trusted"]:
                        yield _sse({
                            "type": "click_confirm",
                            "element": lr["element"],
                            "app": lr["app"],
                            "x": click_x,
                            "y": click_y,
                            "user_confirmed": lr["user_confirmed"],
                            "threshold": 3,
                            "conversation_id": conversation_id,
                            "iteration": iteration + 1
                        })
                        # Pause execution and wait for user response
                        if conversation_id in _execution_state:
                            _execution_state[conversation_id].clear()
                            yield _sse({"type": "waiting_click_confirm", "element": lr["element"]})
                            await _execution_state[conversation_id].wait()

                            # Check user response
                            pending = _pending_interventions.pop(conversation_id, [])
                            for intervention in pending:
                                if intervention["action"] == "confirm_click":
                                    trusted = confirm_element(lr["app"], lr["element"])
                                    yield _sse({
                                        "type": "click_confirmed",
                                        "element": lr["element"],
                                        "trusted": trusted,
                                        "message": f"Bestaetigt! {'Auto-Trust aktiviert.' if trusted else ''}"
                                    })
                                elif intervention["action"] == "deny_click":
                                    deny_element(lr["app"], lr["element"])
                                    yield _sse({
                                        "type": "click_denied",
                                        "element": lr["element"],
                                        "message": "Position verworfen, wird beim naechsten Mal neu gesucht."
                                    })
                                elif intervention["action"] == "cancel":
                                    yield _sse({"type": "cancelled", "message": "Vom User abgebrochen"})
                                    _pending_interventions.pop(conversation_id, None)
                                    _execution_state.pop(conversation_id, None)
                                    return

                            # Focus-restore: bring target app back to foreground
                            try:
                                focus_result = await _handoff_mod.handle_set_focus(lr["app"])
                                if not focus_result.get("success"):
                                    # Fallback to Alt+Tab if window not found by title
                                    await _handoff_mod.handle_action("hotkey", {"keys": ["alt", "tab"]})
                                await asyncio.sleep(0.3)
                            except Exception as e:
                                logger.warning(f"[ClickConfirm] Focus restore failed: {e}")

                # Full result for SSE event (no truncation - user wants complete data)
                result_for_event = dict(result)

                # Emit tool_result
                yield _sse({
                    "type": "tool_result",
                    "iteration": iteration + 1,
                    "tool": tool_name,
                    "params": {k: v for k, v in tool_args.items() if not k.startswith("_")},
                    "result": result_for_event,
                    "success": result.get("success", False),
                    "step_index": step_index
                })

                # ★ VIDEO AGENT: Analyze frame after tool execution (Guardian Mode)
                if video_agent_enabled and tool_name not in VA_SKIP_TOOLS:
                    try:
                        # For fire-and-forget actions, wait for action to complete before analysis
                        if result.get("dispatched"):
                            await asyncio.sleep(0.3)

                        # For mouse_move: capture viewport around target for focused validation
                        va_viewport = None
                        if tool_name == "mouse_move":
                            tx = tool_args.get("x", 0)
                            ty = tool_args.get("y", 0)
                            va_viewport = {"x": max(0, tx - 150), "y": max(0, ty - 150), "width": 300, "height": 300}

                        # Fire screen_find in parallel for OCR-based position hints
                        async def _find_hint():
                            try:
                                task_text = text[:80].strip()
                                if task_text and _handoff_mod:
                                    hint = await _handoff_mod.handle_validate(target=task_text)
                                    if hint.get("success") and hint.get("element_location"):
                                        return hint["element_location"]
                            except Exception:
                                pass
                            return None

                        frame_task = capture_current_frame(quality=50, viewport=va_viewport)
                        find_task = _find_hint()
                        frame_b64, ocr_hint = await asyncio.gather(frame_task, find_task)

                        if frame_b64:
                            va_context = {
                                "tool": tool_name,
                                "params": {k: v for k, v in tool_args.items() if not k.startswith("_")},
                                "result": {"success": result.get("success", False)},
                                "step_index": step_index,
                                "task": text[:100],
                                "viewport": va_viewport,
                                "ocr_hint": ocr_hint
                            }

                            # ★ GUARDIAN MODE: Use analyze_and_guard() for auto-correction
                            if video_agent.guardian_mode:
                                # Wire ActionRouter as tool executor
                                from app.services.action_router import action_router
                                video_agent.set_tool_executor(action_router)

                                # Analyze + Auto-correct if needed
                                guard_result = await video_agent.analyze_and_guard(
                                    frame_b64, va_context, conversation_id, max_retries=2
                                )

                                va_result = guard_result["analysis"]

                                # Stream corrections
                                if guard_result.get("corrections"):
                                    for correction in guard_result["corrections"]:
                                        yield _sse({
                                            "type": "guardian_correction",
                                            "tool": correction.get("tool"),
                                            "args": correction.get("args"),
                                            "result": correction.get("result"),
                                            "step_index": step_index
                                        })

                                # Stream guardian status
                                yield _sse({
                                    "type": "guardian_status",
                                    "status": guard_result["final_status"],
                                    "corrections_count": len(guard_result.get("corrections", [])),
                                    "step_index": step_index
                                })
                            else:
                                # Legacy mode: passive analysis only
                                va_result = await video_agent.analyze_frame(
                                    frame_b64, va_context, conversation_id
                                )

                            # Stream video analysis
                            yield _sse({
                                "type": "video_analysis",
                                "tool": tool_name,
                                "verified": va_result.get("action_verified"),
                                "screen_state": va_result.get("screen_state", ""),
                                "confidence": va_result.get("confidence", 0),
                                "step_index": step_index,
                                "iteration": iteration + 1,
                                "viewport": va_viewport,
                                "ocr_hint": ocr_hint
                            })
                    except Exception as va_err:
                        logger.warning(f"[VideoAgent] Analysis error: {va_err}")

                step_index += 1

                # Append tool result to LLM messages
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "... [truncated]"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str
                })

            # ★ CHECK PAUSE/RESUME AFTER ALL TOOL CALLS IN THIS ITERATION
            if conversation_id and conversation_id in _execution_state:
                if not _execution_state[conversation_id].is_set():
                    yield _sse({"type": "paused", "message": "Pausiert nach Iteration", "iteration": iteration + 1})
                    await _execution_state[conversation_id].wait()
                    yield _sse({"type": "resumed", "message": "Fortgesetzt", "iteration": iteration + 1})

        else:
            # Final answer
            summary = message.get("content", "Befehl ausgefuehrt.")
            all_success = all(s.success for s in steps) if steps else True

            # Save to persistent conversation memory + trigger compaction
            if conversation_id:
                conv = load_conversation(conversation_id)
                conv["recent"].append({"role": "user", "content": text})
                summary_condensed = summary[:500] if len(summary) > 500 else summary
                conv["recent"].append({"role": "assistant", "content": summary_condensed})
                conv["turn_count"] = conv.get("turn_count", 0) + 1
                save_conversation(conversation_id, conv)
                # Compact in background if needed
                if len(conv["recent"]) > COMPACT_THRESHOLD:
                    asyncio.create_task(compact_conversation(conversation_id))

            yield _sse({"type": "summary", "content": summary, "iteration": iteration + 1})

            # ★ VIDEO AGENT: Save training data before done
            if video_agent_enabled and conversation_id:
                try:
                    training_file = video_agent.save_training_data(conversation_id, text[:200])
                    if training_file:
                        yield _sse({"type": "training_saved", "file": training_file})
                except Exception as va_err:
                    logger.warning(f"[VideoAgent] Training save error: {va_err}")

            yield _sse({
                "type": "done",
                "success": all_success,
                "total_steps": len(steps),
                "iterations": iteration + 1,
                "duration_ms": (time.time() - start_time) * 1000,
                "conversation_id": conversation_id,
                "turn_count": conv["turn_count"] if conversation_id else 0
            })
            # Cleanup intervention state
            _pending_interventions.pop(conversation_id, None)
            _execution_state.pop(conversation_id, None)
            return

    # Max iterations reached - still save partial context
    if conversation_id:
        conv = load_conversation(conversation_id)
        conv["recent"].append({"role": "user", "content": text})
        conv["recent"].append({"role": "assistant", "content": "Aufgabe unvollstaendig (max iterations)"})
        conv["turn_count"] = conv.get("turn_count", 0) + 1
        save_conversation(conversation_id, conv)

    yield _sse({"type": "error", "message": "Max iterations reached", "iteration": MAX_ITERATIONS})
    yield _sse({
        "type": "done",
        "success": False,
        "total_steps": len(steps),
        "iterations": MAX_ITERATIONS,
        "duration_ms": (time.time() - start_time) * 1000,
        "conversation_id": conversation_id
    })
    # Cleanup intervention state
    _pending_interventions.pop(conversation_id, None)
    _execution_state.pop(conversation_id, None)


# ============================================
# API Endpoints
# ============================================

def _resolve_video_agent(request_val: Optional[bool]) -> bool:
    """Resolve video agent enabled state: explicit request > config default."""
    if request_val is not None:
        return request_val and video_agent.enabled
    try:
        from app.config import get_settings
        return get_settings().video_agent_default and video_agent.enabled
    except Exception:
        return video_agent.enabled


@router.post("/intent/stream")
async def process_intent_stream(request: IntentRequest):
    """Stream the agentic loop as Server-Sent Events.

    Each event is a JSON line prefixed with 'data: '.
    Event types: thinking, tool_start, tool_result, summary, error, done.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not configured")

    logger.info(f"[LLM Intent Stream] Processing: {request.text}")

    return StreamingResponse(
        run_agentic_loop_stream(
            text=request.text,
            conversation_id=request.conversation_id,
            video_agent_enabled=_resolve_video_agent(request.video_agent)
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/intent", response_model=IntentResponse)
async def process_intent(request: IntentRequest) -> IntentResponse:
    """Process a natural language intent via Claude Opus 4.6 with MCP tools.

    The LLM agent autonomously decides which tools to use to fulfill the request.
    Supports multi-step execution with screen reading, element finding, clicking,
    typing, keyboard shortcuts, scrolling, and shell commands.

    Example:
        POST /api/llm/intent
        {"text": "open notepad and type hello world"}
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not configured. Set it in .env"
        )

    logger.info(f"[LLM Intent] Processing: {request.text}")

    try:
        result = await run_agentic_loop(
            text=request.text,
            conversation_id=request.conversation_id
        )
        logger.info(
            f"[LLM Intent] Done: success={result.success}, "
            f"steps={len(result.steps)}, "
            f"iterations={result.iterations}, "
            f"duration={result.duration_ms:.0f}ms"
        )
        return result

    except Exception as e:
        logger.error(f"[LLM Intent] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intent/health")
async def intent_health():
    """Check LLM intent service health."""
    return {
        "status": "healthy" if OPENROUTER_API_KEY else "no_api_key",
        "model": _get_llm_model(),
        "tools_count": len(TOOLS),
        "tool_names": [t["function"]["name"] for t in TOOLS],
        "max_iterations": MAX_ITERATIONS,
        "video_agent": video_agent.enabled,
        "video_agent_model": "configured via VISION_MODEL"
    }


@router.post("/intent/intervene")
async def intervene(request: InterventionRequest):
    """User intervention during agent execution.

    Actions:
        - pause: Pause the agentic loop (waits at next check point)
        - resume: Resume a paused loop
        - cancel: Abort the current execution
        - feedback: Inject a user message into the LLM context
        - skip_task: Skip a specific task in the task list
    """
    conv_id = request.conversation_id

    if request.action == "pause":
        if conv_id in _execution_state:
            _execution_state[conv_id].clear()  # Pauses the loop
            logger.info(f"[Intervention] Paused: {conv_id}")
        return {"status": "paused"}

    elif request.action == "resume":
        if conv_id in _execution_state:
            _execution_state[conv_id].set()  # Resumes the loop
            logger.info(f"[Intervention] Resumed: {conv_id}")
        return {"status": "resumed"}

    elif request.action == "approve_tool":
        if conv_id not in _pending_interventions:
            _pending_interventions[conv_id] = []
        _pending_interventions[conv_id].append({"action": "approve_tool", "data": request.data or {}})
        if conv_id in _execution_state:
            _execution_state[conv_id].set()  # Resume to process approval
        logger.info(f"[Intervention] Tool APPROVED for {conv_id}")
        return {"status": "approved"}

    elif request.action == "deny_tool":
        if conv_id not in _pending_interventions:
            _pending_interventions[conv_id] = []
        _pending_interventions[conv_id].append({"action": "deny_tool", "data": request.data or {}})
        if conv_id in _execution_state:
            _execution_state[conv_id].set()  # Resume to process denial
        logger.info(f"[Intervention] Tool DENIED for {conv_id}")
        return {"status": "denied"}

    elif request.action == "confirm_click":
        if conv_id not in _pending_interventions:
            _pending_interventions[conv_id] = []
        _pending_interventions[conv_id].append({"action": "confirm_click", "data": request.data or {}})
        if conv_id in _execution_state:
            _execution_state[conv_id].set()
        logger.info(f"[Intervention] Click CONFIRMED for {conv_id}")
        return {"status": "confirmed"}

    elif request.action == "deny_click":
        if conv_id not in _pending_interventions:
            _pending_interventions[conv_id] = []
        _pending_interventions[conv_id].append({"action": "deny_click", "data": request.data or {}})
        if conv_id in _execution_state:
            _execution_state[conv_id].set()
        logger.info(f"[Intervention] Click DENIED for {conv_id}")
        return {"status": "denied"}

    elif request.action in ("cancel", "skip_task", "feedback"):
        if conv_id not in _pending_interventions:
            _pending_interventions[conv_id] = []
        _pending_interventions[conv_id].append({
            "action": request.action,
            "data": request.data or {}
        })
        # If paused, wake up so cancel/feedback gets processed
        if conv_id in _execution_state:
            _execution_state[conv_id].set()
        logger.info(f"[Intervention] Queued {request.action} for {conv_id}")
        return {"status": "queued", "action": request.action}

    return {"status": "unknown_action"}
