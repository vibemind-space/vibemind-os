"""Agent Lease Manager – manages time-limited leases for shared resources.

Agents acquire leases on resources with configurable duration and renewal.
Prevents concurrent access to shared resources and automatically expires
stale leases.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Lease:
    lease_id: str
    resource: str
    holder: str
    duration: float  # seconds
    acquired_at: float
    expires_at: float
    renewed_count: int
    tags: List[str]


@dataclass
class _LeaseEvent:
    event_id: str
    resource: str
    holder: str
    action: str  # acquired, renewed, released, expired
    timestamp: float


class AgentLeaseManager:
    """Manages time-limited leases for shared resources."""

    def __init__(
        self,
        max_leases: int = 50000,
        max_history: int = 100000,
        default_duration: float = 60.0,
        max_renewals: int = 100,
    ):
        self._leases: Dict[str, _Lease] = {}  # lease_id -> lease
        self._resource_index: Dict[str, str] = {}  # resource -> lease_id (active lease)
        self._history: List[_LeaseEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_leases = max_leases
        self._max_history = max_history
        self._default_duration = default_duration
        self._max_renewals = max_renewals
        self._seq = 0

        # stats
        self._total_acquired = 0
        self._total_renewed = 0
        self._total_released = 0
        self._total_expired = 0

    # ------------------------------------------------------------------
    # Acquire / Release
    # ------------------------------------------------------------------

    def acquire(
        self,
        resource: str,
        holder: str,
        duration: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not resource or not holder:
            return ""

        # Check if resource already leased (and not expired)
        existing_lid = self._resource_index.get(resource)
        if existing_lid:
            existing = self._leases.get(existing_lid)
            if existing and time.time() < existing.expires_at:
                return ""  # resource is locked
            else:
                # Expired lease — clean up
                self._expire_lease(existing_lid)

        if len(self._leases) >= self._max_leases:
            return ""

        self._seq += 1
        now = time.time()
        dur = duration if duration > 0 else self._default_duration
        raw = f"{resource}-{holder}-{now}-{self._seq}"
        lid = "lse-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        lease = _Lease(
            lease_id=lid,
            resource=resource,
            holder=holder,
            duration=dur,
            acquired_at=now,
            expires_at=now + dur,
            renewed_count=0,
            tags=tags or [],
        )
        self._leases[lid] = lease
        self._resource_index[resource] = lid
        self._total_acquired += 1
        self._record_event(resource, holder, "acquired")
        self._fire("lease_acquired", {"lease_id": lid, "resource": resource, "holder": holder})
        return lid

    def release(self, lease_id: str) -> bool:
        lease = self._leases.pop(lease_id, None)
        if not lease:
            return False
        if self._resource_index.get(lease.resource) == lease_id:
            self._resource_index.pop(lease.resource, None)
        self._total_released += 1
        self._record_event(lease.resource, lease.holder, "released")
        self._fire("lease_released", {"lease_id": lease_id, "resource": lease.resource})
        return True

    def renew(self, lease_id: str, duration: float = 0.0) -> bool:
        lease = self._leases.get(lease_id)
        if not lease:
            return False
        now = time.time()
        if now >= lease.expires_at:
            self._expire_lease(lease_id)
            return False
        if lease.renewed_count >= self._max_renewals:
            return False

        dur = duration if duration > 0 else lease.duration
        lease.expires_at = now + dur
        lease.renewed_count += 1
        self._total_renewed += 1
        self._record_event(lease.resource, lease.holder, "renewed")
        self._fire("lease_renewed", {"lease_id": lease_id, "resource": lease.resource})
        return True

    def _expire_lease(self, lease_id: str) -> None:
        lease = self._leases.pop(lease_id, None)
        if not lease:
            return
        if self._resource_index.get(lease.resource) == lease_id:
            self._resource_index.pop(lease.resource, None)
        self._total_expired += 1
        self._record_event(lease.resource, lease.holder, "expired")
        self._fire("lease_expired", {"lease_id": lease_id, "resource": lease.resource})

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_lease(self, lease_id: str) -> Optional[Dict[str, Any]]:
        lease = self._leases.get(lease_id)
        if not lease:
            return None
        now = time.time()
        return {
            "lease_id": lease.lease_id,
            "resource": lease.resource,
            "holder": lease.holder,
            "duration": lease.duration,
            "acquired_at": lease.acquired_at,
            "expires_at": lease.expires_at,
            "remaining": max(0.0, lease.expires_at - now),
            "renewed_count": lease.renewed_count,
            "tags": list(lease.tags),
        }

    def get_resource_lease(self, resource: str) -> Optional[Dict[str, Any]]:
        lid = self._resource_index.get(resource)
        if not lid:
            return None
        lease = self._leases.get(lid)
        if not lease:
            return None
        now = time.time()
        if now >= lease.expires_at:
            self._expire_lease(lid)
            return None
        return self.get_lease(lid)

    def is_locked(self, resource: str) -> bool:
        lid = self._resource_index.get(resource)
        if not lid:
            return False
        lease = self._leases.get(lid)
        if not lease:
            return False
        if time.time() >= lease.expires_at:
            self._expire_lease(lid)
            return False
        return True

    def get_holder_leases(self, holder: str) -> List[Dict[str, Any]]:
        results = []
        now = time.time()
        for lease in list(self._leases.values()):
            if lease.holder == holder:
                if now >= lease.expires_at:
                    self._expire_lease(lease.lease_id)
                else:
                    results.append(self.get_lease(lease.lease_id))
        return [r for r in results if r is not None]

    def list_leases(self, holder: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        now = time.time()
        for lease in list(self._leases.values()):
            if now >= lease.expires_at:
                self._expire_lease(lease.lease_id)
                continue
            if holder and lease.holder != holder:
                continue
            if tag and tag not in lease.tags:
                continue
            results.append(self.get_lease(lease.lease_id))
        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> int:
        """Clean up all expired leases."""
        now = time.time()
        expired = [lid for lid, l in self._leases.items() if now >= l.expires_at]
        for lid in expired:
            self._expire_lease(lid)
        return len(expired)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        resource: str = "",
        holder: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if resource and ev.resource != resource:
                continue
            if holder and ev.holder != holder:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "resource": ev.resource,
                "holder": ev.holder,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, resource: str, holder: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{resource}-{holder}-{action}-{now}-{self._seq}"
        evid = "lev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _LeaseEvent(
            event_id=evid, resource=resource, holder=holder,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for l in self._leases.values() if now < l.expires_at)
        return {
            "current_leases": len(self._leases),
            "active_leases": active,
            "total_acquired": self._total_acquired,
            "total_renewed": self._total_renewed,
            "total_released": self._total_released,
            "total_expired": self._total_expired,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._leases.clear()
        self._resource_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_acquired = 0
        self._total_renewed = 0
        self._total_released = 0
        self._total_expired = 0
