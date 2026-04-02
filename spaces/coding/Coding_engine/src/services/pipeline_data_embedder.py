"""Service module for embedding pipeline data."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataEmbedderState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataEmbedder:
    """Embeds pipeline data into vector representations."""

    PREFIX = "pdem-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataEmbedderState()
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
            quarter = len(sorted_keys) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]

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

    def register_callback(self, name: str, cb: Callable) -> None:
        """Register a named callback."""
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def embed(self, pipeline_id: str, data_key: str, dimensions: int = 128, metadata: Optional[dict] = None) -> str:
        """Embed pipeline data and return the record ID."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "dimensions": dimensions,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("embedded", entry)
        return record_id

    def get_embedding(self, record_id: str) -> Optional[dict]:
        """Return the embedding record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_embeddings(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return embedding records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def get_embedding_count(self, pipeline_id: str = "") -> int:
        """Return the number of embeddings, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics about stored embeddings."""
        pipeline_ids = {e.get("pipeline_id", "") for e in self._state.entries.values()}
        return {
            "total_embeddings": len(self._state.entries),
            "unique_pipelines": len(pipeline_ids),
        }

    def reset(self) -> None:
        """Clear all embedding records, callbacks, and on_change."""
        self._state = PipelineDataEmbedderState()
        self._on_change = None
