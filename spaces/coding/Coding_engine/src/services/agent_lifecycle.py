"""
Agent Lifecycle Manager — tracks agent creation, states, heartbeats,
graceful shutdown, and lifecycle events.

Features:
- Agent registration with typed roles
- State tracking (idle, busy, paused, stopping, stopped)
- Heartbeat monitoring with configurable timeout
- Graceful shutdown protocol
- Lifecycle event history
- Agent group management
- Health-aware lifecycle decisions
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class AgentState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentRecord:
    """Record of a managed agent."""
    agent_id: str
    name: str
    role: str
    state: AgentState
    registered_at: float
    last_heartbeat: float
    heartbeat_timeout: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    groups: Set[str] = field(default_factory=set)
    error: str = ""
    shutdown_handler: Optional[Callable] = None


@dataclass
class LifecycleEvent:
    """A lifecycle event record."""
    event_id: str
    agent_id: str
    event_type: str  # registered, state_changed, heartbeat_lost, shutdown, etc.
    old_state: str
    new_state: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent Lifecycle Manager
# ---------------------------------------------------------------------------

class AgentLifecycleManager:
    """Manages agent lifecycle from registration to shutdown."""

    def __init__(
        self,
        default_heartbeat_timeout: float = 30.0,
        max_agents: int = 200,
        max_events: int = 2000,
    ):
        self._default_heartbeat_timeout = default_heartbeat_timeout
        self._max_agents = max_agents
        self._max_events = max_events

        self._agents: Dict[str, AgentRecord] = {}
        self._events: List[LifecycleEvent] = []
        self._groups: Dict[str, Set[str]] = defaultdict(set)  # group → agent_ids

        self._stats = {
            "total_registered": 0,
            "total_stopped": 0,
            "total_heartbeat_losses": 0,
            "total_events": 0,
        }

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        role: str = "worker",
        heartbeat_timeout: float = 0.0,
        groups: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
        shutdown_handler: Optional[Callable] = None,
    ) -> str:
        """Register a new agent. Returns agent_id."""
        aid = f"agent-{uuid.uuid4().hex[:8]}"
        now = time.time()
        timeout = heartbeat_timeout or self._default_heartbeat_timeout

        self._agents[aid] = AgentRecord(
            agent_id=aid,
            name=name,
            role=role,
            state=AgentState.IDLE,
            registered_at=now,
            last_heartbeat=now,
            heartbeat_timeout=timeout,
            metadata=metadata or {},
            groups=groups or set(),
            shutdown_handler=shutdown_handler,
        )

        # Add to groups
        for g in (groups or set()):
            self._groups[g].add(aid)

        self._stats["total_registered"] += 1
        self._record_event(aid, "registered", "", "idle")
        return aid

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent (removes completely)."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        # Remove from groups
        for g in agent.groups:
            self._groups[g].discard(agent_id)

        self._record_event(agent_id, "unregistered", agent.state.value, "removed")
        del self._agents[agent_id]
        return True

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get agent details."""
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return self._agent_to_dict(agent)

    def find_agent(self, name: str) -> Optional[Dict]:
        """Find agent by name."""
        for agent in self._agents.values():
            if agent.name == name:
                return self._agent_to_dict(agent)
        return None

    def list_agents(
        self,
        role: Optional[str] = None,
        state: Optional[str] = None,
        group: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List agents with filters."""
        results = []
        for agent in sorted(self._agents.values(), key=lambda a: a.name):
            if role and agent.role != role:
                continue
            if state and agent.state.value != state:
                continue
            if group and group not in agent.groups:
                continue
            results.append(self._agent_to_dict(agent))
            if len(results) >= limit:
                break
        return results

    def _agent_to_dict(self, agent: AgentRecord) -> Dict:
        now = time.time()
        since_hb = now - agent.last_heartbeat
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "state": agent.state.value,
            "registered_at": agent.registered_at,
            "last_heartbeat": agent.last_heartbeat,
            "heartbeat_age": round(since_hb, 2),
            "heartbeat_timeout": agent.heartbeat_timeout,
            "is_alive": since_hb < agent.heartbeat_timeout,
            "groups": sorted(agent.groups),
            "metadata": agent.metadata,
            "error": agent.error,
            "uptime_seconds": round(now - agent.registered_at, 2),
        }

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state(self, agent_id: str, state: str) -> bool:
        """Set agent state."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        try:
            new_state = AgentState(state)
        except ValueError:
            return False

        old = agent.state.value
        agent.state = new_state
        if state == "error":
            pass  # error field set separately
        self._record_event(agent_id, "state_changed", old, state)
        return True

    def set_error(self, agent_id: str, error: str) -> bool:
        """Put agent in error state with message."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        old = agent.state.value
        agent.state = AgentState.ERROR
        agent.error = error
        self._record_event(agent_id, "error", old, "error", {"error": error})
        return True

    def clear_error(self, agent_id: str) -> bool:
        """Clear error state, return to idle."""
        agent = self._agents.get(agent_id)
        if not agent or agent.state != AgentState.ERROR:
            return False
        agent.state = AgentState.IDLE
        agent.error = ""
        self._record_event(agent_id, "error_cleared", "error", "idle")
        return True

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(self, agent_id: str, metadata: Optional[Dict] = None) -> bool:
        """Record a heartbeat from an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.last_heartbeat = time.time()
        if metadata:
            agent.metadata.update(metadata)
        return True

    def check_heartbeats(self) -> List[Dict]:
        """Check for agents with expired heartbeats. Returns list of lost agents."""
        now = time.time()
        lost = []
        for agent in self._agents.values():
            if agent.state in (AgentState.STOPPED, AgentState.STOPPING):
                continue
            since = now - agent.last_heartbeat
            if since > agent.heartbeat_timeout:
                old = agent.state.value
                agent.state = AgentState.ERROR
                agent.error = f"Heartbeat lost ({round(since, 1)}s)"
                self._stats["total_heartbeat_losses"] += 1
                self._record_event(agent_id=agent.agent_id,
                                   event_type="heartbeat_lost",
                                   old_state=old, new_state="error",
                                   details={"seconds_since": round(since, 1)})
                lost.append(self._agent_to_dict(agent))
        return lost

    # ------------------------------------------------------------------
    # Shutdown protocol
    # ------------------------------------------------------------------

    def request_shutdown(self, agent_id: str, reason: str = "") -> bool:
        """Request graceful shutdown of an agent."""
        agent = self._agents.get(agent_id)
        if not agent or agent.state == AgentState.STOPPED:
            return False

        old = agent.state.value
        agent.state = AgentState.STOPPING
        self._record_event(agent_id, "shutdown_requested", old, "stopping",
                           {"reason": reason})

        if agent.shutdown_handler:
            try:
                agent.shutdown_handler(agent.agent_id, reason)
            except Exception:
                pass

        return True

    def confirm_shutdown(self, agent_id: str) -> bool:
        """Confirm agent has completed shutdown."""
        agent = self._agents.get(agent_id)
        if not agent or agent.state != AgentState.STOPPING:
            return False

        agent.state = AgentState.STOPPED
        self._stats["total_stopped"] += 1
        self._record_event(agent_id, "shutdown_confirmed", "stopping", "stopped")
        return True

    def shutdown_group(self, group: str, reason: str = "") -> int:
        """Request shutdown for all agents in a group. Returns count."""
        agent_ids = self._groups.get(group, set())
        count = 0
        for aid in list(agent_ids):
            if self.request_shutdown(aid, reason):
                count += 1
        return count

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def add_to_group(self, agent_id: str, group: str) -> bool:
        """Add agent to a group."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.groups.add(group)
        self._groups[group].add(agent_id)
        return True

    def remove_from_group(self, agent_id: str, group: str) -> bool:
        """Remove agent from a group."""
        agent = self._agents.get(agent_id)
        if not agent or group not in agent.groups:
            return False
        agent.groups.discard(group)
        self._groups[group].discard(agent_id)
        return True

    def get_group(self, group: str) -> List[Dict]:
        """Get all agents in a group."""
        agent_ids = self._groups.get(group, set())
        return [self._agent_to_dict(self._agents[aid])
                for aid in agent_ids if aid in self._agents]

    def list_groups(self) -> Dict[str, int]:
        """List groups with member counts."""
        return {g: len(ids) for g, ids in sorted(self._groups.items()) if ids}

    # ------------------------------------------------------------------
    # Lifecycle events
    # ------------------------------------------------------------------

    def _record_event(
        self,
        agent_id: str,
        event_type: str,
        old_state: str,
        new_state: str,
        details: Optional[Dict] = None,
    ) -> None:
        eid = f"evt-{uuid.uuid4().hex[:6]}"
        self._events.append(LifecycleEvent(
            event_id=eid,
            agent_id=agent_id,
            event_type=event_type,
            old_state=old_state,
            new_state=new_state,
            timestamp=time.time(),
            details=details or {},
        ))
        self._stats["total_events"] += 1
        self._prune_events()

    def get_events(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get lifecycle events with filters."""
        results = []
        for e in reversed(self._events):
            if agent_id and e.agent_id != agent_id:
                continue
            if event_type and e.event_type != event_type:
                continue
            results.append({
                "event_id": e.event_id,
                "agent_id": e.agent_id,
                "event_type": e.event_type,
                "old_state": e.old_state,
                "new_state": e.new_state,
                "timestamp": e.timestamp,
                "details": e.details,
            })
            if len(results) >= limit:
                break
        return list(reversed(results))

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_events(self) -> None:
        if len(self._events) > self._max_events:
            keep = self._max_events // 2
            self._events = self._events[-keep:]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        states = defaultdict(int)
        for a in self._agents.values():
            states[a.state.value] += 1

        return {
            **self._stats,
            "total_agents": len(self._agents),
            "total_groups": len([g for g, ids in self._groups.items() if ids]),
            "by_state": dict(states),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._events.clear()
        self._groups.clear()
        self._stats = {k: 0 for k in self._stats}
