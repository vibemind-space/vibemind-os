"""Agent workload balancer.

Distributes tasks across agents based on current load, capacity,
and assignment strategies. Tracks agent availability and load metrics.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Agent:
    """Internal agent record."""
    agent_id: str = ""
    name: str = ""
    capacity: int = 10
    current_load: int = 0
    status: str = "available"  # available, busy, offline, draining
    total_assigned: int = 0
    total_completed: int = 0
    total_failed: int = 0
    tags: List[str] = field(default_factory=list)
    registered_at: float = 0.0


@dataclass
class _Assignment:
    """Internal assignment record."""
    assignment_id: str = ""
    agent_id: str = ""
    task_name: str = ""
    priority: int = 0
    status: str = "active"  # active, completed, failed
    created_at: float = 0.0
    completed_at: float = 0.0


class AgentWorkloadBalancer:
    """Distributes tasks across agents based on load and capacity."""

    STRATEGIES = ("least_loaded", "round_robin", "weighted", "random")

    def __init__(self, max_agents: int = 1000, max_assignments: int = 50000):
        self._max_agents = max_agents
        self._max_assignments = max_assignments
        self._agents: Dict[str, _Agent] = {}
        self._assignments: Dict[str, _Assignment] = {}
        self._rr_index = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_agents_registered": 0,
            "total_assigned": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_rebalances": 0,
        }

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    def register_agent(self, name: str, capacity: int = 10,
                       tags: Optional[List[str]] = None) -> str:
        """Register an agent."""
        if not name or capacity < 1:
            return ""
        if len(self._agents) >= self._max_agents:
            return ""

        aid = "wl-" + hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12]
        self._agents[aid] = _Agent(
            agent_id=aid,
            name=name,
            capacity=capacity,
            tags=tags or [],
            registered_at=time.time(),
        )
        self._stats["total_agents_registered"] += 1
        return aid

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get agent info."""
        a = self._agents.get(agent_id)
        if not a:
            return None
        return {
            "agent_id": a.agent_id,
            "name": a.name,
            "capacity": a.capacity,
            "current_load": a.current_load,
            "available_slots": a.capacity - a.current_load,
            "utilization": round(a.current_load / a.capacity, 4) if a.capacity > 0 else 0,
            "status": a.status,
            "total_assigned": a.total_assigned,
            "total_completed": a.total_completed,
            "total_failed": a.total_failed,
            "tags": list(a.tags),
        }

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent (only if no active assignments)."""
        a = self._agents.get(agent_id)
        if not a:
            return False
        if a.current_load > 0:
            return False
        del self._agents[agent_id]
        return True

    def set_status(self, agent_id: str, status: str) -> bool:
        """Set agent status."""
        a = self._agents.get(agent_id)
        if not a:
            return False
        if status not in ("available", "busy", "offline", "draining"):
            return False
        a.status = status
        return True

    def update_capacity(self, agent_id: str, capacity: int) -> bool:
        """Update agent capacity."""
        a = self._agents.get(agent_id)
        if not a or capacity < 1:
            return False
        a.capacity = capacity
        return True

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def assign_task(self, task_name: str, strategy: str = "least_loaded",
                    priority: int = 0, required_tag: Optional[str] = None) -> str:
        """Assign a task to an agent using the specified strategy."""
        if not task_name:
            return ""
        if strategy not in self.STRATEGIES:
            return ""

        candidates = self._get_candidates(required_tag)
        if not candidates:
            return ""

        agent = self._select_agent(candidates, strategy)
        if not agent:
            return ""

        if len(self._assignments) >= self._max_assignments:
            done = [k for k, a in self._assignments.items() if a.status != "active"]
            for k in done[:len(done) // 2]:
                del self._assignments[k]

        asid = "assign-" + hashlib.md5(
            f"{task_name}{agent.agent_id}{time.time()}".encode()
        ).hexdigest()[:12]

        self._assignments[asid] = _Assignment(
            assignment_id=asid,
            agent_id=agent.agent_id,
            task_name=task_name,
            priority=priority,
            created_at=time.time(),
        )
        agent.current_load += 1
        agent.total_assigned += 1
        self._stats["total_assigned"] += 1

        self._fire("task_assigned", {
            "assignment_id": asid, "agent_id": agent.agent_id,
            "task_name": task_name,
        })
        return asid

    def complete_assignment(self, assignment_id: str) -> bool:
        """Mark an assignment as completed."""
        a = self._assignments.get(assignment_id)
        if not a or a.status != "active":
            return False

        a.status = "completed"
        a.completed_at = time.time()

        agent = self._agents.get(a.agent_id)
        if agent:
            agent.current_load = max(0, agent.current_load - 1)
            agent.total_completed += 1

        self._stats["total_completed"] += 1
        return True

    def fail_assignment(self, assignment_id: str) -> bool:
        """Mark an assignment as failed."""
        a = self._assignments.get(assignment_id)
        if not a or a.status != "active":
            return False

        a.status = "failed"
        a.completed_at = time.time()

        agent = self._agents.get(a.agent_id)
        if agent:
            agent.current_load = max(0, agent.current_load - 1)
            agent.total_failed += 1

        self._stats["total_failed"] += 1
        return True

    def get_assignment(self, assignment_id: str) -> Optional[Dict]:
        """Get assignment info."""
        a = self._assignments.get(assignment_id)
        if not a:
            return None
        return {
            "assignment_id": a.assignment_id,
            "agent_id": a.agent_id,
            "task_name": a.task_name,
            "priority": a.priority,
            "status": a.status,
            "created_at": a.created_at,
            "completed_at": a.completed_at,
        }

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _get_candidates(self, required_tag: Optional[str]) -> List[_Agent]:
        """Get available agents with capacity."""
        candidates = []
        for a in self._agents.values():
            if a.status not in ("available",):
                continue
            if a.current_load >= a.capacity:
                continue
            if required_tag and required_tag not in a.tags:
                continue
            candidates.append(a)
        return candidates

    def _select_agent(self, candidates: List[_Agent], strategy: str) -> Optional[_Agent]:
        """Select an agent based on strategy."""
        if not candidates:
            return None

        if strategy == "least_loaded":
            return min(candidates, key=lambda a: a.current_load / a.capacity)
        elif strategy == "round_robin":
            idx = self._rr_index % len(candidates)
            self._rr_index += 1
            return candidates[idx]
        elif strategy == "weighted":
            # Prefer agents with more available capacity
            return max(candidates, key=lambda a: a.capacity - a.current_load)
        elif strategy == "random":
            import random
            return random.choice(candidates)
        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent_assignments(self, agent_id: str,
                               active_only: bool = True) -> List[Dict]:
        """Get assignments for an agent."""
        result = []
        for a in self._assignments.values():
            if a.agent_id != agent_id:
                continue
            if active_only and a.status != "active":
                continue
            result.append({
                "assignment_id": a.assignment_id,
                "task_name": a.task_name,
                "status": a.status,
                "priority": a.priority,
            })
        return result

    def get_load_report(self) -> List[Dict]:
        """Get load report for all agents."""
        result = []
        for a in self._agents.values():
            result.append({
                "agent_id": a.agent_id,
                "name": a.name,
                "current_load": a.current_load,
                "capacity": a.capacity,
                "available_slots": a.capacity - a.current_load,
                "utilization": round(a.current_load / a.capacity, 4) if a.capacity > 0 else 0,
                "status": a.status,
            })
        result.sort(key=lambda x: -x["utilization"])
        return result

    def get_available_agents(self, required_tag: Optional[str] = None) -> List[Dict]:
        """Get agents with available capacity."""
        candidates = self._get_candidates(required_tag)
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "available_slots": a.capacity - a.current_load,
            }
            for a in candidates
        ]

    def get_overloaded_agents(self, threshold: float = 0.9) -> List[Dict]:
        """Get agents above utilization threshold."""
        result = []
        for a in self._agents.values():
            util = a.current_load / a.capacity if a.capacity > 0 else 0
            if util >= threshold:
                result.append({
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "utilization": round(util, 4),
                })
        return result

    def list_agents(self, status: Optional[str] = None,
                    tag: Optional[str] = None) -> List[Dict]:
        """List agents with optional filters."""
        result = []
        for a in self._agents.values():
            if status and a.status != status:
                continue
            if tag and tag not in a.tags:
                continue
            result.append({
                "agent_id": a.agent_id,
                "name": a.name,
                "status": a.status,
                "current_load": a.current_load,
                "capacity": a.capacity,
            })
        return result

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
            "current_agents": len(self._agents),
            "available_agents": sum(
                1 for a in self._agents.values() if a.status == "available"
            ),
            "current_assignments": len(self._assignments),
            "active_assignments": sum(
                1 for a in self._assignments.values() if a.status == "active"
            ),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._assignments.clear()
        self._rr_index = 0
        self._stats = {k: 0 for k in self._stats}
