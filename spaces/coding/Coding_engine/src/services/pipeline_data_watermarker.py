"""Service module for applying watermarks to pipeline data for provenance tracking."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataWatermarkerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataWatermarker:
    """Applies watermarks to pipeline data for provenance tracking."""

    PREFIX = "pdwm-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataWatermarkerState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        self._state._seq += 1
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{digest}"

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            remove_count = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def watermark(
        self,
        pipeline_id: str,
        data_key: str,
        watermark_value: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Apply a watermark to pipeline data and return the record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "watermark_value": watermark_value,
            "metadata": dict(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("watermark", record)
        return record_id

    def get_watermark(self, record_id: str) -> Optional[dict]:
        """Return the watermark record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_watermarks(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return watermark records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)), reverse=True
        )
        return [dict(r) for r in results[:limit]]

    def get_watermark_count(self, pipeline_id: str = "") -> int:
        """Return the number of watermark records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored watermark records."""
        all_pipelines = set()
        for e in self._state.entries.values():
            all_pipelines.add(e.get("pipeline_id", ""))
        return {
            "total_watermarks": len(self._state.entries),
            "unique_pipelines": len(all_pipelines),
        }

    def reset(self) -> None:
        """Clear all watermark records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
