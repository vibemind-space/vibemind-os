"""Pipeline data indexer for fast field-based lookup of pipeline data."""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataIndexerState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataIndexer:
    """Indexes pipeline data fields for fast lookup."""

    PREFIX = "pdix-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataIndexerState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("_seq_num", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, action: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    @property
    def on_change(self):
        return self._callbacks

    @on_change.setter
    def on_change(self, value: dict):
        self._callbacks = value

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def index(self, pipeline_id: str, data: dict, index_fields: List[str], label: str = "") -> str:
        """Index data by specified fields, returns index ID."""
        if not pipeline_id or not data or not index_fields:
            return ""
        index_id = self._generate_id(f"{pipeline_id}{label}")
        seq_num = self._state._seq
        indexed_fields = {}
        for field in index_fields:
            if field in data:
                indexed_fields[field] = copy.deepcopy(data[field])
        entry = {
            "index_id": index_id,
            "pipeline_id": pipeline_id,
            "data": copy.deepcopy(data),
            "index_fields": list(index_fields),
            "indexed_fields": indexed_fields,
            "label": label,
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[index_id] = entry
        self._prune()
        self._fire("indexed", copy.deepcopy(entry))
        return index_id

    def lookup(self, index_id: str, field: str, value: Any) -> Optional[dict]:
        """Lookup by indexed field value."""
        entry = self._state.entries.get(index_id)
        if entry is None:
            return None
        if field not in entry.get("indexed_fields", {}):
            return None
        if entry["indexed_fields"][field] == value:
            return copy.deepcopy(entry["data"])
        return None

    def get_index(self, index_id: str) -> Optional[dict]:
        """Get a single index entry."""
        entry = self._state.entries.get(index_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_indices(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get indices, newest first (sorted by created_at and _seq)."""
        results = list(self._state.entries.values())
        if pipeline_id:
            results = [e for e in results if e["pipeline_id"] == pipeline_id]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)), reverse=True)
        return [copy.deepcopy(e) for e in results[:limit]]

    def get_index_count(self, pipeline_id: str = "") -> int:
        """Count indices, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        """Return stats: total_indices, total_fields_indexed, unique_pipelines."""
        all_fields = 0
        pipelines = set()
        for e in self._state.entries.values():
            all_fields += len(e.get("indexed_fields", {}))
            pipelines.add(e["pipeline_id"])
        return {
            "total_indices": len(self._state.entries),
            "total_fields_indexed": all_fields,
            "unique_pipelines": len(pipelines),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineDataIndexerState()
        self._callbacks.clear()
        self._fire("reset", {})
