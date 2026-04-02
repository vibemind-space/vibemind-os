"""Agent priority scheduler - schedule tasks with priority-based ordering."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ScheduledTask:
    """A scheduled task with priority."""
    task_id: str = ""
    name: str = ""
    priority: int = 0
    agent: str = ""
    status: str = "pending"
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    deadline: float = 0.0
    result: str = ""


class AgentPriorityScheduler:
    """Schedule and dispatch tasks with priority-based ordering."""

    STATUSES = ("pending", "running", "completed", "failed", "cancelled", "blocked")
    PRIORITIES = range(0, 11)  # 0 = lowest, 10 = highest

    def __init__(self, max_tasks: int = 50000, max_running: int = 100):
        self._max_tasks = max(1, max_tasks)
        self._max_running = max(1, max_running)
        self._tasks: Dict[str, ScheduledTask] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_scheduled": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
        }

    # --- Task Management ---

    def schedule(
        self,
        name: str,
        priority: int = 5,
        agent: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        dependencies: Optional[List[str]] = None,
        deadline: float = 0.0,
    ) -> str:
        """Schedule a task. Returns task_id or empty on failure."""
        if not name:
            return ""
        if priority < 0 or priority > 10:
            return ""
        if len(self._tasks) >= self._max_tasks:
            return ""

        # Check dependencies exist
        deps = list(dependencies or [])
        for d in deps:
            if d not in self._tasks:
                return ""

        tid = f"sched-{uuid.uuid4().hex[:12]}"
        now = time.time()

        status = "pending"
        # If any dependency is not completed, mark as blocked
        for d in deps:
            if self._tasks[d].status != "completed":
                status = "blocked"
                break

        self._tasks[tid] = ScheduledTask(
            task_id=tid,
            name=name,
            priority=priority,
            agent=agent,
            status=status,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            dependencies=deps,
            created_at=now,
            deadline=deadline,
        )
        self._stats["total_scheduled"] += 1
        self._fire("task_scheduled", {"task_id": tid, "priority": priority})
        return tid

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a task by ID."""
        t = self._tasks.get(task_id)
        if not t:
            return None
        self._check_deadline(t)
        return self._task_dict(t)

    def remove_task(self, task_id: str) -> bool:
        """Remove a task."""
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        return True

    def start_task(self, task_id: str, agent: str = "") -> bool:
        """Start a pending/blocked task."""
        t = self._tasks.get(task_id)
        if not t:
            return False
        if t.status not in ("pending",):
            return False
        # Check running limit
        running = sum(1 for x in self._tasks.values() if x.status == "running")
        if running >= self._max_running:
            return False
        t.status = "running"
        t.started_at = time.time()
        if agent:
            t.agent = agent
        self._fire("task_started", {"task_id": task_id, "agent": t.agent})
        return True

    def complete_task(self, task_id: str, result: str = "") -> bool:
        """Complete a running task."""
        t = self._tasks.get(task_id)
        if not t or t.status != "running":
            return False
        t.status = "completed"
        t.completed_at = time.time()
        t.result = result
        self._stats["total_completed"] += 1
        self._fire("task_completed", {"task_id": task_id})
        # Unblock dependents
        self._unblock_dependents(task_id)
        return True

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        """Fail a running task."""
        t = self._tasks.get(task_id)
        if not t or t.status != "running":
            return False
        t.status = "failed"
        t.completed_at = time.time()
        t.result = reason
        self._stats["total_failed"] += 1
        self._fire("task_failed", {"task_id": task_id, "reason": reason})
        return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or blocked task."""
        t = self._tasks.get(task_id)
        if not t or t.status not in ("pending", "blocked"):
            return False
        t.status = "cancelled"
        t.completed_at = time.time()
        self._stats["total_cancelled"] += 1
        self._fire("task_cancelled", {"task_id": task_id})
        return True

    def set_priority(self, task_id: str, priority: int) -> bool:
        """Change task priority."""
        t = self._tasks.get(task_id)
        if not t:
            return False
        if priority < 0 or priority > 10:
            return False
        t.priority = priority
        return True

    # --- Queue Operations ---

    def get_next(self, agent: str = "", tag: str = "") -> Optional[Dict]:
        """Get highest priority pending task."""
        candidates = []
        for t in self._tasks.values():
            if t.status != "pending":
                continue
            if agent and t.agent and t.agent != agent:
                continue
            if tag and tag not in t.tags:
                continue
            self._check_deadline(t)
            if t.status != "pending":
                continue
            candidates.append(t)
        if not candidates:
            return None
        # Sort by priority (desc), then creation time (asc)
        candidates.sort(key=lambda x: (-x.priority, x.created_at))
        return self._task_dict(candidates[0])

    def get_queue(self, agent: str = "", tag: str = "", limit: int = 50) -> List[Dict]:
        """Get pending tasks ordered by priority."""
        results = []
        for t in self._tasks.values():
            if t.status != "pending":
                continue
            if agent and t.agent and t.agent != agent:
                continue
            if tag and tag not in t.tags:
                continue
            results.append(t)
        results.sort(key=lambda x: (-x.priority, x.created_at))
        return [self._task_dict(t) for t in results[:limit]]

    def list_tasks(
        self,
        status: str = "",
        agent: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """List tasks with filters."""
        results = []
        for t in self._tasks.values():
            if status and t.status != status:
                continue
            if agent and t.agent != agent:
                continue
            if tag and tag not in t.tags:
                continue
            results.append(self._task_dict(t))
        results.sort(key=lambda x: (-x["priority"], x["created_at"]))
        return results[:limit]

    def get_running_tasks(self) -> List[Dict]:
        """Get all running tasks."""
        return [self._task_dict(t) for t in self._tasks.values() if t.status == "running"]

    def get_blocked_tasks(self) -> List[Dict]:
        """Get all blocked tasks."""
        return [self._task_dict(t) for t in self._tasks.values() if t.status == "blocked"]

    def get_overdue_tasks(self) -> List[Dict]:
        """Get tasks past their deadline."""
        now = time.time()
        overdue = []
        for t in self._tasks.values():
            if t.deadline > 0 and now > t.deadline and t.status in ("pending", "running", "blocked"):
                overdue.append(self._task_dict(t))
        return overdue

    # --- Analytics ---

    def get_agent_tasks(self, agent: str) -> Dict:
        """Get task summary for an agent."""
        tasks = [t for t in self._tasks.values() if t.agent == agent]
        if not tasks:
            return {}
        by_status: Dict[str, int] = {}
        for t in tasks:
            by_status[t.status] = by_status.get(t.status, 0) + 1
        return {
            "agent": agent,
            "total": len(tasks),
            "by_status": by_status,
        }

    def get_priority_distribution(self) -> Dict[int, int]:
        """Get task count by priority level."""
        dist: Dict[int, int] = {}
        for t in self._tasks.values():
            dist[t.priority] = dist.get(t.priority, 0) + 1
        return dist

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict:
        """Get scheduler stats."""
        by_status: Dict[str, int] = {}
        for t in self._tasks.values():
            by_status[t.status] = by_status.get(t.status, 0) + 1
        return {
            **self._stats,
            "total_tasks": len(self._tasks),
            "by_status": by_status,
        }

    def reset(self) -> None:
        """Reset everything."""
        self._tasks.clear()
        self._callbacks.clear()
        self._stats = {
            "total_scheduled": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
        }

    # --- Internal ---

    def _task_dict(self, t: ScheduledTask) -> Dict:
        """Convert task to dict."""
        return {
            "task_id": t.task_id,
            "name": t.name,
            "priority": t.priority,
            "agent": t.agent,
            "status": t.status,
            "tags": list(t.tags),
            "dependencies": list(t.dependencies),
            "created_at": t.created_at,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "deadline": t.deadline,
            "result": t.result,
        }

    def _unblock_dependents(self, completed_id: str) -> None:
        """Unblock tasks whose dependencies are now all completed."""
        for t in self._tasks.values():
            if t.status != "blocked":
                continue
            if completed_id not in t.dependencies:
                continue
            all_done = all(
                self._tasks.get(d) and self._tasks[d].status == "completed"
                for d in t.dependencies
            )
            if all_done:
                t.status = "pending"
                self._fire("task_unblocked", {"task_id": t.task_id})

    def _check_deadline(self, t: ScheduledTask) -> None:
        """Check if task has passed deadline."""
        if t.deadline > 0 and time.time() > t.deadline:
            if t.status in ("pending", "blocked"):
                self._fire("task_overdue", {"task_id": t.task_id})

    def _fire(self, action: str, data: Dict) -> None:
        """Fire callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
