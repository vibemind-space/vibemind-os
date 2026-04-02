from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataCompactorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataCompactor:
    PREFIX = "pdco-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataCompactorState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k]["_seq"],
            ),
        )
        remove_count = len(sorted_keys) // 4
        for k in sorted_keys[:remove_count]:
            del self._state.entries[k]

    def _fire(self, action: str, data: dict) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback %s error", name)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def compact(
        self,
        pipeline_id: str,
        data_key: str,
        strategy: str = "merge",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "strategy": strategy,
            "metadata": copy.deepcopy(metadata) if metadata else None,
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("compacted", entry)
        return record_id

    def get_compaction(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_compactions(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        if pipeline_id:
            items = [
                e
                for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            ]
        else:
            items = list(self._state.entries.values())
        items.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in items[:limit]]

    def get_compaction_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_compactions": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
