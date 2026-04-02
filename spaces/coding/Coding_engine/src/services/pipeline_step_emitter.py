"""Pipeline step emitter — emits structured lifecycle events for pipeline step execution.

Tracks started, completed, failed, and skipped events for pipeline steps,
providing query and statistics capabilities for pipeline observability.
"""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepEmitterState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepEmitter:
    """Emits structured lifecycle events for pipeline step execution."""

    PREFIX = "pse2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepEmitterState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        logger.info("PipelineStepEmitter initialized")

    def _generate_id(self, data: str = "") -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
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

    def _fire(self, action: str, data: dict):
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
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

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def emit(self, pipeline_id: str, step_name: str, event_type: str, data: dict = None) -> str:
        """Emit a lifecycle event for a pipeline step.

        Valid event_type values: "started", "completed", "failed", "skipped".
        Returns the generated event ID.
        """
        seq = self._state._seq
        event_id = self._generate_id(f"{pipeline_id}:{step_name}:{event_type}")
        now = time.time()
        entry = {
            "event_id": event_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "event_type": event_type,
            "data": data or {},
            "created_at": now,
            "_seq": seq,
        }
        self._state.entries[event_id] = entry
        self._prune()
        logger.info("event_emitted: %s [%s] %s -> %s", event_id, pipeline_id, step_name, event_type)
        self._fire("event_emitted", entry)
        return event_id

    def get_event(self, event_id: str) -> Optional[dict]:
        """Get a single event by its ID. Returns None if not found."""
        entry = self._state.entries.get(event_id)
        if entry is None:
            return None
        return dict(entry)

    def get_events(self, pipeline_id: str, step_name: str = "", event_type: str = "", limit: int = 100) -> List[dict]:
        """Query events filtered by pipeline_id, optional step_name, optional event_type.

        Returns matching events sorted newest first, up to limit.
        """
        results = []
        for entry in self._state.entries.values():
            if entry["pipeline_id"] != pipeline_id:
                continue
            if step_name and entry["step_name"] != step_name:
                continue
            if event_type and entry["event_type"] != event_type:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: e["_seq"], reverse=True)
        return results[:limit]

    def get_event_count(self, pipeline_id: str = "", event_type: str = "") -> int:
        """Count events, optionally filtered by pipeline_id and/or event_type."""
        count = 0
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            if event_type and entry["event_type"] != event_type:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics: total_events, events_by_type, unique_pipelines."""
        events_by_type: Dict[str, int] = {}
        unique_pipelines: set = set()
        for entry in self._state.entries.values():
            et = entry["event_type"]
            events_by_type[et] = events_by_type.get(et, 0) + 1
            unique_pipelines.add(entry["pipeline_id"])
        return {
            "total_events": len(self._state.entries),
            "events_by_type": events_by_type,
            "unique_pipelines": len(unique_pipelines),
        }

    def reset(self) -> None:
        """Clear all events, callbacks, and reset sequence counter."""
        self._state.entries.clear()
        self._callbacks.clear()
        self._on_change = None
        self._state._seq = 0
        logger.info("PipelineStepEmitter reset")
