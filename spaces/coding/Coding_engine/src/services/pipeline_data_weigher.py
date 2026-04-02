"""Service module for weighing pipeline data entries."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataWeigherState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataWeigher:
    """Weighs pipeline data entries with configurable weights and metadata."""

    PREFIX = "pdwg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataWeigherState()
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
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(self._state.entries) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]

    # -- Callbacks -----------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, **detail)
            except Exception:
                logger.error("on_change callback error for action %s", action)
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, **detail)
            except Exception:
                logger.error("callback %s error for action %s", name, action)

    # -- Core operations -----------------------------------------------------

    def weigh(
        self,
        pipeline_id: str,
        data_key: str,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(data_key)
        record = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "weight": weight,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("weigh")
        return record_id

    def get_weight(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_weights(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return entries[:limit]

    def get_weight_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        pipelines = {e.get("pipeline_id") for e in self._state.entries.values()}
        return {
            "total_weights": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataWeigherState()
        self._on_change = None
