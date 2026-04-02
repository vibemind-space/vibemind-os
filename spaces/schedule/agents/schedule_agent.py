"""
Schedule Backend Agent

Listens to the events:tasks:schedule Redis stream and executes
schedule.* event types via the Schedule tools.

Follows the BaseBackendAgent pattern from base_agent.py.
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class ScheduleBackendAgent(BaseBackendAgent):
    """
    Backend agent for the Schedule Space.

    Handles schedule.* event types:
    - schedule.create: Create a new scheduled task
    - schedule.list:   List scheduled tasks
    - schedule.cancel: Cancel a scheduled task
    - schedule.modify: Modify a scheduled task
    - schedule.status: Get schedule summary
    - schedule.snooze: Snooze a task
    """

    # Event type → tool function name mapping
    EVENT_TO_TOOL: Dict[str, str] = {
        "schedule.create": "create_scheduled_task",
        "schedule.list":   "list_scheduled_tasks",
        "schedule.cancel": "cancel_scheduled_task",
        "schedule.modify": "modify_scheduled_task",
        "schedule.status": "get_schedule_status",
        "schedule.snooze": "snooze_scheduled_task",
    }

    # Parameter normalization (classifier output → tool params)
    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "schedule.create": {
            "text": "user_text",
            "eingabe": "user_text",
            "aufgabe": "user_text",
            "titel": "title",
            "name": "title",
        },
        "schedule.cancel": {
            "name": "title",
            "aufgabe": "title",
            "id": "task_id",
        },
        "schedule.modify": {
            "name": "title",
            "aufgabe": "title",
            "id": "task_id",
            "zeit": "new_time",
            "neue_zeit": "new_time",
            "aktion": "new_action",
        },
        "schedule.snooze": {
            "name": "title",
            "aufgabe": "title",
            "id": "task_id",
            "text": "user_text",
            "minuten": "minutes",
        },
    }

    @property
    def name(self) -> str:
        return "ScheduleAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:schedule"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load Schedule tools."""
        tools = {}
        try:
            from spaces.schedule.tools.schedule_tools import (
                create_scheduled_task,
                list_scheduled_tasks,
                cancel_scheduled_task,
                modify_scheduled_task,
                get_schedule_status,
                snooze_scheduled_task,
            )

            tools.update({
                "create_scheduled_task": create_scheduled_task,
                "list_scheduled_tasks": list_scheduled_tasks,
                "cancel_scheduled_task": cancel_scheduled_task,
                "modify_scheduled_task": modify_scheduled_task,
                "get_schedule_status": get_schedule_status,
                "snooze_scheduled_task": snooze_scheduled_task,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool function name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton
_schedule_agent: Optional[ScheduleBackendAgent] = None


def get_schedule_agent() -> ScheduleBackendAgent:
    """Get or create the ScheduleBackendAgent singleton."""
    global _schedule_agent
    if _schedule_agent is None:
        _schedule_agent = ScheduleBackendAgent()
    return _schedule_agent


__all__ = ["ScheduleBackendAgent", "get_schedule_agent"]
