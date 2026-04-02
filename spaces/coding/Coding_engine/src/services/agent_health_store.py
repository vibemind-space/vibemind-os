"""Agent health store.

Tracks and reports agent health status including heartbeats,
health checks, and degradation detection. Provides system-wide
health aggregation and per-agent health queries.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Valid health statuses
# ---------------------------------------------------------------------------

VALID_STATUSES = ("healthy", "degraded", "unhealthy", "unknown")


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _AgentRecord:
    """Internal health record for a single agent."""
    agent_id: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "unknown"
    last_heartbeat: float = 0.0
    heartbeat_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0


# ---------------------------------------------------------------------------
# Agent Health Store
# ---------------------------------------------------------------------------

class AgentHealthStore:
    """Tracks and reports agent health status."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._agents: Dict[str, _AgentRecord] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_removed": 0,
            "total_heartbeats": 0,
            "total_health_reports": 0,
            "total_lookups": 0,
            "total_callbacks_fired": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'ahs-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ahs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._agents) < self._max_entries:
            return
        sorted_agents = sorted(
            self._agents.values(), key=lambda a: a.registered_at
        )
        remove_count = len(self._agents) - self._max_entries + 1
        for entry in sorted_agents[:remove_count]:
            del self._agents[entry.agent_id]
            self._stats["total_removed"] += 1
            logger.debug("agent_pruned", agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback for health changes."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
                self._stats["total_callbacks_fired"] += 1
            except Exception:
                logger.warning(
                    "callback_error", callback=cb_name, action=action
                )

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register an agent for health tracking.

        Returns the agent_id on success, or '' if agent_id is empty
        or already registered.
        """
        if not agent_id:
            return ""
        if agent_id in self._agents:
            logger.debug("duplicate_agent", agent_id=agent_id)
            return ""

        self._prune_if_needed()

        now = time.time()
        record = _AgentRecord(
            agent_id=agent_id,
            tags=list(tags) if tags else [],
            status="unknown",
            last_heartbeat=0.0,
            heartbeat_count=0,
            details={},
            registered_at=now,
        )
        self._agents[agent_id] = record
        self._stats["total_registered"] += 1

        logger.debug("agent_registered", agent_id=agent_id, tags=record.tags)
        self._fire("register", {"agent_id": agent_id, "tags": record.tags})
        return agent_id

    # ------------------------------------------------------------------
    # Heartbeats
    # ------------------------------------------------------------------

    def record_heartbeat(self, agent_id: str) -> bool:
        """Record a heartbeat for an agent. Returns False if unknown agent."""
        record = self._agents.get(agent_id)
        if not record:
            return False

        now = time.time()
        record.last_heartbeat = now
        record.heartbeat_count += 1
        self._stats["total_heartbeats"] += 1

        logger.debug(
            "heartbeat_recorded",
            agent_id=agent_id,
            count=record.heartbeat_count,
        )
        self._fire("heartbeat", {
            "agent_id": agent_id,
            "heartbeat_count": record.heartbeat_count,
            "timestamp": now,
        })
        return True

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def report_health(
        self,
        agent_id: str,
        status: str = "healthy",
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Report health status for an agent.

        Status must be one of: healthy, degraded, unhealthy, unknown.
        Returns False if agent not found or invalid status.
        """
        if status not in VALID_STATUSES:
            logger.warning("invalid_status", status=status)
            return False

        record = self._agents.get(agent_id)
        if not record:
            return False

        old_status = record.status
        record.status = status
        if details is not None:
            record.details = dict(details)
        self._stats["total_health_reports"] += 1

        logger.debug(
            "health_reported",
            agent_id=agent_id,
            old_status=old_status,
            new_status=status,
        )

        if old_status != status:
            self._fire("status_change", {
                "agent_id": agent_id,
                "old_status": old_status,
                "new_status": status,
                "details": record.details,
            })

        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_health(self, agent_id: str) -> Dict[str, Any]:
        """Get health info for a single agent.

        Returns dict with agent_id, status, last_heartbeat, details,
        heartbeat_count. Returns empty dict if agent not found.
        """
        record = self._agents.get(agent_id)
        if not record:
            self._stats["total_lookups"] += 1
            return {}

        self._stats["total_lookups"] += 1
        return self._record_to_dict(record)

    def get_unhealthy_agents(self) -> List[Dict[str, Any]]:
        """Return list of agent dicts with non-healthy status."""
        results = []
        for record in self._agents.values():
            if record.status != "healthy":
                results.append(self._record_to_dict(record))
        return results

    def get_system_health(self) -> Dict[str, Any]:
        """Get system-wide health summary.

        Returns dict with total_agents, healthy, degraded, unhealthy,
        and health_pct (percentage of healthy agents).
        """
        total = len(self._agents)
        healthy = 0
        degraded = 0
        unhealthy = 0

        for record in self._agents.values():
            if record.status == "healthy":
                healthy += 1
            elif record.status == "degraded":
                degraded += 1
            elif record.status in ("unhealthy", "unknown"):
                unhealthy += 1

        health_pct = round((healthy / total) * 100, 2) if total > 0 else 0.0

        return {
            "total_agents": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "health_pct": health_pct,
        }

    def list_agents(
        self,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all agents, optionally filtered by tag."""
        results = []
        for record in self._agents.values():
            if tag is not None and tag not in record.tags:
                continue
            results.append(self._record_to_dict(record))
        return results

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent from the store. Returns False if not found."""
        if agent_id not in self._agents:
            return False

        del self._agents[agent_id]
        self._stats["total_removed"] += 1

        logger.debug("agent_removed", agent_id=agent_id)
        self._fire("remove", {"agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_agents": len(self._agents),
            "current_callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._agents.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.debug("store_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_to_dict(self, record: _AgentRecord) -> Dict[str, Any]:
        """Convert an internal record to a plain dict."""
        return {
            "agent_id": record.agent_id,
            "status": record.status,
            "last_heartbeat": record.last_heartbeat,
            "details": dict(record.details),
            "heartbeat_count": record.heartbeat_count,
            "tags": list(record.tags),
            "registered_at": record.registered_at,
        }
