"""
Roarboot Backend Agent

Backend agent for the Roarboot Space that listens to the roarboot Redis stream
and routes tasks to Rowboat's API via the Python SDK.

Integrates with the existing stream architecture:
- events:tasks:roarboot ← This agent

Usage:
    agent = get_roarboot_agent()
    await agent.start()  # Starts listening to Redis stream
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class RoarbootBackendAgent(BaseBackendAgent):
    """
    Backend agent for Roarboot Space (Rowboat Knowledge Graph).

    Extends BaseBackendAgent to use standard event bus subscription.
    Routes voice commands to Rowboat API tools.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        # Knowledge graph operations
        "roarboot.search": "search_knowledge",
        "roarboot.query": "query_knowledge",

        # Content generation
        "roarboot.email_draft": "draft_email",
        "roarboot.meeting_brief": "generate_meeting_brief",
        "roarboot.deck": "generate_deck",

        # Voice notes
        "roarboot.voice_note": "process_voice_note",

        # Docker management
        "roarboot.docker.start": "start_docker",
        "roarboot.docker.stop": "stop_docker",
        "roarboot.docker.restart": "restart_docker",
        "roarboot.docker.status": "docker_status",

        # System
        "roarboot.status": "get_status",
        "roarboot.open": "open_webview",
        "roarboot.reset": "reset_conversation",

        # High-value: Chat, RAG, Upload
        "roarboot.chat": "chat",
        "roarboot.rag.search": "rag_search",
        "roarboot.upload": "upload_document",

        # Medium-value: Graph, Tools
        "roarboot.graph.explore": "explore_graph",
        "roarboot.tools.list": "list_tools",
    }

    # Parameter normalization (classifier output → tool params)
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

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "RoarbootAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:roarboot"

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

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)


# --- Singleton Pattern ---

_roarboot_agent: Optional[RoarbootBackendAgent] = None


def get_roarboot_agent() -> RoarbootBackendAgent:
    """Get or create RoarbootBackendAgent singleton."""
    global _roarboot_agent
    if _roarboot_agent is None:
        _roarboot_agent = RoarbootBackendAgent()
    return _roarboot_agent


__all__ = [
    "RoarbootBackendAgent",
    "get_roarboot_agent",
]
