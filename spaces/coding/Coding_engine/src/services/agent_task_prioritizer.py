"""Agent Task Prioritizer -- manages task priorities for agents in an
emergent autonomous pipeline system.

Provides:
- Per-agent task priority management
- Priority-based task ranking and retrieval
- Callback-based change notifications
- Max-entries pruning to bound memory usage

Usage::

    prioritizer = AgentTaskPrioritizer()

    pid = prioritizer.set_priority("agent-1", "build-api", priority=8)
    top = prioritizer.get_top_tasks("agent-1", limit=3)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------------
# Internal state
# -------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the prioritizer."""

    priorities: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# -------------------------------------------------------------------
# AgentTaskPrioritizer
# -------------------------------------------------------------------

class AgentTaskPrioritizer:
    """Manages task priorities for agents in an emergent autonomous pipeline."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._state = _State()

    # ---------------------------------------------------------------
    # ID generation
    # ---------------------------------------------------------------

    def _next_id(self, agent_id: str, task_name: str) -> str:
        """Generate a collision-free priority ID with prefix ``atp-``."""
        self._state._seq += 1
        raw = f"{agent_id}-{task_name}-{time.time()}-{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"atp-{digest}"

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named callback invoked on state changes.

        Args:
            name: Unique name for this callback.
            callback: ``callback(action, detail)`` where *action* is a string
                and *detail* is a dict with event information.
        """
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name.

        Returns:
            ``True`` if removed, ``False`` if *name* was not registered.
        """
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Invoke all registered callbacks with *action* and *detail*."""
        detail_dict = dict(detail)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail_dict)
            except Exception:
                pass

    # ---------------------------------------------------------------
    # Pruning
    # ---------------------------------------------------------------

    def _maybe_prune(self) -> None:
        """Remove oldest entries when total count exceeds *max_entries*."""
        total = sum(
            len(tasks) for tasks in self._state.priorities.values()
        )
        if total <= self._max_entries:
            return

        all_entries: List[tuple] = []
        for agent_id, tasks in self._state.priorities.items():
            for task_name, entry in tasks.items():
                all_entries.append((entry["created_at"], agent_id, task_name))
        all_entries.sort()

        to_remove = total - self._max_entries
        for _, agent_id, task_name in all_entries[:to_remove]:
            del self._state.priorities[agent_id][task_name]
            if not self._state.priorities[agent_id]:
                del self._state.priorities[agent_id]

    # ---------------------------------------------------------------
    # Priority management
    # ---------------------------------------------------------------

    def set_priority(self, agent_id: str, task_name: str, priority: int = 5) -> str:
        """Set priority for a task.

        Args:
            agent_id: Identifier of the agent owning this task.
            task_name: Name of the task.
            priority: Priority value (higher means more important).

        Returns:
            The generated priority ID (``atp-...``).
        """
        priority_id = self._next_id(agent_id, task_name)

        if agent_id not in self._state.priorities:
            self._state.priorities[agent_id] = {}

        self._state.priorities[agent_id][task_name] = {
            "priority_id": priority_id,
            "task_name": task_name,
            "priority": priority,
            "created_at": time.time(),
        }

        self._maybe_prune()

        logger.info(
            "priority_set",
            priority_id=priority_id,
            agent_id=agent_id,
            task_name=task_name,
            priority=priority,
        )
        self._fire(
            "priority_set",
            priority_id=priority_id,
            agent_id=agent_id,
            task_name=task_name,
            priority=priority,
        )
        return priority_id

    def get_priority(self, agent_id: str, task_name: str) -> int:
        """Get priority for a task.

        Args:
            agent_id: Identifier of the agent.
            task_name: Name of the task.

        Returns:
            The priority value, or ``0`` if not found.
        """
        tasks = self._state.priorities.get(agent_id)
        if not tasks:
            return 0
        entry = tasks.get(task_name)
        if not entry:
            return 0
        return entry["priority"]

    def get_top_tasks(self, agent_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top N tasks sorted by priority (highest first).

        Args:
            agent_id: Identifier of the agent.
            limit: Maximum number of tasks to return.

        Returns:
            A list of dicts with ``task_name`` and ``priority`` keys.
        """
        tasks = self._state.priorities.get(agent_id)
        if not tasks:
            return []

        entries = [
            {"task_name": entry["task_name"], "priority": entry["priority"]}
            for entry in tasks.values()
        ]
        entries.sort(key=lambda d: d["priority"], reverse=True)
        return entries[:limit]

    def remove_priority(self, agent_id: str, task_name: str) -> bool:
        """Remove a task priority.

        Args:
            agent_id: Identifier of the agent.
            task_name: Name of the task.

        Returns:
            ``True`` if removed, ``False`` if not found.
        """
        tasks = self._state.priorities.get(agent_id)
        if not tasks or task_name not in tasks:
            return False

        del tasks[task_name]
        if not tasks:
            del self._state.priorities[agent_id]

        logger.info(
            "priority_removed",
            agent_id=agent_id,
            task_name=task_name,
        )
        self._fire(
            "priority_removed",
            agent_id=agent_id,
            task_name=task_name,
        )
        return True

    def get_task_count(self, agent_id: str = "") -> int:
        """Get count of prioritized tasks.

        Args:
            agent_id: If provided, count only tasks for this agent.
                If empty, count all tasks across all agents.

        Returns:
            The number of prioritized tasks.
        """
        if agent_id:
            tasks = self._state.priorities.get(agent_id)
            return len(tasks) if tasks else 0
        return sum(len(tasks) for tasks in self._state.priorities.values())

    # ---------------------------------------------------------------
    # Queries
    # ---------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return list of agent IDs that have prioritized tasks."""
        return list(self._state.priorities.keys())

    # ---------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return prioritizer statistics as a dict.

        Keys include ``total_agents``, ``total_tasks``, and
        ``callbacks_registered``.
        """
        total_tasks = sum(
            len(tasks) for tasks in self._state.priorities.values()
        )
        return {
            "total_agents": len(self._state.priorities),
            "total_tasks": total_tasks,
            "callbacks_registered": len(self._state.callbacks),
        }

    # ---------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------

    def reset(self) -> None:
        """Clear all prioritizer state, returning it to a pristine condition."""
        self._state.priorities.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("prioritizer_reset")
