"""Pipeline step delayer - delays pipeline steps."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepDelayerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepDelayer:
    """Delays pipeline steps with configurable delay seconds."""

    PREFIX = "psdl-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepDelayerState()
        self._on_change = None
        logger.info("PipelineStepDelayer initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def delay(self, pipeline_id: str, step_name: str, delay_seconds: float = 0, metadata: Any = None) -> str:
        if not pipeline_id or not step_name:
            return ""
        record_id = self._generate_id(f"{pipeline_id}{step_name}")
        now = time.time()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "delay_seconds": delay_seconds,
            "metadata": copy.deepcopy(metadata),
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("delayed", entry)
        logger.info("Delayed step '%s' in pipeline '%s' by %.2fs", step_name, pipeline_id, delay_seconds)
        return record_id

    def get_delay(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_delays(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return results[:limit]

    def get_delay_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        unique_pipelines = set(e["pipeline_id"] for e in self._state.entries.values())
        return {
            "total_delays": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self):
        self._state = PipelineStepDelayerState()
        self._on_change = None
        logger.info("PipelineStepDelayer reset")
