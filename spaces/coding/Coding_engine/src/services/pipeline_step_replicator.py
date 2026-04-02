from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepReplicatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepReplicator:
    PREFIX = "psrp-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineStepReplicatorState()
        self._on_change = _on_change

    # ------------------------------------------------------------------
    def _fire(self, action: str, detail: dict) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            cb(action, data)

    # ------------------------------------------------------------------
    def replicate(
        self,
        pipeline_id: str,
        step_name: str,
        replicas: int = 1,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""

        # Prune oldest entries when at capacity
        while len(self._state.entries) >= self.MAX_ENTRIES:
            oldest_key = min(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

        self._state._seq += 1
        record_id = f"{self.PREFIX}{uuid.uuid4().hex[:12]}"
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "replicas": replicas,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        logger.info("Replicated step %s for pipeline %s -> %s", step_name, pipeline_id, record_id)
        self._fire("replicate", {"record_id": record_id, "pipeline_id": pipeline_id})
        return record_id

    # ------------------------------------------------------------------
    def get_replication(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    def get_replications(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        items = list(self._state.entries.values())
        if pipeline_id:
            items = [e for e in items if e["pipeline_id"] == pipeline_id]
        items.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in items[:limit]]

    # ------------------------------------------------------------------
    def get_replication_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_replications": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._state = PipelineStepReplicatorState()
        self._on_change = None
        logger.info("PipelineStepReplicator reset")
