"""Pipeline Completion Tracker – tracks pipeline completion status and completion time.

Monitors pipeline lifecycle from start through individual step completion to
final success or failure. Records elapsed time, step progress, and notifies
registered callbacks on state changes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _TrackingEntry:
    tracking_id: str
    pipeline_id: str
    status: str  # tracking, complete, failed
    expected_steps: int
    steps_done: List[str]
    reason: str
    created_at: float
    seq: int


class PipelineCompletionTracker:
    """Tracks pipeline completion status and completion time."""

    STATUSES = ("tracking", "complete", "failed")

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _TrackingEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._max_entries = max_entries

        # stats
        self._total_started = 0
        self._total_completed = 0
        self._total_failed = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return "pct2-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._entries) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._entries,
            key=lambda tid: self._entries[tid].created_at,
        )
        while len(self._entries) > self._max_entries and sorted_ids:
            tid = sorted_ids.pop(0)
            self._entries.pop(tid, None)
        logger.debug("pruned_entries", remaining=len(self._entries))

    # ------------------------------------------------------------------
    # Tracking lifecycle
    # ------------------------------------------------------------------

    def start_tracking(self, pipeline_id: str, expected_steps: int = 0) -> str:
        """Begin tracking a pipeline. Returns tracking ID."""
        if not pipeline_id:
            return ""

        self._prune_if_needed()

        tid = self._make_id(pipeline_id)
        now = time.time()
        entry = _TrackingEntry(
            tracking_id=tid,
            pipeline_id=pipeline_id,
            status="tracking",
            expected_steps=max(expected_steps, 0),
            steps_done=[],
            reason="",
            created_at=now,
            seq=self._seq,
        )
        self._entries[tid] = entry
        self._total_started += 1

        logger.info("tracking_started", tracking_id=tid, pipeline_id=pipeline_id)
        self._fire("tracking_started", {
            "tracking_id": tid,
            "pipeline_id": pipeline_id,
            "expected_steps": entry.expected_steps,
        })
        return tid

    def mark_step_done(self, tracking_id: str, step_name: str) -> bool:
        """Record a step as completed. Returns True on success."""
        entry = self._entries.get(tracking_id)
        if not entry:
            logger.warning("mark_step_unknown_tracking", tracking_id=tracking_id)
            return False
        if entry.status != "tracking":
            logger.warning(
                "mark_step_not_tracking",
                tracking_id=tracking_id,
                status=entry.status,
            )
            return False
        if not step_name:
            return False

        entry.steps_done.append(step_name)

        logger.info(
            "step_done",
            tracking_id=tracking_id,
            step_name=step_name,
            steps_done=len(entry.steps_done),
            expected=entry.expected_steps,
        )
        self._fire("step_done", {
            "tracking_id": tracking_id,
            "pipeline_id": entry.pipeline_id,
            "step_name": step_name,
            "steps_done": len(entry.steps_done),
            "expected_steps": entry.expected_steps,
        })
        return True

    def mark_complete(self, tracking_id: str) -> bool:
        """Mark a pipeline as successfully completed. Returns True on success."""
        entry = self._entries.get(tracking_id)
        if not entry:
            logger.warning("mark_complete_unknown", tracking_id=tracking_id)
            return False
        if entry.status != "tracking":
            logger.warning(
                "mark_complete_not_tracking",
                tracking_id=tracking_id,
                status=entry.status,
            )
            return False

        entry.status = "complete"
        elapsed = time.time() - entry.created_at
        self._total_completed += 1

        logger.info(
            "pipeline_completed",
            tracking_id=tracking_id,
            pipeline_id=entry.pipeline_id,
            elapsed_s=round(elapsed, 3),
            steps_done=len(entry.steps_done),
        )
        self._fire("pipeline_completed", {
            "tracking_id": tracking_id,
            "pipeline_id": entry.pipeline_id,
            "elapsed": elapsed,
            "steps_done": len(entry.steps_done),
        })
        return True

    def mark_failed(self, tracking_id: str, reason: str = "") -> bool:
        """Mark a pipeline as failed. Returns True on success."""
        entry = self._entries.get(tracking_id)
        if not entry:
            logger.warning("mark_failed_unknown", tracking_id=tracking_id)
            return False
        if entry.status != "tracking":
            logger.warning(
                "mark_failed_not_tracking",
                tracking_id=tracking_id,
                status=entry.status,
            )
            return False

        entry.status = "failed"
        entry.reason = reason
        elapsed = time.time() - entry.created_at
        self._total_failed += 1

        logger.info(
            "pipeline_failed",
            tracking_id=tracking_id,
            pipeline_id=entry.pipeline_id,
            reason=reason,
            elapsed_s=round(elapsed, 3),
        )
        self._fire("pipeline_failed", {
            "tracking_id": tracking_id,
            "pipeline_id": entry.pipeline_id,
            "reason": reason,
            "elapsed": elapsed,
        })
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_status(self, tracking_id: str) -> Optional[Dict[str, Any]]:
        """Return status dict for a tracking entry, or None if not found."""
        entry = self._entries.get(tracking_id)
        if not entry:
            return None

        elapsed = time.time() - entry.created_at
        return {
            "pipeline_id": entry.pipeline_id,
            "status": entry.status,
            "steps_done": len(entry.steps_done),
            "expected_steps": entry.expected_steps,
            "elapsed": round(elapsed, 3),
        }

    def is_complete(self, tracking_id: str) -> bool:
        """Check whether the tracked pipeline has completed successfully."""
        entry = self._entries.get(tracking_id)
        if not entry:
            return False
        return entry.status == "complete"

    def list_pipelines(self) -> List[str]:
        """Return all unique pipeline IDs being tracked."""
        return list({e.pipeline_id for e in self._entries.values()})

    def get_tracking_count(self) -> int:
        """Return the number of tracked entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "current_entries": len(self._entries),
            "total_started": self._total_started,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_started = 0
        self._total_completed = 0
        self._total_failed = 0
        logger.info("tracker_reset")
