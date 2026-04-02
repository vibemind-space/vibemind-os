"""
Task Priority Queue — priority-based task scheduling with aging and deadlines.

Features:
- Priority-based ordering (higher priority = dequeued first)
- Task aging (priority increases over time)
- Deadline support with expiration
- Per-agent task assignment
- Task categories and filtering
- Batch dequeue
- Queue statistics and monitoring
"""

from __future__ import annotations

import heapq
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PriorityTask:
    """A task in the priority queue."""
    task_id: str
    name: str
    priority: int  # Higher = more important
    created_at: float
    deadline: float  # 0 = no deadline
    category: str
    assigned_to: str
    status: str  # "queued", "assigned", "completed", "expired", "cancelled"
    metadata: Dict[str, Any]
    tags: Set[str]
    age_rate: float  # Priority increase per second

    def effective_priority(self, now: float) -> float:
        """Priority with aging applied."""
        age = now - self.created_at
        return self.priority + age * self.age_rate


# ---------------------------------------------------------------------------
# Task Priority Queue
# ---------------------------------------------------------------------------

class TaskPriorityQueue:
    """Priority-based task queue with aging and deadlines."""

    def __init__(
        self,
        default_age_rate: float = 0.1,
        max_tasks: int = 10000,
    ):
        self._default_age_rate = default_age_rate
        self._max_tasks = max_tasks
        self._tasks: Dict[str, PriorityTask] = {}

        self._stats = {
            "total_enqueued": 0,
            "total_dequeued": 0,
            "total_completed": 0,
            "total_expired": 0,
            "total_cancelled": 0,
        }

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        name: str,
        priority: int = 50,
        category: str = "general",
        deadline_seconds: float = 0.0,
        age_rate: float = 0.0,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Add a task to the queue. Returns task_id."""
        tid = f"pq-{uuid.uuid4().hex[:8]}"
        now = time.time()

        self._tasks[tid] = PriorityTask(
            task_id=tid,
            name=name,
            priority=priority,
            created_at=now,
            deadline=now + deadline_seconds if deadline_seconds > 0 else 0.0,
            category=category,
            assigned_to="",
            status="queued",
            metadata=metadata or {},
            tags=tags or set(),
            age_rate=age_rate if age_rate > 0 else self._default_age_rate,
        )
        self._stats["total_enqueued"] += 1
        self._prune()
        return tid

    # ------------------------------------------------------------------
    # Dequeue
    # ------------------------------------------------------------------

    def dequeue(
        self,
        category: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        assign_to: str = "",
    ) -> Optional[Dict]:
        """Dequeue the highest-priority queued task. Returns task dict or None."""
        self._expire_deadlines()

        now = time.time()
        best = None
        best_prio = -float("inf")

        for t in self._tasks.values():
            if t.status != "queued":
                continue
            if category and t.category != category:
                continue
            if tags and not tags.issubset(t.tags):
                continue
            ep = t.effective_priority(now)
            if ep > best_prio:
                best_prio = ep
                best = t

        if best is None:
            return None

        best.status = "assigned"
        best.assigned_to = assign_to
        self._stats["total_dequeued"] += 1
        return self._task_to_dict(best)

    def dequeue_batch(
        self,
        count: int,
        category: Optional[str] = None,
        assign_to: str = "",
    ) -> List[Dict]:
        """Dequeue multiple tasks."""
        results = []
        for _ in range(count):
            task = self.dequeue(category=category, assign_to=assign_to)
            if task is None:
                break
            results.append(task)
        return results

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def complete(self, task_id: str) -> bool:
        """Mark a task as completed."""
        t = self._tasks.get(task_id)
        if not t or t.status not in ("queued", "assigned"):
            return False
        t.status = "completed"
        self._stats["total_completed"] += 1
        return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        t = self._tasks.get(task_id)
        if not t or t.status not in ("queued", "assigned"):
            return False
        t.status = "cancelled"
        self._stats["total_cancelled"] += 1
        return True

    def requeue(self, task_id: str, priority: Optional[int] = None) -> bool:
        """Put an assigned/cancelled task back in the queue."""
        t = self._tasks.get(task_id)
        if not t or t.status not in ("assigned", "cancelled"):
            return False
        t.status = "queued"
        t.assigned_to = ""
        if priority is not None:
            t.priority = priority
        return True

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task details."""
        t = self._tasks.get(task_id)
        if not t:
            return None
        return self._task_to_dict(t)

    def update_priority(self, task_id: str, priority: int) -> bool:
        """Update a task's priority."""
        t = self._tasks.get(task_id)
        if not t or t.status != "queued":
            return False
        t.priority = priority
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def peek(self, count: int = 1, category: Optional[str] = None) -> List[Dict]:
        """Peek at top tasks without dequeuing."""
        self._expire_deadlines()
        now = time.time()
        queued = []
        for t in self._tasks.values():
            if t.status != "queued":
                continue
            if category and t.category != category:
                continue
            queued.append((t.effective_priority(now), t))
        queued.sort(key=lambda x: x[0], reverse=True)
        return [self._task_to_dict(t) for _, t in queued[:count]]

    def list_tasks(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List tasks with filters."""
        results = []
        for t in self._tasks.values():
            if status and t.status != status:
                continue
            if category and t.category != category:
                continue
            if assigned_to and t.assigned_to != assigned_to:
                continue
            results.append(self._task_to_dict(t))
            if len(results) >= limit:
                break
        return results

    def queue_size(self, category: Optional[str] = None) -> int:
        """Get number of queued tasks."""
        count = 0
        for t in self._tasks.values():
            if t.status != "queued":
                continue
            if category and t.category != category:
                continue
            count += 1
        return count

    def list_categories(self) -> Dict[str, int]:
        """List categories with queued task counts."""
        counts: Dict[str, int] = {}
        for t in self._tasks.values():
            if t.status == "queued":
                counts[t.category] = counts.get(t.category, 0) + 1
        return dict(sorted(counts.items()))

    # ------------------------------------------------------------------
    # Expiration & cleanup
    # ------------------------------------------------------------------

    def _expire_deadlines(self) -> int:
        """Expire tasks past their deadline."""
        now = time.time()
        expired = 0
        for t in self._tasks.values():
            if t.status == "queued" and t.deadline > 0 and now > t.deadline:
                t.status = "expired"
                self._stats["total_expired"] += 1
                expired += 1
        return expired

    def cleanup(self) -> int:
        """Remove completed/expired/cancelled tasks. Returns count removed."""
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in ("completed", "expired", "cancelled")
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _task_to_dict(self, t: PriorityTask) -> Dict:
        now = time.time()
        return {
            "task_id": t.task_id,
            "name": t.name,
            "priority": t.priority,
            "effective_priority": round(t.effective_priority(now), 2),
            "created_at": t.created_at,
            "deadline": t.deadline,
            "category": t.category,
            "assigned_to": t.assigned_to,
            "status": t.status,
            "tags": sorted(t.tags),
            "metadata": t.metadata,
        }

    def _prune(self) -> None:
        if len(self._tasks) <= self._max_tasks:
            return
        done = sorted(
            [t for t in self._tasks.values()
             if t.status in ("completed", "expired", "cancelled")],
            key=lambda x: x.created_at,
        )
        to_remove = len(self._tasks) - self._max_tasks
        for t in done[:to_remove]:
            del self._tasks[t.task_id]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        queued = sum(1 for t in self._tasks.values() if t.status == "queued")
        assigned = sum(1 for t in self._tasks.values() if t.status == "assigned")
        return {
            **self._stats,
            "total_tasks": len(self._tasks),
            "queued": queued,
            "assigned": assigned,
        }

    def reset(self) -> None:
        self._tasks.clear()
        self._stats = {k: 0 for k in self._stats}
