"""
Inter-Agent Protocol — typed message passing between agents with
channels, request/reply patterns, and broadcast support.

Features:
- Named channels with pub/sub
- Direct agent-to-agent messaging
- Request/reply pattern with correlation IDs
- Broadcast to groups
- Message history and replay
- Delivery tracking
- Priority messaging
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    DIRECT = "direct"
    BROADCAST = "broadcast"
    REQUEST = "request"
    REPLY = "reply"
    CHANNEL = "channel"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class Message:
    """A protocol message."""
    msg_id: str
    msg_type: MessageType
    sender: str
    recipient: str  # agent name, channel name, or group name
    subject: str
    body: Any
    priority: int = 50
    correlation_id: str = ""
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    delivered_at: float = 0.0


@dataclass
class Channel:
    """A named message channel."""
    name: str
    subscribers: Set[str] = field(default_factory=set)
    handler: Optional[Callable] = None
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Inter-Agent Protocol
# ---------------------------------------------------------------------------

class InterAgentProtocol:
    """Typed message passing between agents."""

    def __init__(self, max_messages: int = 5000, max_inbox: int = 200):
        self._max_messages = max_messages
        self._max_inbox = max_inbox

        # Channels: name → Channel
        self._channels: Dict[str, Channel] = {}

        # Agent inboxes: agent_name → deque of Message
        self._inboxes: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_inbox))

        # All messages for history
        self._messages: List[Message] = []

        # Pending replies: correlation_id → callback
        self._pending_replies: Dict[str, Callable] = {}

        # Agent handlers: agent_name → callback
        self._handlers: Dict[str, Callable] = {}

        self._stats = {
            "total_sent": 0,
            "total_delivered": 0,
            "total_failed": 0,
            "total_broadcasts": 0,
            "total_requests": 0,
            "total_replies": 0,
        }

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def create_channel(self, name: str, handler: Optional[Callable] = None) -> bool:
        """Create a named channel."""
        if name in self._channels:
            return False
        self._channels[name] = Channel(
            name=name,
            handler=handler,
            created_at=time.time(),
        )
        return True

    def delete_channel(self, name: str) -> bool:
        """Delete a channel."""
        if name not in self._channels:
            return False
        del self._channels[name]
        return True

    def list_channels(self) -> List[Dict]:
        """List all channels."""
        return sorted([{
            "name": ch.name,
            "subscribers": sorted(ch.subscribers),
            "subscriber_count": len(ch.subscribers),
        } for ch in self._channels.values()], key=lambda x: x["name"])

    def subscribe(self, channel_name: str, agent_name: str) -> bool:
        """Subscribe an agent to a channel."""
        ch = self._channels.get(channel_name)
        if not ch:
            return False
        ch.subscribers.add(agent_name)
        return True

    def unsubscribe(self, channel_name: str, agent_name: str) -> bool:
        """Unsubscribe an agent from a channel."""
        ch = self._channels.get(channel_name)
        if not ch or agent_name not in ch.subscribers:
            return False
        ch.subscribers.discard(agent_name)
        return True

    # ------------------------------------------------------------------
    # Agent handlers
    # ------------------------------------------------------------------

    def register_handler(self, agent_name: str, handler: Callable) -> None:
        """Register a message handler for an agent."""
        self._handlers[agent_name] = handler

    def unregister_handler(self, agent_name: str) -> bool:
        """Unregister agent handler."""
        if agent_name not in self._handlers:
            return False
        del self._handlers[agent_name]
        return True

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    def send(
        self,
        sender: str,
        recipient: str,
        subject: str,
        body: Any = None,
        priority: int = 50,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Send a direct message. Returns message ID."""
        msg = self._create_message(
            MessageType.DIRECT, sender, recipient, subject, body,
            priority=priority, metadata=metadata,
        )
        self._deliver_to_agent(msg, recipient)
        return msg.msg_id

    def broadcast(
        self,
        sender: str,
        group: str,
        subject: str,
        body: Any = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Broadcast to all agents in a group/channel. Returns message ID."""
        msg = self._create_message(
            MessageType.BROADCAST, sender, group, subject, body,
            metadata=metadata,
        )
        self._stats["total_broadcasts"] += 1

        # If it's a channel, deliver to subscribers
        ch = self._channels.get(group)
        if ch:
            for sub in ch.subscribers:
                self._deliver_to_agent(msg, sub)
            if ch.handler:
                try:
                    ch.handler(self._msg_to_dict(msg))
                except Exception:
                    pass

        return msg.msg_id

    def request(
        self,
        sender: str,
        recipient: str,
        subject: str,
        body: Any = None,
        reply_handler: Optional[Callable] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Send a request expecting a reply. Returns correlation ID."""
        cid = f"corr-{uuid.uuid4().hex[:8]}"
        msg = self._create_message(
            MessageType.REQUEST, sender, recipient, subject, body,
            correlation_id=cid, metadata=metadata,
        )
        self._stats["total_requests"] += 1

        if reply_handler:
            self._pending_replies[cid] = reply_handler

        self._deliver_to_agent(msg, recipient)
        return cid

    def reply(
        self,
        sender: str,
        correlation_id: str,
        body: Any = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Reply to a request. Returns message ID or None if no correlation."""
        # Find original request
        original = None
        for m in reversed(self._messages):
            if m.correlation_id == correlation_id and m.msg_type == MessageType.REQUEST:
                original = m
                break

        if not original:
            return None

        msg = self._create_message(
            MessageType.REPLY, sender, original.sender, f"RE: {original.subject}",
            body, correlation_id=correlation_id, metadata=metadata,
        )
        self._stats["total_replies"] += 1

        # Deliver to original sender
        self._deliver_to_agent(msg, original.sender)

        # Fire reply handler if registered
        handler = self._pending_replies.pop(correlation_id, None)
        if handler:
            try:
                handler(self._msg_to_dict(msg))
            except Exception:
                pass

        return msg.msg_id

    def publish(
        self,
        sender: str,
        channel_name: str,
        subject: str,
        body: Any = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Publish to a channel. Returns message ID."""
        ch = self._channels.get(channel_name)
        if not ch:
            return None

        msg = self._create_message(
            MessageType.CHANNEL, sender, channel_name, subject, body,
            metadata=metadata,
        )

        for sub in ch.subscribers:
            self._deliver_to_agent(msg, sub)

        if ch.handler:
            try:
                ch.handler(self._msg_to_dict(msg))
            except Exception:
                pass

        return msg.msg_id

    # ------------------------------------------------------------------
    # Inbox operations
    # ------------------------------------------------------------------

    def get_inbox(
        self,
        agent_name: str,
        limit: int = 50,
        subject_filter: str = "",
        msg_type: Optional[str] = None,
    ) -> List[Dict]:
        """Get messages from an agent's inbox."""
        inbox = self._inboxes.get(agent_name, deque())
        results = []
        for msg in reversed(inbox):
            if subject_filter and subject_filter.lower() not in msg.subject.lower():
                continue
            if msg_type and msg.msg_type.value != msg_type:
                continue
            results.append(self._msg_to_dict(msg))
            if len(results) >= limit:
                break
        return list(reversed(results))

    def get_inbox_count(self, agent_name: str) -> int:
        """Get count of messages in inbox."""
        return len(self._inboxes.get(agent_name, deque()))

    def clear_inbox(self, agent_name: str) -> int:
        """Clear an agent's inbox. Returns count cleared."""
        inbox = self._inboxes.get(agent_name, deque())
        count = len(inbox)
        inbox.clear()
        return count

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        msg_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get message history with filters."""
        results = []
        for msg in reversed(self._messages):
            if sender and msg.sender != sender:
                continue
            if recipient and msg.recipient != recipient:
                continue
            if msg_type and msg.msg_type.value != msg_type:
                continue
            results.append(self._msg_to_dict(msg))
            if len(results) >= limit:
                break
        return list(reversed(results))

    def get_message(self, msg_id: str) -> Optional[Dict]:
        """Get a specific message."""
        for msg in reversed(self._messages):
            if msg.msg_id == msg_id:
                return self._msg_to_dict(msg)
        return None

    def get_conversation(self, correlation_id: str) -> List[Dict]:
        """Get all messages in a request/reply conversation."""
        return [self._msg_to_dict(m) for m in self._messages
                if m.correlation_id == correlation_id]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_message(
        self,
        msg_type: MessageType,
        sender: str,
        recipient: str,
        subject: str,
        body: Any,
        priority: int = 50,
        correlation_id: str = "",
        metadata: Optional[Dict] = None,
    ) -> Message:
        msg = Message(
            msg_id=f"msg-{uuid.uuid4().hex[:8]}",
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            priority=priority,
            correlation_id=correlation_id,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._messages.append(msg)
        self._stats["total_sent"] += 1
        self._prune_messages()
        return msg

    def _deliver_to_agent(self, msg: Message, agent_name: str) -> None:
        self._inboxes[agent_name].append(msg)
        msg.delivery_status = DeliveryStatus.DELIVERED
        msg.delivered_at = time.time()
        self._stats["total_delivered"] += 1

        # Fire handler if registered
        handler = self._handlers.get(agent_name)
        if handler:
            try:
                handler(self._msg_to_dict(msg))
            except Exception:
                self._stats["total_failed"] += 1

    def _msg_to_dict(self, msg: Message) -> Dict:
        return {
            "msg_id": msg.msg_id,
            "msg_type": msg.msg_type.value,
            "sender": msg.sender,
            "recipient": msg.recipient,
            "subject": msg.subject,
            "body": msg.body,
            "priority": msg.priority,
            "correlation_id": msg.correlation_id,
            "timestamp": msg.timestamp,
            "metadata": msg.metadata,
            "delivery_status": msg.delivery_status.value,
        }

    def _prune_messages(self) -> None:
        if len(self._messages) > self._max_messages:
            keep = self._max_messages // 2
            self._messages = self._messages[-keep:]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_channels": len(self._channels),
            "total_handlers": len(self._handlers),
            "total_pending_replies": len(self._pending_replies),
            "total_messages_stored": len(self._messages),
        }

    def reset(self) -> None:
        self._channels.clear()
        self._inboxes.clear()
        self._messages.clear()
        self._pending_replies.clear()
        self._handlers.clear()
        self._stats = {k: 0 for k in self._stats}
