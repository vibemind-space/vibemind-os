"""
Conversation Interface - Natural language API for the Automation Engine.

Provides a simple interface for conversational AI to:
- Submit automation tasks in natural language
- Track task progress with real-time updates
- Get results when tasks complete
- Cancel running tasks

Example:
    interface = ConversationInterface(engine)

    # Submit task
    task_id = await interface.submit_task(
        "Open Chrome, search for AI news, and summarize the headlines"
    )

    # Get updates
    while True:
        status = await interface.get_status(task_id)
        if status["state"] == "completed":
            result = await interface.get_result(task_id)
            break
        await asyncio.sleep(1)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class TaskSubmission:
    """A submitted task."""
    task_id: str
    goal: str
    context: Dict[str, Any]
    submitted_at: float
    status: str = "submitted"


class ConversationInterface:
    """
    Natural language interface for the Automation Engine.

    This is the primary interface for a conversational AI to interact
    with the MoireTracker automation system.
    """

    def __init__(self, automation_engine=None):
        """
        Initialize the interface.

        Args:
            automation_engine: AutomationEngine instance
        """
        self.engine = automation_engine

        # Pending task submissions
        self._pending: Dict[str, TaskSubmission] = {}

        # Running task futures
        self._running: Dict[str, asyncio.Task] = {}

        # Status update subscribers
        self._subscribers: Dict[str, List[Callable]] = {}

        # Results cache
        self._results: Dict[str, Any] = {}

    async def submit_task(
        self,
        natural_language_task: str,
        context: Optional[Dict[str, Any]] = None,
        wait: bool = False
    ) -> str:
        """
        Submit a task for automation.

        Args:
            natural_language_task: Task description in natural language
            context: Optional context (current app, user preferences, etc.)
            wait: If True, wait for completion and return result

        Returns:
            task_id for tracking (or result if wait=True)
        """
        import time

        task_id = str(uuid4())
        context = context or {}

        submission = TaskSubmission(
            task_id=task_id,
            goal=natural_language_task,
            context=context,
            submitted_at=time.time()
        )
        self._pending[task_id] = submission

        logger.info(f"Task submitted: {task_id} - {natural_language_task[:50]}...")

        if self.engine:
            # Start task execution
            async_task = asyncio.create_task(
                self._execute_task(task_id, natural_language_task, context)
            )
            self._running[task_id] = async_task

            if wait:
                # Wait for completion
                result = await async_task
                return result
        else:
            # No engine - task stays pending
            logger.warning("No automation engine configured")

        return task_id

    async def _execute_task(
        self,
        task_id: str,
        goal: str,
        context: Dict[str, Any]
    ):
        """Execute a task through the automation engine."""
        try:
            # Update status
            if task_id in self._pending:
                self._pending[task_id].status = "running"

            # Progress callback
            async def on_progress(status: Dict):
                await self._notify_subscribers(task_id, status)

            # Execute
            result = await self.engine.execute_complex_task(
                goal=goal,
                context=context,
                on_progress=on_progress
            )

            # Store result
            self._results[task_id] = result

            # Update status
            if task_id in self._pending:
                self._pending[task_id].status = "completed"

            return result

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self._results[task_id] = {
                "success": False,
                "error": str(e)
            }
            if task_id in self._pending:
                self._pending[task_id].status = "failed"
            raise

        finally:
            # Cleanup
            self._running.pop(task_id, None)

    async def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get current status of a task.

        Args:
            task_id: Task identifier

        Returns:
            Status dictionary with:
            - task_id: str
            - state: "submitted" | "running" | "completed" | "failed" | "cancelled"
            - progress: float (0.0 to 1.0)
            - current_subtask: str (description of current work)
            - subtasks_completed: int
            - subtasks_total: int
        """
        # Check pending
        if task_id in self._pending:
            submission = self._pending[task_id]

            # Get detailed status from engine
            if self.engine:
                engine_status = self.engine.get_task_status(task_id)
                if engine_status:
                    return {
                        "task_id": task_id,
                        "goal": submission.goal,
                        **engine_status
                    }

            return {
                "task_id": task_id,
                "goal": submission.goal,
                "state": submission.status,
                "progress": 0.0 if submission.status == "submitted" else None
            }

        # Check results
        if task_id in self._results:
            result = self._results[task_id]
            return {
                "task_id": task_id,
                "state": "completed" if result.get("success", False) else "failed",
                "progress": 1.0,
                "success": result.get("success", False)
            }

        return {
            "task_id": task_id,
            "state": "not_found",
            "error": "Task not found"
        }

    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get result of a completed task.

        Args:
            task_id: Task identifier

        Returns:
            Result dictionary or None if not completed
        """
        # Wait for running task to complete
        if task_id in self._running:
            try:
                await self._running[task_id]
            except Exception:
                pass

        return self._results.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task identifier

        Returns:
            True if cancelled, False otherwise
        """
        # Cancel in engine
        if self.engine:
            cancelled = await self.engine.cancel_task(task_id)
            if cancelled:
                if task_id in self._pending:
                    self._pending[task_id].status = "cancelled"
                return True

        # Cancel asyncio task
        if task_id in self._running:
            self._running[task_id].cancel()
            if task_id in self._pending:
                self._pending[task_id].status = "cancelled"
            return True

        return False

    def subscribe_to_updates(
        self,
        task_id: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """
        Subscribe to real-time status updates for a task.

        Args:
            task_id: Task identifier
            callback: Async callback function(status_dict)
        """
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(callback)

    def unsubscribe_from_updates(
        self,
        task_id: str,
        callback: Callable
    ) -> None:
        """
        Unsubscribe from task updates.

        Args:
            task_id: Task identifier
            callback: Callback to remove
        """
        if task_id in self._subscribers:
            try:
                self._subscribers[task_id].remove(callback)
            except ValueError:
                pass

    async def _notify_subscribers(
        self,
        task_id: str,
        status: Dict[str, Any]
    ) -> None:
        """Notify all subscribers of a status update."""
        if task_id in self._subscribers:
            for callback in self._subscribers[task_id]:
                try:
                    await callback(status)
                except Exception as e:
                    logger.warning(f"Subscriber callback failed: {e}")

    async def list_tasks(
        self,
        include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all tasks.

        Args:
            include_completed: Include completed tasks

        Returns:
            List of task status dictionaries
        """
        tasks = []

        # Pending/running tasks
        for task_id, submission in self._pending.items():
            tasks.append({
                "task_id": task_id,
                "goal": submission.goal,
                "state": submission.status,
                "submitted_at": submission.submitted_at
            })

        # Completed tasks
        if include_completed:
            for task_id, result in self._results.items():
                if task_id not in self._pending:
                    tasks.append({
                        "task_id": task_id,
                        "state": "completed" if result.get("success") else "failed",
                        "success": result.get("success", False)
                    })

        return tasks

    def clear_completed(self) -> int:
        """
        Clear completed tasks from memory.

        Returns:
            Number of tasks cleared
        """
        # Find completed tasks
        completed = [
            task_id for task_id, sub in self._pending.items()
            if sub.status in ("completed", "failed", "cancelled")
        ]

        # Clear
        for task_id in completed:
            self._pending.pop(task_id, None)
            self._subscribers.pop(task_id, None)

        count = len(completed)
        logger.info(f"Cleared {count} completed tasks")
        return count


# Convenience function for simple usage
async def quick_automate(
    goal: str,
    engine=None,
    on_progress: Callable = None
) -> Dict[str, Any]:
    """
    Quick automation helper for one-off tasks.

    Args:
        goal: Natural language task description
        engine: Optional AutomationEngine instance
        on_progress: Optional progress callback

    Returns:
        Automation result dictionary
    """
    if engine is None:
        from ..core.automation_engine import get_automation_engine
        engine = await get_automation_engine()

    interface = ConversationInterface(engine)

    if on_progress:
        task_id = await interface.submit_task(goal)
        interface.subscribe_to_updates(task_id, on_progress)

        # Wait for result
        while True:
            status = await interface.get_status(task_id)
            if status.get("state") in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        return await interface.get_result(task_id)
    else:
        # Wait for completion
        return await interface.submit_task(goal, wait=True)
