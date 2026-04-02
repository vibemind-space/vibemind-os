"""Service module for emergent autonomous pipeline data denormalization system."""

from __future__ import annotations

import hashlib
import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataDenormalizerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataDenormalizer:
    """Autonomous pipeline data denormalization service."""

    PREFIX = "pddn-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataDenormalizerState()
        self._on_change: Optional[Callable] = None

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            quarter = len(self._state.entries) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]
            logger.info("pruned_entries removed=%d", quarter)

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
                logger.exception("on_change_error action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error action=%s", action)

    # ── API ────────────────────────────────────────────────────────

    def denormalize(
        self,
        pipeline_id: str,
        data_key: str,
        strategy: str = "flatten",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a denormalization record. Returns record_id, or '' if empty."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(pipeline_id)
        record = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "strategy": strategy,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        logger.info("denormalization_added record_id=%s pipeline_id=%s", record_id, pipeline_id)
        self._fire("denormalize", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_denormalization(self, record_id: str) -> Optional[dict]:
        """Return a copy of a denormalization record, or None if not found."""
        rec = self._state.entries.get(record_id)
        if rec is None:
            return None
        return dict(rec)

    def get_denormalizations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return denormalization records sorted by _seq descending (newest first)."""
        if pipeline_id:
            items = [r for r in self._state.entries.values() if r["pipeline_id"] == pipeline_id]
        else:
            items = list(self._state.entries.values())
        items.sort(key=lambda r: r["_seq"], reverse=True)
        return [dict(r) for r in items[:limit]]

    def get_denormalization_count(self, pipeline_id: str = "") -> int:
        """Return the number of denormalization records, optionally scoped to a pipeline."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for r in self._state.entries.values() if r["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics about current denormalization state."""
        unique_pipelines = {r["pipeline_id"] for r in self._state.entries.values()}
        return {
            "total_denormalizations": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Clear all entries, reset sequence counter, and remove callbacks."""
        self._state = PipelineDataDenormalizerState()
        self._on_change = None
        logger.info("state_reset")
