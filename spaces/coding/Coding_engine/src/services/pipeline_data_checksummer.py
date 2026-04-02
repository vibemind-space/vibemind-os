"""Service module for computing and storing checksums for pipeline data integrity."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataChecksummerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataChecksummer:
    """Compute and store checksums for pipeline data integrity."""

    PREFIX = "pdcs-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataChecksummerState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
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

    def _fire(self, event: str, data: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.error("on_change callback error for event %s", event)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.error("callback %s error for event %s", name, event)

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

    def checksum(
        self,
        pipeline_id: str,
        data_key: str,
        checksum_value: str,
        algorithm: str = "sha256",
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a checksum record for a pipeline data entry. Returns record_id."""
        record_id = self._generate_id(f"{pipeline_id}{data_key}")
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "checksum_value": checksum_value,
            "algorithm": algorithm,
            "metadata": metadata or {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("checksum", {"record_id": record_id, "pipeline_id": pipeline_id})
        return record_id

    def get_checksum(self, record_id: str) -> Optional[dict]:
        """Return a checksum record by id, or None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_checksums(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """List checksum records, newest first. Optionally filter by pipeline_id."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_checksum_count(self, pipeline_id: str = "") -> int:
        """Return count of checksum records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        """Return statistics."""
        pipelines = set()
        for e in self._state.entries.values():
            pipelines.add(e.get("pipeline_id", ""))
        return {
            "total_checksums": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataChecksummerState()
        self._on_change = None
        self._fire("reset", {})
