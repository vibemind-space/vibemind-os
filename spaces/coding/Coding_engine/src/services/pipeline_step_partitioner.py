from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepPartitionerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepPartitioner:
    PREFIX = "pspt-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineStepPartitionerState()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------ ids
    def _generate_id(self) -> str:
        self._state._seq += 1
        hash_input = str(self._state._seq).encode()
        h = hashlib.sha256(hash_input).hexdigest()
        return f"{self.PREFIX}{h[:12]}"

    # --------------------------------------------------------------- prune
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
        remove_count = len(sorted_keys) // 4
        for k in sorted_keys[:remove_count]:
            del self._state.entries[k]
        logger.info("Pruned %d entries", remove_count)

    # ----------------------------------------------------------- on_change
    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    # ----------------------------------------------------------- callbacks
    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # -------------------------------------------------------------- _fire
    def _fire(self, action: str, **detail: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, **detail)
            except Exception:
                logger.exception("on_change callback error")
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, **detail)
            except Exception:
                logger.exception("Callback %s error", cb_name)

    # ----------------------------------------------------------- partition
    def partition(
        self,
        pipeline_id: str,
        step_name: str,
        partitions: int = 1,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""

        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "partitions": partitions,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("partition", record_id=record_id, pipeline_id=pipeline_id)
        logger.debug("Created partition %s for pipeline %s", record_id, pipeline_id)
        return record_id

    # ------------------------------------------------------- get_partition
    def get_partition(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------ get_partitions
    def get_partitions(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------- get_partition_count
    def get_partition_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    # ----------------------------------------------------------- get_stats
    def get_stats(self) -> dict:
        unique = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_partitions": len(self._state.entries),
            "unique_pipelines": len(unique),
        }

    # -------------------------------------------------------------- reset
    def reset(self) -> None:
        self._state = PipelineStepPartitionerState()
        self._on_change = None
        logger.info("PipelineStepPartitioner reset")
