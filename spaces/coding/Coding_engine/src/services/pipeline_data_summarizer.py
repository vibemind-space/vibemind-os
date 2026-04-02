import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataSummarizerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataSummarizer:
    PREFIX = "pdsu-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataSummarizerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(self._state.entries.keys(), key=lambda k: (self._state.entries[k].get("created_at", 0), self._state.entries[k].get("_seq", 0)))
            for key in sorted_keys[:len(self._state.entries) // 4]:
                del self._state.entries[key]

    def _fire(self, action: str, data: Any):
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback %s error", name)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]):
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def summarize(self, pipeline_id: str, data_key: str, summary_type: str = "brief", metadata: Optional[dict] = None) -> str:
        if not pipeline_id or not data_key:
            return ""
        record_id = self._generate_id()
        entry = {"record_id": record_id, "pipeline_id": pipeline_id, "data_key": data_key, "summary_type": summary_type, "metadata": copy.deepcopy(metadata) if metadata else {}, "created_at": time.time(), "_seq": self._state._seq}
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("summarized", entry)
        return record_id

    def get_summary(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_summaries(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        if pipeline_id:
            entries = [e for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id]
        else:
            entries = list(self._state.entries.values())
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return entries[:limit]

    def get_summary_count(self, pipeline_id: str = "") -> int:
        if pipeline_id:
            return sum(1 for e in self._state.entries.values() if e.get("pipeline_id") == pipeline_id)
        return len(self._state.entries)

    def get_stats(self) -> dict:
        unique_pipelines = set(e.get("pipeline_id") for e in self._state.entries.values())
        return {"total_summaries": len(self._state.entries), "unique_pipelines": len(unique_pipelines)}

    def reset(self):
        self._state = PipelineDataSummarizerState()
        self._on_change = None
