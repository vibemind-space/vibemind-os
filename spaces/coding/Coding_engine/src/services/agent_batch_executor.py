"""Agent Batch Executor -- creates and executes batches of tasks for agents.

Provides an in-memory store for grouping agent tasks into batches, marking
them as executed, and querying batch state.  Each batch tracks its owning
agent, task list, status, and timestamps.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal state
# ------------------------------------------------------------------

@dataclass
class _State:
    """Mutable internal state for the executor."""

    batches: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentBatchExecutor:
    """In-memory batch executor for agent tasks.

    Parameters
    ----------
    max_batches:
        Maximum number of batches to keep.  When the limit is reached the
        oldest quarter of batches is pruned automatically.
    """

    def __init__(self, max_batches: int = 10000) -> None:
        self._max_batches = max_batches
        self._lock = threading.Lock()
        self._state = _State()

        logger.debug("agent_batch_executor.init", max_batches=max_batches)

    # ------------------------------------------------------------------
    # Batch creation / execution
    # ------------------------------------------------------------------

    def create_batch(self, agent_id: str, tasks: list) -> str:
        """Create a new batch of tasks for *agent_id*.

        Returns the generated ``batch_id`` (prefixed ``abe-``).
        """
        with self._lock:
            if len(self._state.batches) >= self._max_batches:
                self._prune()

            self._state._seq += 1
            now = time.time()
            raw = f"{agent_id}-{now}-{self._state._seq}"
            batch_id = "abe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

            batch: Dict[str, Any] = {
                "batch_id": batch_id,
                "agent_id": agent_id,
                "tasks": list(tasks),
                "status": "pending",
                "created_at": now,
                "executed_at": None,
                "seq": self._state._seq,
            }
            self._state.batches[batch_id] = batch

        logger.debug(
            "agent_batch_executor.create_batch",
            batch_id=batch_id,
            agent_id=agent_id,
            task_count=len(tasks),
        )
        self._fire("batch_created", {
            "batch_id": batch_id,
            "agent_id": agent_id,
            "task_count": len(tasks),
        })
        return batch_id

    def execute_batch(self, batch_id: str) -> dict:
        """Mark *batch_id* as executed.

        Returns a summary dict with ``batch_id``, ``task_count``, and
        ``status``.  Raises ``KeyError`` if the batch does not exist.
        """
        with self._lock:
            batch = self._state.batches.get(batch_id)
            if batch is None:
                raise KeyError(f"unknown batch: {batch_id}")

            batch["status"] = "completed"
            batch["executed_at"] = time.time()
            task_count = len(batch["tasks"])

        logger.debug(
            "agent_batch_executor.execute_batch",
            batch_id=batch_id,
            task_count=task_count,
        )
        self._fire("batch_executed", {
            "batch_id": batch_id,
            "task_count": task_count,
        })
        return {
            "batch_id": batch_id,
            "task_count": task_count,
            "status": "completed",
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_batch(self, batch_id: str) -> Optional[dict]:
        """Return a single batch as a dict, or ``None``."""
        with self._lock:
            batch = self._state.batches.get(batch_id)
            if batch is None:
                return None
            return dict(batch)

    def get_batches(self, agent_id: str) -> list:
        """Return all batches belonging to *agent_id*, newest first."""
        with self._lock:
            results = [
                dict(b)
                for b in self._state.batches.values()
                if b["agent_id"] == agent_id
            ]
            results.sort(key=lambda b: b["seq"], reverse=True)
            return results

    # ------------------------------------------------------------------
    # Counting / Listing
    # ------------------------------------------------------------------

    def get_batch_count(self, agent_id: str = "") -> int:
        """Count batches, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return len(self._state.batches)
            return sum(
                1 for b in self._state.batches.values()
                if b["agent_id"] == agent_id
            )

    def list_agents(self) -> list:
        """Return all unique agent IDs that have at least one batch."""
        with self._lock:
            return list({b["agent_id"] for b in self._state.batches.values()})

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* is taken."""
        with self._lock:
            if name in self._state.callbacks:
                return False
            self._state.callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        with self._lock:
            pending = sum(
                1 for b in self._state.batches.values()
                if b["status"] == "pending"
            )
            completed = sum(
                1 for b in self._state.batches.values()
                if b["status"] == "completed"
            )
            return {
                "total_batches": len(self._state.batches),
                "pending": pending,
                "completed": completed,
                "unique_agents": len({
                    b["agent_id"] for b in self._state.batches.values()
                }),
                "max_batches": self._max_batches,
                "seq": self._state._seq,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.batches.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
        logger.debug("agent_batch_executor.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of batches when at capacity."""
        batches = sorted(self._state.batches.values(), key=lambda b: b["seq"])
        to_remove = max(len(batches) // 4, 1)
        for b in batches[:to_remove]:
            del self._state.batches[b["batch_id"]]
        logger.debug("agent_batch_executor.prune", removed=to_remove)
