"""
CodingBroadcastAgent - Fan-out agent for Code Generation domain.

Migrated from: CodingAgent (backend_agents/coding_agent.py)

Domain prefixes: code.*, idea.to_project
"""

import logging
from typing import Dict, Set, Callable, Optional

from swarm.broadcast.base_broadcast_agent import BaseBroadcastAgent

logger = logging.getLogger(__name__)


class CodingBroadcastAgent(BaseBroadcastAgent):
    """
    Broadcast agent for Code Generation domain.

    Handles 8 tools for generating code, managing previews,
    and voice-controlled code modifications.
    """

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

    PARAM_MAPPING = {
        "code.generate": {
            "name": "title",
            "project": "title",
            "projekt": "title",
            "project_name": "title",
        },
        "code.cancel": {
            "id": "job_id",
            "task_id": "job_id",
        },
        "idea.to_project": {
            "name": "idea_name",
            "title": "idea_name",
            "idea": "idea_name",
        },
        "code.modify": {
            "change": "instruction",
            "modification": "instruction",
            "command": "instruction",
            "aenderung": "instruction",
        },
    }

    @property
    def name(self) -> str:
        return "coding_agent"

    @property
    def domain_prefixes(self) -> Set[str]:
        return {"code."}

    @property
    def profiling_perspective(self) -> str:
        return (
            "Coding/Technik: Technologie-Praeferenzen, Projekttypen, "
            "Code-Generierungs-Muster, Preview-Nutzung, "
            "Komplexitaetsniveau, bevorzugte Tech-Stacks"
        )

    def _load_tools(self) -> Dict[str, Callable]:
        """Load code generation and preview tools."""
        tools = {}

        # Adapted coding tools
        try:
            from spaces.coding.tools.adapted_coding_tools import (
                generate_code,
                get_generation_status,
                start_preview,
                stop_preview,
                list_generated_projects,
                cancel_generation,
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

        # Voice coding tools
        try:
            from spaces.coding.tools.voice_coding_tools import (
                idea_to_project_sync,
                modify_code_sync,
            )
            tools.update({
                "idea_to_project_sync": idea_to_project_sync,
                "modify_code_sync": modify_code_sync,
            })
            logger.info(f"{self.name}: Loaded voice coding tools, total: {len(tools)}")
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load voice coding tools: {e}")

        return tools

    async def evaluate_responsibility(self, intent):
        """
        Extended evaluation to also claim idea.to_project.

        idea.to_project is handled by the CodingAgent despite
        having an 'idea.' prefix.
        """
        if intent.event_type == "idea.to_project":
            from swarm.broadcast.base_broadcast_agent import ResponsibilityEvaluation
            return ResponsibilityEvaluation(
                is_responsible=True,
                confidence=1.0,
                reasoning="idea.to_project is a coding domain event",
                domain_perspective=self.profiling_perspective,
            )
        return await super().evaluate_responsibility(intent)


# --- Singleton ---

_coding_broadcast_agent: Optional[CodingBroadcastAgent] = None


def get_coding_broadcast_agent() -> CodingBroadcastAgent:
    """Get or create CodingBroadcastAgent singleton."""
    global _coding_broadcast_agent
    if _coding_broadcast_agent is None:
        _coding_broadcast_agent = CodingBroadcastAgent()
    return _coding_broadcast_agent


__all__ = ["CodingBroadcastAgent", "get_coding_broadcast_agent"]
