"""Service module for streaming pipeline data in chunks for processing."""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataStreamerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataStreamer:
    """Streams pipeline data in chunks for processing."""

    PREFIX = "pdst-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataStreamerState()
        self._callbacks: Dict[str, Callable] = {}
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
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    # -- Callbacks -----------------------------------------------------------

    def _fire(self, action: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._callbacks.items()):
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
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def create_stream(
        self, pipeline_id: str, data: list, chunk_size: int = 10, label: str = ""
    ) -> str:
        """Create a stream from *data* list, returns stream ID."""
        stream_id = self._generate_id()
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunks.append(copy.deepcopy(data[i : i + chunk_size]))
        record: Dict[str, Any] = {
            "stream_id": stream_id,
            "pipeline_id": pipeline_id,
            "label": label,
            "chunks": chunks,
            "total_chunks": len(chunks),
            "cursor": 0,
            "chunks_delivered": 0,
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[stream_id] = record
        self._prune()
        self._fire("create_stream", copy.deepcopy(record))
        return stream_id

    def get_next_chunk(self, stream_id: str) -> Optional[list]:
        """Get next chunk and advance cursor. Returns None if stream not found or complete."""
        entry = self._state.entries.get(stream_id)
        if entry is None:
            return None
        cursor = entry["cursor"]
        if cursor >= entry["total_chunks"]:
            return None
        chunk = copy.deepcopy(entry["chunks"][cursor])
        entry["cursor"] = cursor + 1
        entry["chunks_delivered"] += 1
        self._fire("get_next_chunk", {"stream_id": stream_id, "chunk_index": cursor})
        return chunk

    def get_stream(self, stream_id: str) -> Optional[dict]:
        """Return the stream record for *stream_id*, or ``None``."""
        entry = self._state.entries.get(stream_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_streams(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return stream records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True
        )
        return [copy.deepcopy(r) for r in results[:limit]]

    def get_stream_count(self, pipeline_id: str = "") -> int:
        """Return the number of streams, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def is_complete(self, stream_id: str) -> bool:
        """Return True if the stream has delivered all chunks."""
        entry = self._state.entries.get(stream_id)
        if entry is None:
            return False
        return entry["cursor"] >= entry["total_chunks"]

    def get_stats(self) -> dict:
        """Return summary statistics about streams."""
        total = len(self._state.entries)
        completed = sum(
            1
            for e in self._state.entries.values()
            if e["cursor"] >= e["total_chunks"]
        )
        total_chunks_delivered = sum(
            e.get("chunks_delivered", 0) for e in self._state.entries.values()
        )
        return {
            "total_streams": total,
            "completed_streams": completed,
            "total_chunks_delivered": total_chunks_delivered,
        }

    def reset(self) -> None:
        """Clear all stream records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
