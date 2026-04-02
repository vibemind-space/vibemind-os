"""
Pipeline Scheduler — cron-like recurring pipeline execution.

Features:
- Schedule definitions with cron-like expressions (simplified)
- One-time and recurring schedules
- Enable/disable schedules without deleting
- Trigger history tracking
- Next-run calculation
- Manual trigger support
- Schedule tags and metadata
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class ScheduleType(str, Enum):
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class TriggerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScheduleDefinition:
    """Defines when and what to run."""
    schedule_id: str
    name: str
    schedule_type: ScheduleType
    action: str  # action identifier (e.g., "build_all", "run_tests")
    # Interval config
    interval_seconds: float = 0.0
    # Cron config (simplified: minute, hour, day_of_week)
    cron_minute: int = -1  # 0-59 or -1 for "any"
    cron_hour: int = -1     # 0-23 or -1 for "any"
    cron_day: int = -1      # 0-6 (Mon-Sun) or -1 for "any"
    # One-time config
    run_at: float = 0.0  # Unix timestamp for one-time
    # Common
    enabled: bool = True
    context: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: float = 0.0
    last_triggered: float = 0.0
    trigger_count: int = 0
    max_triggers: int = 0  # 0 = unlimited


@dataclass
class TriggerRecord:
    """Record of a schedule trigger."""
    trigger_id: str
    schedule_id: str
    schedule_name: str
    action: str
    status: TriggerStatus
    triggered_at: float
    completed_at: float = 0.0
    result: Any = None
    error: str = ""


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class PipelineScheduler:
    """Manages scheduled pipeline executions."""

    def __init__(self, max_history: int = 500):
        self._max_history = max_history

        # Schedules: schedule_id → ScheduleDefinition
        self._schedules: Dict[str, ScheduleDefinition] = {}

        # Name index for quick lookup
        self._by_name: Dict[str, str] = {}  # name → schedule_id

        # Trigger history
        self._history: List[TriggerRecord] = []

        # Callbacks: action → callable
        self._action_handlers: Dict[str, Callable] = {}

        # Stats
        self._stats = {
            "total_created": 0,
            "total_triggered": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_skipped": 0,
        }

    # ------------------------------------------------------------------
    # Schedule management
    # ------------------------------------------------------------------

    def create_schedule(
        self,
        name: str,
        action: str,
        schedule_type: str = "interval",
        interval_seconds: float = 0.0,
        cron_minute: int = -1,
        cron_hour: int = -1,
        cron_day: int = -1,
        run_at: float = 0.0,
        context: Optional[Dict] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
        description: str = "",
        max_triggers: int = 0,
    ) -> Optional[str]:
        """Create a schedule. Returns schedule_id or None if name exists."""
        if name in self._by_name:
            return None

        sid = f"sched-{uuid.uuid4().hex[:8]}"
        stype = ScheduleType(schedule_type) if isinstance(schedule_type, str) else schedule_type

        sched = ScheduleDefinition(
            schedule_id=sid,
            name=name,
            schedule_type=stype,
            action=action,
            interval_seconds=interval_seconds,
            cron_minute=cron_minute,
            cron_hour=cron_hour,
            cron_day=cron_day,
            run_at=run_at,
            context=context or {},
            tags=tags or set(),
            metadata=metadata or {},
            description=description,
            created_at=time.time(),
            max_triggers=max_triggers,
        )

        self._schedules[sid] = sched
        self._by_name[name] = sid
        self._stats["total_created"] += 1
        return sid

    def delete_schedule(self, name: str) -> bool:
        """Delete a schedule by name."""
        sid = self._by_name.get(name)
        if not sid:
            return False
        del self._schedules[sid]
        del self._by_name[name]
        return True

    def enable_schedule(self, name: str) -> bool:
        """Enable a schedule."""
        sid = self._by_name.get(name)
        if not sid:
            return False
        self._schedules[sid].enabled = True
        return True

    def disable_schedule(self, name: str) -> bool:
        """Disable a schedule."""
        sid = self._by_name.get(name)
        if not sid:
            return False
        self._schedules[sid].enabled = False
        return True

    def get_schedule(self, name: str) -> Optional[Dict]:
        """Get schedule info."""
        sid = self._by_name.get(name)
        if not sid:
            return None
        return self._sched_to_dict(self._schedules[sid])

    def list_schedules(
        self,
        enabled_only: bool = False,
        schedule_type: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[Dict]:
        """List schedules with optional filters."""
        results = []
        for s in self._schedules.values():
            if enabled_only and not s.enabled:
                continue
            if schedule_type and s.schedule_type.value != schedule_type:
                continue
            if tags and not tags.issubset(s.tags):
                continue
            results.append(self._sched_to_dict(s))
        return sorted(results, key=lambda x: x["name"])

    def _sched_to_dict(self, s: ScheduleDefinition) -> Dict:
        return {
            "schedule_id": s.schedule_id,
            "name": s.name,
            "schedule_type": s.schedule_type.value,
            "action": s.action,
            "enabled": s.enabled,
            "interval_seconds": s.interval_seconds,
            "cron_minute": s.cron_minute,
            "cron_hour": s.cron_hour,
            "cron_day": s.cron_day,
            "run_at": s.run_at,
            "description": s.description,
            "context": s.context,
            "tags": sorted(s.tags),
            "metadata": s.metadata,
            "created_at": s.created_at,
            "last_triggered": s.last_triggered,
            "trigger_count": s.trigger_count,
            "max_triggers": s.max_triggers,
        }

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def register_action(self, action: str, handler: Callable) -> None:
        """Register a handler for an action name."""
        self._action_handlers[action] = handler

    def unregister_action(self, action: str) -> bool:
        """Unregister an action handler."""
        if action not in self._action_handlers:
            return False
        del self._action_handlers[action]
        return True

    def list_actions(self) -> List[str]:
        """List registered action names."""
        return sorted(self._action_handlers.keys())

    # ------------------------------------------------------------------
    # Triggering
    # ------------------------------------------------------------------

    def check_due(self, now: float = 0.0) -> List[str]:
        """
        Check which schedules are due for triggering.
        Returns list of schedule names that should be triggered.
        """
        now = now or time.time()
        due = []

        for s in self._schedules.values():
            if not s.enabled:
                continue
            if s.max_triggers > 0 and s.trigger_count >= s.max_triggers:
                continue

            if s.schedule_type == ScheduleType.ONCE:
                if s.run_at > 0 and now >= s.run_at and s.trigger_count == 0:
                    due.append(s.name)

            elif s.schedule_type == ScheduleType.INTERVAL:
                if s.interval_seconds <= 0:
                    continue
                if s.last_triggered == 0:
                    # Never triggered, trigger immediately
                    due.append(s.name)
                elif (now - s.last_triggered) >= s.interval_seconds:
                    due.append(s.name)

            elif s.schedule_type == ScheduleType.CRON:
                if self._cron_matches(s, now) and self._cron_not_recently_triggered(s, now):
                    due.append(s.name)

        return due

    def _cron_matches(self, s: ScheduleDefinition, now: float) -> bool:
        """Check if current time matches cron spec."""
        import datetime
        dt = datetime.datetime.fromtimestamp(now)
        if s.cron_minute >= 0 and dt.minute != s.cron_minute:
            return False
        if s.cron_hour >= 0 and dt.hour != s.cron_hour:
            return False
        if s.cron_day >= 0 and dt.weekday() != s.cron_day:
            return False
        return True

    def _cron_not_recently_triggered(self, s: ScheduleDefinition, now: float) -> bool:
        """Ensure we don't re-trigger within the same minute."""
        if s.last_triggered == 0:
            return True
        return (now - s.last_triggered) >= 60.0

    def trigger(self, name: str, context_override: Optional[Dict] = None) -> Optional[str]:
        """
        Manually trigger a schedule. Returns trigger_id or None.
        Runs the action handler if registered, otherwise just records the trigger.
        """
        sid = self._by_name.get(name)
        if not sid:
            return None

        s = self._schedules[sid]

        # Check max triggers
        if s.max_triggers > 0 and s.trigger_count >= s.max_triggers:
            return None

        tid = f"trig-{uuid.uuid4().hex[:8]}"
        now = time.time()

        record = TriggerRecord(
            trigger_id=tid,
            schedule_id=sid,
            schedule_name=name,
            action=s.action,
            status=TriggerStatus.RUNNING,
            triggered_at=now,
        )

        s.last_triggered = now
        s.trigger_count += 1
        self._stats["total_triggered"] += 1

        # Run action handler
        handler = self._action_handlers.get(s.action)
        ctx = {**s.context, **(context_override or {})}

        if handler:
            try:
                result = handler(ctx)
                record.status = TriggerStatus.COMPLETED
                record.result = result
                record.completed_at = time.time()
                self._stats["total_completed"] += 1
            except Exception as e:
                record.status = TriggerStatus.FAILED
                record.error = str(e)
                record.completed_at = time.time()
                self._stats["total_failed"] += 1
        else:
            # No handler, mark as completed with no-op
            record.status = TriggerStatus.COMPLETED
            record.result = {"message": f"No handler for action '{s.action}'"}
            record.completed_at = time.time()
            self._stats["total_completed"] += 1

        self._history.append(record)

        # Auto-disable one-time schedules
        if s.schedule_type == ScheduleType.ONCE:
            s.enabled = False

        # Prune history
        if len(self._history) > self._max_history:
            removed = len(self._history) - self._max_history
            self._history = self._history[-self._max_history:]

        return tid

    def skip_trigger(self, name: str, reason: str = "") -> Optional[str]:
        """Record a skipped trigger."""
        sid = self._by_name.get(name)
        if not sid:
            return None

        s = self._schedules[sid]
        tid = f"trig-{uuid.uuid4().hex[:8]}"

        record = TriggerRecord(
            trigger_id=tid,
            schedule_id=sid,
            schedule_name=name,
            action=s.action,
            status=TriggerStatus.SKIPPED,
            triggered_at=time.time(),
            completed_at=time.time(),
            error=reason,
        )

        self._history.append(record)
        self._stats["total_skipped"] += 1
        return tid

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_trigger_history(
        self,
        name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get trigger history with filters."""
        results = []
        for r in reversed(self._history):
            if name and r.schedule_name != name:
                continue
            if status and r.status.value != status:
                continue
            results.append({
                "trigger_id": r.trigger_id,
                "schedule_id": r.schedule_id,
                "schedule_name": r.schedule_name,
                "action": r.action,
                "status": r.status.value,
                "triggered_at": r.triggered_at,
                "completed_at": r.completed_at,
                "result": r.result,
                "error": r.error,
            })
            if len(results) >= limit:
                break
        return results

    def get_last_trigger(self, name: str) -> Optional[Dict]:
        """Get the most recent trigger for a schedule."""
        for r in reversed(self._history):
            if r.schedule_name == name:
                return {
                    "trigger_id": r.trigger_id,
                    "status": r.status.value,
                    "triggered_at": r.triggered_at,
                    "result": r.result,
                    "error": r.error,
                }
        return None

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_schedules": len(self._schedules),
            "enabled_schedules": sum(1 for s in self._schedules.values() if s.enabled),
            "registered_actions": len(self._action_handlers),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._schedules.clear()
        self._by_name.clear()
        self._history.clear()
        self._action_handlers.clear()
        self._stats = {k: 0 for k in self._stats}
