"""Service module for coalescing pipeline data."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataCoalescerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataCoalescer:
    """Coalesces pipeline data from multiple keys into a single target key."""

    PREFIX = "pdcl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataCoalescerState()
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
            quarter = len(self._state.entries) // 4
            for key in sorted_keys[:quarter]:
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

    def coalesce(
        self,
        pipeline_id: str,
        data_keys: list,
        target_key: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Coalesce multiple data keys into a target key. Returns record_id or empty string."""
        if not pipeline_id or not data_keys or not target_key:
            return ""
        record_id = self._generate_id()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_keys": list(data_keys),
            "target_key": target_key,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("coalesced", entry)
        return record_id

    def get_coalescence(self, record_id: str) -> Optional[dict]:
        """Return a coalescence record by id, or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_coalescences(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return coalescence records, optionally filtered by pipeline_id, sorted newest first."""
        items = list(self._state.entries.values())
        if pipeline_id:
            items = [e for e in items if e.get("pipeline_id") == pipeline_id]
        items.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in items[:limit]]

    def get_coalescence_count(self, pipeline_id: str = "") -> int:
        """Return number of coalescence records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return statistics."""
        unique_pipelines = len(
            {e.get("pipeline_id") for e in self._state.entries.values()}
        )
        return {
            "total_coalescences": len(self._state.entries),
            "unique_pipelines": unique_pipelines,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataCoalescerState()
        self._on_change = None
