"""
Schedule Worker — APScheduler-based task execution engine.

Manages AsyncIOScheduler with MemoryJobStore.
On startup, loads active tasks from SQLite and registers them as APScheduler jobs.

Execution modes:
    simple  → IntentOrchestrator.process_intent_sync(action_text)
    complex → Minibook start_collaboration(action_text)

Delivery:
    1. inject_system_message() → Rachel speaks immediately
    2. NotificationQueue fallback → Rachel picks up on next input
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from data import (
    ScheduledTask,
    ScheduledTaskRepository,
    ScheduleStatus,
    TriggerType,
    ExecutionMode,
)
from spaces.schedule.config import get_config

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    __logger.debug("[ScheduleWorker] %s", msg)


class ScheduleWorker:
    """
    APScheduler-backed task execution engine.

    - Uses AsyncIOScheduler with MemoryJobStore (fast, in-process)
    - VibeMind persists tasks in SQLite (survives restarts)
    - On startup: load active tasks from DB → register as APScheduler jobs
    """

    def __init__(
        self,
        realtime_session_getter: Optional[Callable] = None,
        orchestrator_getter: Optional[Callable] = None,
    ):
        """
        Args:
            realtime_session_getter: Callable returning the active OpenAIRealtimeVoiceSession
            orchestrator_getter: Callable returning the IntentOrchestrator instance
        """
        self._get_session = realtime_session_getter
        self._get_orchestrator = orchestrator_getter
        self._scheduler = None
        self._running = False
        self._repo = ScheduledTaskRepository()
        self._config = get_config()

    async def start(self):
        """Initialize APScheduler and load active tasks from DB."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.jobstores.memory import MemoryJobStore
        except ImportError:
            _logger.error(
                "APScheduler not installed. Run: pip install APScheduler>=3.10.0"
            )
            _debug_print("ERROR: APScheduler not installed!")
            return

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,
                "max_instances": self._config.max_concurrent_jobs,
                "misfire_grace_time": self._config.misfire_grace_time,
            },
        )

        self._scheduler.start()
        self._running = True
        _debug_print("APScheduler started")

        # Load active tasks from DB
        active_tasks = self._repo.get_active()
        loaded = 0
        for task in active_tasks:
            try:
                self.add_job(task)
                loaded += 1
            except Exception as e:
                _logger.warning(f"Failed to register job {task.id}: {e}")

        _debug_print(f"Loaded {loaded}/{len(active_tasks)} active tasks from DB")
        _logger.info(f"ScheduleWorker started: {loaded} active tasks loaded")

    async def stop(self):
        """Shut down the scheduler gracefully."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._running = False
            _debug_print("APScheduler stopped")

    def add_job(self, task: ScheduledTask):
        """
        Register a ScheduledTask as an APScheduler job.

        Args:
            task: The task to register
        """
        if not self._scheduler:
            _logger.warning("Scheduler not started — cannot add job")
            return

        trigger = self._build_trigger(task)
        if trigger is None:
            _logger.warning(f"Could not build trigger for task {task.id}")
            return

        # Remove existing job if re-registering
        try:
            self._scheduler.remove_job(task.id)
        except Exception:
            pass  # Job didn't exist — fine

        self._scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=task.id,
            args=[task.id],
            name=f"schedule:{task.title[:40]}",
            replace_existing=True,
        )
        _debug_print(f"Job registered: {task.id} '{task.title}' ({task.trigger_type})")

    def remove_job(self, task_id: str):
        """Remove a job from APScheduler."""
        if not self._scheduler:
            return
        try:
            self._scheduler.remove_job(task_id)
            _debug_print(f"Job removed: {task_id}")
        except Exception as e:
            _logger.debug(f"Job {task_id} not found in scheduler: {e}")

    def _build_trigger(self, task: ScheduledTask):
        """Build an APScheduler trigger from task config."""
        try:
            from apscheduler.triggers.date import DateTrigger
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            return None

        config = task.trigger_config
        tz = task.timezone

        if task.trigger_type == TriggerType.DATE:
            run_date = config.get("run_date")
            if run_date:
                return DateTrigger(run_date=run_date, timezone=tz)

        elif task.trigger_type == TriggerType.CRON:
            return CronTrigger(
                day_of_week=config.get("day_of_week"),
                hour=config.get("hour"),
                minute=config.get("minute", 0),
                timezone=tz,
            )

        elif task.trigger_type == TriggerType.INTERVAL:
            return IntervalTrigger(
                weeks=config.get("weeks", 0),
                days=config.get("days", 0),
                hours=config.get("hours", 0),
                minutes=config.get("minutes", 0),
                seconds=config.get("seconds", 0),
                timezone=tz,
            )

        return None

    # -----------------------------------------------------------------
    # Task Execution
    # -----------------------------------------------------------------

    async def _execute_task(self, task_id: str):
        """
        APScheduler calls this when a job fires.

        1. Load task from DB
        2. Dispatch: simple → process_intent_sync(), complex → start_collaboration()
        3. Update DB: run_count, last_run_at, status
        4. Deliver result: inject_system_message() → NotificationQueue fallback
        """
        _debug_print(f"Task firing: {task_id}")
        task = self._repo.get(task_id)
        if not task:
            _logger.error(f"Task {task_id} not found in DB — skipping")
            return

        if task.status != ScheduleStatus.ACTIVE:
            _logger.info(f"Task {task_id} is not active ({task.status}) — skipping")
            return

        result_text = None
        error_text = None

        try:
            if task.execution_mode == ExecutionMode.COMPLEX:
                result_text = await self._execute_complex(task)
            else:
                result_text = await self._execute_simple(task)
        except Exception as e:
            error_text = str(e)
            _logger.error(f"Task {task_id} execution failed: {e}")
            _debug_print(f"Task {task_id} FAILED: {e}")

        # Update DB
        self._repo.update_after_run(
            task_id,
            last_result=result_text,
            last_error=error_text,
            new_status=ScheduleStatus.FAILED if error_text else None,
        )

        # Deliver result
        if result_text:
            await self._deliver_result(task, result_text)
        elif error_text:
            await self._deliver_result(
                task,
                f"Geplante Aufgabe '{task.title}' ist fehlgeschlagen: {error_text}"
            )

        _debug_print(f"Task {task_id} done (result={bool(result_text)}, error={bool(error_text)})")

    async def _execute_simple(self, task: ScheduledTask) -> str:
        """
        Option B: Direct execution via IntentOrchestrator.

        Runs task.action_text through the same pipeline as voice input.
        """
        _debug_print(f"Simple execution: '{task.action_text}'")

        # Special case: pure reminder (no action to execute)
        if self._is_pure_reminder(task.action_text):
            return f"Erinnerung: {task.title}"

        # Route through IntentOrchestrator
        if self._get_orchestrator:
            orchestrator = self._get_orchestrator()
            if orchestrator:
                try:
                    result = orchestrator.process_intent_sync(task.action_text)
                    if hasattr(result, "response_hint") and result.response_hint:
                        return f"Geplante Aufgabe '{task.title}': {result.response_hint}"
                    elif hasattr(result, "message") and result.message:
                        return f"Geplante Aufgabe '{task.title}': {result.message}"
                except Exception as e:
                    _logger.error(f"IntentOrchestrator failed for task {task.id}: {e}")
                    return f"Erinnerung: {task.title}"

        # Fallback: just announce
        return f"Erinnerung: {task.title}"

    async def _execute_complex(self, task: ScheduledTask) -> Optional[str]:
        """
        Option A: Minibook collaboration.

        Starts a multi-space collaboration via Minibook.
        Results are delivered asynchronously by DiscussionPollerWorker.
        """
        _debug_print(f"Complex execution via Minibook: '{task.action_text}'")

        try:
            from spaces.minibook.tools.collaboration_tools import start_collaboration
            result = start_collaboration(task=task.action_text, goal=task.title)
            if result.get("success"):
                return (
                    f"Kollaboration fuer '{task.title}' gestartet. "
                    f"Die Ergebnisse kommen, sobald alle Spaces geantwortet haben."
                )
            else:
                return f"Konnte Kollaboration fuer '{task.title}' nicht starten: {result.get('message', '?')}"
        except ImportError:
            _logger.error("Minibook not available for complex execution")
            # Fallback to simple
            return await self._execute_simple(task)
        except Exception as e:
            _logger.error(f"Complex execution failed for {task.id}: {e}")
            return f"Fehler bei '{task.title}': {e}"

    def _is_pure_reminder(self, text: str) -> bool:
        """Check if action text is a pure reminder (no executable action)."""
        if not text or len(text.strip()) < 3:
            return True
        lower = text.lower().strip()
        # Common reminder patterns without actions
        reminder_patterns = [
            "termin", "meeting", "anruf", "einkauf",
            "arzt", "zahnarzt", "medikament",
        ]
        # If it's just a few words and matches a reminder pattern, it's pure
        if len(lower.split()) <= 4:
            for pattern in reminder_patterns:
                if pattern in lower:
                    return True
        return False

    # -----------------------------------------------------------------
    # Result Delivery
    # -----------------------------------------------------------------

    async def _deliver_result(self, task: ScheduledTask, text: str):
        """
        Deliver execution result via best available method.

        1. inject_system_message() → Rachel speaks immediately
        2. NotificationQueue → Rachel picks up on next input
        """
        # Try direct voice injection
        if self._get_session:
            session = self._get_session()
            if session and hasattr(session, "inject_system_message"):
                try:
                    await session.inject_system_message(text)
                    _debug_print(f"Result injected via voice: {text[:60]}...")
                    return
                except Exception as e:
                    _logger.warning(f"Voice injection failed: {e}")

        # Fallback: NotificationQueue
        try:
            from swarm.orchestrator.notification_queue import get_notification_queue
            queue = get_notification_queue()
            queue.add_notification(
                job_id=f"schedule-{task.id}",
                event_type="schedule.fired",
                result=text,
                metadata={
                    "task_id": task.id,
                    "title": task.title,
                    "execution_mode": task.execution_mode,
                },
            )
            _debug_print(f"Result queued in NotificationQueue: {text[:60]}...")
        except Exception as e:
            _logger.error(f"Could not deliver schedule result: {e}")

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def job_count(self) -> int:
        if self._scheduler:
            return len(self._scheduler.get_jobs())
        return 0
