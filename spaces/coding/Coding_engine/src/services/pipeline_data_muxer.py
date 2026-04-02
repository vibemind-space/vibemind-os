from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataMuxerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataMuxer:
    PREFIX = "pdmx-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineDataMuxerState()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{h[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries,
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        quarter = len(sorted_keys) // 4
        for k in sorted_keys[:quarter]:
            del self._state.entries[k]
        logger.debug("Pruned %d entries", quarter)

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def register_callback(self, name: str, cb: Callable) -> None:
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Fire
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data: Dict[str, Any] = {"action": action, **detail}
        try:
            if self._on_change:
                self._on_change(action, data)
        except Exception:
            logger.exception("_on_change callback failed for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Registered callback failed for action=%s", action)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def mux(
        self,
        pipeline_id: str,
        data_key: str,
        channels: int = 2,
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""

        record_id = self._generate_id()
        now = time.time()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "channels": channels,
            "metadata": copy.deepcopy(metadata) if metadata else None,
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("mux", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_mux(self, record_id: str) -> Optional[dict]:
        return self._state.entries.get(record_id)

    def get_muxes(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return entries[:limit]

    def get_mux_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> Dict[str, Any]:
        pipelines = {
            e.get("pipeline_id") for e in self._state.entries.values()
        }
        return {
            "total_muxes": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataMuxerState()
        self._on_change = None
