"""
Agent Communication Bus — high-level communication bus for agent coordination.

Features:
- Topic-based publish/subscribe messaging
- Request/response pattern with correlation
- Message queues per agent
- Message filtering and routing rules
- Broadcast and multicast support
- Message history and replay
- Dead letter queue for undeliverable messages
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BusMessage:
    """A message on the communication bus."""
    message_id: str
    topic: str
    sender: str
    payload: Any
    timestamp: float
    reply_to: str  # correlation ID for request/reply
    ttl: float  # seconds, 0 = no expiry
    headers: Dict[str, str]
    delivered_to: Set[str]


@dataclass
class Subscription:
    """A topic subscription."""
    sub_id: str
    agent: str
    topic: str  # supports "*" wildcard
    created_at: float
    filter_fn: Optional[Callable] = None


# ---------------------------------------------------------------------------
# Agent Communication Bus
# ---------------------------------------------------------------------------

class AgentCommunicationBus:
    """High-level communication bus for agent coordination."""

    def __init__(
        self,
        max_queue_size: int = 1000,
        max_history: int = 5000,
        dead_letter_limit: int = 500,
    ):
        self._max_queue_size = max_queue_size
        self._max_history = max_history
        self._dead_letter_limit = dead_letter_limit

        self._agents: Set[str] = set()
        self._subscriptions: Dict[str, Subscription] = {}
        self._queues: Dict[str, deque] = {}  # agent -> message queue
        self._history: List[BusMessage] = []
        self._dead_letters: List[BusMessage] = []

        self._stats = {
            "total_published": 0,
            "total_delivered": 0,
            "total_dead_letters": 0,
            "total_requests": 0,
            "total_replies": 0,
        }

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def register_agent(self, agent_name: str) -> bool:
        """Register an agent on the bus."""
        if agent_name in self._agents:
            return False
        self._agents.add(agent_name)
        self._queues[agent_name] = deque(maxlen=self._max_queue_size)
        return True

    def unregister_agent(self, agent_name: str) -> bool:
        """Unregister an agent."""
        if agent_name not in self._agents:
            return False
        self._agents.discard(agent_name)
        self._queues.pop(agent_name, None)
        # Remove subscriptions
        to_remove = [sid for sid, s in self._subscriptions.items()
                     if s.agent == agent_name]
        for sid in to_remove:
            del self._subscriptions[sid]
        return True

    def list_agents(self) -> List[str]:
        """List registered agents."""
        return sorted(self._agents)

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        agent: str,
        topic: str,
        filter_fn: Optional[Callable] = None,
    ) -> Optional[str]:
        """Subscribe an agent to a topic. Returns sub_id."""
        if agent not in self._agents:
            return None
        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        self._subscriptions[sub_id] = Subscription(
            sub_id=sub_id,
            agent=agent,
            topic=topic,
            created_at=time.time(),
            filter_fn=filter_fn,
        )
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription."""
        if sub_id not in self._subscriptions:
            return False
        del self._subscriptions[sub_id]
        return True

    def list_subscriptions(self, agent: Optional[str] = None) -> List[Dict]:
        """List subscriptions."""
        results = []
        for s in self._subscriptions.values():
            if agent and s.agent != agent:
                continue
            results.append({
                "sub_id": s.sub_id,
                "agent": s.agent,
                "topic": s.topic,
                "created_at": s.created_at,
            })
        return results

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(
        self,
        topic: str,
        sender: str,
        payload: Any = None,
        headers: Optional[Dict[str, str]] = None,
        ttl: float = 0.0,
    ) -> str:
        """Publish a message to a topic. Returns message_id."""
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        msg = BusMessage(
            message_id=msg_id,
            topic=topic,
            sender=sender,
            payload=payload,
            timestamp=time.time(),
            reply_to="",
            ttl=ttl,
            headers=headers or {},
            delivered_to=set(),
        )
        self._deliver(msg)
        self._stats["total_published"] += 1
        self._add_to_history(msg)
        return msg_id

    def send_direct(
        self,
        target: str,
        sender: str,
        payload: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Send a message directly to a specific agent."""
        if target not in self._agents:
            return False
        msg = BusMessage(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            topic=f"__direct__.{target}",
            sender=sender,
            payload=payload,
            timestamp=time.time(),
            reply_to="",
            ttl=0.0,
            headers=headers or {},
            delivered_to=set(),
        )
        q = self._queues.get(target)
        if q is not None:
            q.append(msg)
            msg.delivered_to.add(target)
            self._stats["total_delivered"] += 1
        self._stats["total_published"] += 1
        self._add_to_history(msg)
        return True

    def request(
        self,
        topic: str,
        sender: str,
        payload: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Send a request message. Returns correlation_id for reply matching."""
        corr_id = f"corr-{uuid.uuid4().hex[:8]}"
        msg = BusMessage(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            topic=topic,
            sender=sender,
            payload=payload,
            timestamp=time.time(),
            reply_to=corr_id,
            ttl=0.0,
            headers=headers or {},
            delivered_to=set(),
        )
        self._deliver(msg)
        self._stats["total_published"] += 1
        self._stats["total_requests"] += 1
        self._add_to_history(msg)
        return corr_id

    def reply(
        self,
        correlation_id: str,
        sender: str,
        target: str,
        payload: Any = None,
    ) -> bool:
        """Send a reply to a request."""
        if target not in self._agents:
            return False
        msg = BusMessage(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            topic=f"__reply__.{correlation_id}",
            sender=sender,
            payload=payload,
            timestamp=time.time(),
            reply_to=correlation_id,
            ttl=0.0,
            headers={},
            delivered_to=set(),
        )
        q = self._queues.get(target)
        if q is not None:
            q.append(msg)
            msg.delivered_to.add(target)
            self._stats["total_delivered"] += 1
        self._stats["total_replies"] += 1
        self._add_to_history(msg)
        return True

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def receive(self, agent: str, limit: int = 10) -> List[Dict]:
        """Receive messages from an agent's queue."""
        q = self._queues.get(agent)
        if not q:
            return []
        msgs = []
        for _ in range(min(limit, len(q))):
            msg = q.popleft()
            msgs.append(self._msg_to_dict(msg))
        return msgs

    def peek(self, agent: str, limit: int = 10) -> List[Dict]:
        """Peek at messages without removing them."""
        q = self._queues.get(agent)
        if not q:
            return []
        return [self._msg_to_dict(msg) for msg in list(q)[:limit]]

    def queue_size(self, agent: str) -> int:
        """Get queue size for an agent."""
        q = self._queues.get(agent)
        return len(q) if q else 0

    def drain(self, agent: str) -> int:
        """Drain all messages from an agent's queue. Returns count."""
        q = self._queues.get(agent)
        if not q:
            return 0
        count = len(q)
        q.clear()
        return count

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        topic: Optional[str] = None,
        sender: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get message history."""
        results = []
        for msg in reversed(self._history):
            if topic and msg.topic != topic:
                continue
            if sender and msg.sender != sender:
                continue
            results.append(self._msg_to_dict(msg))
            if len(results) >= limit:
                break
        return results

    def get_dead_letters(self, limit: int = 50) -> List[Dict]:
        """Get dead letter queue."""
        return [self._msg_to_dict(msg) for msg in self._dead_letters[-limit:]]

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------

    def list_topics(self) -> List[str]:
        """List all topics with active subscriptions."""
        topics = set()
        for s in self._subscriptions.values():
            topics.add(s.topic)
        return sorted(topics)

    def get_topic_subscribers(self, topic: str) -> List[str]:
        """Get agents subscribed to a topic."""
        agents = set()
        for s in self._subscriptions.values():
            if self._topic_matches(s.topic, topic):
                agents.add(s.agent)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def _deliver(self, msg: BusMessage) -> None:
        """Deliver a message to matching subscribers."""
        now = time.time()
        delivered = False

        for s in self._subscriptions.values():
            if not self._topic_matches(s.topic, msg.topic):
                continue
            if s.agent == msg.sender:
                continue  # Don't deliver to sender
            if s.filter_fn:
                try:
                    if not s.filter_fn(msg.payload):
                        continue
                except Exception:
                    continue

            # Check TTL
            if msg.ttl > 0 and now - msg.timestamp > msg.ttl:
                continue

            q = self._queues.get(s.agent)
            if q is not None:
                q.append(msg)
                msg.delivered_to.add(s.agent)
                self._stats["total_delivered"] += 1
                delivered = True

        if not delivered and not msg.topic.startswith("__"):
            self._dead_letters.append(msg)
            self._stats["total_dead_letters"] += 1
            if len(self._dead_letters) > self._dead_letter_limit:
                self._dead_letters = self._dead_letters[-self._dead_letter_limit:]

    def _topic_matches(self, pattern: str, topic: str) -> bool:
        """Check if a subscription pattern matches a topic."""
        if pattern == "*":
            return True
        if pattern == topic:
            return True
        # Simple prefix wildcard: "build.*" matches "build.start"
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic.startswith(prefix + ".")
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _msg_to_dict(self, msg: BusMessage) -> Dict:
        return {
            "message_id": msg.message_id,
            "topic": msg.topic,
            "sender": msg.sender,
            "payload": msg.payload,
            "timestamp": msg.timestamp,
            "reply_to": msg.reply_to,
            "ttl": msg.ttl,
            "headers": msg.headers,
            "delivered_to": sorted(msg.delivered_to),
        }

    def _add_to_history(self, msg: BusMessage) -> None:
        self._history.append(msg)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        total_queued = sum(len(q) for q in self._queues.values())
        return {
            **self._stats,
            "total_agents": len(self._agents),
            "total_subscriptions": len(self._subscriptions),
            "total_queued": total_queued,
            "total_history": len(self._history),
            "dead_letter_count": len(self._dead_letters),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._subscriptions.clear()
        self._queues.clear()
        self._history.clear()
        self._dead_letters.clear()
        self._stats = {k: 0 for k in self._stats}
