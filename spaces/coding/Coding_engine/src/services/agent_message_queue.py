"""Agent Message Queue – per-agent message queues for async communication between agents.

Provides priority-based message queuing per agent with enqueue/dequeue operations,
peek support, queue management, and callback notifications for queue state changes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class QueueEntry:
    queue_id: str
    agent_id: str
    created_at: float = 0.0
    seq: int = 0


@dataclass
class MessageEntry:
    message_id: str
    queue_id: str
    agent_id: str
    message: str
    priority: int = 0
    sender: str = ""
    created_at: float = 0.0
    seq: int = 0


class AgentMessageQueue:
    """Per-agent message queues for async communication between agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, QueueEntry] = {}
        self._messages: Dict[str, MessageEntry] = {}
        self._agent_queues: Dict[str, str] = {}  # agent_id -> queue_id
        self._queue_messages: Dict[str, List[str]] = {}  # queue_id -> [message_ids]
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # stats
        self._total_enqueues = 0
        self._total_dequeues = 0
        self._total_clears = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"amq-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"amq-{digest}"

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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def create_queue(self, agent_id: str) -> str:
        """Create a queue for an agent. Returns queue ID.

        If the agent already has a queue, returns the existing queue ID.
        """
        if not agent_id:
            logger.warning("create_queue_invalid_args", agent_id=agent_id)
            return ""

        existing_qid = self._agent_queues.get(agent_id)
        if existing_qid and existing_qid in self._entries:
            return existing_qid

        queue_id = self._gen_id(f"queue-{agent_id}")
        now = time.time()
        entry = QueueEntry(
            queue_id=queue_id,
            agent_id=agent_id,
            created_at=now,
            seq=self._seq,
        )
        self._entries[queue_id] = entry
        self._agent_queues[agent_id] = queue_id
        self._queue_messages[queue_id] = []

        logger.debug("queue_created", queue_id=queue_id, agent_id=agent_id)
        self._fire("queue_created", {
            "queue_id": queue_id,
            "agent_id": agent_id,
        })
        return queue_id

    def get_queue(self, queue_id: str) -> Optional[Dict]:
        """Get queue by ID."""
        entry = self._entries.get(queue_id)
        if entry is None:
            return None
        return asdict(entry)

    # ------------------------------------------------------------------
    # Enqueue / Dequeue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        agent_id: str,
        message: str,
        priority: int = 0,
        sender: str = "",
    ) -> str:
        """Add a message to an agent's queue. Returns message ID.

        Automatically creates a queue for the agent if one does not exist.
        Higher priority values are dequeued first.
        """
        if not agent_id or not message:
            logger.warning(
                "enqueue_invalid_args", agent_id=agent_id, message=message,
            )
            return ""

        # Ensure queue exists
        if agent_id not in self._agent_queues:
            self.create_queue(agent_id)

        queue_id = self._agent_queues[agent_id]

        # Enforce max entries across all messages
        if len(self._messages) >= self._max_entries:
            logger.warning("enqueue_max_entries_reached", agent_id=agent_id)
            return ""

        now = time.time()
        message_id = self._gen_id(f"msg-{agent_id}-{sender}")
        msg_entry = MessageEntry(
            message_id=message_id,
            queue_id=queue_id,
            agent_id=agent_id,
            message=message,
            priority=priority,
            sender=sender,
            created_at=now,
            seq=self._seq,
        )
        self._messages[message_id] = msg_entry
        self._queue_messages[queue_id].append(message_id)
        self._total_enqueues += 1

        logger.debug(
            "message_enqueued", message_id=message_id, agent_id=agent_id,
            priority=priority, sender=sender,
        )
        self._fire("message_enqueued", {
            "message_id": message_id,
            "queue_id": queue_id,
            "agent_id": agent_id,
            "priority": priority,
            "sender": sender,
        })
        return message_id

    def _pick_highest_priority(self, queue_id: str) -> Optional[str]:
        """Find the message ID with the highest priority in a queue."""
        msg_ids = self._queue_messages.get(queue_id)
        if not msg_ids:
            return None

        best_id: Optional[str] = None
        best_priority = -1
        best_seq = -1

        for mid in msg_ids:
            msg = self._messages.get(mid)
            if msg is None:
                continue
            # Higher priority wins; among equal priority, earliest seq wins
            if best_id is None or msg.priority > best_priority or (
                msg.priority == best_priority and msg.seq < best_seq
            ):
                best_id = mid
                best_priority = msg.priority
                best_seq = msg.seq

        return best_id

    def dequeue(self, agent_id: str) -> Optional[Dict]:
        """Dequeue highest priority message from agent's queue.

        Returns the message as a dict, or None if the queue is empty.
        """
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return None

        best_id = self._pick_highest_priority(queue_id)
        if best_id is None:
            return None

        msg = self._messages.pop(best_id)
        self._queue_messages[queue_id].remove(best_id)
        self._seq += 1
        self._total_dequeues += 1

        result = asdict(msg)
        logger.debug(
            "message_dequeued", message_id=best_id, agent_id=agent_id,
        )
        self._fire("message_dequeued", {
            "message_id": best_id,
            "queue_id": queue_id,
            "agent_id": agent_id,
        })
        return result

    def peek(self, agent_id: str) -> Optional[Dict]:
        """Peek at next message without removing it.

        Returns the highest priority message as a dict, or None.
        """
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return None

        best_id = self._pick_highest_priority(queue_id)
        if best_id is None:
            return None

        msg = self._messages.get(best_id)
        if msg is None:
            return None
        return asdict(msg)

    # ------------------------------------------------------------------
    # Queue info
    # ------------------------------------------------------------------

    def get_queue_size(self, agent_id: str) -> int:
        """Get number of messages in agent's queue."""
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return 0
        return len(self._queue_messages.get(queue_id, []))

    def clear_queue(self, agent_id: str) -> int:
        """Clear all messages from agent's queue. Returns count removed."""
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return 0

        msg_ids = self._queue_messages.get(queue_id, [])
        count = len(msg_ids)

        for mid in msg_ids:
            self._messages.pop(mid, None)

        self._queue_messages[queue_id] = []
        self._seq += 1
        self._total_clears += count

        if count:
            logger.debug(
                "queue_cleared", agent_id=agent_id, queue_id=queue_id, count=count,
            )
            self._fire("queue_cleared", {
                "queue_id": queue_id,
                "agent_id": agent_id,
                "count": count,
            })
        return count

    def list_agents(self) -> List[str]:
        """List all agents with queues."""
        return sorted(self._agent_queues.keys())

    def get_message_count(self) -> int:
        """Total message count across all queues."""
        return len(self._messages)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_queues": len(self._entries),
            "current_messages": len(self._messages),
            "total_enqueues": self._total_enqueues,
            "total_dequeues": self._total_dequeues,
            "total_clears": self._total_clears,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._messages.clear()
        self._agent_queues.clear()
        self._queue_messages.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_enqueues = 0
        self._total_dequeues = 0
        self._total_clears = 0
        logger.debug("agent_message_queue_reset")
