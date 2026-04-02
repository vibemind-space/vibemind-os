from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepVersionerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepVersioner:
    PREFIX = "psvn-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepVersionerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        return f"{self.PREFIX}{uuid.uuid4().hex[:12]}"

    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = min(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, event: str) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event)
            except Exception:
                logger.exception("on_change callback error")
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(event)
            except Exception:
                logger.exception("Callback %s error", cb_name)

    def version(
        self,
        pipeline_id: str,
        step_name: str,
        version_tag: str = "v1",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not step_name:
            return ""
        self._state._seq += 1
        record_id = self._generate_id()
        record = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "version_tag": version_tag,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("version")
        return record_id

    def get_version(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_versions(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        items = list(self._state.entries.values())
        if pipeline_id:
            items = [e for e in items if e["pipeline_id"] == pipeline_id]
        items.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [deepcopy(e) for e in items[:limit]]

    def get_version_count(self, pipeline_id: str = "") -> int:
        if pipeline_id:
            return sum(
                1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        pipelines = {e["pipeline_id"] for e in self._state.entries.values()}
        return {
            "total_versions": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineStepVersionerState()
        self._on_change = None
