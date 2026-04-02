"""Pipeline data transformer v2.

Transforms pipeline data entries with format and metadata support,
callback notifications, and sorted retrieval.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataTransformerV2State:
    """Internal state for PipelineDataTransformerV2."""
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataTransformerV2:
    """Transforms pipeline data with format and metadata tracking."""

    PREFIX = "pdtv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataTransformerV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.values(),
            key=lambda e: (e["created_at"], e["_seq"]),
        )
        to_remove = sorted_entries[: len(sorted_entries) // 4]
        for entry in to_remove:
            del self._state.entries[entry["record_id"]]
        logger.info("prune removed=%d remaining=%d", len(to_remove), len(self._state.entries))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change_error action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error action=%s", action)

    # ------------------------------------------------------------------
    # Transform CRUD
    # ------------------------------------------------------------------

    def transform_v2(
        self,
        pipeline_id: str,
        data_key: str,
        format: str = "json",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a transformation entry and return its record id.

        Returns empty string when *pipeline_id* or *data_key* is empty.
        """
        if not pipeline_id or not data_key:
            logger.warning(
                "transform_v2.invalid_args pipeline_id=%s data_key=%s",
                pipeline_id,
                data_key,
            )
            return ""

        self._prune()

        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "format": format,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        logger.info(
            "transformation_created record_id=%s pipeline_id=%s data_key=%s format=%s",
            record_id,
            pipeline_id,
            data_key,
            format,
        )
        self._fire(
            "transformation_created",
            record_id=record_id,
            pipeline_id=pipeline_id,
        )
        return record_id

    def get_transformation(self, record_id: str) -> Optional[dict]:
        """Return a deep copy of the transformation entry or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_transformations(
        self, pipeline_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Return transformation entries sorted by (created_at, _seq) descending.

        Optionally filtered by *pipeline_id*. At most *limit* entries.
        """
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_transformation_count(self, pipeline_id: str = "") -> int:
        """Return count of transformation entries, optionally filtered."""
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
            "total_transformations": len(self._state.entries),
            "unique_pipelines": len(pipeline_ids),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataTransformerV2State()
        self._on_change = None
        logger.info("pipeline_data_transformer_v2_reset")
