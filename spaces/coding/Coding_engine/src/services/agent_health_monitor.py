"""
Agent Health Monitor — tracks agent health via heartbeats, detects failures, and manages recovery.

Features:
- Heartbeat-based health tracking
- Configurable timeout thresholds
- Health status levels (healthy, degraded, unhealthy, dead)
- Alert callbacks on status changes
- Health history and trends
- Automatic recovery actions
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

HEALTH_LEVELS = ("healthy", "degraded", "unhealthy", "dead")
HEALTH_RANK = {level: i for i, level in enumerate(HEALTH_LEVELS)}


@dataclass
class AgentHealth:
    """Health state for a single agent."""
    agent_name: str
    status: str  # healthy, degraded, unhealthy, dead
    last_heartbeat: float
    heartbeat_count: int
    degraded_threshold: float  # seconds without heartbeat -> degraded
    unhealthy_threshold: float  # seconds -> unhealthy
    dead_threshold: float  # seconds -> dead
    metadata: Dict[str, Any]
    registered_at: float
    custom_checks: Dict[str, bool]  # named checks -> pass/fail
    history: List[Tuple[float, str]]  # (timestamp, status)
    max_history: int = 100


@dataclass
class HealthAlert:
    """Alert triggered on health status change."""
    alert_id: str
    agent_name: str
    old_status: str
    new_status: str
    timestamp: float


# ---------------------------------------------------------------------------
# Agent Health Monitor
# ---------------------------------------------------------------------------

class AgentHealthMonitor:
    """Tracks agent health via heartbeats and custom checks."""

    def __init__(
        self,
        default_degraded_threshold: float = 30.0,
        default_unhealthy_threshold: float = 60.0,
        default_dead_threshold: float = 120.0,
        max_agents: int = 1000,
        max_alerts: int = 5000,
    ):
        self._default_degraded = default_degraded_threshold
        self._default_unhealthy = default_unhealthy_threshold
        self._default_dead = default_dead_threshold
        self._max_agents = max_agents
        self._max_alerts = max_alerts

        self._agents: Dict[str, AgentHealth] = {}
        self._alerts: List[HealthAlert] = []
        self._callbacks: Dict[str, Callable] = {}  # name -> callback

        self._stats = {
            "total_registered": 0,
            "total_unregistered": 0,
            "total_heartbeats": 0,
            "total_status_changes": 0,
            "total_alerts": 0,
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent_name: str,
        degraded_threshold: float = 0.0,
        unhealthy_threshold: float = 0.0,
        dead_threshold: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register an agent for health monitoring."""
        if agent_name in self._agents:
            return False

        now = time.time()
        self._agents[agent_name] = AgentHealth(
            agent_name=agent_name,
            status="healthy",
            last_heartbeat=now,
            heartbeat_count=0,
            degraded_threshold=degraded_threshold or self._default_degraded,
            unhealthy_threshold=unhealthy_threshold or self._default_unhealthy,
            dead_threshold=dead_threshold or self._default_dead,
            metadata=metadata or {},
            registered_at=now,
            custom_checks={},
            history=[(now, "healthy")],
        )
        self._stats["total_registered"] += 1
        return True

    def unregister(self, agent_name: str) -> bool:
        """Remove agent from monitoring."""
        if agent_name not in self._agents:
            return False
        del self._agents[agent_name]
        self._stats["total_unregistered"] += 1
        return True

    # ------------------------------------------------------------------
    # Heartbeats
    # ------------------------------------------------------------------

    def heartbeat(self, agent_name: str, metadata: Optional[Dict] = None) -> bool:
        """Record a heartbeat from an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        now = time.time()
        agent.last_heartbeat = now
        agent.heartbeat_count += 1
        if metadata:
            agent.metadata.update(metadata)
        self._stats["total_heartbeats"] += 1

        # Re-evaluate status
        old_status = agent.status
        agent.status = "healthy"
        if old_status != "healthy":
            self._record_change(agent, old_status, "healthy")

        return True

    # ------------------------------------------------------------------
    # Custom health checks
    # ------------------------------------------------------------------

    def report_check(self, agent_name: str, check_name: str, passed: bool) -> bool:
        """Report a custom health check result."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False
        agent.custom_checks[check_name] = passed
        return True

    def clear_check(self, agent_name: str, check_name: str) -> bool:
        """Remove a custom check."""
        agent = self._agents.get(agent_name)
        if not agent or check_name not in agent.custom_checks:
            return False
        del agent.custom_checks[check_name]
        return True

    # ------------------------------------------------------------------
    # Status evaluation
    # ------------------------------------------------------------------

    def evaluate(self, agent_name: Optional[str] = None) -> List[Dict]:
        """Evaluate health of one or all agents. Returns status changes."""
        changes = []
        agents = [self._agents[agent_name]] if agent_name and agent_name in self._agents else list(self._agents.values())

        now = time.time()
        for agent in agents:
            elapsed = now - agent.last_heartbeat
            old_status = agent.status

            # Determine new status from heartbeat timing
            if elapsed >= agent.dead_threshold:
                new_status = "dead"
            elif elapsed >= agent.unhealthy_threshold:
                new_status = "unhealthy"
            elif elapsed >= agent.degraded_threshold:
                new_status = "degraded"
            else:
                new_status = "healthy"

            # Custom checks can degrade status
            if agent.custom_checks:
                failed = sum(1 for v in agent.custom_checks.values() if not v)
                if failed > 0 and HEALTH_RANK.get(new_status, 0) < HEALTH_RANK["degraded"]:
                    new_status = "degraded"

            if new_status != old_status:
                agent.status = new_status
                change = self._record_change(agent, old_status, new_status)
                changes.append(change)

        return changes

    def get_status(self, agent_name: str) -> Optional[str]:
        """Get current health status of an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return None
        return agent.status

    def get_agent(self, agent_name: str) -> Optional[Dict]:
        """Get full agent health info."""
        agent = self._agents.get(agent_name)
        if not agent:
            return None
        return self._agent_to_dict(agent)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_status_change(self, name: str, callback: Callable) -> bool:
        """Register a callback for status changes."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def list_callbacks(self) -> List[str]:
        """List registered callback names."""
        return list(self._callbacks.keys())

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list_agents(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List monitored agents with optional status filter."""
        results = []
        for agent in self._agents.values():
            if status and agent.status != status:
                continue
            results.append(self._agent_to_dict(agent))
            if len(results) >= limit:
                break
        return results

    def get_unhealthy(self) -> List[Dict]:
        """Get all agents that aren't healthy."""
        return [
            self._agent_to_dict(a) for a in self._agents.values()
            if a.status != "healthy"
        ]

    def get_history(self, agent_name: str, limit: int = 50) -> List[Dict]:
        """Get status change history for an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return []
        entries = agent.history[-limit:]
        return [{"timestamp": ts, "status": s} for ts, s in entries]

    def get_alerts(self, agent_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get health alerts."""
        alerts = self._alerts
        if agent_name:
            alerts = [a for a in alerts if a.agent_name == agent_name]
        alerts = alerts[-limit:]
        return [
            {
                "alert_id": a.alert_id,
                "agent_name": a.agent_name,
                "old_status": a.old_status,
                "new_status": a.new_status,
                "timestamp": a.timestamp,
            }
            for a in alerts
        ]

    def get_summary(self) -> Dict[str, int]:
        """Get counts by health status."""
        counts: Dict[str, int] = defaultdict(int)
        for agent in self._agents.values():
            counts[agent.status] += 1
        return dict(counts)

    # ------------------------------------------------------------------
    # Thresholds
    # ------------------------------------------------------------------

    def set_thresholds(
        self,
        agent_name: str,
        degraded: Optional[float] = None,
        unhealthy: Optional[float] = None,
        dead: Optional[float] = None,
    ) -> bool:
        """Update thresholds for an agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False
        if degraded is not None:
            agent.degraded_threshold = degraded
        if unhealthy is not None:
            agent.unhealthy_threshold = unhealthy
        if dead is not None:
            agent.dead_threshold = dead
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_change(self, agent: AgentHealth, old_status: str, new_status: str) -> Dict:
        """Record a status change and fire callbacks."""
        now = time.time()
        agent.history.append((now, new_status))
        if len(agent.history) > agent.max_history:
            agent.history = agent.history[-agent.max_history:]

        self._stats["total_status_changes"] += 1

        alert = HealthAlert(
            alert_id=f"ha-{uuid.uuid4().hex[:8]}",
            agent_name=agent.agent_name,
            old_status=old_status,
            new_status=new_status,
            timestamp=now,
        )
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]
        self._stats["total_alerts"] += 1

        change_info = {
            "agent_name": agent.agent_name,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": now,
        }

        # Fire callbacks
        for cb in self._callbacks.values():
            try:
                cb(agent.agent_name, old_status, new_status)
            except Exception:
                pass

        return change_info

    def _agent_to_dict(self, agent: AgentHealth) -> Dict:
        now = time.time()
        return {
            "agent_name": agent.agent_name,
            "status": agent.status,
            "last_heartbeat": agent.last_heartbeat,
            "seconds_since_heartbeat": round(now - agent.last_heartbeat, 2),
            "heartbeat_count": agent.heartbeat_count,
            "degraded_threshold": agent.degraded_threshold,
            "unhealthy_threshold": agent.unhealthy_threshold,
            "dead_threshold": agent.dead_threshold,
            "custom_checks": dict(agent.custom_checks),
            "failed_checks": sum(1 for v in agent.custom_checks.values() if not v),
            "metadata": agent.metadata,
            "registered_at": agent.registered_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_agents": len(self._agents),
            "total_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._alerts.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
