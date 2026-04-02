"""Agent Event Store – records and queries agent-level events.

Provides a central store for agent actions, decisions, errors, and other
events with rich filtering, timeline views, and per-agent summaries.
All data lives in-memory with automatic pruning when the entry limit is
reached.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _EventEntry:
    """A single recorded event."""
    event_id: str = ""
    agent_id: str = ""
    event_type: str = ""
    data: Dict = field(default_factory=dict)
    severity: str = "info"
    tags: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentEventStore:
    """In-memory event store for agent-level events."""

    SEVERITIES = ("debug", "info", "warning", "error", "critical")

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._events: Dict[str, _EventEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}

        # indexes for fast lookup
        self._agent_index: Dict[str, List[str]] = {}   # agent_id -> [event_id]
        self._type_index: Dict[str, List[str]] = {}    # event_type -> [event_id]

        # stats counters
        self._stats = {
            "total_recorded": 0,
            "total_pruned": 0,
            "total_purged": 0,
            "total_queries": 0,
        }

        logger.debug("agent_event_store.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        event_type: str,
        data: Optional[Dict] = None,
        severity: str = "info",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Record an agent event and return its event_id."""
        if not agent_id or not event_type:
            return ""
        if severity not in self.SEVERITIES:
            return ""

        # prune if at capacity
        if len(self._events) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()
        raw = f"{agent_id}-{event_type}-{now}-{self._seq}"
        eid = "aes-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _EventEntry(
            event_id=eid,
            agent_id=agent_id,
            event_type=event_type,
            data=data or {},
            severity=severity,
            tags=list(tags) if tags else [],
            timestamp=now,
            seq=self._seq,
        )
        self._events[eid] = entry

        # update indexes
        self._agent_index.setdefault(agent_id, []).append(eid)
        self._type_index.setdefault(event_type, []).append(eid)

        self._stats["total_recorded"] += 1

        logger.debug(
            "agent_event_store.record",
            event_id=eid,
            agent_id=agent_id,
            event_type=event_type,
            severity=severity,
        )
        self._fire("event_recorded", {
            "event_id": eid,
            "agent_id": agent_id,
            "event_type": event_type,
            "severity": severity,
        })
        return eid

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Return a single event as a dict, or None."""
        e = self._events.get(event_id)
        if not e:
            return None
        return self._to_dict(e)

    def query(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query events with optional filters. Returns newest first."""
        self._stats["total_queries"] += 1

        # start with candidate ids
        candidates: Optional[set] = None

        if agent_id is not None:
            ids = self._agent_index.get(agent_id, [])
            candidates = set(ids)

        if event_type is not None:
            ids = set(self._type_index.get(event_type, []))
            candidates = ids if candidates is None else candidates & ids

        if candidates is None:
            pool = list(self._events.values())
        else:
            pool = [self._events[eid] for eid in candidates if eid in self._events]

        # severity filter
        if severity is not None:
            pool = [e for e in pool if e.severity == severity]

        # sort newest first, apply limit
        pool.sort(key=lambda e: e.seq, reverse=True)
        return [self._to_dict(e) for e in pool[:limit]]

    def get_agent_timeline(self, agent_id: str, limit: int = 50) -> List[Dict]:
        """Return events for a specific agent, sorted oldest-first."""
        self._stats["total_queries"] += 1
        ids = self._agent_index.get(agent_id, [])
        entries = [self._events[eid] for eid in ids if eid in self._events]
        entries.sort(key=lambda e: e.seq)
        return [self._to_dict(e) for e in entries[-limit:]]

    # ------------------------------------------------------------------
    # Counting / Summaries
    # ------------------------------------------------------------------

    def get_event_count(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> int:
        """Count events matching the given filters."""
        if agent_id is None and event_type is None:
            return len(self._events)

        candidates: Optional[set] = None

        if agent_id is not None:
            ids = self._agent_index.get(agent_id, [])
            candidates = set(eid for eid in ids if eid in self._events)

        if event_type is not None:
            ids = set(eid for eid in self._type_index.get(event_type, [])
                       if eid in self._events)
            candidates = ids if candidates is None else candidates & ids

        return len(candidates) if candidates is not None else 0

    def get_agent_summary(self, agent_id: str) -> Dict:
        """Return a summary dict for the given agent."""
        ids = self._agent_index.get(agent_id, [])
        entries = [self._events[eid] for eid in ids if eid in self._events]

        if not entries:
            return {
                "total_events": 0,
                "by_type": {},
                "by_severity": {},
                "last_event_at": None,
            }

        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        last_ts = 0.0

        for e in entries:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
            if e.timestamp > last_ts:
                last_ts = e.timestamp

        return {
            "total_events": len(entries),
            "by_type": by_type,
            "by_severity": by_severity,
            "last_event_at": last_ts,
        }

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one event."""
        return [
            aid for aid, ids in self._agent_index.items()
            if any(eid in self._events for eid in ids)
        ]

    def list_event_types(self) -> List[str]:
        """Return all unique event types that have at least one event."""
        return [
            et for et, ids in self._type_index.items()
            if any(eid in self._events for eid in ids)
        ]

    # ------------------------------------------------------------------
    # Purging
    # ------------------------------------------------------------------

    def purge(
        self,
        agent_id: Optional[str] = None,
        before_timestamp: Optional[float] = None,
    ) -> int:
        """Remove events matching criteria. Returns count of purged events."""
        to_remove: List[str] = []

        for eid, e in self._events.items():
            match = True
            if agent_id is not None and e.agent_id != agent_id:
                match = False
            if before_timestamp is not None and e.timestamp >= before_timestamp:
                match = False
            # if no filters given, purge everything
            if agent_id is None and before_timestamp is None:
                match = True
            if match:
                to_remove.append(eid)

        for eid in to_remove:
            self._remove_event(eid)

        self._stats["total_purged"] += len(to_remove)

        if to_remove:
            logger.debug("agent_event_store.purge", count=len(to_remove))
            self._fire("events_purged", {"count": len(to_remove)})

        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_events": len(self._events),
            "unique_agents": len([
                a for a, ids in self._agent_index.items()
                if any(eid in self._events for eid in ids)
            ]),
            "unique_event_types": len([
                t for t, ids in self._type_index.items()
                if any(eid in self._events for eid in ids)
            ]),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._events.clear()
        self._agent_index.clear()
        self._type_index.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_event_store.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, e: _EventEntry) -> Dict:
        """Convert an event entry to a plain dict."""
        return {
            "event_id": e.event_id,
            "agent_id": e.agent_id,
            "event_type": e.event_type,
            "data": dict(e.data),
            "severity": e.severity,
            "tags": list(e.tags),
            "timestamp": e.timestamp,
            "seq": e.seq,
        }

    def _remove_event(self, event_id: str) -> None:
        """Remove a single event from store and indexes."""
        e = self._events.pop(event_id, None)
        if not e:
            return
        # clean agent index
        ids = self._agent_index.get(e.agent_id)
        if ids:
            try:
                ids.remove(event_id)
            except ValueError:
                pass
        # clean type index
        ids = self._type_index.get(e.event_type)
        if ids:
            try:
                ids.remove(event_id)
            except ValueError:
                pass

    def _prune(self) -> None:
        """Remove oldest entries when at capacity."""
        entries = sorted(self._events.values(), key=lambda e: e.seq)
        to_remove = max(len(entries) // 4, 1)
        for e in entries[:to_remove]:
            self._remove_event(e.event_id)
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_event_store.prune", removed=to_remove)
