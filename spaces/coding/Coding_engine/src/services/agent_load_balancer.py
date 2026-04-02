"""Agent Load Balancer -- distributes tasks across agents using round-robin or least-loaded strategy.

Provides agent registration with configurable capacity, task assignment
using pluggable strategies, task completion tracking, and change callbacks.
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
class _AgentEntry:
    """Internal record for a registered agent."""

    entry_id: str = ""
    agent_id: str = ""
    capacity: int = 10
    active_tasks: List[str] = field(default_factory=list)
    total_assigned: int = 0
    total_completed: int = 0
    created_at: float = field(default_factory=time.time)
    seq: int = 0


class AgentLoadBalancer:
    """Distributes tasks across agents using round-robin or least-loaded strategy."""

    STRATEGIES = ("round_robin", "least_loaded")

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _AgentEntry] = {}  # agent_id -> entry
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries
        self._rr_index: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}:{uuid.uuid4().hex}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"alb-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when max_entries is exceeded."""
        if len(self._entries) <= self._max_entries:
            return
        sorted_agents = sorted(
            self._entries.values(), key=lambda e: e.created_at,
        )
        remove_count = len(self._entries) - self._max_entries
        for entry in sorted_agents[:remove_count]:
            del self._entries[entry.agent_id]
            logger.info(
                "agent_pruned",
                agent_id=entry.agent_id,
                entry_id=entry.entry_id,
            )
        self._fire("pruned", {"removed": remove_count})

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, capacity: int = 10) -> str:
        """Register an agent with the load balancer.

        Returns the entry ID on success, or empty string on failure.
        """
        if not agent_id:
            logger.warning("register_agent_failed", reason="empty_agent_id")
            return ""
        if agent_id in self._entries:
            logger.warning("register_agent_failed", reason="duplicate", agent_id=agent_id)
            return ""
        if capacity < 1:
            logger.warning("register_agent_failed", reason="invalid_capacity", capacity=capacity)
            return ""

        entry_id = self._next_id(agent_id)
        self._entries[agent_id] = _AgentEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            capacity=capacity,
            seq=self._seq,
        )
        self._prune_if_needed()
        logger.info("agent_registered", agent_id=agent_id, entry_id=entry_id, capacity=capacity)
        self._fire("agent_registered", {"agent_id": agent_id, "entry_id": entry_id})
        return entry_id

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the pool.

        Returns True if the agent was removed, False if not found.
        """
        if agent_id not in self._entries:
            logger.warning("unregister_agent_failed", reason="not_found", agent_id=agent_id)
            return False
        del self._entries[agent_id]
        logger.info("agent_unregistered", agent_id=agent_id)
        self._fire("agent_unregistered", {"agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Task assignment
    # ------------------------------------------------------------------

    def assign_task(self, task_name: str, strategy: str = "least_loaded") -> Optional[str]:
        """Assign a task to the best available agent.

        Strategies:
            - ``round_robin``: cycle through agents in order.
            - ``least_loaded``: pick the agent with the fewest active tasks.

        Returns the ``agent_id`` that received the task, or ``None`` if no
        agent has available capacity.
        """
        if not task_name:
            logger.warning("assign_task_failed", reason="empty_task_name")
            return None

        effective_strategy = strategy if strategy in self.STRATEGIES else "least_loaded"

        candidates = [
            e for e in self._entries.values()
            if len(e.active_tasks) < e.capacity
        ]
        if not candidates:
            logger.warning("assign_task_failed", reason="no_capacity", task=task_name)
            return None

        selected: Optional[_AgentEntry] = None

        if effective_strategy == "round_robin":
            candidates.sort(key=lambda e: e.agent_id)
            idx = self._rr_index % len(candidates)
            selected = candidates[idx]
            self._rr_index += 1
        elif effective_strategy == "least_loaded":
            selected = min(candidates, key=lambda e: len(e.active_tasks))

        if selected is None:
            return None

        selected.active_tasks.append(task_name)
        selected.total_assigned += 1
        logger.info(
            "task_assigned",
            agent_id=selected.agent_id,
            task=task_name,
            strategy=effective_strategy,
            load=len(selected.active_tasks),
        )
        self._fire("task_assigned", {
            "agent_id": selected.agent_id,
            "task": task_name,
            "strategy": effective_strategy,
        })
        return selected.agent_id

    def complete_task(self, agent_id: str, task_name: str) -> bool:
        """Mark a task as complete and free capacity on the agent.

        Returns True if the task was found and removed, False otherwise.
        """
        entry = self._entries.get(agent_id)
        if entry is None:
            logger.warning("complete_task_failed", reason="agent_not_found", agent_id=agent_id)
            return False
        if task_name not in entry.active_tasks:
            logger.warning(
                "complete_task_failed",
                reason="task_not_found",
                agent_id=agent_id,
                task=task_name,
            )
            return False

        entry.active_tasks.remove(task_name)
        entry.total_completed += 1
        logger.info("task_completed", agent_id=agent_id, task=task_name)
        self._fire("task_completed", {"agent_id": agent_id, "task": task_name})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_load(self, agent_id: str) -> int:
        """Return the current number of active tasks for an agent.

        Returns -1 if the agent is not registered.
        """
        entry = self._entries.get(agent_id)
        if entry is None:
            return -1
        return len(entry.active_tasks)

    def get_available_capacity(self, agent_id: str) -> int:
        """Return remaining capacity for an agent.

        Returns -1 if the agent is not registered.
        """
        entry = self._entries.get(agent_id)
        if entry is None:
            return -1
        return entry.capacity - len(entry.active_tasks)

    def list_agents(self) -> List[str]:
        """Return all registered agent IDs."""
        return list(self._entries.keys())

    def get_agent_count(self) -> int:
        """Return the total number of registered agents."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return aggregate statistics for the load balancer."""
        total_tasks = sum(len(e.active_tasks) for e in self._entries.values())
        total_capacity = sum(e.capacity for e in self._entries.values())
        total_assigned = sum(e.total_assigned for e in self._entries.values())
        total_completed = sum(e.total_completed for e in self._entries.values())
        return {
            "total_agents": len(self._entries),
            "total_tasks": total_tasks,
            "total_capacity": total_capacity,
            "total_available": total_capacity - total_tasks,
            "total_assigned_all_time": total_assigned,
            "total_completed_all_time": total_completed,
            "avg_utilization": (
                total_tasks / total_capacity if total_capacity > 0 else 0.0
            ),
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback that fires on state changes."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns True if the callback was found and removed.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    def _fire(self, action: str, detail: Any) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", callback=cb_name, action=action)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state — agents, callbacks, and counters."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._rr_index = 0
        logger.info("load_balancer_reset")
