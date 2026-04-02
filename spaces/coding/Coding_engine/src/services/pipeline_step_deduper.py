"""Pipeline step deduper - deduplicates pipeline step executions."""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepDeduperState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepDeduper:
    """Deduplicates pipeline step executions based on content hashes."""

    PREFIX = "psdd-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepDeduperState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepDeduper initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(self._state.entries) // 4
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def dedup(self, pipeline_id: str, step_name: str, content_hash: str, metadata: Optional[dict] = None) -> str:
        """Register a dedup record for a pipeline step execution. Returns the dedup record ID."""
        dedup_id = self._generate_id(f"{pipeline_id}:{step_name}:{content_hash}")
        now = time.time()
        entry = {
            "dedup_id": dedup_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "content_hash": content_hash,
            "metadata": metadata or {},
            "created_at": now,
            "_seq": self._state._seq - 1,
        }
        self._state.entries[dedup_id] = entry
        self._prune()
        self._fire("dedup_created", entry)
        logger.info("Dedup record created: %s for pipeline '%s' step '%s'", dedup_id, pipeline_id, step_name)
        return dedup_id

    def get_dedup(self, record_id: str) -> Optional[dict]:
        """Get a single dedup record by ID. Returns None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_dedups(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get dedup records, optionally filtered by pipeline_id, sorted by (created_at, _seq) desc."""
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_dedup_count(self, pipeline_id: str = "") -> int:
        """Count dedup records, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        """Return summary statistics about current dedup state."""
        pipelines = set()
        steps = set()
        for e in self._state.entries.values():
            pipelines.add(e["pipeline_id"])
            steps.add(e["step_name"])
        return {
            "total_records": len(self._state.entries),
            "unique_pipelines": len(pipelines),
            "unique_steps": len(steps),
        }

    def reset(self):
        """Reset all state to initial values."""
        self._state = PipelineStepDeduperState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepDeduper reset")
