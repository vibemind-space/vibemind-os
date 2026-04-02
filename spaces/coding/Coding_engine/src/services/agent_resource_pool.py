"""Agent Resource Pool – manages shared resource pools that agents can acquire/release.

Provides named resource pools with fixed capacity. Agents can acquire
and release resources from pools, with tracking of per-agent usage,
availability metrics, and change callbacks.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _PoolEntry:
    """Internal pool record."""

    pool_id: str = ""
    pool_name: str = ""
    resource_type: str = "generic"
    capacity: int = 10
    allocations: Dict[str, int] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class AgentResourcePool:
    """Manages shared resource pools that agents can acquire/release."""

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _PoolEntry] = {}  # pool_name -> entry
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max_entries

        # stats
        self._total_created = 0
        self._total_removed = 0
        self._total_acquires = 0
        self._total_releases = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"arp-{digest}"

    # ------------------------------------------------------------------
    # Pool lifecycle
    # ------------------------------------------------------------------

    def create_pool(
        self,
        pool_name: str,
        capacity: int = 10,
        resource_type: str = "generic",
    ) -> str:
        """Create a resource pool. Returns pool ID or empty string on failure."""
        if not pool_name or capacity <= 0:
            return ""
        if pool_name in self._entries:
            logger.warning("pool_already_exists", pool_name=pool_name)
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        pool_id = self._next_id(pool_name)
        self._seq += 1
        entry = _PoolEntry(
            pool_id=pool_id,
            pool_name=pool_name,
            resource_type=resource_type,
            capacity=capacity,
            allocations={},
            created_at=time.time(),
            seq=self._seq,
        )
        self._entries[pool_name] = entry
        self._total_created += 1
        logger.info("pool_created", pool_id=pool_id, pool_name=pool_name, capacity=capacity)
        self._fire("pool_created", {"pool_id": pool_id, "pool_name": pool_name})
        return pool_id

    def get_pool(self, pool_id: str) -> Optional[Dict]:
        """Return pool dict by pool_id, or None."""
        for entry in self._entries.values():
            if entry.pool_id == pool_id:
                return asdict(entry)
        return None

    def remove_pool(self, pool_name: str) -> bool:
        """Remove a pool by name. Returns True if removed."""
        entry = self._entries.pop(pool_name, None)
        if not entry:
            return False
        self._seq += 1
        self._total_removed += 1
        logger.info("pool_removed", pool_name=pool_name, pool_id=entry.pool_id)
        self._fire("pool_removed", {"pool_id": entry.pool_id, "pool_name": pool_name})
        return True

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def acquire(self, pool_name: str, agent_id: str, amount: int = 1) -> bool:
        """Acquire resources from a pool. Returns True if successful."""
        entry = self._entries.get(pool_name)
        if not entry or amount <= 0 or not agent_id:
            return False

        allocated = sum(entry.allocations.values())
        available = entry.capacity - allocated
        if amount > available:
            logger.warning(
                "acquire_failed_insufficient",
                pool_name=pool_name,
                agent_id=agent_id,
                requested=amount,
                available=available,
            )
            return False

        self._seq += 1
        entry.allocations[agent_id] = entry.allocations.get(agent_id, 0) + amount
        entry.seq = self._seq
        self._total_acquires += 1
        logger.info("resource_acquired", pool_name=pool_name, agent_id=agent_id, amount=amount)
        self._fire("acquired", {
            "pool_name": pool_name,
            "agent_id": agent_id,
            "amount": amount,
        })
        return True

    def release(self, pool_name: str, agent_id: str, amount: int = 1) -> bool:
        """Release resources back to a pool. Returns True if successful."""
        entry = self._entries.get(pool_name)
        if not entry or amount <= 0 or not agent_id:
            return False

        current = entry.allocations.get(agent_id, 0)
        if current <= 0 or amount > current:
            return False

        self._seq += 1
        remaining = current - amount
        if remaining <= 0:
            del entry.allocations[agent_id]
        else:
            entry.allocations[agent_id] = remaining

        entry.seq = self._seq
        self._total_releases += 1
        logger.info("resource_released", pool_name=pool_name, agent_id=agent_id, amount=amount)
        self._fire("released", {
            "pool_name": pool_name,
            "agent_id": agent_id,
            "amount": amount,
        })
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_available(self, pool_name: str) -> int:
        """Return available capacity, 0 if pool not found."""
        entry = self._entries.get(pool_name)
        if not entry:
            return 0
        allocated = sum(entry.allocations.values())
        return entry.capacity - allocated

    def get_usage(self, pool_name: str) -> Dict[str, int]:
        """Return per-agent usage dict, empty if pool not found."""
        entry = self._entries.get(pool_name)
        if not entry:
            return {}
        return dict(entry.allocations)

    def list_pools(self) -> List[str]:
        """Return list of pool names."""
        return list(self._entries.keys())

    def get_pool_count(self) -> int:
        """Return number of pools."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns True if registered."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            "current_pools": len(self._entries),
            "total_created": self._total_created,
            "total_removed": self._total_removed,
            "total_acquires": self._total_acquires,
            "total_releases": self._total_releases,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all pools, callbacks, and counters."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_removed = 0
        self._total_acquires = 0
        self._total_releases = 0
