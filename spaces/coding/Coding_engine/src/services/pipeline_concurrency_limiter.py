"""Pipeline Concurrency Limiter — manage concurrency slots for pipeline executions.

Controls how many executions of a given pipeline can run simultaneously.
Each pipeline can have a configurable maximum concurrency, and callers
must acquire a slot before executing and release it when done.

Thread-safe: all public methods are guarded by a threading lock.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConcurrencyLimit:
    """A concurrency limit for a single pipeline."""

    limit_id: str = ""
    pipeline_id: str = ""
    max_concurrent: int = 1
    active_executions: Set[str] = field(default_factory=set)
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Concurrency Limiter
# ---------------------------------------------------------------------------

class PipelineConcurrencyLimiter:
    """Manages concurrency limits that control how many pipeline executions
    can run simultaneously.

    All public methods acquire a lock before mutating or reading internal
    state, making the service safe for concurrent use from multiple threads.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._limits: Dict[str, ConcurrencyLimit] = {}  # keyed by pipeline_id
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_limits_created": 0,
            "total_limits_updated": 0,
            "total_limits_removed": 0,
            "total_slots_acquired": 0,
            "total_slots_released": 0,
            "total_acquire_denied": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique limit ID with prefix ``pcl-``."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pcl-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds *max_entries*."""
        if len(self._limits) <= self._max_entries:
            return
        sorted_records = sorted(
            self._limits.values(), key=lambda r: r.created_at
        )
        remove_count = len(self._limits) - self._max_entries
        for record in sorted_records[:remove_count]:
            del self._limits[record.pipeline_id]
            self._stats["total_pruned"] += 1
            logger.debug(
                "limit_pruned: limit_id=%s pipeline_id=%s",
                record.limit_id,
                record.pipeline_id,
            )

    def _record_to_dict(self, record: ConcurrencyLimit) -> Dict[str, Any]:
        """Convert a *ConcurrencyLimit* dataclass to a plain dictionary."""
        return {
            "limit_id": record.limit_id,
            "pipeline_id": record.pipeline_id,
            "max_concurrent": record.max_concurrent,
            "current_count": len(record.active_executions),
            "created_at": record.created_at,
        }

    # ------------------------------------------------------------------
    # Set limit
    # ------------------------------------------------------------------

    def set_limit(self, pipeline_id: str, max_concurrent: int) -> str:
        """Create or update a concurrency limit. Returns limit_id (``pcl-`` prefix)."""
        with self._lock:
            existing = self._limits.get(pipeline_id)
            if existing is not None:
                existing.max_concurrent = max_concurrent
                self._stats["total_limits_updated"] += 1
                logger.info(
                    "limit_updated: id=%s pipeline_id=%s max_concurrent=%d",
                    existing.limit_id, pipeline_id, max_concurrent,
                )
                detail = self._record_to_dict(existing)
                lid = existing.limit_id
            else:
                self._prune_if_needed()
                lid = self._next_id(pipeline_id)
                now = time.time()
                record = ConcurrencyLimit(
                    limit_id=lid,
                    pipeline_id=pipeline_id,
                    max_concurrent=max_concurrent,
                    created_at=now,
                    seq=self._seq,
                )
                self._limits[pipeline_id] = record
                self._stats["total_limits_created"] += 1
                logger.info(
                    "limit_created: id=%s pipeline_id=%s max_concurrent=%d",
                    lid, pipeline_id, max_concurrent,
                )
                detail = self._record_to_dict(record)

        self._fire("limit_set", detail)
        return lid

    # ------------------------------------------------------------------
    # Get limit
    # ------------------------------------------------------------------

    def get_limit(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """Get limit by pipeline ID. Returns dict or ``None``."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return None
            return self._record_to_dict(record)

    # ------------------------------------------------------------------
    # Acquire slot
    # ------------------------------------------------------------------

    def acquire_slot(self, pipeline_id: str, execution_id: str) -> bool:
        """Acquire a concurrency slot. Returns ``False`` if at max."""
        denied = False
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return False
            if execution_id in record.active_executions:
                return True  # already holding
            if len(record.active_executions) >= record.max_concurrent:
                self._stats["total_acquire_denied"] += 1
                logger.debug(
                    "slot_denied: pipeline_id=%s execution_id=%s current=%d max=%d",
                    pipeline_id, execution_id,
                    len(record.active_executions), record.max_concurrent,
                )
                denied = True
                detail = self._record_to_dict(record)
                detail["execution_id"] = execution_id
            else:
                record.active_executions.add(execution_id)
                self._stats["total_slots_acquired"] += 1
                logger.info(
                    "slot_acquired: pipeline_id=%s execution_id=%s current=%d",
                    pipeline_id, execution_id, len(record.active_executions),
                )
                detail = self._record_to_dict(record)
                detail["execution_id"] = execution_id

        if denied:
            self._fire("slot_denied", detail)
            return False
        self._fire("slot_acquired", detail)
        return True

    # ------------------------------------------------------------------
    # Release slot
    # ------------------------------------------------------------------

    def release_slot(self, pipeline_id: str, execution_id: str) -> bool:
        """Release a concurrency slot. Returns ``False`` if not held."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return False
            if execution_id not in record.active_executions:
                return False
            record.active_executions.discard(execution_id)
            self._stats["total_slots_released"] += 1
            logger.info(
                "slot_released: pipeline_id=%s execution_id=%s current=%d",
                pipeline_id, execution_id, len(record.active_executions),
            )
            detail = self._record_to_dict(record)
            detail["execution_id"] = execution_id

        self._fire("slot_released", detail)
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_current_count(self, pipeline_id: str) -> int:
        """Current number of active slots for a pipeline."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return 0
            return len(record.active_executions)

    def is_available(self, pipeline_id: str) -> bool:
        """Return ``True`` if slots are available for the pipeline."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return False
            return len(record.active_executions) < record.max_concurrent

    def get_active_executions(self, pipeline_id: str) -> List[str]:
        """Return list of execution IDs currently holding slots."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return []
            return list(record.active_executions)

    # ------------------------------------------------------------------
    # Remove limit
    # ------------------------------------------------------------------

    def remove_limit(self, pipeline_id: str) -> bool:
        """Remove a concurrency limit entirely. Returns ``False`` if not found."""
        with self._lock:
            record = self._limits.pop(pipeline_id, None)
            if record is None:
                return False
            self._stats["total_limits_removed"] += 1
            logger.info("limit_removed: id=%s pipeline_id=%s", record.limit_id, pipeline_id)
            detail = self._record_to_dict(record)

        self._fire("limit_removed", detail)
        return True

    # ------------------------------------------------------------------
    # List pipelines
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of pipeline IDs that have concurrency limits set."""
        with self._lock:
            return list(self._limits.keys())

    # ------------------------------------------------------------------
    # Utilization
    # ------------------------------------------------------------------

    def get_utilization(self, pipeline_id: str) -> float:
        """Return current_count / max_concurrent (0.0-1.0). Returns 0.0 if no limit."""
        with self._lock:
            record = self._limits.get(pipeline_id)
            if record is None:
                return 0.0
            if record.max_concurrent <= 0:
                return 0.0
            return len(record.active_executions) / record.max_concurrent

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("callback_registered: name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns ``True`` if removed."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("callback_removed: name=%s", name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        with self._lock:
            callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, details)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the limiter."""
        with self._lock:
            total_active = sum(
                len(r.active_executions) for r in self._limits.values()
            )
            total_capacity = sum(
                r.max_concurrent for r in self._limits.values()
            )
            return {
                **self._stats,
                "current_limits": len(self._limits),
                "max_entries": self._max_entries,
                "total_active_slots": total_active,
                "total_capacity": total_capacity,
                "overall_utilization": (
                    total_active / total_capacity if total_capacity > 0 else 0.0
                ),
                "registered_callbacks": len(self._callbacks),
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored limits, callbacks, and reset counters."""
        with self._lock:
            self._limits.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_concurrency_limiter_reset")
