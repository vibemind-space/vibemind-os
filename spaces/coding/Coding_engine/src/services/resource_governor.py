"""
Resource Governor — enforces resource limits and quotas across pipeline agents.

Features:
- Per-agent resource quotas (CPU, memory, tasks, API calls)
- Real-time usage tracking
- Quota enforcement with soft/hard limits
- Usage alerts and throttling
- Resource reservation system
- Usage history and reporting
- Auto-scaling recommendations
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ResourceQuota:
    """Resource quota definition."""
    resource_type: str  # "cpu", "memory", "tasks", "api_calls", custom
    soft_limit: float
    hard_limit: float
    current_usage: float = 0.0
    reserved: float = 0.0
    unit: str = ""  # "cores", "MB", "count", "per_minute"


@dataclass
class AgentQuotas:
    """All quotas for an agent."""
    agent_name: str
    quotas: Dict[str, ResourceQuota] = field(default_factory=dict)
    violations: int = 0
    throttled: bool = False
    registered_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Reservation:
    """A resource reservation."""
    reservation_id: str
    agent_name: str
    resource_type: str
    amount: float
    created_at: float
    expires_at: float
    status: str = "active"  # active, released, expired


# ---------------------------------------------------------------------------
# Resource Governor
# ---------------------------------------------------------------------------

class ResourceGovernor:
    """Enforces resource limits and quotas."""

    def __init__(self, max_reservations: int = 5000):
        self._max_reservations = max_reservations
        self._agents: Dict[str, AgentQuotas] = {}
        self._reservations: Dict[str, Reservation] = {}
        self._usage_history: List[Dict] = []
        self._max_history = 10000

        self._stats = {
            "total_checks": 0,
            "total_violations": 0,
            "total_throttles": 0,
            "total_reservations": 0,
            "total_releases": 0,
        }

    # ------------------------------------------------------------------
    # Agent quota management
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_name: str,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Register an agent for resource governance."""
        if agent_name in self._agents:
            return False
        self._agents[agent_name] = AgentQuotas(
            agent_name=agent_name,
            registered_at=time.time(),
            metadata=metadata or {},
        )
        return True

    def unregister_agent(self, agent_name: str) -> bool:
        """Unregister an agent."""
        if agent_name not in self._agents:
            return False
        # Release all reservations
        for rid, r in list(self._reservations.items()):
            if r.agent_name == agent_name and r.status == "active":
                r.status = "released"
        del self._agents[agent_name]
        return True

    def set_quota(
        self,
        agent_name: str,
        resource_type: str,
        soft_limit: float,
        hard_limit: float,
        unit: str = "",
    ) -> bool:
        """Set or update a resource quota for an agent."""
        aq = self._agents.get(agent_name)
        if not aq:
            return False
        if hard_limit < soft_limit:
            return False
        aq.quotas[resource_type] = ResourceQuota(
            resource_type=resource_type,
            soft_limit=soft_limit,
            hard_limit=hard_limit,
            unit=unit,
        )
        return True

    def remove_quota(self, agent_name: str, resource_type: str) -> bool:
        """Remove a quota."""
        aq = self._agents.get(agent_name)
        if not aq or resource_type not in aq.quotas:
            return False
        del aq.quotas[resource_type]
        return True

    def get_agent(self, agent_name: str) -> Optional[Dict]:
        """Get agent quota details."""
        aq = self._agents.get(agent_name)
        if not aq:
            return None
        return self._agent_to_dict(aq)

    def list_agents(self, throttled_only: bool = False) -> List[Dict]:
        """List all governed agents."""
        results = []
        for aq in sorted(self._agents.values(), key=lambda a: a.agent_name):
            if throttled_only and not aq.throttled:
                continue
            results.append(self._agent_to_dict(aq))
        return results

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

    def record_usage(
        self,
        agent_name: str,
        resource_type: str,
        amount: float,
    ) -> Dict:
        """Record resource usage. Returns check result."""
        aq = self._agents.get(agent_name)
        if not aq:
            return {"allowed": False, "reason": "agent_not_registered"}

        self._stats["total_checks"] += 1

        quota = aq.quotas.get(resource_type)
        if not quota:
            # No quota set = unlimited
            return {"allowed": True, "reason": "no_quota"}

        quota.current_usage += amount

        # Record history
        self._usage_history.append({
            "agent_name": agent_name,
            "resource_type": resource_type,
            "amount": amount,
            "total_usage": quota.current_usage,
            "timestamp": time.time(),
        })
        if len(self._usage_history) > self._max_history:
            self._usage_history = self._usage_history[-self._max_history:]

        # Check limits
        result = self._check_limits(aq, quota)
        return result

    def get_usage(
        self,
        agent_name: str,
        resource_type: Optional[str] = None,
    ) -> List[Dict]:
        """Get current usage for an agent."""
        aq = self._agents.get(agent_name)
        if not aq:
            return []
        results = []
        for rt, q in sorted(aq.quotas.items()):
            if resource_type and rt != resource_type:
                continue
            pct = 0.0
            if q.hard_limit > 0:
                pct = round(q.current_usage / q.hard_limit * 100, 2)
            results.append({
                "resource_type": rt,
                "current_usage": round(q.current_usage, 2),
                "reserved": round(q.reserved, 2),
                "soft_limit": q.soft_limit,
                "hard_limit": q.hard_limit,
                "usage_percent": pct,
                "unit": q.unit,
                "over_soft": q.current_usage > q.soft_limit,
                "over_hard": q.current_usage > q.hard_limit,
            })
        return results

    def reset_usage(self, agent_name: str, resource_type: Optional[str] = None) -> bool:
        """Reset usage counters for an agent."""
        aq = self._agents.get(agent_name)
        if not aq:
            return False
        for rt, q in aq.quotas.items():
            if resource_type and rt != resource_type:
                continue
            q.current_usage = 0.0
        aq.throttled = False
        return True

    # ------------------------------------------------------------------
    # Reservations
    # ------------------------------------------------------------------

    def reserve(
        self,
        agent_name: str,
        resource_type: str,
        amount: float,
        duration_seconds: float = 300.0,
    ) -> Optional[str]:
        """Reserve resources. Returns reservation_id or None."""
        aq = self._agents.get(agent_name)
        if not aq:
            return None

        quota = aq.quotas.get(resource_type)
        if not quota:
            return None

        # Check if reservation would exceed hard limit
        total = quota.current_usage + quota.reserved + amount
        if total > quota.hard_limit:
            return None

        rid = f"rsrv-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._reservations[rid] = Reservation(
            reservation_id=rid,
            agent_name=agent_name,
            resource_type=resource_type,
            amount=amount,
            created_at=now,
            expires_at=now + duration_seconds,
        )
        quota.reserved += amount
        self._stats["total_reservations"] += 1
        return rid

    def release(self, reservation_id: str) -> bool:
        """Release a reservation."""
        r = self._reservations.get(reservation_id)
        if not r or r.status != "active":
            return False

        aq = self._agents.get(r.agent_name)
        if aq and r.resource_type in aq.quotas:
            aq.quotas[r.resource_type].reserved -= r.amount
            aq.quotas[r.resource_type].reserved = max(0, aq.quotas[r.resource_type].reserved)

        r.status = "released"
        self._stats["total_releases"] += 1
        return True

    def get_reservation(self, reservation_id: str) -> Optional[Dict]:
        """Get reservation details."""
        r = self._reservations.get(reservation_id)
        if not r:
            return None
        self._check_reservation_expiry(r)
        return {
            "reservation_id": r.reservation_id,
            "agent_name": r.agent_name,
            "resource_type": r.resource_type,
            "amount": r.amount,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
            "status": r.status,
        }

    def list_reservations(
        self,
        agent_name: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict]:
        """List reservations."""
        results = []
        for r in self._reservations.values():
            self._check_reservation_expiry(r)
            if active_only and r.status != "active":
                continue
            if agent_name and r.agent_name != agent_name:
                continue
            results.append({
                "reservation_id": r.reservation_id,
                "agent_name": r.agent_name,
                "resource_type": r.resource_type,
                "amount": r.amount,
                "status": r.status,
                "expires_at": r.expires_at,
            })
        return results

    def cleanup_expired_reservations(self) -> int:
        """Clean up expired reservations. Returns count cleaned."""
        cleaned = 0
        now = time.time()
        for r in self._reservations.values():
            if r.status == "active" and now > r.expires_at:
                aq = self._agents.get(r.agent_name)
                if aq and r.resource_type in aq.quotas:
                    aq.quotas[r.resource_type].reserved -= r.amount
                    aq.quotas[r.resource_type].reserved = max(
                        0, aq.quotas[r.resource_type].reserved
                    )
                r.status = "expired"
                cleaned += 1
        return cleaned

    # ------------------------------------------------------------------
    # Throttling
    # ------------------------------------------------------------------

    def throttle(self, agent_name: str) -> bool:
        """Manually throttle an agent."""
        aq = self._agents.get(agent_name)
        if not aq:
            return False
        aq.throttled = True
        self._stats["total_throttles"] += 1
        return True

    def unthrottle(self, agent_name: str) -> bool:
        """Remove throttle from an agent."""
        aq = self._agents.get(agent_name)
        if not aq or not aq.throttled:
            return False
        aq.throttled = False
        return True

    def is_throttled(self, agent_name: str) -> bool:
        """Check if an agent is throttled."""
        aq = self._agents.get(agent_name)
        return aq.throttled if aq else False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_limits(self, aq: AgentQuotas, quota: ResourceQuota) -> Dict:
        if quota.current_usage > quota.hard_limit:
            aq.violations += 1
            aq.throttled = True
            self._stats["total_violations"] += 1
            self._stats["total_throttles"] += 1
            return {
                "allowed": False,
                "reason": "hard_limit_exceeded",
                "usage": round(quota.current_usage, 2),
                "limit": quota.hard_limit,
            }
        if quota.current_usage > quota.soft_limit:
            return {
                "allowed": True,
                "reason": "soft_limit_warning",
                "usage": round(quota.current_usage, 2),
                "limit": quota.soft_limit,
            }
        return {
            "allowed": True,
            "reason": "within_limits",
            "usage": round(quota.current_usage, 2),
        }

    def _check_reservation_expiry(self, r: Reservation) -> None:
        if r.status == "active" and time.time() > r.expires_at:
            aq = self._agents.get(r.agent_name)
            if aq and r.resource_type in aq.quotas:
                aq.quotas[r.resource_type].reserved -= r.amount
                aq.quotas[r.resource_type].reserved = max(
                    0, aq.quotas[r.resource_type].reserved
                )
            r.status = "expired"

    def _agent_to_dict(self, aq: AgentQuotas) -> Dict:
        quotas = {}
        for rt, q in sorted(aq.quotas.items()):
            quotas[rt] = {
                "soft_limit": q.soft_limit,
                "hard_limit": q.hard_limit,
                "current_usage": round(q.current_usage, 2),
                "reserved": round(q.reserved, 2),
                "unit": q.unit,
            }
        return {
            "agent_name": aq.agent_name,
            "quotas": quotas,
            "violations": aq.violations,
            "throttled": aq.throttled,
            "registered_at": aq.registered_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_agents": len(self._agents),
            "total_active_reservations": sum(
                1 for r in self._reservations.values() if r.status == "active"
            ),
            "total_throttled": sum(
                1 for a in self._agents.values() if a.throttled
            ),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._reservations.clear()
        self._usage_history.clear()
        self._stats = {k: 0 for k in self._stats}
