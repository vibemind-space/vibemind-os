"""Pipeline retry handler.

Manages retry logic for failed pipeline operations with configurable
strategies, backoff policies, and dead-letter tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _RetryPolicy:
    """Retry policy configuration."""
    policy_id: str = ""
    name: str = ""
    max_retries: int = 3
    backoff_type: str = "exponential"  # fixed, linear, exponential
    base_delay: float = 1.0
    max_delay: float = 60.0
    retry_on: List[str] = field(default_factory=list)  # error types to retry
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class _RetryRecord:
    """A tracked retry operation."""
    record_id: str = ""
    operation: str = ""
    policy_id: str = ""
    status: str = "pending"  # pending, retrying, succeeded, exhausted, cancelled
    attempt: int = 0
    max_retries: int = 3
    last_error: str = ""
    errors: List[str] = field(default_factory=list)
    next_retry_at: float = 0.0
    created_at: float = 0.0
    completed_at: float = 0.0
    source: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class PipelineRetryHandler:
    """Manages retry logic for pipeline operations."""

    BACKOFF_TYPES = ("fixed", "linear", "exponential")
    RECORD_STATUSES = ("pending", "retrying", "succeeded", "exhausted", "cancelled")

    def __init__(self, max_policies: int = 1000, max_records: int = 50000):
        self._max_policies = max_policies
        self._max_records = max_records
        self._policies: Dict[str, _RetryPolicy] = {}
        self._records: Dict[str, _RetryRecord] = {}
        self._dead_letter: List[Dict] = []
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_records_created": 0,
            "total_retries_attempted": 0,
            "total_succeeded": 0,
            "total_exhausted": 0,
            "total_cancelled": 0,
        }

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def create_policy(self, name: str, max_retries: int = 3,
                      backoff_type: str = "exponential",
                      base_delay: float = 1.0, max_delay: float = 60.0,
                      retry_on: Optional[List[str]] = None,
                      tags: Optional[List[str]] = None) -> str:
        """Create a retry policy."""
        if not name:
            return ""
        if backoff_type not in self.BACKOFF_TYPES:
            return ""
        if max_retries < 1 or base_delay <= 0 or max_delay <= 0:
            return ""
        if len(self._policies) >= self._max_policies:
            return ""

        pid = "rpol-" + hashlib.md5(
            f"{name}{time.time()}{len(self._policies)}".encode()
        ).hexdigest()[:12]

        self._policies[pid] = _RetryPolicy(
            policy_id=pid,
            name=name,
            max_retries=max_retries,
            backoff_type=backoff_type,
            base_delay=base_delay,
            max_delay=max_delay,
            retry_on=retry_on or [],
            tags=tags or [],
            created_at=time.time(),
        )
        return pid

    def get_policy(self, policy_id: str) -> Optional[Dict]:
        """Get policy info."""
        p = self._policies.get(policy_id)
        if not p:
            return None
        return {
            "policy_id": p.policy_id,
            "name": p.name,
            "max_retries": p.max_retries,
            "backoff_type": p.backoff_type,
            "base_delay": p.base_delay,
            "max_delay": p.max_delay,
            "retry_on": list(p.retry_on),
            "tags": list(p.tags),
        }

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy."""
        if policy_id not in self._policies:
            return False
        del self._policies[policy_id]
        return True

    def list_policies(self, tag: Optional[str] = None) -> List[Dict]:
        """List all policies."""
        result = []
        for p in self._policies.values():
            if tag and tag not in p.tags:
                continue
            result.append({
                "policy_id": p.policy_id,
                "name": p.name,
                "max_retries": p.max_retries,
                "backoff_type": p.backoff_type,
            })
        return result

    # ------------------------------------------------------------------
    # Retry records
    # ------------------------------------------------------------------

    def create_record(self, operation: str, policy_id: str = "",
                      source: str = "", tags: Optional[List[str]] = None,
                      metadata: Optional[Dict] = None,
                      max_retries: int = 3) -> str:
        """Create a retry record for an operation."""
        if not operation:
            return ""
        if len(self._records) >= self._max_records:
            self._prune_records()

        # Use policy settings if available
        actual_max = max_retries
        if policy_id and policy_id in self._policies:
            actual_max = self._policies[policy_id].max_retries

        rid = "rr-" + hashlib.md5(
            f"{operation}{time.time()}{len(self._records)}".encode()
        ).hexdigest()[:12]

        self._records[rid] = _RetryRecord(
            record_id=rid,
            operation=operation,
            policy_id=policy_id,
            max_retries=actual_max,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._stats["total_records_created"] += 1
        self._fire("record_created", {"record_id": rid, "operation": operation})
        return rid

    def get_record(self, record_id: str) -> Optional[Dict]:
        """Get record info."""
        r = self._records.get(record_id)
        if not r:
            return None
        return {
            "record_id": r.record_id,
            "operation": r.operation,
            "policy_id": r.policy_id,
            "status": r.status,
            "attempt": r.attempt,
            "max_retries": r.max_retries,
            "last_error": r.last_error,
            "errors": list(r.errors),
            "next_retry_at": r.next_retry_at,
            "source": r.source,
            "tags": list(r.tags),
            "created_at": r.created_at,
            "completed_at": r.completed_at,
        }

    def remove_record(self, record_id: str) -> bool:
        """Remove a record."""
        if record_id not in self._records:
            return False
        del self._records[record_id]
        return True

    # ------------------------------------------------------------------
    # Retry operations
    # ------------------------------------------------------------------

    def record_attempt(self, record_id: str, error: str = "") -> bool:
        """Record a retry attempt with an error."""
        r = self._records.get(record_id)
        if not r:
            return False
        if r.status in ("succeeded", "exhausted", "cancelled"):
            return False

        r.attempt += 1
        r.status = "retrying"
        if error:
            r.last_error = error
            r.errors.append(error)
        self._stats["total_retries_attempted"] += 1

        # Calculate next retry delay
        delay = self._calculate_delay(r)
        r.next_retry_at = time.time() + delay

        # Check if exhausted
        if r.attempt >= r.max_retries:
            r.status = "exhausted"
            r.completed_at = time.time()
            self._stats["total_exhausted"] += 1
            self._add_to_dead_letter(r)
            self._fire("retries_exhausted", {
                "record_id": record_id, "operation": r.operation,
                "attempts": r.attempt,
            })
        else:
            self._fire("retry_attempted", {
                "record_id": record_id, "attempt": r.attempt,
                "next_retry_at": r.next_retry_at,
            })

        return True

    def mark_succeeded(self, record_id: str) -> bool:
        """Mark a retry record as succeeded."""
        r = self._records.get(record_id)
        if not r:
            return False
        if r.status in ("succeeded", "exhausted", "cancelled"):
            return False
        r.status = "succeeded"
        r.completed_at = time.time()
        self._stats["total_succeeded"] += 1
        self._fire("retry_succeeded", {
            "record_id": record_id, "operation": r.operation,
            "attempts": r.attempt,
        })
        return True

    def cancel_record(self, record_id: str) -> bool:
        """Cancel a retry record."""
        r = self._records.get(record_id)
        if not r:
            return False
        if r.status in ("succeeded", "exhausted", "cancelled"):
            return False
        r.status = "cancelled"
        r.completed_at = time.time()
        self._stats["total_cancelled"] += 1
        return True

    def get_ready_retries(self) -> List[Dict]:
        """Get records that are ready for retry (next_retry_at <= now)."""
        now = time.time()
        result = []
        for r in self._records.values():
            if r.status != "retrying":
                continue
            if r.next_retry_at <= now:
                result.append({
                    "record_id": r.record_id,
                    "operation": r.operation,
                    "attempt": r.attempt,
                    "max_retries": r.max_retries,
                    "source": r.source,
                })
        return result

    # ------------------------------------------------------------------
    # Dead letter
    # ------------------------------------------------------------------

    def get_dead_letter_queue(self, limit: int = 50) -> List[Dict]:
        """Get entries from the dead letter queue."""
        return list(self._dead_letter[-limit:])

    def clear_dead_letter(self) -> int:
        """Clear the dead letter queue. Returns count cleared."""
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count

    def _add_to_dead_letter(self, r: _RetryRecord) -> None:
        """Add exhausted record to dead letter queue."""
        self._dead_letter.append({
            "record_id": r.record_id,
            "operation": r.operation,
            "attempts": r.attempt,
            "last_error": r.last_error,
            "source": r.source,
            "exhausted_at": time.time(),
        })
        # Cap dead letter size
        if len(self._dead_letter) > 10000:
            self._dead_letter = self._dead_letter[-5000:]

    # ------------------------------------------------------------------
    # Delay calculation
    # ------------------------------------------------------------------

    def _calculate_delay(self, r: _RetryRecord) -> float:
        """Calculate delay for next retry based on policy."""
        policy = self._policies.get(r.policy_id) if r.policy_id else None
        if not policy:
            # Default exponential backoff
            return min(2.0 ** r.attempt, 60.0)

        attempt = r.attempt
        if policy.backoff_type == "fixed":
            delay = policy.base_delay
        elif policy.backoff_type == "linear":
            delay = policy.base_delay * attempt
        else:  # exponential
            delay = policy.base_delay * (2.0 ** (attempt - 1))

        return min(delay, policy.max_delay)

    def calculate_delay(self, record_id: str) -> float:
        """Get the calculated delay for a record (public API)."""
        r = self._records.get(record_id)
        if not r:
            return 0.0
        return self._calculate_delay(r)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_records(self, status: Optional[str] = None,
                     operation: Optional[str] = None,
                     source: Optional[str] = None) -> List[Dict]:
        """List retry records with filters."""
        result = []
        for r in self._records.values():
            if status and r.status != status:
                continue
            if operation and r.operation != operation:
                continue
            if source and r.source != source:
                continue
            result.append({
                "record_id": r.record_id,
                "operation": r.operation,
                "status": r.status,
                "attempt": r.attempt,
                "max_retries": r.max_retries,
                "source": r.source,
            })
        return result

    def get_retry_rate(self, operation: Optional[str] = None) -> Dict:
        """Get retry success/failure rate."""
        total = 0
        succeeded = 0
        exhausted = 0
        for r in self._records.values():
            if operation and r.operation != operation:
                continue
            if r.status in ("succeeded", "exhausted"):
                total += 1
                if r.status == "succeeded":
                    succeeded += 1
                else:
                    exhausted += 1

        if total == 0:
            return {"total": 0, "succeeded": 0, "exhausted": 0,
                    "success_rate": 0.0}
        return {
            "total": total,
            "succeeded": succeeded,
            "exhausted": exhausted,
            "success_rate": round(succeeded / total * 100.0, 1),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_records(self) -> None:
        """Remove oldest completed records."""
        completed = [(k, v) for k, v in self._records.items()
                     if v.status in ("succeeded", "exhausted", "cancelled")]
        completed.sort(key=lambda x: x[1].created_at)
        to_remove = len(completed) // 2
        for k, _ in completed[:to_remove]:
            del self._records[k]

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
            "current_records": len(self._records),
            "pending_records": sum(
                1 for r in self._records.values() if r.status == "pending"
            ),
            "retrying_records": sum(
                1 for r in self._records.values() if r.status == "retrying"
            ),
            "current_policies": len(self._policies),
            "dead_letter_size": len(self._dead_letter),
        }

    def reset(self) -> None:
        self._policies.clear()
        self._records.clear()
        self._dead_letter.clear()
        self._stats = {k: 0 for k in self._stats}
