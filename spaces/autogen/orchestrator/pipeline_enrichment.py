"""
Pipeline Enrichment — Multi-turn voice/chat dialog to enrich the task description
before starting the HybridPipeline.

Rachel asks clarifying questions to build a complete spec:
1. What does the team do? (already from user)
2. What data sources? (CRM, API, CSV, DB?)
3. What output format? (Report, Email, Dashboard?)
4. Any specific tools/MCP servers?
5. Missing API keys / credentials check
6. Confirmation before pipeline start

Works with both Voice (Rachel) and Chat (ClawPort).
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default MCP servers always available
DEFAULT_MCP_SERVERS = [
    {"name": "context7", "description": "Library documentation lookup (AutoGen, FastAPI, etc.)"},
    {"name": "web_fetch", "description": "Fetch and read web pages"},
    {"name": "filesystem", "description": "Read/write local files"},
]

# Optional MCP servers that require API keys
MCP_SERVER_CREDENTIALS: Dict[str, Dict[str, str]] = {
    "brave-search": {"env_key": "BRAVE_API_KEY", "label": "Brave Search API Key"},
    "brave": {"env_key": "BRAVE_API_KEY", "label": "Brave Search API Key"},
    "postgres": {"env_key": "POSTGRES_URL", "label": "PostgreSQL Connection URL"},
    "github": {"env_key": "GITHUB_TOKEN", "label": "GitHub Token"},
    "tavily": {"env_key": "TAVILY_API_KEY", "label": "Tavily API Key"},
    "supabase": {"env_key": "SUPABASE_URL", "label": "Supabase URL"},
}

# Questions Rachel asks (in order)
ENRICHMENT_QUESTIONS = [
    {
        "id": "data_sources",
        "question": "Was fuer Datenquellen soll das Team nutzen? Z.B. API, Datenbank, CSV, Web-Scraping?",
        "question_en": "What data sources? API, database, CSV, web scraping?",
        "extract_key": "data_sources",
        "skip_if": ["datenquelle", "datenbank", "api", "csv", "scrape", "web"],
    },
    {
        "id": "output_format",
        "question": "Was soll der Output sein? Report, Email, Dashboard, JSON-API?",
        "question_en": "What output? Report, email, dashboard, JSON API?",
        "extract_key": "output_format",
        "skip_if": ["report", "email", "dashboard", "json", "pdf", "bericht"],
    },
    {
        "id": "mcp_servers",
        "question": "Sollen spezielle Tools aktiviert werden? Wir haben: brave-search (Web-Suche), postgres (Datenbank), context7 (Doku-Lookup). Oder soll ich automatisch auswaehlen?",
        "question_en": "Any specific MCP tools? brave-search, postgres, context7? Or auto-select?",
        "extract_key": "mcp_hint",
        "skip_if": ["brave", "postgres", "mcp", "tool", "server"],
    },
]


# ---------------------------------------------------------------------------
# Credentials Detection
# ---------------------------------------------------------------------------

def _detect_requested_servers(task: str, answers: Dict[str, str]) -> List[str]:
    """Extract which optional MCP servers the user wants from task + answers."""
    text = f"{task} {answers.get('data_sources', '')} {answers.get('mcp_hint', '')}".lower()
    requested = []
    for server_name in MCP_SERVER_CREDENTIALS:
        if server_name in text:
            requested.append(server_name)
    # Infer from data source answers
    if any(kw in text for kw in ["datenbank", "database", "sql", "postgresql"]):
        if "postgres" not in requested:
            requested.append("postgres")
    if any(kw in text for kw in ["web-suche", "web search", "recherche"]):
        if "brave-search" not in requested and "brave" not in requested:
            requested.append("brave-search")
    if any(kw in text for kw in ["github", "repo", "repository"]):
        if "github" not in requested:
            requested.append("github")
    return requested


def _find_missing_credentials(requested_servers: List[str]) -> List[Dict[str, str]]:
    """Check which API keys are missing from the environment for requested servers."""
    missing = []
    seen_keys = set()
    for server in requested_servers:
        cred = MCP_SERVER_CREDENTIALS.get(server)
        if not cred:
            continue
        env_key = cred["env_key"]
        if env_key in seen_keys:
            continue
        seen_keys.add(env_key)
        val = os.getenv(env_key, "").strip()
        if not val:
            missing.append({"server": server, "env_key": env_key, "label": cred["label"]})
    return missing


def _save_credential_to_env(env_key: str, value: str) -> bool:
    """Save a credential to .env file and set in current environment."""
    os.environ[env_key] = value

    # Also persist to .env file
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parents[4] / ".env.example"
        if not env_path.exists():
            logger.warning(f"No .env file found, credential {env_key} set in memory only")
            return True

    try:
        content = env_path.with_name(".env").read_text(encoding="utf-8") if env_path.with_name(".env").exists() else ""
        lines = content.splitlines()

        # Update existing key or append
        updated = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{env_key}=") or stripped.startswith(f"# {env_key}="):
                lines[i] = f"{env_key}={value}"
                updated = True
                break

        if not updated:
            lines.append(f"{env_key}={value}")

        env_path.with_name(".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Saved {env_key} to .env")
        return True
    except Exception as e:
        logger.warning(f"Could not write {env_key} to .env: {e}")
        return True  # Still set in memory


def needs_enrichment(task_description: str) -> bool:
    """Check if the task description is detailed enough or needs clarification."""
    words = task_description.split()

    # Short descriptions (< 8 words) always need enrichment
    if len(words) < 8:
        return True

    # If user already mentioned specific details, skip enrichment
    detail_indicators = [
        "agent", "datenbank", "api", "report", "email", "csv",
        "postgres", "brave", "mcp", "tool", "dashboard",
        "pdf", "json", "webhook", "scrape", "fetch",
    ]
    detail_count = sum(1 for w in task_description.lower().split()
                       if any(d in w for d in detail_indicators))

    # If 3+ detail words found, user knows what they want
    return detail_count < 3


def get_next_question(task_description: str, answered: Dict[str, str]) -> Optional[Dict]:
    """Get the next unanswered question, skipping if already covered."""
    text_lower = task_description.lower()

    for q in ENRICHMENT_QUESTIONS:
        if q["id"] in answered:
            continue

        # Skip if task description already contains relevant keywords
        if any(kw in text_lower for kw in q["skip_if"]):
            continue

        return q

    return None  # All questions answered or skipped


def build_enriched_description(
    original_task: str,
    answers: Dict[str, str],
) -> str:
    """Combine original task + answers into a rich task description."""
    parts = [original_task]

    if answers.get("data_sources"):
        parts.append(f"Datenquellen: {answers['data_sources']}")

    if answers.get("output_format"):
        parts.append(f"Output: {answers['output_format']}")

    if answers.get("mcp_hint"):
        parts.append(f"Tools: {answers['mcp_hint']}")

    return ". ".join(parts)


def build_confirmation_message(
    original_task: str,
    answers: Dict[str, str],
) -> str:
    """Build a human-readable confirmation before pipeline start."""
    lines = ["Ich starte die Pipeline mit:"]
    lines.append(f"  Aufgabe: {original_task}")

    if answers.get("data_sources"):
        lines.append(f"  Datenquellen: {answers['data_sources']}")
    if answers.get("output_format"):
        lines.append(f"  Output: {answers['output_format']}")
    if answers.get("mcp_hint"):
        lines.append(f"  Tools: {answers['mcp_hint']}")
    else:
        lines.append(f"  Tools: context7, web_fetch, filesystem (Standard)")

    # Show configured credentials
    requested = _detect_requested_servers(original_task, answers)
    if requested:
        configured = [s for s in requested if os.getenv(MCP_SERVER_CREDENTIALS.get(s, {}).get("env_key", ""), "")]
        if configured:
            lines.append(f"  Credentials: {', '.join(configured)} (konfiguriert)")

    lines.append("Soll ich loslegen?")
    return "\n".join(lines)


class PipelineEnrichment:
    """Manages the multi-turn enrichment conversation.

    Flow: enrichment questions → credentials check → confirmation → ready.
    """

    def __init__(self):
        self._active_sessions: Dict[str, Dict] = {}

    def start_session(self, session_id: str, task_description: str) -> Dict[str, Any]:
        """Start enrichment for a new pipeline request.

        Returns either:
        - {"action": "ask", "question": "..."} — need more info
        - {"action": "ready", "enriched_task": "..."} — ready to start
        """
        if not needs_enrichment(task_description):
            # Even without enrichment, check credentials for servers mentioned in task
            missing = _find_missing_credentials(_detect_requested_servers(task_description, {}))
            if missing:
                session = {
                    "task": task_description,
                    "answers": {},
                    "state": "credentials",
                    "missing_creds": missing,
                    "cred_index": 0,
                }
                self._active_sessions[session_id] = session
                return self._ask_next_credential(session)

            return {
                "action": "ready",
                "enriched_task": task_description,
                "confirmation": build_confirmation_message(task_description, {}),
            }

        session = {
            "task": task_description,
            "answers": {},
            "state": "asking",
            "missing_creds": [],
            "cred_index": 0,
        }
        self._active_sessions[session_id] = session

        next_q = get_next_question(task_description, {})
        if next_q:
            return {"action": "ask", "question": next_q["question"], "question_id": next_q["id"]}
        else:
            return self._transition_to_credentials_or_confirm(session)

    def answer(self, session_id: str, answer_text: str) -> Dict[str, Any]:
        """Process user's answer and return next question or ready state."""
        session = self._active_sessions.get(session_id)
        if not session:
            return {"action": "error", "message": "No active enrichment session"}

        # --- Credentials phase ---
        if session["state"] == "credentials":
            return self._handle_credential_answer(session, answer_text)

        # --- Enrichment questions phase ---
        # Find which question we're answering
        next_q = get_next_question(session["task"], session["answers"])
        if next_q:
            session["answers"][next_q["extract_key"]] = answer_text

        # Check if more questions needed
        next_q = get_next_question(session["task"], session["answers"])
        if next_q:
            return {"action": "ask", "question": next_q["question"], "question_id": next_q["id"]}

        # All enrichment questions answered — check credentials
        return self._transition_to_credentials_or_confirm(session)

    def confirm(self, session_id: str, confirmed: bool = True) -> Dict[str, Any]:
        """User confirmed — return enriched task or cancel."""
        session = self._active_sessions.pop(session_id, None)
        if not session:
            return {"action": "error", "message": "No active session"}

        if confirmed:
            return {"action": "ready", "enriched_task": session.get("enriched_task", session["task"])}
        else:
            return {"action": "cancelled"}

    def cancel(self, session_id: str):
        """Cancel enrichment session."""
        self._active_sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Credentials Flow
    # ------------------------------------------------------------------

    def _transition_to_credentials_or_confirm(self, session: Dict) -> Dict[str, Any]:
        """After enrichment questions: check for missing API keys, then confirm."""
        requested = _detect_requested_servers(session["task"], session["answers"])
        missing = _find_missing_credentials(requested)

        if missing:
            session["state"] = "credentials"
            session["missing_creds"] = missing
            session["cred_index"] = 0
            return self._ask_next_credential(session)

        # No missing credentials — go straight to confirmation
        return self._build_confirm_response(session)

    def _ask_next_credential(self, session: Dict) -> Dict[str, Any]:
        """Ask for the next missing API key."""
        idx = session["cred_index"]
        missing = session["missing_creds"]

        if idx >= len(missing):
            # All credentials collected — confirm
            return self._build_confirm_response(session)

        cred = missing[idx]
        question = (
            f"Fuer {cred['server']} brauche ich den {cred['label']}. "
            f"Bitte gib den Wert fuer {cred['env_key']} ein, "
            f"oder sag 'skip' um {cred['server']} ohne Key zu nutzen."
        )
        return {
            "action": "ask",
            "question": question,
            "question_id": f"cred_{cred['env_key']}",
            "credential_request": True,
            "env_key": cred["env_key"],
        }

    def _handle_credential_answer(self, session: Dict, answer_text: str) -> Dict[str, Any]:
        """Process a credential answer (API key value or 'skip')."""
        idx = session["cred_index"]
        missing = session["missing_creds"]

        if idx < len(missing):
            cred = missing[idx]
            answer_clean = answer_text.strip()

            if answer_clean.lower() not in ("skip", "ueberspringen", "nein", "no", ""):
                _save_credential_to_env(cred["env_key"], answer_clean)
                logger.info(f"Credential {cred['env_key']} configured for {cred['server']}")
            else:
                logger.info(f"Credential {cred['env_key']} skipped by user")

        session["cred_index"] = idx + 1
        return self._ask_next_credential(session)

    def _build_confirm_response(self, session: Dict) -> Dict[str, Any]:
        """Build the enriched task and confirmation message."""
        enriched = build_enriched_description(session["task"], session["answers"])
        confirmation = build_confirmation_message(session["task"], session["answers"])

        session["state"] = "confirming"
        session["enriched_task"] = enriched

        return {
            "action": "confirm",
            "enriched_task": enriched,
            "confirmation": confirmation,
        }


# Singleton
_enrichment = PipelineEnrichment()


def get_pipeline_enrichment() -> PipelineEnrichment:
    return _enrichment
