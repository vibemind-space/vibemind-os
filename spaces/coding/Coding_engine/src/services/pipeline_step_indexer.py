"""Service module for indexing pipeline steps."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepIndexerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepIndexer:
    """Indexes pipeline steps for efficient lookup."""

    PREFIX = "psix-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepIndexerState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
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
            quarter = len(sorted_keys) // 4
            if quarter < 1:
                quarter = 1
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]

    # -- Callbacks -----------------------------------------------------------

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
                self._on_change(action, **detail)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, **detail)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    # -- Core methods --------------------------------------------------------

    def index(
        self,
        pipeline_id: str,
        step_name: str,
        index_type: str = "primary",
        metadata: Optional[dict] = None,
    ) -> str:
        """Index a pipeline step and return the record ID."""
        if not pipeline_id or not step_name:
            return ""
        record_id = self._generate_id()
        now = time.time()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "index_type": index_type,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("index", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_index(self, record_id: str) -> Optional[dict]:
        """Return the index record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_indexes(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return index records, newest first, optionally filtered."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)), reverse=True
        )
        return [dict(r) for r in results[:limit]]

    def get_index_count(self, pipeline_id: str = "") -> int:
        """Return the number of indexes, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored indexes."""
        pipelines = {e.get("pipeline_id", "") for e in self._state.entries.values()}
        return {
            "total_indexes": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        """Clear all index records, callbacks, and on_change."""
        self._state = PipelineStepIndexerState()
        self._on_change = None
