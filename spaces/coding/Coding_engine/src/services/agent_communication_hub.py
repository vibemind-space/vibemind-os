"""Agent communication hub.

Inter-agent communication hub - manages message passing between agents.
Supports direct messages, broadcasts, and callback-based change notifications.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MessageEntry:
    """A message in the communication hub."""
    message_id: str
    from_agent: str
    to_agent: str
    content: str
    msg_type: str
    created_at: float
    read: bool


class AgentCommunicationHub:
    """Hub for inter-agent messaging."""

    def __init__(self) -> None:
        self._messages: Dict[str, MessageEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"ach-{self._seq}-{id(self)}"
        return "ach-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when over capacity."""
        if len(self._messages) > self._max_entries:
            sorted_ids = sorted(
                self._messages,
                key=lambda mid: self._messages[mid].created_at,
            )
            excess = len(self._messages) - self._max_entries
            for mid in sorted_ids[:excess]:
                del self._messages[mid]

    # ------------------------------------------------------------------
    # Messaging API
    # ------------------------------------------------------------------

    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: str = "direct",
    ) -> str:
        """Send a direct message from one agent to another.

        Returns the new message_id (prefixed with 'ach-').
        """
        message_id = self._generate_id()
        entry = MessageEntry(
            message_id=message_id,
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            msg_type=msg_type,
            created_at=time.time(),
            read=False,
        )
        self._messages[message_id] = entry
        self._prune()
        self._fire("send_message", {
            "message_id": message_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "msg_type": msg_type,
        })
        return message_id

    def get_message(self, message_id: str) -> Optional[Dict]:
        """Retrieve a message by its id. Returns dict or None."""
        entry = self._messages.get(message_id)
        if entry is None:
            return None
        return {
            "message_id": entry.message_id,
            "from_agent": entry.from_agent,
            "to_agent": entry.to_agent,
            "content": entry.content,
            "msg_type": entry.msg_type,
            "created_at": entry.created_at,
            "read": entry.read,
        }

    def get_inbox(self, agent_id: str) -> List[Dict]:
        """Get all messages received by a given agent."""
        results = []
        for entry in self._messages.values():
            if entry.to_agent == agent_id or entry.to_agent == "*":
                results.append({
                    "message_id": entry.message_id,
                    "from_agent": entry.from_agent,
                    "to_agent": entry.to_agent,
                    "content": entry.content,
                    "msg_type": entry.msg_type,
                    "created_at": entry.created_at,
                    "read": entry.read,
                })
        results.sort(key=lambda m: m["created_at"])
        return results

    def get_outbox(self, agent_id: str) -> List[Dict]:
        """Get all messages sent by a given agent."""
        results = []
        for entry in self._messages.values():
            if entry.from_agent == agent_id:
                results.append({
                    "message_id": entry.message_id,
                    "from_agent": entry.from_agent,
                    "to_agent": entry.to_agent,
                    "content": entry.content,
                    "msg_type": entry.msg_type,
                    "created_at": entry.created_at,
                    "read": entry.read,
                })
        results.sort(key=lambda m: m["created_at"])
        return results

    def broadcast(
        self,
        from_agent: str,
        content: str,
        msg_type: str = "broadcast",
    ) -> str:
        """Broadcast a message to all agents (to_agent='*').

        Returns the new message_id.
        """
        return self.send_message(
            from_agent=from_agent,
            to_agent="*",
            content=content,
            msg_type=msg_type,
        )

    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read. Returns True if successful."""
        entry = self._messages.get(message_id)
        if entry is None:
            return False
        entry.read = True
        self._fire("mark_read", {"message_id": message_id})
        return True

    def delete_message(self, message_id: str) -> bool:
        """Delete a message by id. Returns True if it existed."""
        if message_id not in self._messages:
            return False
        del self._messages[message_id]
        self._fire("delete_message", {"message_id": message_id})
        return True

    def get_unread_count(self, agent_id: str) -> int:
        """Count unread messages in an agent's inbox."""
        count = 0
        for entry in self._messages.values():
            if (entry.to_agent == agent_id or entry.to_agent == "*") and not entry.read:
                count += 1
        return count

    def list_agents(self) -> List[str]:
        """List all agent ids that have sent or received messages."""
        agents: set = set()
        for entry in self._messages.values():
            agents.add(entry.from_agent)
            if entry.to_agent != "*":
                agents.add(entry.to_agent)
        return sorted(agents)

    def get_message_count(self) -> int:
        """Return the total number of messages in the hub."""
        return len(self._messages)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback by name."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return hub statistics."""
        total = len(self._messages)
        unread = sum(1 for e in self._messages.values() if not e.read)
        read = total - unread
        agents = self.list_agents()
        return {
            "total_messages": total,
            "read_messages": read,
            "unread_messages": unread,
            "agent_count": len(agents),
            "callback_count": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._messages.clear()
        self._callbacks.clear()
        self._seq = 0
