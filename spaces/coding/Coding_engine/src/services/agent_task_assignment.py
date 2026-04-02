"""Agent Task Assignment -- assigns tasks to agents based on availability
and capability.

Provides:
- Task assignment with priority and metadata
- Assignment completion and reassignment
- Per-agent workload tracking
- Pending assignment queries
- Callback-based change notifications
- Max-entries pruning to bound memory usage

Usage::

    manager = AgentTaskAssignment()

    aid = manager.assign_task("agent-1", "build-api", priority=3)
    manager.complete_assignment(aid, result={"status": "ok"})
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskAssignmentState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskAssignment:
    """Assigns tasks to agents based on availability and capability."""

    PREFIX = "ata-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskAssignmentState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Callable | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, task_name: str) -> str:
        self._state._seq += 1
        raw = f"{agent_id}-{task_name}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        completed = [
            k for k, v in self._state.entries.items() if v["status"] == "completed"
        ]
        for k in completed:
            del self._state.entries[k]
            if len(self._state.entries) <= self.MAX_ENTRIES:
                return

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Callable | None:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Callable | None) -> None:
        self._on_change = value

    def remove_callback(self, callback_id: str) -> bool:
        return self._callbacks.pop(callback_id, None) is not None

    # ------------------------------------------------------------------
    # Task assignment
    # ------------------------------------------------------------------

    def assign_task(
        self,
        agent_id: str,
        task_name: str,
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Assign a task to an agent.

        Args:
            agent_id: The agent to assign the task to.
            task_name: Name/identifier of the task.
            priority: Priority level (lower is higher priority).
            metadata: Optional metadata dict attached to the assignment.

        Returns:
            The generated assignment ID, or ``""`` on failure.
        """
        if not agent_id or not task_name:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        assignment_id = self._generate_id(agent_id, task_name)
        self._state.entries[assignment_id] = {
            "assignment_id": assignment_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "priority": priority,
            "metadata": dict(metadata) if metadata else {},
            "status": "assigned",
            "assigned_at": now,
            "completed_at": None,
            "created_at": now,
        }

        self._fire("assigned", self._state.entries[assignment_id])
        logger.debug("Task assigned: %s to %s (%s)", assignment_id, agent_id, task_name)
        return assignment_id

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def complete_assignment(self, assignment_id: str, result: Any = None) -> bool:
        """Mark an assignment as completed.

        Args:
            assignment_id: The ID returned by :meth:`assign_task`.
            result: Optional result data to store.

        Returns:
            ``True`` if completed, ``False`` if not found or already completed.
        """
        entry = self._state.entries.get(assignment_id)
        if entry is None or entry["status"] != "assigned":
            return False

        entry["status"] = "completed"
        entry["completed_at"] = time.time()
        entry["result"] = result

        self._fire("completed", entry)
        logger.debug("Assignment completed: %s", assignment_id)
        return True

    # ------------------------------------------------------------------
    # Reassignment
    # ------------------------------------------------------------------

    def reassign(self, assignment_id: str, new_agent_id: str) -> bool:
        """Reassign a task to a different agent.

        Args:
            assignment_id: The assignment to reassign.
            new_agent_id: The new agent to assign to.

        Returns:
            ``True`` if reassigned, ``False`` if not found, already completed,
            or *new_agent_id* is empty.
        """
        if not new_agent_id:
            return False

        entry = self._state.entries.get(assignment_id)
        if entry is None or entry["status"] != "assigned":
            return False

        old_agent = entry["agent_id"]
        entry["agent_id"] = new_agent_id
        entry["assigned_at"] = time.time()
        entry["reassigned"] = True

        self._fire("reassigned", {
            "assignment_id": assignment_id,
            "old_agent_id": old_agent,
            "new_agent_id": new_agent_id,
        })
        logger.debug(
            "Assignment reassigned: %s from %s to %s",
            assignment_id, old_agent, new_agent_id,
        )
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_assignment(self, assignment_id: str) -> dict:
        """Return assignment details or empty dict."""
        entry = self._state.entries.get(assignment_id)
        return dict(entry) if entry else {}

    def get_assignments(self, agent_id: str, status: str = "") -> list:
        """Return assignments for an agent, optionally filtered by status."""
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_pending_assignments(self, agent_id: str) -> list:
        """Return assignments with status='assigned' for the given agent."""
        return self.get_assignments(agent_id, status="assigned")

    def get_assignment_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of assignments matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            count += 1
        return count

    def get_agent_workload(self) -> dict:
        """Return {agent_id: count_of_assigned_tasks}."""
        workload: Dict[str, int] = {}
        for entry in self._state.entries.values():
            if entry["status"] == "assigned":
                aid = entry["agent_id"]
                workload[aid] = workload.get(aid, 0) + 1
        return workload

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        assigned = sum(
            1 for e in self._state.entries.values() if e["status"] == "assigned"
        )
        completed = sum(
            1 for e in self._state.entries.values() if e["status"] == "completed"
        )
        reassigned = sum(
            1 for e in self._state.entries.values() if e.get("reassigned")
        )
        return {
            "total_assignments": total,
            "assigned": assigned,
            "completed": completed,
            "reassigned": reassigned,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskAssignmentState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskAssignment reset")
