"""Service module for pipeline data deduplication tracking."""

from __future__ import annotations

import hashlib
import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataDeduperState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataDeduper:
    """Track and manage pipeline data deduplication records."""

    PREFIX = "pddd-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataDeduperState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + digest[:12]

    # -- Pruning -------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            to_remove = len(self._state.entries) // 4
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    # -- Change callback -----------------------------------------------------

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
                logger.exception("on_change error action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback error action=%s", action)

    # -- API -----------------------------------------------------------------

    def dedupe(
        self,
        pipeline_id: str,
        data_key: str,
        strategy: str = "exact",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a deduplication record. Returns record_id or '' on bad input."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(pipeline_id)
        record = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "strategy": strategy,
            "metadata": deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        logger.info("dedupe created record_id=%s pipeline_id=%s", record_id, pipeline_id)
        self._prune()
        self._fire("dedupe", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_dedupe(self, record_id: str) -> Optional[dict]:
        """Return a copy of a deduplication record, or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_dedupes(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return deduplication records sorted by (created_at, _seq) descending."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_dedupe_count(self, pipeline_id: str = "") -> int:
        """Return count of deduplication records, optionally filtered by pipeline."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics."""
        pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_dedupes": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataDeduperState()
        self._on_change = None
