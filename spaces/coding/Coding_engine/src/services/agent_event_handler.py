"""Agent Event Handler – event bus for agent-to-agent communication.

Provides a typed event system where agents can subscribe to event types
and publish events. Supports wildcard subscriptions, event filtering,
and bounded event history with replay capability.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Subscription:
    sub_id: str
    event_type: str  # "*" for wildcard
    agent: str
    handler: Optional[Callable]
    active: bool
    one_shot: bool
    total_received: int
    created_at: float


@dataclass
class _Event:
    event_id: str
    event_type: str
    source: str
    payload: Any
    delivered_to: int
    created_at: float


class AgentEventHandler:
    """Event bus for agent communication with typed events."""

    def __init__(self, max_subscriptions: int = 10000, max_history: int = 100000):
        self._subs: Dict[str, _Subscription] = {}
        self._agent_type_index: Dict[str, str] = {}  # "agent:type" -> sub_id
        self._history: List[_Event] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_subs = max_subscriptions
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_subs = 0
        self._total_events = 0
        self._total_deliveries = 0

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        agent: str,
        handler: Optional[Callable] = None,
        one_shot: bool = False,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not event_type or not agent:
            return ""
        key = f"{agent}:{event_type}"
        if key in self._agent_type_index:
            return ""
        if len(self._subs) >= self._max_subs:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{event_type}-{agent}-{now}-{self._seq}"
        sid = "sub-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        sub = _Subscription(
            sub_id=sid,
            event_type=event_type,
            agent=agent,
            handler=handler,
            active=True,
            one_shot=one_shot,
            total_received=0,
            created_at=now,
        )
        self._subs[sid] = sub
        self._agent_type_index[key] = sid
        self._total_subs += 1
        self._fire_cb("subscription_created", {"sub_id": sid, "event_type": event_type})
        return sid

    def get_subscription(self, sub_id: str) -> Optional[Dict[str, Any]]:
        s = self._subs.get(sub_id)
        if not s:
            return None
        return {
            "sub_id": s.sub_id,
            "event_type": s.event_type,
            "agent": s.agent,
            "active": s.active,
            "one_shot": s.one_shot,
            "total_received": s.total_received,
            "created_at": s.created_at,
        }

    def unsubscribe(self, sub_id: str) -> bool:
        s = self._subs.pop(sub_id, None)
        if not s:
            return False
        key = f"{s.agent}:{s.event_type}"
        self._agent_type_index.pop(key, None)
        self._fire_cb("subscription_removed", {"sub_id": sub_id})
        return True

    def pause_subscription(self, sub_id: str) -> bool:
        s = self._subs.get(sub_id)
        if not s or not s.active:
            return False
        s.active = False
        return True

    def resume_subscription(self, sub_id: str) -> bool:
        s = self._subs.get(sub_id)
        if not s or s.active:
            return False
        s.active = True
        return True

    def list_subscriptions(
        self,
        agent: str = "",
        event_type: str = "",
        active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        results = []
        for s in self._subs.values():
            if agent and s.agent != agent:
                continue
            if event_type and s.event_type != event_type:
                continue
            if active is not None and s.active != active:
                continue
            results.append(self.get_subscription(s.sub_id))
        return results

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        event_type: str,
        source: str = "",
        payload: Any = None,
    ) -> int:
        if not event_type:
            return 0

        self._seq += 1
        now = time.time()
        raw = f"evt-{event_type}-{now}-{self._seq}"
        eid = "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        delivered = 0
        to_remove = []

        for sid, sub in list(self._subs.items()):
            if not sub.active:
                continue
            if sub.event_type != "*" and sub.event_type != event_type:
                continue
            # deliver
            if sub.handler:
                try:
                    sub.handler(event_type, payload)
                except Exception:
                    pass
            sub.total_received += 1
            delivered += 1
            if sub.one_shot:
                to_remove.append(sid)

        for sid in to_remove:
            s = self._subs.pop(sid, None)
            if s:
                key = f"{s.agent}:{s.event_type}"
                self._agent_type_index.pop(key, None)

        event = _Event(
            event_id=eid,
            event_type=event_type,
            source=source,
            payload=payload,
            delivered_to=delivered,
            created_at=now,
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            trim = self._max_history // 10
            self._history = self._history[trim:]

        self._total_events += 1
        self._total_deliveries += delivered
        self._fire_cb("event_published", {"event_id": eid, "event_type": event_type, "delivered": delivered})
        return delivered

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_event_history(
        self,
        event_type: str = "",
        source: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for e in reversed(self._history):
            if event_type and e.event_type != event_type:
                continue
            if source and e.source != source:
                continue
            results.append({
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "payload": e.payload,
                "delivered_to": e.delivered_to,
                "created_at": e.created_at,
            })
            if len(results) >= limit:
                break
        return results

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        for e in self._history:
            if e.event_id == event_id:
                return {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "source": e.source,
                    "payload": e.payload,
                    "delivered_to": e.delivered_to,
                    "created_at": e.created_at,
                }
        return None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire_cb(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_subscriptions": len(self._subs),
            "total_subscriptions": self._total_subs,
            "total_events": self._total_events,
            "total_deliveries": self._total_deliveries,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._subs.clear()
        self._agent_type_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_subs = 0
        self._total_events = 0
        self._total_deliveries = 0
