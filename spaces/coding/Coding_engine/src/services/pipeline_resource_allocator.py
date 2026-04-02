"""Pipeline resource allocator — manages resource budgets for pipeline stages."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResourcePool:
    """A pool of a specific resource type."""
    name: str
    capacity: float
    allocated: float = 0.0
    reserved: float = 0.0
    unit: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Allocation:
    """An active resource allocation."""
    allocation_id: str
    pool_name: str
    holder: str
    amount: float
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Reservation:
    """A pending resource reservation."""
    reservation_id: str
    pool_name: str
    holder: str
    amount: float
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineResourceAllocator:
    """Manages resource pools with allocation, release, and reservation."""

    def __init__(self, max_pools: int = 500, max_allocations: int = 10000):
        self._pools: Dict[str, ResourcePool] = {}
        self._allocations: Dict[str, Allocation] = {}
        self._reservations: Dict[str, Reservation] = {}
        self._max_pools = max_pools
        self._max_allocations = max_allocations
        self._callbacks: Dict[str, Any] = {}

        # Stats
        self._total_pools_created = 0
        self._total_allocations = 0
        self._total_releases = 0
        self._total_reservations = 0
        self._total_denied = 0

    # ── Pool Management ──

    def create_pool(self, name: str, capacity: float, unit: str = "",
                    metadata: Optional[Dict] = None) -> bool:
        """Create a resource pool."""
        if name in self._pools:
            return False
        if capacity <= 0:
            return False
        if len(self._pools) >= self._max_pools:
            return False

        self._pools[name] = ResourcePool(
            name=name,
            capacity=capacity,
            unit=unit,
            metadata=metadata or {},
        )
        self._total_pools_created += 1
        return True

    def remove_pool(self, name: str) -> bool:
        """Remove a pool (must have no active allocations)."""
        pool = self._pools.get(name)
        if pool is None:
            return False
        if pool.allocated > 0 or pool.reserved > 0:
            return False
        del self._pools[name]
        return True

    def get_pool(self, name: str) -> Optional[Dict]:
        """Get pool info."""
        pool = self._pools.get(name)
        if pool is None:
            return None
        self._expire_reservations(name)
        return {
            "name": pool.name,
            "capacity": pool.capacity,
            "allocated": pool.allocated,
            "reserved": pool.reserved,
            "available": pool.capacity - pool.allocated - pool.reserved,
            "utilization": round(pool.allocated / pool.capacity * 100, 1) if pool.capacity > 0 else 0.0,
            "unit": pool.unit,
            "metadata": dict(pool.metadata),
            "created_at": pool.created_at,
        }

    def resize_pool(self, name: str, new_capacity: float) -> bool:
        """Resize a pool capacity (can't go below current usage)."""
        pool = self._pools.get(name)
        if pool is None:
            return False
        if new_capacity <= 0:
            return False
        if new_capacity < pool.allocated + pool.reserved:
            return False
        pool.capacity = new_capacity
        return True

    def list_pools(self, min_utilization: float = 0.0) -> List[Dict]:
        """List all pools, optionally filtered by minimum utilization."""
        result = []
        for name in self._pools:
            info = self.get_pool(name)
            if info and info["utilization"] >= min_utilization:
                result.append(info)
        return result

    # ── Allocation ──

    def allocate(self, pool_name: str, holder: str, amount: float,
                 metadata: Optional[Dict] = None) -> str:
        """Allocate resources from a pool. Returns allocation_id or empty string."""
        pool = self._pools.get(pool_name)
        if pool is None:
            self._total_denied += 1
            return ""
        if amount <= 0:
            return ""

        self._expire_reservations(pool_name)
        available = pool.capacity - pool.allocated - pool.reserved
        if amount > available:
            self._total_denied += 1
            return ""

        if len(self._allocations) >= self._max_allocations:
            self._total_denied += 1
            return ""

        alloc_id = f"alloc-{uuid.uuid4().hex[:8]}"
        self._allocations[alloc_id] = Allocation(
            allocation_id=alloc_id,
            pool_name=pool_name,
            holder=holder,
            amount=amount,
            metadata=metadata or {},
        )
        pool.allocated += amount
        self._total_allocations += 1
        self._fire_callbacks("allocate", pool_name, holder, amount)
        return alloc_id

    def release(self, allocation_id: str) -> bool:
        """Release an allocation."""
        alloc = self._allocations.get(allocation_id)
        if alloc is None:
            return False

        pool = self._pools.get(alloc.pool_name)
        if pool:
            pool.allocated = max(0.0, pool.allocated - alloc.amount)

        del self._allocations[allocation_id]
        self._total_releases += 1
        if pool:
            self._fire_callbacks("release", alloc.pool_name, alloc.holder, alloc.amount)
        return True

    def get_allocation(self, allocation_id: str) -> Optional[Dict]:
        """Get allocation info."""
        alloc = self._allocations.get(allocation_id)
        if alloc is None:
            return None
        return {
            "allocation_id": alloc.allocation_id,
            "pool_name": alloc.pool_name,
            "holder": alloc.holder,
            "amount": alloc.amount,
            "created_at": alloc.created_at,
            "metadata": dict(alloc.metadata),
        }

    def get_holder_allocations(self, holder: str) -> List[Dict]:
        """Get all allocations for a holder."""
        result = []
        for alloc in self._allocations.values():
            if alloc.holder == holder:
                result.append({
                    "allocation_id": alloc.allocation_id,
                    "pool_name": alloc.pool_name,
                    "amount": alloc.amount,
                    "created_at": alloc.created_at,
                })
        return result

    def release_holder(self, holder: str) -> int:
        """Release all allocations for a holder."""
        to_release = [a.allocation_id for a in self._allocations.values()
                      if a.holder == holder]
        count = 0
        for alloc_id in to_release:
            if self.release(alloc_id):
                count += 1
        return count

    def list_allocations(self, pool_name: str = "", holder: str = "",
                         limit: int = 50) -> List[Dict]:
        """List allocations with optional filters."""
        result = []
        for alloc in self._allocations.values():
            if pool_name and alloc.pool_name != pool_name:
                continue
            if holder and alloc.holder != holder:
                continue
            result.append(self.get_allocation(alloc.allocation_id))
            if len(result) >= limit:
                break
        return [r for r in result if r is not None]

    # ── Reservation ──

    def reserve(self, pool_name: str, holder: str, amount: float,
                timeout_seconds: float = 60.0,
                metadata: Optional[Dict] = None) -> str:
        """Reserve resources (held but not allocated). Returns reservation_id."""
        pool = self._pools.get(pool_name)
        if pool is None:
            return ""
        if amount <= 0 or timeout_seconds <= 0:
            return ""

        self._expire_reservations(pool_name)
        available = pool.capacity - pool.allocated - pool.reserved
        if amount > available:
            return ""

        res_id = f"res-{uuid.uuid4().hex[:8]}"
        self._reservations[res_id] = Reservation(
            reservation_id=res_id,
            pool_name=pool_name,
            holder=holder,
            amount=amount,
            expires_at=time.time() + timeout_seconds,
            metadata=metadata or {},
        )
        pool.reserved += amount
        self._total_reservations += 1
        return res_id

    def claim_reservation(self, reservation_id: str) -> str:
        """Convert a reservation to an allocation. Returns allocation_id."""
        res = self._reservations.get(reservation_id)
        if res is None:
            return ""
        if time.time() > res.expires_at:
            self._cancel_reservation_internal(reservation_id)
            return ""

        pool = self._pools.get(res.pool_name)
        if pool is None:
            return ""

        # Move from reserved to allocated
        pool.reserved = max(0.0, pool.reserved - res.amount)

        alloc_id = f"alloc-{uuid.uuid4().hex[:8]}"
        self._allocations[alloc_id] = Allocation(
            allocation_id=alloc_id,
            pool_name=res.pool_name,
            holder=res.holder,
            amount=res.amount,
            metadata=dict(res.metadata),
        )
        pool.allocated += res.amount
        self._total_allocations += 1

        del self._reservations[reservation_id]
        return alloc_id

    def cancel_reservation(self, reservation_id: str) -> bool:
        """Cancel a reservation."""
        return self._cancel_reservation_internal(reservation_id)

    def _cancel_reservation_internal(self, reservation_id: str) -> bool:
        res = self._reservations.get(reservation_id)
        if res is None:
            return False
        pool = self._pools.get(res.pool_name)
        if pool:
            pool.reserved = max(0.0, pool.reserved - res.amount)
        del self._reservations[reservation_id]
        return True

    def get_reservation(self, reservation_id: str) -> Optional[Dict]:
        """Get reservation info."""
        res = self._reservations.get(reservation_id)
        if res is None:
            return None
        expired = time.time() > res.expires_at
        return {
            "reservation_id": res.reservation_id,
            "pool_name": res.pool_name,
            "holder": res.holder,
            "amount": res.amount,
            "expires_at": res.expires_at,
            "expired": expired,
            "created_at": res.created_at,
        }

    def list_reservations(self, pool_name: str = "", limit: int = 50) -> List[Dict]:
        """List active reservations."""
        result = []
        for res_id, res in list(self._reservations.items()):
            if time.time() > res.expires_at:
                self._cancel_reservation_internal(res_id)
                continue
            if pool_name and res.pool_name != pool_name:
                continue
            info = self.get_reservation(res_id)
            if info:
                result.append(info)
            if len(result) >= limit:
                break
        return result

    def _expire_reservations(self, pool_name: str) -> None:
        """Remove expired reservations for a pool."""
        now = time.time()
        to_remove = [rid for rid, r in self._reservations.items()
                     if r.pool_name == pool_name and now > r.expires_at]
        for rid in to_remove:
            self._cancel_reservation_internal(rid)

    # ── Queries ──

    def can_allocate(self, pool_name: str, amount: float) -> bool:
        """Check if allocation is possible without doing it."""
        pool = self._pools.get(pool_name)
        if pool is None:
            return False
        self._expire_reservations(pool_name)
        available = pool.capacity - pool.allocated - pool.reserved
        return amount <= available and amount > 0

    def get_available(self, pool_name: str) -> float:
        """Get available capacity in a pool."""
        pool = self._pools.get(pool_name)
        if pool is None:
            return 0.0
        self._expire_reservations(pool_name)
        return pool.capacity - pool.allocated - pool.reserved

    def get_utilization(self, pool_name: str) -> float:
        """Get utilization percentage of a pool."""
        pool = self._pools.get(pool_name)
        if pool is None:
            return 0.0
        if pool.capacity <= 0:
            return 0.0
        return round(pool.allocated / pool.capacity * 100, 1)

    def get_summary(self) -> Dict[str, Dict]:
        """Get summary of all pools."""
        summary = {}
        for name in self._pools:
            info = self.get_pool(name)
            if info:
                summary[name] = {
                    "capacity": info["capacity"],
                    "allocated": info["allocated"],
                    "available": info["available"],
                    "utilization": info["utilization"],
                }
        return summary

    # ── Callbacks ──

    def on_change(self, name: str, callback) -> bool:
        """Register a callback for allocation changes."""
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

    def _fire_callbacks(self, action: str, pool_name: str, holder: str, amount: float) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, pool_name, holder, amount)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        """Get allocator statistics."""
        return {
            "total_pools": len(self._pools),
            "total_pools_created": self._total_pools_created,
            "total_active_allocations": len(self._allocations),
            "total_active_reservations": len(self._reservations),
            "total_allocations": self._total_allocations,
            "total_releases": self._total_releases,
            "total_reservations": self._total_reservations,
            "total_denied": self._total_denied,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._pools.clear()
        self._allocations.clear()
        self._reservations.clear()
        self._callbacks.clear()
        self._total_pools_created = 0
        self._total_allocations = 0
        self._total_releases = 0
        self._total_reservations = 0
        self._total_denied = 0
