"""
Progress Tracker - Monitors and reports task execution progress.

Provides:
- Real-time progress tracking (percentage completion)
- Subtask status management
- Result aggregation
- Duration tracking
- Callback system for status updates

Example:
    tracker = ProgressTracker()
    tracker.start_task("task123", subtasks)

    for subtask in subtasks:
        tracker.start_subtask("task123", subtask.id)
        # ... execute ...
        tracker.complete_subtask("task123", subtask.id, success=True)

    print(f"Progress: {tracker.get_progress('task123'):.0%}")
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SubtaskStatus(Enum):
    """Status of a subtask."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubtaskProgress:
    """Progress information for a single subtask."""
    subtask_id: str
    description: str
    status: SubtaskStatus = SubtaskStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        """Get duration in seconds."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return None


@dataclass
class TaskProgress:
    """Progress information for a complete task."""
    task_id: str
    subtasks: Dict[str, SubtaskProgress] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    current_subtask: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.subtasks)

    @property
    def completed(self) -> int:
        return sum(
            1 for s in self.subtasks.values()
            if s.status in (SubtaskStatus.COMPLETED, SubtaskStatus.SKIPPED)
        )

    @property
    def failed(self) -> int:
        return sum(
            1 for s in self.subtasks.values()
            if s.status == SubtaskStatus.FAILED
        )

    @property
    def running(self) -> int:
        return sum(
            1 for s in self.subtasks.values()
            if s.status == SubtaskStatus.RUNNING
        )

    @property
    def progress(self) -> float:
        if self.total == 0:
            return 0.0
        return self.completed / self.total

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return None


class ProgressTracker:
    """
    Tracks progress of automation tasks and subtasks.

    Features:
    - Task-level and subtask-level progress tracking
    - Status callbacks for real-time updates
    - Result aggregation
    - History for completed tasks
    """

    def __init__(self, max_history: int = 100):
        """
        Initialize the progress tracker.

        Args:
            max_history: Maximum completed tasks to keep in history
        """
        self.max_history = max_history

        # Active tasks
        self._tasks: Dict[str, TaskProgress] = {}

        # Completed task history
        self._history: List[TaskProgress] = []

        # Status callbacks
        self._callbacks: Dict[str, List[Callable]] = {}

    def start_task(self, task_id: str, subtasks: List) -> None:
        """
        Start tracking a new task.

        Args:
            task_id: Unique task identifier
            subtasks: List of Subtask objects
        """
        subtask_progress = {}
        for subtask in subtasks:
            subtask_progress[subtask.id] = SubtaskProgress(
                subtask_id=subtask.id,
                description=subtask.description
            )

        self._tasks[task_id] = TaskProgress(
            task_id=task_id,
            subtasks=subtask_progress,
            started_at=time.time()
        )

        logger.info(f"Started tracking task {task_id} with {len(subtasks)} subtasks")
        self._notify(task_id, "task_started")

    def end_task(self, task_id: str) -> None:
        """
        End tracking for a task.

        Args:
            task_id: Task identifier
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.completed_at = time.time()

            # Move to history
            self._history.append(task)
            if len(self._history) > self.max_history:
                self._history.pop(0)

            del self._tasks[task_id]

            logger.info(
                f"Task {task_id} ended: {task.completed}/{task.total} completed, "
                f"duration: {task.duration:.1f}s"
            )
            self._notify(task_id, "task_ended")

        # Clean up callbacks
        self._callbacks.pop(task_id, None)

    def start_subtask(self, task_id: str, subtask_id: str) -> None:
        """
        Mark a subtask as started.

        Args:
            task_id: Task identifier
            subtask_id: Subtask identifier
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if subtask_id in task.subtasks:
                subtask = task.subtasks[subtask_id]
                subtask.status = SubtaskStatus.RUNNING
                subtask.started_at = time.time()
                task.current_subtask = subtask_id

                logger.debug(f"Subtask {subtask_id} started")
                self._notify(task_id, "subtask_started", subtask_id=subtask_id)

    def complete_subtask(
        self,
        task_id: str,
        subtask_id: str,
        success: bool = True,
        result: Optional[Dict] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Mark a subtask as completed.

        Args:
            task_id: Task identifier
            subtask_id: Subtask identifier
            success: Whether subtask succeeded
            result: Optional result data
            error: Optional error message
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if subtask_id in task.subtasks:
                subtask = task.subtasks[subtask_id]
                subtask.status = (
                    SubtaskStatus.COMPLETED if success else SubtaskStatus.FAILED
                )
                subtask.completed_at = time.time()
                subtask.result = result
                subtask.error = error

                if task.current_subtask == subtask_id:
                    task.current_subtask = None

                logger.debug(
                    f"Subtask {subtask_id} completed: "
                    f"success={success}, duration={subtask.duration:.1f}s"
                )
                self._notify(
                    task_id, "subtask_completed",
                    subtask_id=subtask_id, success=success
                )

    def skip_subtask(self, task_id: str, subtask_id: str, reason: str = None) -> None:
        """
        Mark a subtask as skipped.

        Args:
            task_id: Task identifier
            subtask_id: Subtask identifier
            reason: Optional skip reason
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if subtask_id in task.subtasks:
                subtask = task.subtasks[subtask_id]
                subtask.status = SubtaskStatus.SKIPPED
                subtask.error = reason

                logger.debug(f"Subtask {subtask_id} skipped: {reason}")
                self._notify(task_id, "subtask_skipped", subtask_id=subtask_id)

    def get_progress(self, task_id: str) -> float:
        """
        Get progress percentage for a task.

        Args:
            task_id: Task identifier

        Returns:
            Progress as float (0.0 to 1.0)
        """
        if task_id in self._tasks:
            return self._tasks[task_id].progress
        return 0.0

    def get_completed_count(self, task_id: str) -> int:
        """
        Get count of completed subtasks.

        Args:
            task_id: Task identifier

        Returns:
            Number of completed subtasks
        """
        if task_id in self._tasks:
            return self._tasks[task_id].completed
        return 0

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed status for a task.

        Args:
            task_id: Task identifier

        Returns:
            Status dictionary or None
        """
        if task_id not in self._tasks:
            # Check history
            for task in self._history:
                if task.task_id == task_id:
                    return self._format_status(task, from_history=True)
            return None

        task = self._tasks[task_id]
        return self._format_status(task)

    def _format_status(
        self,
        task: TaskProgress,
        from_history: bool = False
    ) -> Dict[str, Any]:
        """Format task progress as status dictionary."""
        subtask_statuses = []
        for subtask in task.subtasks.values():
            subtask_statuses.append({
                "id": subtask.subtask_id,
                "description": subtask.description,
                "status": subtask.status.value,
                "duration": subtask.duration,
                "error": subtask.error
            })

        return {
            "task_id": task.task_id,
            "progress": task.progress,
            "total_subtasks": task.total,
            "completed_subtasks": task.completed,
            "failed_subtasks": task.failed,
            "running_subtasks": task.running,
            "current_subtask": task.current_subtask,
            "duration": task.duration,
            "subtasks": subtask_statuses,
            "from_history": from_history
        }

    def get_current_subtask(self, task_id: str) -> Optional[str]:
        """
        Get currently running subtask description.

        Args:
            task_id: Task identifier

        Returns:
            Subtask description or None
        """
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.current_subtask and task.current_subtask in task.subtasks:
                return task.subtasks[task.current_subtask].description
        return None

    def subscribe(self, task_id: str, callback: Callable) -> None:
        """
        Subscribe to status updates for a task.

        Args:
            task_id: Task identifier
            callback: Callback function(task_id, event, **kwargs)
        """
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        self._callbacks[task_id].append(callback)

    def unsubscribe(self, task_id: str, callback: Callable) -> None:
        """
        Unsubscribe from status updates.

        Args:
            task_id: Task identifier
            callback: Callback to remove
        """
        if task_id in self._callbacks:
            try:
                self._callbacks[task_id].remove(callback)
            except ValueError:
                pass

    def _notify(self, task_id: str, event: str, **kwargs) -> None:
        """Notify subscribers of an event."""
        if task_id in self._callbacks:
            for callback in self._callbacks[task_id]:
                try:
                    callback(task_id, event, **kwargs)
                except Exception as e:
                    logger.warning(f"Callback failed: {e}")

    def get_all_active_tasks(self) -> List[Dict[str, Any]]:
        """Get status of all active tasks."""
        return [
            self._format_status(task)
            for task in self._tasks.values()
        ]

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent task history.

        Args:
            limit: Maximum tasks to return

        Returns:
            List of task status dictionaries
        """
        return [
            self._format_status(task, from_history=True)
            for task in self._history[-limit:]
        ]

    def clear_history(self) -> None:
        """Clear task history."""
        self._history.clear()
        logger.info("Task history cleared")
