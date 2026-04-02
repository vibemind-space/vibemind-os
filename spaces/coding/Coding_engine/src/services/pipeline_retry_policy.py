"""Pipeline Retry Policy – defines retry strategies for pipeline steps.

Manages retry policies with configurable backoff strategies (exponential,
linear, fixed) and tracks attempt history per pipeline.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RetryPolicyEntry:
    policy_id: str
    pipeline_id: str
    max_retries: int
    backoff: str
    initial_delay: float
    created_at: float
    attempts: List[Dict[str, Any]] = field(default_factory=list)


class PipelineRetryPolicy:
    """Pipeline retry policy management."""

    def __init__(self) -> None:
        self._policies: Dict[str, RetryPolicyEntry] = {}
        self._pipeline_map: Dict[str, str] = {}  # pipeline_id -> policy_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"prp-{self._seq}-{id(self)}"
        return "prp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        while len(self._policies) > self._max_entries:
            oldest_id = min(
                self._policies,
                key=lambda pid: self._policies[pid].created_at,
            )
            entry = self._policies.pop(oldest_id)
            self._pipeline_map.pop(entry.pipeline_id, None)

    # ------------------------------------------------------------------
    # Policy CRUD
    # ------------------------------------------------------------------

    def create_policy(
        self,
        pipeline_id: str,
        max_retries: int = 3,
        backoff: str = "exponential",
        initial_delay: float = 1.0,
    ) -> str:
        policy_id = self._generate_id()
        now = time.time()

        entry = RetryPolicyEntry(
            policy_id=policy_id,
            pipeline_id=pipeline_id,
            max_retries=max_retries,
            backoff=backoff,
            initial_delay=initial_delay,
            created_at=now,
            attempts=[],
        )

        self._policies[policy_id] = entry
        self._pipeline_map[pipeline_id] = policy_id
        self._prune()
        self._fire("create_policy", {
            "policy_id": policy_id,
            "pipeline_id": pipeline_id,
        })
        return policy_id

    def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        entry = self._policies.get(policy_id)
        if entry is None:
            return None
        return {
            "policy_id": entry.policy_id,
            "pipeline_id": entry.pipeline_id,
            "max_retries": entry.max_retries,
            "backoff": entry.backoff,
            "initial_delay": entry.initial_delay,
            "created_at": entry.created_at,
            "attempts": list(entry.attempts),
        }

    def get_policy_for_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        policy_id = self._pipeline_map.get(pipeline_id)
        if policy_id is None:
            return None
        return self.get_policy(policy_id)

    def update_policy(
        self,
        policy_id: str,
        max_retries: Optional[int] = None,
        backoff: Optional[str] = None,
    ) -> bool:
        entry = self._policies.get(policy_id)
        if entry is None:
            return False
        if max_retries is not None:
            entry.max_retries = max_retries
        if backoff is not None:
            entry.backoff = backoff
        self._fire("update_policy", {"policy_id": policy_id})
        return True

    def remove_policy(self, policy_id: str) -> bool:
        entry = self._policies.pop(policy_id, None)
        if entry is None:
            return False
        self._pipeline_map.pop(entry.pipeline_id, None)
        self._fire("remove_policy", {"policy_id": policy_id})
        return True

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def should_retry(self, pipeline_id: str, attempt_number: int) -> bool:
        policy_id = self._pipeline_map.get(pipeline_id)
        if policy_id is None:
            return False
        entry = self._policies[policy_id]
        return attempt_number < entry.max_retries

    def get_delay(self, pipeline_id: str, attempt_number: int) -> float:
        policy_id = self._pipeline_map.get(pipeline_id)
        if policy_id is None:
            return 0.0
        entry = self._policies[policy_id]

        if entry.backoff == "exponential":
            return entry.initial_delay * (2 ** (attempt_number - 1))
        elif entry.backoff == "linear":
            return entry.initial_delay * attempt_number
        else:  # fixed
            return entry.initial_delay

    # ------------------------------------------------------------------
    # Attempt tracking
    # ------------------------------------------------------------------

    def record_attempt(self, pipeline_id: str, success: bool) -> Dict[str, Any]:
        policy_id = self._pipeline_map.get(pipeline_id)
        if policy_id is None:
            return {}
        entry = self._policies[policy_id]
        attempt_number = len(entry.attempts) + 1
        attempt_info: Dict[str, Any] = {
            "attempt_number": attempt_number,
            "success": success,
            "timestamp": time.time(),
            "delay": self.get_delay(pipeline_id, attempt_number),
        }
        entry.attempts.append(attempt_info)
        self._fire("record_attempt", {
            "pipeline_id": pipeline_id,
            "attempt": attempt_info,
        })
        return attempt_info

    def get_attempt_history(self, pipeline_id: str) -> List[Dict[str, Any]]:
        policy_id = self._pipeline_map.get(pipeline_id)
        if policy_id is None:
            return []
        entry = self._policies[policy_id]
        return list(entry.attempts)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        return list(self._pipeline_map.keys())

    def get_policy_count(self) -> int:
        return len(self._policies)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total_attempts = sum(len(e.attempts) for e in self._policies.values())
        return {
            "policy_count": len(self._policies),
            "pipeline_count": len(self._pipeline_map),
            "total_attempts": total_attempts,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._policies.clear()
        self._pipeline_map.clear()
        self._callbacks.clear()
        self._seq = 0
        self._max_entries = 10000
