"""
Workflow VibeCoder — Iterative chat-based n8n workflow builder.

Entry point is a structured Clarification Checklist that collects all
required data before the free-form LLM chat begins:

1. [Checklist Phase] — TODO items with options/text input
   - Workflow description (required)
   - Trigger type (required)
   - Data sources, AI model, output (optional)
   - Auto-checks: n8n reachable, LLM key, credentials
2. [Chat Phase] — Free-form LLM chat with full context from checklist

Each session tracks: checklist answers, chat history, current workflow JSON,
deployed workflow_id, and the current phase.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Electron broadcast (optional)
try:
    from tools.workspace_tools import _broadcast_to_electron
except ImportError:
    def _broadcast_to_electron(msg):
        pass


# ---------------------------------------------------------------------------
# Checklist Definition
# ---------------------------------------------------------------------------

CHECKLIST_ITEMS = [
    {
        "id": "description",
        "label": "Workflow-Beschreibung",
        "prompt": "Was soll der Workflow tun?",
        "required": True,
        "type": "text",          # free text input
        "options": None,
    },
    {
        "id": "trigger_type",
        "label": "Trigger",
        "prompt": "Wie soll der Workflow ausgeloest werden?",
        "required": True,
        "type": "select",
        "options": ["Chat Trigger", "Webhook", "Schedule"],
    },
    {
        "id": "data_sources",
        "label": "Datenquellen",
        "prompt": "Welche Datenquellen braucht der Workflow?",
        "required": False,
        "type": "multi",         # multiple selection
        "options": ["PostgreSQL", "HTTP API", "CSV", "MySQL", "Keine"],
    },
    {
        "id": "ai_model",
        "label": "AI Model",
        "prompt": "Soll ein AI Agent integriert werden?",
        "required": False,
        "type": "select",
        "options": ["GPT-4o", "GPT-5.4", "Claude", "Kein AI"],
    },
    {
        "id": "output",
        "label": "Output",
        "prompt": "Was soll der Output sein?",
        "required": False,
        "type": "select",
        "options": ["Chat-Antwort", "Email", "Webhook-Response", "DB-Eintrag", "JSON-API"],
    },
]

# Credential requirements keyed by data_sources / ai_model selections
CREDENTIAL_CHECKS = {
    "PostgreSQL": {"env_key": "POSTGRES_URL", "label": "PostgreSQL URL"},
    "MySQL": {"env_key": "MYSQL_URL", "label": "MySQL URL"},
    "GPT-4o": {"env_key": "OPENAI_API_KEY", "label": "OpenAI API Key"},
    "GPT-5.4": {"env_key": "OPENAI_API_KEY", "label": "OpenAI API Key"},
    "Claude": {"env_key": "ANTHROPIC_API_KEY", "label": "Anthropic API Key"},
}


def _run_auto_checks(checklist: Dict[str, str]) -> List[Dict[str, Any]]:
    """Run automatic prerequisite checks based on checklist answers.

    Returns list of check results:
    [{"id": "...", "label": "...", "ok": bool, "detail": "..."}]
    """
    checks = []

    # 1. n8n reachable
    try:
        from spaces.n8n.tools.n8n_api_client import get_n8n_client
        client = get_n8n_client()
        health = client.health_check()
        checks.append({
            "id": "n8n_online",
            "label": "n8n erreichbar",
            "ok": health.get("online", False),
            "detail": health.get("url", "") if health.get("online") else "n8n nicht erreichbar",
        })
    except Exception as e:
        checks.append({"id": "n8n_online", "label": "n8n erreichbar", "ok": False, "detail": str(e)})

    # 2. LLM API key
    has_llm = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
    checks.append({
        "id": "llm_key",
        "label": "LLM API Key",
        "ok": has_llm,
        "detail": "Konfiguriert" if has_llm else "OPENAI_API_KEY oder OPENROUTER_API_KEY fehlt",
    })

    # 3. Credential checks based on selections
    selected_sources = [s.strip() for s in checklist.get("data_sources", "").split(",") if s.strip()]
    ai_model = checklist.get("ai_model", "")
    all_selections = selected_sources + ([ai_model] if ai_model else [])

    for selection in all_selections:
        cred = CREDENTIAL_CHECKS.get(selection)
        if not cred:
            continue
        val = os.getenv(cred["env_key"], "").strip()
        checks.append({
            "id": f"cred_{cred['env_key']}",
            "label": cred["label"],
            "ok": bool(val),
            "detail": "Konfiguriert" if val else f"{cred['env_key']} fehlt in .env",
        })

    return checks


def _build_context_from_checklist(checklist: Dict[str, str]) -> str:
    """Build structured context string from checklist answers for LLM."""
    parts = []
    for item in CHECKLIST_ITEMS:
        val = checklist.get(item["id"], "")
        if val:
            parts.append(f"- {item['label']}: {val}")
    return "\n".join(parts) if parts else "(keine Details angegeben)"


# ---------------------------------------------------------------------------
# LLM-powered Chat (uses same provider as Society)
# ---------------------------------------------------------------------------

def _get_chat_completion(messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
    """Call LLM for workflow chat responses."""
    try:
        from llm_config import get_model, get_api_key, get_base_url
        import httpx

        model = os.getenv("N8N_GENERATOR_MODEL", get_model("n8n"))
        api_key = get_api_key()
        base_url = get_base_url()

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LLM chat completion failed: {e}")
        return f"Fehler bei der LLM-Antwort: {e}"


SYSTEM_PROMPT = """Du bist der VibeCoder fuer n8n Workflows. Du hilfst dem Benutzer iterativ,
n8n Workflows zu planen, bauen und verbessern.

Deine Faehigkeiten:
- Du kennst alle n8n Node-Typen: Chat Trigger, Webhook, AI Agent, HTTP Request, PostgreSQL, MySQL, Code, Think Tool, Memory Buffer, etc.
- Du kannst Workflow-Plaene als strukturiertes JSON erstellen
- Du kannst bestehende Workflows analysieren und Verbesserungen vorschlagen
- Du antwortest auf Deutsch, technische Begriffe bleiben auf Englisch

Der Benutzer hat bereits einen Clarification-Checklist ausgefuellt. Nutze diese Informationen
um direkt einen passenden Workflow zu planen und zu bauen.

Ablauf:
1. Fasse die Anforderungen kurz zusammen
2. Erstelle einen Workflow-Plan
3. Generiere das vollstaendige n8n JSON

Wenn ein Workflow bereits existiert und der Benutzer Aenderungen will:
1. Analysiere den aktuellen Workflow
2. Schlage konkrete Aenderungen vor
3. Generiere das aktualisierte JSON

Markiere fertiges Workflow-JSON immer mit:
```n8n-workflow
{...}
```

So kann es automatisch erkannt und deployed werden."""


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class WorkflowChatSession:
    """A single VibeCoder chat session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.messages: List[Dict[str, str]] = []
        self.workflow_json: Optional[Dict] = None
        self.workflow_id: Optional[str] = None
        self.workflow_name: Optional[str] = None
        self.description: str = ""
        self.state: str = "checklist"  # checklist → chat → iterating
        self.checklist: Dict[str, str] = {}
        self.auto_checks: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "state": self.state,
            "has_workflow": self.workflow_json is not None,
            "checklist": self.checklist,
            "auto_checks": self.auto_checks,
        }


class WorkflowChatManager:
    """Manages VibeCoder chat sessions with checklist entry-point."""

    def __init__(self):
        self._sessions: Dict[str, WorkflowChatSession] = {}

    def create_session(self, description: str = "") -> Dict[str, Any]:
        """Create a new session starting in checklist phase."""
        session_id = uuid4().hex[:12]
        session = WorkflowChatSession(session_id)
        self._sessions[session_id] = session

        # Pre-fill description if provided
        if description:
            session.checklist["description"] = description
            session.description = description

        return {
            "success": True,
            "session_id": session_id,
            "state": "checklist",
            "checklist_items": CHECKLIST_ITEMS,
            "checklist": session.checklist,
            "message": "Checklist ausgefuellt? Dann starte den VibeCoder Chat.",
        }

    def answer_checklist(self, session_id: str, item_id: str, value: str) -> Dict[str, Any]:
        """Answer a single checklist item."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "message": f"Session '{session_id}' nicht gefunden."}

        if session.state != "checklist":
            return {"success": False, "message": "Session ist nicht in der Checklist-Phase."}

        # Validate item_id
        valid_ids = {item["id"] for item in CHECKLIST_ITEMS}
        if item_id not in valid_ids:
            return {"success": False, "message": f"Unbekanntes Checklist-Item: {item_id}"}

        # Store answer
        value = value.strip()
        if value:
            session.checklist[item_id] = value
        else:
            session.checklist.pop(item_id, None)

        # Track description
        if item_id == "description" and value:
            session.description = value

        # Check completion: all required items answered?
        required_done = all(
            session.checklist.get(item["id"])
            for item in CHECKLIST_ITEMS
            if item["required"]
        )

        return {
            "success": True,
            "session_id": session_id,
            "state": "checklist",
            "checklist": session.checklist,
            "item_id": item_id,
            "required_complete": required_done,
        }

    def complete_checklist(self, session_id: str) -> Dict[str, Any]:
        """Finish checklist phase, run auto-checks, transition to chat."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "message": f"Session '{session_id}' nicht gefunden."}

        # Verify required items
        missing = [
            item["label"] for item in CHECKLIST_ITEMS
            if item["required"] and not session.checklist.get(item["id"])
        ]
        if missing:
            return {
                "success": False,
                "message": f"Pflichtfelder fehlen: {', '.join(missing)}",
                "missing": missing,
            }

        # Run auto-checks
        session.auto_checks = _run_auto_checks(session.checklist)

        # Transition to chat
        session.state = "chat"

        # Build initial context message from checklist
        context = _build_context_from_checklist(session.checklist)
        intro = f"Checklist abgeschlossen. Anforderungen:\n{context}"

        # Add as first assistant message
        session.messages.append({"role": "assistant", "content": intro})

        # Broadcast
        _broadcast_to_electron({
            "type": "n8n_vibecoder_checklist_complete",
            "session_id": session_id,
            "checklist": session.checklist,
            "auto_checks": session.auto_checks,
        })

        return {
            "success": True,
            "session_id": session_id,
            "state": "chat",
            "checklist": session.checklist,
            "auto_checks": session.auto_checks,
            "response": intro,
            "message": "Checklist abgeschlossen. VibeCoder Chat ist bereit.",
        }

    def send_message(self, session_id: str, user_message: str) -> Dict[str, Any]:
        """Send a user message in the chat phase."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "message": f"Session '{session_id}' nicht gefunden."}

        # If still in checklist, auto-complete first
        if session.state == "checklist":
            complete = self.complete_checklist(session_id)
            if not complete.get("success"):
                return complete

        user_message = user_message.strip()
        if not user_message:
            return {"success": False, "message": "Leere Nachricht."}

        # Add user message
        session.messages.append({"role": "user", "content": user_message})

        # Check for deploy command
        if user_message.lower() in ("deploy", "deployen", "auf n8n pushen", "aktivieren"):
            return self._handle_deploy(session)

        # Build LLM messages
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject checklist context
        context = _build_context_from_checklist(session.checklist)
        llm_messages.append({
            "role": "system",
            "content": f"Benutzer-Anforderungen (aus Checklist):\n{context}",
        })

        # Inject workflow context
        if session.workflow_json:
            ctx = json.dumps(session.workflow_json, indent=2)[:3000]
            llm_messages.append({
                "role": "system",
                "content": f"Aktueller Workflow (bereits generiert):\n```json\n{ctx}\n```",
            })
        if session.workflow_id:
            llm_messages.append({
                "role": "system",
                "content": f"Workflow deployed in n8n: ID {session.workflow_id}",
            })

        # Chat history (last 20)
        for msg in session.messages[-20:]:
            llm_messages.append({"role": msg["role"], "content": msg["content"]})

        # LLM call
        session.state = "generating"
        response = _get_chat_completion(llm_messages)
        session.messages.append({"role": "assistant", "content": response})

        # Extract workflow JSON
        workflow_extracted = self._extract_workflow_json(response)
        if workflow_extracted:
            session.workflow_json = workflow_extracted
            session.workflow_name = workflow_extracted.get("name", "VibeCoder Workflow")
            session.state = "iterating"
            _broadcast_to_electron({
                "type": "n8n_vibecoder_workflow_ready",
                "session_id": session_id,
                "workflow_name": session.workflow_name,
                "nodes_count": len(workflow_extracted.get("nodes", [])),
            })
        else:
            session.state = "iterating" if session.workflow_json else "chat"

        return {
            "success": True,
            "session_id": session_id,
            "response": response,
            "state": session.state,
            "has_workflow": session.workflow_json is not None,
            "workflow_name": session.workflow_name,
            "workflow_id": session.workflow_id,
        }

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session info and history."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "message": f"Session '{session_id}' nicht gefunden."}
        return {"success": True, **session.to_dict(), "messages": session.messages}

    def list_sessions(self) -> Dict[str, Any]:
        """List all active sessions."""
        sessions = [s.to_dict() for s in self._sessions.values()]
        return {
            "success": True,
            "sessions": sorted(sessions, key=lambda s: s["created_at"], reverse=True),
            "count": len(sessions),
        }

    def deploy_workflow(self, session_id: str) -> Dict[str, Any]:
        """Deploy the current session's workflow to n8n."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "message": f"Session '{session_id}' nicht gefunden."}
        return self._handle_deploy(session)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_deploy(self, session: WorkflowChatSession) -> Dict[str, Any]:
        """Deploy or update workflow in n8n."""
        if not session.workflow_json:
            return {
                "success": False,
                "session_id": session.session_id,
                "message": "Kein Workflow vorhanden. Beschreibe erst was du brauchst.",
                "state": session.state,
            }

        from spaces.n8n.tools.n8n_api_client import get_n8n_client
        client = get_n8n_client()

        health = client.health_check()
        if not health.get("online"):
            return {
                "success": False,
                "session_id": session.session_id,
                "message": "n8n ist nicht erreichbar. Starte mit: docker compose -f docker-compose.n8n.yml up -d",
            }

        if session.workflow_id:
            updated = client.update_workflow(session.workflow_id, session.workflow_json)
            if "error" in updated:
                return {
                    "success": False,
                    "session_id": session.session_id,
                    "message": f"Update fehlgeschlagen: {updated['error']}",
                }
            _broadcast_to_electron({
                "type": "n8n_workflow_updated",
                "workflow_id": session.workflow_id,
                "workflow_name": session.workflow_name,
            })
            response_msg = f"Workflow '{session.workflow_name}' aktualisiert in n8n."
        else:
            created = client.create_workflow(session.workflow_json)
            if "error" in created:
                return {
                    "success": False,
                    "session_id": session.session_id,
                    "message": f"Deploy fehlgeschlagen: {created['error']}",
                }
            session.workflow_id = created.get("id", "")
            session.workflow_name = created.get("name", session.workflow_name)
            _broadcast_to_electron({
                "type": "n8n_workflow_created",
                "workflow_id": session.workflow_id,
                "workflow_name": session.workflow_name,
                "n8n_url": f"{client.base_url}/workflow/{session.workflow_id}",
            })
            response_msg = f"Workflow '{session.workflow_name}' deployed! ID: {session.workflow_id}"

        session.messages.append({"role": "assistant", "content": response_msg})
        return {
            "success": True,
            "session_id": session.session_id,
            "message": response_msg,
            "response": response_msg,
            "workflow_id": session.workflow_id,
            "workflow_name": session.workflow_name,
            "workflow_url": f"{client.base_url}/workflow/{session.workflow_id}",
            "state": "iterating",
        }

    def _extract_workflow_json(self, text: str) -> Optional[Dict]:
        """Extract n8n workflow JSON from LLM response."""
        import re

        match = re.search(r'```n8n-workflow\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "nodes" in data:
                    return data
            except json.JSONDecodeError:
                pass

        for match in re.finditer(r'```json\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                if "nodes" in data and "connections" in data:
                    return data
            except json.JSONDecodeError:
                continue

        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager = WorkflowChatManager()


def get_workflow_chat_manager() -> WorkflowChatManager:
    return _manager
