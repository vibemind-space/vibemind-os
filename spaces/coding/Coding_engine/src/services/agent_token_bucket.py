"""Agent Token Bucket -- per-agent token bucket rate limiting.

Controls how many actions each agent can take per time window using
the token bucket algorithm.  Tokens refill at a configurable rate
and are consumed on each action.  Thread-safe with callback support.

Usage::

    svc = AgentTokenBucket()
    bid = svc.create_bucket("planner", capacity=10, refill_rate=2.0)
    result = svc.consume("planner", tokens=1)
    if result["success"]:
        # action allowed
        ...
    stats = svc.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class _BucketEntry:
    """State for a single agent's token bucket."""

    bucket_id: str
    agent_id: str
    capacity: float
    tokens: float
    refill_rate: float        # tokens per refill interval
    refill_interval: float    # seconds between refills
    last_refill: float
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0


# ======================================================================
# Service
# ======================================================================

class AgentTokenBucket:
    """Token bucket rate limiter keyed by agent.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._buckets: Dict[str, _BucketEntry] = {}  # agent_id -> entry
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._total_created: int = 0
        self._total_consumed: int = 0
        self._total_rejected: int = 0
        self._total_refills: int = 0
        self._total_deleted: int = 0

        logger.debug("agent_token_bucket.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, agent_id: str) -> str:
        """Generate a unique bucket ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{agent_id}-{time.time()}-{self._seq}"
        return "atb-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest buckets when max_entries is exceeded."""
        if len(self._buckets) <= self._max_entries:
            return
        sorted_agents = sorted(
            self._buckets.keys(),
            key=lambda a: self._buckets[a].created_at,
        )
        remove_count = len(self._buckets) - self._max_entries
        for agent_id in sorted_agents[:remove_count]:
            del self._buckets[agent_id]
            self._total_deleted += 1
        logger.debug("pruned %d bucket(s)", remove_count)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_bucket(
        self,
        agent_id: str,
        capacity: float,
        refill_rate: float,
        refill_interval: float = 1.0,
    ) -> str:
        """Create a token bucket for *agent_id*.

        Each agent can have one bucket.  Returns the bucket id
        (``atb-`` prefix) or ``""`` if a bucket already exists for the
        agent or the store is full.
        """
        if not agent_id:
            return ""
        with self._lock:
            if agent_id in self._buckets:
                logger.debug("bucket already exists for agent %s", agent_id)
                return ""
            self._prune_if_needed()
            if len(self._buckets) >= self._max_entries:
                logger.warning("max entries reached (%d)", self._max_entries)
                return ""
            now = time.time()
            bid = self._next_id(agent_id)
            entry = _BucketEntry(
                bucket_id=bid,
                agent_id=agent_id,
                capacity=capacity,
                tokens=capacity,
                refill_rate=refill_rate,
                refill_interval=refill_interval,
                last_refill=now,
                created_at=now,
            )
            self._buckets[agent_id] = entry
            self._total_created += 1
            logger.info(
                "created bucket %s for agent %s (cap=%.1f, rate=%.2f, interval=%.2f)",
                bid, agent_id, capacity, refill_rate, refill_interval,
            )
        self._fire("bucket_created", {"bucket_id": bid, "agent_id": agent_id})
        return bid

    def consume(self, agent_id: str, tokens: float = 1) -> Dict[str, Any]:
        """Try to consume *tokens* from the agent's bucket.

        Automatically refills before checking.  Returns a dict with
        ``success``, ``remaining``, and ``wait_time``.
        """
        with self._lock:
            entry = self._buckets.get(agent_id)
            if entry is None:
                return {"success": False, "remaining": 0, "wait_time": 0.0}
            self._refill_entry(entry)
            if entry.tokens >= tokens:
                entry.tokens -= tokens
                self._total_consumed += 1
                result = {
                    "success": True,
                    "remaining": int(entry.tokens),
                    "wait_time": 0.0,
                }
            else:
                self._total_rejected += 1
                deficit = tokens - entry.tokens
                rate_per_sec = entry.refill_rate / entry.refill_interval if entry.refill_interval > 0 else 0.0
                wait = deficit / rate_per_sec if rate_per_sec > 0 else 0.0
                result = {
                    "success": False,
                    "remaining": int(entry.tokens),
                    "wait_time": wait,
                }
                logger.debug(
                    "consume rejected for %s (need %.1f, have %.1f, wait %.2fs)",
                    agent_id, tokens, entry.tokens, wait,
                )
        if result["success"]:
            self._fire("tokens_consumed", {
                "agent_id": agent_id,
                "tokens": tokens,
                "remaining": result["remaining"],
            })
        return result

    def get_tokens(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return bucket info for *agent_id*, or ``None`` if no bucket."""
        with self._lock:
            entry = self._buckets.get(agent_id)
            if entry is None:
                return None
            self._refill_entry(entry)
            return {
                "agent_id": entry.agent_id,
                "tokens": int(entry.tokens),
                "capacity": entry.capacity,
                "refill_rate": entry.refill_rate,
            }

    def refill(self, agent_id: str) -> bool:
        """Manually refill tokens based on elapsed time since last refill.

        Returns ``False`` if no bucket exists for *agent_id*.
        """
        with self._lock:
            entry = self._buckets.get(agent_id)
            if entry is None:
                return False
            self._refill_entry(entry)
            self._total_refills += 1
            return True

    def set_capacity(self, agent_id: str, capacity: float) -> bool:
        """Update the capacity of an existing bucket.

        Clamps current tokens to the new capacity if needed.
        Returns ``False`` if the bucket is not found.
        """
        with self._lock:
            entry = self._buckets.get(agent_id)
            if entry is None:
                return False
            entry.capacity = capacity
            if entry.tokens > capacity:
                entry.tokens = capacity
            logger.info("capacity updated for %s to %.1f", agent_id, capacity)
        self._fire("capacity_changed", {"agent_id": agent_id, "capacity": capacity})
        return True

    def reset_bucket(self, agent_id: str) -> bool:
        """Reset a bucket to full capacity.

        Returns ``False`` if the bucket is not found.
        """
        with self._lock:
            entry = self._buckets.get(agent_id)
            if entry is None:
                return False
            entry.tokens = entry.capacity
            entry.last_refill = time.time()
            logger.info("bucket reset for %s", agent_id)
        self._fire("bucket_reset", {"agent_id": agent_id})
        return True

    def delete_bucket(self, agent_id: str) -> bool:
        """Delete a bucket.  Returns ``False`` if not found."""
        with self._lock:
            if agent_id not in self._buckets:
                return False
            bid = self._buckets[agent_id].bucket_id
            del self._buckets[agent_id]
            self._total_deleted += 1
            logger.info("deleted bucket %s for agent %s", bid, agent_id)
        self._fire("bucket_deleted", {"bucket_id": bid, "agent_id": agent_id})
        return True

    def list_buckets(self) -> List[str]:
        """Return a list of agent_ids that have buckets."""
        with self._lock:
            return list(self._buckets.keys())

    def get_bucket_count(self) -> int:
        """Return the number of active buckets."""
        with self._lock:
            return len(self._buckets)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback under *name*."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``False`` if
        the name was not registered."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, details)
            except Exception:
                logger.debug("callback error on action=%s", action, exc_info=True)

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        with self._lock:
            return {
                "total_buckets": len(self._buckets),
                "total_created": self._total_created,
                "total_consumed": self._total_consumed,
                "total_rejected": self._total_rejected,
                "total_refills": self._total_refills,
                "total_deleted": self._total_deleted,
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._buckets.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_created = 0
            self._total_consumed = 0
            self._total_rejected = 0
            self._total_refills = 0
            self._total_deleted = 0
            logger.info("agent token bucket reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refill_entry(self, entry: _BucketEntry) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.time()
        elapsed = now - entry.last_refill
        if elapsed <= 0:
            return
        intervals = elapsed / entry.refill_interval if entry.refill_interval > 0 else 0
        added = intervals * entry.refill_rate
        entry.tokens = min(entry.capacity, entry.tokens + added)
        entry.last_refill = now
