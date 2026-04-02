"""Agent Task Allocator -- assigns tasks to agents based on availability,
capacity, and workload.

Provides:
- Agent registration with configurable capacity and tags
- Automatic least-loaded agent selection when no agent is specified
- Task assignment lifecycle (active -> completed)
- Per-agent workload and utilization tracking
- Callback-based change notifications
- Max-entries pruning to bound memory usage

Usage::

    allocator = AgentTaskAllocator()

    allocator.register_agent("agent-1", capacity=5, tags=["backend"])
    allocator.register_agent("agent-2", capacity=10, tags=["frontend"])

    aid = allocator.allocate("task-build-api", priority=3)
    allocator.complete_task(aid)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------------
# Internal state
# -------------------------------------------------------------------

@dataclass
class _AgentSlot:
    """Registered agent with capacity tracking."""

    agent_id: str
    capacity: int
    tags: List[str]
    registered_at: float
    active_tasks: int = 0
    total_assigned: int = 0
    total_completed: int = 0


@dataclass
class _TaskAssignment:
    """A single task-to-agent assignment."""

    assignment_id: str
    task_id: str
    agent_id: str
    priority: int
    status: str  # "active" | "completed"
    created_at: float
    completed_at: Optional[float] = None


# -------------------------------------------------------------------
# AgentTaskAllocator
# -------------------------------------------------------------------

class AgentTaskAllocator:
    """Assigns tasks to agents based on availability, capacity, and workload."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._seq = 0

        self._agents: Dict[str, _AgentSlot] = {}
        self._assignments: Dict[str, _TaskAssignment] = {}
        self._callbacks: Dict[str, Callable] = {}

        # Stats counters
        self._total_assignments = 0
        self._total_completed = 0
        self._total_auto_assigned = 0
        self._total_pruned = 0

    # ---------------------------------------------------------------
    # ID generation
    # ---------------------------------------------------------------

    def _next_id(self, task_id: str, agent_id: str) -> str:
        """Generate a collision-free assignment ID with prefix ``ata-``."""
        self._seq += 1
        raw = f"{task_id}-{agent_id}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ata-{digest}"

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback invoked on state changes.

        Args:
            name: Unique name for this callback.
            callback: ``callback(action, data)`` where *action* is a string
                like ``"allocated"`` or ``"completed"`` and *data* is a dict.

        Returns:
            ``True`` if registered, ``False`` if *name* already exists.
        """
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name.

        Returns:
            ``True`` if removed, ``False`` if *name* was not registered.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *data*."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ---------------------------------------------------------------
    # Pruning
    # ---------------------------------------------------------------

    def _maybe_prune(self) -> None:
        """Remove oldest completed assignments when *max_entries* is exceeded."""
        if len(self._assignments) <= self._max_entries:
            return

        completed = [
            (a.completed_at or 0.0, aid)
            for aid, a in self._assignments.items()
            if a.status == "completed"
        ]
        completed.sort()

        to_remove = len(self._assignments) - self._max_entries
        for _, aid in completed[:to_remove]:
            del self._assignments[aid]
            self._total_pruned += 1

    # ---------------------------------------------------------------
    # Agent registration
    # ---------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        capacity: int = 10,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a new agent with the allocator.

        Args:
            agent_id: Unique identifier for the agent.
            capacity: Maximum number of concurrent tasks.
            tags: Optional list of tags for filtering.

        Returns:
            The *agent_id* on success, or ``""`` if the agent is already
            registered or *agent_id* is empty.
        """
        if not agent_id or agent_id in self._agents:
            return ""

        self._agents[agent_id] = _AgentSlot(
            agent_id=agent_id,
            capacity=max(1, capacity),
            tags=list(tags) if tags else [],
            registered_at=time.time(),
        )

        logger.info("agent_registered", agent_id=agent_id, capacity=capacity)
        self._fire("agent_registered", {"agent_id": agent_id, "capacity": capacity})
        return agent_id

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the allocator.

        Active assignments held by this agent are marked completed so that
        internal counts remain consistent.

        Returns:
            ``True`` if the agent was removed, ``False`` if not found.
        """
        slot = self._agents.get(agent_id)
        if not slot:
            return False

        # Complete any active assignments for this agent
        for a in self._assignments.values():
            if a.agent_id == agent_id and a.status == "active":
                a.status = "completed"
                a.completed_at = time.time()
                self._total_completed += 1

        del self._agents[agent_id]

        logger.info("agent_removed", agent_id=agent_id)
        self._fire("agent_removed", {"agent_id": agent_id})
        return True

    # ---------------------------------------------------------------
    # Allocation
    # ---------------------------------------------------------------

    def allocate(
        self,
        task_id: str,
        agent_id: Optional[str] = None,
        priority: int = 5,
    ) -> str:
        """Allocate a task to an agent.

        If *agent_id* is ``None`` the least-loaded agent is chosen
        automatically.  The priority is clamped to the range 0-9 (lower is
        higher priority).

        Args:
            task_id: Application-level task identifier.
            agent_id: Explicit agent, or ``None`` to auto-select.
            priority: Priority level 0 (highest) to 9 (lowest).

        Returns:
            The generated *assignment_id*, or ``""`` if no agent is available
            or the chosen agent is at capacity.
        """
        priority = max(0, min(9, priority))

        if agent_id is not None:
            slot = self._agents.get(agent_id)
            if not slot or slot.active_tasks >= slot.capacity:
                return ""
        else:
            slot = self._pick_least_loaded()
            if not slot:
                return ""
            self._total_auto_assigned += 1

        assignment_id = self._next_id(task_id, slot.agent_id)

        self._assignments[assignment_id] = _TaskAssignment(
            assignment_id=assignment_id,
            task_id=task_id,
            agent_id=slot.agent_id,
            priority=priority,
            status="active",
            created_at=time.time(),
        )

        slot.active_tasks += 1
        slot.total_assigned += 1
        self._total_assignments += 1

        self._maybe_prune()

        logger.info(
            "task_allocated",
            assignment_id=assignment_id,
            task_id=task_id,
            agent_id=slot.agent_id,
            priority=priority,
        )
        self._fire("allocated", {
            "assignment_id": assignment_id,
            "task_id": task_id,
            "agent_id": slot.agent_id,
            "priority": priority,
        })
        return assignment_id

    # ---------------------------------------------------------------
    # Completion
    # ---------------------------------------------------------------

    def complete_task(self, assignment_id: str) -> bool:
        """Mark an assignment as completed.

        Args:
            assignment_id: The ID returned by :meth:`allocate`.

        Returns:
            ``True`` if the assignment was completed, ``False`` if not found
            or already completed.
        """
        assignment = self._assignments.get(assignment_id)
        if not assignment or assignment.status != "active":
            return False

        assignment.status = "completed"
        assignment.completed_at = time.time()

        slot = self._agents.get(assignment.agent_id)
        if slot and slot.active_tasks > 0:
            slot.active_tasks -= 1
            slot.total_completed += 1

        self._total_completed += 1

        logger.info(
            "task_completed",
            assignment_id=assignment_id,
            agent_id=assignment.agent_id,
        )
        self._fire("completed", {
            "assignment_id": assignment_id,
            "task_id": assignment.task_id,
            "agent_id": assignment.agent_id,
        })
        return True

    # ---------------------------------------------------------------
    # Queries
    # ---------------------------------------------------------------

    def get_assignment(self, assignment_id: str) -> Optional[Dict[str, Any]]:
        """Return assignment details as a dict, or ``None`` if not found."""
        a = self._assignments.get(assignment_id)
        if not a:
            return None
        return {
            "assignment_id": a.assignment_id,
            "task_id": a.task_id,
            "agent_id": a.agent_id,
            "priority": a.priority,
            "status": a.status,
            "created_at": a.created_at,
            "completed_at": a.completed_at,
        }

    def get_agent_workload(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return workload info for a single agent, or ``None`` if not found.

        Returns a dict with keys ``agent_id``, ``active_tasks``, ``capacity``,
        and ``utilization`` (0.0 -- 1.0).
        """
        slot = self._agents.get(agent_id)
        if not slot:
            return None
        return {
            "agent_id": slot.agent_id,
            "active_tasks": slot.active_tasks,
            "capacity": slot.capacity,
            "utilization": slot.active_tasks / slot.capacity if slot.capacity > 0 else 0.0,
        }

    def get_least_loaded(self) -> Optional[Dict[str, Any]]:
        """Return the least-loaded agent as a dict, or ``None`` if empty.

        Returns a dict with ``agent_id``, ``active_tasks``, ``capacity``,
        ``utilization``, and ``tags``.
        """
        slot = self._pick_least_loaded()
        if not slot:
            return None
        return {
            "agent_id": slot.agent_id,
            "active_tasks": slot.active_tasks,
            "capacity": slot.capacity,
            "utilization": slot.active_tasks / slot.capacity if slot.capacity > 0 else 0.0,
            "tags": list(slot.tags),
        }

    def list_assignments(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List assignments, optionally filtered by *agent_id* and/or *status*.

        Args:
            agent_id: Filter to assignments for this agent.
            status: Filter to ``"active"`` or ``"completed"``.

        Returns:
            A list of assignment dicts sorted by creation time (newest first).
        """
        results: List[Dict[str, Any]] = []
        for a in self._assignments.values():
            if agent_id is not None and a.agent_id != agent_id:
                continue
            if status is not None and a.status != status:
                continue
            results.append({
                "assignment_id": a.assignment_id,
                "task_id": a.task_id,
                "agent_id": a.agent_id,
                "priority": a.priority,
                "status": a.status,
                "created_at": a.created_at,
                "completed_at": a.completed_at,
            })
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def list_agents(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List registered agents, optionally filtered by *tag*.

        Args:
            tag: If provided, only agents with this tag are returned.

        Returns:
            A list of agent info dicts.
        """
        results: List[Dict[str, Any]] = []
        for slot in self._agents.values():
            if tag is not None and tag not in slot.tags:
                continue
            results.append({
                "agent_id": slot.agent_id,
                "capacity": slot.capacity,
                "active_tasks": slot.active_tasks,
                "utilization": slot.active_tasks / slot.capacity if slot.capacity > 0 else 0.0,
                "tags": list(slot.tags),
                "total_assigned": slot.total_assigned,
                "total_completed": slot.total_completed,
                "registered_at": slot.registered_at,
            })
        return results

    # ---------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return allocator statistics as a dict.

        Keys include ``total_assignments``, ``total_completed``,
        ``total_auto_assigned``, ``total_pruned``, ``registered_agents``,
        ``active_assignments``, and ``avg_utilization``.
        """
        active = sum(1 for a in self._assignments.values() if a.status == "active")
        total_cap = sum(s.capacity for s in self._agents.values())
        total_load = sum(s.active_tasks for s in self._agents.values())

        return {
            "total_assignments": self._total_assignments,
            "total_completed": self._total_completed,
            "total_auto_assigned": self._total_auto_assigned,
            "total_pruned": self._total_pruned,
            "registered_agents": len(self._agents),
            "active_assignments": active,
            "total_capacity": total_cap,
            "total_load": total_load,
            "avg_utilization": total_load / total_cap if total_cap > 0 else 0.0,
        }

    # ---------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------

    def reset(self) -> None:
        """Clear all allocator state, returning it to a pristine condition."""
        self._agents.clear()
        self._assignments.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_assignments = 0
        self._total_completed = 0
        self._total_auto_assigned = 0
        self._total_pruned = 0
        logger.info("allocator_reset")

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    def _pick_least_loaded(self) -> Optional[_AgentSlot]:
        """Return the agent slot with the lowest utilization ratio.

        Only considers agents that have remaining capacity.  Returns ``None``
        when no agent can accept a task.
        """
        best: Optional[_AgentSlot] = None
        best_ratio = float("inf")

        for slot in self._agents.values():
            if slot.active_tasks >= slot.capacity:
                continue
            ratio = slot.active_tasks / slot.capacity if slot.capacity > 0 else 0.0
            if ratio < best_ratio:
                best_ratio = ratio
                best = slot

        return best
