"""Service module for deep cloning pipeline data with tracking."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataClonerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataCloner:
    """Deep clones pipeline data with tracking and retrieval."""

    PREFIX = "pdcl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataClonerState()
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

    def clone(self, data: dict, label: str = "", metadata: dict = None) -> str:
        """Deep copy *data*, store a clone record, and return the clone ID."""
        clone_id = self._generate_id()
        cloned_data = copy.deepcopy(data)
        record: Dict[str, Any] = {
            "clone_id": clone_id,
            "label": label,
            "data": cloned_data,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[clone_id] = record
        self._prune()
        self._fire("clone", record)
        return clone_id

    def get_clone(self, clone_id: str) -> Optional[dict]:
        """Return the clone record for *clone_id*, or ``None``."""
        entry = self._state.entries.get(clone_id)
        if entry is None:
            return None
        return dict(entry)

    def get_clones(self, label: str = "", limit: int = 50) -> List[dict]:
        """Return clone records, newest first, optionally filtered by *label*."""
        results = list(self._state.entries.values())
        if label:
            results = [r for r in results if r.get("label") == label]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def retrieve_data(self, clone_id: str) -> Optional[dict]:
        """Return a deep copy of the cloned data for *clone_id*, or ``None``."""
        entry = self._state.entries.get(clone_id)
        if entry is None:
            return None
        return copy.deepcopy(entry.get("data"))

    def get_clone_count(self, label: str = "") -> int:
        """Return the number of clones, optionally filtered by *label*."""
        if not label:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("label") == label)

    def get_stats(self) -> dict:
        """Return summary statistics about stored clones."""
        labels = {e.get("label", "") for e in self._state.entries.values()}
        return {
            "total_clones": len(self._state.entries),
            "unique_labels": len(labels),
        }

    def reset(self) -> None:
        """Clear all clone records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
