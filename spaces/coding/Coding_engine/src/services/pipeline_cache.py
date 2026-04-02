"""
Pipeline Cache — multi-layer caching for pipeline execution results.

Features:
- Key/value storage with TTL expiration
- Namespaced caches (per-agent, per-phase, global)
- Size-limited with LRU eviction
- Hit/miss statistics per namespace
- Cache warming (bulk preload)
- Tag-based invalidation
- Content-addressable entries (optional dedup)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """A single cache entry."""
    key: str
    value: Any
    namespace: str
    created_at: float
    accessed_at: float
    ttl: float  # 0 = never expires
    size_bytes: int
    tags: Set[str]
    content_hash: str = ""


# ---------------------------------------------------------------------------
# Pipeline Cache
# ---------------------------------------------------------------------------

class PipelineCache:
    """Multi-layer cache with namespaces, TTL, and LRU eviction."""

    def __init__(
        self,
        max_entries: int = 10000,
        max_bytes: int = 100 * 1024 * 1024,  # 100 MB
        default_ttl: float = 3600.0,  # 1 hour
    ):
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._default_ttl = default_ttl

        # namespace -> OrderedDict[key, CacheEntry]  (LRU order)
        self._caches: Dict[str, OrderedDict[str, CacheEntry]] = {}
        self._total_bytes = 0

        self._stats = {
            "total_sets": 0,
            "total_gets": 0,
            "total_hits": 0,
            "total_misses": 0,
            "total_evictions": 0,
            "total_expirations": 0,
            "total_invalidations": 0,
        }
        # Per-namespace hit/miss
        self._ns_stats: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = "global",
        ttl: float = 0.0,
        tags: Optional[Set[str]] = None,
        size_bytes: int = 0,
    ) -> bool:
        """Store a value in the cache."""
        if not key:
            return False

        effective_ttl = ttl if ttl > 0 else self._default_ttl
        now = time.time()

        # Estimate size if not provided
        if size_bytes <= 0:
            size_bytes = self._estimate_size(value)

        # Content hash for dedup lookups
        content_hash = ""
        if isinstance(value, (bytes, str)):
            data = value if isinstance(value, bytes) else value.encode()
            content_hash = hashlib.sha256(data).hexdigest()[:16]

        # Remove old entry if exists (update)
        if namespace in self._caches and key in self._caches[namespace]:
            old = self._caches[namespace][key]
            self._total_bytes -= old.size_bytes
            del self._caches[namespace][key]

        # Ensure namespace exists
        if namespace not in self._caches:
            self._caches[namespace] = OrderedDict()
            self._ns_stats[namespace] = {"hits": 0, "misses": 0, "sets": 0}

        entry = CacheEntry(
            key=key,
            value=value,
            namespace=namespace,
            created_at=now,
            accessed_at=now,
            ttl=effective_ttl,
            size_bytes=size_bytes,
            tags=tags or set(),
            content_hash=content_hash,
        )

        self._caches[namespace][key] = entry
        self._total_bytes += size_bytes
        self._stats["total_sets"] += 1
        self._ns_stats[namespace]["sets"] += 1

        # Evict if over limits
        self._evict_if_needed()

        return True

    def get(
        self,
        key: str,
        namespace: str = "global",
    ) -> Any:
        """Get a value from cache. Returns None on miss."""
        self._stats["total_gets"] += 1

        if namespace not in self._caches:
            self._stats["total_misses"] += 1
            if namespace in self._ns_stats:
                self._ns_stats[namespace]["misses"] += 1
            return None

        entry = self._caches[namespace].get(key)
        if entry is None:
            self._stats["total_misses"] += 1
            self._ns_stats[namespace]["misses"] += 1
            return None

        # Check TTL
        now = time.time()
        if entry.ttl > 0 and (now - entry.created_at) > entry.ttl:
            self._remove_entry(namespace, key)
            self._stats["total_expirations"] += 1
            self._stats["total_misses"] += 1
            self._ns_stats[namespace]["misses"] += 1
            return None

        # Hit — move to end (most recently used)
        entry.accessed_at = now
        self._caches[namespace].move_to_end(key)
        self._stats["total_hits"] += 1
        self._ns_stats[namespace]["hits"] += 1
        return entry.value

    def delete(self, key: str, namespace: str = "global") -> bool:
        """Delete a specific entry."""
        if namespace not in self._caches or key not in self._caches[namespace]:
            return False
        self._remove_entry(namespace, key)
        return True

    def has(self, key: str, namespace: str = "global") -> bool:
        """Check if key exists and is not expired (without counting as a get)."""
        if namespace not in self._caches:
            return False
        entry = self._caches[namespace].get(key)
        if entry is None:
            return False
        now = time.time()
        if entry.ttl > 0 and (now - entry.created_at) > entry.ttl:
            self._remove_entry(namespace, key)
            self._stats["total_expirations"] += 1
            return False
        return True

    # ------------------------------------------------------------------
    # Namespace operations
    # ------------------------------------------------------------------

    def list_namespaces(self) -> List[Dict]:
        """List all namespaces with entry counts."""
        result = []
        for ns, cache in sorted(self._caches.items()):
            ns_bytes = sum(e.size_bytes for e in cache.values())
            result.append({
                "namespace": ns,
                "entry_count": len(cache),
                "size_bytes": ns_bytes,
                "hits": self._ns_stats.get(ns, {}).get("hits", 0),
                "misses": self._ns_stats.get(ns, {}).get("misses", 0),
            })
        return result

    def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace. Returns count removed."""
        if namespace not in self._caches:
            return 0
        count = len(self._caches[namespace])
        for entry in self._caches[namespace].values():
            self._total_bytes -= entry.size_bytes
        del self._caches[namespace]
        return count

    def list_keys(self, namespace: str = "global", limit: int = 100) -> List[str]:
        """List keys in a namespace."""
        if namespace not in self._caches:
            return []
        keys = list(self._caches[namespace].keys())
        return keys[:limit]

    # ------------------------------------------------------------------
    # Tag-based invalidation
    # ------------------------------------------------------------------

    def invalidate_by_tag(self, tag: str) -> int:
        """Remove all entries with a given tag. Returns count removed."""
        removed = 0
        for ns in list(self._caches.keys()):
            to_remove = [
                k for k, e in self._caches[ns].items() if tag in e.tags
            ]
            for k in to_remove:
                self._remove_entry(ns, k)
                removed += 1
        self._stats["total_invalidations"] += removed
        return removed

    def invalidate_by_tags(self, tags: Set[str]) -> int:
        """Remove entries matching ANY of the given tags."""
        removed = 0
        for ns in list(self._caches.keys()):
            to_remove = [
                k for k, e in self._caches[ns].items()
                if e.tags.intersection(tags)
            ]
            for k in to_remove:
                self._remove_entry(ns, k)
                removed += 1
        self._stats["total_invalidations"] += removed
        return removed

    # ------------------------------------------------------------------
    # Bulk / warming
    # ------------------------------------------------------------------

    def warm(
        self,
        entries: List[Dict],
        namespace: str = "global",
    ) -> int:
        """Bulk load entries. Each dict: {key, value, ttl?, tags?}. Returns count loaded."""
        loaded = 0
        for entry in entries:
            key = entry.get("key", "")
            value = entry.get("value")
            if not key:
                continue
            self.set(
                key=key,
                value=value,
                namespace=namespace,
                ttl=entry.get("ttl", 0.0),
                tags=entry.get("tags"),
            )
            loaded += 1
        return loaded

    def get_multi(
        self,
        keys: List[str],
        namespace: str = "global",
    ) -> Dict[str, Any]:
        """Get multiple keys at once. Returns {key: value} for hits."""
        result = {}
        for key in keys:
            val = self.get(key, namespace)
            if val is not None:
                result[key] = val
        return result

    # ------------------------------------------------------------------
    # Info & metadata
    # ------------------------------------------------------------------

    def get_entry_info(self, key: str, namespace: str = "global") -> Optional[Dict]:
        """Get metadata about a cache entry (without counting as hit)."""
        if namespace not in self._caches:
            return None
        entry = self._caches[namespace].get(key)
        if entry is None:
            return None
        now = time.time()
        age = now - entry.created_at
        remaining_ttl = max(0, entry.ttl - age) if entry.ttl > 0 else -1
        return {
            "key": entry.key,
            "namespace": entry.namespace,
            "size_bytes": entry.size_bytes,
            "created_at": entry.created_at,
            "accessed_at": entry.accessed_at,
            "ttl": entry.ttl,
            "remaining_ttl": remaining_ttl,
            "age_seconds": round(age, 2),
            "tags": sorted(entry.tags),
            "content_hash": entry.content_hash,
            "expired": entry.ttl > 0 and age > entry.ttl,
        }

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        removed = 0
        now = time.time()
        for ns in list(self._caches.keys()):
            to_remove = [
                k for k, e in self._caches[ns].items()
                if e.ttl > 0 and (now - e.created_at) > e.ttl
            ]
            for k in to_remove:
                self._remove_entry(ns, k)
                removed += 1
        self._stats["total_expirations"] += removed
        return removed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _remove_entry(self, namespace: str, key: str) -> None:
        if namespace in self._caches and key in self._caches[namespace]:
            entry = self._caches[namespace][key]
            self._total_bytes -= entry.size_bytes
            del self._caches[namespace][key]
            if not self._caches[namespace]:
                del self._caches[namespace]

    def _evict_if_needed(self) -> None:
        """Evict LRU entries if over limits."""
        total_entries = sum(len(c) for c in self._caches.values())

        while (total_entries > self._max_entries or
               self._total_bytes > self._max_bytes):
            # Find namespace with oldest accessed entry
            oldest_ns = None
            oldest_key = None
            oldest_time = float("inf")

            for ns, cache in self._caches.items():
                if cache:
                    first_key = next(iter(cache))
                    entry = cache[first_key]
                    if entry.accessed_at < oldest_time:
                        oldest_time = entry.accessed_at
                        oldest_ns = ns
                        oldest_key = first_key

            if oldest_ns is None:
                break

            self._remove_entry(oldest_ns, oldest_key)
            self._stats["total_evictions"] += 1
            total_entries -= 1

    def _estimate_size(self, value: Any) -> int:
        """Rough size estimate for a value."""
        if isinstance(value, bytes):
            return len(value)
        if isinstance(value, str):
            return len(value.encode())
        if isinstance(value, (int, float, bool)):
            return 8
        if isinstance(value, (list, tuple)):
            return sum(self._estimate_size(v) for v in value) + 56
        if isinstance(value, dict):
            return sum(
                self._estimate_size(k) + self._estimate_size(v)
                for k, v in value.items()
            ) + 200
        return 64  # default

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        total_entries = sum(len(c) for c in self._caches.values())
        hit_rate = 0.0
        total_gets = self._stats["total_gets"]
        if total_gets > 0:
            hit_rate = round(self._stats["total_hits"] / total_gets * 100, 2)
        return {
            **self._stats,
            "total_entries": total_entries,
            "total_bytes": self._total_bytes,
            "total_namespaces": len(self._caches),
            "hit_rate_percent": hit_rate,
        }

    def reset(self) -> None:
        self._caches.clear()
        self._ns_stats.clear()
        self._total_bytes = 0
        self._stats = {k: 0 for k in self._stats}
