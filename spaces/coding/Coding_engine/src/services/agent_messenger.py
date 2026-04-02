"""
Agent Messenger — Direct agent-to-agent communication protocol.

Provides:
- Direct messaging between named agents
- Channel-based group messaging (pub/sub)
- Request/reply pattern with correlation IDs
- Message history and delivery tracking
- Priority messaging with TTL
- Inbox management (read/unread, archive)

Usage:
    messenger = AgentMessenger(event_bus=event_bus)

    # Direct message
    messenger.send("Builder", "Tester", "Build complete, ready for tests", topic="handoff")

    # Channel messaging
    messenger.create_channel("build-status", description="Build status updates")
    messenger.subscribe("build-status", "Tester")
    messenger.subscribe("build-status", "Deployer")
    messenger.broadcast("build-status", "Builder", "Build v1.2 succeeded")

    # Request/reply
    req_id = messenger.request("Builder", "Planner", "Need architecture review for auth module")
    messenger.reply(req_id, "Planner", "Approved with suggestions: use JWT")

    # Inbox
    msgs = messenger.get_inbox("Tester")
    messenger.mark_read("Tester", msg_id)
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class MessageType(str, Enum):
    DIRECT = "direct"
    BROADCAST = "broadcast"
    REQUEST = "request"
    REPLY = "reply"
    SYSTEM = "system"


class MessagePriority(int, Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 8
    URGENT = 10


class DeliveryStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class Message:
    """A message between agents."""
    message_id: str
    sender: str
    recipient: str  # agent name or channel name
    body: str
    msg_type: MessageType = MessageType.DIRECT
    topic: str = ""
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: str = ""  # For request/reply pairing
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 0.0  # 0 = no expiry
    delivery_status: DeliveryStatus = DeliveryStatus.SENT
    read_at: Optional[float] = None
    channel: str = ""  # Set for broadcast messages

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


@dataclass
class Channel:
    """A named channel for group messaging."""
    name: str
    description: str = ""
    subscribers: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    message_count: int = 0
    creator: str = ""


class AgentMessenger:
    """Agent-to-agent messaging system with channels and request/reply."""

    def __init__(self, event_bus=None, max_history: int = 1000):
        self._event_bus = event_bus
        self._max_history = max_history

        # Agent inboxes: agent_name -> list of Message
        self._inboxes: Dict[str, List[Message]] = {}

        # All messages by ID for lookup
        self._messages: Dict[str, Message] = {}

        # Channels
        self._channels: Dict[str, Channel] = {}

        # Pending requests awaiting replies: correlation_id -> Message
        self._pending_requests: Dict[str, Message] = {}

        # Callbacks: agent_name -> list of callables
        self._on_message_callbacks: Dict[str, List[Callable]] = {}

        # Stats
        self._total_sent = 0
        self._total_delivered = 0
        self._total_broadcasts = 0
        self._total_requests = 0
        self._total_replies = 0
        self._total_expired = 0

    # ── Direct Messaging ──────────────────────────────────────────────

    def send(
        self,
        sender: str,
        recipient: str,
        body: str,
        topic: str = "",
        priority: MessagePriority = MessagePriority.NORMAL,
        ttl_seconds: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a direct message from one agent to another."""
        msg = Message(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            sender=sender,
            recipient=recipient,
            body=body,
            msg_type=MessageType.DIRECT,
            topic=topic,
            priority=priority,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )

        self._deliver(msg, recipient)
        self._total_sent += 1

        logger.debug(
            "message_sent",
            component="agent_messenger",
            sender=sender,
            recipient=recipient,
            topic=topic,
            msg_id=msg.message_id,
        )

        return msg.message_id

    # ── Channel Messaging ─────────────────────────────────────────────

    def create_channel(self, name: str, description: str = "", creator: str = "") -> Channel:
        """Create a named channel for group messaging."""
        if name in self._channels:
            return self._channels[name]

        channel = Channel(
            name=name,
            description=description,
            creator=creator,
        )
        self._channels[name] = channel

        logger.info(
            "channel_created",
            component="agent_messenger",
            channel=name,
            creator=creator,
        )
        return channel

    def delete_channel(self, name: str) -> bool:
        """Delete a channel."""
        if name not in self._channels:
            return False
        del self._channels[name]
        return True

    def subscribe(self, channel_name: str, agent_name: str) -> bool:
        """Subscribe an agent to a channel."""
        channel = self._channels.get(channel_name)
        if not channel:
            return False
        if agent_name in channel.subscribers:
            return False
        channel.subscribers.add(agent_name)

        logger.debug(
            "channel_subscribed",
            component="agent_messenger",
            channel=channel_name,
            agent=agent_name,
        )
        return True

    def unsubscribe(self, channel_name: str, agent_name: str) -> bool:
        """Unsubscribe an agent from a channel."""
        channel = self._channels.get(channel_name)
        if not channel or agent_name not in channel.subscribers:
            return False
        channel.subscribers.discard(agent_name)
        return True

    def broadcast(
        self,
        channel_name: str,
        sender: str,
        body: str,
        topic: str = "",
        priority: MessagePriority = MessagePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Broadcast a message to all subscribers of a channel."""
        channel = self._channels.get(channel_name)
        if not channel:
            logger.warning(
                "broadcast_channel_not_found",
                component="agent_messenger",
                channel=channel_name,
            )
            return ""

        msg_id = f"msg-{uuid.uuid4().hex[:8]}"

        delivered = 0
        for subscriber in channel.subscribers:
            if subscriber == sender:
                continue  # Don't deliver to sender
            msg = Message(
                message_id=f"{msg_id}-{subscriber[:4]}",
                sender=sender,
                recipient=subscriber,
                body=body,
                msg_type=MessageType.BROADCAST,
                topic=topic,
                priority=priority,
                channel=channel_name,
                metadata=metadata or {},
            )
            self._deliver(msg, subscriber)
            delivered += 1

        channel.message_count += 1
        self._total_broadcasts += 1

        logger.info(
            "broadcast_sent",
            component="agent_messenger",
            channel=channel_name,
            sender=sender,
            delivered_to=delivered,
        )
        return msg_id

    def get_channel(self, name: str) -> Optional[Channel]:
        """Get channel info."""
        return self._channels.get(name)

    def get_channel_subscribers(self, name: str) -> List[str]:
        """Get list of subscribers for a channel."""
        channel = self._channels.get(name)
        if not channel:
            return []
        return sorted(channel.subscribers)

    def list_channels(self) -> List[Dict[str, Any]]:
        """List all channels with subscriber counts."""
        return [
            {
                "name": ch.name,
                "description": ch.description,
                "subscribers": len(ch.subscribers),
                "message_count": ch.message_count,
                "creator": ch.creator,
            }
            for ch in self._channels.values()
        ]

    # ── Request/Reply ─────────────────────────────────────────────────

    def request(
        self,
        sender: str,
        recipient: str,
        body: str,
        topic: str = "",
        ttl_seconds: float = 60.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a request that expects a reply. Returns correlation_id."""
        correlation_id = f"req-{uuid.uuid4().hex[:8]}"

        msg = Message(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            sender=sender,
            recipient=recipient,
            body=body,
            msg_type=MessageType.REQUEST,
            topic=topic,
            priority=MessagePriority.HIGH,
            correlation_id=correlation_id,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )

        self._deliver(msg, recipient)
        self._pending_requests[correlation_id] = msg
        self._total_requests += 1

        logger.debug(
            "request_sent",
            component="agent_messenger",
            sender=sender,
            recipient=recipient,
            correlation_id=correlation_id,
        )
        return correlation_id

    def reply(
        self,
        correlation_id: str,
        sender: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Reply to a pending request."""
        req = self._pending_requests.get(correlation_id)
        if not req:
            logger.warning(
                "reply_no_pending_request",
                component="agent_messenger",
                correlation_id=correlation_id,
            )
            return None

        msg = Message(
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            sender=sender,
            recipient=req.sender,  # Reply goes back to original sender
            body=body,
            msg_type=MessageType.REPLY,
            topic=req.topic,
            priority=MessagePriority.HIGH,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        self._deliver(msg, req.sender)
        del self._pending_requests[correlation_id]
        self._total_replies += 1

        logger.debug(
            "reply_sent",
            component="agent_messenger",
            sender=sender,
            recipient=req.sender,
            correlation_id=correlation_id,
        )
        return msg.message_id

    def get_pending_requests(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get pending requests sent by an agent that haven't been replied to."""
        results = []
        for cid, msg in self._pending_requests.items():
            if msg.sender == agent_name:
                results.append({
                    "correlation_id": cid,
                    "recipient": msg.recipient,
                    "body": msg.body,
                    "topic": msg.topic,
                    "age_seconds": msg.age_seconds,
                    "is_expired": msg.is_expired,
                })
        return results

    def get_incoming_requests(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get requests waiting for this agent to reply."""
        results = []
        for cid, msg in self._pending_requests.items():
            if msg.recipient == agent_name:
                results.append({
                    "correlation_id": cid,
                    "sender": msg.sender,
                    "body": msg.body,
                    "topic": msg.topic,
                    "age_seconds": msg.age_seconds,
                })
        return results

    # ── Inbox Management ──────────────────────────────────────────────

    def get_inbox(
        self,
        agent_name: str,
        unread_only: bool = False,
        topic: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get messages in an agent's inbox."""
        inbox = self._inboxes.get(agent_name, [])

        # Clean expired
        self._cleanup_expired(agent_name)

        msgs = inbox
        if unread_only:
            msgs = [m for m in msgs if m.delivery_status != DeliveryStatus.READ]
        if topic:
            msgs = [m for m in msgs if m.topic == topic]

        # Sort by priority (desc) then time (desc)
        msgs = sorted(msgs, key=lambda m: (-m.priority.value, -m.created_at))

        results = []
        for m in msgs[:limit]:
            results.append({
                "message_id": m.message_id,
                "sender": m.sender,
                "body": m.body,
                "msg_type": m.msg_type.value,
                "topic": m.topic,
                "priority": m.priority.value,
                "channel": m.channel,
                "correlation_id": m.correlation_id,
                "age_seconds": round(m.age_seconds, 1),
                "is_read": m.delivery_status == DeliveryStatus.READ,
                "metadata": m.metadata,
            })
        return results

    def get_unread_count(self, agent_name: str) -> int:
        """Count unread messages for an agent."""
        inbox = self._inboxes.get(agent_name, [])
        return sum(1 for m in inbox if m.delivery_status == DeliveryStatus.DELIVERED)

    def mark_read(self, agent_name: str, message_id: str) -> bool:
        """Mark a message as read."""
        inbox = self._inboxes.get(agent_name, [])
        for msg in inbox:
            if msg.message_id == message_id:
                msg.delivery_status = DeliveryStatus.READ
                msg.read_at = time.time()
                return True
        return False

    def mark_all_read(self, agent_name: str) -> int:
        """Mark all messages as read for an agent."""
        inbox = self._inboxes.get(agent_name, [])
        count = 0
        for msg in inbox:
            if msg.delivery_status == DeliveryStatus.DELIVERED:
                msg.delivery_status = DeliveryStatus.READ
                msg.read_at = time.time()
                count += 1
        return count

    def delete_message(self, agent_name: str, message_id: str) -> bool:
        """Delete a message from an agent's inbox."""
        inbox = self._inboxes.get(agent_name, [])
        for i, msg in enumerate(inbox):
            if msg.message_id == message_id:
                inbox.pop(i)
                if message_id in self._messages:
                    del self._messages[message_id]
                return True
        return False

    def clear_inbox(self, agent_name: str) -> int:
        """Clear all messages from an agent's inbox."""
        inbox = self._inboxes.get(agent_name, [])
        count = len(inbox)
        for msg in inbox:
            self._messages.pop(msg.message_id, None)
        self._inboxes[agent_name] = []
        return count

    # ── Callbacks ─────────────────────────────────────────────────────

    def on_message(self, agent_name: str, callback: Callable) -> None:
        """Register a callback for when an agent receives a message."""
        if agent_name not in self._on_message_callbacks:
            self._on_message_callbacks[agent_name] = []
        self._on_message_callbacks[agent_name].append(callback)

    # ── Message Lookup ────────────────────────────────────────────────

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific message by ID."""
        msg = self._messages.get(message_id)
        if not msg:
            return None
        return {
            "message_id": msg.message_id,
            "sender": msg.sender,
            "recipient": msg.recipient,
            "body": msg.body,
            "msg_type": msg.msg_type.value,
            "topic": msg.topic,
            "priority": msg.priority.value,
            "correlation_id": msg.correlation_id,
            "channel": msg.channel,
            "delivery_status": msg.delivery_status.value,
            "age_seconds": round(msg.age_seconds, 1),
            "metadata": msg.metadata,
        }

    def get_conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get message history between two agents."""
        results = []
        for msg in self._messages.values():
            if (
                (msg.sender == agent_a and msg.recipient == agent_b) or
                (msg.sender == agent_b and msg.recipient == agent_a)
            ):
                results.append({
                    "message_id": msg.message_id,
                    "sender": msg.sender,
                    "recipient": msg.recipient,
                    "body": msg.body,
                    "msg_type": msg.msg_type.value,
                    "topic": msg.topic,
                    "age_seconds": round(msg.age_seconds, 1),
                })

        results.sort(key=lambda m: m["age_seconds"], reverse=True)
        return results[:limit]

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get messenger statistics."""
        total_inbox_msgs = sum(len(inbox) for inbox in self._inboxes.values())
        total_unread = sum(
            self.get_unread_count(agent) for agent in self._inboxes
        )

        return {
            "total_sent": self._total_sent,
            "total_delivered": self._total_delivered,
            "total_broadcasts": self._total_broadcasts,
            "total_requests": self._total_requests,
            "total_replies": self._total_replies,
            "total_expired": self._total_expired,
            "total_channels": len(self._channels),
            "total_inbox_messages": total_inbox_msgs,
            "total_unread": total_unread,
            "pending_requests": len(self._pending_requests),
            "agents_with_inboxes": list(self._inboxes.keys()),
        }

    def cleanup_expired(self) -> int:
        """Clean up expired messages across all inboxes."""
        total = 0
        for agent_name in list(self._inboxes.keys()):
            total += self._cleanup_expired(agent_name)
        # Also clean expired pending requests
        expired_reqs = [
            cid for cid, msg in self._pending_requests.items()
            if msg.is_expired
        ]
        for cid in expired_reqs:
            del self._pending_requests[cid]
            total += 1
        return total

    def reset(self):
        """Reset all messaging state."""
        self._inboxes.clear()
        self._messages.clear()
        self._channels.clear()
        self._pending_requests.clear()
        self._on_message_callbacks.clear()
        self._total_sent = 0
        self._total_delivered = 0
        self._total_broadcasts = 0
        self._total_requests = 0
        self._total_replies = 0
        self._total_expired = 0

    # ── Internal ──────────────────────────────────────────────────────

    def _deliver(self, msg: Message, recipient: str):
        """Deliver a message to a recipient's inbox."""
        if recipient not in self._inboxes:
            self._inboxes[recipient] = []

        msg.delivery_status = DeliveryStatus.DELIVERED
        self._inboxes[recipient].append(msg)
        self._messages[msg.message_id] = msg
        self._total_delivered += 1

        # Trim inbox if over limit
        inbox = self._inboxes[recipient]
        if len(inbox) > self._max_history:
            removed = inbox[:len(inbox) - self._max_history]
            self._inboxes[recipient] = inbox[len(inbox) - self._max_history:]
            for m in removed:
                self._messages.pop(m.message_id, None)

        # Fire callbacks
        callbacks = self._on_message_callbacks.get(recipient, [])
        for cb in callbacks:
            try:
                cb(msg)
            except Exception as e:
                logger.warning(
                    "message_callback_error",
                    component="agent_messenger",
                    recipient=recipient,
                    error=str(e),
                )

    def _cleanup_expired(self, agent_name: str) -> int:
        """Remove expired messages from an agent's inbox."""
        inbox = self._inboxes.get(agent_name, [])
        expired = [m for m in inbox if m.is_expired]

        for msg in expired:
            msg.delivery_status = DeliveryStatus.EXPIRED
            inbox.remove(msg)
            self._messages.pop(msg.message_id, None)
            self._total_expired += 1

        return len(expired)
