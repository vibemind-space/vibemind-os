"""
MiroFish Backend Agent

Backend agent for the MiroFish Space that listens to the mirofish_pred Redis stream
and routes tasks to MiroFish-Offline's Flask API.

Integrates with the existing stream architecture:
- events:tasks:mirofish_pred ← This agent

Usage:
    agent = get_mirofish_agent()
    await agent.start()  # Starts listening to Redis stream
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class MiroFishBackendAgent(BaseBackendAgent):
    """
    Backend agent for MiroFish Space (Prediction Engine).

    Extends BaseBackendAgent to use standard event bus subscription.
    Routes voice commands to MiroFish API tools.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        # Core prediction
        "mirofish.simulate": "simulate",
        "mirofish.predict": "simulate",  # alias
        "mirofish.predict_from_knowledge": "predict_from_knowledge",

        # Graph operations
        "mirofish.graph.build": "build_graph",
        "mirofish.graph.search": "search_graph",

        # Projects
        "mirofish.list_projects": "list_projects",

        # Report interaction
        "mirofish.report.chat": "chat_report",

        # Agent interview
        "mirofish.interview": "interview_agent",

        # Docker management
        "mirofish.docker.start": "start_docker",
        "mirofish.docker.stop": "stop_docker",
        "mirofish.docker.restart": "restart_docker",
        "mirofish.docker.status": "docker_status",

        # Bubble Evaluation
        "mirofish.evaluate": "evaluate_bubble_readiness",

        # System
        "mirofish.status": "get_status",
    }

    # Parameter normalization (classifier output → tool params)
    PARAM_MAPPING = {
        "mirofish.simulate": {
            "anforderung": "requirement",
            "beschreibung": "requirement",
            "description": "requirement",
            "was": "requirement",
            "text": "text",
            "inhalt": "text",
            "content": "text",
            "datei": "file_path",
            "file": "file_path",
            "agenten": "agent_count",
            "agents": "agent_count",
            "runden": "rounds",
        },
        "mirofish.predict": {
            "anforderung": "requirement",
            "beschreibung": "requirement",
            "description": "requirement",
            "was": "requirement",
            "text": "text",
        },
        "mirofish.predict_from_knowledge": {
            "anforderung": "requirement",
            "beschreibung": "requirement",
            "description": "requirement",
            "was": "requirement",
            "suche": "query",
            "suchbegriff": "query",
            "agenten": "agent_count",
            "runden": "rounds",
        },
        "mirofish.graph.build": {
            "anforderung": "requirement",
            "beschreibung": "requirement",
            "description": "requirement",
            "text": "text",
            "datei": "file_path",
        },
        "mirofish.graph.search": {
            "suche": "query",
            "suchbegriff": "query",
            "anfrage": "query",
            "graph": "graph_id",
        },
        "mirofish.report.chat": {
            "frage": "question",
            "question": "question",
            "report": "report_id",
        },
        "mirofish.interview": {
            "agent": "agent_name",
            "name": "agent_name",
            "frage": "question",
            "question": "question",
            "simulation": "simulation_id",
        },
        "mirofish.evaluate": {
            "name": "bubble_name",
            "bubble": "bubble_name",
            "title": "bubble_name",
            "titel": "bubble_name",
            "space": "bubble_name",
        },
    }

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "MiroFishAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:mirofish_pred"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load all MiroFish tools (prediction, graph, docker, system)."""
        tools = {}

        # --- Prediction & Graph Tools ---
        try:
            from spaces.mirofish.tools.mirofish_tools import (
                get_status,
                simulate,
                build_graph,
                search_graph,
                list_projects,
                chat_report,
                interview_agent,
                predict_from_knowledge,
                evaluate_bubble_readiness,
            )

            tools.update({
                "get_status": get_status,
                "simulate": simulate,
                "build_graph": build_graph,
                "search_graph": search_graph,
                "list_projects": list_projects,
                "chat_report": chat_report,
                "interview_agent": interview_agent,
                "predict_from_knowledge": predict_from_knowledge,
                "evaluate_bubble_readiness": evaluate_bubble_readiness,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} prediction/graph tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load mirofish tools: {e}")

        # --- Docker Management Tools ---
        try:
            from spaces.mirofish.tools.docker_tools import (
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

_mirofish_agent: Optional[MiroFishBackendAgent] = None


def get_mirofish_agent() -> MiroFishBackendAgent:
    """Get or create MiroFishBackendAgent singleton."""
    global _mirofish_agent
    if _mirofish_agent is None:
        _mirofish_agent = MiroFishBackendAgent()
    return _mirofish_agent


__all__ = [
    "MiroFishBackendAgent",
    "get_mirofish_agent",
]
