"""Agent Delegation Manager – delegates tasks between agents.

Manages task delegation from one agent to another with tracking,
status updates, and result collection. Supports delegation chains
and automatic timeout handling.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Delegation:
    delegation_id: str
    task_name: str
    from_agent: str
    to_agent: str
    status: str  # pending, accepted, rejected, completed, failed, timeout
    payload: Any
    result: Any
    priority: int
    timeout_ms: float
    created_at: float
    updated_at: float
    completed_at: float
    tags: List[str]


class AgentDelegationManager:
    """Manages task delegation between agents."""

    STATUSES = ("pending", "accepted", "rejected", "completed", "failed", "timeout")

    def __init__(self, max_delegations: int = 100000):
        self._delegations: Dict[str, _Delegation] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_delegations = max_delegations
        self._seq = 0

        # stats
        self._total_delegations = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_rejected = 0

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    def delegate(
        self,
        task_name: str,
        from_agent: str,
        to_agent: str,
        payload: Any = None,
        priority: int = 5,
        timeout_ms: float = 30000,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not task_name or not from_agent or not to_agent:
            return ""
        if from_agent == to_agent:
            return ""
        if len(self._delegations) >= self._max_delegations:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{task_name}-{from_agent}-{to_agent}-{now}-{self._seq}"
        did = "dlg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        d = _Delegation(
            delegation_id=did,
            task_name=task_name,
            from_agent=from_agent,
            to_agent=to_agent,
            status="pending",
            payload=payload,
            result=None,
            priority=priority,
            timeout_ms=timeout_ms,
            created_at=now,
            updated_at=now,
            completed_at=0.0,
            tags=tags or [],
        )
        self._delegations[did] = d
        self._total_delegations += 1
        self._fire("task_delegated", {"delegation_id": did, "task": task_name,
                                       "from": from_agent, "to": to_agent})
        return did

    def get_delegation(self, delegation_id: str) -> Optional[Dict[str, Any]]:
        d = self._delegations.get(delegation_id)
        if not d:
            return None
        return {
            "delegation_id": d.delegation_id,
            "task_name": d.task_name,
            "from_agent": d.from_agent,
            "to_agent": d.to_agent,
            "status": d.status,
            "payload": d.payload,
            "result": d.result,
            "priority": d.priority,
            "timeout_ms": d.timeout_ms,
            "tags": list(d.tags),
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "completed_at": d.completed_at,
        }

    def remove_delegation(self, delegation_id: str) -> bool:
        return self._delegations.pop(delegation_id, None) is not None

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def accept(self, delegation_id: str) -> bool:
        d = self._delegations.get(delegation_id)
        if not d or d.status != "pending":
            return False
        d.status = "accepted"
        d.updated_at = time.time()
        self._fire("delegation_accepted", {"delegation_id": delegation_id})
        return True

    def reject(self, delegation_id: str, reason: str = "") -> bool:
        d = self._delegations.get(delegation_id)
        if not d or d.status != "pending":
            return False
        d.status = "rejected"
        d.result = reason
        d.updated_at = time.time()
        d.completed_at = time.time()
        self._total_rejected += 1
        self._fire("delegation_rejected", {"delegation_id": delegation_id})
        return True

    def complete(self, delegation_id: str, result: Any = None) -> bool:
        d = self._delegations.get(delegation_id)
        if not d or d.status not in ("pending", "accepted"):
            return False
        d.status = "completed"
        d.result = result
        now = time.time()
        d.updated_at = now
        d.completed_at = now
        self._total_completed += 1
        self._fire("delegation_completed", {"delegation_id": delegation_id})
        return True

    def fail(self, delegation_id: str, error: str = "") -> bool:
        d = self._delegations.get(delegation_id)
        if not d or d.status not in ("pending", "accepted"):
            return False
        d.status = "failed"
        d.result = error
        now = time.time()
        d.updated_at = now
        d.completed_at = now
        self._total_failed += 1
        self._fire("delegation_failed", {"delegation_id": delegation_id})
        return True

    def check_timeouts(self) -> List[str]:
        """Check for timed-out delegations. Returns list of timed-out IDs."""
        now = time.time()
        timed_out = []
        for d in self._delegations.values():
            if d.status not in ("pending", "accepted"):
                continue
            elapsed_ms = (now - d.created_at) * 1000
            if elapsed_ms > d.timeout_ms:
                d.status = "timeout"
                d.updated_at = now
                d.completed_at = now
                timed_out.append(d.delegation_id)
                self._fire("delegation_timeout", {"delegation_id": d.delegation_id})
        return timed_out

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_delegations(
        self,
        from_agent: str = "",
        to_agent: str = "",
        status: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for d in self._delegations.values():
            if from_agent and d.from_agent != from_agent:
                continue
            if to_agent and d.to_agent != to_agent:
                continue
            if status and d.status != status:
                continue
            if tag and tag not in d.tags:
                continue
            results.append(self.get_delegation(d.delegation_id))
        return results

    def get_pending_for_agent(self, agent: str) -> List[Dict[str, Any]]:
        return [self.get_delegation(d.delegation_id)
                for d in self._delegations.values()
                if d.to_agent == agent and d.status == "pending"]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_delegations": len(self._delegations),
            "total_delegations": self._total_delegations,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "total_rejected": self._total_rejected,
            "pending_count": sum(1 for d in self._delegations.values() if d.status == "pending"),
        }

    def reset(self) -> None:
        self._delegations.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_delegations = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_rejected = 0
