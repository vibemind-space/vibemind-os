"""Pipeline data aggregator v2.

Aggregates keyed data entries per pipeline with sum/avg/count/min/max methods,
callback notifications, and sorted retrieval.
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
class PipelineDataAggregatorV2State:
    """Internal state for PipelineDataAggregatorV2."""
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataAggregatorV2:
    """Aggregates keyed data per pipeline using configurable methods."""

    PREFIX = "pdav-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataAggregatorV2State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if *name* is already taken."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        data = {"action": action, **detail}
        self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error action=%s", action)

    def _on_change(self, action: str, data: Dict[str, Any]) -> None:
        logger.debug("on_change action=%s", action)

    # ------------------------------------------------------------------
    # Aggregation CRUD
    # ------------------------------------------------------------------

    def aggregate_v2(
        self,
        pipeline_id: str,
        data_key: str,
        method: str = "sum",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create an aggregation entry and return its record id.

        Returns empty string when *pipeline_id* or *data_key* is empty.
        """
        if not pipeline_id or not data_key:
            logger.warning(
                "aggregate_v2.invalid_args pipeline_id=%s data_key=%s",
                pipeline_id,
                data_key,
            )
            return ""

        if len(self._state.entries) >= self.MAX_ENTRIES:
            logger.warning("aggregate_v2.limit_reached")
            return ""

        record_id = self._next_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "method": method,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        logger.info(
            "aggregation_created record_id=%s pipeline_id=%s data_key=%s method=%s",
            record_id,
            pipeline_id,
            data_key,
            method,
        )
        self._fire(
            "aggregation_created",
            {"record_id": record_id, "pipeline_id": pipeline_id},
        )
        return record_id

    def get_aggregation(self, record_id: str) -> Optional[dict]:
        """Return a copy of the aggregation entry or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_aggregations(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Return aggregation entries sorted by (created_at, _seq) descending.

        Optionally filtered by *pipeline_id*. At most *limit* entries.
        """
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_aggregation_count(self, pipeline_id: str = "") -> int:
        """Return count of aggregation entries, optionally filtered."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        pipeline_ids = {
            e["pipeline_id"] for e in self._state.entries.values()
        }
        return {
            "total_aggregations": len(self._state.entries),
            "unique_pipelines": len(pipeline_ids),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("pipeline_data_aggregator_v2_reset")
