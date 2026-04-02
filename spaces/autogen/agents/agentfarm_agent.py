"""AgentFarm backend agent for Autogen 0.4 team orchestration.

Follows the BaseBackendAgent pattern -- routes agentfarm.* events to tool functions.
"""
import logging
from typing import Callable, Dict, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class AgentFarmBackendAgent(BaseBackendAgent):
    """Backend agent for the Autogen AgentFarm space."""

    EVENT_TO_TOOL: Dict[str, str] = {
        "agentfarm.create_team":    "create_team",
        "agentfarm.run":            "run_team",
        "agentfarm.status":         "get_farm_status",
        "agentfarm.list_teams":     "list_teams",
        "agentfarm.stop":           "stop_run",
        "agentfarm.results":        "get_run_results",
        "agentfarm.list_templates": "list_templates",
        "agentfarm.collaborate":    "start_collaboration",
    }

    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "agentfarm.create_team": {
            "vorlage": "template_id",
            "template": "template_id",
            "name": "team_name",
        },
        "agentfarm.run": {
            "aufgabe": "task",
            "beschreibung": "task",
            "text": "task",
            "team": "team_id",
        },
        "agentfarm.stop": {
            "run": "run_id",
        },
        "agentfarm.results": {
            "run": "run_id",
        },
    }

    @property
    def name(self) -> str:
        return "AgentFarmAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:agentfarm"

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        return self.EVENT_TO_TOOL.get(event_type)

    def _load_tools(self) -> Dict[str, Callable]:
        tools = {}
        try:
            from spaces.autogen.tools.agentfarm_tools import (
                create_team, run_team, get_farm_status, list_teams,
                stop_run, get_run_results, list_templates, start_collaboration,
            )
            tools.update({
                "create_team": create_team,
                "run_team": run_team,
                "get_farm_status": get_farm_status,
                "list_teams": list_teams,
                "stop_run": stop_run,
                "get_run_results": get_run_results,
                "list_templates": list_templates,
                "start_collaboration": start_collaboration,
            })
        except ImportError as e:
            logger.warning(f"{self.name}: Could not load tools: {e}")
        return tools


# --- Singleton ---
_agentfarm_agent: Optional[AgentFarmBackendAgent] = None


def get_agentfarm_agent() -> AgentFarmBackendAgent:
    global _agentfarm_agent
    if _agentfarm_agent is None:
        _agentfarm_agent = AgentFarmBackendAgent()
    return _agentfarm_agent


__all__ = ["AgentFarmBackendAgent", "get_agentfarm_agent"]
