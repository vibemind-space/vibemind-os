"""Service module for binding pipeline data fields to named variables."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataBinderState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataBinder:
    """Binds pipeline data fields to named variables for downstream steps."""

    PREFIX = "pdbi-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataBinderState()
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
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_order", 0),
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

    def register_callback(self, name: str, cb: Callable) -> None:
        """Register a named callback."""
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def bind(self, pipeline_id: str, field_name: str, value: Any, metadata: Optional[dict] = None) -> str:
        """Bind a pipeline data field to a named variable and return the binding ID."""
        binding_id = self._generate_id()
        entry: Dict[str, Any] = {
            "binding_id": binding_id,
            "pipeline_id": pipeline_id,
            "field_name": field_name,
            "value": value,
            "metadata": metadata if metadata is not None else {},
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[binding_id] = entry
        self._prune()
        self._fire("bind", entry)
        return binding_id

    def get_binding(self, binding_id: str) -> Optional[dict]:
        """Return the binding record for *binding_id*, or ``None``."""
        entry = self._state.entries.get(binding_id)
        if entry is None:
            return None
        return dict(entry)

    def get_bindings(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return binding records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(key=lambda r: (r.get("created_at", 0), r.get("_order", 0)), reverse=True)
        return [dict(r) for r in results[:limit]]

    def get_binding_count(self, pipeline_id: str = "") -> int:
        """Return the number of bindings, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics about stored bindings."""
        pipeline_ids = {e.get("pipeline_id", "") for e in self._state.entries.values()}
        field_names = {e.get("field_name", "") for e in self._state.entries.values()}
        return {
            "total_bindings": len(self._state.entries),
            "unique_pipelines": len(pipeline_ids),
            "unique_fields": len(field_names),
        }

    def reset(self) -> None:
        """Clear all binding records, callbacks, and on_change."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
        self._fire("reset", {})
