"""Agent Task Scheduler -- schedule tasks to run at specific times or intervals
for agents.

Provides:
- Scheduled task creation with one-time or recurring execution
- Task lifecycle management (pending -> running -> completed/failed)
- Per-agent task querying
- Callback-based change notifications
- Max-entries pruning to bound memory usage

Usage::

    scheduler = AgentTaskScheduler()

    task_id = scheduler.schedule_task("agent-1", "backup-db", schedule_type="recurring", interval=3600)
    scheduler.mark_running(task_id)
    scheduler.mark_completed(task_id)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List, Optional


# -------------------------------------------------------------------
# Internal state
# -------------------------------------------------------------------

@dataclass
class _ScheduledTaskEntry:
    """A single scheduled task entry."""

    task_id: str
    agent_id: str
    task_name: str
    schedule_type: str  # "once" | "recurring"
    interval: float
    delay: float
    status: str  # "pending" | "running" | "completed" | "failed" | "cancelled"
    scheduled_at: float
    next_run_at: float
    started_at: float = 0.0
    completed_at: float = 0.0
    failure_reason: str = ""
    run_count: int = 0
    created_at: float = 0.0
    seq: int = 0


# -------------------------------------------------------------------
# AgentTaskScheduler
# -------------------------------------------------------------------

class AgentTaskScheduler:
    """Schedule tasks to run at specific times or intervals for agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._seq: int = 0

        self._entries: Dict[str, _ScheduledTaskEntry] = {}
        self._callbacks: Dict[str, Callable] = {}

        # Stats counters
        self._total_scheduled = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._total_pruned = 0

    # ---------------------------------------------------------------
    # ID generation
    # ---------------------------------------------------------------

    def _next_id(self, agent_id: str, task_name: str) -> str:
        """Generate a collision-free task ID with prefix ``ats-``."""
        self._seq += 1
        raw = f"{agent_id}-{task_name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ats-{digest}"

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback invoked on state changes.

        Args:
            name: Unique name for this callback.
            callback: ``callback(action, data)`` where *action* is a string
                like ``"scheduled"`` or ``"completed"`` and *data* is a dict.

        Returns:
            ``True`` if registered, ``False`` if *name* already exists.
        """
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name.

        Returns:
            ``True`` if removed, ``False`` if *name* was not registered.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *data*."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ---------------------------------------------------------------
    # Pruning
    # ---------------------------------------------------------------

    def _maybe_prune(self) -> None:
        """Remove oldest completed/failed/cancelled entries when *max_entries* is exceeded."""
        if len(self._entries) <= self._max_entries:
            return

        terminal = [
            (e.completed_at or e.created_at, tid)
            for tid, e in self._entries.items()
            if e.status in ("completed", "failed", "cancelled")
        ]
        terminal.sort()

        to_remove = len(self._entries) - self._max_entries
        for _, tid in terminal[:to_remove]:
            del self._entries[tid]
            self._total_pruned += 1

    # ---------------------------------------------------------------
    # Scheduling
    # ---------------------------------------------------------------

    def schedule_task(
        self,
        agent_id: str,
        task_name: str,
        schedule_type: str = "once",
        interval: float = 0.0,
        delay: float = 0.0,
    ) -> str:
        """Create a scheduled task entry.

        Args:
            agent_id: The agent that should execute this task.
            task_name: Human-readable name for the task.
            schedule_type: ``"once"`` for one-time execution or ``"recurring"``
                for repeated execution.
            interval: For recurring tasks, the interval in seconds between runs.
            delay: Delay in seconds before the first execution.

        Returns:
            The generated task ID, or ``""`` if validation fails.
        """
        if not agent_id or not task_name:
            return ""
        if schedule_type not in ("once", "recurring"):
            return ""
        if schedule_type == "recurring" and interval <= 0.0:
            return ""

        now = time.time()
        task_id = self._next_id(agent_id, task_name)

        entry = _ScheduledTaskEntry(
            task_id=task_id,
            agent_id=agent_id,
            task_name=task_name,
            schedule_type=schedule_type,
            interval=interval,
            delay=delay,
            status="pending",
            scheduled_at=now,
            next_run_at=now + delay,
            created_at=now,
            seq=self._seq,
        )

        self._entries[task_id] = entry
        self._total_scheduled += 1

        self._maybe_prune()

        self._fire("scheduled", asdict(entry))
        return task_id

    # ---------------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task by ID.

        Returns:
            A dict of all task fields, or ``None`` if not found.
        """
        entry = self._entries.get(task_id)
        if entry is None:
            return None
        return asdict(entry)

    def get_agent_tasks(self, agent_id: str) -> List[Dict]:
        """Get all tasks for a specific agent.

        Args:
            agent_id: The agent whose tasks to retrieve.

        Returns:
            A list of task dicts sorted by creation time (newest first).
        """
        results: List[Dict] = []
        for entry in self._entries.values():
            if entry.agent_id == agent_id:
                results.append(asdict(entry))
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def get_pending_tasks(self) -> List[Dict]:
        """Get all tasks with status ``"pending"``.

        Returns:
            A list of pending task dicts sorted by next_run_at (earliest first).
        """
        results: List[Dict] = []
        for entry in self._entries.values():
            if entry.status == "pending":
                results.append(asdict(entry))
        results.sort(key=lambda d: d["next_run_at"])
        return results

    def list_agents(self) -> List[str]:
        """List all agent IDs that have scheduled tasks.

        Returns:
            A sorted list of unique agent IDs.
        """
        agents = set()
        for entry in self._entries.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    # ---------------------------------------------------------------
    # Task lifecycle
    # ---------------------------------------------------------------

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Only tasks with status ``"pending"`` can be cancelled.

        Returns:
            ``True`` if the task was cancelled, ``False`` otherwise.
        """
        entry = self._entries.get(task_id)
        if entry is None or entry.status != "pending":
            return False

        self._seq += 1
        entry.status = "cancelled"
        entry.completed_at = time.time()
        entry.seq = self._seq
        self._total_cancelled += 1

        self._fire("cancelled", asdict(entry))
        return True

    def mark_running(self, task_id: str) -> bool:
        """Mark a task as ``"running"``.

        Only tasks with status ``"pending"`` can transition to running.

        Returns:
            ``True`` if the task was marked running, ``False`` otherwise.
        """
        entry = self._entries.get(task_id)
        if entry is None or entry.status != "pending":
            return False

        self._seq += 1
        entry.status = "running"
        entry.started_at = time.time()
        entry.run_count += 1
        entry.seq = self._seq

        self._fire("running", asdict(entry))
        return True

    def mark_completed(self, task_id: str) -> bool:
        """Mark a task as ``"completed"``.

        For recurring tasks, the status is reset to ``"pending"`` and
        ``next_run_at`` is advanced by the interval.

        Returns:
            ``True`` if the task was marked completed, ``False`` otherwise.
        """
        entry = self._entries.get(task_id)
        if entry is None or entry.status != "running":
            return False

        self._seq += 1
        now = time.time()
        self._total_completed += 1

        if entry.schedule_type == "recurring":
            entry.status = "pending"
            entry.next_run_at = now + entry.interval
            entry.started_at = 0.0
            entry.completed_at = now
            entry.seq = self._seq
            self._fire("recurring_reset", asdict(entry))
        else:
            entry.status = "completed"
            entry.completed_at = now
            entry.seq = self._seq
            self._fire("completed", asdict(entry))

        return True

    def mark_failed(self, task_id: str, reason: str = "") -> bool:
        """Mark a task as ``"failed"``.

        Args:
            task_id: The task to mark as failed.
            reason: Optional reason describing the failure.

        Returns:
            ``True`` if the task was marked failed, ``False`` otherwise.
        """
        entry = self._entries.get(task_id)
        if entry is None or entry.status != "running":
            return False

        self._seq += 1
        entry.status = "failed"
        entry.failure_reason = reason
        entry.completed_at = time.time()
        entry.seq = self._seq
        self._total_failed += 1

        self._fire("failed", asdict(entry))
        return True

    # ---------------------------------------------------------------
    # Count
    # ---------------------------------------------------------------

    def get_task_count(self) -> int:
        """Return the total number of tasks currently tracked."""
        return len(self._entries)

    # ---------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return scheduler statistics as a dict.

        Keys include ``total_scheduled``, ``total_completed``,
        ``total_failed``, ``total_cancelled``, ``total_pruned``,
        ``current_entries``, ``pending_count``, and ``running_count``.
        """
        pending = sum(1 for e in self._entries.values() if e.status == "pending")
        running = sum(1 for e in self._entries.values() if e.status == "running")

        return {
            "total_scheduled": self._total_scheduled,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_cancelled": self._total_cancelled,
            "total_pruned": self._total_pruned,
            "current_entries": len(self._entries),
            "pending_count": pending,
            "running_count": running,
        }

    # ---------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------

    def reset(self) -> None:
        """Clear all scheduler state, returning it to a pristine condition."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_scheduled = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._total_pruned = 0
