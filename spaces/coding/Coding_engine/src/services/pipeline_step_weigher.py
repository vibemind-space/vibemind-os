"""Service module for assigning weights/priority scores to pipeline steps."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepWeigherState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepWeigher:
    """Assigns weights/priority scores to pipeline steps."""

    PREFIX = "pswg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepWeigherState()

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
        on_change = self._state.callbacks.get("__on_change__")
        if on_change is not None:
            try:
                on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            if name == "__on_change__":
                continue
            try:
                cb(action, data)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        if cb is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # -- Core methods --------------------------------------------------------

    def weigh(
        self,
        pipeline_id: str,
        step_name: str,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Assign a weight to a pipeline step and return the weight record ID."""
        record_id = self._generate_id()
        record: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "weight": weight,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("weigh", record)
        return record_id

    def get_weight(self, record_id: str) -> Optional[dict]:
        """Return the weight record for *record_id*, or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_weights(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Return weight records, newest first, optionally filtered by *pipeline_id*."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [r for r in results if r.get("pipeline_id") == pipeline_id]
        results.sort(
            key=lambda r: (r.get("created_at", 0), r.get("_seq", 0)),
            reverse=True,
        )
        return [dict(r) for r in results[:limit]]

    def get_weight_count(self, pipeline_id: str = "") -> int:
        """Return the number of weight records, optionally filtered by *pipeline_id*."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # -- Stats / reset -------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics about stored weight records."""
        all_pipelines = set()
        for e in self._state.entries.values():
            all_pipelines.add(e.get("pipeline_id", ""))
        return {
            "total_weights": len(self._state.entries),
            "unique_pipelines": len(all_pipelines) if self._state.entries else 0,
        }

    def reset(self) -> None:
        """Clear all weight records, callbacks, and on_change."""
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
