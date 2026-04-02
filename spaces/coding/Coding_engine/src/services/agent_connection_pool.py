"""Agent Connection Pool -- manages connection pools for agents.

Maintains per-agent connection pools with configurable maximum connections.
Tracks available and in-use connection counts, supports acquire/release
semantics, and fires change callbacks on pool mutations.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _PoolEntry:
    """Internal state for a single agent's connection pool."""

    pool_id: str
    agent_id: str
    max_connections: int
    in_use: int
    created_at: float = field(default_factory=time.time)
    total_acquires: int = 0
    total_releases: int = 0
    seq: int = 0


# ---------------------------------------------------------------------------
# AgentConnectionPool
# ---------------------------------------------------------------------------

class AgentConnectionPool:
    """Manages connection pools for agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._pools: Dict[str, _PoolEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        # cumulative stats
        self._total_pools_created: int = 0
        self._total_acquires: int = 0
        self._total_releases: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"acp-{digest}"

    # ------------------------------------------------------------------
    # Pool creation
    # ------------------------------------------------------------------

    def create_pool(self, agent_id: str, max_connections: int = 10) -> str:
        """Create a connection pool for an agent.

        Returns the pool ID (``acp-...``), or empty string on failure.
        """
        if not agent_id or max_connections <= 0:
            logger.warning(
                "create_pool.invalid_input",
                agent_id=agent_id,
                max_connections=max_connections,
            )
            return ""
        if agent_id in self._pools:
            logger.debug("create_pool.already_exists", agent_id=agent_id)
            return ""
        if len(self._pools) >= self._max_entries:
            logger.warning("create_pool.capacity_reached", max_entries=self._max_entries)
            return ""

        pool_id = self._make_id(agent_id)
        now = time.time()
        entry = _PoolEntry(
            pool_id=pool_id,
            agent_id=agent_id,
            max_connections=max_connections,
            in_use=0,
            created_at=now,
            seq=self._seq,
        )
        self._pools[agent_id] = entry
        self._total_pools_created += 1
        logger.info(
            "create_pool.ok",
            agent_id=agent_id,
            pool_id=pool_id,
            max_connections=max_connections,
        )
        self._fire("pool_created", {"pool_id": pool_id, "agent_id": agent_id})
        return pool_id

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def acquire(self, agent_id: str) -> bool:
        """Acquire a connection from the agent's pool.

        Returns True if a connection was available and acquired, False otherwise.
        """
        entry = self._pools.get(agent_id)
        if not entry:
            logger.debug("acquire.unknown_agent", agent_id=agent_id)
            return False

        if entry.in_use >= entry.max_connections:
            logger.debug(
                "acquire.pool_exhausted",
                agent_id=agent_id,
                in_use=entry.in_use,
                max_connections=entry.max_connections,
            )
            return False

        entry.in_use += 1
        entry.total_acquires += 1
        self._total_acquires += 1
        logger.info("acquire.ok", agent_id=agent_id, in_use=entry.in_use)
        self._fire("connection_acquired", {"agent_id": agent_id, "pool_id": entry.pool_id})
        return True

    def release(self, agent_id: str) -> bool:
        """Release a connection back to the agent's pool.

        Returns True if a connection was released, False otherwise.
        """
        entry = self._pools.get(agent_id)
        if not entry:
            logger.debug("release.unknown_agent", agent_id=agent_id)
            return False

        if entry.in_use <= 0:
            logger.debug("release.no_connections_in_use", agent_id=agent_id)
            return False

        entry.in_use -= 1
        entry.total_releases += 1
        self._total_releases += 1
        logger.info("release.ok", agent_id=agent_id, in_use=entry.in_use)
        self._fire("connection_released", {"agent_id": agent_id, "pool_id": entry.pool_id})
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_available(self, agent_id: str) -> int:
        """Return the number of available connections for the agent."""
        entry = self._pools.get(agent_id)
        if not entry:
            return 0
        return entry.max_connections - entry.in_use

    def get_in_use(self, agent_id: str) -> int:
        """Return the number of in-use connections for the agent."""
        entry = self._pools.get(agent_id)
        if not entry:
            return 0
        return entry.in_use

    def get_pool_info(self, agent_id: str) -> Optional[dict]:
        """Return pool details as a dict, or None if not found."""
        entry = self._pools.get(agent_id)
        if not entry:
            return None
        return {
            "pool_id": entry.pool_id,
            "agent_id": entry.agent_id,
            "max_connections": entry.max_connections,
            "in_use": entry.in_use,
            "available": entry.max_connections - entry.in_use,
            "total_acquires": entry.total_acquires,
            "total_releases": entry.total_releases,
            "created_at": entry.created_at,
        }

    def get_pool_count(self) -> int:
        """Return the number of registered pools."""
        return len(self._pools)

    def list_agents(self) -> list:
        """Return all agent IDs that have a connection pool."""
        return list(self._pools.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback."""
        self._callbacks[name] = callback
        logger.debug("on_change.registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback by name."""
        removed = self._callbacks.pop(name, None) is not None
        if removed:
            logger.debug("remove_callback.ok", name=name)
        return removed

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given event and data."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("_fire.callback_error", callback=cb_name, event=event)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics as a dict."""
        total_available = sum(
            e.max_connections - e.in_use for e in self._pools.values()
        )
        total_in_use = sum(e.in_use for e in self._pools.values())
        return {
            "pool_count": len(self._pools),
            "total_available": total_available,
            "total_in_use": total_in_use,
            "total_pools_created": self._total_pools_created,
            "total_acquires": self._total_acquires,
            "total_releases": self._total_releases,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._pools.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_pools_created = 0
        self._total_acquires = 0
        self._total_releases = 0
        logger.info("reset.ok")
