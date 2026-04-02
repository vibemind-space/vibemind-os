"""
Roarboot Broadcast Agent

Fan-out broadcast agent for the Roarboot Space.
Handles all roarboot.* events: knowledge graph operations,
content generation, Docker management, and system commands.

Follows the BaseBroadcastAgent pattern from spaces/ideas/broadcast/.
"""

import logging
from typing import Dict, Set, Callable, Optional

from swarm.broadcast.base_broadcast_agent import BaseBroadcastAgent

logger = logging.getLogger(__name__)


class RoarbootBroadcastAgent(BaseBroadcastAgent):
    """
    Broadcast agent for the Roarboot Space (Rowboat Knowledge Graph).

    Handles all roarboot.* event types via fan-out broadcast.
    Merges knowledge, content, Docker, and system tools.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        # === Knowledge Graph Operations ===
        "roarboot.search": "search_knowledge",
        "roarboot.query": "query_knowledge",

        # === Content Generation ===
        "roarboot.email_draft": "draft_email",
        "roarboot.meeting_brief": "generate_meeting_brief",
        "roarboot.deck": "generate_deck",
        "roarboot.voice_note": "process_voice_note",

        # === Docker Management ===
        "roarboot.docker.start": "start_docker",
        "roarboot.docker.stop": "stop_docker",
        "roarboot.docker.restart": "restart_docker",
        "roarboot.docker.status": "docker_status",

        # === System ===
        "roarboot.status": "get_status",
        "roarboot.open": "open_webview",
        "roarboot.reset": "reset_conversation",
    }

    # Parameter normalization (classifier output -> tool params)
    PARAM_MAPPING = {
        "roarboot.search": {
            "suche": "query",
            "suchbegriff": "query",
            "text": "query",
            "anfrage": "query",
        },
        "roarboot.query": {
            "name": "subject",
            "person": "subject",
            "projekt": "subject",
            "thema": "subject",
            "topic": "subject",
            "frage": "question",
        },
        "roarboot.email_draft": {
            "empfaenger": "recipient",
            "an": "recipient",
            "to": "recipient",
            "betreff": "topic",
            "thema": "topic",
            "kontext": "context",
        },
        "roarboot.meeting_brief": {
            "name": "meeting",
            "titel": "meeting",
            "title": "meeting",
            "teilnehmer": "participants",
        },
        "roarboot.deck": {
            "thema": "topic",
            "titel": "topic",
            "title": "topic",
            "kontext": "context",
        },
        "roarboot.voice_note": {
            "notiz": "text",
            "note": "text",
            "inhalt": "text",
            "content": "text",
        },
        "roarboot.reset": {
            "kontext": "context",
            "gespraech": "context",
        },
    }

    @property
    def name(self) -> str:
        return "roarboot_agent"

    @property
    def domain_prefixes(self) -> Set[str]:
        return {"roarboot."}

    @property
    def profiling_perspective(self) -> str:
        return (
            "Du analysierst Nutzerverhalten im Kontext von Wissensmanagement. "
            "Welche Themen sucht der Nutzer? Welche Kontakte sind wichtig? "
            "Welche Muster gibt es bei Email-Entwuerfen und Meeting-Vorbereitungen?"
        )

    def _load_tools(self) -> Dict[str, Callable]:
        """Load all Roarboot tools (knowledge, content, docker, system)."""
        tools = {}

        # --- Knowledge & Content Tools ---
        try:
            from spaces.rowboat.tools.roarboot_tools import (
                search_knowledge,
                query_knowledge,
                draft_email,
                generate_meeting_brief,
                generate_deck,
                process_voice_note,
                get_status,
                open_webview,
                reset_conversation,
            )

            tools.update({
                "search_knowledge": search_knowledge,
                "query_knowledge": query_knowledge,
                "draft_email": draft_email,
                "generate_meeting_brief": generate_meeting_brief,
                "generate_deck": generate_deck,
                "process_voice_note": process_voice_note,
                "get_status": get_status,
                "open_webview": open_webview,
                "reset_conversation": reset_conversation,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} knowledge/content tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load roarboot tools: {e}")

        # --- Docker Management Tools ---
        try:
            from spaces.rowboat.tools.docker_tools import (
                start_docker,
                stop_docker,
                restart_docker,
                docker_status,
            )

            tools.update({
                "start_docker": start_docker,
                "stop_docker": stop_docker,
                "restart_docker": restart_docker,
                "docker_status": docker_status,
            })
            logger.info(f"{self.name}: Loaded 4 Docker tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load Docker tools: {e}")

        logger.info(f"{self.name}: Total tools loaded: {len(tools)}")
        return tools


# --- Singleton Pattern ---

_roarboot_broadcast_agent: Optional[RoarbootBroadcastAgent] = None


def get_roarboot_broadcast_agent() -> RoarbootBroadcastAgent:
    """Get or create RoarbootBroadcastAgent singleton."""
    global _roarboot_broadcast_agent
    if _roarboot_broadcast_agent is None:
        _roarboot_broadcast_agent = RoarbootBroadcastAgent()
    return _roarboot_broadcast_agent


__all__ = [
    "RoarbootBroadcastAgent",
    "get_roarboot_broadcast_agent",
]
