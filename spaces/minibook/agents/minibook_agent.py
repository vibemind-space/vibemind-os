"""
Minibook Backend Agent

Listens to the events:tasks:minibook Redis stream and executes
minibook.* event types via the Minibook tools.

Follows the BaseBackendAgent pattern from base_agent.py.
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class MinibookBackendAgent(BaseBackendAgent):
    """
    Backend agent for the Minibook Space.

    Handles minibook.* event types:
    - minibook.discuss: Start a discussion
    - minibook.collaborate: Start multi-space collaboration
    - minibook.status: Check Minibook connection
    - minibook.results: Get discussion results
    - minibook.list_projects: List projects
    - minibook.poll: Poll for collaboration responses
    """

    # Event type → tool function name mapping
    EVENT_TO_TOOL: Dict[str, str] = {
        "minibook.discuss": "start_discussion",
        "minibook.collaborate": "start_collaboration",
        "minibook.status": "get_minibook_status",
        "minibook.results": "get_discussion_results",
        "minibook.list_projects": "list_projects",
        "minibook.poll": "poll_responses",
    }

    # Parameter normalization (German → English)
    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "minibook.discuss": {
            "anfrage": "message",
            "thema": "topic",
            "nachricht": "message",
        },
        "minibook.collaborate": {
            "aufgabe": "task",
            "ziel": "goal",
            "anfrage": "task",
        },
        "minibook.results": {
            "diskussion": "discussion_id",
        },
    }

    @property
    def name(self) -> str:
        return "MinibookAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:minibook"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load Minibook tools."""
        tools = {}
        try:
            from spaces.minibook.tools.minibook_tools import (
                start_discussion,
                get_minibook_status,
                get_discussion_results,
                list_projects,
            )
            from spaces.minibook.tools.collaboration_tools import (
                start_collaboration,
                poll_responses,
            )

            tools.update({
                "start_discussion": start_discussion,
                "get_minibook_status": get_minibook_status,
                "get_discussion_results": get_discussion_results,
                "list_projects": list_projects,
                "start_collaboration": start_collaboration,
                "poll_responses": poll_responses,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool function name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton
_minibook_agent: Optional[MinibookBackendAgent] = None


def get_minibook_agent() -> MinibookBackendAgent:
    """Get or create the MinibookBackendAgent singleton."""
    global _minibook_agent
    if _minibook_agent is None:
        _minibook_agent = MinibookBackendAgent()
    return _minibook_agent


__all__ = ["MinibookBackendAgent", "get_minibook_agent"]
