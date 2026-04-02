"""
n8n Backend Agent

Listens to the events:tasks:n8n Redis stream and executes
n8n.* event types via the n8n workflow tools.

Follows the BaseBackendAgent pattern from base_agent.py.
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class N8nBackendAgent(BaseBackendAgent):
    """
    Backend agent for the n8n Workflow Builder Space.

    Handles n8n.* event types:
    - n8n.generate:   Generate workflow from NL description and push to n8n
    - n8n.list:       List all workflows in n8n
    - n8n.status:     Check n8n instance health
    - n8n.activate:   Activate a workflow
    - n8n.deactivate: Deactivate a workflow
    - n8n.delete:     Delete a workflow
    - n8n.execute:    Execute a workflow manually
    - n8n.describe:   Show workflow details
    """

    # Event type -> tool function name mapping
    EVENT_TO_TOOL: Dict[str, str] = {
        "n8n.generate":   "generate_workflow",
        "n8n.list":       "list_workflows",
        "n8n.status":     "get_n8n_status",
        "n8n.activate":   "activate_workflow",
        "n8n.deactivate": "deactivate_workflow",
        "n8n.delete":     "delete_workflow",
        "n8n.execute":    "execute_workflow",
        "n8n.describe":   "describe_workflow",
    }

    # Parameter normalization (classifier output -> tool params)
    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "n8n.generate": {
            "beschreibung": "description",
            "aufgabe": "description",
            "text": "description",
            "workflow": "description",
        },
        "n8n.activate": {
            "name": "name",
            "workflow_name": "name",
            "id": "workflow_id",
        },
        "n8n.deactivate": {
            "name": "name",
            "workflow_name": "name",
            "id": "workflow_id",
        },
        "n8n.delete": {
            "name": "name",
            "workflow_name": "name",
            "id": "workflow_id",
        },
        "n8n.execute": {
            "name": "name",
            "workflow_name": "name",
            "id": "workflow_id",
        },
        "n8n.describe": {
            "name": "name",
            "workflow_name": "name",
            "id": "workflow_id",
        },
    }

    @property
    def name(self) -> str:
        return "N8nAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:n8n"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load n8n workflow tools."""
        tools = {}
        try:
            from spaces.n8n.tools.n8n_workflow_tools import (
                generate_workflow,
                list_workflows,
                get_n8n_status,
                activate_workflow,
                deactivate_workflow,
                delete_workflow,
                execute_workflow,
                describe_workflow,
            )

            tools.update({
                "generate_workflow": generate_workflow,
                "list_workflows": list_workflows,
                "get_n8n_status": get_n8n_status,
                "activate_workflow": activate_workflow,
                "deactivate_workflow": deactivate_workflow,
                "delete_workflow": delete_workflow,
                "execute_workflow": execute_workflow,
                "describe_workflow": describe_workflow,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool function name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton
_n8n_agent: Optional[N8nBackendAgent] = None


def get_n8n_agent() -> N8nBackendAgent:
    """Get or create the N8nBackendAgent singleton."""
    global _n8n_agent
    if _n8n_agent is None:
        _n8n_agent = N8nBackendAgent()
    return _n8n_agent


__all__ = ["N8nBackendAgent", "get_n8n_agent"]
