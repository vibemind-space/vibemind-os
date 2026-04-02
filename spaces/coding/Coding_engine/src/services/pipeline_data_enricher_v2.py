from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataEnricherV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataEnricherV2:
    PREFIX = "pdev-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataEnricherV2State()
        self._on_change: Optional[Callable] = None
        logger.info("PipelineDataEnricherV2 initialised")

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        hash_hex = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{hash_hex[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", ""),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        quarter = len(sorted_keys) // 4
        to_remove = sorted_keys[:quarter]
        for k in to_remove:
            del self._state.entries[k]
        logger.info("Pruned %d entries", len(to_remove))
        self._fire("prune", removed=len(to_remove))

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

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

    def enrich_v2(
        self,
        pipeline_id: str,
        data_key: str,
        source: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            logger.warning("enrich_v2 called with empty pipeline_id or data_key")
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "source": source,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        logger.info("Enriched data_key %s for pipeline %s -> %s", data_key, pipeline_id, record_id)
        self._prune()
        self._fire("enrich_v2", pipeline_id=pipeline_id, record_id=record_id)
        return record_id

    def get_enrichment(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_enrichments(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_enrichment_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)

    def get_stats(self) -> dict:
        pipelines = {e.get("pipeline_id") for e in self._state.entries.values()}
        return {
            "total_enrichments": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataEnricherV2State()
        self._on_change = None
        logger.info("PipelineDataEnricherV2 reset")
