"""Service module for renaming pipeline data fields."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataRenamerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineDataRenamer:
    """Renames pipeline data fields."""

    PREFIX = "pdrn-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataRenamerState()
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
            if quarter < 1:
                quarter = 1
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

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def rename(
        self,
        pipeline_id: str,
        old_name: str,
        new_name: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a rename operation and return the rename record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "old_name": old_name,
            "new_name": new_name,
            "metadata": dict(metadata) if metadata else {},
            "created_at": time.time(),
            "_order": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("rename", record)
        return record_id

    def get_rename(self, record_id: str) -> Optional[dict]:
        """Return the rename record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_renames(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return rename records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_order", 0)),
            reverse=True,
        )
        return [dict(r) for r in results[:limit]]

    def get_rename_count(self, pipeline_id: str = "") -> int:
        """Return the number of rename records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics about stored rename records."""
        all_pipelines = set()
        for e in self._state.entries.values():
            all_pipelines.add(e.get("pipeline_id", ""))
        return {
            "total_records": len(self._state.entries),
            "unique_pipelines": len(all_pipelines),
        }

    def reset(self) -> None:
        """Clear all rename records."""
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
