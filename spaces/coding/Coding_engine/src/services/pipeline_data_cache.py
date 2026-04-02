"""Pipeline data cache — caches pipeline data for reuse.

Stores key-value data with optional TTL and pipeline scoping.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    """Internal state for PipelineDataCache."""
    cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataCache:
    """Caches pipeline data for reuse with optional TTL and pipeline scoping."""

    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = _State()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdc-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_key(self, pipeline_id: str, key: str) -> str:
        return f"{pipeline_id}::{key}"

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        if entry.get("ttl", 0) <= 0:
            return False
        return time.time() > entry["expiry"]

    def _prune_if_needed(self) -> None:
        if len(self._state.cache) >= self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.cache))
            del self._state.cache[oldest_key]
            logger.warning("cache_pruned", removed_key=oldest_key)

    # ------------------------------------------------------------------
    # Cache API
    # ------------------------------------------------------------------

    def cache_set(
        self,
        pipeline_id: str,
        key: str,
        value: Any,
        ttl_seconds: float = 0.0,
    ) -> str:
        """Store a value in the cache. Returns cache entry ID (pdc-xxx)."""
        self._prune_if_needed()

        entry_id = self._next_id()
        ck = self._cache_key(pipeline_id, key)

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "pipeline_id": pipeline_id,
            "key": key,
            "value": value,
            "ttl": ttl_seconds,
            "created_at": time.time(),
        }
        if ttl_seconds > 0:
            entry["expiry"] = time.time() + ttl_seconds

        self._state.cache[ck] = entry
        logger.info("cache_set", entry_id=entry_id,
                     pipeline_id=pipeline_id, key=key)
        self._fire("cache_set", {"entry_id": entry_id,
                                  "pipeline_id": pipeline_id, "key": key})
        return entry_id

    def cache_get(self, pipeline_id: str, key: str) -> Any:
        """Get a cached value. Return None if not found or expired."""
        ck = self._cache_key(pipeline_id, key)
        entry = self._state.cache.get(ck)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._state.cache[ck]
            return None
        return entry["value"]

    def cache_has(self, pipeline_id: str, key: str) -> bool:
        """Check if key exists and is not expired."""
        ck = self._cache_key(pipeline_id, key)
        entry = self._state.cache.get(ck)
        if entry is None:
            return False
        if self._is_expired(entry):
            del self._state.cache[ck]
            return False
        return True

    def cache_delete(self, pipeline_id: str, key: str) -> bool:
        """Delete a cached value."""
        ck = self._cache_key(pipeline_id, key)
        if ck in self._state.cache:
            del self._state.cache[ck]
            logger.info("cache_delete", pipeline_id=pipeline_id, key=key)
            self._fire("cache_delete", {"pipeline_id": pipeline_id, "key": key})
            return True
        return False

    def cache_clear(self, pipeline_id: str) -> int:
        """Clear all cache entries for a pipeline. Return count cleared."""
        to_remove = [
            ck for ck, entry in self._state.cache.items()
            if entry["pipeline_id"] == pipeline_id
        ]
        for ck in to_remove:
            del self._state.cache[ck]
        if to_remove:
            logger.info("cache_clear", pipeline_id=pipeline_id,
                         count=len(to_remove))
            self._fire("cache_clear", {"pipeline_id": pipeline_id,
                                        "count": len(to_remove)})
        return len(to_remove)

    def get_cache_size(self, pipeline_id: str = "") -> int:
        """Count cache entries. If pipeline_id given, count for that pipeline."""
        if not pipeline_id:
            return len(self._state.cache)
        return sum(
            1 for entry in self._state.cache.values()
            if entry["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> List[str]:
        """List all pipelines with cache entries."""
        pids = {entry["pipeline_id"] for entry in self._state.cache.values()}
        return sorted(pids)

    def list_keys(self, pipeline_id: str) -> List[str]:
        """List all keys for a pipeline."""
        return sorted(
            entry["key"] for entry in self._state.cache.values()
            if entry["pipeline_id"] == pipeline_id
        )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return summary statistics."""
        return {
            "total_entries": len(self._state.cache),
            "total_pipelines": len(self.list_pipelines()),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.cache.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("pipeline_data_cache_reset")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)
