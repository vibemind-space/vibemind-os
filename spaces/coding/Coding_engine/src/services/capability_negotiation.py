"""
Agent Capability Negotiation Protocol — enables agents to advertise
capabilities, request assistance, and negotiate task assignments.

Features:
- Capability advertisements with proficiency levels
- Task requirement specifications
- Best-match agent selection for tasks
- Negotiation requests (ask, offer, accept, reject)
- Collaboration agreements tracking
- Load-aware assignment (prefer agents with lower current load)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class Proficiency(int, Enum):
    NOVICE = 1
    BASIC = 2
    INTERMEDIATE = 3
    ADVANCED = 4
    EXPERT = 5


class NegotiationStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class AgentCapability:
    """An agent's advertised capability."""
    agent_name: str
    capabilities: Dict[str, int] = field(default_factory=dict)  # capability → proficiency
    current_load: int = 0  # number of active tasks
    max_load: int = 10
    available: bool = True
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class TaskRequirement:
    """Requirements for a task that needs agent assignment."""
    task_id: str
    name: str
    required_capabilities: Dict[str, int]  # capability → min proficiency
    preferred_capabilities: Dict[str, int] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    priority: int = 50
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    assigned_to: Optional[str] = None


@dataclass
class Negotiation:
    """A negotiation between agents for task collaboration."""
    neg_id: str
    initiator: str
    target: str
    task_id: str
    message: str
    status: NegotiationStatus
    created_at: float
    resolved_at: float = 0.0
    response_message: str = ""
    terms: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class CapabilityNegotiationProtocol:
    """Manages agent capability advertisement and task negotiation."""

    def __init__(self, negotiation_ttl: float = 300.0):
        self._negotiation_ttl = negotiation_ttl

        # Agent profiles: agent_name → AgentCapability
        self._agents: Dict[str, AgentCapability] = {}

        # Task requirements: task_id → TaskRequirement
        self._tasks: Dict[str, TaskRequirement] = {}

        # Negotiations: neg_id → Negotiation
        self._negotiations: Dict[str, Negotiation] = {}

        # Stats
        self._stats = {
            "total_agents": 0,
            "total_tasks": 0,
            "total_assignments": 0,
            "total_negotiations": 0,
            "total_accepted": 0,
            "total_rejected": 0,
        }

    # ------------------------------------------------------------------
    # Agent capability management
    # ------------------------------------------------------------------

    def advertise(
        self,
        agent_name: str,
        capabilities: Dict[str, int],
        max_load: int = 10,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Advertise agent capabilities. Returns True if new, False if updated."""
        now = time.time()
        is_new = agent_name not in self._agents

        if is_new:
            self._agents[agent_name] = AgentCapability(
                agent_name=agent_name,
                capabilities=capabilities,
                max_load=max_load,
                tags=tags or set(),
                metadata=metadata or {},
                registered_at=now,
                updated_at=now,
            )
            self._stats["total_agents"] += 1
        else:
            agent = self._agents[agent_name]
            agent.capabilities = capabilities
            agent.max_load = max_load
            if tags is not None:
                agent.tags = tags
            if metadata is not None:
                agent.metadata = metadata
            agent.updated_at = now

        return is_new

    def withdraw(self, agent_name: str) -> bool:
        """Remove agent from the protocol."""
        if agent_name not in self._agents:
            return False
        del self._agents[agent_name]
        return True

    def set_availability(self, agent_name: str, available: bool) -> bool:
        """Set agent availability."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False
        agent.available = available
        return True

    def update_load(self, agent_name: str, current_load: int) -> bool:
        """Update agent's current task load."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False
        agent.current_load = max(0, current_load)
        return True

    def get_agent(self, agent_name: str) -> Optional[Dict]:
        """Get agent capability profile."""
        agent = self._agents.get(agent_name)
        if not agent:
            return None
        return self._agent_to_dict(agent)

    def list_agents(
        self,
        available_only: bool = False,
        capability: Optional[str] = None,
        min_proficiency: int = 0,
    ) -> List[Dict]:
        """List agents with optional filters."""
        results = []
        for a in self._agents.values():
            if available_only and (not a.available or a.current_load >= a.max_load):
                continue
            if capability:
                prof = a.capabilities.get(capability, 0)
                if prof < min_proficiency:
                    continue
            results.append(self._agent_to_dict(a))
        return sorted(results, key=lambda x: x["agent_name"])

    def _agent_to_dict(self, a: AgentCapability) -> Dict:
        return {
            "agent_name": a.agent_name,
            "capabilities": dict(a.capabilities),
            "current_load": a.current_load,
            "max_load": a.max_load,
            "available": a.available,
            "load_ratio": round(a.current_load / a.max_load, 2) if a.max_load > 0 else 0,
            "tags": sorted(a.tags),
            "metadata": a.metadata,
            "registered_at": a.registered_at,
            "updated_at": a.updated_at,
        }

    # ------------------------------------------------------------------
    # Task requirements
    # ------------------------------------------------------------------

    def post_task(
        self,
        name: str,
        required_capabilities: Dict[str, int],
        preferred_capabilities: Optional[Dict[str, int]] = None,
        tags: Optional[Set[str]] = None,
        priority: int = 50,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Post a task that needs an agent. Returns task_id."""
        tid = f"task-{uuid.uuid4().hex[:8]}"
        self._tasks[tid] = TaskRequirement(
            task_id=tid,
            name=name,
            required_capabilities=required_capabilities,
            preferred_capabilities=preferred_capabilities or {},
            tags=tags or set(),
            priority=priority,
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._stats["total_tasks"] += 1
        return tid

    def get_task(self, task_id: str) -> Optional[Dict]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "name": task.name,
            "required_capabilities": dict(task.required_capabilities),
            "preferred_capabilities": dict(task.preferred_capabilities),
            "tags": sorted(task.tags),
            "priority": task.priority,
            "assigned_to": task.assigned_to,
            "created_at": task.created_at,
        }

    def list_tasks(self, unassigned_only: bool = False) -> List[Dict]:
        results = []
        for t in self._tasks.values():
            if unassigned_only and t.assigned_to:
                continue
            results.append(self.get_task(t.task_id))
        return sorted(results, key=lambda x: x["priority"], reverse=True)

    def remove_task(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        return True

    # ------------------------------------------------------------------
    # Matching & assignment
    # ------------------------------------------------------------------

    def find_best_agents(self, task_id: str, limit: int = 5) -> List[Dict]:
        """Find best matching agents for a task, scored by fit."""
        task = self._tasks.get(task_id)
        if not task:
            return []

        candidates = []
        for agent in self._agents.values():
            if not agent.available or agent.current_load >= agent.max_load:
                continue

            # Check required capabilities
            meets_required = True
            required_score = 0.0
            for cap, min_prof in task.required_capabilities.items():
                agent_prof = agent.capabilities.get(cap, 0)
                if agent_prof < min_prof:
                    meets_required = False
                    break
                required_score += agent_prof / max(min_prof, 1)

            if not meets_required:
                continue

            # Score preferred capabilities
            preferred_score = 0.0
            for cap, pref_prof in task.preferred_capabilities.items():
                agent_prof = agent.capabilities.get(cap, 0)
                preferred_score += min(agent_prof / max(pref_prof, 1), 1.0)

            # Load penalty (lower load = better)
            load_ratio = agent.current_load / agent.max_load if agent.max_load > 0 else 0
            load_bonus = 1.0 - load_ratio

            total_score = required_score + preferred_score * 0.5 + load_bonus * 0.3
            candidates.append({
                "agent_name": agent.agent_name,
                "score": round(total_score, 3),
                "required_score": round(required_score, 3),
                "preferred_score": round(preferred_score, 3),
                "load_ratio": round(load_ratio, 2),
                "capabilities": dict(agent.capabilities),
            })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:limit]

    def assign_task(self, task_id: str, agent_name: str) -> bool:
        """Assign a task to an agent."""
        task = self._tasks.get(task_id)
        agent = self._agents.get(agent_name)
        if not task or not agent:
            return False
        if task.assigned_to:
            return False  # Already assigned

        task.assigned_to = agent_name
        agent.current_load += 1
        self._stats["total_assignments"] += 1
        return True

    def unassign_task(self, task_id: str) -> bool:
        """Unassign a task."""
        task = self._tasks.get(task_id)
        if not task or not task.assigned_to:
            return False
        agent = self._agents.get(task.assigned_to)
        if agent:
            agent.current_load = max(0, agent.current_load - 1)
        task.assigned_to = None
        return True

    def auto_assign(self, task_id: str) -> Optional[str]:
        """Automatically assign task to best available agent. Returns agent_name or None."""
        candidates = self.find_best_agents(task_id, limit=1)
        if not candidates:
            return None
        agent_name = candidates[0]["agent_name"]
        if self.assign_task(task_id, agent_name):
            return agent_name
        return None

    # ------------------------------------------------------------------
    # Negotiation
    # ------------------------------------------------------------------

    def request_collaboration(
        self,
        initiator: str,
        target: str,
        task_id: str,
        message: str = "",
        terms: Optional[Dict] = None,
    ) -> Optional[str]:
        """Initiator requests collaboration from target. Returns neg_id."""
        if initiator not in self._agents or target not in self._agents:
            return None
        if task_id not in self._tasks:
            return None

        nid = f"neg-{uuid.uuid4().hex[:8]}"
        self._negotiations[nid] = Negotiation(
            neg_id=nid,
            initiator=initiator,
            target=target,
            task_id=task_id,
            message=message,
            status=NegotiationStatus.OPEN,
            created_at=time.time(),
            terms=terms or {},
        )
        self._stats["total_negotiations"] += 1
        return nid

    def respond_negotiation(
        self,
        neg_id: str,
        accept: bool,
        response_message: str = "",
    ) -> bool:
        """Target responds to a negotiation."""
        neg = self._negotiations.get(neg_id)
        if not neg or neg.status != NegotiationStatus.OPEN:
            return False

        if accept:
            neg.status = NegotiationStatus.ACCEPTED
            self._stats["total_accepted"] += 1
        else:
            neg.status = NegotiationStatus.REJECTED
            self._stats["total_rejected"] += 1

        neg.response_message = response_message
        neg.resolved_at = time.time()
        return True

    def cancel_negotiation(self, neg_id: str) -> bool:
        """Initiator cancels a negotiation."""
        neg = self._negotiations.get(neg_id)
        if not neg or neg.status != NegotiationStatus.OPEN:
            return False
        neg.status = NegotiationStatus.CANCELLED
        neg.resolved_at = time.time()
        return True

    def get_negotiation(self, neg_id: str) -> Optional[Dict]:
        neg = self._negotiations.get(neg_id)
        if not neg:
            return None
        return {
            "neg_id": neg.neg_id,
            "initiator": neg.initiator,
            "target": neg.target,
            "task_id": neg.task_id,
            "message": neg.message,
            "status": neg.status.value,
            "response_message": neg.response_message,
            "terms": neg.terms,
            "created_at": neg.created_at,
            "resolved_at": neg.resolved_at,
        }

    def get_agent_negotiations(
        self,
        agent_name: str,
        status: Optional[str] = None,
    ) -> List[Dict]:
        """Get negotiations involving an agent."""
        results = []
        for n in self._negotiations.values():
            if n.initiator != agent_name and n.target != agent_name:
                continue
            if status and n.status.value != status:
                continue
            results.append(self.get_negotiation(n.neg_id))
        return sorted(results, key=lambda x: x["created_at"], reverse=True)

    def expire_old_negotiations(self) -> int:
        """Expire old open negotiations. Returns count expired."""
        now = time.time()
        expired = 0
        for n in self._negotiations.values():
            if n.status == NegotiationStatus.OPEN:
                if (now - n.created_at) > self._negotiation_ttl:
                    n.status = NegotiationStatus.EXPIRED
                    n.resolved_at = now
                    expired += 1
        return expired

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "active_agents": sum(1 for a in self._agents.values() if a.available),
            "unassigned_tasks": sum(1 for t in self._tasks.values() if not t.assigned_to),
            "open_negotiations": sum(1 for n in self._negotiations.values()
                                     if n.status == NegotiationStatus.OPEN),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._tasks.clear()
        self._negotiations.clear()
        self._stats = {k: 0 for k in self._stats}
