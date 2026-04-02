from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepActivatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepActivator:
    PREFIX = "psat-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineStepActivatorState()
        self._on_change = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data: dict = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("_on_change callback failed for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("state callback failed for action=%s", action)

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries,
            key=lambda k: (entries[k].get("created_at", ""), entries[k].get("_seq", 0)),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for key in sorted_keys[:to_remove]:
            del entries[key]
        logger.debug("Pruned %d entries, %d remain", to_remove, len(entries))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(
        self,
        pipeline_id: str,
        step_name: str,
        mode: str = "immediate",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""

        self._state._seq += 1
        record_id = f"{self.PREFIX}{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()

        entry: dict = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "mode": mode,
            "metadata": metadata or {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("activate", record_id=record_id, pipeline_id=pipeline_id, step_name=step_name)
        logger.info("Activated step %s for pipeline %s -> %s", step_name, pipeline_id, record_id)
        return record_id

    def get_activation(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_activations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_activation_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        entries = self._state.entries.values()
        unique_pipelines = {e.get("pipeline_id") for e in entries}
        return {
            "total_activations": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineStepActivatorState()
        self._on_change = None
        logger.info("PipelineStepActivator reset")
