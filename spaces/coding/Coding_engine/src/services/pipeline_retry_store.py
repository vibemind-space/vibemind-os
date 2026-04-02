"""Pipeline retry store.

Tracks pipeline retry attempts — recording retry policies and execution
attempts for failed pipelines. Supports configurable max retries, backoff
seconds, success-rate queries, and should-retry checks.
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class _RetryPolicy:
    """Retry policy for a named pipeline."""

    policy_id: str = ""
    pipeline_name: str = ""
    max_retries: int = 3
    backoff_seconds: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0


@dataclass
class _RetryAttempt:
    """A single retry attempt record."""

    attempt_id: str = ""
    pipeline_name: str = ""
    execution_id: str = ""
    success: bool = False
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Retry Store
# ---------------------------------------------------------------------------


class PipelineRetryStore:
    """Tracks retry policies and execution attempts for failed pipelines."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._policies: Dict[str, _RetryPolicy] = {}  # pipeline_name -> policy
        self._attempts: List[_RetryAttempt] = []
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_policies_set": 0,
            "total_attempts_recorded": 0,
            "total_attempts_cleared": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique ID with prefix 'prt-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"prt-{digest}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prune_attempts_if_needed(self) -> None:
        """Remove oldest attempts when at capacity."""
        if len(self._attempts) < self._max_entries:
            return
        remove_count = len(self._attempts) - self._max_entries + 1
        self._attempts = self._attempts[remove_count:]
        logger.debug("attempts_pruned: removed=%d", remove_count)

    def _policy_to_dict(self, p: _RetryPolicy) -> Dict:
        return {
            "policy_id": p.policy_id,
            "pipeline_name": p.pipeline_name,
            "max_retries": p.max_retries,
            "backoff_seconds": p.backoff_seconds,
            "metadata": dict(p.metadata),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    def _attempt_to_dict(self, a: _RetryAttempt) -> Dict:
        return {
            "attempt_id": a.attempt_id,
            "pipeline_name": a.pipeline_name,
            "execution_id": a.execution_id,
            "success": a.success,
            "error": a.error,
            "metadata": dict(a.metadata),
            "created_at": a.created_at,
        }

    # ------------------------------------------------------------------
    # Policies
    # ------------------------------------------------------------------

    def set_policy(
        self,
        pipeline_name: str,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Set retry policy for a pipeline.

        Returns policy_id (prefix 'prt-'). Updates if a policy already
        exists for the given pipeline_name.
        """
        with self._lock:
            if not pipeline_name:
                logger.warning("set_policy_invalid_name")
                return ""

            now = time.time()
            existing = self._policies.get(pipeline_name)

            if existing:
                existing.max_retries = max_retries
                existing.backoff_seconds = backoff_seconds
                existing.metadata = dict(metadata) if metadata else existing.metadata
                existing.updated_at = now
                self._stats["total_policies_set"] += 1
                logger.info(
                    "policy_updated: pipeline=%s policy_id=%s",
                    pipeline_name,
                    existing.policy_id,
                )
                self._fire("policy_updated", self._policy_to_dict(existing))
                return existing.policy_id

            policy_id = self._next_id(pipeline_name)
            policy = _RetryPolicy(
                policy_id=policy_id,
                pipeline_name=pipeline_name,
                max_retries=max_retries,
                backoff_seconds=backoff_seconds,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                updated_at=now,
                seq=self._seq,
            )
            self._policies[pipeline_name] = policy
            self._stats["total_policies_set"] += 1

            logger.info(
                "policy_created: pipeline=%s policy_id=%s",
                pipeline_name,
                policy_id,
            )
            self._fire("policy_created", self._policy_to_dict(policy))
            return policy_id

    def get_policy(self, pipeline_name: str) -> Optional[Dict]:
        """Get retry policy for a pipeline. Returns dict or None."""
        with self._lock:
            p = self._policies.get(pipeline_name)
            if not p:
                return None
            return self._policy_to_dict(p)

    # ------------------------------------------------------------------
    # Attempts
    # ------------------------------------------------------------------

    def record_attempt(
        self,
        pipeline_name: str,
        execution_id: str,
        success: bool,
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a retry attempt.

        Returns attempt_id (prefix 'prt-'), or '' on invalid input.
        """
        with self._lock:
            if not pipeline_name or not execution_id:
                logger.warning("record_attempt_invalid_args")
                return ""

            self._prune_attempts_if_needed()

            now = time.time()
            attempt_id = self._next_id(
                f"{pipeline_name}:{execution_id}"
            )

            attempt = _RetryAttempt(
                attempt_id=attempt_id,
                pipeline_name=pipeline_name,
                execution_id=execution_id,
                success=success,
                error=error,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                seq=self._seq,
            )
            self._attempts.append(attempt)
            self._stats["total_attempts_recorded"] += 1

            logger.info(
                "attempt_recorded: pipeline=%s execution=%s success=%s",
                pipeline_name,
                execution_id,
                success,
            )
            self._fire("attempt_recorded", self._attempt_to_dict(attempt))
            return attempt_id

    def get_attempts(
        self,
        pipeline_name: str,
        execution_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get attempts for a pipeline, optionally filtered by execution_id."""
        with self._lock:
            results = []
            for a in self._attempts:
                if a.pipeline_name != pipeline_name:
                    continue
                if execution_id is not None and a.execution_id != execution_id:
                    continue
                results.append(self._attempt_to_dict(a))
            results.sort(key=lambda d: d["created_at"])
            return results

    def get_retry_count(self, pipeline_name: str, execution_id: str) -> int:
        """Get number of retry attempts for a specific execution."""
        with self._lock:
            count = 0
            for a in self._attempts:
                if (
                    a.pipeline_name == pipeline_name
                    and a.execution_id == execution_id
                ):
                    count += 1
            return count

    def should_retry(self, pipeline_name: str, execution_id: str) -> bool:
        """Check if a retry should be attempted based on policy and attempts.

        Returns False if no policy exists, or if the attempt count has
        reached or exceeded max_retries.
        """
        with self._lock:
            policy = self._policies.get(pipeline_name)
            if not policy:
                return False

            count = 0
            for a in self._attempts:
                if (
                    a.pipeline_name == pipeline_name
                    and a.execution_id == execution_id
                ):
                    count += 1

            return count < policy.max_retries

    def get_success_rate(self, pipeline_name: str) -> float:
        """Get success rate (0.0-1.0) across all attempts for a pipeline."""
        with self._lock:
            total = 0
            successes = 0
            for a in self._attempts:
                if a.pipeline_name == pipeline_name:
                    total += 1
                    if a.success:
                        successes += 1
            if total == 0:
                return 0.0
            return successes / total

    def clear_attempts(self, pipeline_name: str) -> int:
        """Clear all attempts for a pipeline. Returns count removed."""
        with self._lock:
            before = len(self._attempts)
            self._attempts = [
                a for a in self._attempts
                if a.pipeline_name != pipeline_name
            ]
            removed = before - len(self._attempts)
            self._stats["total_attempts_cleared"] += removed

            if removed:
                logger.info(
                    "attempts_cleared: pipeline=%s count=%d",
                    pipeline_name,
                    removed,
                )
                self._fire("attempts_cleared", {
                    "pipeline_name": pipeline_name,
                    "count": removed,
                })
            return removed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all pipeline names with retry policies or attempts."""
        with self._lock:
            names = set(self._policies.keys())
            for a in self._attempts:
                names.add(a.pipeline_name)
            return sorted(names)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_policies": len(self._policies),
                "current_attempts": len(self._attempts),
                "max_entries": self._max_entries,
                "callbacks_registered": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._policies.clear()
            self._attempts.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
            logger.info("store_reset")
