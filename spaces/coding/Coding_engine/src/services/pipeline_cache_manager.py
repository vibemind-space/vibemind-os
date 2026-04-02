"""Pipeline cache manager.

Provides in-memory caching for pipeline operations with TTL-based
expiration, LRU eviction, namespace isolation, and hit/miss tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _CacheEntry:
    """A cached value."""
    key: str = ""
    value: Any = None
    namespace: str = "default"
    ttl_ms: float = 0.0  # 0 = no expiration
    created_at: float = 0.0
    expires_at: float = 0.0
    last_accessed_at: float = 0.0
    access_count: int = 0
    size_bytes: int = 0
    tags: List[str] = field(default_factory=list)
    seq: int = 0


class PipelineCacheManager:
    """Manages pipeline caches."""

    def __init__(self, max_entries: int = 100000,
                 default_ttl_ms: float = 300000.0):  # 5 min default
        self._max_entries = max_entries
        self._default_ttl_ms = default_ttl_ms
        self._cache: Dict[str, _CacheEntry] = {}
        self._entry_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_sets": 0,
            "total_gets": 0,
            "total_hits": 0,
            "total_misses": 0,
            "total_evictions": 0,
            "total_expirations": 0,
        }

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any, namespace: str = "default",
            ttl_ms: float = 0.0, tags: Optional[List[str]] = None) -> bool:
        """Set a cache entry."""
        if not key:
            return False

        # Use default TTL if none specified
        effective_ttl = ttl_ms if ttl_ms > 0 else self._default_ttl_ms

        # Evict if at capacity
        cache_key = f"{namespace}:{key}"
        if cache_key not in self._cache and len(self._cache) >= self._max_entries:
            self._evict_lru()

        now = time.time()
        self._entry_seq += 1
        expires_at = now + (effective_ttl / 1000.0) if effective_ttl > 0 else 0.0

        size_bytes = len(str(value).encode()) if value is not None else 0

        self._cache[cache_key] = _CacheEntry(
            key=key,
            value=value,
            namespace=namespace,
            ttl_ms=effective_ttl,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
            access_count=0,
            size_bytes=size_bytes,
            tags=tags or [],
            seq=self._entry_seq,
        )
        self._stats["total_sets"] += 1
        return True

    def get(self, key: str, namespace: str = "default") -> Any:
        """Get a cached value. Returns None if not found or expired."""
        cache_key = f"{namespace}:{key}"
        self._stats["total_gets"] += 1

        entry = self._cache.get(cache_key)
        if not entry:
            self._stats["total_misses"] += 1
            return None

        # Check expiration
        if entry.expires_at > 0 and time.time() > entry.expires_at:
            del self._cache[cache_key]
            self._stats["total_expirations"] += 1
            self._stats["total_misses"] += 1
            return None

        entry.last_accessed_at = time.time()
        entry.access_count += 1
        self._stats["total_hits"] += 1
        return entry.value

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a cache entry."""
        cache_key = f"{namespace}:{key}"
        if cache_key not in self._cache:
            return False
        del self._cache[cache_key]
        return True

    def exists(self, key: str, namespace: str = "default") -> bool:
        """Check if a key exists and is not expired."""
        return self.get(key, namespace) is not None

    def get_or_set(self, key: str, default_value: Any,
                   namespace: str = "default",
                   ttl_ms: float = 0.0) -> Any:
        """Get value if cached, otherwise set and return default."""
        val = self.get(key, namespace)
        if val is not None:
            return val
        self.set(key, default_value, namespace, ttl_ms)
        return default_value

    # ------------------------------------------------------------------
    # Namespace Operations
    # ------------------------------------------------------------------

    def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace. Returns count cleared."""
        to_remove = [k for k, e in self._cache.items()
                     if e.namespace == namespace]
        for k in to_remove:
            del self._cache[k]
        return len(to_remove)

    def get_namespaces(self) -> List[str]:
        """Get all active namespaces."""
        namespaces: Set[str] = set()
        for e in self._cache.values():
            namespaces.add(e.namespace)
        return sorted(namespaces)

    def get_namespace_size(self, namespace: str) -> int:
        """Get number of entries in a namespace."""
        return sum(1 for e in self._cache.values()
                   if e.namespace == namespace)

    # ------------------------------------------------------------------
    # Eviction / Cleanup
    # ------------------------------------------------------------------

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._cache:
            return
        lru_key = min(self._cache.keys(),
                      key=lambda k: self._cache[k].last_accessed_at)
        del self._cache[lru_key]
        self._stats["total_evictions"] += 1

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.time()
        to_remove = [k for k, e in self._cache.items()
                     if e.expires_at > 0 and now > e.expires_at]
        for k in to_remove:
            del self._cache[k]
        self._stats["total_expirations"] += len(to_remove)
        return len(to_remove)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entry_info(self, key: str, namespace: str = "default") -> Optional[Dict]:
        """Get cache entry metadata (without value)."""
        cache_key = f"{namespace}:{key}"
        e = self._cache.get(cache_key)
        if not e:
            return None
        return {
            "key": e.key,
            "namespace": e.namespace,
            "ttl_ms": e.ttl_ms,
            "expires_at": e.expires_at,
            "last_accessed_at": e.last_accessed_at,
            "access_count": e.access_count,
            "size_bytes": e.size_bytes,
            "tags": list(e.tags),
            "seq": e.seq,
        }

    def search_entries(self, namespace: Optional[str] = None,
                       tag: Optional[str] = None,
                       limit: int = 100) -> List[Dict]:
        """Search cache entries."""
        result = []
        for e in self._cache.values():
            if namespace and e.namespace != namespace:
                continue
            if tag and tag not in e.tags:
                continue
            result.append({
                "key": e.key,
                "namespace": e.namespace,
                "access_count": e.access_count,
                "size_bytes": e.size_bytes,
                "seq": e.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_hit_rate(self) -> Dict:
        """Get cache hit rate."""
        total = self._stats["total_gets"]
        if total == 0:
            return {"total_gets": 0, "hit_rate": 0.0}
        rate = round((self._stats["total_hits"] / total) * 100.0, 1)
        return {
            "total_gets": total,
            "total_hits": self._stats["total_hits"],
            "total_misses": self._stats["total_misses"],
            "hit_rate": rate,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        total_size = sum(e.size_bytes for e in self._cache.values())
        return {
            **self._stats,
            "current_entries": len(self._cache),
            "total_size_bytes": total_size,
            "namespace_count": len(self.get_namespaces()),
        }

    def reset(self) -> None:
        self._cache.clear()
        self._entry_seq = 0
        self._stats = {k: 0 for k in self._stats}
