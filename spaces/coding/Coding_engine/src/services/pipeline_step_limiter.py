"""Pipeline step limiter - limits step execution frequency (max N executions per step)."""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepLimiterState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepLimiter:
    """Limits step execution frequency (max N executions per step)."""

    PREFIX = "psli-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepLimiterState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepLimiter initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

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

    def set_limit(self, pipeline_id: str, step_name: str, max_executions: int = 10) -> str:
        """Set execution limit for a pipeline step, returns limit ID."""
        limit_id = self._generate_id(f"{pipeline_id}:{step_name}")
        now = time.time()
        entry = {
            "limit_id": limit_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "max_executions": max_executions,
            "current_executions": 0,
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[limit_id] = entry
        self._prune()
        self._fire("limit_set", entry)
        logger.info("Limit set: %s for pipeline '%s' step '%s' (max=%d)", limit_id, pipeline_id, step_name, max_executions)
        return limit_id

    def record_execution(self, limit_id: str) -> bool:
        """Record an execution. Returns False if limit exceeded."""
        entry = self._state.entries.get(limit_id)
        if entry is None:
            return False
        if entry["current_executions"] >= entry["max_executions"]:
            self._fire("execution_denied", entry)
            return False
        entry["current_executions"] += 1
        self._fire("execution_recorded", entry)
        return True

    def get_limit(self, limit_id: str) -> Optional[dict]:
        """Get limit info by ID."""
        entry = self._state.entries.get(limit_id)
        if entry is None:
            return None
        return dict(entry)

    def get_limits(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get limits, newest first (sorted by created_at and _seq)."""
        results = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def is_allowed(self, limit_id: str) -> bool:
        """Check if more executions are allowed."""
        entry = self._state.entries.get(limit_id)
        if entry is None:
            return False
        return entry["current_executions"] < entry["max_executions"]

    def get_limit_count(self, pipeline_id: str = "") -> int:
        """Get count of limits, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["pipeline_id"] == pipeline_id)

    def get_stats(self) -> dict:
        """Get statistics: total_limits, total_executions, exceeded_count."""
        total_executions = sum(e["current_executions"] for e in self._state.entries.values())
        exceeded_count = sum(1 for e in self._state.entries.values() if e["current_executions"] >= e["max_executions"])
        return {
            "total_limits": len(self._state.entries),
            "total_executions": total_executions,
            "exceeded_count": exceeded_count,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = PipelineStepLimiterState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepLimiter reset")
