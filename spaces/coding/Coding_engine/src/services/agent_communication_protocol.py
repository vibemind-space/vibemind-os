"""Agent Communication Protocol – structured communication between agents.

Defines message types (request, response, notification, broadcast),
channels with topic/direct/broadcast semantics, and delivery guarantees
(at-least-once via acknowledgement tracking).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Channel:
    channel_id: str
    name: str
    channel_type: str
    tags: List[str]
    created_at: float


@dataclass
class _Subscription:
    sub_id: str
    channel_name: str
    agent_id: str
    last_read_seq: int
    subscribed_at: float


@dataclass
class _Message:
    message_id: str
    channel_name: str
    sender: str
    msg_type: str
    payload: Dict[str, Any]
    requires_ack: bool
    seq_num: int
    acked_by: List[str]
    created_at: float


@dataclass
class _ProtocolEvent:
    event_id: str
    channel_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentCommunicationProtocol:
    """Structured communication protocol between agents."""

    def __init__(self, max_channels: int = 5000, max_history: int = 100000):
        self._channels: Dict[str, _Channel] = {}
        self._name_index: Dict[str, str] = {}
        self._subscriptions: Dict[str, List[_Subscription]] = {}
        self._messages: Dict[str, _Message] = {}
        self._channel_messages: Dict[str, List[str]] = {}
        self._channel_seq: Dict[str, int] = {}
        self._history: List[_ProtocolEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_channels = max_channels
        self._max_history = max_history
        self._seq = 0
        self._total_channels_created = 0
        self._total_messages_sent = 0
        self._total_acks = 0

    def create_channel(self, name: str, channel_type: str = "topic", tags: Optional[List[str]] = None) -> str:
        if not name or channel_type not in ("topic", "direct", "broadcast"):
            return ""
        if name in self._name_index or len(self._channels) >= self._max_channels:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        cid = "ach-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        channel = _Channel(channel_id=cid, name=name, channel_type=channel_type, tags=tags or [], created_at=now)
        self._channels[cid] = channel
        self._name_index[name] = cid
        self._subscriptions[name] = []
        self._channel_messages[name] = []
        self._channel_seq[name] = 0
        self._total_channels_created += 1
        self._record_event(name, "channel_created", {"channel_id": cid, "channel_type": channel_type})
        self._fire("channel_created", {"channel_id": cid, "name": name, "channel_type": channel_type})
        return cid

    def subscribe(self, channel_name: str, agent_id: str) -> bool:
        if channel_name not in self._name_index or not agent_id:
            return False
        subs = self._subscriptions[channel_name]
        for s in subs:
            if s.agent_id == agent_id:
                return False
        self._seq += 1
        now = time.time()
        raw = f"{channel_name}-{agent_id}-{now}-{self._seq}"
        sid = "sub-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        current_seq = self._channel_seq.get(channel_name, 0)
        sub = _Subscription(sub_id=sid, channel_name=channel_name, agent_id=agent_id, last_read_seq=current_seq, subscribed_at=now)
        subs.append(sub)
        self._record_event(channel_name, "subscribed", {"agent_id": agent_id, "sub_id": sid})
        self._fire("subscribed", {"channel_name": channel_name, "agent_id": agent_id})
        return True

    def unsubscribe(self, channel_name: str, agent_id: str) -> bool:
        if channel_name not in self._name_index or not agent_id:
            return False
        subs = self._subscriptions[channel_name]
        for i, s in enumerate(subs):
            if s.agent_id == agent_id:
                subs.pop(i)
                self._record_event(channel_name, "unsubscribed", {"agent_id": agent_id})
                self._fire("unsubscribed", {"channel_name": channel_name, "agent_id": agent_id})
                return True
        return False

    def send(self, channel_name: str, sender: str, msg_type: str = "notification", payload: Optional[Dict[str, Any]] = None, requires_ack: bool = False) -> str:
        if channel_name not in self._name_index:
            return ""
        if msg_type not in ("request", "response", "notification", "broadcast"):
            return ""
        if not sender:
            return ""
        self._seq += 1
        now = time.time()
        self._channel_seq[channel_name] = self._channel_seq.get(channel_name, 0) + 1
        seq_num = self._channel_seq[channel_name]
        raw = f"{channel_name}-{sender}-{now}-{self._seq}"
        mid = "msg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        msg = _Message(message_id=mid, channel_name=channel_name, sender=sender, msg_type=msg_type, payload=payload or {}, requires_ack=requires_ack, seq_num=seq_num, acked_by=[], created_at=now)
        self._messages[mid] = msg
        self._channel_messages[channel_name].append(mid)
        self._total_messages_sent += 1
        self._record_event(channel_name, "message_sent", {"message_id": mid, "sender": sender, "msg_type": msg_type})
        self._fire("message_sent", {"message_id": mid, "channel_name": channel_name, "sender": sender, "msg_type": msg_type})
        return mid

    def receive(self, channel_name: str, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        if channel_name not in self._name_index or not agent_id:
            return []
        subs = self._subscriptions.get(channel_name, [])
        sub = None
        for s in subs:
            if s.agent_id == agent_id:
                sub = s
                break
        if sub is None:
            return []
        msg_ids = self._channel_messages.get(channel_name, [])
        results: List[Dict[str, Any]] = []
        max_seq_seen = sub.last_read_seq
        for mid in msg_ids:
            msg = self._messages.get(mid)
            if not msg:
                continue
            if msg.seq_num <= sub.last_read_seq:
                continue
            results.append(self._msg_to_dict(msg))
            if msg.seq_num > max_seq_seen:
                max_seq_seen = msg.seq_num
            if len(results) >= limit:
                break
        sub.last_read_seq = max_seq_seen
        return results

    def acknowledge(self, message_id: str, agent_id: str) -> bool:
        msg = self._messages.get(message_id)
        if not msg or not agent_id:
            return False
        if not msg.requires_ack:
            return False
        if agent_id in msg.acked_by:
            return False
        msg.acked_by.append(agent_id)
        self._total_acks += 1
        self._record_event(msg.channel_name, "acknowledged", {"message_id": message_id, "agent_id": agent_id})
        self._fire("acknowledged", {"message_id": message_id, "agent_id": agent_id, "channel_name": msg.channel_name})
        return True

    def get_unacknowledged(self, channel_name: str = "", agent_id: str = "") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for msg in self._messages.values():
            if not msg.requires_ack:
                continue
            if channel_name and msg.channel_name != channel_name:
                continue
            # Determine expected ack agents: all subscribers of the channel except sender
            subs = self._subscriptions.get(msg.channel_name, [])
            expected_agents = [s.agent_id for s in subs if s.agent_id != msg.sender]
            if agent_id:
                if agent_id not in expected_agents:
                    continue
                if agent_id in msg.acked_by:
                    continue
            else:
                pending = [a for a in expected_agents if a not in msg.acked_by]
                if not pending:
                    continue
            d = self._msg_to_dict(msg)
            if agent_id:
                d["pending_from"] = [agent_id]
            else:
                d["pending_from"] = [a for a in expected_agents if a not in msg.acked_by]
            results.append(d)
        return results

    def get_channel(self, name: str) -> Optional[Dict[str, Any]]:
        cid = self._name_index.get(name)
        if not cid:
            return None
        ch = self._channels[cid]
        subs = self._subscriptions.get(name, [])
        msg_ids = self._channel_messages.get(name, [])
        pending_acks = 0
        for mid in msg_ids:
            msg = self._messages.get(mid)
            if msg and msg.requires_ack:
                expected = [s.agent_id for s in subs if s.agent_id != msg.sender]
                pending_acks += len([a for a in expected if a not in msg.acked_by])
        return {"channel_id": ch.channel_id, "name": ch.name, "channel_type": ch.channel_type, "tags": list(ch.tags), "subscriber_count": len(subs), "message_count": len(msg_ids), "pending_acks": pending_acks, "created_at": ch.created_at}

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        msg = self._messages.get(message_id)
        if not msg:
            return None
        return self._msg_to_dict(msg)

    def list_channels(self, channel_type: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for ch in self._channels.values():
            if channel_type and ch.channel_type != channel_type:
                continue
            if tag and tag not in ch.tags:
                continue
            subs = self._subscriptions.get(ch.name, [])
            msg_ids = self._channel_messages.get(ch.name, [])
            results.append({"channel_id": ch.channel_id, "name": ch.name, "channel_type": ch.channel_type, "tags": list(ch.tags), "subscriber_count": len(subs), "message_count": len(msg_ids), "created_at": ch.created_at})
        return results

    def remove_channel(self, name: str) -> bool:
        cid = self._name_index.pop(name, None)
        if not cid:
            return False
        self._channels.pop(cid, None)
        # Remove messages for the channel
        msg_ids = self._channel_messages.pop(name, [])
        for mid in msg_ids:
            self._messages.pop(mid, None)
        self._subscriptions.pop(name, None)
        self._channel_seq.pop(name, None)
        self._record_event(name, "channel_removed", {"channel_id": cid})
        self._fire("channel_removed", {"channel_id": cid, "name": name})
        return True

    def get_history(self, limit: int = 50, channel_name: str = "", action: str = "") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for ev in reversed(self._history):
            if channel_name and ev.channel_name != channel_name:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "channel_name": ev.channel_name, "action": ev.action, "data": ev.data, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, channel_name: str, action: str, data: Dict[str, Any]) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{channel_name}-{action}-{now}-{self._seq}"
        evid = "pev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _ProtocolEvent(event_id=evid, channel_name=channel_name, action=action, data=data, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    def _msg_to_dict(self, msg: _Message) -> Dict[str, Any]:
        return {"message_id": msg.message_id, "channel_name": msg.channel_name, "sender": msg.sender, "msg_type": msg.msg_type, "payload": msg.payload, "requires_ack": msg.requires_ack, "seq_num": msg.seq_num, "acked_by": list(msg.acked_by), "created_at": msg.created_at}

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

    def get_stats(self) -> Dict[str, Any]:
        total_subscribers = sum(len(s) for s in self._subscriptions.values())
        total_pending = len(self.get_unacknowledged())
        return {"current_channels": len(self._channels), "total_channels_created": self._total_channels_created, "total_messages_sent": self._total_messages_sent, "total_acks": self._total_acks, "total_subscribers": total_subscribers, "total_pending_acks": total_pending, "total_stored_messages": len(self._messages), "history_size": len(self._history)}

    def reset(self) -> None:
        self._channels.clear()
        self._name_index.clear()
        self._subscriptions.clear()
        self._messages.clear()
        self._channel_messages.clear()
        self._channel_seq.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_channels_created = 0
        self._total_messages_sent = 0
        self._total_acks = 0
