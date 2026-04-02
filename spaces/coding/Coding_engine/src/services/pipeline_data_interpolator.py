"""Service module for interpolating pipeline data records."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataInterpolatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataInterpolator:
    """Interpolates pipeline data records."""

    PREFIX = "pdin-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataInterpolatorState()
        self._on_change: Optional[Callable] = None

    # -- ID generation -------------------------------------------------------

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{key}{self._state._seq}{id(self)}{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

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

    def _fire(self, action: str) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    # -- Core methods --------------------------------------------------------

    def interpolate(
        self,
        pipeline_id: str,
        data_key: str,
        method: str = "linear",
        metadata: Optional[dict] = None,
    ) -> str:
        """Interpolate a data record and return the record ID."""
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(f"{pipeline_id}:{data_key}")
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "method": method,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("interpolate")
        return record_id

    def get_interpolation(self, record_id: str) -> Optional[dict]:
        """Return the interpolation record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_interpolations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return interpolation records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)), reverse=True
        )
        return [dict(r) for r in results[:limit]]

    def get_interpolation_count(self, pipeline_id: str = "") -> int:
        """Return the number of interpolations, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored interpolations."""
        unique_pipelines = {
            e.get("pipeline_id", "") for e in self._state.entries.values()
        }
        return {
            "total_interpolations": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Clear all interpolation records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset")
