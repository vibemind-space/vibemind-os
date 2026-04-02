from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataBatcherV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataBatcherV2:
    PREFIX = "pdbv-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineDataBatcherV2State()
        self._on_change: Optional[Callable] = _on_change

    def _generate_id(self) -> str:
        seq = self._state._seq
        self._state._seq += 1
        hash_val = hashlib.sha256(str(seq).encode()).hexdigest()
        return f"{self.PREFIX}{hash_val[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries,
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k]["_seq"],
            ),
        )
        quarter = len(sorted_keys) // 4
        if quarter < 1:
            quarter = 1
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]
        logger.info("Pruned %d entries", quarter)

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

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    def batch_v2(
        self,
        pipeline_id: str,
        data_key: str,
        size: int = 100,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "size": size,
            "metadata": deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq - 1,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("batch_v2", pipeline_id=pipeline_id, record_id=record_id)
        logger.debug("Batched %s for pipeline %s", record_id, pipeline_id)
        return record_id

    def get_batch(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_batches(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [deepcopy(e) for e in entries[:limit]]

    def get_batch_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_batches": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataBatcherV2State()
        self._on_change = None
        logger.info("PipelineDataBatcherV2 reset")
