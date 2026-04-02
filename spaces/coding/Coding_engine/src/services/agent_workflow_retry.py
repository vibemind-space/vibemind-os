"""Agent workflow retry.

Manages retry policies and tracking for agent workflow executions.
Supports configurable max retries, backoff seconds, and backoff multipliers
per policy, and tracks per-execution retry state.
"""

import hashlib
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowRetryState:
    """Internal state container for workflow retry tracking."""
    entries: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowRetry:
    """Manages retry policies and tracking for agent workflow executions."""

    PREFIX = "awr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowRetryState()
        self._policies: Dict[str, Dict[str, Any]] = {}
        self._retries: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}{uuid.uuid4()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries if we exceed MAX_ENTRIES."""
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = min(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            del self._state.entries[oldest_key]
            self._policies.pop(oldest_key, None)
            self._retries.pop(oldest_key, None)
            logger.debug("Pruned entry %s", oldest_key)

    # ------------------------------------------------------------------
    # Change notification
    # ------------------------------------------------------------------

    def _fire(self, event: str, data: Any = None) -> None:
        """Fire change callbacks."""
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback failed")
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s failed", cb_id)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a registered callback. Returns True if found."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def register_policy(
        self,
        name: str,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
    ) -> str:
        """Register a retry policy. Returns the policy ID."""
        if not name:
            return ""
        policy_id = self._generate_id()
        policy = {
            "policy_id": policy_id,
            "name": name,
            "max_retries": max_retries,
            "backoff_seconds": backoff_seconds,
            "backoff_multiplier": backoff_multiplier,
            "created_at": time.time(),
        }
        self._policies[policy_id] = policy
        self._state.entries[policy_id] = policy
        self._prune()
        self._fire("policy_registered", policy)
        logger.info("Registered policy %s: %s", policy_id, name)
        return policy_id

    # ------------------------------------------------------------------
    # Retry tracking
    # ------------------------------------------------------------------

    def start_retry(self, policy_id: str, agent_id: str, workflow_name: str) -> str:
        """Start tracking retries for a workflow execution. Returns retry ID."""
        if not policy_id or policy_id not in self._policies:
            return ""
        if not agent_id or not workflow_name:
            return ""
        retry_id = self._generate_id()
        retry = {
            "retry_id": retry_id,
            "policy_id": policy_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "attempt": 0,
            "status": "active",
            "errors": [],
            "created_at": time.time(),
        }
        self._retries[retry_id] = retry
        self._state.entries[retry_id] = retry
        self._prune()
        self._fire("retry_started", retry)
        logger.info("Started retry %s for agent %s workflow %s", retry_id, agent_id, workflow_name)
        return retry_id

    def record_attempt(self, retry_id: str, success: bool, error: str = "") -> dict:
        """Record an attempt. Returns status dict with next_backoff_seconds."""
        if retry_id not in self._retries:
            return {}
        retry = self._retries[retry_id]
        policy = self._policies.get(retry["policy_id"])
        if not policy:
            return {}

        retry["attempt"] += 1
        if error:
            retry["errors"].append(error)

        if success:
            retry["status"] = "succeeded"
            next_backoff = None
        elif retry["attempt"] >= policy["max_retries"]:
            retry["status"] = "exhausted"
            next_backoff = None
        else:
            # Calculate next backoff: backoff_seconds * (backoff_multiplier ** attempt_index)
            # attempt_index is 0-based for backoff calculation (current attempt - 1)
            next_backoff = policy["backoff_seconds"] * (
                policy["backoff_multiplier"] ** (retry["attempt"] - 1)
            )

        result = {
            "retry_id": retry_id,
            "attempt": retry["attempt"],
            "status": retry["status"],
            "next_backoff_seconds": next_backoff,
        }
        self._fire("attempt_recorded", result)
        logger.info("Recorded attempt %d for %s: %s", retry["attempt"], retry_id, retry["status"])
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_retry(self, retry_id: str) -> dict:
        """Get a retry record by ID."""
        retry = self._retries.get(retry_id)
        if retry is None:
            return {}
        return dict(retry)

    def get_retries(self, agent_id: str, status: str = "") -> list:
        """Get retries for an agent, optionally filtered by status."""
        results = []
        for retry in self._retries.values():
            if retry["agent_id"] != agent_id:
                continue
            if status and retry["status"] != status:
                continue
            results.append(dict(retry))
        return results

    def get_retry_count(self, agent_id: str = "", status: str = "") -> int:
        """Count retries, optionally filtered by agent_id and/or status."""
        count = 0
        for retry in self._retries.values():
            if agent_id and retry["agent_id"] != agent_id:
                continue
            if status and retry["status"] != status:
                continue
            count += 1
        return count

    # ------------------------------------------------------------------
    # Stats and reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics."""
        statuses = [r["status"] for r in self._retries.values()]
        return {
            "total_policies": len(self._policies),
            "total_retries": len(self._retries),
            "active_retries": statuses.count("active"),
            "succeeded": statuses.count("succeeded"),
            "exhausted": statuses.count("exhausted"),
        }

    def reset(self) -> None:
        """Clear all policies, retries, and state."""
        self._policies.clear()
        self._retries.clear()
        self._state = AgentWorkflowRetryState()
        self._callbacks.clear()
        self._on_change = None
        self._fire = lambda *a, **k: None  # suppress during reset
        logger.info("Reset all workflow retry state")
        # Restore _fire
        self._fire = AgentWorkflowRetry._fire.__get__(self, AgentWorkflowRetry)
