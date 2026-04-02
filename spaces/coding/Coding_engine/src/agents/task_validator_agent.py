# -*- coding: utf-8 -*-
"""
Task Validator Agent - Post-epic validation and fix loop.

Subscribes to EPIC_EXECUTION_COMPLETED. When an epic finishes with
failed tasks, runs TaskValidator.run_fix_loop() to fix them via
MCP Orchestrator + Claude CLI, then unblocks downstream tasks.

Publishes:
- EPIC_TASK_COMPLETED: per fixed task (so other agents see it)
- TASK_VALIDATION_COMPLETE: summary of the fix loop
"""
import asyncio
from pathlib import Path
from typing import Optional
import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class TaskValidatorAgent(AutonomousAgent):
    """
    Post-epic validation agent.

    Listens for EPIC_EXECUTION_COMPLETED events with failed_tasks > 0,
    then uses TaskValidator to fix them via MCP tools and Claude CLI.
    """

    # Prevent running multiple fix loops in parallel
    _running = False

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        max_iterations: int = 3,
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.max_iterations = max_iterations

    @property
    def subscribed_events(self) -> list:
        return [EventType.EPIC_EXECUTION_COMPLETED]

    async def should_act(self, events: list) -> bool:
        if self._running:
            return False

        for event in events:
            if event.type == EventType.EPIC_EXECUTION_COMPLETED:
                result = event.data.get("result", {})
                if result.get("failed_tasks", 0) > 0:
                    return True
        return False

    async def act(self, events: list) -> Optional[Event]:
        from ..tools.task_validator import TaskValidator

        self._running = True
        try:
            # Find the triggering event
            event = next(
                (e for e in events if e.type == EventType.EPIC_EXECUTION_COMPLETED),
                None,
            )
            if not event:
                return None

            epic_id = event.data.get("epic_id", "unknown")
            result_data = event.data.get("result", {})

            self.logger.info(
                "task_validator_agent_start",
                epic_id=epic_id,
                failed_tasks=result_data.get("failed_tasks", 0),
            )

            # Resolve task file
            task_file = self._find_task_file(epic_id)
            if not task_file:
                self.logger.warning("task_validator_agent_no_task_file", epic_id=epic_id)
                return None

            # Run fix loop
            validator = TaskValidator(
                task_file=str(task_file),
                output_dir=self.working_dir,
            )

            summary = await validator.run_fix_loop(
                max_iterations=self.max_iterations,
            )

            # Publish per-fix events
            for r in summary.get("results", []):
                if r.get("fixed"):
                    await self.event_bus.publish(Event(
                        type=EventType.EPIC_TASK_COMPLETED,
                        source=self.name,
                        data={
                            "task_id": r["task_id"],
                            "fixed_by": self.name,
                            "epic_id": epic_id,
                        },
                    ))

            self.logger.info(
                "task_validator_agent_done",
                epic_id=epic_id,
                tasks_fixed=summary.get("tasks_fixed", 0),
                tasks_attempted=summary.get("tasks_attempted", 0),
            )

            # Return summary event
            return Event(
                type=EventType.TASK_VALIDATION_COMPLETE,
                source=self.name,
                data={
                    "epic_id": epic_id,
                    "tasks_fixed": summary.get("tasks_fixed", 0),
                    "tasks_attempted": summary.get("tasks_attempted", 0),
                    "before": summary.get("before", {}),
                    "after": summary.get("after", {}),
                },
            )

        except Exception as e:
            self.logger.error("task_validator_agent_error", error=str(e))
            return None
        finally:
            self._running = False

    def _find_task_file(self, epic_id: str) -> Optional[Path]:
        """
        Locate the task JSON file for the given epic.

        Searches Data/all_services/*/tasks/<epic_id>-tasks.json
        (mirrors EpicOrchestrator._get_task_file_path logic).
        """
        data_dir = Path("Data/all_services")
        if not data_dir.exists():
            return None

        for project_dir in data_dir.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / "tasks" / f"{epic_id.lower()}-tasks.json"
            if candidate.exists():
                return candidate

        return None
