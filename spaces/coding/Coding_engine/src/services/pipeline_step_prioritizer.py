"""Service module for assigning priorities to pipeline steps for execution ordering."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepPrioritizerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class PipelineStepPrioritizer:
    """Assigns priorities to pipeline steps for execution ordering."""

    PREFIX = "pspr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepPrioritizerState()
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
            quarter = len(self._state.entries) // 4
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

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

    def set_priority(
        self,
        pipeline_id: str,
        step_name: str,
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Assign a priority to a pipeline step and return the priority record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "priority": priority,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("set_priority", record)
        return record_id

    def get_priority(self, record_id: str) -> Optional[dict]:
        """Return the priority record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_priorities(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return priority records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)),
            reverse=True,
        )
        return [dict(r) for r in results[:limit]]

    def get_priority_count(self, pipeline_id: str = "") -> int:
        """Return the number of priority records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # -- Stats / reset -------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics about stored priority records."""
        all_pipelines = set()
        all_steps = set()
        for e in self._state.entries.values():
            all_pipelines.add(e.get("pipeline_id", ""))
            all_steps.add((e.get("pipeline_id", ""), e.get("step_name", "")))
        return {
            "total_records": len(self._state.entries),
            "unique_pipelines": len(all_pipelines) if self._state.entries else 0,
            "unique_steps": len(all_steps) if self._state.entries else 0,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all priority records, callbacks, and on_change."""
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
