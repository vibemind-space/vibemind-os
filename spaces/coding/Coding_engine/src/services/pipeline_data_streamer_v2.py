"""Pipeline data streamer v2 service."""

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataStreamerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataStreamerV2:
    PREFIX = "pdsv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataStreamerV2State()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            remove_count = len(self._state.entries) // 4
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]

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

    def _fire(self, action: str, **detail) -> None:
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

    def stream_v2(
        self,
        pipeline_id: str,
        data_key: str,
        mode: str = "continuous",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "mode": mode,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("stream_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

    def get_stream(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is not None:
            return copy.deepcopy(entry)
        return None

    def get_streams(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e["pipeline_id"] == pipeline_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_stream_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id
        )

    def get_stats(self) -> dict:
        unique_pipelines = {
            e["pipeline_id"] for e in self._state.entries.values()
        }
        return {
            "total_streams": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataStreamerV2State()
        self._on_change = None
