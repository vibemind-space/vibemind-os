"""Pipeline Event Mesh — lightweight pub/sub event mesh connecting pipeline modules.

Supports topic-based routing, wildcard subscriptions via glob patterns,
event filtering with custom predicates, and dead-letter queues for
failed deliveries.
"""

from __future__ import annotations

import fnmatch
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Topic:
    topic_id: str
    name: str
    event_count: int
    last_event_at: float
    tags: List[str]
    created_at: float


@dataclass
class _Subscription:
    sub_id: str
    topic_name: str
    subscriber_id: str
    has_handler: bool
    has_filter: bool
    created_at: float


@dataclass
class _MeshEvent:
    event_id: str
    topic_name: str
    publisher: str
    data: Dict[str, Any]
    delivered_to: List[str]
    failed_to: List[str]
    timestamp: float


@dataclass
class _DeadLetter:
    letter_id: str
    event_id: str
    topic_name: str
    subscriber_id: str
    error: str
    timestamp: float


@dataclass
class _MeshHistoryEntry:
    entry_id: str
    topic_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class PipelineEventMesh:
    """Lightweight pub/sub event mesh connecting all pipeline modules."""

    def __init__(self, max_topics: int = 5000, max_history: int = 100000):
        self._max_topics = max_topics
        self._max_history = max_history
        self._topics: Dict[str, _Topic] = {}
        self._subscriptions: Dict[str, _Subscription] = {}
        self._handlers: Dict[str, Callable] = {}
        self._filters: Dict[str, Callable] = {}
        self._topic_subs: Dict[str, List[str]] = {}
        self._dead_letters: List[_DeadLetter] = []
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0
        self._total_topics_created = 0
        self._total_events_published = 0
        self._total_deliveries = 0
        self._total_failures = 0

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------

    def create_topic(self, name: str, tags: Optional[List[str]] = None) -> str:
        if not name or name in self._topics or len(self._topics) >= self._max_topics:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        topic_id = "top-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        topic = _Topic(
            topic_id=topic_id,
            name=name,
            event_count=0,
            last_event_at=0.0,
            tags=tags or [],
            created_at=now,
        )
        self._topics[name] = topic
        self._topic_subs[name] = []
        self._total_topics_created += 1
        self._record("topic_created", name, {"topic_id": topic_id})
        self._fire("topic_created", {"name": name, "topic_id": topic_id})
        return topic_id

    def get_topic(self, name: str) -> Optional[Dict[str, Any]]:
        topic = self._topics.get(name)
        if not topic:
            return None
        return {
            "topic_id": topic.topic_id,
            "name": topic.name,
            "event_count": topic.event_count,
            "last_event_at": topic.last_event_at,
            "tags": list(topic.tags),
            "subscriber_count": len(self._topic_subs.get(name, [])),
            "created_at": topic.created_at,
        }

    def list_topics(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for topic in self._topics.values():
            if tag and tag not in topic.tags:
                continue
            results.append(self.get_topic(topic.name))
        return [r for r in results if r]

    def remove_topic(self, name: str) -> bool:
        if name not in self._topics:
            return False
        sub_ids = list(self._topic_subs.get(name, []))
        for sid in sub_ids:
            self._remove_sub(sid)
        self._topics.pop(name, None)
        self._topic_subs.pop(name, None)
        self._record("topic_removed", name, {})
        self._fire("topic_removed", {"name": name})
        return True

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic_name: str,
        subscriber_id: str,
        handler: Optional[Callable] = None,
        filter_fn: Optional[Callable] = None,
    ) -> str:
        if not topic_name or not subscriber_id:
            return ""
        if topic_name not in self._topics:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{topic_name}-{subscriber_id}-{now}-{self._seq}"
        sub_id = "sub-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        sub = _Subscription(
            sub_id=sub_id,
            topic_name=topic_name,
            subscriber_id=subscriber_id,
            has_handler=handler is not None,
            has_filter=filter_fn is not None,
            created_at=now,
        )
        self._subscriptions[sub_id] = sub
        if handler is not None:
            self._handlers[sub_id] = handler
        if filter_fn is not None:
            self._filters[sub_id] = filter_fn
        self._topic_subs[topic_name].append(sub_id)
        self._record("subscribed", topic_name, {"sub_id": sub_id, "subscriber_id": subscriber_id})
        self._fire("subscribed", {"topic_name": topic_name, "subscriber_id": subscriber_id})
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        return self._remove_sub(subscription_id)

    def _remove_sub(self, sub_id: str) -> bool:
        sub = self._subscriptions.pop(sub_id, None)
        if not sub:
            return False
        self._handlers.pop(sub_id, None)
        self._filters.pop(sub_id, None)
        subs_list = self._topic_subs.get(sub.topic_name)
        if subs_list and sub_id in subs_list:
            subs_list.remove(sub_id)
        self._record("unsubscribed", sub.topic_name, {"sub_id": sub_id})
        return True

    def get_subscription(self, sub_id: str) -> Optional[Dict[str, Any]]:
        sub = self._subscriptions.get(sub_id)
        if not sub:
            return None
        return {
            "sub_id": sub.sub_id,
            "topic_name": sub.topic_name,
            "subscriber_id": sub.subscriber_id,
            "has_handler": sub.has_handler,
            "has_filter": sub.has_filter,
            "created_at": sub.created_at,
        }

    def list_subscriptions(self, topic_name: str = "", subscriber_id: str = "") -> List[Dict[str, Any]]:
        results = []
        for sub in self._subscriptions.values():
            if topic_name and sub.topic_name != topic_name:
                continue
            if subscriber_id and sub.subscriber_id != subscriber_id:
                continue
            results.append(self.get_subscription(sub.sub_id))
        return [r for r in results if r]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, topic_name: str, event_data: Dict[str, Any], publisher: str = "") -> str:
        if topic_name not in self._topics:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{topic_name}-{publisher}-{now}-{self._seq}"
        event_id = "evt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        topic = self._topics[topic_name]
        topic.event_count += 1
        topic.last_event_at = now
        delivered_to: List[str] = []
        failed_to: List[str] = []
        sub_ids = list(self._topic_subs.get(topic_name, []))
        for sid in sub_ids:
            sub = self._subscriptions.get(sid)
            if not sub:
                continue
            # Apply filter
            filter_fn = self._filters.get(sid)
            if filter_fn is not None:
                try:
                    if not filter_fn(event_data):
                        continue
                except Exception:
                    continue
            # Deliver via handler
            handler = self._handlers.get(sid)
            if handler is not None:
                try:
                    handler(event_data)
                    delivered_to.append(sub.subscriber_id)
                    self._total_deliveries += 1
                except Exception as exc:
                    failed_to.append(sub.subscriber_id)
                    self._total_failures += 1
                    self._add_dead_letter(event_id, topic_name, sub.subscriber_id, str(exc))
            else:
                delivered_to.append(sub.subscriber_id)
                self._total_deliveries += 1
        self._total_events_published += 1
        self._record("published", topic_name, {"event_id": event_id, "publisher": publisher})
        self._fire("event_published", {"topic_name": topic_name, "event_id": event_id})
        return event_id

    def publish_pattern(self, pattern: str, event_data: Dict[str, Any], publisher: str = "") -> int:
        if not pattern:
            return 0
        matched = 0
        for topic_name in list(self._topics.keys()):
            if fnmatch.fnmatch(topic_name, pattern):
                result = self.publish(topic_name, event_data, publisher=publisher)
                if result:
                    matched += 1
        return matched

    # ------------------------------------------------------------------
    # Dead letters
    # ------------------------------------------------------------------

    def _add_dead_letter(self, event_id: str, topic_name: str, subscriber_id: str, error: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"dl-{event_id}-{subscriber_id}-{now}-{self._seq}"
        letter_id = "dlq-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        dl = _DeadLetter(
            letter_id=letter_id,
            event_id=event_id,
            topic_name=topic_name,
            subscriber_id=subscriber_id,
            error=error,
            timestamp=now,
        )
        self._dead_letters.append(dl)

    def get_dead_letters(self, topic_name: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for dl in reversed(self._dead_letters):
            if topic_name and dl.topic_name != topic_name:
                continue
            results.append({
                "letter_id": dl.letter_id,
                "event_id": dl.event_id,
                "topic_name": dl.topic_name,
                "subscriber_id": dl.subscriber_id,
                "error": dl.error,
                "timestamp": dl.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record(self, action: str, topic_name: str, data: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{topic_name}-{action}-{now}-{self._seq}"
        entry_id = "mhe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append({
            "entry_id": entry_id,
            "topic_name": topic_name,
            "action": action,
            "data": data,
            "timestamp": now,
        })

    def get_history(self, topic_name: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for entry in reversed(self._history):
            if topic_name and entry["topic_name"] != topic_name:
                continue
            if action and entry["action"] != action:
                continue
            results.append(entry)
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
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_topics": len(self._topics),
            "current_subscriptions": len(self._subscriptions),
            "total_topics_created": self._total_topics_created,
            "total_events_published": self._total_events_published,
            "total_deliveries": self._total_deliveries,
            "total_failures": self._total_failures,
            "dead_letter_count": len(self._dead_letters),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._topics.clear()
        self._subscriptions.clear()
        self._handlers.clear()
        self._filters.clear()
        self._topic_subs.clear()
        self._dead_letters.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_topics_created = 0
        self._total_events_published = 0
        self._total_deliveries = 0
        self._total_failures = 0
