"""Service module for segmenting pipeline data."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class PipelineDataSegmenterState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataSegmenter:
    """Service for segmenting pipeline data."""

    PREFIX = "pdsg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataSegmenterState()
        self._on_change: Optional[Callable] = None

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(self._state.entries) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]
            logger.info("pruned_segments, removed=%d", quarter)

    # ── Callbacks ──────────────────────────────────────────────────

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

    def _fire(self, action: str, **detail: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, detail)
            except Exception:
                logger.exception("on_change callback error, action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error, action=%s", action)

    # ── API ────────────────────────────────────────────────────────

    def segment(
        self,
        pipeline_id: str,
        data_key: str,
        segment_count: int = 2,
        metadata: Optional[dict] = None,
    ) -> str:
        """Segment pipeline data and return the record_id."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(pipeline_id)
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "segment_count": segment_count,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._prune()
        logger.info("segment_created, record_id=%s, pipeline_id=%s", record_id, pipeline_id)
        self._fire("segment", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_segment(self, record_id: str) -> Optional[dict]:
        """Return a copy of a segment record or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_segments(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return segments sorted by (created_at, _seq) descending."""
        if pipeline_id:
            items = [
                e for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            ]
        else:
            items = list(self._state.entries.values())
        items.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return items[:limit]

    def get_segment_count(self, pipeline_id: str = "") -> int:
        """Return the number of segments, optionally filtered by pipeline."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total = len(self._state.entries)
        unique_pipelines = len({e["pipeline_id"] for e in self._state.entries.values()})
        return {
            "total_segments": total,
            "unique_pipelines": unique_pipelines,
        }

    def reset(self) -> None:
        """Reset to fresh state and clear on_change."""
        self._state = PipelineDataSegmenterState()
        self._on_change = None
        logger.info("state_reset")
