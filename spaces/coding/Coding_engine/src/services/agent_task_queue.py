"""
Agent Task Queue — Priority-based task scheduling and distribution for agents.

Provides:
- Priority queue with configurable priority levels (0=highest, 9=lowest)
- Per-agent task assignment with concurrency limits
- Task lifecycle tracking (queued -> assigned -> running -> completed/failed)
- Task dependencies (task B waits for task A to complete)
- Starvation prevention via aging (tasks gain priority over time)
- Dead-letter queue for repeatedly failed tasks
- Metrics and queue health monitoring

Usage::

    queue = AgentTaskQueue(event_bus=bus)

    # Submit tasks
    task_id = queue.submit("build_api", agent_type="backend", priority=3)

    # Assign to agent
    task = queue.assign_next("backend_agent_1")

    # Complete
    queue.complete(task_id, result={"files": ["api.py"]})
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class TaskPriority(int, Enum):
    """Task priority levels. Lower = higher priority."""
    CRITICAL = 0
    HIGH = 1
    ELEVATED = 2
    NORMAL = 3
    LOW = 5
    BACKGROUND = 7
    IDLE = 9


class TaskStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


@dataclass
class TaskItem:
    """A task in the queue."""
    task_id: str
    description: str
    agent_type: str  # Which type of agent can handle this
    priority: int = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.QUEUED

    # Timing
    created_at: float = field(default_factory=time.time)
    assigned_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    deadline: Optional[float] = None  # Optional deadline timestamp

    # Assignment
    assigned_to: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Dependencies
    depends_on: Set[str] = field(default_factory=set)  # Task IDs this depends on

    # Results
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def effective_priority(self) -> float:
        """Priority adjusted for aging. Older tasks get boosted."""
        age_bonus = min(self.age_seconds / 60.0, 3.0)  # Max 3 priority levels boost
        return self.priority - age_bonus

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED, TaskStatus.FAILED,
            TaskStatus.CANCELLED, TaskStatus.DEAD_LETTER,
        )

    @property
    def wait_time_ms(self) -> Optional[int]:
        if self.assigned_at:
            return int((self.assigned_at - self.created_at) * 1000)
        return None

    @property
    def execution_time_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return None

    @property
    def is_overdue(self) -> bool:
        return self.deadline is not None and time.time() > self.deadline

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "agent_type": self.agent_type,
            "priority": self.priority,
            "effective_priority": round(self.effective_priority, 2),
            "status": self.status.value,
            "age_seconds": round(self.age_seconds, 1),
            "assigned_to": self.assigned_to,
            "retry_count": self.retry_count,
            "depends_on": list(self.depends_on),
            "wait_time_ms": self.wait_time_ms,
            "execution_time_ms": self.execution_time_ms,
            "is_overdue": self.is_overdue,
            "metadata": self.metadata,
        }


class AgentTaskQueue:
    """
    Priority-based task queue with agent assignment and dependency tracking.
    """

    def __init__(
        self,
        event_bus=None,
        max_retries: int = 3,
        starvation_threshold: float = 300.0,  # 5 min
        dead_letter_after: int = 3,
    ):
        self.event_bus = event_bus
        self.max_retries = max_retries
        self.starvation_threshold = starvation_threshold
        self.dead_letter_after = dead_letter_after

        # All tasks by ID
        self._tasks: Dict[str, TaskItem] = {}

        # Active queue: tasks with QUEUED status, indexed by agent_type
        self._queues: Dict[str, List[str]] = {}  # agent_type -> [task_ids]

        # Agent assignments: agent_name -> set of assigned task_ids
        self._agent_tasks: Dict[str, Set[str]] = {}

        # Agent concurrency limits: agent_name -> max_concurrent
        self._agent_limits: Dict[str, int] = {}

        # Completed task IDs for dependency checking
        self._completed_tasks: Set[str] = set()

        # Dead letter queue
        self._dead_letter: List[str] = []

        # Callbacks
        self._on_complete_callbacks: Dict[str, List[Callable]] = {}

        self.logger = logger.bind(component="task_queue")

    # ------------------------------------------------------------------
    # Submit & Cancel
    # ------------------------------------------------------------------

    def submit(
        self,
        description: str,
        agent_type: str = "general",
        priority: int = TaskPriority.NORMAL,
        task_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        deadline: Optional[float] = None,
        max_retries: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Submit a new task to the queue."""
        task_id = task_id or f"task-{uuid.uuid4().hex[:8]}"

        task = TaskItem(
            task_id=task_id,
            description=description,
            agent_type=agent_type,
            priority=priority,
            depends_on=set(depends_on or []),
            deadline=deadline,
            max_retries=max_retries if max_retries is not None else self.max_retries,
            metadata=metadata or {},
        )

        self._tasks[task_id] = task

        # Add to agent_type queue
        if agent_type not in self._queues:
            self._queues[agent_type] = []
        self._queues[agent_type].append(task_id)

        self.logger.info(
            "task_submitted",
            task_id=task_id,
            agent_type=agent_type,
            priority=priority,
            depends_on=list(task.depends_on),
        )
        self._broadcast("task_submitted", task)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a queued or assigned task."""
        task = self._tasks.get(task_id)
        if not task or task.is_terminal:
            return False

        if task.status in (TaskStatus.QUEUED, TaskStatus.ASSIGNED):
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()

            # Remove from queue
            queue = self._queues.get(task.agent_type, [])
            if task_id in queue:
                queue.remove(task_id)

            # Remove from agent assignment
            if task.assigned_to:
                agent_tasks = self._agent_tasks.get(task.assigned_to, set())
                agent_tasks.discard(task_id)

            self.logger.info("task_cancelled", task_id=task_id)
            return True
        return False

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def set_agent_limit(self, agent_name: str, max_concurrent: int):
        """Set concurrency limit for an agent."""
        self._agent_limits[agent_name] = max_concurrent

    def assign_next(
        self,
        agent_name: str,
        agent_type: Optional[str] = None,
        preferred_types: Optional[List[str]] = None,
    ) -> Optional[TaskItem]:
        """
        Assign the highest-priority ready task to an agent.

        Args:
            agent_name: Name of the agent requesting work
            agent_type: Specific agent type to dequeue from
            preferred_types: List of agent types the agent can handle
        """
        # Check concurrency limit
        max_concurrent = self._agent_limits.get(agent_name, 10)
        current_tasks = self._agent_tasks.get(agent_name, set())
        active = sum(1 for tid in current_tasks if not self._tasks[tid].is_terminal)
        if active >= max_concurrent:
            return None

        # Determine which queues to check
        types_to_check = []
        if agent_type:
            types_to_check = [agent_type]
        elif preferred_types:
            types_to_check = preferred_types
        else:
            types_to_check = list(self._queues.keys())

        # Find best task across all applicable queues
        best_task = None
        best_priority = float('inf')

        for atype in types_to_check:
            queue = self._queues.get(atype, [])
            for tid in queue:
                task = self._tasks.get(tid)
                if not task or task.status != TaskStatus.QUEUED:
                    continue
                if not self._dependencies_met(task):
                    continue
                if task.effective_priority < best_priority:
                    best_priority = task.effective_priority
                    best_task = task

        if not best_task:
            return None

        # Assign
        best_task.status = TaskStatus.ASSIGNED
        best_task.assigned_to = agent_name
        best_task.assigned_at = time.time()

        # Remove from queue
        queue = self._queues.get(best_task.agent_type, [])
        if best_task.task_id in queue:
            queue.remove(best_task.task_id)

        # Track agent assignment
        if agent_name not in self._agent_tasks:
            self._agent_tasks[agent_name] = set()
        self._agent_tasks[agent_name].add(best_task.task_id)

        self.logger.info(
            "task_assigned",
            task_id=best_task.task_id,
            agent=agent_name,
            priority=best_task.priority,
            wait_time_ms=best_task.wait_time_ms,
        )
        self._broadcast("task_assigned", best_task)
        return best_task

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    def start(self, task_id: str):
        """Mark a task as started (running)."""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.ASSIGNED:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self._broadcast("task_started", task)

    def complete(self, task_id: str, result: Any = None):
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if not task or task.is_terminal:
            return

        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result
        self._completed_tasks.add(task_id)

        self.logger.info(
            "task_completed",
            task_id=task_id,
            agent=task.assigned_to,
            execution_time_ms=task.execution_time_ms,
        )
        self._broadcast("task_completed", task)

        # Fire completion callbacks
        for cb in self._on_complete_callbacks.get(task_id, []):
            try:
                cb(task)
            except Exception:
                pass

        # Check if this unblocks any queued tasks (for logging)
        self._check_unblocked(task_id)

    def fail(self, task_id: str, error: str = ""):
        """Mark a task as failed. May retry or send to dead letter."""
        task = self._tasks.get(task_id)
        if not task or task.is_terminal:
            return

        task.retry_count += 1
        task.error = error

        if task.retry_count >= task.max_retries:
            # Send to dead letter
            task.status = TaskStatus.DEAD_LETTER
            task.completed_at = time.time()
            self._dead_letter.append(task_id)
            self.logger.warning(
                "task_dead_lettered",
                task_id=task_id,
                retries=task.retry_count,
                error=error,
            )
            self._broadcast("task_dead_lettered", task)
        else:
            # Re-queue for retry
            task.status = TaskStatus.QUEUED
            task.assigned_to = None
            task.assigned_at = None
            task.started_at = None

            queue = self._queues.get(task.agent_type, [])
            queue.append(task_id)

            self.logger.info(
                "task_retrying",
                task_id=task_id,
                retry=task.retry_count,
                max_retries=task.max_retries,
            )
            self._broadcast("task_retrying", task)

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def _dependencies_met(self, task: TaskItem) -> bool:
        """Check if all dependencies for a task are completed."""
        if not task.depends_on:
            return True
        return task.depends_on.issubset(self._completed_tasks)

    def _check_unblocked(self, completed_task_id: str):
        """Check if completing this task unblocks others."""
        for tid, task in self._tasks.items():
            if task.status == TaskStatus.QUEUED and completed_task_id in task.depends_on:
                if self._dependencies_met(task):
                    self.logger.debug(
                        "task_unblocked",
                        task_id=tid,
                        unblocked_by=completed_task_id,
                    )

    def on_complete(self, task_id: str, callback: Callable):
        """Register a callback for when a task completes."""
        if task_id not in self._on_complete_callbacks:
            self._on_complete_callbacks[task_id] = []
        self._on_complete_callbacks[task_id].append(callback)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task details."""
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def get_queue_depth(self, agent_type: Optional[str] = None) -> int:
        """Get number of queued tasks."""
        if agent_type:
            queue = self._queues.get(agent_type, [])
            return sum(1 for tid in queue if self._tasks[tid].status == TaskStatus.QUEUED)
        return sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.QUEUED
        )

    def get_agent_tasks(self, agent_name: str) -> List[dict]:
        """Get all tasks assigned to an agent."""
        task_ids = self._agent_tasks.get(agent_name, set())
        return [
            self._tasks[tid].to_dict()
            for tid in task_ids
            if tid in self._tasks and not self._tasks[tid].is_terminal
        ]

    def get_pending_by_type(self) -> Dict[str, int]:
        """Get pending task count per agent type."""
        counts = {}
        for atype, queue in self._queues.items():
            counts[atype] = sum(
                1 for tid in queue if self._tasks[tid].status == TaskStatus.QUEUED
            )
        return counts

    def get_dead_letter_queue(self) -> List[dict]:
        """Get tasks in the dead letter queue."""
        return [
            self._tasks[tid].to_dict()
            for tid in self._dead_letter
            if tid in self._tasks
        ]

    def get_overdue_tasks(self) -> List[dict]:
        """Get tasks that have passed their deadline."""
        overdue = []
        for task in self._tasks.values():
            if not task.is_terminal and task.is_overdue:
                overdue.append(task.to_dict())
        return overdue

    def get_stale_tasks(self) -> List[dict]:
        """Get tasks waiting longer than starvation threshold."""
        stale = []
        for task in self._tasks.values():
            if task.status == TaskStatus.QUEUED and task.age_seconds > self.starvation_threshold:
                stale.append(task.to_dict())
        return stale

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get queue statistics."""
        status_counts = {}
        for task in self._tasks.values():
            s = task.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        # Average wait time for completed tasks
        wait_times = [
            t.wait_time_ms for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED and t.wait_time_ms is not None
        ]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0

        # Average execution time
        exec_times = [
            t.execution_time_ms for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED and t.execution_time_ms is not None
        ]
        avg_exec = sum(exec_times) / len(exec_times) if exec_times else 0

        return {
            "total_tasks": len(self._tasks),
            "status_counts": status_counts,
            "queue_depth": self.get_queue_depth(),
            "dead_letter_count": len(self._dead_letter),
            "active_agents": len(self._agent_tasks),
            "avg_wait_time_ms": round(avg_wait, 1),
            "avg_execution_time_ms": round(avg_exec, 1),
            "overdue_count": len(self.get_overdue_tasks()),
            "pending_by_type": self.get_pending_by_type(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _broadcast(self, action: str, task: TaskItem):
        """Broadcast task event via event bus."""
        if not self.event_bus:
            return
        try:
            from src.mind.event_bus import Event, EventType
            event = Event(
                type=EventType.PIPELINE_STARTED,  # Generic event type
                source="task_queue",
                data={
                    "action": action,
                    "task": task.to_dict(),
                },
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.event_bus.publish(event))
            except RuntimeError:
                pass
        except Exception:
            pass

    def clear_completed(self, older_than_seconds: float = 3600.0):
        """Remove completed tasks older than threshold."""
        cutoff = time.time() - older_than_seconds
        to_remove = []
        for tid, task in self._tasks.items():
            if task.is_terminal and task.completed_at and task.completed_at < cutoff:
                to_remove.append(tid)

        for tid in to_remove:
            del self._tasks[tid]
            self._completed_tasks.discard(tid)

        return len(to_remove)

    def reset(self):
        """Clear all queue state."""
        self._tasks.clear()
        self._queues.clear()
        self._agent_tasks.clear()
        self._completed_tasks.clear()
        self._dead_letter.clear()
        self._on_complete_callbacks.clear()
