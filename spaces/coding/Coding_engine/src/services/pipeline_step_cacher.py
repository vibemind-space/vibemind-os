"""Pipeline step cacher service for caching pipeline steps."""

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepCacherState:
    """State container for pipeline step cacher."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepCacher:
    """Service for caching pipeline steps."""

    PREFIX = "psch-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepCacherState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash."""
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _fire(self, event: str, data: Any = None) -> None:
        """Fire callbacks for an event."""
        for cb_id, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback %s failed: %s", cb_id, e)

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, cb_id: str) -> bool:
        """Remove a registered callback. Returns True if found."""
        return self._state.callbacks.pop(cb_id, None) is not None

    def _prune(self) -> None:
        """Prune oldest quarter of entries if over MAX_ENTRIES limit."""
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries.keys(),
            key=lambda k: (entries[k].get("created_at", 0), entries[k].get("_seq", 0)),
        )
        to_remove = len(entries) // 4
        for key in sorted_keys[:to_remove]:
            del entries[key]
        logger.info("Pruned %d cache entries", to_remove)

    def cache(
        self,
        pipeline_id: str,
        step_name: str,
        ttl_seconds: int = 3600,
        metadata: Optional[dict] = None,
    ) -> str:
        """Cache a pipeline step. Returns record_id or empty string on invalid input."""
        if not pipeline_id or not step_name:
            return ""

        record_id = self._generate_id(f"{pipeline_id}:{step_name}")
        now = time.time()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "ttl_seconds": ttl_seconds,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }

        self._prune()
        self._fire("cached", {"record_id": record_id, "pipeline_id": pipeline_id, "step_name": step_name})

        if self._on_change is not None:
            try:
                self._on_change("cached", {"record_id": record_id})
            except Exception as e:
                logger.warning("on_change callback failed: %s", e)

        logger.info("Cached step %s for pipeline %s as %s", step_name, pipeline_id, record_id)
        return record_id

    def get_cache_entry(self, record_id: str) -> Optional[dict]:
        """Get a cache entry by record_id. Returns a copy of the dict or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_cache_entries(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get cache entries, optionally filtered by pipeline_id, sorted by (created_at, _seq) desc."""
        if pipeline_id:
            entries = [
                copy.deepcopy(v)
                for v in self._state.entries.values()
                if v.get("pipeline_id") == pipeline_id
            ]
        else:
            entries = [copy.deepcopy(v) for v in self._state.entries.values()]

        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return entries[:limit]

    def get_cache_count(self, pipeline_id: str = "") -> int:
        """Get count of cached entries, optionally filtered by pipeline_id."""
        if pipeline_id:
            return sum(
                1 for v in self._state.entries.values()
                if v.get("pipeline_id") == pipeline_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        """Get overall cache statistics."""
        unique_pipelines = set()
        for entry in self._state.entries.values():
            pid = entry.get("pipeline_id")
            if pid:
                unique_pipelines.add(pid)
        return {
            "total_caches": len(self._state.entries),
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Reset all state to fresh and clear on_change."""
        self._state = PipelineStepCacherState()
        self._on_change = None
        logger.info("Pipeline step cacher reset")
