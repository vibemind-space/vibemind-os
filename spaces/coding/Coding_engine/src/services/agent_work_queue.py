"""Agent Work Queue — per-agent work queues with priority ordering.

Provides dedicated work queues for each agent with priority-based push/pop,
peek support, queue lifecycle management, and callback notifications.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class QueueEntry:
    """Represents a per-agent queue."""
    queue_id: str = ""
    agent_id: str = ""
    items: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    seq: int = 0


@dataclass
class WorkItemEntry:
    """A single work item within a queue."""
    item_id: str = ""
    agent_id: str = ""
    work_item: str = ""
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    seq: int = 0


class AgentWorkQueue:
    """Per-agent work queues with priority ordering."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._queues: Dict[str, QueueEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        # Internal stores
        self._agent_queues: Dict[str, str] = {}  # agent_id -> queue_id
        self._items: Dict[str, WorkItemEntry] = {}  # item_id -> WorkItemEntry
        self._queue_items: Dict[str, List[str]] = {}  # queue_id -> [item_ids]

        # Stats
        self._total_pushes: int = 0
        self._total_pops: int = 0
        self._total_clears: int = 0
        self._total_queues_created: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4().hex}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"awq-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning("callback_error", action=action, exc_info=True)

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
        if existing_qid and existing_qid in self._queues:
            return existing_qid

        queue_id = self._gen_id(f"queue-{agent_id}")
        now = time.time()
        entry = QueueEntry(
            queue_id=queue_id,
            agent_id=agent_id,
            created_at=now,
            seq=self._seq,
        )
        self._queues[queue_id] = entry
        self._agent_queues[agent_id] = queue_id
        self._queue_items[queue_id] = []
        self._total_queues_created += 1

        logger.debug("queue_created", queue_id=queue_id, agent_id=agent_id)
        self._fire("queue_created", {
            "queue_id": queue_id,
            "agent_id": agent_id,
        })
        return queue_id

    # ------------------------------------------------------------------
    # Push / Pop / Peek
    # ------------------------------------------------------------------

    def push(
        self,
        agent_id: str,
        work_item: str,
        priority: int = 0,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Push a work item onto an agent's queue. Returns item ID.

        Automatically creates a queue for the agent if one does not exist.
        Higher priority values are popped first.
        """
        if not agent_id or not work_item:
            logger.warning(
                "push_invalid_args", agent_id=agent_id, work_item=work_item,
            )
            return ""

        # Enforce max entries
        if len(self._items) >= self._max_entries:
            logger.warning("push_max_entries_reached", agent_id=agent_id)
            return ""

        # Ensure queue exists
        if agent_id not in self._agent_queues:
            self.create_queue(agent_id)

        queue_id = self._agent_queues[agent_id]
        item_id = self._gen_id(f"item-{agent_id}")
        now = time.time()

        entry = WorkItemEntry(
            item_id=item_id,
            agent_id=agent_id,
            work_item=work_item,
            priority=priority,
            metadata=dict(metadata or {}),
            created_at=now,
            seq=self._seq,
        )
        self._items[item_id] = entry
        self._queue_items[queue_id].append(item_id)
        self._total_pushes += 1

        logger.debug(
            "work_pushed", item_id=item_id, agent_id=agent_id,
            priority=priority,
        )
        self._fire("work_pushed", {
            "item_id": item_id,
            "queue_id": queue_id,
            "agent_id": agent_id,
            "priority": priority,
        })
        return item_id

    def _pick_highest_priority(self, queue_id: str) -> Optional[str]:
        """Find the item ID with the highest priority in a queue."""
        item_ids = self._queue_items.get(queue_id)
        if not item_ids:
            return None

        best_id: Optional[str] = None
        best_priority = -1
        best_seq = -1

        for iid in item_ids:
            item = self._items.get(iid)
            if item is None:
                continue
            # Higher priority wins; among equal priority, earliest seq wins
            if best_id is None or item.priority > best_priority or (
                item.priority == best_priority and item.seq < best_seq
            ):
                best_id = iid
                best_priority = item.priority
                best_seq = item.seq

        return best_id

    def pop(self, agent_id: str) -> Optional[Dict]:
        """Pop the highest priority work item from agent's queue.

        Returns the work item as a dict, or None if the queue is empty.
        """
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return None

        best_id = self._pick_highest_priority(queue_id)
        if best_id is None:
            return None

        item = self._items.pop(best_id)
        self._queue_items[queue_id].remove(best_id)
        self._total_pops += 1

        result = {
            "item_id": item.item_id,
            "agent_id": item.agent_id,
            "work_item": item.work_item,
            "priority": item.priority,
            "metadata": dict(item.metadata),
            "created_at": item.created_at,
            "seq": item.seq,
        }

        logger.debug(
            "work_popped", item_id=best_id, agent_id=agent_id,
        )
        self._fire("work_popped", {
            "item_id": best_id,
            "queue_id": queue_id,
            "agent_id": agent_id,
        })
        return result

    def peek(self, agent_id: str) -> Optional[Dict]:
        """Peek at the highest priority work item without removing it.

        Returns the work item as a dict, or None if the queue is empty.
        """
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return None

        best_id = self._pick_highest_priority(queue_id)
        if best_id is None:
            return None

        item = self._items.get(best_id)
        if item is None:
            return None

        return {
            "item_id": item.item_id,
            "agent_id": item.agent_id,
            "work_item": item.work_item,
            "priority": item.priority,
            "metadata": dict(item.metadata),
            "created_at": item.created_at,
            "seq": item.seq,
        }

    # ------------------------------------------------------------------
    # Queue info
    # ------------------------------------------------------------------

    def get_queue_length(self, agent_id: str) -> int:
        """Get number of work items in agent's queue."""
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return 0
        return len(self._queue_items.get(queue_id, []))

    def clear_queue(self, agent_id: str) -> int:
        """Clear all work items from agent's queue. Returns count removed."""
        queue_id = self._agent_queues.get(agent_id)
        if queue_id is None:
            return 0

        item_ids = self._queue_items.get(queue_id, [])
        count = len(item_ids)

        for iid in item_ids:
            self._items.pop(iid, None)

        self._queue_items[queue_id] = []
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

    def get_queue_count(self) -> int:
        """Total number of queues."""
        return len(self._queues)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "current_queues": len(self._queues),
            "current_items": len(self._items),
            "total_queues_created": self._total_queues_created,
            "total_pushes": self._total_pushes,
            "total_pops": self._total_pops,
            "total_clears": self._total_clears,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._queues.clear()
        self._items.clear()
        self._agent_queues.clear()
        self._queue_items.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_pushes = 0
        self._total_pops = 0
        self._total_clears = 0
        self._total_queues_created = 0
        logger.debug("agent_work_queue_reset")
