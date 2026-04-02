"""Pipeline Notification Hub – routes notifications to subscribers.

Manages notification channels, subscriber registration, and delivery
with filtering by severity, source, and topic. Tracks delivery history.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Subscriber:
    sub_id: str
    name: str
    handler: Callable
    topics: List[str]
    min_severity: int  # 0=debug, 1=info, 2=warn, 3=error, 4=critical
    tags: List[str]
    total_received: int
    created_at: float


@dataclass
class _Notification:
    notif_id: str
    source: str
    topic: str
    severity: int
    message: str
    data: Dict[str, Any]
    delivered_to: List[str]
    timestamp: float


class PipelineNotificationHub:
    """Routes notifications to registered subscribers."""

    SEVERITIES = {"debug": 0, "info": 1, "warn": 2, "error": 3, "critical": 4}

    def __init__(self, max_subscribers: int = 5000, max_history: int = 100000):
        self._subscribers: Dict[str, _Subscriber] = {}
        self._name_index: Dict[str, str] = {}  # name -> sub_id
        self._topic_index: Dict[str, List[str]] = {}  # topic -> [sub_ids]
        self._history: List[_Notification] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_subscribers = max_subscribers
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_subscribers = 0
        self._total_sent = 0
        self._total_delivered = 0

    # ------------------------------------------------------------------
    # Subscriber management
    # ------------------------------------------------------------------

    def subscribe(
        self,
        name: str,
        handler: Callable,
        topics: Optional[List[str]] = None,
        min_severity: str = "info",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or not handler:
            return ""
        if name in self._name_index:
            return ""
        if len(self._subscribers) >= self._max_subscribers:
            return ""

        sev = self.SEVERITIES.get(min_severity, 1)
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        sid = "sub-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        sub = _Subscriber(
            sub_id=sid,
            name=name,
            handler=handler,
            topics=topics or [],
            min_severity=sev,
            tags=tags or [],
            total_received=0,
            created_at=now,
        )
        self._subscribers[sid] = sub
        self._name_index[name] = sid
        for topic in sub.topics:
            self._topic_index.setdefault(topic, []).append(sid)
        self._total_subscribers += 1
        self._fire("subscriber_added", {"sub_id": sid, "name": name})
        return sid

    def unsubscribe(self, sub_id: str) -> bool:
        sub = self._subscribers.pop(sub_id, None)
        if not sub:
            return False
        self._name_index.pop(sub.name, None)
        for topic in sub.topics:
            tlist = self._topic_index.get(topic, [])
            if sub_id in tlist:
                tlist.remove(sub_id)
        self._fire("subscriber_removed", {"sub_id": sub_id, "name": sub.name})
        return True

    def unsubscribe_by_name(self, name: str) -> bool:
        sid = self._name_index.get(name)
        if not sid:
            return False
        return self.unsubscribe(sid)

    def get_subscriber(self, sub_id: str) -> Optional[Dict[str, Any]]:
        sub = self._subscribers.get(sub_id)
        if not sub:
            return None
        return {
            "sub_id": sub.sub_id,
            "name": sub.name,
            "topics": list(sub.topics),
            "min_severity": sub.min_severity,
            "tags": list(sub.tags),
            "total_received": sub.total_received,
            "created_at": sub.created_at,
        }

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        sid = self._name_index.get(name)
        if not sid:
            return None
        return self.get_subscriber(sid)

    # ------------------------------------------------------------------
    # Notification sending
    # ------------------------------------------------------------------

    def notify(
        self,
        source: str,
        topic: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send notification to matching subscribers. Returns notification id."""
        if not source or not message:
            return ""

        sev = self.SEVERITIES.get(severity, 1)
        self._seq += 1
        now = time.time()
        raw = f"{source}-{topic}-{now}-{self._seq}"
        nid = "ntf-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        delivered_to: List[str] = []

        # Find matching subscribers
        candidates: List[_Subscriber] = []
        if topic:
            # Topic-specific subscribers + subscribers with no topic filter
            topic_sids = self._topic_index.get(topic, [])
            for sid in topic_sids:
                sub = self._subscribers.get(sid)
                if sub:
                    candidates.append(sub)
            # Also add subscribers with empty topics (they get everything)
            for sub in self._subscribers.values():
                if not sub.topics and sub not in candidates:
                    candidates.append(sub)
        else:
            candidates = list(self._subscribers.values())

        for sub in candidates:
            if sev < sub.min_severity:
                continue
            try:
                sub.handler(source, topic, message, severity, data or {})
                delivered_to.append(sub.name)
                sub.total_received += 1
                self._total_delivered += 1
            except Exception:
                pass

        notif = _Notification(
            notif_id=nid,
            source=source,
            topic=topic,
            severity=sev,
            message=message,
            data=data or {},
            delivered_to=delivered_to,
            timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(notif)
        self._total_sent += 1

        self._fire("notification_sent", {
            "notif_id": nid, "source": source, "topic": topic,
            "delivered_count": len(delivered_to),
        })
        return nid

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_subscribers(
        self,
        topic: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for sub in self._subscribers.values():
            if topic and topic not in sub.topics:
                continue
            if tag and tag not in sub.tags:
                continue
            results.append(self.get_subscriber(sub.sub_id))
        return results

    def get_history(
        self,
        source: str = "",
        topic: str = "",
        severity: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        sev_filter = self.SEVERITIES.get(severity, -1) if severity else -1
        results = []
        for notif in reversed(self._history):
            if source and notif.source != source:
                continue
            if topic and notif.topic != topic:
                continue
            if sev_filter >= 0 and notif.severity != sev_filter:
                continue
            results.append({
                "notif_id": notif.notif_id,
                "source": notif.source,
                "topic": notif.topic,
                "severity": notif.severity,
                "message": notif.message,
                "delivered_to": list(notif.delivered_to),
                "timestamp": notif.timestamp,
            })
            if len(results) >= limit:
                break
        return results

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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
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
            "current_subscribers": len(self._subscribers),
            "total_subscribers": self._total_subscribers,
            "total_sent": self._total_sent,
            "total_delivered": self._total_delivered,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._subscribers.clear()
        self._name_index.clear()
        self._topic_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_subscribers = 0
        self._total_sent = 0
        self._total_delivered = 0
