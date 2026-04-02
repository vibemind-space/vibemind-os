from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepDeactivatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepDeactivator:
    PREFIX = "psda-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineStepDeactivatorState()
        self._on_change = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: object) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            cb(action, data)

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            entries,
            key=lambda rid: (entries[rid]["created_at"], entries[rid]["_seq"]),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for rid in sorted_ids[:to_remove]:
            del entries[rid]
        logger.info("Pruned %d deactivation entries", to_remove)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deactivate(
        self,
        pipeline_id: str,
        step_name: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""

        record_id = f"{self.PREFIX}{uuid.uuid4().hex[:12]}"
        self._state._seq += 1
        now = datetime.now(timezone.utc).isoformat()

        entry: dict = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "reason": reason,
            "metadata": metadata if metadata is not None else {},
            "created_at": now,
            "_seq": self._state._seq,
        }

        self._state.entries[record_id] = entry
        self._prune()
        self._fire("deactivate", record_id=record_id, pipeline_id=pipeline_id, step_name=step_name)
        logger.debug("Deactivated step %s in pipeline %s -> %s", step_name, pipeline_id, record_id)
        return record_id

    def get_deactivation(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_deactivations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_deactivation_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        entries = self._state.entries
        unique_pipelines = {e["pipeline_id"] for e in entries.values()}
        return {
            "total_deactivations": len(entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineStepDeactivatorState()
        self._on_change = None
        logger.info("PipelineStepDeactivator reset")
