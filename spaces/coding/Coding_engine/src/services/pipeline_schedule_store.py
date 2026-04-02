"""Pipeline Schedule Store -- manages scheduled pipeline executions with
cron-like interval scheduling and next-run tracking.

Features:
- Create schedules with interval-based recurrence
- Enable/disable schedules without deleting
- Track last-run and next-run timestamps
- Query due schedules (enabled + next_run <= now)
- Pipeline-name uniqueness enforcement
- Max-entries pruning with configurable limit
- Change callbacks for reactive integrations
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScheduleEntry:
    """Internal representation of a scheduled pipeline execution."""
    schedule_id: str
    pipeline_name: str
    interval_seconds: float
    last_run: float
    next_run: float
    enabled: bool
    metadata: Dict[str, Any]
    tags: List[str]
    created_at: float


# ---------------------------------------------------------------------------
# Pipeline Schedule Store
# ---------------------------------------------------------------------------

class PipelineScheduleStore:
    """Manages scheduled pipeline executions with interval-based recurrence,
    next-run tracking, and due-schedule queries."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._schedules: Dict[str, ScheduleEntry] = {}
        self._by_pipeline: Dict[str, str] = {}  # pipeline_name -> schedule_id
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_runs_marked = 0
        self._total_enabled = 0
        self._total_disabled = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        """Generate a collision-free ID with prefix pss-."""
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pss-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.warning("callback_error", callback=cb_name, action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._schedules) > self._max_entries:
            oldest_id = min(
                self._schedules,
                key=lambda k: self._schedules[k].created_at,
            )
            entry = self._schedules.pop(oldest_id)
            self._by_pipeline.pop(entry.pipeline_name, None)
            logger.info("schedule_pruned", schedule_id=oldest_id,
                        pipeline=entry.pipeline_name)

    # ------------------------------------------------------------------
    # Serialisation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: ScheduleEntry) -> Dict[str, Any]:
        """Convert a ScheduleEntry to a plain dict."""
        return {
            "schedule_id": entry.schedule_id,
            "pipeline_name": entry.pipeline_name,
            "interval_seconds": entry.interval_seconds,
            "last_run": entry.last_run,
            "next_run": entry.next_run,
            "enabled": entry.enabled,
            "metadata": dict(entry.metadata),
            "tags": list(entry.tags),
            "created_at": entry.created_at,
        }

    # ------------------------------------------------------------------
    # create_schedule
    # ------------------------------------------------------------------

    def create_schedule(
        self,
        pipeline_name: str,
        interval_seconds: float,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new schedule for a pipeline.

        Returns the schedule_id (pss-...) on success, or "" if a schedule
        already exists for the given pipeline_name.
        """
        if pipeline_name in self._by_pipeline:
            logger.warning("schedule_duplicate", pipeline=pipeline_name)
            return ""

        schedule_id = self._generate_id(pipeline_name)
        now = time.time()

        entry = ScheduleEntry(
            schedule_id=schedule_id,
            pipeline_name=pipeline_name,
            interval_seconds=float(interval_seconds),
            last_run=0.0,
            next_run=now,
            enabled=True,
            metadata=dict(metadata) if metadata else {},
            tags=list(tags) if tags else [],
            created_at=now,
        )

        self._schedules[schedule_id] = entry
        self._by_pipeline[pipeline_name] = schedule_id
        self._total_created += 1
        self._prune()

        logger.info("schedule_created", schedule_id=schedule_id,
                     pipeline=pipeline_name, interval=interval_seconds)
        self._fire("create_schedule", self._entry_to_dict(entry))
        return schedule_id

    # ------------------------------------------------------------------
    # get_schedule
    # ------------------------------------------------------------------

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a schedule by its ID. Returns None if not found."""
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # get_schedule_by_pipeline
    # ------------------------------------------------------------------

    def get_schedule_by_pipeline(self, pipeline_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a schedule by pipeline name. Returns None if not found."""
        schedule_id = self._by_pipeline.get(pipeline_name)
        if schedule_id is None:
            return None
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # enable_schedule / disable_schedule
    # ------------------------------------------------------------------

    def enable_schedule(self, schedule_id: str) -> bool:
        """Enable a schedule. Returns False if not found."""
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return False
        entry.enabled = True
        self._total_enabled += 1
        logger.info("schedule_enabled", schedule_id=schedule_id,
                     pipeline=entry.pipeline_name)
        self._fire("enable_schedule", {"schedule_id": schedule_id,
                                        "pipeline_name": entry.pipeline_name})
        return True

    def disable_schedule(self, schedule_id: str) -> bool:
        """Disable a schedule. Returns False if not found."""
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return False
        entry.enabled = False
        self._total_disabled += 1
        logger.info("schedule_disabled", schedule_id=schedule_id,
                     pipeline=entry.pipeline_name)
        self._fire("disable_schedule", {"schedule_id": schedule_id,
                                         "pipeline_name": entry.pipeline_name})
        return True

    # ------------------------------------------------------------------
    # mark_run
    # ------------------------------------------------------------------

    def mark_run(self, schedule_id: str) -> bool:
        """Record that a schedule has just been executed.

        Updates last_run to now and sets next_run = now + interval_seconds.
        Returns False if the schedule_id is not found.
        """
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return False

        now = time.time()
        entry.last_run = now
        entry.next_run = now + entry.interval_seconds
        self._total_runs_marked += 1

        logger.info("schedule_run_marked", schedule_id=schedule_id,
                     pipeline=entry.pipeline_name, next_run=entry.next_run)
        self._fire("mark_run", {
            "schedule_id": schedule_id,
            "pipeline_name": entry.pipeline_name,
            "last_run": entry.last_run,
            "next_run": entry.next_run,
        })
        return True

    # ------------------------------------------------------------------
    # get_due_schedules
    # ------------------------------------------------------------------

    def get_due_schedules(self) -> List[Dict[str, Any]]:
        """Return all enabled schedules whose next_run <= now.

        Results are sorted by next_run (earliest first).
        """
        now = time.time()
        due: List[Dict[str, Any]] = []

        for entry in self._schedules.values():
            if not entry.enabled:
                continue
            if entry.next_run <= now:
                due.append(self._entry_to_dict(entry))

        due.sort(key=lambda d: d["next_run"])
        logger.debug("due_schedules_queried", count=len(due))
        return due

    # ------------------------------------------------------------------
    # list_schedules
    # ------------------------------------------------------------------

    def list_schedules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all schedules, optionally filtered to enabled only.

        Results are sorted by pipeline_name.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._schedules.values():
            if enabled_only and not entry.enabled:
                continue
            results.append(self._entry_to_dict(entry))
        results.sort(key=lambda d: d["pipeline_name"])
        return results

    # ------------------------------------------------------------------
    # remove_schedule
    # ------------------------------------------------------------------

    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule by ID. Returns False if not found."""
        entry = self._schedules.get(schedule_id)
        if entry is None:
            return False

        del self._schedules[schedule_id]
        self._by_pipeline.pop(entry.pipeline_name, None)
        self._total_removed += 1

        logger.info("schedule_removed", schedule_id=schedule_id,
                     pipeline=entry.pipeline_name)
        self._fire("remove_schedule", {"schedule_id": schedule_id,
                                        "pipeline_name": entry.pipeline_name})
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        enabled_count = sum(1 for e in self._schedules.values() if e.enabled)
        disabled_count = len(self._schedules) - enabled_count
        return {
            "total_created": self._total_created,
            "total_removed": self._total_removed,
            "total_runs_marked": self._total_runs_marked,
            "total_enabled": self._total_enabled,
            "total_disabled": self._total_disabled,
            "current_schedules": len(self._schedules),
            "current_enabled": enabled_count,
            "current_disabled": disabled_count,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all schedules, callbacks, and counters."""
        self._schedules.clear()
        self._by_pipeline.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_runs_marked = 0
        self._total_enabled = 0
        self._total_disabled = 0
        logger.info("schedule_store_reset")
