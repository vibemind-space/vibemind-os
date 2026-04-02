"""Agent Response Cache – caches agent responses to avoid redundant processing.

Stores responses keyed by agent+request hash so that identical requests
from the same agent are served from cache instead of being reprocessed.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CachedResponse:
    cache_id: str
    agent_id: str
    request_key: str
    response: Any
    ttl_seconds: float
    created_at: float
    expires_at: float
    seq: int = 0


class AgentResponseCache:
    """Caches agent responses to avoid redundant processing."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._cache: Dict[str, CachedResponse] = {}
        self._lookup: Dict[str, str] = {}  # "agent_id:request_key" -> cache_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # stats
        self._total_caches = 0
        self._total_gets = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_invalidations = 0
        self._total_expirations = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"arc-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"arc-{digest}"

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
    def _make_lookup_key(agent_id: str, request_key: str) -> str:
        return f"{agent_id}:{request_key}"

    def _is_expired(self, entry: CachedResponse) -> bool:
        if entry.expires_at == 0.0:
            return False
        return time.time() >= entry.expires_at

    def _prune_if_needed(self) -> None:
        if len(self._cache) < self._max_entries:
            return

        # Evict by oldest seq
        sorted_ids = sorted(
            self._cache.keys(),
            key=lambda cid: self._cache[cid].seq,
        )
        to_remove = len(self._cache) - self._max_entries + 1
        for cid in sorted_ids[:to_remove]:
            entry = self._cache[cid]
            lk = self._make_lookup_key(entry.agent_id, entry.request_key)
            self._lookup.pop(lk, None)
            del self._cache[cid]
            logger.debug("response_cache_evicted", cache_id=cid, agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def cache_response(
        self,
        agent_id: str,
        request_key: str,
        response: Any,
        ttl_seconds: float = 0.0,
    ) -> str:
        """Cache a response. Returns cache ID (arc-xxx).

        If ttl_seconds > 0, the entry will expire after that many seconds.
        If ttl_seconds <= 0, the entry does not expire.
        """
        lk = self._make_lookup_key(agent_id, request_key)
        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds > 0 else 0.0

        # Update existing entry
        existing_cid = self._lookup.get(lk)
        if existing_cid and existing_cid in self._cache:
            entry = self._cache[existing_cid]
            old_response = entry.response
            entry.response = response
            entry.ttl_seconds = ttl_seconds
            entry.created_at = now
            entry.expires_at = expires_at
            self._seq += 1
            entry.seq = self._seq
            self._total_caches += 1
            logger.debug(
                "response_cache_updated", agent_id=agent_id, request_key=request_key,
            )
            self._fire("cache_updated", {
                "cache_id": existing_cid,
                "agent_id": agent_id,
                "request_key": request_key,
                "old_response": old_response,
                "new_response": response,
            })
            return existing_cid

        # New entry
        self._prune_if_needed()
        cache_id = self._gen_id(f"{agent_id}-{request_key}")
        entry = CachedResponse(
            cache_id=cache_id,
            agent_id=agent_id,
            request_key=request_key,
            response=response,
            ttl_seconds=ttl_seconds,
            created_at=now,
            expires_at=expires_at,
            seq=self._seq,
        )
        self._cache[cache_id] = entry
        self._lookup[lk] = cache_id
        self._total_caches += 1
        logger.debug(
            "response_cached", agent_id=agent_id, request_key=request_key,
            cache_id=cache_id,
        )
        self._fire("response_cached", {
            "cache_id": cache_id,
            "agent_id": agent_id,
            "request_key": request_key,
            "response": response,
        })
        return cache_id

    def get_response(self, agent_id: str, request_key: str) -> Any:
        """Get cached response. Returns None if not found or expired."""
        self._total_gets += 1

        lk = self._make_lookup_key(agent_id, request_key)
        cid = self._lookup.get(lk)
        if not cid or cid not in self._cache:
            self._total_misses += 1
            logger.debug("response_cache_miss", agent_id=agent_id, request_key=request_key)
            return None

        entry = self._cache[cid]

        if self._is_expired(entry):
            self._lookup.pop(lk, None)
            del self._cache[cid]
            self._total_misses += 1
            self._total_expirations += 1
            logger.debug(
                "response_cache_expired", agent_id=agent_id, request_key=request_key,
            )
            return None

        self._total_hits += 1
        logger.debug("response_cache_hit", agent_id=agent_id, request_key=request_key)
        return entry.response

    def has_response(self, agent_id: str, request_key: str) -> bool:
        """Check if a cached response exists and is not expired."""
        lk = self._make_lookup_key(agent_id, request_key)
        cid = self._lookup.get(lk)
        if not cid or cid not in self._cache:
            return False

        entry = self._cache[cid]
        if self._is_expired(entry):
            self._lookup.pop(lk, None)
            del self._cache[cid]
            self._total_expirations += 1
            return False

        return True

    def invalidate(self, agent_id: str, request_key: str) -> bool:
        """Remove a cached response. Returns True if it existed."""
        lk = self._make_lookup_key(agent_id, request_key)
        cid = self._lookup.get(lk)
        if not cid or cid not in self._cache:
            return False

        entry = self._cache[cid]
        del self._cache[cid]
        del self._lookup[lk]
        self._total_invalidations += 1
        logger.debug(
            "response_invalidated", agent_id=agent_id, request_key=request_key,
        )
        self._fire("response_invalidated", {
            "cache_id": cid,
            "agent_id": agent_id,
            "request_key": request_key,
            "response": entry.response,
        })
        return True

    def invalidate_all(self, agent_id: str) -> int:
        """Clear all cached responses for an agent. Returns count removed."""
        to_remove: List[str] = []
        for cid, entry in self._cache.items():
            if entry.agent_id == agent_id:
                to_remove.append(cid)

        for cid in to_remove:
            entry = self._cache[cid]
            lk = self._make_lookup_key(entry.agent_id, entry.request_key)
            self._lookup.pop(lk, None)
            del self._cache[cid]

        count = len(to_remove)
        if count:
            self._total_invalidations += count
            logger.debug(
                "response_cache_agent_cleared", agent_id=agent_id, count=count,
            )
            self._fire("agent_cache_cleared", {
                "agent_id": agent_id,
                "count": count,
            })
        return count

    def get_cache_size(self, agent_id: str = "") -> int:
        """Return number of cached entries, optionally filtered by agent."""
        if agent_id:
            return sum(
                1 for e in self._cache.values() if e.agent_id == agent_id
            )
        return len(self._cache)

    def list_agents(self) -> List[str]:
        """Return list of agents that have cached responses."""
        agents = set()
        for entry in self._cache.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total_access = self._total_hits + self._total_misses
        return {
            "current_entries": len(self._cache),
            "total_caches": self._total_caches,
            "total_gets": self._total_gets,
            "total_invalidations": self._total_invalidations,
            "hits": self._total_hits,
            "misses": self._total_misses,
            "hit_rate": (
                self._total_hits / total_access if total_access > 0 else 0.0
            ),
            "total_expirations": self._total_expirations,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._cache.clear()
        self._lookup.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_caches = 0
        self._total_gets = 0
        self._total_hits = 0
        self._total_misses = 0
        self._total_invalidations = 0
        self._total_expirations = 0
        logger.debug("agent_response_cache_reset")
