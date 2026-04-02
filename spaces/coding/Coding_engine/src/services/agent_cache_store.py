"""Agent Cache Store – per-agent caching with TTL, namespaces, and eviction.

Provides namespaced key-value caching per agent with time-to-live expiration,
automatic eviction of expired entries, max-entries pruning, and hit/miss
tracking for cache performance analysis.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    cache_id: str
    agent_id: str
    namespace: str
    key: str
    value: Any
    ttl: float
    created_at: float
    expires_at: float
    tags: List[str] = field(default_factory=list)
    seq: int = 0


class AgentCacheStore:
    """Per-agent caching with TTL, namespaces, and eviction."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, CacheEntry] = {}
        self._lookup: Dict[str, str] = {}  # "agent:ns:key" -> cache_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_puts = 0
        self._total_gets = 0
        self._total_deletes = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._total_expirations = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"acs-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acs-{digest}"

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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_lookup_key(agent_id: str, namespace: str, key: str) -> str:
        return f"{agent_id}:{namespace}:{key}"

    def _is_expired(self, entry: CacheEntry) -> bool:
        return time.time() >= entry.expires_at

    def _evict_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.time()
        expired_ids = [
            eid for eid, entry in self._entries.items()
            if now >= entry.expires_at
        ]
        for eid in expired_ids:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.namespace, entry.key)
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_expirations += 1
            logger.debug("cache_entry_expired", cache_id=eid, agent_id=entry.agent_id)

        return len(expired_ids)

    def _prune_if_needed(self) -> None:
        """Prune oldest entries when max_entries is exceeded."""
        if len(self._entries) < self._max_entries:
            return

        # First try evicting expired entries
        self._evict_expired()
        if len(self._entries) < self._max_entries:
            return

        # Evict by oldest seq
        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.namespace, entry.key)
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug("cache_entry_evicted", cache_id=eid, agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def put(
        self,
        agent_id: str,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl: float = 3600,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a value in the cache. Returns the cache_id."""
        if not agent_id or not key:
            logger.warning("cache_put_invalid_args", agent_id=agent_id, key=key)
            return ""

        lk = self._make_lookup_key(agent_id, namespace, key)
        now = time.time()
        expires_at = now + ttl
        resolved_tags = list(tags) if tags else []

        # Update existing entry
        existing_eid = self._lookup.get(lk)
        if existing_eid and existing_eid in self._entries:
            entry = self._entries[existing_eid]
            old_value = entry.value
            entry.value = value
            entry.ttl = ttl
            entry.created_at = now
            entry.expires_at = expires_at
            entry.tags = resolved_tags
            self._seq += 1
            entry.seq = self._seq
            self._total_puts += 1
            logger.debug(
                "cache_updated", agent_id=agent_id, namespace=namespace, key=key,
            )
            self._fire("cache_updated", {
                "cache_id": existing_eid,
                "agent_id": agent_id,
                "namespace": namespace,
                "key": key,
                "old_value": old_value,
                "new_value": value,
            })
            return existing_eid

        # New entry
        self._prune_if_needed()
        cache_id = self._gen_id(f"{agent_id}-{namespace}-{key}")
        entry = CacheEntry(
            cache_id=cache_id,
            agent_id=agent_id,
            namespace=namespace,
            key=key,
            value=value,
            ttl=ttl,
            created_at=now,
            expires_at=expires_at,
            tags=resolved_tags,
            seq=self._seq,
        )
        self._entries[cache_id] = entry
        self._lookup[lk] = cache_id
        self._total_puts += 1
        logger.debug(
            "cache_created", agent_id=agent_id, namespace=namespace, key=key,
            cache_id=cache_id,
        )
        self._fire("cache_created", {
            "cache_id": cache_id,
            "agent_id": agent_id,
            "namespace": namespace,
            "key": key,
            "value": value,
        })
        return cache_id

    def get(
        self,
        agent_id: str,
        key: str,
        namespace: str = "default",
    ) -> Optional[Any]:
        """Retrieve a cached value. Returns None if expired or missing."""
        self._total_gets += 1

        if not agent_id or not key:
            self._total_misses += 1
            return None

        lk = self._make_lookup_key(agent_id, namespace, key)
        eid = self._lookup.get(lk)
        if not eid or eid not in self._entries:
            self._total_misses += 1
            logger.debug("cache_miss", agent_id=agent_id, namespace=namespace, key=key)
            return None

        entry = self._entries[eid]

        # Check expiration
        if self._is_expired(entry):
            # Remove expired entry
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_misses += 1
            self._total_expirations += 1
            logger.debug(
                "cache_expired_on_access", agent_id=agent_id,
                namespace=namespace, key=key,
            )
            return None

        self._total_hits += 1
        logger.debug("cache_hit", agent_id=agent_id, namespace=namespace, key=key)
        return entry.value

    def delete(
        self,
        agent_id: str,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """Delete a cached entry. Returns True if it existed."""
        if not agent_id or not key:
            return False

        lk = self._make_lookup_key(agent_id, namespace, key)
        eid = self._lookup.get(lk)
        if not eid or eid not in self._entries:
            return False

        entry = self._entries[eid]
        del self._entries[eid]
        del self._lookup[lk]
        self._total_deletes += 1
        logger.debug(
            "cache_deleted", agent_id=agent_id, namespace=namespace, key=key,
        )
        self._fire("cache_deleted", {
            "cache_id": eid,
            "agent_id": agent_id,
            "namespace": namespace,
            "key": key,
            "value": entry.value,
        })
        return True

    def has(
        self,
        agent_id: str,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """Check whether a non-expired entry exists."""
        if not agent_id or not key:
            return False

        lk = self._make_lookup_key(agent_id, namespace, key)
        eid = self._lookup.get(lk)
        if not eid or eid not in self._entries:
            return False

        entry = self._entries[eid]
        if self._is_expired(entry):
            # Lazily remove expired entry
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_expirations += 1
            return False

        return True

    # ------------------------------------------------------------------
    # Agent-level operations
    # ------------------------------------------------------------------

    def clear_agent(self, agent_id: str, namespace: Optional[str] = None) -> int:
        """Clear cached entries for an agent. Optionally filter by namespace.

        Returns count of entries removed.
        """
        if not agent_id:
            return 0

        to_remove: List[str] = []
        for eid, entry in self._entries.items():
            if entry.agent_id != agent_id:
                continue
            if namespace is not None and entry.namespace != namespace:
                continue
            to_remove.append(eid)

        for eid in to_remove:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.namespace, entry.key)
            self._lookup.pop(lk, None)
            del self._entries[eid]

        count = len(to_remove)
        if count:
            self._total_deletes += count
            logger.debug(
                "cache_agent_cleared", agent_id=agent_id,
                namespace=namespace, count=count,
            )
            self._fire("cache_agent_cleared", {
                "agent_id": agent_id,
                "namespace": namespace,
                "count": count,
            })
        return count

    def list_keys(self, agent_id: str, namespace: str = "default") -> List[str]:
        """List all non-expired cache keys for an agent in a namespace."""
        if not agent_id:
            return []

        now = time.time()
        keys: List[str] = []
        for entry in self._entries.values():
            if entry.agent_id == agent_id and entry.namespace == namespace:
                if now < entry.expires_at:
                    keys.append(entry.key)
        return sorted(keys)

    # ------------------------------------------------------------------
    # Compute-if-absent
    # ------------------------------------------------------------------

    def get_or_compute(
        self,
        agent_id: str,
        key: str,
        compute_fn: Callable[[], Any],
        namespace: str = "default",
        ttl: float = 3600,
    ) -> Any:
        """Return cached value or compute, cache, and return it."""
        cached = self.get(agent_id, key, namespace)
        if cached is not None:
            return cached

        value = compute_fn()
        self.put(agent_id, key, value, namespace=namespace, ttl=ttl)
        logger.debug(
            "cache_computed", agent_id=agent_id, namespace=namespace, key=key,
        )
        return value

    # ------------------------------------------------------------------
    # Cache stats
    # ------------------------------------------------------------------

    def get_cache_stats(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Return cache statistics, optionally filtered by agent_id."""
        if agent_id is not None:
            now = time.time()
            total = sum(
                1 for e in self._entries.values()
                if e.agent_id == agent_id and now < e.expires_at
            )
            return {
                "total_entries": total,
                "hits": self._total_hits,
                "misses": self._total_misses,
                "hit_rate": (
                    self._total_hits / (self._total_hits + self._total_misses)
                    if (self._total_hits + self._total_misses) > 0
                    else 0.0
                ),
            }

        total_access = self._total_hits + self._total_misses
        return {
            "total_entries": len(self._entries),
            "hits": self._total_hits,
            "misses": self._total_misses,
            "hit_rate": (
                self._total_hits / total_access if total_access > 0 else 0.0
            ),
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total_access = self._total_hits + self._total_misses
        return {
            "current_entries": len(self._entries),
            "total_puts": self._total_puts,
            "total_gets": self._total_gets,
            "total_deletes": self._total_deletes,
            "hits": self._total_hits,
            "misses": self._total_misses,
            "hit_rate": (
                self._total_hits / total_access if total_access > 0 else 0.0
            ),
            "total_evictions": self._total_evictions,
            "total_expirations": self._total_expirations,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._lookup.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_puts = 0
        self._total_gets = 0
        self._total_deletes = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._total_expirations = 0
        logger.debug("agent_cache_store_reset")
