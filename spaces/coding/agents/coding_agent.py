"""
Coding Agent - Backend agent for Code Generation tools

Listens to events:tasks:coding stream and executes:
- Code generation: generate_code, get_status, cancel
- Preview: start_preview, stop_preview
- Projects: list_generated_projects
- Voice coding: idea_to_project, modify_code
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent
from swarm.event_bus import EventBus

logger = logging.getLogger(__name__)


class CodingAgent(BaseBackendAgent):
    """
    Backend agent for Code Generation domain.

    Handles 8 tools for generating code, managing previews,
    and voice-controlled code modifications.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        # Code generation
        "code.generate": "generate_code",
        "code.status": "get_generation_status",
        "code.cancel": "cancel_generation",
        "code.list": "list_generated_projects",
        # Preview
        "code.preview.start": "start_preview",
        "code.preview.stop": "stop_preview",
        # Voice coding
        "idea.to_project": "idea_to_project_sync",
        "code.modify": "modify_code_sync",
    }

    # Parameter normalization: map classifier output to tool expected params
    PARAM_MAPPING = {
        # generate_code expects "title"
        "code.generate": {"name": "title", "project": "title", "projekt": "title", "project_name": "title"},
        # cancel_generation expects "job_id"
        "code.cancel": {"id": "job_id", "task_id": "job_id"},
        # idea_to_project expects "idea_name"
        "idea.to_project": {"name": "idea_name", "title": "idea_name", "idea": "idea_name"},
        # modify_code expects "instruction"
        "code.modify": {"change": "instruction", "modification": "instruction", "command": "instruction", "aenderung": "instruction"},
    }

    @property
    def stream(self) -> str:
        return EventBus.STREAM_TASKS_CODING

    @property
    def name(self) -> str:
        return "CodingAgent"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load code generation tools."""
        tools = {}

        # Load adapted coding tools
        try:
            from spaces.coding.tools.adapted_coding_tools import (
                generate_code, get_generation_status, start_preview,
                stop_preview, list_generated_projects, cancel_generation
            )
            tools.update({
                "generate_code": generate_code,
                "get_generation_status": get_generation_status,
                "start_preview": start_preview,
                "stop_preview": stop_preview,
                "list_generated_projects": list_generated_projects,
                "cancel_generation": cancel_generation,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} coding tools")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load coding tools: {e}")

        # Load voice coding tools
        try:
            from spaces.coding.tools.voice_coding_tools import (
                idea_to_project_sync, modify_code_sync
            )
            tools.update({
                "idea_to_project_sync": idea_to_project_sync,
                "modify_code_sync": modify_code_sync,
            })
            logger.info(f"{self.name}: Loaded voice coding tools, total: {len(tools)}")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load voice coding tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton instance
_coding_agent: Optional[CodingAgent] = None


def get_coding_agent() -> CodingAgent:
    """Get or create CodingAgent singleton."""
    global _coding_agent
    if _coding_agent is None:
        _coding_agent = CodingAgent()
    return _coding_agent


__all__ = ["CodingAgent", "get_coding_agent"]
