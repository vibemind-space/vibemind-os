"""Agent Message Broker -- brokers messages between agents via topics.

Agents can publish messages to topics and subscribe to topics to receive
messages.  The broker maintains an in-memory store of messages keyed by
topic and a registry of subscriptions.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the message broker."""

    messages: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    subscriptions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentMessageBroker:
    """In-memory message broker for inter-agent communication.

    Parameters
    ----------
    max_entries:
        Maximum total number of messages to keep.  When the limit
        is reached the oldest quarter of messages is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()

        # stats counters
        self._stats: Dict[str, int] = {
            "total_published": 0,
            "total_subscribed": 0,
            "total_unsubscribed": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_message_broker.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, *parts: Any) -> str:
        """Create a collision-free ID using SHA-256 + _seq."""
        raw = "-".join(str(p) for p in parts) + f"-{self._state._seq}"
        return "amb-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Total message count (internal)
    # ------------------------------------------------------------------

    def _total_messages(self) -> int:
        """Return the total number of messages across all topics."""
        return sum(len(v) for v in self._state.messages.values())

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, agent_id: str, topic: str) -> str:
        """Subscribe an agent to a topic.

        Returns the generated ``amb-...`` subscription ID.
        """
        with self._lock:
            self._state._seq += 1
            now = time.time()
            sub_id = self._generate_id(agent_id, topic, now)

            self._state.subscriptions[sub_id] = {
                "sub_id": sub_id,
                "agent_id": agent_id,
                "topic": topic,
                "timestamp": now,
            }
            self._stats["total_subscribed"] += 1

        logger.debug(
            "agent_message_broker.subscribe",
            sub_id=sub_id,
            agent_id=agent_id,
            topic=topic,
        )
        self._fire("subscribed", {
            "sub_id": sub_id,
            "agent_id": agent_id,
            "topic": topic,
        })
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription.

        Returns ``True`` if the subscription existed and was removed.
        """
        with self._lock:
            if sub_id in self._state.subscriptions:
                info = self._state.subscriptions.pop(sub_id)
                self._stats["total_unsubscribed"] += 1
                removed = True
            else:
                info = None
                removed = False

        if removed:
            logger.debug(
                "agent_message_broker.unsubscribe",
                sub_id=sub_id,
            )
            self._fire("unsubscribed", {
                "sub_id": sub_id,
                "agent_id": info["agent_id"],
                "topic": info["topic"],
            })
        return removed

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        agent_id: str,
        topic: str,
        message: str,
        payload: dict = None,
    ) -> str:
        """Publish a message to a topic.

        Returns the generated ``amb-...`` message ID.
        """
        with self._lock:
            # prune if at capacity
            if self._total_messages() >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            msg_id = self._generate_id(agent_id, topic, message, now)

            entry: Dict[str, Any] = {
                "message_id": msg_id,
                "agent_id": agent_id,
                "topic": topic,
                "message": message,
                "payload": payload,
                "timestamp": now,
            }

            self._state.messages.setdefault(topic, []).append(entry)
            self._stats["total_published"] += 1

        logger.debug(
            "agent_message_broker.publish",
            message_id=msg_id,
            agent_id=agent_id,
            topic=topic,
        )
        self._fire("published", {
            "message_id": msg_id,
            "agent_id": agent_id,
            "topic": topic,
            "message": message,
        })
        return msg_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_messages(self, topic: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent messages for a topic (most recent last), up to *limit*."""
        with self._lock:
            self._stats["total_queries"] += 1
            entries = list(self._state.messages.get(topic, []))
            return entries[-limit:]

    def get_subscribers(self, topic: str) -> List[str]:
        """Get list of agent IDs subscribed to a topic."""
        with self._lock:
            self._stats["total_queries"] += 1
            return [
                sub["agent_id"]
                for sub in self._state.subscriptions.values()
                if sub["topic"] == topic
            ]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_subscription_count(self, agent_id: str = "") -> int:
        """Count subscriptions.  If *agent_id* given, count for that agent."""
        with self._lock:
            if not agent_id:
                return len(self._state.subscriptions)
            return sum(
                1 for sub in self._state.subscriptions.values()
                if sub["agent_id"] == agent_id
            )

    def get_message_count(self, topic: str = "") -> int:
        """Count messages.  If *topic* given, count for that topic only."""
        with self._lock:
            if not topic:
                return self._total_messages()
            return len(self._state.messages.get(topic, []))

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_topics(self) -> List[str]:
        """List all topics that have messages or subscribers."""
        with self._lock:
            topics: set = set()
            for topic, msgs in self._state.messages.items():
                if msgs:
                    topics.add(topic)
            for sub in self._state.subscriptions.values():
                topics.add(sub["topic"])
            return sorted(topics)

    def list_agents(self) -> List[str]:
        """List all agents that have subscriptions."""
        with self._lock:
            agents: set = set()
            for sub in self._state.subscriptions.values():
                agents.add(sub["agent_id"])
            return sorted(agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            topics: set = set()
            for topic, msgs in self._state.messages.items():
                if msgs:
                    topics.add(topic)
            for sub in self._state.subscriptions.values():
                topics.add(sub["topic"])
            return {
                **self._stats,
                "current_messages": self._total_messages(),
                "current_subscriptions": len(self._state.subscriptions),
                "unique_topics": len(topics),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.messages.clear()
            self._state.subscriptions.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_message_broker.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of messages when at capacity."""
        all_entries: List[tuple] = []
        for topic, msgs in self._state.messages.items():
            for msg in msgs:
                all_entries.append((topic, msg))

        all_entries.sort(key=lambda x: x[1]["timestamp"])
        to_remove = max(len(all_entries) // 4, 1)

        for topic, msg in all_entries[:to_remove]:
            topic_list = self._state.messages.get(topic, [])
            try:
                topic_list.remove(msg)
            except ValueError:
                pass

        self._stats["total_pruned"] += to_remove
        logger.debug("agent_message_broker.prune", removed=to_remove)
