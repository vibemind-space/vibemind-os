"""Agent Quota Manager – manages per-agent resource quotas with enforcement and tracking.

Enforces rate-limited quotas on named resources per agent, tracks usage over
rolling time windows, and records violations when limits are exceeded.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _Quota:
    quota_id: str
    agent_id: str
    resource: str
    limit: int
    period_seconds: float
    used: int
    window_start: float
    created_at: float
    updated_at: float


@dataclass
class _Violation:
    violation_id: str
    agent_id: str
    resource: str
    requested: int
    limit: int
    used_at_time: int
    timestamp: float


class AgentQuotaManager:
    """Manages per-agent resource quotas with enforcement and tracking."""

    def __init__(self, max_entries: int = 10000):
        self._quotas: Dict[str, _Quota] = {}
        self._key_index: Dict[str, str] = {}  # "agent_id:resource" -> quota_id
        self._violations: List[_Violation] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0
        self._total_quotas_created = 0
        self._total_requests = 0
        self._total_allowed = 0
        self._total_denied = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _quota_key(self, agent_id: str, resource: str) -> str:
        return f"{agent_id}:{resource}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._quotas) <= self._max_entries:
            return
        # Remove oldest quotas by created_at
        sorted_ids = sorted(self._quotas, key=lambda qid: self._quotas[qid].created_at)
        to_remove = len(self._quotas) - self._max_entries
        for qid in sorted_ids[:to_remove]:
            q = self._quotas.pop(qid)
            key = self._quota_key(q.agent_id, q.resource)
            self._key_index.pop(key, None)
        logger.debug("pruned_quotas", removed=to_remove)

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _maybe_reset_window(self, q: _Quota) -> None:
        """Reset the usage counter if the current time window has elapsed."""
        now = time.time()
        if now - q.window_start >= q.period_seconds:
            q.used = 0
            q.window_start = now
            q.updated_at = now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_quota(
        self,
        agent_id: str,
        resource: str,
        limit: int,
        period_seconds: float = 3600,
    ) -> str:
        """Create or update a quota for an agent/resource pair.

        Returns the quota_id string.
        """
        if not agent_id or not resource or limit < 0:
            return ""

        key = self._quota_key(agent_id, resource)
        now = time.time()

        # Update existing quota
        existing_id = self._key_index.get(key)
        if existing_id and existing_id in self._quotas:
            q = self._quotas[existing_id]
            q.limit = limit
            q.period_seconds = period_seconds
            q.updated_at = now
            logger.info("quota_updated", agent_id=agent_id, resource=resource, limit=limit)
            self._fire("quota_updated", {"quota_id": existing_id, "agent_id": agent_id, "resource": resource, "limit": limit})
            return existing_id

        # Create new quota
        qid = self._gen_id("aqm-", f"{agent_id}-{resource}")
        quota = _Quota(
            quota_id=qid,
            agent_id=agent_id,
            resource=resource,
            limit=limit,
            period_seconds=period_seconds,
            used=0,
            window_start=now,
            created_at=now,
            updated_at=now,
        )
        self._quotas[qid] = quota
        self._key_index[key] = qid
        self._total_quotas_created += 1
        self._prune_if_needed()

        logger.info("quota_created", quota_id=qid, agent_id=agent_id, resource=resource, limit=limit)
        self._fire("quota_created", {"quota_id": qid, "agent_id": agent_id, "resource": resource, "limit": limit})
        return qid

    def use_quota(
        self,
        agent_id: str,
        resource: str,
        amount: int = 1,
    ) -> Dict[str, Any]:
        """Attempt to consume quota. Returns usage result dict."""
        self._total_requests += 1
        key = self._quota_key(agent_id, resource)
        qid = self._key_index.get(key)

        if not qid or qid not in self._quotas:
            logger.warning("quota_not_found", agent_id=agent_id, resource=resource)
            return {"allowed": False, "remaining": 0, "used": 0, "limit": 0}

        q = self._quotas[qid]
        self._maybe_reset_window(q)

        remaining = q.limit - q.used

        if amount <= remaining:
            q.used += amount
            q.updated_at = time.time()
            self._total_allowed += 1
            new_remaining = q.limit - q.used
            logger.debug("quota_consumed", agent_id=agent_id, resource=resource, amount=amount, remaining=new_remaining)
            self._fire("quota_used", {"agent_id": agent_id, "resource": resource, "amount": amount, "remaining": new_remaining})
            return {"allowed": True, "remaining": new_remaining, "used": q.used, "limit": q.limit}

        # Denied — record violation
        self._total_denied += 1
        vid = self._gen_id("aqv-", f"{agent_id}-{resource}-violation")
        violation = _Violation(
            violation_id=vid,
            agent_id=agent_id,
            resource=resource,
            requested=amount,
            limit=q.limit,
            used_at_time=q.used,
            timestamp=time.time(),
        )
        self._violations.append(violation)
        if len(self._violations) > self._max_entries:
            self._violations = self._violations[-self._max_entries:]

        logger.warning("quota_exceeded", agent_id=agent_id, resource=resource, requested=amount, remaining=remaining)
        self._fire("quota_exceeded", {"agent_id": agent_id, "resource": resource, "requested": amount, "remaining": remaining})
        return {"allowed": False, "remaining": remaining, "used": q.used, "limit": q.limit}

    def get_usage(self, agent_id: str, resource: str) -> Dict[str, Any]:
        """Return current usage for an agent/resource pair."""
        key = self._quota_key(agent_id, resource)
        qid = self._key_index.get(key)

        if not qid or qid not in self._quotas:
            return {"used": 0, "limit": 0, "remaining": 0, "utilization_pct": 0.0}

        q = self._quotas[qid]
        self._maybe_reset_window(q)
        remaining = q.limit - q.used
        pct = (q.used / q.limit * 100.0) if q.limit > 0 else 0.0

        return {
            "used": q.used,
            "limit": q.limit,
            "remaining": remaining,
            "utilization_pct": round(pct, 2),
        }

    def reset_quota(self, agent_id: str, resource: str) -> bool:
        """Reset usage counter for an agent/resource pair. Returns True on success."""
        key = self._quota_key(agent_id, resource)
        qid = self._key_index.get(key)

        if not qid or qid not in self._quotas:
            return False

        q = self._quotas[qid]
        q.used = 0
        q.window_start = time.time()
        q.updated_at = q.window_start

        logger.info("quota_reset", agent_id=agent_id, resource=resource)
        self._fire("quota_reset", {"agent_id": agent_id, "resource": resource})
        return True

    def list_quotas(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all quotas, optionally filtered by agent_id."""
        results: List[Dict[str, Any]] = []
        for q in self._quotas.values():
            if agent_id is not None and q.agent_id != agent_id:
                continue
            self._maybe_reset_window(q)
            remaining = q.limit - q.used
            pct = (q.used / q.limit * 100.0) if q.limit > 0 else 0.0
            results.append({
                "quota_id": q.quota_id,
                "agent_id": q.agent_id,
                "resource": q.resource,
                "limit": q.limit,
                "used": q.used,
                "remaining": remaining,
                "utilization_pct": round(pct, 2),
                "period_seconds": q.period_seconds,
                "window_start": q.window_start,
                "created_at": q.created_at,
                "updated_at": q.updated_at,
            })
        return results

    def remove_quota(self, agent_id: str, resource: str) -> bool:
        """Remove a quota for an agent/resource pair. Returns True on success."""
        key = self._quota_key(agent_id, resource)
        qid = self._key_index.pop(key, None)

        if not qid:
            return False

        self._quotas.pop(qid, None)
        logger.info("quota_removed", agent_id=agent_id, resource=resource)
        self._fire("quota_removed", {"agent_id": agent_id, "resource": resource})
        return True

    def get_violations(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return recorded quota violations, optionally filtered by agent_id."""
        results: List[Dict[str, Any]] = []
        for v in self._violations:
            if agent_id is not None and v.agent_id != agent_id:
                continue
            results.append({
                "violation_id": v.violation_id,
                "agent_id": v.agent_id,
                "resource": v.resource,
                "requested": v.requested,
                "limit": v.limit,
                "used_at_time": v.used_at_time,
                "timestamp": v.timestamp,
            })
        return results

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
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_quotas": len(self._quotas),
            "total_quotas_created": self._total_quotas_created,
            "total_requests": self._total_requests,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
            "active_violations": len(self._violations),
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        self._quotas.clear()
        self._key_index.clear()
        self._violations.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_quotas_created = 0
        self._total_requests = 0
        self._total_allowed = 0
        self._total_denied = 0
        logger.info("quota_manager_reset")
