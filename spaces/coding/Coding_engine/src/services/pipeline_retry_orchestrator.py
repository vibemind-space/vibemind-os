"""Pipeline retry orchestrator — manages retry policies and retry scheduling."""

import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


BACKOFF_STRATEGIES = ("fixed", "linear", "exponential", "jitter")


@dataclass
class RetryPolicy:
    """A retry policy configuration."""
    policy_id: str
    name: str
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff: str = "exponential"
    jitter: float = 0.1  # 0-1 jitter factor
    retry_on: List[str] = field(default_factory=list)  # Error categories to retry on
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class RetryAttempt:
    """Record of a retry attempt."""
    attempt_id: str
    task_name: str
    policy_id: str
    attempt_number: int
    delay: float
    status: str = "pending"  # pending, success, failed, exhausted
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


@dataclass
class RetrySession:
    """A retry session tracking all attempts for one task."""
    session_id: str
    task_name: str
    policy_id: str
    attempts: List[str] = field(default_factory=list)
    current_attempt: int = 0
    status: str = "active"  # active, succeeded, exhausted, cancelled
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PipelineRetryOrchestrator:
    """Orchestrates retries with configurable policies and backoff."""

    def __init__(self, max_policies: int = 100, max_sessions: int = 10000):
        self._policies: Dict[str, RetryPolicy] = {}
        self._sessions: Dict[str, RetrySession] = {}
        self._attempts: Dict[str, RetryAttempt] = {}
        self._max_policies = max_policies
        self._max_sessions = max_sessions
        self._callbacks: Dict[str, Any] = {}

        # Stats
        self._total_policies_created = 0
        self._total_sessions_created = 0
        self._total_attempts = 0
        self._total_successes = 0
        self._total_exhausted = 0

    # ── Policy Management ──

    def create_policy(self, name: str, max_retries: int = 3,
                      base_delay: float = 1.0, max_delay: float = 60.0,
                      backoff: str = "exponential", jitter: float = 0.1,
                      retry_on: Optional[List[str]] = None,
                      metadata: Optional[Dict] = None) -> str:
        """Create a retry policy. Returns policy_id."""
        if backoff not in BACKOFF_STRATEGIES:
            return ""
        if max_retries < 1:
            return ""
        if base_delay < 0 or max_delay < 0:
            return ""
        if len(self._policies) >= self._max_policies:
            return ""

        policy_id = f"rpol-{uuid.uuid4().hex[:8]}"
        self._policies[policy_id] = RetryPolicy(
            policy_id=policy_id,
            name=name,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            backoff=backoff,
            jitter=max(0.0, min(1.0, jitter)),
            retry_on=retry_on or [],
            metadata=metadata or {},
        )
        self._total_policies_created += 1
        return policy_id

    def remove_policy(self, policy_id: str) -> bool:
        if policy_id not in self._policies:
            return False
        del self._policies[policy_id]
        return True

    def get_policy(self, policy_id: str) -> Optional[Dict]:
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        return {
            "policy_id": policy.policy_id,
            "name": policy.name,
            "max_retries": policy.max_retries,
            "base_delay": policy.base_delay,
            "max_delay": policy.max_delay,
            "backoff": policy.backoff,
            "jitter": policy.jitter,
            "retry_on": list(policy.retry_on),
            "metadata": dict(policy.metadata),
        }

    def list_policies(self) -> List[Dict]:
        return [self.get_policy(pid) for pid in self._policies
                if self.get_policy(pid) is not None]

    # ── Delay Calculation ──

    def calculate_delay(self, policy_id: str, attempt_number: int) -> float:
        """Calculate delay for a given attempt number."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return 0.0

        if policy.backoff == "fixed":
            delay = policy.base_delay
        elif policy.backoff == "linear":
            delay = policy.base_delay * attempt_number
        elif policy.backoff == "exponential":
            delay = policy.base_delay * (2 ** (attempt_number - 1))
        elif policy.backoff == "jitter":
            exp_delay = policy.base_delay * (2 ** (attempt_number - 1))
            delay = random.uniform(0, exp_delay)
        else:
            delay = policy.base_delay

        # Apply jitter
        if policy.jitter > 0 and policy.backoff != "jitter":
            jitter_amount = delay * policy.jitter
            delay += random.uniform(-jitter_amount, jitter_amount)

        return min(max(0.0, delay), policy.max_delay)

    # ── Retry Sessions ──

    def start_session(self, task_name: str, policy_id: str,
                      metadata: Optional[Dict] = None) -> str:
        """Start a retry session for a task. Returns session_id."""
        if policy_id not in self._policies:
            return ""
        if len(self._sessions) >= self._max_sessions:
            return ""

        session_id = f"rsess-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = RetrySession(
            session_id=session_id,
            task_name=task_name,
            policy_id=policy_id,
            metadata=metadata or {},
        )
        self._total_sessions_created += 1
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        policy = self._policies.get(session.policy_id)
        return {
            "session_id": session.session_id,
            "task_name": session.task_name,
            "policy_id": session.policy_id,
            "current_attempt": session.current_attempt,
            "max_retries": policy.max_retries if policy else 0,
            "remaining_retries": max(0, (policy.max_retries if policy else 0) - session.current_attempt),
            "status": session.status,
            "attempt_count": len(session.attempts),
            "created_at": session.created_at,
            "metadata": dict(session.metadata),
        }

    def next_attempt(self, session_id: str) -> Optional[Dict]:
        """Create the next retry attempt. Returns attempt info or None if exhausted."""
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return None

        policy = self._policies.get(session.policy_id)
        if policy is None:
            return None

        if session.current_attempt >= policy.max_retries:
            session.status = "exhausted"
            self._total_exhausted += 1
            self._fire_callbacks("exhausted", session_id, session.task_name)
            return None

        session.current_attempt += 1
        delay = self.calculate_delay(policy.policy_id, session.current_attempt)

        attempt_id = f"rattempt-{uuid.uuid4().hex[:8]}"
        attempt = RetryAttempt(
            attempt_id=attempt_id,
            task_name=session.task_name,
            policy_id=session.policy_id,
            attempt_number=session.current_attempt,
            delay=delay,
        )
        self._attempts[attempt_id] = attempt
        session.attempts.append(attempt_id)
        self._total_attempts += 1

        return {
            "attempt_id": attempt_id,
            "attempt_number": session.current_attempt,
            "delay": delay,
            "remaining_retries": policy.max_retries - session.current_attempt,
        }

    def record_success(self, session_id: str) -> bool:
        """Record that the current attempt succeeded."""
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return False

        session.status = "succeeded"
        self._total_successes += 1

        # Mark last attempt as success
        if session.attempts:
            last = self._attempts.get(session.attempts[-1])
            if last:
                last.status = "success"
                last.completed_at = time.time()

        self._fire_callbacks("success", session_id, session.task_name)
        return True

    def record_failure(self, session_id: str, error: str = "") -> bool:
        """Record that the current attempt failed."""
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return False

        # Mark last attempt as failed
        if session.attempts:
            last = self._attempts.get(session.attempts[-1])
            if last:
                last.status = "failed"
                last.error = error
                last.completed_at = time.time()

        return True

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a retry session."""
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return False
        session.status = "cancelled"
        return True

    def should_retry(self, session_id: str, error_category: str = "") -> bool:
        """Check if retry should be attempted."""
        session = self._sessions.get(session_id)
        if session is None or session.status != "active":
            return False

        policy = self._policies.get(session.policy_id)
        if policy is None:
            return False

        if session.current_attempt >= policy.max_retries:
            return False

        # Check error category filter
        if policy.retry_on and error_category:
            if error_category not in policy.retry_on:
                return False

        return True

    # ── Queries ──

    def list_sessions(self, status: str = "", limit: int = 50) -> List[Dict]:
        result = []
        for session in self._sessions.values():
            if status and session.status != status:
                continue
            info = self.get_session(session.session_id)
            if info:
                result.append(info)
            if len(result) >= limit:
                break
        return result

    def get_attempt(self, attempt_id: str) -> Optional[Dict]:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            return None
        return {
            "attempt_id": attempt.attempt_id,
            "task_name": attempt.task_name,
            "attempt_number": attempt.attempt_number,
            "delay": attempt.delay,
            "status": attempt.status,
            "error": attempt.error,
            "created_at": attempt.created_at,
            "completed_at": attempt.completed_at,
        }

    def get_session_attempts(self, session_id: str) -> List[Dict]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        result = []
        for aid in session.attempts:
            info = self.get_attempt(aid)
            if info:
                result.append(info)
        return result

    # ── Callbacks ──

    def on_event(self, name: str, callback) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, event: str, session_id: str, task_name: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, session_id, task_name)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            "total_policies": len(self._policies),
            "total_sessions": len(self._sessions),
            "total_active_sessions": sum(1 for s in self._sessions.values() if s.status == "active"),
            "total_sessions_created": self._total_sessions_created,
            "total_attempts": self._total_attempts,
            "total_successes": self._total_successes,
            "total_exhausted": self._total_exhausted,
            "success_rate": round(
                self._total_successes / max(1, self._total_successes + self._total_exhausted) * 100, 1
            ),
        }

    def reset(self) -> None:
        self._policies.clear()
        self._sessions.clear()
        self._attempts.clear()
        self._callbacks.clear()
        self._total_policies_created = 0
        self._total_sessions_created = 0
        self._total_attempts = 0
        self._total_successes = 0
        self._total_exhausted = 0
