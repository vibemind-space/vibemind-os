from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataPreviewerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataPreviewer:
    PREFIX = "pdpv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataPreviewerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        digest = hashlib.sha256(f"{key}-{self._state._seq}".encode()).hexdigest()
        return self.PREFIX + digest[:12]

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                entries,
                key=lambda k: (entries[k]["created_at"], entries[k]["_seq"]),
            )
            to_remove = len(entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del entries[k]

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

    def _fire(self, action: str, **detail: object) -> None:
        payload = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(payload)
        for cb in list(self._state.callbacks.values()):
            cb(payload)

    def preview(
        self,
        pipeline_id: str,
        data_key: str,
        format: str = "json",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id(f"{pipeline_id}:{data_key}")
        record = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "format": format,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("preview", record_id=record_id)
        return record_id

    def get_preview(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_previews(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_preview_count(self, pipeline_id: str = "") -> int:
        if pipeline_id:
            return sum(
                1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        entries = self._state.entries.values()
        unique_pipelines = {e["pipeline_id"] for e in entries}
        return {
            "total_previews": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataPreviewerState()
        self._on_change = None
