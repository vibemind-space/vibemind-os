"""Pipeline quota manager - manage resource quotas per agent/team with tracking and enforcement."""

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Quota:
    quota_id: str
    name: str
    resource_type: str
    limit: float
    period_seconds: float  # 0 = no reset
    owner: str  # agent or team name
    owner_type: str  # agent, team, global
    current_usage: float
    period_start: float
    created_at: float
    metadata: Dict = field(default_factory=dict)


class PipelineQuotaManager:
    """Manage and enforce resource quotas with periodic resets and usage tracking."""

    RESOURCE_TYPES = ("cpu", "memory", "storage", "api_calls", "tasks", "tokens", "bandwidth", "custom")
    OWNER_TYPES = ("agent", "team", "global")

    def __init__(self, max_quotas: int = 5000):
        self._max_quotas = max_quotas
        self._quotas: Dict[str, _Quota] = {}
        self._usage_history: List[Dict] = []
        self._max_history = 50000
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_quotas_created": 0,
            "total_consumed": 0,
            "total_rejected": 0,
            "total_resets": 0,
        }

    # ── Quota Management ──

    def create_quota(self, name: str, resource_type: str, limit: float,
                     owner: str, owner_type: str = "agent",
                     period_seconds: float = 0.0,
                     metadata: Optional[Dict] = None) -> str:
        """Create a resource quota."""
        if not name or not owner:
            return ""
        if resource_type not in self.RESOURCE_TYPES:
            return ""
        if owner_type not in self.OWNER_TYPES:
            return ""
        if limit <= 0:
            return ""
        if len(self._quotas) >= self._max_quotas:
            return ""

        qid = f"quota-{uuid.uuid4().hex[:10]}"
        now = time.time()
        self._quotas[qid] = _Quota(
            quota_id=qid,
            name=name,
            resource_type=resource_type,
            limit=limit,
            period_seconds=period_seconds,
            owner=owner,
            owner_type=owner_type,
            current_usage=0.0,
            period_start=now,
            created_at=now,
            metadata=metadata or {},
        )
        self._stats["total_quotas_created"] += 1
        return qid

    def remove_quota(self, quota_id: str) -> bool:
        if quota_id not in self._quotas:
            return False
        del self._quotas[quota_id]
        return True

    def get_quota(self, quota_id: str) -> Optional[Dict]:
        q = self._quotas.get(quota_id)
        if not q:
            return None
        self._check_period_reset(q)
        return {
            "quota_id": q.quota_id,
            "name": q.name,
            "resource_type": q.resource_type,
            "limit": q.limit,
            "current_usage": q.current_usage,
            "remaining": q.limit - q.current_usage,
            "utilization": q.current_usage / q.limit if q.limit > 0 else 0.0,
            "owner": q.owner,
            "owner_type": q.owner_type,
            "period_seconds": q.period_seconds,
        }

    def list_quotas(self, owner: str = "", resource_type: str = "",
                    owner_type: str = "") -> List[Dict]:
        result = []
        for q in self._quotas.values():
            self._check_period_reset(q)
            if owner and q.owner != owner:
                continue
            if resource_type and q.resource_type != resource_type:
                continue
            if owner_type and q.owner_type != owner_type:
                continue
            result.append({
                "quota_id": q.quota_id,
                "name": q.name,
                "resource_type": q.resource_type,
                "limit": q.limit,
                "current_usage": q.current_usage,
                "remaining": q.limit - q.current_usage,
                "owner": q.owner,
            })
        return result

    def update_limit(self, quota_id: str, new_limit: float) -> bool:
        q = self._quotas.get(quota_id)
        if not q or new_limit <= 0:
            return False
        q.limit = new_limit
        return True

    # ── Usage ──

    def consume(self, quota_id: str, amount: float = 1.0,
                source: str = "") -> bool:
        """Consume quota. Returns False if would exceed limit."""
        q = self._quotas.get(quota_id)
        if not q or amount <= 0:
            return False
        self._check_period_reset(q)

        if q.current_usage + amount > q.limit:
            self._stats["total_rejected"] += 1
            self._fire_callbacks("quota_exceeded", quota_id)
            return False

        q.current_usage += amount
        self._stats["total_consumed"] += 1
        self._record_usage(quota_id, amount, source)

        # Warn at 80%
        if q.current_usage / q.limit >= 0.8:
            self._fire_callbacks("quota_warning", quota_id)

        return True

    def release(self, quota_id: str, amount: float = 1.0) -> bool:
        """Release consumed quota back."""
        q = self._quotas.get(quota_id)
        if not q or amount <= 0:
            return False
        q.current_usage = max(0.0, q.current_usage - amount)
        return True

    def check_available(self, quota_id: str, amount: float = 1.0) -> bool:
        """Check if amount is available without consuming."""
        q = self._quotas.get(quota_id)
        if not q:
            return False
        self._check_period_reset(q)
        return q.current_usage + amount <= q.limit

    def reset_usage(self, quota_id: str) -> bool:
        """Manually reset usage to zero."""
        q = self._quotas.get(quota_id)
        if not q:
            return False
        q.current_usage = 0.0
        q.period_start = time.time()
        self._stats["total_resets"] += 1
        return True

    def _check_period_reset(self, q: _Quota) -> None:
        """Auto-reset if period has elapsed."""
        if q.period_seconds > 0:
            elapsed = time.time() - q.period_start
            if elapsed >= q.period_seconds:
                q.current_usage = 0.0
                q.period_start = time.time()
                self._stats["total_resets"] += 1

    def _record_usage(self, quota_id: str, amount: float, source: str) -> None:
        if len(self._usage_history) >= self._max_history:
            self._usage_history = self._usage_history[-(self._max_history // 2):]
        self._usage_history.append({
            "quota_id": quota_id,
            "amount": amount,
            "source": source,
            "timestamp": time.time(),
        })

    # ── Analysis ──

    def get_owner_usage(self, owner: str) -> Dict[str, float]:
        """Get total usage per resource type for an owner."""
        usage: Dict[str, float] = defaultdict(float)
        for q in self._quotas.values():
            if q.owner == owner:
                self._check_period_reset(q)
                usage[q.resource_type] += q.current_usage
        return dict(usage)

    def get_exhausted_quotas(self) -> List[Dict]:
        """Get quotas at or near their limit (>= 90%)."""
        result = []
        for q in self._quotas.values():
            self._check_period_reset(q)
            if q.limit > 0 and q.current_usage / q.limit >= 0.9:
                result.append({
                    "quota_id": q.quota_id,
                    "name": q.name,
                    "owner": q.owner,
                    "utilization": q.current_usage / q.limit,
                })
        return result

    def get_usage_history(self, quota_id: str = "", limit: int = 50) -> List[Dict]:
        result = []
        for h in reversed(self._usage_history):
            if quota_id and h["quota_id"] != quota_id:
                continue
            result.append(h)
            if len(result) >= limit:
                break
        return result

    def get_owner_summary(self, owner: str) -> Dict:
        """Get summary for an owner."""
        quotas = [q for q in self._quotas.values() if q.owner == owner]
        if not quotas:
            return {}
        total_limit = sum(q.limit for q in quotas)
        total_usage = sum(q.current_usage for q in quotas)
        return {
            "owner": owner,
            "quota_count": len(quotas),
            "total_limit": total_limit,
            "total_usage": total_usage,
            "overall_utilization": total_usage / total_limit if total_limit > 0 else 0.0,
        }

    # ── Callbacks ──

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

    def _fire_callbacks(self, action: str, quota_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, quota_id)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        total_usage = sum(q.current_usage for q in self._quotas.values())
        total_limit = sum(q.limit for q in self._quotas.values())
        return {
            **self._stats,
            "total_quotas": len(self._quotas),
            "total_usage": total_usage,
            "total_limit": total_limit,
            "overall_utilization": total_usage / total_limit if total_limit > 0 else 0.0,
        }

    def reset(self) -> None:
        self._quotas.clear()
        self._usage_history.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
