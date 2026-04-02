"""
Resource Pool Manager — Manages shared resources with leasing and fairness.

Provides:
- Named resource pools with configurable capacity
- Lease-based allocation with automatic timeout release
- Fair queueing to prevent resource starvation
- Resource usage tracking and metrics
- Priority-based allocation (higher priority agents get resources first)

Resources include: file locks, API slots, GPU time, workspace directories, etc.

Usage::

    pool = ResourcePoolManager()
    pool.create_pool("api_slots", capacity=5)
    pool.create_pool("workspaces", capacity=3)

    lease = pool.acquire("api_slots", holder="backend_agent", timeout=60.0)
    if lease:
        # Use the resource
        pool.release(lease.lease_id)
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class LeaseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"
    REVOKED = "revoked"


@dataclass
class ResourceLease:
    """A lease on a resource from a pool."""
    lease_id: str
    pool_name: str
    holder: str
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 300.0  # 5 min default
    status: LeaseStatus = LeaseStatus.ACTIVE
    released_at: Optional[float] = None
    priority: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == LeaseStatus.ACTIVE and not self.is_expired

    @property
    def is_expired(self) -> bool:
        if self.status != LeaseStatus.ACTIVE:
            return False
        return time.time() > self.created_at + self.timeout_seconds

    @property
    def remaining_seconds(self) -> float:
        if not self.is_active:
            return 0.0
        return max(0.0, (self.created_at + self.timeout_seconds) - time.time())

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "lease_id": self.lease_id,
            "pool_name": self.pool_name,
            "holder": self.holder,
            "status": self.status.value,
            "age_seconds": round(self.age_seconds, 1),
            "remaining_seconds": round(self.remaining_seconds, 1),
            "timeout_seconds": self.timeout_seconds,
            "priority": self.priority,
            "metadata": self.metadata,
        }


@dataclass
class ResourcePool:
    """A pool of fungible resources."""
    name: str
    capacity: int
    description: str = ""

    # Active leases
    _leases: Dict[str, ResourceLease] = field(default_factory=dict)

    # Waiting queue (holder, priority, timestamp)
    _waiters: List[tuple] = field(default_factory=list)

    # Metrics
    total_acquisitions: int = 0
    total_releases: int = 0
    total_timeouts: int = 0
    total_revocations: int = 0
    total_denials: int = 0

    @property
    def active_count(self) -> int:
        return sum(1 for l in self._leases.values() if l.is_active)

    @property
    def available(self) -> int:
        return max(0, self.capacity - self.active_count)

    @property
    def utilization(self) -> float:
        if self.capacity == 0:
            return 0.0
        return self.active_count / self.capacity

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "capacity": self.capacity,
            "active": self.active_count,
            "available": self.available,
            "utilization": round(self.utilization * 100, 1),
            "waiters": len(self._waiters),
            "total_acquisitions": self.total_acquisitions,
            "total_releases": self.total_releases,
            "total_timeouts": self.total_timeouts,
            "total_denials": self.total_denials,
        }


class ResourcePoolManager:
    """
    Manages multiple resource pools with fair allocation.
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self._pools: Dict[str, ResourcePool] = {}
        self._leases: Dict[str, ResourceLease] = {}  # Global lease index
        self._holder_leases: Dict[str, Set[str]] = {}  # holder -> lease_ids
        self.logger = logger.bind(component="resource_pool")

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def create_pool(
        self,
        name: str,
        capacity: int,
        description: str = "",
    ) -> ResourcePool:
        """Create a new resource pool."""
        pool = ResourcePool(name=name, capacity=capacity, description=description)
        self._pools[name] = pool
        self.logger.info("pool_created", pool=name, capacity=capacity)
        return pool

    def get_pool(self, name: str) -> Optional[ResourcePool]:
        """Get a pool by name."""
        return self._pools.get(name)

    def resize_pool(self, name: str, new_capacity: int) -> bool:
        """Resize a pool's capacity."""
        pool = self._pools.get(name)
        if not pool:
            return False
        old = pool.capacity
        pool.capacity = new_capacity
        self.logger.info("pool_resized", pool=name, old_capacity=old, new_capacity=new_capacity)
        return True

    # ------------------------------------------------------------------
    # Acquire & Release
    # ------------------------------------------------------------------

    def acquire(
        self,
        pool_name: str,
        holder: str,
        timeout_seconds: float = 300.0,
        priority: int = 5,
        metadata: Optional[dict] = None,
    ) -> Optional[ResourceLease]:
        """
        Acquire a resource from a pool.

        Returns a lease if successful, None if pool is full.
        """
        pool = self._pools.get(pool_name)
        if not pool:
            self.logger.warning("pool_not_found", pool=pool_name)
            return None

        # Clean expired leases first
        self._cleanup_expired(pool)

        if pool.available <= 0:
            pool.total_denials += 1
            self.logger.debug(
                "resource_denied",
                pool=pool_name,
                holder=holder,
                active=pool.active_count,
                capacity=pool.capacity,
            )
            return None

        # Create lease
        lease = ResourceLease(
            lease_id=f"lease-{uuid.uuid4().hex[:8]}",
            pool_name=pool_name,
            holder=holder,
            timeout_seconds=timeout_seconds,
            priority=priority,
            metadata=metadata or {},
        )

        pool._leases[lease.lease_id] = lease
        self._leases[lease.lease_id] = lease
        pool.total_acquisitions += 1

        # Track holder's leases
        if holder not in self._holder_leases:
            self._holder_leases[holder] = set()
        self._holder_leases[holder].add(lease.lease_id)

        self.logger.info(
            "resource_acquired",
            pool=pool_name,
            holder=holder,
            lease_id=lease.lease_id,
            remaining=pool.available,
        )
        return lease

    def release(self, lease_id: str) -> bool:
        """Release a leased resource."""
        lease = self._leases.get(lease_id)
        if not lease or not lease.is_active:
            return False

        lease.status = LeaseStatus.RELEASED
        lease.released_at = time.time()

        pool = self._pools.get(lease.pool_name)
        if pool:
            pool.total_releases += 1

        # Remove from holder tracking
        holder_leases = self._holder_leases.get(lease.holder, set())
        holder_leases.discard(lease_id)

        self.logger.info(
            "resource_released",
            pool=lease.pool_name,
            holder=lease.holder,
            lease_id=lease_id,
            held_seconds=round(lease.age_seconds, 1),
        )

        # Process waiters
        if pool:
            self._process_waiters(pool)

        return True

    def release_all(self, holder: str) -> int:
        """Release all resources held by a holder."""
        lease_ids = list(self._holder_leases.get(holder, set()))
        released = 0
        for lid in lease_ids:
            if self.release(lid):
                released += 1
        return released

    def revoke(self, lease_id: str, reason: str = "") -> bool:
        """Forcefully revoke a lease (e.g., for rebalancing)."""
        lease = self._leases.get(lease_id)
        if not lease or not lease.is_active:
            return False

        lease.status = LeaseStatus.REVOKED
        lease.released_at = time.time()

        pool = self._pools.get(lease.pool_name)
        if pool:
            pool.total_revocations += 1

        holder_leases = self._holder_leases.get(lease.holder, set())
        holder_leases.discard(lease_id)

        self.logger.warning(
            "resource_revoked",
            pool=lease.pool_name,
            holder=lease.holder,
            lease_id=lease_id,
            reason=reason,
        )
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_lease(self, lease_id: str) -> Optional[dict]:
        """Get lease details."""
        lease = self._leases.get(lease_id)
        return lease.to_dict() if lease else None

    def get_holder_resources(self, holder: str) -> List[dict]:
        """Get all active resources held by a holder."""
        lease_ids = self._holder_leases.get(holder, set())
        return [
            self._leases[lid].to_dict()
            for lid in lease_ids
            if lid in self._leases and self._leases[lid].is_active
        ]

    def get_pool_leases(self, pool_name: str) -> List[dict]:
        """Get all active leases in a pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return []
        return [
            l.to_dict() for l in pool._leases.values() if l.is_active
        ]

    def get_pool_holders(self, pool_name: str) -> List[str]:
        """Get all current holders in a pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return []
        return list(set(
            l.holder for l in pool._leases.values() if l.is_active
        ))

    # ------------------------------------------------------------------
    # Waiters (simple fair queue)
    # ------------------------------------------------------------------

    def wait_for(
        self,
        pool_name: str,
        holder: str,
        priority: int = 5,
    ) -> bool:
        """Add holder to wait queue for a pool. Returns True if added."""
        pool = self._pools.get(pool_name)
        if not pool:
            return False

        # Don't add duplicates
        for waiter in pool._waiters:
            if waiter[0] == holder:
                return False

        pool._waiters.append((holder, priority, time.time()))
        # Sort by priority (lower = higher priority), then by time
        pool._waiters.sort(key=lambda w: (w[1], w[2]))
        return True

    def _process_waiters(self, pool: ResourcePool):
        """Try to satisfy waiting requests when resources free up."""
        while pool.available > 0 and pool._waiters:
            holder, priority, _ = pool._waiters.pop(0)
            lease = self.acquire(
                pool.name, holder,
                priority=priority,
            )
            if lease:
                self.logger.info(
                    "waiter_satisfied",
                    pool=pool.name,
                    holder=holder,
                )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def _cleanup_expired(self, pool: ResourcePool):
        """Clean up expired leases in a pool."""
        expired = [
            lid for lid, lease in pool._leases.items()
            if lease.status == LeaseStatus.ACTIVE and lease.is_expired
        ]
        for lid in expired:
            lease = pool._leases[lid]
            lease.status = LeaseStatus.EXPIRED
            lease.released_at = time.time()
            pool.total_timeouts += 1

            holder_leases = self._holder_leases.get(lease.holder, set())
            holder_leases.discard(lid)

            self.logger.warning(
                "lease_expired",
                pool=pool.name,
                holder=lease.holder,
                lease_id=lid,
                age=round(lease.age_seconds, 1),
            )

    def cleanup_all_expired(self) -> int:
        """Clean up expired leases across all pools."""
        total = 0
        for pool in self._pools.values():
            before = pool.total_timeouts
            self._cleanup_expired(pool)
            total += pool.total_timeouts - before
        return total

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get overall resource pool stats."""
        pools_info = {}
        for name, pool in self._pools.items():
            self._cleanup_expired(pool)
            pools_info[name] = pool.to_dict()

        total_active = sum(p.active_count for p in self._pools.values())
        total_capacity = sum(p.capacity for p in self._pools.values())

        return {
            "total_pools": len(self._pools),
            "total_capacity": total_capacity,
            "total_active_leases": total_active,
            "overall_utilization": round(
                (total_active / total_capacity * 100) if total_capacity > 0 else 0, 1
            ),
            "total_holders": len(self._holder_leases),
            "pools": pools_info,
        }

    def get_pool_stats(self, pool_name: str) -> Optional[dict]:
        """Get stats for a specific pool."""
        pool = self._pools.get(pool_name)
        if not pool:
            return None
        self._cleanup_expired(pool)
        return pool.to_dict()

    def reset(self):
        """Clear all pools and leases."""
        self._pools.clear()
        self._leases.clear()
        self._holder_leases.clear()
