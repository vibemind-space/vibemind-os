from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataLinkerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataLinker:
    PREFIX = "pdlk-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = PipelineDataLinkerState()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries,
            key=lambda k: (
                self._state.entries[k].get("created_at", ""),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        quarter = len(sorted_ids) // 4
        to_remove = sorted_ids[:quarter]
        for rid in to_remove:
            del self._state.entries[rid]
        logger.info("Pruned %d entries, %d remaining", len(to_remove), len(self._state.entries))

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

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Fire callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data: dict = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback failed for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Named callback failed for action=%s", action)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def link(
        self,
        pipeline_id: str,
        data_key: str,
        target_key: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry: dict = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "target_key": target_key,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("link_created", record_id=record_id, pipeline_id=pipeline_id)
        logger.debug("Created link %s for pipeline %s", record_id, pipeline_id)
        return record_id

    def get_link(self, record_id: str) -> Optional[dict]:
        return self._state.entries.get(record_id)

    def get_links(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(
            key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)),
            reverse=True,
        )
        return entries[:limit]

    def get_link_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        pipelines = {e.get("pipeline_id") for e in self._state.entries.values()}
        return {
            "total_links": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataLinkerState()
        self._on_change = None
        logger.info("PipelineDataLinker reset")
