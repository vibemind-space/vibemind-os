"""APScheduler worker backed by the durable Schedule execution repository."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable
from zoneinfo import ZoneInfo

from spaces.schedule.execution import ScheduleRepository

logger = logging.getLogger(__name__)


class ScheduleWorker:
    """Reload persisted jobs on boot and dispatch only to an explicit target."""

    def __init__(
        self,
        *,
        execution_target: Callable[[dict[str, Any]], Any] | None = None,
        scheduler_factory: Callable[[], Any] | None = None,
        trigger_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._execution_target = execution_target
        self._scheduler_factory = scheduler_factory
        self._trigger_factory = trigger_factory
        self._scheduler: Any = None
        self._repo = ScheduleRepository()
        self._running = False

    @staticmethod
    def _default_scheduler() -> Any:
        try:
            from apscheduler.jobstores.memory import MemoryJobStore
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError as exc:
            raise RuntimeError("APScheduler is required for live schedule execution") from exc
        return AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
            timezone=ZoneInfo("Europe/Berlin"),
        )

    @staticmethod
    def _trigger(task: dict[str, Any]) -> Any:
        try:
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.date import DateTrigger
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is required for trigger execution") from exc
        config = task["trigger_config"]
        timezone = ZoneInfo(task["timezone"])
        if task["trigger_type"] == "cron":
            return CronTrigger.from_crontab(config["cron"], timezone=timezone)
        if task["trigger_type"] == "date":
            return DateTrigger(run_date=config["run_date"], timezone=timezone)
        if task["trigger_type"] == "interval":
            return IntervalTrigger(seconds=config["interval_seconds"], timezone=timezone)
        raise RuntimeError(f"unsupported persisted trigger: {task['trigger_type']}")

    async def start(self) -> None:
        if self._execution_target is None:
            raise RuntimeError("schedule execution target is not configured")
        factory = self._scheduler_factory or self._default_scheduler
        self._scheduler = factory()
        self._scheduler.start()
        for task in self._repo.list("active"):
            self.add_job(task)
        self._running = True
        logger.info("ScheduleWorker loaded %d persisted active tasks", self.job_count)

    async def stop(self) -> None:
        if self._scheduler is not None:
            result = self._scheduler.shutdown(wait=False)
            if inspect.isawaitable(result):
                await result
        self._running = False

    def add_job(self, task: dict[str, Any]) -> None:
        if self._scheduler is None:
            raise RuntimeError("schedule worker is not started")
        self._scheduler.add_job(
            self._execute_task,
            trigger=(self._trigger_factory or self._trigger)(task),
            id=task["id"],
            args=[task["id"]],
            name=f"schedule:{task['title'][:40]}",
            replace_existing=True,
        )

    async def _execute_task(self, task_id: str) -> None:
        task = self._repo.get(task_id)
        if task is None or task["status"] != "active":
            return
        try:
            result = self._execution_target(task)  # type: ignore[misc]
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError("execution target did not return verified ok=true")
        except Exception:
            self._repo.update(task_id, {"status": "failed"})
            logger.exception("Scheduled task %s failed closed", task_id)
            raise

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def job_count(self) -> int:
        if self._scheduler is None or not hasattr(self._scheduler, "get_jobs"):
            return len(self._repo.list("active"))
        return len(self._scheduler.get_jobs())
