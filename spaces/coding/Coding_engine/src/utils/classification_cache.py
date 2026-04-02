"""
Classification Cache - Multi-tier caching for LLM-based classifications.

Provides a unified interface for all classification needs in the codebase,
with progressive fallback from fast pattern matching to LLM-based semantic
classification.

Used by:
- FixerAgent._categorize_error_type()
- BrowserConsoleAgent.from_overlay_text()
- ContinuousDebugAgent.humanize_error_message()
- Slicer domain/feature detection
- UIIntegrationAgent category mapping
- ChunkPlannerAgent domain keywords
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ClassificationSource(Enum):
    """Source of classification result."""

    LOCAL_CACHE = "local_cache"
    REDIS_CACHE = "redis_cache"
    PATTERN = "pattern"
    SUPERMEMORY = "supermemory"
    LLM = "llm"


@dataclass
class ClassificationResult:
    """Result of a classification operation."""

    category: str
    confidence: float  # 0.0 to 1.0
    source: ClassificationSource
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "source": self.source.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationResult":
        return cls(
            category=data["category"],
            confidence=data["confidence"],
            source=ClassificationSource(data["source"]),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class CacheEntry:
    """Entry in the local cache with TTL tracking."""

    result: ClassificationResult
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class ClassificationCache:
    """
    Multi-tier classification cache with LLM fallback.

    Features:
    - In-memory cache with TTL (Tier 1)
    - Optional Redis persistence (Tier 2)
    - Pattern-based fast path (Tier 3)
    - Optional Supermemory RAG (Tier 4)
    - LLM semantic fallback (Tier 5)

    Architecture:
    ```
    Tier 1: Local Dict Cache (< 1ms)
    Tier 2: Redis Cache (~ 5ms)  [Optional]
    Tier 3: Pattern Classifier (< 10ms)
    Tier 4: Supermemory RAG (~ 100ms)  [Optional]
    Tier 5: LLM Fallback (~ 500ms)
    ```

    Usage:
        cache = ClassificationCache(ttl_seconds=300)

        result = await cache.classify(
            key="error:123",
            content="Cannot find module 'foo'",
            pattern_classifier=my_pattern_fn,
            llm_classifier=my_llm_fn,
        )
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_entries: int = 1000,
        redis_url: Optional[str] = None,
        supermemory_tools: Optional[Any] = None,
        min_pattern_confidence: float = 0.8,
        enable_learning: bool = True,
    ):
        """
        Initialize ClassificationCache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 5 min)
            max_entries: Maximum local cache size before eviction
            redis_url: Optional Redis URL for persistent caching
            supermemory_tools: Optional SupermemoryTools instance for RAG
            min_pattern_confidence: Minimum confidence to accept pattern result
            enable_learning: Store successful LLM classifications for learning
        """
        self._local_cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._redis_url = redis_url
        self._redis = None
        self._supermemory = supermemory_tools
        self._min_pattern_confidence = min_pattern_confidence
        self._enable_learning = enable_learning
        self._stats = {
            "hits": 0,
            "misses": 0,
            "pattern_matches": 0,
            "llm_calls": 0,
            "supermemory_matches": 0,
        }
        self.logger = logger.bind(component="ClassificationCache")

    async def _init_redis(self) -> bool:
        """Lazy-initialize Redis connection."""
        if self._redis is not None:
            return True
        if not self._redis_url:
            return False

        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self.logger.debug("redis_connected", url=self._redis_url[:30] + "...")
            return True
        except ImportError:
            self.logger.warning("redis_not_installed", msg="pip install redis")
            return False
        except Exception as e:
            self.logger.debug("redis_connection_failed", error=str(e))
            return False

    def _generate_key(self, content: str, prefix: str = "cls") -> str:
        """Generate cache key from content hash."""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"{prefix}:{content_hash}"

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - entry.created_at) > self._ttl

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        if len(self._local_cache) <= self._max_entries:
            return

        # Remove expired entries first
        expired = [k for k, v in self._local_cache.items() if self._is_expired(v)]
        for key in expired:
            del self._local_cache[key]

        # If still over limit, remove least accessed
        if len(self._local_cache) > self._max_entries:
            sorted_entries = sorted(
                self._local_cache.items(),
                key=lambda x: (x[1].access_count, x[1].created_at),
            )
            for key, _ in sorted_entries[: len(sorted_entries) // 4]:
                del self._local_cache[key]

    async def get(self, key: str) -> Optional[ClassificationResult]:
        """
        Get cached classification result.

        Args:
            key: Cache key

        Returns:
            ClassificationResult if found and not expired, else None
        """
        # Tier 1: Local cache
        if key in self._local_cache:
            entry = self._local_cache[key]
            if not self._is_expired(entry):
                entry.access_count += 1
                self._stats["hits"] += 1
                return entry.result
            else:
                del self._local_cache[key]

        # Tier 2: Redis cache
        if await self._init_redis():
            try:
                cached = await self._redis.get(f"classification:{key}")
                if cached:
                    result = ClassificationResult.from_dict(json.loads(cached))
                    # Promote to local cache
                    self._local_cache[key] = CacheEntry(result=result)
                    self._stats["hits"] += 1
                    return result
            except Exception as e:
                self.logger.debug("redis_get_failed", error=str(e))

        self._stats["misses"] += 1
        return None

    async def set(
        self,
        key: str,
        result: ClassificationResult,
        persist: bool = True,
    ) -> None:
        """
        Store classification result in cache.

        Args:
            key: Cache key
            result: Classification result to store
            persist: Whether to persist to Redis
        """
        self._evict_if_needed()

        # Store in local cache
        self._local_cache[key] = CacheEntry(result=result)

        # Persist to Redis if enabled
        if persist and await self._init_redis():
            try:
                await self._redis.setex(
                    f"classification:{key}",
                    self._ttl,
                    json.dumps(result.to_dict()),
                )
            except Exception as e:
                self.logger.debug("redis_set_failed", error=str(e))

    async def classify(
        self,
        key: str,
        content: str,
        pattern_classifier: Callable[[str], ClassificationResult],
        llm_classifier: Callable[[str], Awaitable[ClassificationResult]],
        category_type: str = "general",
    ) -> ClassificationResult:
        """
        Classify content with multi-tier caching.

        Args:
            key: Cache key (use _generate_key for content-based keys)
            content: Content to classify
            pattern_classifier: Sync function for pattern-based classification
            llm_classifier: Async function for LLM-based classification
            category_type: Type of classification (for Supermemory queries)

        Returns:
            ClassificationResult from the fastest available source
        """
        # Tier 1 & 2: Check caches
        cached = await self.get(key)
        if cached:
            return cached

        # Tier 3: Pattern-based classification
        pattern_result = pattern_classifier(content)
        if pattern_result.confidence >= self._min_pattern_confidence:
            self._stats["pattern_matches"] += 1
            await self.set(key, pattern_result)
            self.logger.debug(
                "pattern_classification",
                category=pattern_result.category,
                confidence=pattern_result.confidence,
            )
            return pattern_result

        # Tier 4: Supermemory RAG (if available)
        if self._supermemory:
            try:
                similar = await self._search_supermemory(content, category_type)
                if similar and similar.confidence >= self._min_pattern_confidence:
                    self._stats["supermemory_matches"] += 1
                    await self.set(key, similar)
                    self.logger.debug(
                        "supermemory_classification",
                        category=similar.category,
                        confidence=similar.confidence,
                    )
                    return similar
            except Exception as e:
                self.logger.debug("supermemory_search_failed", error=str(e))

        # Tier 5: LLM fallback
        self._stats["llm_calls"] += 1
        self.logger.debug("llm_classification_start", content_length=len(content))

        try:
            llm_result = await llm_classifier(content)
        except Exception as e:
            self.logger.warning("llm_classification_failed", error=str(e))
            # Return unknown with low confidence
            llm_result = ClassificationResult(
                category="unknown",
                confidence=0.3,
                source=ClassificationSource.LLM,
                metadata={"error": str(e)},
            )

        # Store result for future use
        await self.set(key, llm_result)

        # Learn from successful classification
        if (
            self._enable_learning
            and self._supermemory
            and llm_result.confidence > 0.7
        ):
            await self._store_for_learning(content, llm_result, category_type)

        self.logger.debug(
            "llm_classification_complete",
            category=llm_result.category,
            confidence=llm_result.confidence,
        )

        return llm_result

    async def _search_supermemory(
        self,
        content: str,
        category_type: str,
    ) -> Optional[ClassificationResult]:
        """Search Supermemory for similar classifications."""
        try:
            results = await self._supermemory.search(
                query=content[:500],
                limit=3,
                filters={"category": f"classification:{category_type}"},
            )

            if results and len(results) > 0:
                best = results[0]
                if best.score > 0.85:
                    # Extract classification from stored memory
                    metadata = best.metadata or {}
                    return ClassificationResult(
                        category=metadata.get("classification", "unknown"),
                        confidence=best.score,
                        source=ClassificationSource.SUPERMEMORY,
                        metadata={
                            "memory_id": best.id,
                            "original_content": best.content[:200],
                        },
                    )
        except Exception as e:
            self.logger.debug("supermemory_search_error", error=str(e))

        return None

    async def _store_for_learning(
        self,
        content: str,
        result: ClassificationResult,
        category_type: str,
    ) -> None:
        """Store successful classification for future RAG retrieval."""
        try:
            await self._supermemory.add(
                content=content[:500],
                metadata={
                    "classification": result.category,
                    "confidence": result.confidence,
                    "category_type": category_type,
                },
                category=f"classification:{category_type}",
            )
            self.logger.debug(
                "classification_stored_for_learning",
                category=result.category,
                category_type=category_type,
            )
        except Exception as e:
            self.logger.debug("supermemory_store_failed", error=str(e))

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "cache_size": len(self._local_cache),
            "hit_rate": (
                self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            ),
        }

    async def clear(self) -> None:
        """Clear all caches."""
        self._local_cache.clear()
        if await self._init_redis():
            try:
                keys = await self._redis.keys("classification:*")
                if keys:
                    await self._redis.delete(*keys)
                self.logger.debug("cache_cleared", redis_keys=len(keys) if keys else 0)
            except Exception as e:
                self.logger.debug("redis_clear_failed", error=str(e))

    async def close(self) -> None:
        """Close connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self.logger.debug("redis_connection_closed")

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a specific cache entry.

        Args:
            key: Cache key to invalidate

        Returns:
            True if entry was found and removed
        """
        if key in self._local_cache:
            del self._local_cache[key]
            return True
        return False

    def invalidate_by_prefix(self, prefix: str) -> int:
        """
        Invalidate all cache entries with given prefix.

        Args:
            prefix: Key prefix to match

        Returns:
            Number of entries invalidated
        """
        keys_to_remove = [k for k in self._local_cache if k.startswith(prefix)]
        for key in keys_to_remove:
            del self._local_cache[key]
        return len(keys_to_remove)


# Global singleton for shared cache across agents
_global_cache: Optional[ClassificationCache] = None
_global_cache_lock = asyncio.Lock()


def get_classification_cache(
    ttl_seconds: int = 300,
    redis_url: Optional[str] = None,
    reset: bool = False,
) -> ClassificationCache:
    """
    Get or create global ClassificationCache singleton.

    Args:
        ttl_seconds: Cache TTL
        redis_url: Redis URL for persistence
        reset: Force create new instance (for testing)

    Returns:
        Shared ClassificationCache instance
    """
    global _global_cache

    if reset or _global_cache is None:
        redis_url = redis_url or os.environ.get("REDIS_URL")
        _global_cache = ClassificationCache(
            ttl_seconds=ttl_seconds,
            redis_url=redis_url,
        )
        logger.debug(
            "classification_cache_created",
            ttl=ttl_seconds,
            redis_enabled=redis_url is not None,
        )

    return _global_cache


async def get_classification_cache_async(
    ttl_seconds: int = 300,
    redis_url: Optional[str] = None,
    reset: bool = False,
) -> ClassificationCache:
    """
    Thread-safe async version of get_classification_cache.

    Args:
        ttl_seconds: Cache TTL
        redis_url: Redis URL for persistence
        reset: Force create new instance

    Returns:
        Shared ClassificationCache instance
    """
    global _global_cache

    async with _global_cache_lock:
        return get_classification_cache(ttl_seconds, redis_url, reset)
