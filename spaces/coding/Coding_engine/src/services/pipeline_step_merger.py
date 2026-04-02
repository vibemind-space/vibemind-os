"""Service module for merging pipeline steps."""

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepMergerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepMerger:
    PREFIX = "psmg-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepMergerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:12]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            remove_count = len(sorted_keys) // 4
            for k in sorted_keys[:remove_count]:
                del self._state.entries[k]

    def _fire(self, action: str, data: Any):
        try:
            if self._on_change is not None:
                self._on_change(action, data)
        except Exception:
            logger.exception("on_change callback failed")
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Callback %s failed", name)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]):
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._state.callbacks.pop(name, None) is not None

    def merge(
        self,
        pipeline_id: str,
        step_a: str,
        step_b: str,
        merged_name: str,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_a or not step_b or not merged_name:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_a": step_a,
            "step_b": step_b,
            "merged_name": merged_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("merged", entry)
        return record_id

    def get_merge(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_merges(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    def get_merge_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        unique_pipelines = {
            e.get("pipeline_id") for e in self._state.entries.values()
        }
        return {
            "total_merges": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self):
        self._state = PipelineStepMergerState()
        self._on_change = None
