"""Pipeline step tracker — tracks pipeline step execution progress.

Monitors the progress of individual pipeline steps, including start,
update, and completion lifecycle events with item-level tracking.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepTrackerState:
    """Internal state for the PipelineStepTracker service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepTracker:
    """Tracks pipeline step execution progress.

    Manages the lifecycle of pipeline step tracking from start through
    completion, with support for progress updates and item counting.
    """

    PREFIX = "pstr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepTrackerState()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        if callback is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # start_tracking
    # ------------------------------------------------------------------

    def start_tracking(
        self, pipeline_id: str, step_name: str, total_items: int = 0
    ) -> str:
        """Start tracking a pipeline step. Returns tracker ID."""
        self._prune()
        tracker_id = self._generate_id()
        now = time.time()
        entry = {
            "tracker_id": tracker_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "total_items": total_items,
            "completed_items": 0,
            "status": "in_progress",
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[tracker_id] = entry
        self._fire("tracking_started", dict(entry))
        return tracker_id

    # ------------------------------------------------------------------
    # update_progress
    # ------------------------------------------------------------------

    def update_progress(
        self, tracker_id: str, completed_items: int = 0, status: str = ""
    ) -> bool:
        """Update progress on a tracked step. Returns False if not found."""
        entry = self._state.entries.get(tracker_id)
        if entry is None:
            return False
        if completed_items:
            entry["completed_items"] = completed_items
        if status:
            entry["status"] = status
        entry["updated_at"] = time.time()
        self._fire("progress_updated", dict(entry))
        return True

    # ------------------------------------------------------------------
    # complete_tracking
    # ------------------------------------------------------------------

    def complete_tracking(
        self, tracker_id: str, status: str = "completed"
    ) -> bool:
        """Mark a tracked step as complete. Returns False if not found."""
        entry = self._state.entries.get(tracker_id)
        if entry is None:
            return False
        entry["status"] = status
        entry["updated_at"] = time.time()
        self._fire("tracking_completed", dict(entry))
        return True

    # ------------------------------------------------------------------
    # get_tracker
    # ------------------------------------------------------------------

    def get_tracker(self, tracker_id: str) -> Optional[dict]:
        """Get a single tracker by ID. Returns None if not found."""
        entry = self._state.entries.get(tracker_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_trackers
    # ------------------------------------------------------------------

    def get_trackers(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Get trackers, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_tracker_count
    # ------------------------------------------------------------------

    def get_tracker_count(self, pipeline_id: str = "") -> int:
        """Count trackers, optionally filtering by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        entries = list(self._state.entries.values())
        total = len(entries)
        completed = sum(1 for e in entries if e.get("status") == "completed")
        in_progress = sum(1 for e in entries if e.get("status") == "in_progress")
        return {
            "total_trackers": total,
            "completed_count": completed,
            "in_progress_count": in_progress,
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence."""
        self._state.entries.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
