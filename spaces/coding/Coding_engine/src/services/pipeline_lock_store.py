"""Pipeline Lock Store -- manages distributed-style locks for pipeline resources.

Features:
- Acquire and release locks on named resources
- TTL-based automatic expiration
- Holder-based lock ownership tracking
- Force-release for admin overrides
- Expired-lock cleanup with batch removal
- Max-entries pruning with configurable limit
- Change callbacks for reactive integrations
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
class LockEntry:
    """Internal representation of a resource lock."""
    lock_id: str
    resource_name: str
    holder: str
    acquired_at: float
    expires_at: float
    tags: List[str]


# ---------------------------------------------------------------------------
# Pipeline Lock Store
# ---------------------------------------------------------------------------

class PipelineLockStore:
    """Manages distributed-style locks for pipeline resources with TTL-based
    expiration, holder ownership, and admin force-release."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._locks: Dict[str, LockEntry] = {}          # lock_id -> LockEntry
        self._by_resource: Dict[str, str] = {}           # resource_name -> lock_id
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_acquired = 0
        self._total_released = 0
        self._total_expired = 0
        self._total_force_released = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, resource_name: str) -> str:
        """Generate a collision-free ID with prefix pls-."""
        self._seq += 1
        raw = f"{resource_name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pls-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.warning("callback_error", callback=cb_name, action=action)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when exceeding max_entries."""
        while len(self._locks) > self._max_entries:
            oldest_id = min(
                self._locks,
                key=lambda k: self._locks[k].acquired_at,
            )
            entry = self._locks.pop(oldest_id)
            self._by_resource.pop(entry.resource_name, None)
            logger.info("lock_pruned", lock_id=oldest_id,
                        resource=entry.resource_name)

    # ------------------------------------------------------------------
    # Serialisation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: LockEntry) -> Dict[str, Any]:
        """Convert a LockEntry to a plain dict."""
        return {
            "lock_id": entry.lock_id,
            "resource_name": entry.resource_name,
            "holder": entry.holder,
            "acquired_at": entry.acquired_at,
            "expires_at": entry.expires_at,
            "tags": list(entry.tags),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, entry: LockEntry) -> bool:
        """Check whether a lock entry has expired."""
        return time.time() >= entry.expires_at

    def _remove_lock(self, entry: LockEntry) -> None:
        """Remove a lock entry from all indices."""
        self._locks.pop(entry.lock_id, None)
        self._by_resource.pop(entry.resource_name, None)

    # ------------------------------------------------------------------
    # acquire
    # ------------------------------------------------------------------

    def acquire(
        self,
        resource_name: str,
        holder: str,
        ttl: float = 60,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Acquire a lock on a resource.

        Returns the lock_id (pls-...) on success, or "" if the resource
        is already locked by another holder (and the lock has not expired).
        """
        # Check for existing lock on this resource
        existing_id = self._by_resource.get(resource_name)
        if existing_id is not None:
            existing = self._locks.get(existing_id)
            if existing is not None:
                if self._is_expired(existing):
                    # Expired -- clean it up and allow re-acquisition
                    self._remove_lock(existing)
                    self._total_expired += 1
                    logger.info("lock_expired_on_acquire", lock_id=existing_id,
                                resource=resource_name, holder=existing.holder)
                else:
                    # Still active -- reject
                    logger.warning("lock_already_held", resource=resource_name,
                                   holder=existing.holder)
                    return ""

        lock_id = self._generate_id(resource_name)
        now = time.time()

        entry = LockEntry(
            lock_id=lock_id,
            resource_name=resource_name,
            holder=holder,
            acquired_at=now,
            expires_at=now + ttl,
            tags=list(tags) if tags else [],
        )

        self._locks[lock_id] = entry
        self._by_resource[resource_name] = lock_id
        self._total_acquired += 1
        self._prune()

        logger.info("lock_acquired", lock_id=lock_id, resource=resource_name,
                     holder=holder, ttl=ttl)
        self._fire("acquire", self._entry_to_dict(entry))
        return lock_id

    # ------------------------------------------------------------------
    # release
    # ------------------------------------------------------------------

    def release(self, resource_name: str, holder: str) -> bool:
        """Release a lock held by the specified holder.

        Returns False if the resource is not locked or the holder does
        not match.
        """
        lock_id = self._by_resource.get(resource_name)
        if lock_id is None:
            return False

        entry = self._locks.get(lock_id)
        if entry is None:
            return False

        if entry.holder != holder:
            logger.warning("lock_release_denied", resource=resource_name,
                           holder=holder, actual_holder=entry.holder)
            return False

        self._remove_lock(entry)
        self._total_released += 1

        logger.info("lock_released", lock_id=lock_id, resource=resource_name,
                     holder=holder)
        self._fire("release", {"lock_id": lock_id,
                                "resource_name": resource_name,
                                "holder": holder})
        return True

    # ------------------------------------------------------------------
    # is_locked
    # ------------------------------------------------------------------

    def is_locked(self, resource_name: str) -> bool:
        """Check whether a resource is currently locked (non-expired)."""
        lock_id = self._by_resource.get(resource_name)
        if lock_id is None:
            return False

        entry = self._locks.get(lock_id)
        if entry is None:
            return False

        if self._is_expired(entry):
            self._remove_lock(entry)
            self._total_expired += 1
            return False

        return True

    # ------------------------------------------------------------------
    # get_lock_info
    # ------------------------------------------------------------------

    def get_lock_info(self, resource_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve lock information for a resource. Returns None if
        the resource is not locked or the lock has expired."""
        lock_id = self._by_resource.get(resource_name)
        if lock_id is None:
            return None

        entry = self._locks.get(lock_id)
        if entry is None:
            return None

        if self._is_expired(entry):
            self._remove_lock(entry)
            self._total_expired += 1
            return None

        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # get_holder_locks
    # ------------------------------------------------------------------

    def get_holder_locks(self, holder: str) -> List[Dict[str, Any]]:
        """Return all active (non-expired) locks held by the given holder.

        Results are sorted by acquired_at (earliest first).
        """
        now = time.time()
        results: List[Dict[str, Any]] = []

        for entry in list(self._locks.values()):
            if entry.holder != holder:
                continue
            if now >= entry.expires_at:
                continue
            results.append(self._entry_to_dict(entry))

        results.sort(key=lambda d: d["acquired_at"])
        return results

    # ------------------------------------------------------------------
    # force_release
    # ------------------------------------------------------------------

    def force_release(self, resource_name: str) -> bool:
        """Admin override to release a lock regardless of holder.

        Returns False if the resource is not locked.
        """
        lock_id = self._by_resource.get(resource_name)
        if lock_id is None:
            return False

        entry = self._locks.get(lock_id)
        if entry is None:
            return False

        self._remove_lock(entry)
        self._total_force_released += 1

        logger.info("lock_force_released", lock_id=lock_id,
                     resource=resource_name, holder=entry.holder)
        self._fire("force_release", {"lock_id": lock_id,
                                      "resource_name": resource_name,
                                      "holder": entry.holder})
        return True

    # ------------------------------------------------------------------
    # list_locks
    # ------------------------------------------------------------------

    def list_locks(self) -> List[Dict[str, Any]]:
        """List all active (non-expired) locks.

        Results are sorted by resource_name.
        """
        now = time.time()
        results: List[Dict[str, Any]] = []

        for entry in self._locks.values():
            if now >= entry.expires_at:
                continue
            results.append(self._entry_to_dict(entry))

        results.sort(key=lambda d: d["resource_name"])
        return results

    # ------------------------------------------------------------------
    # cleanup_expired
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> int:
        """Remove all expired locks and return the count of removed entries."""
        now = time.time()
        expired_ids: List[str] = []

        for lock_id, entry in self._locks.items():
            if now >= entry.expires_at:
                expired_ids.append(lock_id)

        for lock_id in expired_ids:
            entry = self._locks.pop(lock_id)
            self._by_resource.pop(entry.resource_name, None)
            self._total_expired += 1
            logger.info("lock_expired_cleanup", lock_id=lock_id,
                         resource=entry.resource_name, holder=entry.holder)
            self._fire("expired", {"lock_id": lock_id,
                                    "resource_name": entry.resource_name,
                                    "holder": entry.holder})

        if expired_ids:
            logger.info("expired_locks_cleaned", count=len(expired_ids))
        return len(expired_ids)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        now = time.time()
        active_count = sum(1 for e in self._locks.values() if now < e.expires_at)
        expired_count = len(self._locks) - active_count
        return {
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
            "total_expired": self._total_expired,
            "total_force_released": self._total_force_released,
            "current_locks": len(self._locks),
            "current_active": active_count,
            "current_expired_pending": expired_count,
            "callbacks": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all locks, callbacks, and counters."""
        self._locks.clear()
        self._by_resource.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_acquired = 0
        self._total_released = 0
        self._total_expired = 0
        self._total_force_released = 0
        logger.info("lock_store_reset")
