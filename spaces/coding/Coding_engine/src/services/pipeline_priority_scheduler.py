"""Pipeline priority scheduler.

Schedules pipeline executions based on priority with support for
dependencies.  Higher-priority pipelines are dispatched first, and a
pipeline is only considered *ready* when every entry listed in its
``depends_on`` set has been marked as completed.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScheduleEntry:
    """A single scheduled pipeline execution."""
    schedule_id: str = ""
    pipeline_id: str = ""
    priority: int = 0
    status: str = "pending"
    depends_on: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Priority Scheduler
# ---------------------------------------------------------------------------

class PipelinePriorityScheduler:
    """Schedule and dispatch pipeline executions based on priority."""

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, ScheduleEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries
        self._stats = {
            "total_scheduled": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, key: str) -> str:
        """Generate a collision-free ID with prefix 'pps-'."""
        self._seq += 1
        raw = f"{key}:{uuid.uuid4().hex}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pps-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._entries) < self._max_entries:
            return
        sorted_entries = sorted(
            self._entries.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._entries) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._entries[entry.schedule_id]
            logger.debug("schedule_entry_pruned", schedule_id=entry.schedule_id)

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        pipeline_id: str,
        priority: int = 0,
        depends_on: Optional[List[str]] = None,
    ) -> str:
        """Schedule a pipeline execution.

        Args:
            pipeline_id: Identifier of the pipeline to execute.
            priority: Numeric priority (higher = more urgent).
            depends_on: List of schedule IDs that must complete first.

        Returns:
            The new schedule ID, or ``""`` on invalid input.
        """
        if not pipeline_id:
            logger.warning("schedule_invalid_input", pipeline_id=pipeline_id)
            return ""

        deps = list(depends_on or [])
        # Validate that all dependencies exist
        for dep_id in deps:
            if dep_id not in self._entries:
                logger.warning(
                    "schedule_unknown_dependency",
                    pipeline_id=pipeline_id,
                    dependency=dep_id,
                )
                return ""

        self._prune_if_needed()

        schedule_id = self._next_id(pipeline_id)
        now = time.time()

        entry = ScheduleEntry(
            schedule_id=schedule_id,
            pipeline_id=pipeline_id,
            priority=priority,
            status="pending",
            depends_on=deps,
            created_at=now,
            seq=self._seq,
        )

        self._entries[schedule_id] = entry
        self._stats["total_scheduled"] += 1

        logger.info(
            "pipeline_scheduled",
            schedule_id=schedule_id,
            pipeline_id=pipeline_id,
            priority=priority,
            depends_on=deps,
        )
        self._fire("scheduled", self._entry_to_dict(entry))
        return schedule_id

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def get_next(self) -> Optional[Dict]:
        """Get the highest-priority *ready* pipeline.

        A pipeline is ready when its status is ``"pending"`` and every
        entry in its ``depends_on`` list has status ``"completed"``.

        Returns:
            A dict with ``pipeline_id``, ``priority``, ``schedule_id``,
            or ``None`` if no ready pipeline exists.
        """
        candidates: List[ScheduleEntry] = []
        for entry in self._entries.values():
            if entry.status != "pending":
                continue
            # Check all dependencies are completed
            if not self._deps_met(entry):
                continue
            candidates.append(entry)

        if not candidates:
            return None

        # Sort by priority descending, then creation time ascending
        candidates.sort(key=lambda e: (-e.priority, e.created_at))
        best = candidates[0]
        return {
            "pipeline_id": best.pipeline_id,
            "priority": best.priority,
            "schedule_id": best.schedule_id,
        }

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_running(self, schedule_id: str) -> bool:
        """Mark a pending schedule as running."""
        entry = self._entries.get(schedule_id)
        if not entry or entry.status != "pending":
            return False
        entry.status = "running"
        entry.started_at = time.time()
        logger.info("pipeline_running", schedule_id=schedule_id)
        self._fire("running", self._entry_to_dict(entry))
        return True

    def mark_completed(self, schedule_id: str) -> bool:
        """Mark a running schedule as completed."""
        entry = self._entries.get(schedule_id)
        if not entry or entry.status != "running":
            return False
        entry.status = "completed"
        entry.completed_at = time.time()
        self._stats["total_completed"] += 1
        logger.info("pipeline_completed", schedule_id=schedule_id)
        self._fire("completed", self._entry_to_dict(entry))
        return True

    def mark_failed(self, schedule_id: str) -> bool:
        """Mark a running schedule as failed."""
        entry = self._entries.get(schedule_id)
        if not entry or entry.status != "running":
            return False
        entry.status = "failed"
        entry.completed_at = time.time()
        self._stats["total_failed"] += 1
        logger.info("pipeline_failed", schedule_id=schedule_id)
        self._fire("failed", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        """Get a schedule entry by ID."""
        entry = self._entries.get(schedule_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_pending_count(self) -> int:
        """Return the number of pending schedules."""
        return sum(1 for e in self._entries.values() if e.status == "pending")

    def list_pipelines(self) -> List[str]:
        """List all scheduled pipeline IDs (unique, sorted)."""
        pipelines = set()
        for entry in self._entries.values():
            pipelines.add(entry.pipeline_id)
        return sorted(pipelines)

    def get_schedule_count(self) -> int:
        """Return the total number of schedule entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return scheduler statistics."""
        by_status: Dict[str, int] = {}
        for entry in self._entries.values():
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "max_entries": self._max_entries,
            "by_status": by_status,
            "pipelines": len(set(e.pipeline_id for e in self._entries.values())),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("scheduler_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deps_met(self, entry: ScheduleEntry) -> bool:
        """Return True if all dependencies are completed."""
        for dep_id in entry.depends_on:
            dep = self._entries.get(dep_id)
            if not dep or dep.status != "completed":
                return False
        return True

    def _entry_to_dict(self, entry: ScheduleEntry) -> Dict:
        """Convert a ScheduleEntry to a plain dict."""
        return {
            "schedule_id": entry.schedule_id,
            "pipeline_id": entry.pipeline_id,
            "priority": entry.priority,
            "status": entry.status,
            "depends_on": list(entry.depends_on),
            "created_at": entry.created_at,
            "started_at": entry.started_at,
            "completed_at": entry.completed_at,
            "seq": entry.seq,
        }

    def _fire(self, action: str, detail: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
