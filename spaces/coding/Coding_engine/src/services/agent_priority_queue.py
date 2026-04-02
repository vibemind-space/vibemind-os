"""Agent Priority Queue - manages prioritized task queues for agents.

Provides per-agent priority queues backed by heapq. Higher priority number
means higher priority. Tasks with the same priority are dequeued in FIFO
order using an internal sequence counter as tiebreaker.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TaskEntry:
    """Single queued task."""

    task_id: str
    agent_id: str
    task_name: str
    priority: int
    payload: Any
    created_at: float
    seq: int = 0


class AgentPriorityQueue:
    """Priority-based task queue for autonomous agents.

    Each agent has its own logical queue. Tasks are ordered by priority
    (descending) then by insertion order (FIFO via ``seq``).
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._tasks: Dict[str, TaskEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"apq-{self._seq}-{id(self)}"
        return "apq-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if *name* already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Unregister a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest tasks when the store exceeds ``_max_entries``."""
        while len(self._tasks) > self._max_entries:
            oldest_id: Optional[str] = None
            oldest_seq: int = self._seq + 1
            for tid, entry in self._tasks.items():
                if entry.seq < oldest_seq:
                    oldest_seq = entry.seq
                    oldest_id = tid
            if oldest_id is not None:
                removed = self._tasks.pop(oldest_id)
                self._fire("task_pruned", {"task_id": oldest_id, "agent_id": removed.agent_id})

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        agent_id: str,
        task_name: str,
        priority: int = 0,
        payload: Any = None,
    ) -> str:
        """Add a task to the agent's queue. Returns the task ID (``apq-...``)."""
        task_id = self._generate_id()
        now = time.time()

        entry = TaskEntry(
            task_id=task_id,
            agent_id=agent_id,
            task_name=task_name,
            priority=priority,
            payload=payload,
            created_at=now,
            seq=self._seq,
        )

        self._tasks[task_id] = entry
        self._prune()

        self._fire("task_enqueued", {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "priority": priority,
        })
        return task_id

    def dequeue(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Remove and return the highest-priority task for *agent_id*.

        Among tasks with equal priority the one enqueued first is returned.
        Returns ``None`` when the agent's queue is empty.
        """
        best: Optional[TaskEntry] = None
        for entry in self._tasks.values():
            if entry.agent_id != agent_id:
                continue
            if best is None:
                best = entry
            elif entry.priority > best.priority:
                best = entry
            elif entry.priority == best.priority and entry.seq < best.seq:
                best = entry

        if best is None:
            return None

        self._tasks.pop(best.task_id)
        self._fire("task_dequeued", {"task_id": best.task_id, "agent_id": agent_id})
        return self._entry_to_dict(best)

    def peek(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the highest-priority task for *agent_id* without removing it."""
        best: Optional[TaskEntry] = None
        for entry in self._tasks.values():
            if entry.agent_id != agent_id:
                continue
            if best is None:
                best = entry
            elif entry.priority > best.priority:
                best = entry
            elif entry.priority == best.priority and entry.seq < best.seq:
                best = entry

        if best is None:
            return None
        return self._entry_to_dict(best)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Look up a task by its ID. Returns ``None`` if not found."""
        entry = self._tasks.get(task_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    def get_queue_size(self, agent_id: str) -> int:
        """Return the number of tasks queued for *agent_id*."""
        return sum(1 for e in self._tasks.values() if e.agent_id == agent_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task by ID. Returns ``True`` if the task existed."""
        entry = self._tasks.pop(task_id, None)
        if entry is None:
            return False
        self._fire("task_cancelled", {"task_id": task_id, "agent_id": entry.agent_id})
        return True

    def list_agents(self) -> List[str]:
        """Return a list of agent IDs that currently have queued tasks."""
        agents: set[str] = set()
        for entry in self._tasks.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def get_task_count(self) -> int:
        """Return the total number of tasks across all agents."""
        return len(self._tasks)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        agents = self.list_agents()
        per_agent = {a: self.get_queue_size(a) for a in agents}
        return {
            "total_tasks": self.get_task_count(),
            "agent_count": len(agents),
            "per_agent": per_agent,
            "max_entries": self._max_entries,
            "seq": self._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all internal state."""
        self._tasks.clear()
        self._callbacks.clear()
        self._seq = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: TaskEntry) -> Dict[str, Any]:
        return {
            "task_id": entry.task_id,
            "agent_id": entry.agent_id,
            "task_name": entry.task_name,
            "priority": entry.priority,
            "payload": entry.payload,
            "created_at": entry.created_at,
            "seq": entry.seq,
        }
