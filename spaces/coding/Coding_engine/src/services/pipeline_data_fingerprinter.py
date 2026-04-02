"""Service module for fingerprinting pipeline data."""

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataFingerprinterState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataFingerprinter:
    PREFIX = "pdfp-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataFingerprinterState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        hex_hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + hex_hash[:12]

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            remove_count = len(self._state.entries) // 4
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]

    def _fire(self, action: str, data: Any) -> None:
        try:
            if self._on_change is not None:
                self._on_change(action, data)
        except Exception:
            logger.exception("on_change callback failed")
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Callback %s failed", name)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        return self._state.callbacks.pop(name, None) is not None

    def fingerprint(
        self,
        pipeline_id: str,
        data_key: str,
        algorithm: str = "sha256",
        metadata: Optional[dict] = None,
    ) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "data_key": data_key,
            "algorithm": algorithm,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("fingerprinted", entry)
        return record_id

    def get_fingerprint(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_fingerprints(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        else:
            entries = list(entries)
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    def get_fingerprint_count(self, pipeline_id: str = "") -> int:
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    def get_stats(self) -> dict:
        unique_pipelines = set(
            e.get("pipeline_id") for e in self._state.entries.values()
        )
        return {
            "total_fingerprints": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        self._state = PipelineDataFingerprinterState()
        self._on_change = None
