"""Agent event replay - record and replay agent events for auditing and debugging."""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    events: Dict[str, List[Dict]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentEventReplay:
    """Record and replay agent events for auditing and debugging."""

    MAX_EVENTS = 10000

    def __init__(self) -> None:
        self._state = _State()

    def _next_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"aer-{digest}"

    # ── Recording ──

    def record_event(self, agent_id: str, event_type: str,
                     payload: Optional[Dict] = None) -> str:
        """Record an event for an agent, returns event_id (aer-...)."""
        total = sum(len(v) for v in self._state.events.values())
        if total >= self.MAX_EVENTS:
            logger.warning("max_events_reached", max=self.MAX_EVENTS)
            return ""

        event_id = self._next_id()
        if agent_id not in self._state.events:
            self._state.events[agent_id] = []

        idx = len(self._state.events[agent_id])
        entry = {
            "event_id": event_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "payload": payload or {},
            "timestamp": time.time(),
            "index": idx,
        }
        self._state.events[agent_id].append(entry)
        logger.debug("event_recorded", event_id=event_id, agent_id=agent_id,
                      event_type=event_type)
        self._fire("event_recorded", {"event_id": event_id, "agent_id": agent_id})
        return event_id

    # ── Replay ──

    def replay(self, agent_id: str, from_index: int = 0,
               to_index: int = -1) -> List[Dict]:
        """Replay events from index range. -1 means end."""
        events = self._state.events.get(agent_id, [])
        end = None if to_index == -1 else to_index
        return list(events[from_index:end])

    # ── Query ──

    def get_events(self, agent_id: str, event_type: str = "") -> List[Dict]:
        """Get events for an agent, optionally filtered by event_type."""
        events = self._state.events.get(agent_id, [])
        if not event_type:
            return list(events)
        return [e for e in events if e["event_type"] == event_type]

    def get_event_count(self, agent_id: str = "") -> int:
        """Get total event count, or count for a specific agent."""
        if agent_id:
            return len(self._state.events.get(agent_id, []))
        return sum(len(v) for v in self._state.events.values())

    def clear_events(self, agent_id: str) -> int:
        """Clear all events for an agent, return count removed."""
        events = self._state.events.pop(agent_id, [])
        count = len(events)
        if count:
            logger.info("events_cleared", agent_id=agent_id, count=count)
            self._fire("events_cleared", {"agent_id": agent_id, "count": count})
        return count

    def list_agents(self) -> List[str]:
        """List all agent IDs that have recorded events."""
        return list(self._state.events.keys())

    # ── Stats ──

    def get_stats(self) -> Dict:
        total = sum(len(v) for v in self._state.events.values())
        return {
            "total_events": total,
            "agent_count": len(self._state.events),
            "max_events": self.MAX_EVENTS,
            "sequence": self._state._seq,
            "callback_count": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state.events.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")

    # ── Callbacks ──

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already exists."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
