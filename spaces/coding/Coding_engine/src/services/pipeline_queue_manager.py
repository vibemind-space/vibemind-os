"""Pipeline Queue Manager – named priority queues for pipeline work items.

Manages multiple named queues with priority-based ordering. Items are
enqueued with a priority and dequeued in priority order (higher first).
Supports queue-level limits, peek, and dead-letter tracking.
"""

from __future__ import annotations

import hashlib
import heapq
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _QueueItem:
    item_id: str
    queue_id: str
    payload: Any
    priority: int
    created_at: float
    seq: int  # for stable ordering within same priority


@dataclass
class _Queue:
    queue_id: str
    name: str
    max_size: int
    heap: List  # list of (-priority, seq, item)
    item_index: Dict[str, _QueueItem]
    total_enqueued: int
    total_dequeued: int
    total_dropped: int
    tags: List[str]
    created_at: float


class PipelineQueueManager:
    """Manages named priority queues for pipeline work items."""

    def __init__(self, max_queues: int = 5000):
        self._queues: Dict[str, _Queue] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_queues = max_queues
        self._seq = 0

        # stats
        self._total_queues = 0
        self._total_enqueued = 0
        self._total_dequeued = 0

    # ------------------------------------------------------------------
    # Queues
    # ------------------------------------------------------------------

    def create_queue(
        self,
        name: str,
        max_size: int = 10000,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name or max_size < 1:
            return ""
        if name in self._name_index:
            return ""
        if len(self._queues) >= self._max_queues:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        qid = "que-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        q = _Queue(
            queue_id=qid,
            name=name,
            max_size=max_size,
            heap=[],
            item_index={},
            total_enqueued=0,
            total_dequeued=0,
            total_dropped=0,
            tags=tags or [],
            created_at=now,
        )
        self._queues[qid] = q
        self._name_index[name] = qid
        self._total_queues += 1
        self._fire("queue_created", {"queue_id": qid, "name": name})
        return qid

    def get_queue(self, queue_id: str) -> Optional[Dict[str, Any]]:
        q = self._queues.get(queue_id)
        if not q:
            return None
        return {
            "queue_id": q.queue_id,
            "name": q.name,
            "max_size": q.max_size,
            "size": len(q.item_index),
            "total_enqueued": q.total_enqueued,
            "total_dequeued": q.total_dequeued,
            "total_dropped": q.total_dropped,
            "tags": list(q.tags),
            "created_at": q.created_at,
        }

    def get_queue_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        qid = self._name_index.get(name)
        if not qid:
            return None
        return self.get_queue(qid)

    def remove_queue(self, queue_id: str) -> bool:
        q = self._queues.pop(queue_id, None)
        if not q:
            return False
        self._name_index.pop(q.name, None)
        self._fire("queue_removed", {"queue_id": queue_id})
        return True

    def list_queues(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for q in self._queues.values():
            if tag and tag not in q.tags:
                continue
            results.append(self.get_queue(q.queue_id))
        return results

    # ------------------------------------------------------------------
    # Enqueue / Dequeue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        queue_id: str,
        payload: Any = None,
        priority: int = 5,
    ) -> str:
        q = self._queues.get(queue_id)
        if not q:
            return ""
        if len(q.item_index) >= q.max_size:
            q.total_dropped += 1
            return ""

        self._seq += 1
        now = time.time()
        raw = f"item-{queue_id}-{now}-{self._seq}"
        iid = "itm-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        item = _QueueItem(
            item_id=iid,
            queue_id=queue_id,
            payload=payload,
            priority=priority,
            created_at=now,
            seq=self._seq,
        )
        q.item_index[iid] = item
        # Use negative priority for max-heap behavior with heapq (min-heap)
        heapq.heappush(q.heap, (-priority, item.seq, iid))
        q.total_enqueued += 1
        self._total_enqueued += 1
        self._fire("item_enqueued", {"queue_id": queue_id, "item_id": iid})
        return iid

    def dequeue(self, queue_id: str) -> Optional[Dict[str, Any]]:
        q = self._queues.get(queue_id)
        if not q:
            return None
        # Pop items from heap until we find one still in index (not already removed)
        while q.heap:
            neg_pri, seq, iid = heapq.heappop(q.heap)
            item = q.item_index.pop(iid, None)
            if item:
                q.total_dequeued += 1
                self._total_dequeued += 1
                self._fire("item_dequeued", {"queue_id": queue_id, "item_id": iid})
                return {
                    "item_id": item.item_id,
                    "payload": item.payload,
                    "priority": item.priority,
                    "created_at": item.created_at,
                }
        return None

    def peek(self, queue_id: str) -> Optional[Dict[str, Any]]:
        q = self._queues.get(queue_id)
        if not q:
            return None
        # Find first valid item without removing
        for neg_pri, seq, iid in q.heap:
            item = q.item_index.get(iid)
            if item:
                return {
                    "item_id": item.item_id,
                    "payload": item.payload,
                    "priority": item.priority,
                    "created_at": item.created_at,
                }
        return None

    def queue_size(self, queue_id: str) -> int:
        q = self._queues.get(queue_id)
        if not q:
            return 0
        return len(q.item_index)

    def purge_queue(self, queue_id: str) -> int:
        """Remove all items from a queue. Returns count removed."""
        q = self._queues.get(queue_id)
        if not q:
            return 0
        count = len(q.item_index)
        q.item_index.clear()
        q.heap.clear()
        self._fire("queue_purged", {"queue_id": queue_id, "count": count})
        return count

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
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_queues": len(self._queues),
            "total_queues": self._total_queues,
            "total_enqueued": self._total_enqueued,
            "total_dequeued": self._total_dequeued,
            "total_items": sum(len(q.item_index) for q in self._queues.values()),
        }

    def reset(self) -> None:
        self._queues.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_queues = 0
        self._total_enqueued = 0
        self._total_dequeued = 0
