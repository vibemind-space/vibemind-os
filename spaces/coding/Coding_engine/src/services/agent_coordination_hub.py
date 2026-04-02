"""Agent coordination hub.

Central hub for coordinating agent interactions, managing communication
channels, broadcasting messages, and tracking coordination patterns.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Channel:
    """Communication channel."""
    channel_id: str = ""
    name: str = ""
    channel_type: str = "broadcast"  # broadcast, direct, group
    members: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: str = "active"  # active, archived
    message_count: int = 0
    created_at: float = 0.0


@dataclass
class _Message:
    """Channel message."""
    message_id: str = ""
    channel_id: str = ""
    sender: str = ""
    content: str = ""
    msg_type: str = "text"  # text, command, status, alert
    priority: int = 0
    timestamp: float = 0.0
    seq: int = 0


@dataclass
class _Task:
    """Coordination task."""
    task_id: str = ""
    name: str = ""
    assigned_to: List[str] = field(default_factory=list)
    coordinator: str = ""
    status: str = "pending"  # pending, active, completed, failed
    priority: int = 0
    created_at: float = 0.0
    completed_at: float = 0.0


class AgentCoordinationHub:
    """Central hub for agent coordination."""

    CHANNEL_TYPES = ("broadcast", "direct", "group")
    MSG_TYPES = ("text", "command", "status", "alert")

    def __init__(self, max_channels: int = 5000, max_messages: int = 100000,
                 max_tasks: int = 50000):
        self._max_channels = max_channels
        self._max_messages = max_messages
        self._max_tasks = max_tasks
        self._channels: Dict[str, _Channel] = {}
        self._messages: Dict[str, _Message] = {}
        self._tasks: Dict[str, _Task] = {}
        self._msg_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_channels_created": 0,
            "total_messages_sent": 0,
            "total_tasks_created": 0,
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
        }

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def create_channel(self, name: str, channel_type: str = "broadcast",
                       members: Optional[List[str]] = None,
                       tags: Optional[List[str]] = None) -> str:
        """Create a communication channel."""
        if not name:
            return ""
        if channel_type not in self.CHANNEL_TYPES:
            return ""
        if len(self._channels) >= self._max_channels:
            return ""

        cid = "ch-" + hashlib.md5(
            f"{name}{time.time()}{len(self._channels)}".encode()
        ).hexdigest()[:12]

        self._channels[cid] = _Channel(
            channel_id=cid,
            name=name,
            channel_type=channel_type,
            members=members or [],
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_channels_created"] += 1
        return cid

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """Get channel info."""
        c = self._channels.get(channel_id)
        if not c:
            return None
        return {
            "channel_id": c.channel_id,
            "name": c.name,
            "channel_type": c.channel_type,
            "members": list(c.members),
            "tags": list(c.tags),
            "status": c.status,
            "message_count": c.message_count,
            "member_count": len(c.members),
        }

    def remove_channel(self, channel_id: str) -> bool:
        """Remove a channel."""
        if channel_id not in self._channels:
            return False
        del self._channels[channel_id]
        return True

    def archive_channel(self, channel_id: str) -> bool:
        """Archive a channel."""
        c = self._channels.get(channel_id)
        if not c or c.status != "active":
            return False
        c.status = "archived"
        return True

    def join_channel(self, channel_id: str, agent: str) -> bool:
        """Add agent to channel."""
        c = self._channels.get(channel_id)
        if not c or not agent or c.status != "active":
            return False
        if agent in c.members:
            return False
        c.members.append(agent)
        return True

    def leave_channel(self, channel_id: str, agent: str) -> bool:
        """Remove agent from channel."""
        c = self._channels.get(channel_id)
        if not c or agent not in c.members:
            return False
        c.members.remove(agent)
        return True

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, channel_id: str, sender: str, content: str,
                     msg_type: str = "text", priority: int = 0) -> str:
        """Send a message to a channel."""
        c = self._channels.get(channel_id)
        if not c or c.status != "active":
            return ""
        if not sender or not content:
            return ""
        if msg_type not in self.MSG_TYPES:
            return ""

        if len(self._messages) >= self._max_messages:
            self._prune_messages()

        mid = "msg-" + hashlib.md5(
            f"{sender}{content}{time.time()}{len(self._messages)}".encode()
        ).hexdigest()[:12]

        self._msg_seq += 1
        self._messages[mid] = _Message(
            message_id=mid,
            channel_id=channel_id,
            sender=sender,
            content=content,
            msg_type=msg_type,
            priority=priority,
            timestamp=time.time(),
            seq=self._msg_seq,
        )
        c.message_count += 1
        self._stats["total_messages_sent"] += 1

        self._fire("message_sent", {
            "message_id": mid, "channel_id": channel_id,
            "sender": sender, "msg_type": msg_type,
        })
        return mid

    def get_message(self, message_id: str) -> Optional[Dict]:
        """Get message info."""
        m = self._messages.get(message_id)
        if not m:
            return None
        return {
            "message_id": m.message_id,
            "channel_id": m.channel_id,
            "sender": m.sender,
            "content": m.content,
            "msg_type": m.msg_type,
            "priority": m.priority,
            "timestamp": m.timestamp,
        }

    def get_channel_messages(self, channel_id: str,
                              limit: int = 50) -> List[Dict]:
        """Get messages for a channel."""
        result = []
        for m in self._messages.values():
            if m.channel_id != channel_id:
                continue
            result.append({
                "message_id": m.message_id,
                "sender": m.sender,
                "content": m.content,
                "msg_type": m.msg_type,
                "timestamp": m.timestamp,
                "seq": m.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def broadcast(self, sender: str, content: str,
                  msg_type: str = "alert") -> List[str]:
        """Send message to all active broadcast channels."""
        sent = []
        for c in self._channels.values():
            if c.status != "active" or c.channel_type != "broadcast":
                continue
            mid = self.send_message(c.channel_id, sender, content, msg_type)
            if mid:
                sent.append(mid)
        return sent

    # ------------------------------------------------------------------
    # Task coordination
    # ------------------------------------------------------------------

    def create_task(self, name: str, coordinator: str = "",
                    assigned_to: Optional[List[str]] = None,
                    priority: int = 0) -> str:
        """Create a coordination task."""
        if not name:
            return ""
        if len(self._tasks) >= self._max_tasks:
            return ""

        tid = "ctask-" + hashlib.md5(
            f"{name}{time.time()}{len(self._tasks)}".encode()
        ).hexdigest()[:12]

        self._tasks[tid] = _Task(
            task_id=tid,
            name=name,
            coordinator=coordinator,
            assigned_to=assigned_to or [],
            priority=priority,
            created_at=time.time(),
        )
        self._stats["total_tasks_created"] += 1
        return tid

    def start_task(self, task_id: str) -> bool:
        """Start a coordination task."""
        t = self._tasks.get(task_id)
        if not t or t.status != "pending":
            return False
        t.status = "active"
        return True

    def complete_task(self, task_id: str) -> bool:
        """Complete a coordination task."""
        t = self._tasks.get(task_id)
        if not t or t.status != "active":
            return False
        t.status = "completed"
        t.completed_at = time.time()
        self._stats["total_tasks_completed"] += 1
        return True

    def fail_task(self, task_id: str) -> bool:
        """Fail a coordination task."""
        t = self._tasks.get(task_id)
        if not t or t.status != "active":
            return False
        t.status = "failed"
        t.completed_at = time.time()
        self._stats["total_tasks_failed"] += 1
        return True

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task info."""
        t = self._tasks.get(task_id)
        if not t:
            return None
        return {
            "task_id": t.task_id,
            "name": t.name,
            "coordinator": t.coordinator,
            "assigned_to": list(t.assigned_to),
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at,
            "completed_at": t.completed_at,
        }

    def remove_task(self, task_id: str) -> bool:
        """Remove a task."""
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_channels(self, agent: str) -> List[Dict]:
        """Get channels an agent belongs to."""
        result = []
        for c in self._channels.values():
            if agent in c.members:
                result.append({
                    "channel_id": c.channel_id,
                    "name": c.name,
                    "channel_type": c.channel_type,
                    "status": c.status,
                })
        return result

    def get_agent_tasks(self, agent: str,
                        status: Optional[str] = None) -> List[Dict]:
        """Get tasks assigned to an agent."""
        result = []
        for t in self._tasks.values():
            if agent not in t.assigned_to:
                continue
            if status and t.status != status:
                continue
            result.append({
                "task_id": t.task_id,
                "name": t.name,
                "status": t.status,
                "priority": t.priority,
            })
        return result

    def list_channels(self, status: Optional[str] = None,
                      tag: Optional[str] = None) -> List[Dict]:
        """List channels with optional filters."""
        result = []
        for c in self._channels.values():
            if status and c.status != status:
                continue
            if tag and tag not in c.tags:
                continue
            result.append({
                "channel_id": c.channel_id,
                "name": c.name,
                "channel_type": c.channel_type,
                "status": c.status,
                "member_count": len(c.members),
                "message_count": c.message_count,
            })
        return result

    def list_tasks(self, status: Optional[str] = None,
                   coordinator: Optional[str] = None) -> List[Dict]:
        """List tasks with optional filters."""
        result = []
        for t in self._tasks.values():
            if status and t.status != status:
                continue
            if coordinator and t.coordinator != coordinator:
                continue
            result.append({
                "task_id": t.task_id,
                "name": t.name,
                "status": t.status,
                "assigned_count": len(t.assigned_to),
                "priority": t.priority,
            })
        return result

    def get_all_agents(self) -> List[str]:
        """Get all agents across channels."""
        agents = set()
        for c in self._channels.values():
            agents.update(c.members)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_messages(self) -> None:
        """Remove oldest messages."""
        items = sorted(self._messages.items(), key=lambda x: x[1].timestamp)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._messages[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_channels": len(self._channels),
            "active_channels": sum(
                1 for c in self._channels.values() if c.status == "active"
            ),
            "current_messages": len(self._messages),
            "current_tasks": len(self._tasks),
            "active_tasks": sum(
                1 for t in self._tasks.values() if t.status == "active"
            ),
        }

    def reset(self) -> None:
        self._channels.clear()
        self._messages.clear()
        self._tasks.clear()
        self._msg_seq = 0
        self._stats = {k: 0 for k in self._stats}
