"""Agent Task Progress Tracker -- records task start, progress updates, and completion.

Tracks per-agent task progress with status, step counts, and completion state.
Provides progress querying, agent listing, and filtered task retrieval.

Usage::

    tracker = AgentTaskTracker()

    # Start a task
    task_id = tracker.start_task("agent-1", "build_index", total_steps=5)

    # Update progress
    tracker.update_progress(task_id, current_step=3)

    # Complete task
    tracker.complete_task(task_id)

    # Query
    progress = tracker.get_progress(task_id)
    stats = tracker.get_stats()
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class AgentTaskTrackerState:
    """Primary state container for the tracker."""

    tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ======================================================================
# Agent Task Tracker
# ======================================================================

class AgentTaskTracker:
    """Tracks agent task progress with start, update, and completion.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._state = AgentTaskTrackerState()
        self._callbacks: Dict[str, Callable] = {}

        # cumulative counters
        self._total_started: int = 0
        self._total_completed: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_task_tracker.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, task_name: str) -> str:
        """Generate a unique task ID using SHA-256 + sequence counter."""
        self._state._seq += 1
        raw = f"{agent_id}:{task_name}:{self._state._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"att-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when capacity is reached."""
        if len(self._state.tasks) < self._max_entries:
            return

        all_sorted = sorted(
            self._state.tasks.items(),
            key=lambda pair: pair[1].get("created_at", 0),
        )

        to_remove = max(1, len(self._state.tasks) - self._max_entries + 1)
        victims = all_sorted[:to_remove]

        for key, _entry in victims:
            del self._state.tasks[key]
            self._total_evictions += 1

        logger.debug(
            "agent_task_tracker.pruned",
            removed=len(victims),
            remaining=len(self._state.tasks),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback.

        If *name* already exists the callback is silently replaced.
        """
        self._callbacks[name] = callback
        logger.debug("agent_task_tracker.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("agent_task_tracker.callback_removed", name=name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break tracker operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "agent_task_tracker.callback_error",
                    callback=cb_name,
                    action=action,
                )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def start_task(
        self,
        agent_id: str,
        task_name: str,
        total_steps: int = 1,
    ) -> str:
        """Start tracking a task.  Returns the task ID (att-xxx)."""
        task_id = self._generate_id(agent_id, task_name)
        task = {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "status": "in_progress",
            "current_step": 0,
            "total_steps": total_steps,
            "created_at": time.time(),
        }
        self._state.tasks[task_id] = task
        self._total_started += 1
        self._prune()

        self._fire("start_task", {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
        })
        logger.debug(
            "agent_task_tracker.start_task",
            task_id=task_id,
            agent_id=agent_id,
            task_name=task_name,
        )
        return task_id

    def update_progress(self, task_id: str, current_step: int) -> bool:
        """Update task progress.  Returns False if task not found."""
        task = self._state.tasks.get(task_id)
        if task is None:
            return False
        task["current_step"] = current_step

        self._fire("update_progress", {
            "task_id": task_id,
            "current_step": current_step,
        })
        logger.debug(
            "agent_task_tracker.update_progress",
            task_id=task_id,
            current_step=current_step,
        )
        return True

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed.  Returns False if task not found."""
        task = self._state.tasks.get(task_id)
        if task is None:
            return False
        task["status"] = "completed"
        task["current_step"] = task["total_steps"]
        self._total_completed += 1

        self._fire("complete_task", {
            "task_id": task_id,
            "agent_id": task["agent_id"],
        })
        logger.debug(
            "agent_task_tracker.complete_task",
            task_id=task_id,
        )
        return True

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a single task by ID.  Returns dict or None."""
        task = self._state.tasks.get(task_id)
        if task is None:
            return None
        return dict(task)

    def get_tasks(self, agent_id: str, status: str = "") -> List[Dict[str, Any]]:
        """Get tasks for an agent, optionally filtered by status."""
        results: List[Dict[str, Any]] = []
        for task in self._state.tasks.values():
            if task["agent_id"] != agent_id:
                continue
            if status and task["status"] != status:
                continue
            results.append(dict(task))
        return results

    def get_progress(self, task_id: str) -> float:
        """Return progress as 0.0-1.0 (current_step/total_steps).

        Returns 0.0 if task not found.
        """
        task = self._state.tasks.get(task_id)
        if task is None:
            return 0.0
        total = task["total_steps"]
        if total <= 0:
            return 0.0
        return task["current_step"] / total

    def get_task_count(self, agent_id: str = "") -> int:
        """Get total number of tasks, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.tasks)
        return sum(
            1 for t in self._state.tasks.values()
            if t["agent_id"] == agent_id
        )

    def list_agents(self) -> List[str]:
        """Get list of unique agent IDs."""
        agents: set[str] = set()
        for task in self._state.tasks.values():
            agents.add(task["agent_id"])
        return sorted(agents)

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        agent_count = len({t["agent_id"] for t in self._state.tasks.values()})
        return {
            "total_tasks": len(self._state.tasks),
            "total_started": self._total_started,
            "total_completed": self._total_completed,
            "total_evictions": self._total_evictions,
            "unique_agents": agent_count,
            "max_entries": self._max_entries,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.tasks.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._total_started = 0
        self._total_completed = 0
        self._total_evictions = 0
        logger.debug("agent_task_tracker.reset")
