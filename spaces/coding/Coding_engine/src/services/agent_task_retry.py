"""Agent Task Retry – managing task retry policies and attempt tracking.

Manages task retry policies and retry attempt tracking, including
backoff strategies, attempt recording, and retry eligibility checks.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskRetryState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskRetry:
    """Manages task retry policies and retry attempt tracking."""

    PREFIX = "atr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskRetryState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k].get("_seq", 0),
            ),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Policy operations
    # ------------------------------------------------------------------

    def register_policy(
        self,
        task_id: str,
        max_retries: int = 3,
        backoff: str = "fixed",
        metadata: dict = None,
    ) -> str:
        """Register a retry policy for a task.

        Returns the policy ID on success or ``""`` on failure.
        """
        if not task_id:
            return ""

        valid_backoffs = ("fixed", "linear", "exponential")
        if backoff not in valid_backoffs:
            backoff = "fixed"

        if max_retries < 0:
            max_retries = 0

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        policy_id = self._generate_id()
        self._state.entries[policy_id] = {
            "policy_id": policy_id,
            "task_id": task_id,
            "max_retries": max_retries,
            "backoff": backoff,
            "metadata": dict(metadata) if metadata else {},
            "attempts": [],
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._fire("policy_registered", {"policy_id": policy_id, "task_id": task_id})
        return policy_id

    def record_attempt(
        self,
        policy_id: str,
        success: bool = False,
        error: str = "",
    ) -> bool:
        """Record a retry attempt against a policy.

        Returns True if the attempt was recorded, False otherwise.
        """
        if not policy_id or policy_id not in self._state.entries:
            return False

        entry = self._state.entries[policy_id]
        now = time.time()
        attempt = {
            "timestamp": now,
            "success": success,
            "error": error,
            "attempt_number": entry["total_attempts"] + 1,
        }
        entry["attempts"].append(attempt)
        entry["total_attempts"] += 1
        if success:
            entry["successful_attempts"] += 1
        else:
            entry["failed_attempts"] += 1
        entry["updated_at"] = now

        self._fire(
            "attempt_recorded",
            {"policy_id": policy_id, "attempt": attempt, "success": success},
        )
        return True

    def get_policy(self, policy_id: str) -> Optional[dict]:
        """Return a policy dict or None if not found."""
        if not policy_id or policy_id not in self._state.entries:
            return None
        return dict(self._state.entries[policy_id])

    def get_policies(self, task_id: str = "", limit: int = 50) -> List[dict]:
        """Return policies, newest first. Optionally filter by task_id."""
        entries = list(self._state.entries.values())
        if task_id:
            entries = [e for e in entries if e["task_id"] == task_id]
        entries.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        if limit > 0:
            entries = entries[:limit]
        return [dict(e) for e in entries]

    def should_retry(self, policy_id: str) -> bool:
        """Check whether more retries are available for a policy."""
        if not policy_id or policy_id not in self._state.entries:
            return False
        entry = self._state.entries[policy_id]
        # If already succeeded, no need to retry
        if entry["successful_attempts"] > 0:
            return False
        return entry["failed_attempts"] < entry["max_retries"]

    def get_policy_count(self, task_id: str = "") -> int:
        """Return the number of policies, optionally filtered by task_id."""
        if not task_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["task_id"] == task_id)

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total_policies = len(self._state.entries)
        total_attempts = sum(e["total_attempts"] for e in self._state.entries.values())
        total_success = sum(
            e["successful_attempts"] for e in self._state.entries.values()
        )
        success_rate = (total_success / total_attempts) if total_attempts > 0 else 0.0
        return {
            "total_policies": total_policies,
            "total_attempts": total_attempts,
            "success_rate": success_rate,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskRetryState()
        self._fire("reset", {})
