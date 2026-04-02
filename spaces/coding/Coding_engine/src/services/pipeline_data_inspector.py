"""Service module for inspecting pipeline data structure and types."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataInspectorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataInspector:
    """Inspects pipeline data structure and types."""

    PREFIX = "pdin-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataInspectorState()
        self._callbacks: Dict[str, Callable] = {}
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
        for name, cb in list(self._callbacks.items()):
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
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Helpers -------------------------------------------------------------

    def _analyze_structure(self, data: Any, depth: int = 0) -> Dict[str, Any]:
        """Recursively analyze data structure returning keys, types, and depth."""
        result: Dict[str, Any] = {
            "type": type(data).__name__,
            "depth": depth,
        }
        if isinstance(data, dict):
            result["keys"] = list(data.keys())
            result["key_count"] = len(data)
            result["children"] = {}
            for k, v in data.items():
                result["children"][k] = self._analyze_structure(v, depth + 1)
            child_depths = [
                result["children"][k].get("max_depth", depth + 1)
                for k in result["children"]
            ]
            result["max_depth"] = max(child_depths) if child_depths else depth
        elif isinstance(data, (list, tuple)):
            result["length"] = len(data)
            if data:
                result["element_types"] = list({type(e).__name__ for e in data})
                child_depths = [
                    self._analyze_structure(e, depth + 1).get("max_depth", depth + 1)
                    for e in data
                ]
                result["max_depth"] = max(child_depths) if child_depths else depth
            else:
                result["element_types"] = []
                result["max_depth"] = depth
        else:
            result["max_depth"] = depth
        return result

    # -- Core methods --------------------------------------------------------

    def inspect(self, data: dict, label: str = "") -> str:
        """Analyze data structure (keys, types, depth), store inspection record, return ID."""
        structure = self._analyze_structure(data)
        inspection_id = self._generate_id(f"{label}{time.time()}")
        record = {
            "inspection_id": inspection_id,
            "label": label,
            "structure": structure,
            "data": copy.deepcopy(data),
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[inspection_id] = record
        self._prune()
        self._fire("inspect", {"inspection_id": inspection_id, "label": label})
        return inspection_id

    def get_inspection(self, inspection_id: str) -> Optional[dict]:
        """Return a single inspection record by ID, or None if not found."""
        entry = self._state.entries.get(inspection_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_inspections(self, label: str = "", limit: int = 50) -> List[dict]:
        """Return inspection records, newest first. Filter by label if provided."""
        entries = list(self._state.entries.values())
        if label:
            entries = [e for e in entries if e.get("label") == label]
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_order", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_inspection_count(self, label: str = "") -> int:
        """Return the number of stored inspections, optionally filtered by label."""
        if not label:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("label") == label)

    def get_stats(self) -> dict:
        """Return statistics about inspections."""
        labels = {e.get("label", "") for e in self._state.entries.values()}
        return {
            "total_inspections": len(self._state.entries),
            "unique_labels": len(labels),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataInspectorState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
