"""
Collaboration Tools - Inter-space coordination via Minibook

Handles:
- Space agent registration (each VibeMind space → Minibook agent)
- Multi-space task coordination (detect needed spaces, post with @mentions)
- Polling for collaboration results
"""

import logging
import os
from typing import Dict, Any, List, Optional

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[MinibookCollab] %s", msg)


# =============================================================================
# Space Agent Registry
# =============================================================================
# Maps VibeMind spaces to Minibook agent names and their role descriptions.
# Used at startup to register all spaces as Minibook agents.

SPACE_AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "ideas": {
        "name": "vibemind_ideas",
        "domain_prefix": "bubble.,idea.,shuttle.",
        "role": (
            "Verwaltet Ideen-Bubbles: erstellen, auflisten, betreten, verlinken, "
            "formatieren, zusammenfassen, erweitern, analysieren. "
            "Zustaendig fuer alles rund um Ideen, Notizen und Brainstorming."
        ),
    },
    "coding": {
        "name": "vibemind_coding",
        "domain_prefix": "code.",
        "role": (
            "Code-Generierung und Projekte: erstellen, modifizieren, Status pruefen, "
            "Previews starten, Projekte auflisten. "
            "Zustaendig fuer Software-Entwicklung und Code."
        ),
    },
    "desktop": {
        "name": "vibemind_desktop",
        "domain_prefix": "desktop.,task.",
        "role": (
            "Desktop-Automatisierung: Apps oeffnen, klicken, tippen, Screenshots, "
            "Scrollen, System-Aufgaben. "
            "Zustaendig fuer Interaktion mit dem Desktop-System."
        ),
    },
    "research": {
        "name": "vibemind_research",
        "domain_prefix": "research.",
        "role": (
            "Web-Recherche: URLs durchsuchen, Inhalte scrapen und zusammenfassen, "
            "Recherche-Ergebnisse als Ideen oder in Rowboat speichern. "
            "Zustaendig fuer Informationsbeschaffung aus dem Web."
        ),
    },
    "rowboat": {
        "name": "vibemind_rowboat",
        "domain_prefix": "roarboot.",
        "role": (
            "Knowledge Graph: Wissen durchsuchen, Emails entwerfen, Meeting-Briefs, "
            "Praesentationen, Voice-Notes verarbeiten. "
            "Zustaendig fuer gespeichertes Wissen und Kontexte."
        ),
    },
    "openclaw": {
        "name": "vibemind_openclaw",
        "domain_prefix": "desktop.",
        "role": (
            "AutoGen Society of Mind: Desktop-Swarm mit Claude CLI, "
            "Browser-Automatisierung, komplexe Multi-Step Desktop-Aufgaben. "
            "Zustaendig fuer fortgeschrittene Desktop-Orchestrierung."
        ),
    },
    "swe_design": {
        "name": "vibemind_swe_design",
        "domain_prefix": "shuttle.",
        "role": (
            "Software Engineering Design Factory: Requirements-Analyse, "
            "Spezifikations-Generierung, Architektur-Design. "
            "Zustaendig fuer die Shuttle-Pipeline von Idee zu Spezifikation."
        ),
    },
    "transformer": {
        "name": "vibemind_transformer",
        "domain_prefix": "shuttle.",
        "role": (
            "Transformer Pipeline: Wandelt Bubbles in Coding-Projekte um, "
            "Ideen-zu-Spezifikation, Shuttle-Verarbeitung. "
            "Zustaendig fuer die Umwandlung von Ideen in ausfuehrbare Specs."
        ),
    },
    "schedule": {
        "name": "vibemind_schedule",
        "domain_prefix": "schedule.",
        "role": (
            "Zeitplan und Erinnerungen: Erstellen, auflisten, aendern, abbrechen "
            "von geplanten Aufgaben, Erinnerungen und wiederkehrenden Tasks. "
            "Zustaendig fuer alles mit Zeitbezug (in X Minuten, um X Uhr, jeden Montag)."
        ),
    },
    "n8n": {
        "name": "vibemind_n8n",
        "domain_prefix": "n8n.",
        "role": (
            "n8n Workflow Builder: Workflows generieren, auflisten, aktivieren, "
            "deaktivieren, loeschen, testen. Society of Mind Multi-Agent System "
            "plant, baut und testet n8n Workflows iterativ via Chat Trigger. "
            "Zustaendig fuer Automatisierung und Workflow-Erstellung."
        ),
    },
}

# Keywords that hint at a specific space being needed
SPACE_KEYWORDS: Dict[str, List[str]] = {
    "ideas": ["idee", "bubble", "notiz", "brainstorm", "sammle", "verlinke", "formatiere"],
    "coding": ["code", "app", "programm", "software", "projekt", "react", "python", "generier"],
    "desktop": ["oeffne", "klick", "screenshot", "desktop", "app starten", "fenster"],
    "research": ["recherchier", "recherche ", "such ", "web", "scrape", "zusammenfass", "internet", "google"],
    "rowboat": ["wissen", "knowledge", "email", "meeting", "brief", "praesentation", "dokument", "document", "zusammenfassung", "summary", "deck", "notiz"],
    "openclaw": ["autogen", "swarm", "browser", "claude cli", "multi-step", "orchestrier"],
    "swe_design": ["spec", "spezifikation", "requirement", "architektur", "design factory"],
    "transformer": ["transform", "umwandel", "pipeline", "shuttle"],
    "schedule": ["erinner", "erinnerung", "alarm", "timer", "zeitplan", "schedule", "snooze", "taeglich", "wecker"],
    "n8n": ["n8n", "workflow", "automatisier", "automation", "webhook", "trigger", "pipeline", "agent workflow"],
}


def register_all_space_agents(
    client: "MinibookClient",
    project_id: str = None,
) -> str:
    """
    Register all VibeMind spaces as Minibook agents and join the collaboration project.

    If no project_id is provided, creates the "VibeMind Collaboration" project
    and registers the orchestrator agent first.

    Args:
        client: MinibookClient instance
        project_id: Optional Minibook project ID (auto-created if None)

    Returns:
        The collaboration project ID
    """
    # Register orchestrator agent first (needed to create project)
    orchestrator_name = "vibemind_orchestrator"
    if not client.has_agent(orchestrator_name):
        try:
            client.register_agent(orchestrator_name)
            _debug_print(f"Registered orchestrator agent '{orchestrator_name}'")
        except Exception as e:
            _logger.warning(f"Could not register orchestrator: {e}")

    # Create or use existing collaboration project
    if not project_id:
        try:
            project = client.create_project(
                "VibeMind Collaboration",
                "Inter-space collaboration for VibeMind workspace",
                agent_name=orchestrator_name,
            )
            project_id = project.get("id", "")
            _debug_print(f"Created collaboration project: {project_id}")
        except Exception as e:
            _logger.warning(f"Could not create project: {e}")
            # Try to find existing project
            try:
                projects = client.list_projects(agent_name=orchestrator_name)
                for p in projects:
                    if p.get("name") == "VibeMind Collaboration":
                        project_id = p.get("id", "")
                        break
            except Exception:
                pass
            if not project_id:
                _debug_print("FAILED to create or find collaboration project")
                return ""

    client.project_id = project_id

    # Register each space as a Minibook agent
    for space_key, agent_info in SPACE_AGENT_REGISTRY.items():
        agent_name = agent_info["name"]
        role = agent_info["role"]

        try:
            if not client.has_agent(agent_name):
                client.register_agent(agent_name)

            client.join_project(project_id, agent_name, role)
            _debug_print(f"Registered space '{space_key}' as agent '{agent_name}'")

        except Exception as e:
            _logger.warning(f"Could not register space '{space_key}': {e}")
            _debug_print(f"FAILED to register '{space_key}': {e}")

    _debug_print(f"Registered {len(SPACE_AGENT_REGISTRY)} space agents for project {project_id}")
    return project_id


def detect_needed_spaces(task: str) -> List[str]:
    """
    Analyze a task description to determine which spaces are needed.

    Uses keyword matching against SPACE_KEYWORDS to identify relevant spaces.

    Args:
        task: Natural language task description

    Returns:
        List of space keys (e.g., ["research", "ideas"])
    """
    task_lower = task.lower()
    needed = []

    for space_key, keywords in SPACE_KEYWORDS.items():
        for kw in keywords:
            if kw in task_lower:
                if space_key not in needed:
                    needed.append(space_key)
                break

    # If no spaces detected, default to ideas (most common)
    if not needed:
        needed = ["ideas"]

    return needed


def start_collaboration(task: str, goal: str = "") -> Dict[str, Any]:
    """
    Start a multi-space collaboration task.

    1. Detects which spaces are needed based on task keywords
    2. Posts a discussion with @mentions to the collaboration project
    3. Returns immediately with acknowledgment (non-blocking)

    The DiscussionPollerWorker will track responses and deliver results async.

    Args:
        task: The user's request in natural language
        goal: Optional goal description

    Returns:
        Dict with success, post_id, mentioned_agents, and response_hint
    """
    from .minibook_client import get_minibook_client

    client = get_minibook_client()

    # Check connection
    status = client.get_status()
    if not status.get("success"):
        return {
            "success": False,
            "error": "Minibook nicht erreichbar",
            "response_hint": "Minibook ist gerade nicht verfuegbar. Ich versuche es direkt.",
        }

    project_id = client.project_id
    if not project_id:
        return {
            "success": False,
            "error": "Kein Collaboration-Projekt konfiguriert",
            "response_hint": "Das Collaboration-System ist noch nicht eingerichtet.",
        }

    # Detect which spaces are needed
    needed_spaces = detect_needed_spaces(task)
    _debug_print(f"Collaboration: needed spaces = {needed_spaces} for task: {task[:100]}")

    # Build @mentions
    mentions = []
    mentioned_agents = []
    for space_key in needed_spaces:
        agent_info = SPACE_AGENT_REGISTRY.get(space_key)
        if agent_info:
            agent_name = agent_info["name"]
            mentions.append(f"@{agent_name}")
            mentioned_agents.append(agent_name)

    # Build discussion post content
    mention_str = " ".join(mentions)
    full_goal = f" Ziel: {goal}" if goal else ""
    post_content = f"Aufgabe: {task}{full_goal}\n\n{mention_str} bitte bearbeitet euren Teil."

    try:
        # Post to Minibook
        post_data = client.create_post(
            project_id=project_id,
            content=post_content,
            agent_name="vibemind_orchestrator",
            post_type="discussion",
        )
        post_id = post_data.get("id", "")

        # Register with the discussion poller for async tracking
        # This is done via the worker module — import lazily to avoid circular deps
        try:
            from spaces.minibook.workers.minibook_workers import get_discussion_poller
            poller = get_discussion_poller()
            if poller:
                poller.track_discussion(
                    post_id=post_id,
                    mentioned_agents=mentioned_agents,
                    original_request=task,
                )
        except Exception as e:
            _logger.warning(f"Could not register discussion with poller: {e}")

        space_names = ", ".join(needed_spaces)
        _debug_print(f"Collaboration started: post_id={post_id}, spaces={space_names}")

        return {
            "success": True,
            "post_id": post_id,
            "mentioned_agents": mentioned_agents,
            "needed_spaces": needed_spaces,
            "response_hint": (
                f"Ich koordiniere das mit {space_names}. "
                "Die Ergebnisse kommen gleich."
            ),
        }

    except Exception as e:
        _logger.error(f"Collaboration post failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "response_hint": f"Konnte die Zusammenarbeit nicht starten: {e}",
        }


def poll_responses() -> Dict[str, Any]:
    """
    Manually poll for collaboration responses.

    Checks the discussion poller for any completed discussions.

    Returns:
        Dict with pending discussion count and any completed results
    """
    try:
        from spaces.minibook.workers.minibook_workers import get_discussion_poller
        poller = get_discussion_poller()
        if not poller:
            return {
                "success": False,
                "response_hint": "Discussion Poller ist nicht aktiv.",
            }

        active = poller.active_discussion_count
        return {
            "success": True,
            "active_discussions": active,
            "response_hint": (
                f"Es laufen {active} Diskussionen."
                if active > 0
                else "Keine aktiven Diskussionen."
            ),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "response_hint": f"Fehler beim Polling: {e}",
        }


__all__ = [
    "SPACE_AGENT_REGISTRY",
    "SPACE_KEYWORDS",
    "register_all_space_agents",
    "detect_needed_spaces",
    "start_collaboration",
    "poll_responses",
]
