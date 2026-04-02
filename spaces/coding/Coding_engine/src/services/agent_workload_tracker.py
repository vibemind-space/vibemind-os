"""Agent workload tracker for monitoring agent task assignments and utilization.

Tracks active tasks, completed tasks, and utilization per agent.
Provides querying by agent and aggregate statistics.

Usage::

    tracker = AgentWorkloadTracker()
    task_id = tracker.assign_task("agent-1", "build_index")
    tracker.complete_task("agent-1", "build_index")
    util = tracker.get_utilization("agent-1", capacity=10)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentWorkloadTracker:
    """Tracks agent workload including active tasks, completed tasks, and utilization."""

    max_entries: int = 10000
    _tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_assigned: int = field(default=0)
    _total_completed: int = field(default=0)

    def _next_id(self, agent_id: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{agent_id}{self._seq}".encode()).hexdigest()[:12]
        return f"awt-{raw}"

    def _prune(self) -> None:
        while len(self._tasks) > self.max_entries:
            oldest_id = min(
                self._tasks,
                key=lambda tid: (
                    self._tasks[tid]["created_at"],
                    self._tasks[tid]["seq"],
                ),
            )
            del self._tasks[oldest_id]
            logger.debug("agent_workload_tracker.pruned", task_id=oldest_id)

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_workload_tracker.callback_error",
                    callback=name,
                    event=event,
                )

    # -- public API ----------------------------------------------------------

    def assign_task(self, agent_id: str, task_name: str) -> str:
        """Assign a task to an agent. Returns the task ID."""
        if not agent_id or not task_name:
            return ""
        task_id = self._next_id(agent_id)
        now = time.time()
        entry: Dict[str, Any] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "status": "active",
            "created_at": now,
            "completed_at": 0.0,
            "seq": self._seq,
        }
        self._tasks[task_id] = entry
        self._total_assigned += 1
        self._prune()
        logger.info(
            "agent_workload_tracker.task_assigned",
            task_id=task_id,
            agent_id=agent_id,
            task_name=task_name,
        )
        self._fire(
            "task_assigned",
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "task_name": task_name,
            },
        )
        return task_id

    def complete_task(self, agent_id: str, task_name: str) -> bool:
        """Mark the first matching active task as completed. Returns True if found."""
        for entry in self._tasks.values():
            if (
                entry["agent_id"] == agent_id
                and entry["task_name"] == task_name
                and entry["status"] == "active"
            ):
                entry["status"] = "completed"
                entry["completed_at"] = time.time()
                self._total_completed += 1
                logger.info(
                    "agent_workload_tracker.task_completed",
                    task_id=entry["task_id"],
                    agent_id=agent_id,
                    task_name=task_name,
                )
                self._fire(
                    "task_completed",
                    {
                        "task_id": entry["task_id"],
                        "agent_id": agent_id,
                        "task_name": task_name,
                    },
                )
                return True
        return False

    def get_active_tasks(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return a list of active task dicts for the given agent."""
        results = [
            dict(t)
            for t in self._tasks.values()
            if t["agent_id"] == agent_id and t["status"] == "active"
        ]
        results.sort(key=lambda t: (t["created_at"], t["seq"]))
        return results

    def get_utilization(self, agent_id: str, capacity: int = 10) -> float:
        """Return utilization ratio (0.0-1.0) for an agent given capacity."""
        if capacity <= 0:
            return 0.0
        active_count = sum(
            1
            for t in self._tasks.values()
            if t["agent_id"] == agent_id and t["status"] == "active"
        )
        return min(1.0, active_count / capacity)

    def get_completed_count(self, agent_id: str) -> int:
        """Return the number of completed tasks for a given agent."""
        return sum(
            1
            for t in self._tasks.values()
            if t["agent_id"] == agent_id and t["status"] == "completed"
        )

    def get_task_count(self) -> int:
        """Return the total number of stored tasks."""
        return len(self._tasks)

    def list_agents(self) -> List[str]:
        """Return a list of unique agent IDs that have tasks."""
        seen: set[str] = set()
        result: List[str] = []
        for t in self._tasks.values():
            aid = t["agent_id"]
            if aid not in seen:
                seen.add(aid)
                result.append(aid)
        return result

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback
        logger.debug("agent_workload_tracker.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("agent_workload_tracker.callback_removed", name=name)
            return True
        return False

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_tasks": len(self._tasks),
            "total_assigned": self._total_assigned,
            "total_completed": self._total_completed,
            "max_entries": self.max_entries,
            "agents": len(self.list_agents()),
            "active_tasks": sum(
                1 for t in self._tasks.values() if t["status"] == "active"
            ),
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._tasks.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_assigned = 0
        self._total_completed = 0
        logger.info("agent_workload_tracker.reset")
