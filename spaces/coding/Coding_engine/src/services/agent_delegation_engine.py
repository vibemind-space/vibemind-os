"""Agent Delegation Engine – manages task delegation between agents.

Allows agents to delegate tasks to other agents with acceptance/rejection,
tracks delegation chains, handles escalation, and measures delegation
success rates.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Delegation:
    delegation_id: str
    task_name: str
    from_agent: str
    to_agent: str
    status: str  # pending | accepted | rejected | completed | failed | cancelled
    priority: int
    reason: str
    result: str
    parent_delegation_id: str  # for delegation chains
    tags: List[str]
    created_at: float
    updated_at: float
    seq: int


class AgentDelegationEngine:
    """Manages task delegation between agents."""

    STATUSES = ("pending", "accepted", "rejected", "completed", "failed", "cancelled")

    def __init__(self, max_delegations: int = 100000) -> None:
        self._max_delegations = max_delegations
        self._delegations: Dict[str, _Delegation] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_delegations": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # Delegation CRUD
    # ------------------------------------------------------------------

    def delegate(self, task_name: str, from_agent: str, to_agent: str,
                 priority: int = 5, reason: str = "",
                 parent_delegation_id: str = "",
                 tags: Optional[List[str]] = None) -> str:
        if not task_name or not from_agent or not to_agent:
            return ""
        if from_agent == to_agent:
            return ""
        if parent_delegation_id and parent_delegation_id not in self._delegations:
            return ""
        if len(self._delegations) >= self._max_delegations:
            return ""
        self._seq += 1
        raw = f"dlg-{task_name}-{from_agent}-{to_agent}-{self._seq}-{len(self._delegations)}"
        did = "dlg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        d = _Delegation(
            delegation_id=did, task_name=task_name,
            from_agent=from_agent, to_agent=to_agent,
            status="pending", priority=max(1, min(10, priority)),
            reason=reason, result="",
            parent_delegation_id=parent_delegation_id,
            tags=list(tags or []),
            created_at=time.time(), updated_at=time.time(), seq=self._seq,
        )
        self._delegations[did] = d
        self._stats["total_delegations"] += 1
        self._fire("task_delegated", {"delegation_id": did, "from": from_agent, "to": to_agent})
        return did

    def get_delegation(self, delegation_id: str) -> Optional[Dict]:
        d = self._delegations.get(delegation_id)
        if d is None:
            return None
        return self._d_to_dict(d)

    def remove_delegation(self, delegation_id: str) -> bool:
        if delegation_id not in self._delegations:
            return False
        del self._delegations[delegation_id]
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def accept(self, delegation_id: str) -> bool:
        d = self._delegations.get(delegation_id)
        if d is None or d.status != "pending":
            return False
        d.status = "accepted"
        d.updated_at = time.time()
        self._stats["total_accepted"] += 1
        self._fire("delegation_accepted", {"delegation_id": delegation_id})
        return True

    def reject(self, delegation_id: str, reason: str = "") -> bool:
        d = self._delegations.get(delegation_id)
        if d is None or d.status != "pending":
            return False
        d.status = "rejected"
        d.reason = reason or d.reason
        d.updated_at = time.time()
        self._stats["total_rejected"] += 1
        self._fire("delegation_rejected", {"delegation_id": delegation_id})
        return True

    def complete(self, delegation_id: str, result: str = "") -> bool:
        d = self._delegations.get(delegation_id)
        if d is None or d.status != "accepted":
            return False
        d.status = "completed"
        d.result = result
        d.updated_at = time.time()
        self._stats["total_completed"] += 1
        self._fire("delegation_completed", {"delegation_id": delegation_id})
        return True

    def fail(self, delegation_id: str, reason: str = "") -> bool:
        d = self._delegations.get(delegation_id)
        if d is None or d.status != "accepted":
            return False
        d.status = "failed"
        d.reason = reason or d.reason
        d.updated_at = time.time()
        self._stats["total_failed"] += 1
        self._fire("delegation_failed", {"delegation_id": delegation_id})
        return True

    def cancel(self, delegation_id: str) -> bool:
        d = self._delegations.get(delegation_id)
        if d is None or d.status not in ("pending", "accepted"):
            return False
        d.status = "cancelled"
        d.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_delegations_from(self, agent: str, status: str = "") -> List[Dict]:
        results = []
        for d in self._delegations.values():
            if d.from_agent != agent:
                continue
            if status and d.status != status:
                continue
            results.append(self._d_to_dict(d))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_delegations_to(self, agent: str, status: str = "") -> List[Dict]:
        results = []
        for d in self._delegations.values():
            if d.to_agent != agent:
                continue
            if status and d.status != status:
                continue
            results.append(self._d_to_dict(d))
        results.sort(key=lambda x: x["seq"])
        return results

    def search_delegations(self, from_agent: str = "", to_agent: str = "",
                           status: str = "", tag: str = "") -> List[Dict]:
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
            results.append(self._d_to_dict(d))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_delegation_chain(self, delegation_id: str) -> List[Dict]:
        """Get chain from root to this delegation."""
        chain = []
        did = delegation_id
        visited = set()
        while did and did not in visited:
            visited.add(did)
            d = self._delegations.get(did)
            if d is None:
                break
            chain.append(self._d_to_dict(d))
            did = d.parent_delegation_id
        chain.reverse()
        return chain

    def get_agent_success_rate(self, agent: str) -> Dict:
        """Get delegation success rate for agent as delegatee."""
        completed = 0
        failed = 0
        total = 0
        for d in self._delegations.values():
            if d.to_agent != agent:
                continue
            if d.status in ("completed", "failed"):
                total += 1
                if d.status == "completed":
                    completed += 1
                else:
                    failed += 1
        return {
            "agent": agent,
            "total_resolved": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total * 100, 1) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
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
            "current_delegations": len(self._delegations),
            "pending_delegations": sum(1 for d in self._delegations.values() if d.status == "pending"),
        }

    def reset(self) -> None:
        self._delegations.clear()
        self._seq = 0
        self._stats = {
            "total_delegations": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_completed": 0,
            "total_failed": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _d_to_dict(d: _Delegation) -> Dict:
        return {
            "delegation_id": d.delegation_id,
            "task_name": d.task_name,
            "from_agent": d.from_agent,
            "to_agent": d.to_agent,
            "status": d.status,
            "priority": d.priority,
            "reason": d.reason,
            "result": d.result,
            "parent_delegation_id": d.parent_delegation_id,
            "tags": list(d.tags),
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "seq": d.seq,
        }
