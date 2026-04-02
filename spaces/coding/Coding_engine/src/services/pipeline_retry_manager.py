"""Pipeline retry manager.

Manages retry policies and tracks retry attempts for pipeline operations.
Supports exponential backoff, max attempts, and retry budgets.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _RetryPolicy:
    """A retry policy."""
    policy_id: str = ""
    name: str = ""
    max_attempts: int = 3
    base_delay_ms: float = 1000.0
    max_delay_ms: float = 60000.0
    backoff_multiplier: float = 2.0
    retryable_errors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: str = "active"  # active, disabled
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _RetryAttempt:
    """A single retry attempt."""
    attempt_id: str = ""
    policy_id: str = ""
    operation: str = ""
    attempt_number: int = 0
    error: str = ""
    delay_ms: float = 0.0
    status: str = "pending"  # pending, succeeded, failed, exhausted
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class PipelineRetryManager:
    """Manages retry policies and attempts."""

    POLICY_STATUSES = ("active", "disabled")
    ATTEMPT_STATUSES = ("pending", "succeeded", "failed", "exhausted")

    def __init__(self, max_policies: int = 5000,
                 max_attempts: int = 500000):
        self._max_policies = max_policies
        self._max_attempts = max_attempts
        self._policies: Dict[str, _RetryPolicy] = {}
        self._attempts: Dict[str, _RetryAttempt] = {}
        self._pol_seq = 0
        self._att_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_policies_created": 0,
            "total_attempts": 0,
            "total_succeeded": 0,
            "total_exhausted": 0,
        }

    # ------------------------------------------------------------------
    # Policies
    # ------------------------------------------------------------------

    def create_policy(self, name: str, max_attempts: int = 3,
                      base_delay_ms: float = 1000.0,
                      max_delay_ms: float = 60000.0,
                      backoff_multiplier: float = 2.0,
                      retryable_errors: Optional[List[str]] = None,
                      tags: Optional[List[str]] = None,
                      metadata: Optional[Dict] = None) -> str:
        if not name or not name.strip():
            return ""
        if max_attempts < 1:
            return ""
        if len(self._policies) >= self._max_policies:
            return ""

        self._pol_seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._pol_seq}-{len(self._policies)}"
        pid = "rpol-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._policies[pid] = _RetryPolicy(
            policy_id=pid,
            name=name,
            max_attempts=max_attempts,
            base_delay_ms=base_delay_ms,
            max_delay_ms=max_delay_ms,
            backoff_multiplier=backoff_multiplier,
            retryable_errors=list(retryable_errors or []),
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            status="active",
            created_at=now,
            seq=self._pol_seq,
        )
        self._stats["total_policies_created"] += 1
        self._fire("policy_created", {"policy_id": pid, "name": name})
        return pid

    def get_policy(self, policy_id: str) -> Optional[Dict]:
        p = self._policies.get(policy_id)
        if not p:
            return None
        return {
            "policy_id": p.policy_id, "name": p.name,
            "max_attempts": p.max_attempts,
            "base_delay_ms": p.base_delay_ms,
            "max_delay_ms": p.max_delay_ms,
            "backoff_multiplier": p.backoff_multiplier,
            "retryable_errors": list(p.retryable_errors),
            "tags": list(p.tags), "metadata": dict(p.metadata),
            "status": p.status, "created_at": p.created_at,
        }

    def remove_policy(self, policy_id: str) -> bool:
        if policy_id not in self._policies:
            return False
        del self._policies[policy_id]
        return True

    def disable_policy(self, policy_id: str) -> bool:
        p = self._policies.get(policy_id)
        if not p or p.status == "disabled":
            return False
        p.status = "disabled"
        return True

    def enable_policy(self, policy_id: str) -> bool:
        p = self._policies.get(policy_id)
        if not p or p.status == "active":
            return False
        p.status = "active"
        return True

    # ------------------------------------------------------------------
    # Retry attempts
    # ------------------------------------------------------------------

    def record_attempt(self, policy_id: str, operation: str,
                       attempt_number: int, error: str = "",
                       status: str = "pending",
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> str:
        if not policy_id or not operation:
            return ""
        p = self._policies.get(policy_id)
        if not p:
            return ""
        if status not in self.ATTEMPT_STATUSES:
            return ""
        if len(self._attempts) >= self._max_attempts:
            return ""

        # Calculate delay
        delay = min(
            p.base_delay_ms * (p.backoff_multiplier ** (attempt_number - 1)),
            p.max_delay_ms,
        )

        self._att_seq += 1
        now = time.time()
        raw = f"{policy_id}-{operation}-{now}-{self._att_seq}-{len(self._attempts)}"
        aid = "ratt-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._attempts[aid] = _RetryAttempt(
            attempt_id=aid,
            policy_id=policy_id,
            operation=operation,
            attempt_number=attempt_number,
            error=error,
            delay_ms=delay,
            status=status,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=now,
            seq=self._att_seq,
        )
        self._stats["total_attempts"] += 1
        if status == "succeeded":
            self._stats["total_succeeded"] += 1
        elif status == "exhausted":
            self._stats["total_exhausted"] += 1
        self._fire("attempt_recorded", {
            "attempt_id": aid, "policy_id": policy_id,
            "operation": operation, "status": status,
        })
        return aid

    def mark_succeeded(self, attempt_id: str) -> bool:
        a = self._attempts.get(attempt_id)
        if not a or a.status != "pending":
            return False
        a.status = "succeeded"
        self._stats["total_succeeded"] += 1
        return True

    def mark_failed(self, attempt_id: str) -> bool:
        a = self._attempts.get(attempt_id)
        if not a or a.status != "pending":
            return False
        a.status = "failed"
        return True

    def mark_exhausted(self, attempt_id: str) -> bool:
        a = self._attempts.get(attempt_id)
        if not a or a.status != "pending":
            return False
        a.status = "exhausted"
        self._stats["total_exhausted"] += 1
        return True

    def get_attempt(self, attempt_id: str) -> Optional[Dict]:
        a = self._attempts.get(attempt_id)
        if not a:
            return None
        return {
            "attempt_id": a.attempt_id,
            "policy_id": a.policy_id,
            "operation": a.operation,
            "attempt_number": a.attempt_number,
            "error": a.error, "delay_ms": a.delay_ms,
            "status": a.status, "tags": list(a.tags),
            "metadata": dict(a.metadata),
            "created_at": a.created_at,
        }

    def remove_attempt(self, attempt_id: str) -> bool:
        if attempt_id not in self._attempts:
            return False
        del self._attempts[attempt_id]
        return True

    def calculate_delay(self, policy_id: str,
                        attempt_number: int) -> float:
        """Calculate delay for a given attempt number."""
        p = self._policies.get(policy_id)
        if not p:
            return 0.0
        return min(
            p.base_delay_ms * (p.backoff_multiplier ** (attempt_number - 1)),
            p.max_delay_ms,
        )

    def should_retry(self, policy_id: str, attempt_number: int,
                     error: str = "") -> bool:
        """Determine if a retry should happen."""
        p = self._policies.get(policy_id)
        if not p or p.status != "active":
            return False
        if attempt_number >= p.max_attempts:
            return False
        if p.retryable_errors and error:
            return any(e in error for e in p.retryable_errors)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_operation_attempts(self, operation: str,
                                limit: int = 50) -> List[Dict]:
        results = []
        for a in self._attempts.values():
            if a.operation == operation:
                results.append(self.get_attempt(a.attempt_id))
        results.sort(key=lambda x: x["attempt_number"])
        return results[:limit]

    def search_attempts(self, policy_id: str = "",
                        operation: str = "",
                        status: str = "", tag: str = "",
                        limit: int = 100) -> List[Dict]:
        results = []
        for a in self._attempts.values():
            if policy_id and a.policy_id != policy_id:
                continue
            if operation and a.operation != operation:
                continue
            if status and a.status != status:
                continue
            if tag and tag not in a.tags:
                continue
            results.append(self.get_attempt(a.attempt_id))
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    def list_policies(self, status: str = "",
                      tag: str = "") -> List[Dict]:
        results = []
        for p in self._policies.values():
            if status and p.status != status:
                continue
            if tag and tag not in p.tags:
                continue
            results.append(self.get_policy(p.policy_id))
        results.sort(key=lambda x: x["created_at"])
        return results

    def get_retry_summary(self, policy_id: str = "") -> Dict:
        """Get retry statistics summary."""
        total = 0
        succeeded = 0
        failed = 0
        exhausted = 0
        for a in self._attempts.values():
            if policy_id and a.policy_id != policy_id:
                continue
            total += 1
            if a.status == "succeeded":
                succeeded += 1
            elif a.status == "failed":
                failed += 1
            elif a.status == "exhausted":
                exhausted += 1
        success_rate = (succeeded / total * 100.0) if total > 0 else 0.0
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "exhausted": exhausted,
            "success_rate": round(success_rate, 1),
        }

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

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_policies": len(self._policies),
            "current_attempts": len(self._attempts),
        }

    def reset(self) -> None:
        self._policies.clear()
        self._attempts.clear()
        self._pol_seq = 0
        self._att_seq = 0
        self._stats = {k: 0 for k in self._stats}
