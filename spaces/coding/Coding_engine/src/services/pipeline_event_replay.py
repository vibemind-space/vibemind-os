"""Pipeline event replay - record and replay events for debugging and testing."""

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _RecordedEvent:
    event_id: str
    recording_id: str
    event_type: str
    source: str
    data: Dict
    timestamp: float
    sequence: int


@dataclass
class _Recording:
    recording_id: str
    name: str
    status: str  # recording, stopped, replaying
    events: List[str]  # event_ids
    started_at: float
    stopped_at: float
    replay_count: int
    tags: List[str]
    metadata: Dict = field(default_factory=dict)


class PipelineEventReplay:
    """Record pipeline events and replay them for debugging and testing."""

    def __init__(self, max_recordings: int = 1000, max_events: int = 100000):
        self._max_recordings = max_recordings
        self._max_events = max_events
        self._recordings: Dict[str, _Recording] = {}
        self._events: Dict[str, _RecordedEvent] = {}
        self._active_recording: Optional[str] = None
        self._sequence = 0
        self._replay_handlers: Dict[str, Callable] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_recordings": 0,
            "total_events_recorded": 0,
            "total_replays": 0,
            "total_events_replayed": 0,
        }

    # ── Recording Management ──

    def start_recording(self, name: str, tags: Optional[List[str]] = None,
                        metadata: Optional[Dict] = None) -> str:
        """Start a new recording session."""
        if not name:
            return ""
        if self._active_recording:
            return ""  # Already recording
        if len(self._recordings) >= self._max_recordings:
            return ""

        rid = f"rec-{uuid.uuid4().hex[:10]}"
        self._recordings[rid] = _Recording(
            recording_id=rid,
            name=name,
            status="recording",
            events=[],
            started_at=time.time(),
            stopped_at=0.0,
            replay_count=0,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._active_recording = rid
        self._sequence = 0
        self._stats["total_recordings"] += 1
        self._fire_callbacks("recording_started", rid)
        return rid

    def stop_recording(self) -> str:
        """Stop the active recording."""
        if not self._active_recording:
            return ""
        rid = self._active_recording
        rec = self._recordings[rid]
        rec.status = "stopped"
        rec.stopped_at = time.time()
        self._active_recording = None
        self._fire_callbacks("recording_stopped", rid)
        return rid

    def is_recording(self) -> bool:
        return self._active_recording is not None

    def get_active_recording(self) -> Optional[str]:
        return self._active_recording

    def get_recording(self, recording_id: str) -> Optional[Dict]:
        rec = self._recordings.get(recording_id)
        if not rec:
            return None
        return {
            "recording_id": rec.recording_id,
            "name": rec.name,
            "status": rec.status,
            "event_count": len(rec.events),
            "started_at": rec.started_at,
            "stopped_at": rec.stopped_at,
            "duration": (rec.stopped_at or time.time()) - rec.started_at,
            "replay_count": rec.replay_count,
            "tags": list(rec.tags),
        }

    def remove_recording(self, recording_id: str) -> bool:
        rec = self._recordings.get(recording_id)
        if not rec:
            return False
        if self._active_recording == recording_id:
            return False
        # Remove associated events
        for eid in rec.events:
            self._events.pop(eid, None)
        del self._recordings[recording_id]
        return True

    def list_recordings(self, tag: str = "", status: str = "") -> List[Dict]:
        result = []
        for rec in self._recordings.values():
            if tag and tag not in rec.tags:
                continue
            if status and rec.status != status:
                continue
            result.append({
                "recording_id": rec.recording_id,
                "name": rec.name,
                "status": rec.status,
                "event_count": len(rec.events),
            })
        return result

    # ── Event Capture ──

    def record_event(self, event_type: str, source: str,
                     data: Optional[Dict] = None) -> str:
        """Record an event during an active recording."""
        if not self._active_recording:
            return ""
        if len(self._events) >= self._max_events:
            return ""

        eid = f"evt-{uuid.uuid4().hex[:10]}"
        self._sequence += 1
        self._events[eid] = _RecordedEvent(
            event_id=eid,
            recording_id=self._active_recording,
            event_type=event_type,
            source=source,
            data=data or {},
            timestamp=time.time(),
            sequence=self._sequence,
        )
        self._recordings[self._active_recording].events.append(eid)
        self._stats["total_events_recorded"] += 1
        return eid

    def get_event(self, event_id: str) -> Optional[Dict]:
        e = self._events.get(event_id)
        if not e:
            return None
        return {
            "event_id": e.event_id,
            "recording_id": e.recording_id,
            "event_type": e.event_type,
            "source": e.source,
            "data": dict(e.data),
            "timestamp": e.timestamp,
            "sequence": e.sequence,
        }

    def get_events(self, recording_id: str, event_type: str = "",
                   source: str = "", limit: int = 100) -> List[Dict]:
        """Get events from a recording with optional filters."""
        rec = self._recordings.get(recording_id)
        if not rec:
            return []
        result = []
        for eid in rec.events:
            e = self._events.get(eid)
            if not e:
                continue
            if event_type and e.event_type != event_type:
                continue
            if source and e.source != source:
                continue
            result.append({
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "data": dict(e.data),
                "sequence": e.sequence,
            })
            if len(result) >= limit:
                break
        return result

    def get_event_types(self, recording_id: str) -> Dict[str, int]:
        """Get event type counts for a recording."""
        rec = self._recordings.get(recording_id)
        if not rec:
            return {}
        counts: Dict[str, int] = defaultdict(int)
        for eid in rec.events:
            e = self._events.get(eid)
            if e:
                counts[e.event_type] += 1
        return dict(counts)

    # ── Replay ──

    def register_handler(self, event_type: str, handler: Callable) -> bool:
        """Register a replay handler for an event type."""
        if event_type in self._replay_handlers:
            return False
        self._replay_handlers[event_type] = handler
        return True

    def unregister_handler(self, event_type: str) -> bool:
        if event_type not in self._replay_handlers:
            return False
        del self._replay_handlers[event_type]
        return True

    def replay(self, recording_id: str, speed: float = 1.0,
               event_types: Optional[List[str]] = None) -> Dict:
        """Replay a recording, calling registered handlers."""
        rec = self._recordings.get(recording_id)
        if not rec or rec.status == "recording":
            return {"success": False, "reason": "invalid_recording"}

        events_to_replay = []
        for eid in rec.events:
            e = self._events.get(eid)
            if not e:
                continue
            if event_types and e.event_type not in event_types:
                continue
            events_to_replay.append(e)

        replayed = 0
        errors = 0
        for evt in events_to_replay:
            handler = self._replay_handlers.get(evt.event_type)
            if handler:
                try:
                    handler(evt.event_type, evt.source, dict(evt.data))
                    replayed += 1
                except Exception:
                    errors += 1
            else:
                replayed += 1  # No handler, count as skipped-ok

        rec.replay_count += 1
        self._stats["total_replays"] += 1
        self._stats["total_events_replayed"] += replayed
        self._fire_callbacks("replay_completed", recording_id)

        return {
            "success": True,
            "recording_id": recording_id,
            "total_events": len(events_to_replay),
            "replayed": replayed,
            "errors": errors,
        }

    # ── Search ──

    def search_events(self, query: str, recording_id: str = "",
                      limit: int = 50) -> List[Dict]:
        """Search events by type, source, or data content."""
        q = query.lower()
        result = []
        events = self._events.values()
        if recording_id:
            rec = self._recordings.get(recording_id)
            if not rec:
                return []
            events = [self._events[eid] for eid in rec.events if eid in self._events]

        for e in events:
            if (q in e.event_type.lower() or
                q in e.source.lower() or
                q in str(e.data).lower()):
                result.append({
                    "event_id": e.event_id,
                    "recording_id": e.recording_id,
                    "event_type": e.event_type,
                    "source": e.source,
                })
                if len(result) >= limit:
                    break
        return result

    # ── Callbacks ──

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, action: str, recording_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, recording_id)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "active_recording": self._active_recording is not None,
            "stored_recordings": len(self._recordings),
            "stored_events": len(self._events),
            "registered_handlers": len(self._replay_handlers),
        }

    def reset(self) -> None:
        self._recordings.clear()
        self._events.clear()
        self._active_recording = None
        self._sequence = 0
        self._replay_handlers.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
