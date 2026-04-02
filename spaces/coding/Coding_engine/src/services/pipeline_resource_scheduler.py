"""Pipeline Resource Scheduler -- manages scheduling of pipeline resources.

Tracks resource schedules through their lifecycle: pending -> allocated ->
released, with priority-based ordering and per-pipeline queries.

Usage::

    scheduler = PipelineResourceScheduler()

    # Schedule a resource
    sid = scheduler.schedule_resource("pipe-1", "cpu", 4, priority=8)

    # Allocate and release
    scheduler.allocate(sid)
    scheduler.release(sid)

    # Query
    pending = scheduler.get_pending_schedules()
    usage = scheduler.get_resource_usage("cpu")
    stats = scheduler.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class _ScheduleEntry:
    """A single pipeline resource schedule."""

    schedule_id: str = ""
    pipeline_id: str = ""
    resource_type: str = ""
    amount: float = 0.0
    priority: int = 5
    status: str = "pending"  # pending | allocated | released | cancelled
    created_at: float = 0.0
    allocated_at: float = 0.0
    released_at: float = 0.0
    seq: int = 0


# ======================================================================
# Scheduler
# ======================================================================

class PipelineResourceScheduler:
    """Manages scheduling of pipeline resources.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage
        self._schedules: Dict[str, _ScheduleEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_scheduled: int = 0
        self._total_allocated: int = 0
        self._total_released: int = 0
        self._total_cancelled: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("pipeline_resource_scheduler.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, pipeline_id: str, resource_type: str) -> str:
        """Generate a unique schedule ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{pipeline_id}:{resource_type}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"prs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached.

        Prefers removing terminal records (released / cancelled)
        first, falling back to the oldest overall entries if necessary.
        """
        if len(self._schedules) < self._max_entries:
            return

        terminal = [
            (sid, entry)
            for sid, entry in self._schedules.items()
            if entry.status in ("released", "cancelled")
        ]
        terminal.sort(key=lambda pair: pair[1].seq)

        to_remove = max(1, len(self._schedules) - self._max_entries + 1)

        if len(terminal) >= to_remove:
            victims = terminal[:to_remove]
        else:
            all_sorted = sorted(
                self._schedules.items(), key=lambda pair: pair[1].seq,
            )
            victims = all_sorted[:to_remove]

        for sid, _entry in victims:
            del self._schedules[sid]
            self._total_evictions += 1

        logger.debug(
            "pipeline_resource_scheduler.pruned removed=%d remaining=%d",
            len(victims),
            len(self._schedules),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback.

        If *name* already exists the callback is silently replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("pipeline_resource_scheduler.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("pipeline_resource_scheduler.callback_removed name=%s", name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break scheduler operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "pipeline_resource_scheduler.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _ScheduleEntry) -> Dict[str, Any]:
        """Convert a _ScheduleEntry to a plain dict for external use."""
        return {
            "schedule_id": entry.schedule_id,
            "pipeline_id": entry.pipeline_id,
            "resource_type": entry.resource_type,
            "amount": entry.amount,
            "priority": entry.priority,
            "status": entry.status,
            "allocated_at": entry.allocated_at,
            "created_at": entry.created_at,
        }

    # ------------------------------------------------------------------
    # Core API -- schedule resource
    # ------------------------------------------------------------------

    def schedule_resource(
        self,
        pipeline_id: str,
        resource_type: str,
        amount: float,
        priority: int = 5,
    ) -> str:
        """Schedule a resource for a pipeline.

        Parameters
        ----------
        pipeline_id:
            The pipeline requesting the resource.
        resource_type:
            The type of resource (e.g., "cpu", "memory", "gpu").
        amount:
            The amount of the resource to schedule.
        priority:
            Priority level (higher = more urgent). Defaults to 5.

        Returns
        -------
        str
            The generated schedule ID (prefix ``"prs-"``).
        """
        with self._lock:
            self._prune_if_needed()

            now = time.time()
            schedule_id = self._gen_id(pipeline_id, resource_type)

            entry = _ScheduleEntry(
                schedule_id=schedule_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
                amount=amount,
                priority=priority,
                status="pending",
                created_at=now,
                seq=self._seq,
            )
            self._schedules[schedule_id] = entry
            self._total_scheduled += 1

            details = self._to_dict(entry)

        logger.debug(
            "pipeline_resource_scheduler.resource_scheduled id=%s pipeline=%s type=%s",
            schedule_id,
            pipeline_id,
            resource_type,
        )
        self._fire("resource_scheduled", details)
        return schedule_id

    # ------------------------------------------------------------------
    # Core API -- lookup
    # ------------------------------------------------------------------

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Return a schedule record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            entry = self._schedules.get(schedule_id)
            if entry is None:
                return None
            return self._to_dict(entry)

    # ------------------------------------------------------------------
    # Core API -- lifecycle transitions
    # ------------------------------------------------------------------

    def allocate(self, schedule_id: str) -> bool:
        """Mark a resource schedule as allocated.

        Returns ``False`` if the schedule is not found or is not in
        ``"pending"`` status.
        """
        if not schedule_id:
            return False

        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry is None:
                logger.debug(
                    "pipeline_resource_scheduler.allocate.not_found id=%s",
                    schedule_id,
                )
                return False

            if entry.status != "pending":
                logger.debug(
                    "pipeline_resource_scheduler.allocate.wrong_status id=%s status=%s",
                    schedule_id,
                    entry.status,
                )
                return False

            entry.status = "allocated"
            entry.allocated_at = time.time()
            self._total_allocated += 1
            details = self._to_dict(entry)

        logger.debug(
            "pipeline_resource_scheduler.resource_allocated id=%s", schedule_id,
        )
        self._fire("resource_allocated", details)
        return True

    def release(self, schedule_id: str) -> bool:
        """Mark an allocated resource schedule as released.

        Returns ``False`` if the schedule is not found or is not in
        ``"allocated"`` status.
        """
        if not schedule_id:
            return False

        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry is None:
                logger.debug(
                    "pipeline_resource_scheduler.release.not_found id=%s",
                    schedule_id,
                )
                return False

            if entry.status != "allocated":
                logger.debug(
                    "pipeline_resource_scheduler.release.wrong_status id=%s status=%s",
                    schedule_id,
                    entry.status,
                )
                return False

            entry.status = "released"
            entry.released_at = time.time()
            self._total_released += 1
            details = self._to_dict(entry)

        logger.debug(
            "pipeline_resource_scheduler.resource_released id=%s", schedule_id,
        )
        self._fire("resource_released", details)
        return True

    def cancel_schedule(self, schedule_id: str) -> bool:
        """Cancel a pending resource schedule.

        Returns ``False`` if the schedule is not found or is already
        in ``"allocated"`` status.
        """
        if not schedule_id:
            return False

        with self._lock:
            entry = self._schedules.get(schedule_id)
            if entry is None:
                logger.debug(
                    "pipeline_resource_scheduler.cancel.not_found id=%s",
                    schedule_id,
                )
                return False

            if entry.status == "allocated":
                logger.debug(
                    "pipeline_resource_scheduler.cancel.already_allocated id=%s",
                    schedule_id,
                )
                return False

            entry.status = "cancelled"
            self._total_cancelled += 1
            details = self._to_dict(entry)

        logger.debug(
            "pipeline_resource_scheduler.schedule_cancelled id=%s", schedule_id,
        )
        self._fire("schedule_cancelled", details)
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_pipeline_schedules(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return all schedules for a pipeline, newest first."""
        with self._lock:
            self._total_lookups += 1
            if not pipeline_id:
                return []
            results = [
                self._to_dict(entry)
                for entry in self._schedules.values()
                if entry.pipeline_id == pipeline_id
            ]
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def get_pending_schedules(self) -> List[Dict[str, Any]]:
        """Return all pending schedules, sorted by priority (highest first)."""
        with self._lock:
            self._total_lookups += 1
            pending = [
                entry
                for entry in self._schedules.values()
                if entry.status == "pending"
            ]
        pending.sort(key=lambda e: (-e.priority, e.created_at))
        return [self._to_dict(e) for e in pending]

    def get_allocated_resources(
        self, pipeline_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return allocated schedules, optionally filtered by pipeline.

        Parameters
        ----------
        pipeline_id:
            If provided, only return allocated schedules for this pipeline.
        """
        with self._lock:
            self._total_lookups += 1
            results = [
                self._to_dict(entry)
                for entry in self._schedules.values()
                if entry.status == "allocated"
                and (pipeline_id is None or entry.pipeline_id == pipeline_id)
            ]
        results.sort(key=lambda d: d["allocated_at"], reverse=True)
        return results

    def get_resource_usage(self, resource_type: str) -> Dict[str, Any]:
        """Return usage summary for a resource type.

        Returns
        -------
        dict
            Contains resource_type, total_allocated, total_pending,
            and schedule_count.
        """
        with self._lock:
            self._total_lookups += 1
            total_allocated = 0.0
            total_pending = 0.0
            schedule_count = 0

            for entry in self._schedules.values():
                if entry.resource_type != resource_type:
                    continue
                schedule_count += 1
                if entry.status == "allocated":
                    total_allocated += entry.amount
                elif entry.status == "pending":
                    total_pending += entry.amount

            return {
                "resource_type": resource_type,
                "total_allocated": total_allocated,
                "total_pending": total_pending,
                "schedule_count": schedule_count,
            }

    def list_pipelines(self) -> List[str]:
        """Return a sorted list of unique pipeline IDs that have schedules."""
        with self._lock:
            self._total_lookups += 1
            pipelines: set[str] = set()
            for entry in self._schedules.values():
                pipelines.add(entry.pipeline_id)
            return sorted(pipelines)

    def get_schedule_count(self, pipeline_id: Optional[str] = None) -> int:
        """Count schedules, optionally filtered by pipeline.

        Parameters
        ----------
        pipeline_id:
            If provided, only count schedules for this pipeline.
            Otherwise returns total count.
        """
        with self._lock:
            self._total_lookups += 1
            if pipeline_id is None:
                return len(self._schedules)
            count = 0
            for entry in self._schedules.values():
                if entry.pipeline_id == pipeline_id:
                    count += 1
            return count

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the scheduler."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            unique_pipelines: set[str] = set()
            unique_resource_types: set[str] = set()

            for entry in self._schedules.values():
                status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
                unique_pipelines.add(entry.pipeline_id)
                unique_resource_types.add(entry.resource_type)

            return {
                "current_entries": len(self._schedules),
                "max_entries": self._max_entries,
                "status_counts": status_counts,
                "unique_pipelines": len(unique_pipelines),
                "unique_resource_types": len(unique_resource_types),
                "total_scheduled": self._total_scheduled,
                "total_allocated": self._total_allocated,
                "total_released": self._total_released,
                "total_cancelled": self._total_cancelled,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all schedule records, callbacks, and counters."""
        with self._lock:
            self._schedules.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_scheduled = 0
            self._total_allocated = 0
            self._total_released = 0
            self._total_cancelled = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("pipeline_resource_scheduler.reset")
