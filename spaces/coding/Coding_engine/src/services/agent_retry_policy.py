"""Agent retry policy service.

Defines retry policies for agent operations - specifying how many retries,
backoff strategy, and which errors are retryable.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentRetryPolicy:
    """Manages retry policies for agent operations."""

    policies: Dict[str, Any] = field(default_factory=dict)
    _seq: int = 0

    def __post_init__(self) -> None:
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries: int = 10000
        self._stats: Dict[str, int] = {
            "policies_created": 0,
            "policies_removed": 0,
            "retries_checked": 0,
            "backoffs_computed": 0,
            "resets": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self) -> str:
        self._seq += 1
        raw = f"arp-{self._seq}"
        return "arp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        while len(self.policies) > self._max_entries:
            oldest_key = next(iter(self.policies))
            del self.policies[oldest_key]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        self._callbacks[name] = cb
        logger.info("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", name=name, action=action)

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    def create_policy(
        self,
        agent_id: str,
        operation: str,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        retryable_errors: Optional[List[str]] = None,
    ) -> str:
        """Create a retry policy. Returns policy ID (arp-xxx)."""
        if retryable_errors is None:
            retryable_errors = []
        policy_id = self._make_id()
        entry = {
            "policy_id": policy_id,
            "agent_id": agent_id,
            "operation": operation,
            "max_retries": max_retries,
            "backoff_factor": backoff_factor,
            "retryable_errors": retryable_errors,
        }
        self.policies[policy_id] = entry
        self._stats["policies_created"] += 1
        self._prune()
        logger.info("policy_created", policy_id=policy_id, agent_id=agent_id, operation=operation)
        self._fire("create_policy", {"policy_id": policy_id, "agent_id": agent_id})
        return policy_id

    def get_policy(self, agent_id: str, operation: str) -> Optional[dict]:
        """Get the policy for agent+operation."""
        for entry in self.policies.values():
            if entry["agent_id"] == agent_id and entry["operation"] == operation:
                return dict(entry)
        return None

    def should_retry(
        self, agent_id: str, operation: str, attempt: int, error_type: str = ""
    ) -> bool:
        """Check if should retry given current attempt number."""
        self._stats["retries_checked"] += 1
        policy = self.get_policy(agent_id, operation)
        if policy is None:
            return False
        if attempt >= policy["max_retries"]:
            return False
        if policy["retryable_errors"] and error_type not in policy["retryable_errors"]:
            return False
        return True

    def get_backoff(self, agent_id: str, operation: str, attempt: int) -> float:
        """Get backoff delay for given attempt. Formula: backoff_factor ** attempt."""
        self._stats["backoffs_computed"] += 1
        policy = self.get_policy(agent_id, operation)
        if policy is None:
            return 0.0
        return policy["backoff_factor"] ** attempt

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID."""
        if policy_id in self.policies:
            entry = self.policies.pop(policy_id)
            self._stats["policies_removed"] += 1
            logger.info("policy_removed", policy_id=policy_id)
            self._fire("remove_policy", {"policy_id": policy_id, "agent_id": entry["agent_id"]})
            return True
        return False

    def get_policies(self, agent_id: str) -> List[dict]:
        """Get all policies for an agent."""
        return [
            dict(entry)
            for entry in self.policies.values()
            if entry["agent_id"] == agent_id
        ]

    def get_policy_count(self, agent_id: str = "") -> int:
        """Count policies. If agent_id given, count for that agent."""
        if not agent_id:
            return len(self.policies)
        return sum(
            1 for entry in self.policies.values() if entry["agent_id"] == agent_id
        )

    def list_agents(self) -> List[str]:
        """List all agents with policies."""
        agents = sorted({entry["agent_id"] for entry in self.policies.values()})
        return agents

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return dict with counts."""
        return {
            **self._stats,
            "current_policies": len(self.policies),
            "current_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self.policies.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        self._stats["resets"] = 1
        logger.info("reset")
