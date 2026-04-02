"""Pipeline Cache Layer – in-memory caching with TTL and eviction.

Provides get/set/delete with TTL-based expiration, LRU eviction when
capacity is reached, and namespace support for cache isolation.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CacheEntry:
    key: str
    namespace: str
    value: Any
    ttl_seconds: float
    created_at: float
    accessed_at: float
    access_count: int


class PipelineCacheLayer:
    """In-memory cache with TTL and LRU eviction."""

    def __init__(self, max_entries: int = 100000, default_ttl: float = 300.0):
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._callbacks: Dict[str, Callable] = {}

        # stats
        self._total_sets = 0
        self._total_gets = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._total_expirations = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl_seconds: float = 0.0,
    ) -> bool:
        if not key:
            return False

        full_key = f"{namespace}:{key}"
        ttl = ttl_seconds if ttl_seconds > 0 else self._default_ttl
        now = time.time()

        if full_key in self._entries:
            # Update existing
            entry = self._entries[full_key]
            entry.value = value
            entry.ttl_seconds = ttl
            entry.created_at = now
            entry.accessed_at = now
            self._entries.move_to_end(full_key)
        else:
            # Evict if at capacity
            while len(self._entries) >= self._max_entries:
                self._evict_one()

            entry = _CacheEntry(
                key=key,
                namespace=namespace,
                value=value,
                ttl_seconds=ttl,
                created_at=now,
                accessed_at=now,
                access_count=0,
            )
            self._entries[full_key] = entry

        self._total_sets += 1
        return True

    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        full_key = f"{namespace}:{key}"
        self._total_gets += 1

        entry = self._entries.get(full_key)
        if not entry:
            self._total_misses += 1
            return default

        # Check TTL
        if self._is_expired(entry):
            self._entries.pop(full_key)
            self._total_expirations += 1
            self._total_misses += 1
            return default

        entry.accessed_at = time.time()
        entry.access_count += 1
        self._entries.move_to_end(full_key)
        self._total_hits += 1
        return entry.value

    def delete(self, key: str, namespace: str = "default") -> bool:
        full_key = f"{namespace}:{key}"
        entry = self._entries.pop(full_key, None)
        return entry is not None

    def exists(self, key: str, namespace: str = "default") -> bool:
        full_key = f"{namespace}:{key}"
        entry = self._entries.get(full_key)
        if not entry:
            return False
        if self._is_expired(entry):
            self._entries.pop(full_key)
            self._total_expirations += 1
            return False
        return True

    def get_or_set(
        self,
        key: str,
        factory: Callable,
        namespace: str = "default",
        ttl_seconds: float = 0.0,
    ) -> Any:
        """Get value or compute and cache it if missing."""
        val = self.get(key, namespace)
        if val is not None:
            return val
        val = factory()
        self.set(key, val, namespace, ttl_seconds)
        return val

    # ------------------------------------------------------------------
    # Namespace operations
    # ------------------------------------------------------------------

    def clear_namespace(self, namespace: str) -> int:
        keys_to_remove = [k for k, e in self._entries.items() if e.namespace == namespace]
        for k in keys_to_remove:
            self._entries.pop(k)
        return len(keys_to_remove)

    def get_namespace_keys(self, namespace: str) -> List[str]:
        return [e.key for e in self._entries.values()
                if e.namespace == namespace and not self._is_expired(e)]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        expired = [k for k, e in self._entries.items() if self._is_expired(e)]
        for k in expired:
            self._entries.pop(k)
        self._total_expirations += len(expired)
        return len(expired)

    def _evict_one(self) -> None:
        """Evict the least recently used entry."""
        if self._entries:
            self._entries.popitem(last=False)
            self._total_evictions += 1

    def _is_expired(self, entry: _CacheEntry) -> bool:
        if entry.ttl_seconds <= 0:
            return False
        return (time.time() - entry.created_at) > entry.ttl_seconds

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_info(self, key: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        full_key = f"{namespace}:{key}"
        entry = self._entries.get(full_key)
        if not entry or self._is_expired(entry):
            return None
        remaining = max(0.0, entry.ttl_seconds - (time.time() - entry.created_at)) if entry.ttl_seconds > 0 else 0.0
        return {
            "key": entry.key,
            "namespace": entry.namespace,
            "ttl_seconds": entry.ttl_seconds,
            "remaining_ttl": remaining,
            "access_count": entry.access_count,
            "created_at": entry.created_at,
            "accessed_at": entry.accessed_at,
        }

    def size(self) -> int:
        return len(self._entries)

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
        hit_rate = (self._total_hits / self._total_gets * 100.0) if self._total_gets > 0 else 0.0
        return {
            "current_entries": len(self._entries),
            "max_entries": self._max_entries,
            "total_sets": self._total_sets,
            "total_gets": self._total_gets,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "hit_rate_pct": hit_rate,
            "total_evictions": self._total_evictions,
            "total_expirations": self._total_expirations,
        }

    def reset(self) -> None:
        self._entries.clear()
        self._callbacks.clear()
        self._total_sets = 0
        self._total_gets = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._total_expirations = 0
