"""Agent retry handler.

Manages retry logic for agent task failures with configurable policies,
supporting linear, exponential, and fixed backoff strategies. Tracks
attempt history per agent/task and enforces retry limits.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _PolicyEntry:
    """A retry policy for an agent."""
    policy_id: str = ""
    agent_id: str = ""
    max_retries: int = 3
    backoff: str = "linear"  # linear, exponential, fixed
    base_delay: float = 1.0
    created_at: float = field(default_factory=time.time)
    seq: int = 0


@dataclass
class _AttemptEntry:
    """A recorded attempt for an agent task."""
    attempt_id: str = ""
    agent_id: str = ""
    task_name: str = ""
    success: bool = False
    created_at: float = field(default_factory=time.time)
    seq: int = 0


class AgentRetryHandler:
    """Manages retry logic for agent task failures."""

    BACKOFF_STRATEGIES = ("linear", "exponential", "fixed")

    def __init__(self) -> None:
        self._entries: Dict[str, Any] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000
        self._policies: Dict[str, _PolicyEntry] = {}
        self._attempts: Dict[str, _AttemptEntry] = {}
        self._stats = {
            "total_policies_created": 0,
            "total_attempts_recorded": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_resets": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, key: str) -> str:
        self._seq += 1
        raw = f"{key}{uuid.uuid4()}{self._seq}"
        return "arh-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def create_policy(self, agent_id: str, max_retries: int = 3,
                      backoff: str = "linear",
                      base_delay: float = 1.0) -> str:
        """Create a retry policy for an agent. Returns the policy ID."""
        if not agent_id:
            return ""
        if backoff not in self.BACKOFF_STRATEGIES:
            return ""
        if max_retries < 0:
            return ""
        if base_delay < 0:
            return ""
        if len(self._policies) >= self._max_entries:
            return ""

        pid = self._make_id(agent_id)
        self._seq += 0  # seq already incremented in _make_id
        self._policies[pid] = _PolicyEntry(
            policy_id=pid,
            agent_id=agent_id,
            max_retries=max_retries,
            backoff=backoff,
            base_delay=base_delay,
            seq=self._seq,
        )
        self._entries[pid] = self._policies[pid]
        self._stats["total_policies_created"] += 1

        logger.info("retry_policy_created", agent_id=agent_id,
                     policy_id=pid, backoff=backoff)
        self._fire("policy_created", {
            "policy_id": pid, "agent_id": agent_id,
            "max_retries": max_retries, "backoff": backoff,
        })
        return pid

    def _get_agent_policy(self, agent_id: str) -> Optional[_PolicyEntry]:
        """Find the most recent policy for an agent."""
        best: Optional[_PolicyEntry] = None
        for p in self._policies.values():
            if p.agent_id == agent_id:
                if best is None or p.seq > best.seq:
                    best = p
        return best

    # ------------------------------------------------------------------
    # Attempt tracking
    # ------------------------------------------------------------------

    def record_attempt(self, agent_id: str, task_name: str,
                       success: bool) -> str:
        """Record a task attempt. Returns the attempt ID."""
        if not agent_id or not task_name:
            return ""
        if len(self._attempts) >= self._max_entries:
            self._prune_attempts()

        aid = self._make_id(f"{agent_id}:{task_name}")
        self._attempts[aid] = _AttemptEntry(
            attempt_id=aid,
            agent_id=agent_id,
            task_name=task_name,
            success=success,
            seq=self._seq,
        )
        self._entries[aid] = self._attempts[aid]
        self._stats["total_attempts_recorded"] += 1
        if success:
            self._stats["total_successes"] += 1
        else:
            self._stats["total_failures"] += 1

        logger.info("attempt_recorded", agent_id=agent_id,
                     task_name=task_name, success=success, attempt_id=aid)
        self._fire("attempt_recorded", {
            "attempt_id": aid, "agent_id": agent_id,
            "task_name": task_name, "success": success,
        })
        return aid

    def _get_task_attempts(self, agent_id: str,
                           task_name: str) -> List[_AttemptEntry]:
        """Get all attempts for an agent/task pair, ordered by seq."""
        results = [
            a for a in self._attempts.values()
            if a.agent_id == agent_id and a.task_name == task_name
        ]
        results.sort(key=lambda x: x.seq)
        return results

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def should_retry(self, agent_id: str, task_name: str) -> bool:
        """Check whether a retry is allowed based on the agent's policy."""
        policy = self._get_agent_policy(agent_id)
        if not policy:
            return False

        attempts = self._get_task_attempts(agent_id, task_name)
        if not attempts:
            return True

        # If the last attempt succeeded, no retry needed
        if attempts[-1].success:
            return False

        failed_count = sum(1 for a in attempts if not a.success)
        return failed_count < policy.max_retries

    def get_attempt_count(self, agent_id: str, task_name: str) -> int:
        """Return the number of attempts recorded for an agent/task pair."""
        return len(self._get_task_attempts(agent_id, task_name))

    def get_next_delay(self, agent_id: str, task_name: str) -> float:
        """Calculate the next delay based on the backoff strategy."""
        policy = self._get_agent_policy(agent_id)
        if not policy:
            return 0.0

        attempts = self._get_task_attempts(agent_id, task_name)
        failed_count = sum(1 for a in attempts if not a.success)
        if failed_count == 0:
            return 0.0

        if policy.backoff == "fixed":
            return policy.base_delay
        elif policy.backoff == "exponential":
            return policy.base_delay * (2 ** (failed_count - 1))
        else:  # linear
            return policy.base_delay * failed_count

    def reset_task(self, agent_id: str, task_name: str) -> bool:
        """Reset the attempt counter for a specific agent/task pair."""
        keys_to_remove = [
            k for k, a in self._attempts.items()
            if a.agent_id == agent_id and a.task_name == task_name
        ]
        if not keys_to_remove:
            return False

        for k in keys_to_remove:
            del self._attempts[k]
            self._entries.pop(k, None)

        self._stats["total_resets"] += 1
        logger.info("task_reset", agent_id=agent_id, task_name=task_name)
        self._fire("task_reset", {
            "agent_id": agent_id, "task_name": task_name,
        })
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """List all agent IDs that have policies registered."""
        agents = set()
        for p in self._policies.values():
            agents.add(p.agent_id)
        return sorted(agents)

    def get_policy_count(self) -> int:
        """Return the number of registered policies."""
        return len(self._policies)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_attempts(self) -> None:
        """Remove oldest attempts when limit is reached."""
        items = sorted(self._attempts.items(), key=lambda x: x[1].seq)
        to_remove = max(len(items) // 4, 1)
        for k, _ in items[:to_remove]:
            del self._attempts[k]
            self._entries.pop(k, None)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return handler statistics."""
        return {
            **self._stats,
            "current_policies": len(self._policies),
            "current_attempts": len(self._attempts),
            "current_entries": len(self._entries),
            "registered_agents": len(self.list_agents()),
            "active_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._entries.clear()
        self._policies.clear()
        self._attempts.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("agent_retry_handler_reset")
