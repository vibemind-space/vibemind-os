"""Pipeline Event Aggregator - aggregates pipeline events for dashboards/reporting."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PipelineEventAggregator:
    """Aggregates pipeline events for dashboards and reporting."""

    max_entries: int = 10000
    _events: Dict[str, dict] = field(default_factory=dict)
    _pipeline_index: Dict[str, List[str]] = field(default_factory=dict)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _seq: int = field(default=0)

    def _next_id(self, pipeline_id: str, event_type: str) -> str:
        self._seq += 1
        raw = f"{pipeline_id}-{event_type}-{time.time()}-{self._seq}"
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pea-{hash_part}"

    def _fire(self, action: str, detail: dict) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb({"action": action, **detail})
            except Exception:
                logger.warning("pipeline_event_aggregator.callback_error", name=name)

    def _prune(self) -> None:
        if len(self._events) <= self.max_entries:
            return
        sorted_ids = sorted(
            self._events,
            key=lambda eid: (self._events[eid]["created_at"], self._events[eid]["seq"]),
        )
        to_remove = sorted_ids[: len(self._events) - self.max_entries]
        for eid in to_remove:
            ev = self._events.pop(eid)
            pid = ev["pipeline_id"]
            if pid in self._pipeline_index:
                try:
                    self._pipeline_index[pid].remove(eid)
                except ValueError:
                    pass
                if not self._pipeline_index[pid]:
                    del self._pipeline_index[pid]
        logger.debug("pipeline_event_aggregator.pruned", removed=len(to_remove))

    def record_event(
        self,
        pipeline_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a pipeline event and return the event ID."""
        event_id = self._next_id(pipeline_id, event_type)
        now = time.time()
        event = {
            "event_id": event_id,
            "pipeline_id": pipeline_id,
            "event_type": event_type,
            "data": data or {},
            "created_at": now,
            "seq": self._seq,
        }
        self._events[event_id] = event
        self._pipeline_index.setdefault(pipeline_id, []).append(event_id)
        self._prune()
        logger.info(
            "pipeline_event_aggregator.event_recorded",
            event_id=event_id,
            pipeline_id=pipeline_id,
            event_type=event_type,
        )
        self._fire("event_recorded", {"event_id": event_id, "pipeline_id": pipeline_id, "event_type": event_type})
        return event_id

    def get_events(self, pipeline_id: str, event_type: str = "") -> List[dict]:
        """Get events for a pipeline, optionally filtered by event type."""
        eids = self._pipeline_index.get(pipeline_id, [])
        events = [self._events[eid] for eid in eids if eid in self._events]
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        return events

    def get_event_count(self, pipeline_id: str = "") -> int:
        """Get total event count, or count for a specific pipeline."""
        if pipeline_id:
            return len(self._pipeline_index.get(pipeline_id, []))
        return len(self._events)

    def get_event_types(self, pipeline_id: str = "") -> List[str]:
        """Get unique event types, optionally scoped to a pipeline."""
        if pipeline_id:
            eids = self._pipeline_index.get(pipeline_id, [])
            types = {self._events[eid]["event_type"] for eid in eids if eid in self._events}
        else:
            types = {ev["event_type"] for ev in self._events.values()}
        return sorted(types)

    def get_latest_event(self, pipeline_id: str) -> Optional[dict]:
        """Get the most recent event for a pipeline, or None."""
        eids = self._pipeline_index.get(pipeline_id, [])
        if not eids:
            return None
        valid = [self._events[eid] for eid in eids if eid in self._events]
        if not valid:
            return None
        return max(valid, key=lambda e: (e["created_at"], e["seq"]))

    def get_summary(self, pipeline_id: str = "") -> dict:
        """Get counts per event_type, optionally scoped to a pipeline."""
        if pipeline_id:
            eids = self._pipeline_index.get(pipeline_id, [])
            events = [self._events[eid] for eid in eids if eid in self._events]
        else:
            events = list(self._events.values())
        counts: Dict[str, int] = {}
        for ev in events:
            counts[ev["event_type"]] = counts.get(ev["event_type"], 0) + 1
        return counts

    def get_total_events(self) -> int:
        """Get the total number of events across all pipelines."""
        return len(self._events)

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback
        logger.debug("pipeline_event_aggregator.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback."""
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("pipeline_event_aggregator.callback_removed", name=name)
            return True
        return False

    def get_stats(self) -> dict:
        """Return aggregator statistics."""
        return {
            "total_events": len(self._events),
            "total_pipelines": len(self._pipeline_index),
            "max_entries": self.max_entries,
            "seq": self._seq,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._events.clear()
        self._pipeline_index.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("pipeline_event_aggregator.reset")
