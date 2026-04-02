"""Pipeline step cache service for caching pipeline step results to avoid re-execution."""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepCacheState:
    """State container for pipeline step cache."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class PipelineStepCache:
    """Cache pipeline step results to avoid re-execution with same inputs."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pstc-"

    def __init__(self) -> None:
        self._state = PipelineStepCacheState()
        self._callbacks: Dict[str, Callable] = {}

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash."""
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _fire(self, event: str, data: Any = None) -> None:
        """Fire callbacks for an event."""
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback %s failed: %s", cb_id, e)

    def on_change(self, callback: Callable) -> str:
        """Register a change callback. Returns callback ID."""
        cb_id = self._generate_id("callback")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        """Remove a registered callback. Returns True if found."""
        return self._callbacks.pop(cb_id, None) is not None

    def _prune(self) -> None:
        """Prune entries if over MAX_ENTRIES limit."""
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        # Remove oldest entries by cached_at timestamp
        sorted_keys = sorted(entries.keys(), key=lambda k: entries[k].get("cached_at", 0))
        to_remove = len(entries) - self.MAX_ENTRIES
        for key in sorted_keys[:to_remove]:
            del entries[key]
        logger.info("Pruned %d cache entries", to_remove)

    def _make_key(self, pipeline_id: str, step_name: str, input_hash: str) -> str:
        """Create a composite key for cache lookup."""
        return f"{pipeline_id}::{step_name}::{input_hash}"

    def _make_config_key(self, pipeline_id: str, step_name: str) -> str:
        """Create a config key for cache configuration."""
        return f"config::{pipeline_id}::{step_name}"

    def configure(self, pipeline_id: str, step_name: str, ttl_seconds: float = 300.0, max_size: int = 100) -> str:
        """Configure cache for a pipeline step. Returns cache_id."""
        cache_id = self._generate_id(f"config:{pipeline_id}:{step_name}")
        config_key = self._make_config_key(pipeline_id, step_name)
        self._state.entries[config_key] = {
            "cache_id": cache_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "ttl_seconds": ttl_seconds,
            "max_size": max_size,
            "hits": 0,
            "misses": 0,
            "type": "config",
        }
        self._fire("configured", {"cache_id": cache_id, "pipeline_id": pipeline_id, "step_name": step_name})
        logger.info("Configured cache %s for %s/%s (ttl=%.1fs, max_size=%d)",
                     cache_id, pipeline_id, step_name, ttl_seconds, max_size)
        return cache_id

    def _get_config(self, pipeline_id: str, step_name: str) -> Optional[dict]:
        """Get config for a pipeline step."""
        config_key = self._make_config_key(pipeline_id, step_name)
        config = self._state.entries.get(config_key)
        if config and config.get("type") == "config":
            return config
        return None

    def _count_step_entries(self, pipeline_id: str, step_name: str) -> int:
        """Count cached entries for a specific pipeline step."""
        prefix = f"{pipeline_id}::{step_name}::"
        return sum(1 for k, v in self._state.entries.items()
                   if k.startswith(prefix) and v.get("type") == "cached_result")

    def _enforce_max_size(self, pipeline_id: str, step_name: str, max_size: int) -> None:
        """Evict oldest entries if step exceeds max_size."""
        prefix = f"{pipeline_id}::{step_name}::"
        step_entries = [(k, v) for k, v in self._state.entries.items()
                        if k.startswith(prefix) and v.get("type") == "cached_result"]
        if len(step_entries) <= max_size:
            return
        step_entries.sort(key=lambda x: x[1].get("cached_at", 0))
        to_remove = len(step_entries) - max_size
        for key, _ in step_entries[:to_remove]:
            del self._state.entries[key]

    def cache_result(self, pipeline_id: str, step_name: str, input_hash: str, result: Any) -> bool:
        """Cache a pipeline step result. Returns True on success."""
        config = self._get_config(pipeline_id, step_name)
        ttl = config["ttl_seconds"] if config else 300.0
        max_size = config["max_size"] if config else 100

        key = self._make_key(pipeline_id, step_name, input_hash)
        self._state.entries[key] = {
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "input_hash": input_hash,
            "result": result,
            "cached_at": time.time(),
            "ttl_seconds": ttl,
            "type": "cached_result",
        }

        self._enforce_max_size(pipeline_id, step_name, max_size)
        self._prune()
        self._fire("cached", {"pipeline_id": pipeline_id, "step_name": step_name, "input_hash": input_hash})
        logger.debug("Cached result for %s/%s/%s", pipeline_id, step_name, input_hash)
        return True

    def get_cached(self, pipeline_id: str, step_name: str, input_hash: str) -> Any:
        """Get a cached result, respecting TTL. Returns None if not found or expired."""
        key = self._make_key(pipeline_id, step_name, input_hash)
        entry = self._state.entries.get(key)

        config = self._get_config(pipeline_id, step_name)

        if entry is None or entry.get("type") != "cached_result":
            if config:
                config["misses"] = config.get("misses", 0) + 1
            return None

        ttl = entry.get("ttl_seconds", 300.0)
        cached_at = entry.get("cached_at", 0)
        if time.time() - cached_at > ttl:
            # Expired
            del self._state.entries[key]
            if config:
                config["misses"] = config.get("misses", 0) + 1
            return None

        if config:
            config["hits"] = config.get("hits", 0) + 1
        return entry["result"]

    def has_cached(self, pipeline_id: str, step_name: str, input_hash: str) -> bool:
        """Check if a valid cached result exists."""
        key = self._make_key(pipeline_id, step_name, input_hash)
        entry = self._state.entries.get(key)
        if entry is None or entry.get("type") != "cached_result":
            return False
        ttl = entry.get("ttl_seconds", 300.0)
        cached_at = entry.get("cached_at", 0)
        if time.time() - cached_at > ttl:
            del self._state.entries[key]
            return False
        return True

    def invalidate(self, pipeline_id: str, step_name: str, input_hash: str = "") -> int:
        """Invalidate cached entries. Empty input_hash invalidates all for the step. Returns count."""
        count = 0
        if input_hash:
            key = self._make_key(pipeline_id, step_name, input_hash)
            if key in self._state.entries and self._state.entries[key].get("type") == "cached_result":
                del self._state.entries[key]
                count = 1
        else:
            prefix = f"{pipeline_id}::{step_name}::"
            keys_to_remove = [k for k, v in self._state.entries.items()
                              if k.startswith(prefix) and v.get("type") == "cached_result"]
            for key in keys_to_remove:
                del self._state.entries[key]
            count = len(keys_to_remove)

        if count > 0:
            self._fire("invalidated", {"pipeline_id": pipeline_id, "step_name": step_name, "count": count})
            logger.info("Invalidated %d entries for %s/%s", count, pipeline_id, step_name)
        return count

    def get_cache_info(self, cache_id: str) -> dict:
        """Get cache info by cache_id. Returns dict with hits, misses, size, hit_rate."""
        for key, entry in self._state.entries.items():
            if entry.get("type") == "config" and entry.get("cache_id") == cache_id:
                pipeline_id = entry["pipeline_id"]
                step_name = entry["step_name"]
                size = self._count_step_entries(pipeline_id, step_name)
                hits = entry.get("hits", 0)
                misses = entry.get("misses", 0)
                total = hits + misses
                hit_rate = hits / total if total > 0 else 0.0
                return {
                    "hits": hits,
                    "misses": misses,
                    "size": size,
                    "hit_rate": hit_rate,
                }
        return {"hits": 0, "misses": 0, "size": 0, "hit_rate": 0.0}

    def get_cache_count(self, pipeline_id: str = "") -> int:
        """Get count of cached entries, optionally filtered by pipeline_id."""
        if pipeline_id:
            prefix = f"{pipeline_id}::"
            return sum(1 for k, v in self._state.entries.items()
                       if k.startswith(prefix) and v.get("type") == "cached_result")
        return sum(1 for v in self._state.entries.values() if v.get("type") == "cached_result")

    def list_pipelines(self) -> list:
        """List unique pipeline IDs that have configurations."""
        pipelines = set()
        for entry in self._state.entries.values():
            if entry.get("type") == "config":
                pipelines.add(entry["pipeline_id"])
        return sorted(pipelines)

    def get_stats(self) -> dict:
        """Get overall cache statistics."""
        total_entries = sum(1 for v in self._state.entries.values() if v.get("type") == "cached_result")
        total_configs = sum(1 for v in self._state.entries.values() if v.get("type") == "config")
        total_hits = sum(v.get("hits", 0) for v in self._state.entries.values() if v.get("type") == "config")
        total_misses = sum(v.get("misses", 0) for v in self._state.entries.values() if v.get("type") == "config")
        total_requests = total_hits + total_misses
        return {
            "total_entries": total_entries,
            "total_configs": total_configs,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": total_hits / total_requests if total_requests > 0 else 0.0,
            "pipelines": len(self.list_pipelines()),
        }

    def reset(self) -> None:
        """Reset all cache state."""
        self._state = PipelineStepCacheState()
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("Pipeline step cache reset")
