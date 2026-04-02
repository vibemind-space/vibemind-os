"""Agent Workflow Queue - manages ordering and processing of agent workflow executions.

Provides a priority-based queue for scheduling and tracking agent workflow
executions through their lifecycle: queued -> processing -> completed/failed.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowQueueState:
    """Internal state container for the workflow queue."""

    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowQueue:
    """Queue for agent workflow executions with priority ordering.

    Workflows are enqueued with a priority (lower number = higher priority)
    and processed in priority order. Each item tracks its lifecycle status:
    queued, processing, completed, or failed.
    """

    PREFIX = "awq-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowQueueState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID from data combined with the internal sequence counter."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries by created_at if entries exceed MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            self._state.entries,
            key=lambda k: self._state.entries[k]["created_at"],
        )
        to_remove = len(self._state.entries) - self.MAX_ENTRIES
        for item_id in sorted_ids[:to_remove]:
            del self._state.entries[item_id]

    # ------------------------------------------------------------------
    # Event firing
    # ------------------------------------------------------------------

    def _fire(self, event: str, data: Any) -> None:
        """Fire event to on_change handler and all registered callbacks."""
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception as exc:
                logger.error("on_change handler error: %s", exc)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.error("Callback '%s' error: %s", name, exc)

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the current on_change handler."""
        return self._on_change

    @on_change.setter
    def on_change(self, handler: Optional[Callable]) -> None:
        """Set the on_change handler."""
        self._on_change = handler

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Core queue operations
    # ------------------------------------------------------------------

    def enqueue(
        self,
        agent_id: str,
        workflow_name: str,
        priority: int = 5,
        payload: Any = None,
    ) -> str:
        """Add a workflow to the queue. Returns the item ID."""
        item_id = self._generate_id(f"{agent_id}{workflow_name}")
        now = time.time()
        self._state.entries[item_id] = {
            "item_id": item_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "priority": priority,
            "payload": payload,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }
        self._prune()
        self._fire("enqueue", {"item_id": item_id})
        return item_id

    def dequeue(self, agent_id: str = "") -> Optional[dict]:
        """Get and start the highest priority queued item (lowest priority number).

        If *agent_id* is provided, only items for that agent are considered.
        Returns None if no queued items are available.
        """
        candidates = [
            e for e in self._state.entries.values()
            if e["status"] == "queued"
            and (not agent_id or e["agent_id"] == agent_id)
        ]
        if not candidates:
            return None
        # Lowest priority number = highest priority; tie-break by created_at
        best = min(candidates, key=lambda e: (e["priority"], e["created_at"]))
        best["status"] = "processing"
        best["started_at"] = time.time()
        self._fire("dequeue", {"item_id": best["item_id"]})
        return dict(best)

    def complete(self, item_id: str, result: Any = None) -> bool:
        """Mark an item as completed. Returns False if item not found."""
        entry = self._state.entries.get(item_id)
        if entry is None:
            return False
        entry["status"] = "completed"
        entry["completed_at"] = time.time()
        if result is not None:
            entry["result"] = result
        self._fire("complete", {"item_id": item_id})
        return True

    def fail(self, item_id: str, error: str = "") -> bool:
        """Mark an item as failed. Returns False if item not found."""
        entry = self._state.entries.get(item_id)
        if entry is None:
            return False
        entry["status"] = "failed"
        if error:
            entry["error"] = error
        self._fire("fail", {"item_id": item_id})
        return True

    def requeue(self, item_id: str) -> bool:
        """Reset an item back to queued status. Returns False if item not found."""
        entry = self._state.entries.get(item_id)
        if entry is None:
            return False
        entry["status"] = "queued"
        entry["started_at"] = None
        entry["completed_at"] = None
        self._fire("requeue", {"item_id": item_id})
        return True

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_item(self, item_id: str) -> Optional[dict]:
        """Return a copy of a queue item, or None if not found."""
        entry = self._state.entries.get(item_id)
        if entry is None:
            return None
        return dict(entry)

    def get_queue(self, agent_id: str = "", status: str = "") -> list:
        """List queue items, optionally filtered by agent_id and/or status."""
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_queue_length(self, agent_id: str = "", status: str = "") -> int:
        """Return the count of items matching the optional filters."""
        return len(self.get_queue(agent_id=agent_id, status=status))

    def get_stats(self) -> dict:
        """Return aggregate statistics about the queue."""
        entries = self._state.entries.values()
        return {
            "total_items": len(entries),
            "queued": sum(1 for e in entries if e["status"] == "queued"),
            "processing": sum(1 for e in entries if e["status"] == "processing"),
            "completed": sum(1 for e in entries if e["status"] == "completed"),
            "failed": sum(1 for e in entries if e["status"] == "failed"),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowQueueState()
        self._fire("reset", {})
