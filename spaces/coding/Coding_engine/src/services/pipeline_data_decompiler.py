from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataDecompilerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataDecompiler:
    PREFIX = "pddc-"
    MAX_ENTRIES = 10000

    def __init__(self, on_change: Optional[Callable] = None) -> None:
        self._state = PipelineDataDecompilerState()
        self._on_change: Optional[Callable] = on_change
        logger.debug("PipelineDataDecompiler initialised")

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------
    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------
    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            entries,
            key=lambda rid: (entries[rid].get("created_at", 0), entries[rid].get("_seq", 0)),
        )
        quarter = len(sorted_ids) // 4
        to_remove = sorted_ids[:quarter]
        for rid in to_remove:
            del entries[rid]
        logger.info("Pruned %d entries", len(to_remove))

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
    # Callbacks
    # ------------------------------------------------------------------
    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            logger.debug("Removed callback %s", name)
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

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def decompile(
        self,
        pipeline_id: str,
        data_key: str,
        target_format: str = "raw",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""

        record_id = self._generate_id()
        now = time.time()
        entry: dict = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "target_format": target_format,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        logger.debug("Decompiled %s for pipeline %s", record_id, pipeline_id)
        self._prune()
        self._fire("decompile", record_id=record_id, pipeline_id=pipeline_id)
        return record_id

    def get_decompilation(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_decompilations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_decompilation_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        pipelines = {e.get("pipeline_id") for e in self._state.entries.values()}
        return {
            "total_decompilations": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataDecompilerState()
        self._on_change = None
        logger.info("PipelineDataDecompiler reset")
