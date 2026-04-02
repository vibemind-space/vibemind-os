"""
Bubbles Agent - Backend agent for Space/Bubble management

Listens to events:tasks:bubbles stream and executes:
- Bubble tools: list, create, enter, exit, delete, find, stats, score, evaluate, promote, update

MIGRATED FROM: swarm/backend_agents/bubbles_agent.py
"""

import logging
from typing import Dict, Callable, Optional

# NOTE: These imports will be updated as core migration progresses
from swarm.backend_agents.base_agent import BaseBackendAgent
from swarm.event_bus import EventBus

logger = logging.getLogger(__name__)


class BubblesAgent(BaseBackendAgent):
    """
    Backend agent for Bubbles/Spaces domain.

    Handles 13 tools for managing spaces (bubbles) in the multiverse.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        "bubble.list": "list_bubbles",
        "bubble.create": "create_bubble",
        "bubble.enter": "enter_bubble",
        "bubble.exit": "exit_bubble",
        "bubble.back": "exit_bubble",  # Alias for bubble.exit
        "bubble.delete": "delete_bubble",
        "bubble.delete_all_except": "delete_all_bubbles_except",
        "bubble.update": "update_bubble",
        "bubble.find": "find_bubble",
        "bubble.stats": "get_bubble_stats",
        "bubble.score": "score_bubble",
        "bubble.evaluate": "evaluate_bubble_evolution",
        "bubble.promote": "promote_bubble",
        "bubble.current": "get_current_space",
    }

    # Parameter normalization: map classifier output to tool expected params
    PARAM_MAPPING = {
        # bubble.create expects "title" but classifier might use bubble_name/name/space
        "bubble.create": {
            "bubble_name": "title",
            "name": "title",
            "space": "title",
            "space_name": "title",
        },
        # Bubble tools expect "bubble_name" but classifier might use title/name/space
        "bubble.enter": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.delete": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.delete_all_except": {
            "ausnahme": "exceptions",
            "ausnahmen": "exceptions",
            "behalten": "keep",
            "keep": "exceptions",
            "außer": "exceptions",
            "ausser": "exceptions",
            "bubble_name": "exceptions",
            "title": "exceptions",
        },
        "bubble.find": {
            "title": "query",
            "name": "query",
            "space": "query",
            "space_name": "query",
            "search": "query",
        },
        "bubble.stats": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.score": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.evaluate": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        "bubble.promote": {
            "title": "bubble_name",
            "name": "bubble_name",
            "space": "bubble_name",
            "space_name": "bubble_name",
        },
        # bubble.update expects "new_title" but classifier might use title/name
        "bubble.update": {
            "title": "new_title",
            "name": "new_title",
            "neuer_name": "new_title",
            "description": "new_description",
            "beschreibung": "new_description",
        },
    }

    @property
    def stream(self) -> str:
        return EventBus.STREAM_TASKS_BUBBLES

    @property
    def name(self) -> str:
        return "BubblesAgent"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load bubble tools."""
        tools = {}

        try:
            from spaces.ideas.adapted.bubble_tools import (
                list_bubbles,
                create_bubble,
                enter_bubble,
                exit_bubble,
                delete_bubble,
                delete_all_bubbles_except,
                get_bubble_stats,
                score_bubble,
                evaluate_bubble_evolution,
                promote_bubble,
                update_bubble,
            )
            from tools.bubble_tools import find_bubble
            from tools.idea_tools import get_current_space

            tools.update({
                "list_bubbles": list_bubbles,
                "create_bubble": create_bubble,
                "enter_bubble": enter_bubble,
                "exit_bubble": exit_bubble,
                "delete_bubble": delete_bubble,
                "delete_all_bubbles_except": delete_all_bubbles_except,
                "update_bubble": update_bubble,
                "find_bubble": find_bubble,
                "get_bubble_stats": get_bubble_stats,
                "score_bubble": score_bubble,
                "evaluate_bubble_evolution": evaluate_bubble_evolution,
                "promote_bubble": promote_bubble,
                "get_current_space": get_current_space,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} bubble tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load bubble tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton instance
_bubbles_agent: Optional[BubblesAgent] = None


def get_bubbles_agent() -> BubblesAgent:
    """Get or create BubblesAgent singleton."""
    global _bubbles_agent
    if _bubbles_agent is None:
        _bubbles_agent = BubblesAgent()
    return _bubbles_agent


__all__ = ["BubblesAgent", "get_bubbles_agent"]
