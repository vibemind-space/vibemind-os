from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepConsolidatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepConsolidator:
    PREFIX = "pscn-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepConsolidatorState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        digest = hashlib.sha256(str(self._state._seq).encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k]["_seq"],
            )
            remove_count = len(sorted_keys) // 4
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]
            logger.info("Pruned %d consolidation entries", remove_count)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._state.callbacks:
            del self._state.callbacks[callback_id]
            return True
        return False

    def _fire(self) -> None:
        if self._on_change is not None:
            self._on_change()
        for cb in list(self._state.callbacks.values()):
            cb()

    def consolidate(
        self,
        pipeline_id: str,
        step_name: str,
        target: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""

        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "target": target,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire()
        logger.debug("Consolidated step %s for pipeline %s -> %s", step_name, pipeline_id, record_id)
        return record_id

    def get_consolidation(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is not None:
            return deepcopy(entry)
        return None

    def get_consolidations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: e["_seq"], reverse=True)
        return [deepcopy(e) for e in entries[:limit]]

    def get_consolidation_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        unique_pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_consolidations": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineStepConsolidatorState()
        self._on_change = None
        logger.info("PipelineStepConsolidator reset")
