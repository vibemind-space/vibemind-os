"""Pipeline result cache — caches pipeline execution results.

Stores pipeline outputs keyed by arbitrary strings with TTL-based
expiration, max-entries eviction, tag-based invalidation, and
hit/miss tracking.  Supports compute-on-miss via ``get_or_compute``.

All methods are synchronous with no external dependencies beyond stdlib.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    """A single cached result."""
    cache_id: str = ""
    key: str = ""
    value: Any = None
    tags: List[str] = field(default_factory=list)
    ttl_seconds: float = 300.0
    created_at: float = 0.0
    accessed_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Result Cache
# ---------------------------------------------------------------------------

class PipelineResultCache:
    """Caches pipeline execution results with TTL, eviction, and tracking."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, _CacheEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_puts": 0,
            "total_gets": 0,
            "total_hits": 0,
            "total_misses": 0,
            "total_deletes": 0,
            "total_evictions": 0,
            "total_expired": 0,
            "total_clears": 0,
            "total_computes": 0,
        }

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: float = 300.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a value in the cache.

        If the key already exists its entry is replaced.
        Returns the generated cache_id string.
        """
        if not key:
            return ""

        # Remove existing entry for this key if present
        if key in self._entries:
            del self._entries[key]

        # Generate collision-free ID
        self._seq += 1
        cache_id = "prc-" + hashlib.sha256(
            f"{key}{time.time()}{self._seq}".encode()
        ).hexdigest()[:16]

        now = time.time()
        entry = _CacheEntry(
            cache_id=cache_id,
            key=key,
            value=value,
            tags=list(tags) if tags else [],
            ttl_seconds=ttl_seconds,
            created_at=now,
            accessed_at=now,
            seq=self._seq,
        )
        self._entries[key] = entry
        self._stats["total_puts"] += 1

        # Evict oldest entries if over capacity
        self._prune_if_needed()

        logger.debug("cache_put", key=key, cache_id=cache_id,
                     ttl=ttl_seconds)
        self._fire("put", {"key": key, "cache_id": cache_id})
        return cache_id

    def get(self, key: str) -> Any:
        """Get a cached value by key.

        Returns the value if found and not expired, otherwise ``None``.
        Tracks hits and misses.
        """
        self._stats["total_gets"] += 1

        entry = self._entries.get(key)
        if entry is None:
            self._stats["total_misses"] += 1
            return None

        # Check TTL expiration
        now = time.time()
        if entry.ttl_seconds > 0 and (now - entry.created_at) > entry.ttl_seconds:
            del self._entries[key]
            self._stats["total_expired"] += 1
            self._stats["total_misses"] += 1
            return None

        # Record hit
        entry.accessed_at = now
        self._stats["total_hits"] += 1
        return entry.value

    def delete(self, key: str) -> bool:
        """Delete a specific cached entry.

        Returns ``True`` if the key was found and removed.
        """
        if key not in self._entries:
            return False
        del self._entries[key]
        self._stats["total_deletes"] += 1
        logger.debug("cache_delete", key=key)
        self._fire("delete", {"key": key})
        return True

    def has(self, key: str) -> bool:
        """Check whether *key* exists and is not expired.

        Does not count as a hit or miss.
        """
        entry = self._entries.get(key)
        if entry is None:
            return False
        now = time.time()
        if entry.ttl_seconds > 0 and (now - entry.created_at) > entry.ttl_seconds:
            del self._entries[key]
            self._stats["total_expired"] += 1
            return False
        return True

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl_seconds: float = 300.0,
    ) -> Any:
        """Return cached value or compute, cache, and return it.

        If the key is present and not expired the cached value is
        returned (counting as a hit).  Otherwise *compute_fn* is
        called, the result is stored under *key* with the given TTL,
        and the computed value is returned.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        # Compute fresh value
        value = compute_fn()
        self.put(key, value, ttl_seconds=ttl_seconds)
        self._stats["total_computes"] += 1
        return value

    # ------------------------------------------------------------------
    # Bulk / tag operations
    # ------------------------------------------------------------------

    def clear(self, tag: Optional[str] = None) -> int:
        """Clear cache entries.

        If *tag* is given only entries tagged with it are removed.
        Otherwise **all** entries are removed.  Returns the count of
        entries cleared.
        """
        if tag is None:
            count = len(self._entries)
            self._entries.clear()
            self._stats["total_clears"] += count
            if count > 0:
                logger.debug("cache_cleared", count=count)
                self._fire("clear", {"count": count})
            return count

        to_remove = [
            k for k, e in self._entries.items() if tag in e.tags
        ]
        for k in to_remove:
            del self._entries[k]
        count = len(to_remove)
        self._stats["total_clears"] += count
        if count > 0:
            logger.debug("cache_cleared_by_tag", tag=tag, count=count)
            self._fire("clear", {"tag": tag, "count": count})
        return count

    def list_keys(self, tag: Optional[str] = None) -> List[str]:
        """List all cached keys, optionally filtered by *tag*.

        Returns keys sorted by insertion order (oldest first).
        Expired entries are excluded.
        """
        now = time.time()
        result: List[str] = []
        expired_keys: List[str] = []

        for key, entry in self._entries.items():
            # Skip expired
            if entry.ttl_seconds > 0 and (now - entry.created_at) > entry.ttl_seconds:
                expired_keys.append(key)
                continue
            if tag is not None and tag not in entry.tags:
                continue
            result.append(key)

        # Lazily remove expired entries encountered during iteration
        for k in expired_keys:
            del self._entries[k]
            self._stats["total_expired"] += 1

        return result

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns the count of entries removed.
        """
        now = time.time()
        to_remove = [
            k for k, e in self._entries.items()
            if e.ttl_seconds > 0 and (now - e.created_at) > e.ttl_seconds
        ]
        for k in to_remove:
            del self._entries[k]
        count = len(to_remove)
        self._stats["total_expired"] += count
        if count > 0:
            logger.debug("expired_cleanup", count=count)
            self._fire("cleanup", {"count": count})
        return count

    # ------------------------------------------------------------------
    # Cache statistics
    # ------------------------------------------------------------------

    def get_cache_stats(self) -> Dict:
        """Return cache-specific statistics.

        Includes total entries, hit/miss counts, hit rate, and
        eviction count.
        """
        hits = self._stats["total_hits"]
        misses = self._stats["total_misses"]
        total_lookups = hits + misses
        hit_rate = 0.0
        if total_lookups > 0:
            hit_rate = round(hits / total_lookups * 100, 2)

        return {
            "total_entries": len(self._entries),
            "hits": hits,
            "misses": misses,
            "hit_rate": hit_rate,
            "evictions": self._stats["total_evictions"],
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Callbacks receive ``(action, data)`` arguments when cache
        state changes.  Returns ``False`` if *name* is already taken.
        """
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Invoke all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict oldest entries when over *max_entries*."""
        if len(self._entries) <= self._max_entries:
            return

        # Sort by seq (oldest first) and remove excess
        sorted_keys = sorted(
            self._entries.keys(),
            key=lambda k: self._entries[k].seq,
        )
        to_remove = len(self._entries) - self._max_entries
        for key in sorted_keys[:to_remove]:
            del self._entries[key]
            self._stats["total_evictions"] += 1

        if to_remove > 0:
            logger.debug("cache_eviction", evicted=to_remove)
            self._fire("eviction", {"count": to_remove})

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        hits = self._stats["total_hits"]
        misses = self._stats["total_misses"]
        total_lookups = hits + misses
        hit_rate = 0.0
        if total_lookups > 0:
            hit_rate = round(hits / total_lookups * 100, 2)

        return {
            **self._stats,
            "current_entries": len(self._entries),
            "max_entries": self._max_entries,
            "hit_rate_percent": hit_rate,
        }

    def reset(self) -> None:
        """Clear all entries, counters, and callbacks.

        Restores the cache to its initial empty state.  The sequence
        counter is reset to zero, all callbacks are removed, and
        all stat counters are zeroed out.
        """
        self._entries.clear()
        self._seq = 0
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
        logger.debug("result_cache_reset")
