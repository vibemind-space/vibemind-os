"""Pipeline step throttler - service for throttling pipeline steps.

Manages throttle records for pipeline steps, supports querying by pipeline,
collecting statistics, and automatic pruning when the store exceeds
*MAX_ENTRIES*.  Uses SHA-256-based IDs with a ``psth-`` prefix.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepThrottlerState:
    """Internal store for pipeline step throttler entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepThrottler:
    """Service for throttling pipeline steps.

    Supports creating, retrieving, and querying throttle records with automatic
    pruning when the store exceeds *MAX_ENTRIES*.
    """

    PREFIX = "psth-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepThrottlerState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict the oldest quarter of entries when the store exceeds *MAX_ENTRIES*."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("_seq", 0)),
        )
        remove_count = len(self._state.entries) // 4
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change and all registered callbacks; exceptions are silently ignored."""
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Throttle
    # ------------------------------------------------------------------

    def throttle(
        self,
        pipeline_id: str,
        step_name: str,
        max_rate: int = 100,
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a throttle record for a pipeline step.

        Returns the record ID (``psth-`` prefix), or ``""`` if inputs are invalid.
        """
        if not pipeline_id or not step_name:
            return ""

        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "max_rate": max_rate,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("throttle_created", entry)
        logger.debug(
            "Throttle created: %s for pipeline=%s step=%s max_rate=%d",
            record_id,
            pipeline_id,
            step_name,
            max_rate,
        )
        return record_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_throttle(self, record_id: str) -> Optional[dict]:
        """Get throttle by record ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_throttles(
        self,
        pipeline_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query throttles, optionally filtered by *pipeline_id*, newest first.

        Returns at most *limit* results as copies.
        """
        if pipeline_id:
            candidates = [
                e
                for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            ]
        else:
            candidates = list(self._state.entries.values())
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Count
    # ------------------------------------------------------------------

    def get_throttle_count(self, pipeline_id: str = "") -> int:
        """Return the number of stored throttles, optionally filtered by pipeline."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the throttler service."""
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return {
            "total_throttles": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored throttles and reset state."""
        self._state = PipelineStepThrottlerState()
        self._on_change = None
