"""Service module for slicing pipeline data by selecting specific fields or ranges."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataSlicerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataSlicer:
    """Slices pipeline data by selecting specific fields or ranges."""

    PREFIX = "pdsl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataSlicerState()
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

    def slice_fields(self, data: dict, fields: List[str], label: str = "") -> str:
        """Extract only specified fields from *data* and return the slice ID."""
        slice_id = self._generate_id()
        sliced = {k: copy.deepcopy(v) for k, v in data.items() if k in fields}
        record: Dict[str, Any] = {
            "slice_id": slice_id,
            "label": label,
            "type": "fields",
            "fields": list(fields),
            "data": sliced,
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[slice_id] = record
        self._prune()
        self._fire("slice_fields", record)
        return slice_id

    def slice_range(self, data: list, start: int, end: int, label: str = "") -> str:
        """Extract a range from list *data* and return the slice ID."""
        slice_id = self._generate_id()
        sliced = copy.deepcopy(data[start:end])
        record: Dict[str, Any] = {
            "slice_id": slice_id,
            "label": label,
            "type": "range",
            "start": start,
            "end": end,
            "data": sliced,
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[slice_id] = record
        self._prune()
        self._fire("slice_range", record)
        return slice_id

    def get_slice(self, slice_id: str) -> Optional[dict]:
        """Return the slice record for *slice_id*, or ``None``."""
        entry = self._state.entries.get(slice_id)
        if entry is None:
            return None
        return dict(entry)

    def get_slices(self, label: str = "", limit: int = 50) -> List[dict]:
        """Return slice records, newest first, optionally filtered by *label*."""
        results = list(self._state.entries.values())
        if label:
            results = [r for r in results if r.get("label") == label]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def get_slice_count(self, label: str = "") -> int:
        """Return the number of slices, optionally filtered by *label*."""
        if not label:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("label") == label)

    def get_stats(self) -> dict:
        """Return summary statistics about stored slices."""
        labels = {e.get("label", "") for e in self._state.entries.values()}
        return {
            "total_slices": len(self._state.entries),
            "unique_labels": len(labels),
        }

    def reset(self) -> None:
        """Clear all slice records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
