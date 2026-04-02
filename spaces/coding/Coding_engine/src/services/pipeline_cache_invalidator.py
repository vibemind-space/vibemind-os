"""Pipeline cache invalidator.

Manages cache invalidation for pipeline data with TTL-based expiration,
bulk invalidation by pipeline, and change notification callbacks.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _CacheRecord:
    """A registered cache entry."""
    cache_id: str = ""
    pipeline_id: str = ""
    cache_name: str = ""
    ttl_seconds: float = 300.0
    created_at: float = 0.0
    expires_at: float = 0.0
    invalidated: bool = False
    invalidated_at: float = 0.0
    seq: int = 0


class PipelineCacheInvalidator:
    """Manages cache invalidation for pipeline data."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._caches: Dict[str, _CacheRecord] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_invalidated": 0,
            "total_expired": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # ID Generation
    # ------------------------------------------------------------------

    def _make_id(self, pipeline_id: str, cache_name: str) -> str:
        raw = hashlib.sha256(
            f"{pipeline_id}{cache_name}{self._seq}".encode()
        ).hexdigest()[:12]
        return f"pci-{raw}"

    def _cache_key(self, pipeline_id: str, cache_name: str) -> str:
        return f"{pipeline_id}:{cache_name}"

    # ------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------

    def register_cache(self, pipeline_id: str, cache_name: str,
                       ttl_seconds: float = 300.0) -> str:
        """Register a cache for a pipeline. Returns cache_id."""
        if not pipeline_id or not cache_name:
            return ""

        key = self._cache_key(pipeline_id, cache_name)

        # Prune if at capacity and this is a new entry
        if key not in self._caches and len(self._caches) >= self._max_entries:
            self._prune_oldest()

        now = time.time()
        self._seq += 1
        cache_id = self._make_id(pipeline_id, cache_name)

        record = _CacheRecord(
            cache_id=cache_id,
            pipeline_id=pipeline_id,
            cache_name=cache_name,
            ttl_seconds=ttl_seconds,
            created_at=now,
            expires_at=now + ttl_seconds,
            invalidated=False,
            invalidated_at=0.0,
            seq=self._seq,
        )
        self._caches[key] = record
        self._stats["total_registered"] += 1

        logger.info("cache_registered", cache_id=cache_id,
                     pipeline_id=pipeline_id, cache_name=cache_name)
        self._fire("cache_registered", self._record_to_dict(record))
        return cache_id

    def invalidate(self, pipeline_id: str, cache_name: str) -> bool:
        """Invalidate a specific cache. Returns True if found and invalidated."""
        key = self._cache_key(pipeline_id, cache_name)
        record = self._caches.get(key)
        if not record:
            return False
        if record.invalidated:
            return False

        record.invalidated = True
        record.invalidated_at = time.time()
        self._stats["total_invalidated"] += 1

        logger.info("cache_invalidated", cache_id=record.cache_id,
                     pipeline_id=pipeline_id, cache_name=cache_name)
        self._fire("cache_invalidated", self._record_to_dict(record))
        return True

    def is_valid(self, pipeline_id: str, cache_name: str) -> bool:
        """Check if a cache is still valid (not invalidated and not expired)."""
        self._stats["total_lookups"] += 1
        key = self._cache_key(pipeline_id, cache_name)
        record = self._caches.get(key)
        if not record:
            return False
        if record.invalidated:
            return False
        if time.time() > record.expires_at:
            self._stats["total_expired"] += 1
            return False
        return True

    def get_cache(self, pipeline_id: str, cache_name: str) -> Optional[Dict]:
        """Get cache info as a dict. Returns None if not found."""
        key = self._cache_key(pipeline_id, cache_name)
        record = self._caches.get(key)
        if not record:
            return None
        return self._record_to_dict(record)

    def invalidate_all(self, pipeline_id: str) -> int:
        """Invalidate all caches for a pipeline. Returns count invalidated."""
        count = 0
        now = time.time()
        for record in self._caches.values():
            if record.pipeline_id == pipeline_id and not record.invalidated:
                record.invalidated = True
                record.invalidated_at = now
                count += 1

        self._stats["total_invalidated"] += count
        if count > 0:
            logger.info("pipeline_caches_invalidated",
                        pipeline_id=pipeline_id, count=count)
            self._fire("pipeline_invalidated", {
                "pipeline_id": pipeline_id,
                "count": count,
            })
        return count

    def list_caches(self, pipeline_id: str = "") -> List[Dict]:
        """List caches, optionally filtered by pipeline_id."""
        result = []
        for record in self._caches.values():
            if pipeline_id and record.pipeline_id != pipeline_id:
                continue
            result.append(self._record_to_dict(record))
        result.sort(key=lambda x: -x["seq"])
        return result

    def get_cache_count(self) -> int:
        """Get total number of registered caches."""
        return len(self._caches)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_oldest(self) -> None:
        """Remove the oldest entry by seq to make room."""
        if not self._caches:
            return
        oldest_key = min(self._caches.keys(),
                         key=lambda k: self._caches[k].seq)
        del self._caches[oldest_key]

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

    def _fire(self, event: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        valid = sum(1 for r in self._caches.values()
                    if not r.invalidated and time.time() <= r.expires_at)
        return {
            **self._stats,
            "current_entries": len(self._caches),
            "valid_entries": valid,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._caches.clear()
        self._seq = 0
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_to_dict(self, record: _CacheRecord) -> Dict:
        return {
            "cache_id": record.cache_id,
            "pipeline_id": record.pipeline_id,
            "cache_name": record.cache_name,
            "ttl_seconds": record.ttl_seconds,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "invalidated": record.invalidated,
            "invalidated_at": record.invalidated_at,
            "seq": record.seq,
        }
