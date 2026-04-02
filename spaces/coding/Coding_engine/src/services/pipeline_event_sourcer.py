"""Pipeline Event Sourcer – append-only event store for pipeline state reconstruction.

Records domain events with aggregate roots, supports event replay,
snapshot-based state reconstruction, and event stream subscriptions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _DomainEvent:
    event_id: str
    aggregate_id: str
    aggregate_type: str
    event_type: str
    payload: Dict
    version: int
    timestamp: float
    source: str
    tags: List[str]
    seq: int


@dataclass
class _Snapshot:
    snapshot_id: str
    aggregate_id: str
    state: Dict
    version: int
    created_at: float
    seq: int


@dataclass
class _Stream:
    stream_id: str
    name: str
    aggregate_type: str  # filter by aggregate type (empty = all)
    event_types: List[str]  # filter by event type (empty = all)
    status: str  # active | paused
    created_at: float
    seq: int


class PipelineEventSourcer:
    """Append-only event store with replay and snapshot support."""

    def __init__(self, max_events: int = 1000000,
                 max_snapshots: int = 50000,
                 max_streams: int = 1000) -> None:
        self._max_events = max_events
        self._max_snapshots = max_snapshots
        self._max_streams = max_streams
        self._events: Dict[str, _DomainEvent] = {}
        self._snapshots: Dict[str, _Snapshot] = {}
        self._streams: Dict[str, _Stream] = {}
        self._aggregate_versions: Dict[str, int] = {}  # aggregate_id -> latest version
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_events": 0,
            "total_snapshots": 0,
            "total_replays": 0,
        }

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def append_event(self, aggregate_id: str, aggregate_type: str,
                     event_type: str, payload: Optional[Dict] = None,
                     source: str = "", tags: Optional[List[str]] = None) -> str:
        if not aggregate_id or not event_type:
            return ""
        if len(self._events) >= self._max_events:
            return ""
        self._seq += 1
        version = self._aggregate_versions.get(aggregate_id, 0) + 1
        self._aggregate_versions[aggregate_id] = version
        raw = f"evt-{aggregate_id}-{event_type}-{self._seq}-{len(self._events)}"
        eid = "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        ev = _DomainEvent(
            event_id=eid, aggregate_id=aggregate_id,
            aggregate_type=aggregate_type, event_type=event_type,
            payload=dict(payload or {}), version=version,
            timestamp=time.time(), source=source,
            tags=list(tags or []), seq=self._seq,
        )
        self._events[eid] = ev
        self._stats["total_events"] += 1
        self._fire("event_appended", {"event_id": eid, "aggregate_id": aggregate_id})
        return eid

    def get_event(self, event_id: str) -> Optional[Dict]:
        ev = self._events.get(event_id)
        if ev is None:
            return None
        return self._ev_to_dict(ev)

    def get_aggregate_events(self, aggregate_id: str,
                              from_version: int = 0) -> List[Dict]:
        results = []
        for ev in self._events.values():
            if ev.aggregate_id != aggregate_id:
                continue
            if ev.version <= from_version:
                continue
            results.append(self._ev_to_dict(ev))
        results.sort(key=lambda x: x["version"])
        return results

    def get_aggregate_version(self, aggregate_id: str) -> int:
        return self._aggregate_versions.get(aggregate_id, 0)

    def search_events(self, aggregate_type: str = "", event_type: str = "",
                      source: str = "", tag: str = "",
                      limit: int = 100) -> List[Dict]:
        results = []
        for ev in self._events.values():
            if aggregate_type and ev.aggregate_type != aggregate_type:
                continue
            if event_type and ev.event_type != event_type:
                continue
            if source and ev.source != source:
                continue
            if tag and tag not in ev.tags:
                continue
            results.append(self._ev_to_dict(ev))
        results.sort(key=lambda x: x["seq"])
        if limit > 0:
            results = results[-limit:]
        return results

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def create_snapshot(self, aggregate_id: str, state: Dict) -> str:
        version = self._aggregate_versions.get(aggregate_id, 0)
        if version == 0:
            return ""
        if len(self._snapshots) >= self._max_snapshots:
            return ""
        self._seq += 1
        raw = f"snap-{aggregate_id}-{version}-{self._seq}-{len(self._snapshots)}"
        sid = "snap-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        snap = _Snapshot(
            snapshot_id=sid, aggregate_id=aggregate_id,
            state=dict(state), version=version,
            created_at=time.time(), seq=self._seq,
        )
        self._snapshots[sid] = snap
        self._stats["total_snapshots"] += 1
        self._fire("snapshot_created", {"snapshot_id": sid, "aggregate_id": aggregate_id})
        return sid

    def get_latest_snapshot(self, aggregate_id: str) -> Optional[Dict]:
        best: Optional[_Snapshot] = None
        for snap in self._snapshots.values():
            if snap.aggregate_id != aggregate_id:
                continue
            if best is None or snap.version > best.version:
                best = snap
        if best is None:
            return None
        return self._snap_to_dict(best)

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        snap = self._snapshots.get(snapshot_id)
        if snap is None:
            return None
        return self._snap_to_dict(snap)

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay_aggregate(self, aggregate_id: str) -> Dict:
        """Return all events for an aggregate, optionally from latest snapshot."""
        self._stats["total_replays"] += 1
        snapshot = self.get_latest_snapshot(aggregate_id)
        from_version = 0
        if snapshot:
            from_version = snapshot["version"]
        events = self.get_aggregate_events(aggregate_id, from_version=from_version)
        return {
            "aggregate_id": aggregate_id,
            "snapshot": snapshot,
            "events_since_snapshot": events,
            "current_version": self.get_aggregate_version(aggregate_id),
        }

    # ------------------------------------------------------------------
    # Streams
    # ------------------------------------------------------------------

    def create_stream(self, name: str, aggregate_type: str = "",
                      event_types: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if len(self._streams) >= self._max_streams:
            return ""
        self._seq += 1
        raw = f"str-{name}-{self._seq}-{len(self._streams)}"
        sid = "str-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        st = _Stream(
            stream_id=sid, name=name, aggregate_type=aggregate_type,
            event_types=list(event_types or []), status="active",
            created_at=time.time(), seq=self._seq,
        )
        self._streams[sid] = st
        return sid

    def get_stream(self, stream_id: str) -> Optional[Dict]:
        st = self._streams.get(stream_id)
        if st is None:
            return None
        return self._str_to_dict(st)

    def remove_stream(self, stream_id: str) -> bool:
        if stream_id not in self._streams:
            return False
        del self._streams[stream_id]
        return True

    def pause_stream(self, stream_id: str) -> bool:
        st = self._streams.get(stream_id)
        if st is None or st.status != "active":
            return False
        st.status = "paused"
        return True

    def resume_stream(self, stream_id: str) -> bool:
        st = self._streams.get(stream_id)
        if st is None or st.status != "paused":
            return False
        st.status = "active"
        return True

    def get_stream_events(self, stream_id: str, limit: int = 100) -> List[Dict]:
        st = self._streams.get(stream_id)
        if st is None:
            return []
        results = []
        for ev in self._events.values():
            if st.aggregate_type and ev.aggregate_type != st.aggregate_type:
                continue
            if st.event_types and ev.event_type not in st.event_types:
                continue
            results.append(self._ev_to_dict(ev))
        results.sort(key=lambda x: x["seq"])
        if limit > 0:
            results = results[-limit:]
        return results

    def list_streams(self) -> List[Dict]:
        results = [self._str_to_dict(s) for s in self._streams.values()]
        results.sort(key=lambda x: x["seq"])
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
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
        return {
            **self._stats,
            "current_events": len(self._events),
            "current_snapshots": len(self._snapshots),
            "current_streams": len(self._streams),
            "unique_aggregates": len(self._aggregate_versions),
        }

    def reset(self) -> None:
        self._events.clear()
        self._snapshots.clear()
        self._streams.clear()
        self._aggregate_versions.clear()
        self._seq = 0
        self._stats = {
            "total_events": 0,
            "total_snapshots": 0,
            "total_replays": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ev_to_dict(ev: _DomainEvent) -> Dict:
        return {
            "event_id": ev.event_id,
            "aggregate_id": ev.aggregate_id,
            "aggregate_type": ev.aggregate_type,
            "event_type": ev.event_type,
            "payload": dict(ev.payload),
            "version": ev.version,
            "timestamp": ev.timestamp,
            "source": ev.source,
            "tags": list(ev.tags),
            "seq": ev.seq,
        }

    @staticmethod
    def _snap_to_dict(snap: _Snapshot) -> Dict:
        return {
            "snapshot_id": snap.snapshot_id,
            "aggregate_id": snap.aggregate_id,
            "state": dict(snap.state),
            "version": snap.version,
            "created_at": snap.created_at,
            "seq": snap.seq,
        }

    @staticmethod
    def _str_to_dict(st: _Stream) -> Dict:
        return {
            "stream_id": st.stream_id,
            "name": st.name,
            "aggregate_type": st.aggregate_type,
            "event_types": list(st.event_types),
            "status": st.status,
            "created_at": st.created_at,
            "seq": st.seq,
        }
