"""Pipeline Cost Optimizer – optimize pipeline execution costs.

Tracks resource spending, identifies wasteful patterns, and suggests
optimizations through budget management and savings plans.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CostResource:
    resource_id: str
    name: str
    unit_cost: float
    resource_type: str
    budget_limit: float
    total_usage: float
    total_cost: float
    usage_count: int
    tags: List[str]
    created_at: float


@dataclass
class _UsageRecord:
    usage_id: str
    resource_name: str
    amount: float
    cost: float
    context: str
    timestamp: float


@dataclass
class _SavingsPlan:
    plan_id: str
    name: str
    target_reduction_pct: float
    resources: List[str]
    status: str
    tags: List[str]
    created_at: float


@dataclass
class _CostEvent:
    event_id: str
    resource_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class PipelineCostOptimizer:
    """Optimize pipeline execution costs by tracking spending and suggesting optimizations."""

    RESOURCE_TYPES = ("compute", "storage", "network", "api_call")

    def __init__(self, max_resources: int = 5000, max_history: int = 100000):
        self._resources: Dict[str, _CostResource] = {}
        self._name_index: Dict[str, str] = {}
        self._usage_records: Dict[str, _UsageRecord] = {}
        self._savings_plans: Dict[str, _SavingsPlan] = {}
        self._plan_name_index: Dict[str, str] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_resources = max_resources
        self._max_history = max_history
        self._seq = 0
        self._total_resources_created = 0
        self._total_usage_recorded = 0
        self._total_plans_created = 0
        self._total_cost = 0.0

    # --- Resources ---

    def register_resource(
        self,
        name: str,
        unit_cost: float = 1.0,
        resource_type: str = "compute",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a resource to track. Returns resource ID or empty on failure."""
        if not name or name in self._name_index:
            return ""
        if resource_type not in self.RESOURCE_TYPES:
            return ""
        if unit_cost < 0:
            return ""
        if len(self._resources) >= self._max_resources:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        rid = "cor-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        res = _CostResource(
            resource_id=rid,
            name=name,
            unit_cost=unit_cost,
            resource_type=resource_type,
            budget_limit=0.0,
            total_usage=0.0,
            total_cost=0.0,
            usage_count=0,
            tags=list(tags or []),
            created_at=now,
        )
        self._resources[rid] = res
        self._name_index[name] = rid
        self._total_resources_created += 1
        self._record("resource_registered", name, {"resource_type": resource_type, "unit_cost": unit_cost})
        self._fire("resource_registered", {"name": name, "resource_id": rid})
        return rid

    def record_usage(self, resource_name: str, amount: float, context: str = "") -> str:
        """Record a usage event. Returns usage ID or empty on failure."""
        rid = self._name_index.get(resource_name)
        if not rid:
            return ""
        if amount <= 0:
            return ""
        res = self._resources[rid]
        cost = amount * res.unit_cost
        self._seq += 1
        now = time.time()
        raw = f"{resource_name}-{now}-{self._seq}"
        uid = "cus-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        record = _UsageRecord(
            usage_id=uid,
            resource_name=resource_name,
            amount=amount,
            cost=cost,
            context=context,
            timestamp=now,
        )
        self._usage_records[uid] = record
        res.total_usage += amount
        res.total_cost += cost
        res.usage_count += 1
        self._total_usage_recorded += 1
        self._total_cost += cost
        self._record("usage_recorded", resource_name, {"amount": amount, "cost": cost, "context": context})
        self._fire("usage_recorded", {"resource_name": resource_name, "usage_id": uid, "cost": cost})
        return uid

    def get_resource(self, name: str) -> Optional[Dict]:
        """Get a resource by name with usage stats."""
        rid = self._name_index.get(name)
        if not rid:
            return None
        res = self._resources[rid]
        return {
            "resource_id": res.resource_id,
            "name": res.name,
            "unit_cost": res.unit_cost,
            "resource_type": res.resource_type,
            "budget_limit": res.budget_limit,
            "total_usage": res.total_usage,
            "total_cost": res.total_cost,
            "usage_count": res.usage_count,
            "tags": list(res.tags),
            "created_at": res.created_at,
        }

    def remove_resource(self, name: str) -> bool:
        """Remove a resource by name."""
        rid = self._name_index.get(name)
        if not rid:
            return False
        del self._resources[rid]
        del self._name_index[name]
        self._record("resource_removed", name, {})
        self._fire("resource_removed", {"name": name})
        return True

    def list_resources(self, resource_type: str = "", tag: str = "") -> List[Dict]:
        """List resources with optional filters."""
        results = []
        for res in self._resources.values():
            if resource_type and res.resource_type != resource_type:
                continue
            if tag and tag not in res.tags:
                continue
            results.append({
                "resource_id": res.resource_id,
                "name": res.name,
                "unit_cost": res.unit_cost,
                "resource_type": res.resource_type,
                "total_cost": res.total_cost,
                "usage_count": res.usage_count,
                "tags": list(res.tags),
            })
        return results

    # --- Budgets ---

    def set_budget(self, resource_name: str, budget_limit: float) -> bool:
        """Set a spending cap for a resource."""
        rid = self._name_index.get(resource_name)
        if not rid:
            return False
        if budget_limit <= 0:
            return False
        res = self._resources[rid]
        res.budget_limit = budget_limit
        self._record("budget_set", resource_name, {"budget_limit": budget_limit})
        self._fire("budget_set", {"resource_name": resource_name, "budget_limit": budget_limit})
        return True

    def check_budget(self, resource_name: str) -> Dict:
        """Check budget status for a resource."""
        rid = self._name_index.get(resource_name)
        if not rid:
            return {}
        res = self._resources[rid]
        if res.budget_limit <= 0:
            return {
                "resource_name": resource_name,
                "budget_limit": 0.0,
                "total_cost": res.total_cost,
                "remaining": 0.0,
                "pct_used": 0.0,
                "over_budget": False,
            }
        remaining = max(0.0, res.budget_limit - res.total_cost)
        pct_used = (res.total_cost / res.budget_limit) * 100.0
        over_budget = res.total_cost > res.budget_limit
        return {
            "resource_name": resource_name,
            "budget_limit": res.budget_limit,
            "total_cost": res.total_cost,
            "remaining": remaining,
            "pct_used": pct_used,
            "over_budget": over_budget,
        }

    # --- Cost Analysis ---

    def get_cost_breakdown(self, resource_name: str = "") -> Dict:
        """Get cost breakdown, optionally filtered to one resource."""
        by_resource: Dict[str, float] = {}
        total = 0.0
        count = 0
        for rec in self._usage_records.values():
            if resource_name and rec.resource_name != resource_name:
                continue
            by_resource[rec.resource_name] = by_resource.get(rec.resource_name, 0.0) + rec.cost
            total += rec.cost
            count += 1
        return {
            "by_resource": by_resource,
            "total": total,
            "count": count,
        }

    def get_top_spenders(self, limit: int = 10) -> List[Dict]:
        """Get resources sorted by total cost descending."""
        results = []
        for res in self._resources.values():
            results.append({
                "name": res.name,
                "resource_type": res.resource_type,
                "total_cost": res.total_cost,
                "total_usage": res.total_usage,
                "usage_count": res.usage_count,
                "unit_cost": res.unit_cost,
            })
        results.sort(key=lambda x: x["total_cost"], reverse=True)
        return results[:limit]

    def suggest_optimizations(self) -> List[Dict]:
        """Analyze patterns and suggest optimizations."""
        suggestions: List[Dict] = []
        for res in self._resources.values():
            # Flag resources with >80% budget used
            if res.budget_limit > 0:
                pct = (res.total_cost / res.budget_limit) * 100.0
                if pct > 80.0:
                    suggestions.append({
                        "type": "budget_warning",
                        "resource": res.name,
                        "message": f"Resource '{res.name}' has used {pct:.1f}% of its budget",
                        "pct_used": pct,
                        "severity": "high" if pct > 100.0 else "medium",
                    })
            # Flag resources with high usage variance
            amounts = [
                rec.amount for rec in self._usage_records.values()
                if rec.resource_name == res.name
            ]
            if len(amounts) >= 3:
                mean = sum(amounts) / len(amounts)
                if mean > 0:
                    variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
                    std_dev = variance ** 0.5
                    cv = std_dev / mean
                    if cv > 1.0:
                        suggestions.append({
                            "type": "high_variance",
                            "resource": res.name,
                            "message": f"Resource '{res.name}' has high usage variance (CV={cv:.2f})",
                            "coefficient_of_variation": cv,
                            "severity": "medium",
                        })
            # Flag unused resources
            if res.usage_count == 0:
                suggestions.append({
                    "type": "unused_resource",
                    "resource": res.name,
                    "message": f"Resource '{res.name}' is registered but has no usage",
                    "severity": "low",
                })
        return suggestions

    # --- Savings Plans ---

    def create_savings_plan(
        self,
        name: str,
        target_reduction_pct: float = 20.0,
        resources: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a savings plan. Returns plan ID or empty on failure."""
        if not name or name in self._plan_name_index:
            return ""
        if target_reduction_pct <= 0 or target_reduction_pct > 100.0:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        pid = "csp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        plan = _SavingsPlan(
            plan_id=pid,
            name=name,
            target_reduction_pct=target_reduction_pct,
            resources=list(resources or []),
            status="active",
            tags=list(tags or []),
            created_at=now,
        )
        self._savings_plans[pid] = plan
        self._plan_name_index[name] = pid
        self._total_plans_created += 1
        self._record("savings_plan_created", name, {"target_reduction_pct": target_reduction_pct})
        self._fire("savings_plan_created", {"name": name, "plan_id": pid})
        return pid

    def get_savings_plan(self, name: str) -> Optional[Dict]:
        """Get a savings plan by name."""
        pid = self._plan_name_index.get(name)
        if not pid:
            return None
        plan = self._savings_plans[pid]
        return {
            "plan_id": plan.plan_id,
            "name": plan.name,
            "target_reduction_pct": plan.target_reduction_pct,
            "resources": list(plan.resources),
            "status": plan.status,
            "tags": list(plan.tags),
            "created_at": plan.created_at,
        }

    def list_savings_plans(self) -> List[Dict]:
        """List all savings plans."""
        results = []
        for plan in self._savings_plans.values():
            results.append({
                "plan_id": plan.plan_id,
                "name": plan.name,
                "target_reduction_pct": plan.target_reduction_pct,
                "resources": list(plan.resources),
                "status": plan.status,
                "tags": list(plan.tags),
                "created_at": plan.created_at,
            })
        return results

    # --- History ---

    def get_history(self, limit: int = 50, **filters: Any) -> List[Dict]:
        """Get event history with optional filters."""
        results = []
        for evt in reversed(self._history):
            match = True
            for key, val in filters.items():
                if evt.get(key) != val:
                    match = False
                    break
            if match:
                results.append(evt)
            if len(results) >= limit:
                break
        return results

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer stats."""
        return {
            "total_resources_created": self._total_resources_created,
            "total_usage_recorded": self._total_usage_recorded,
            "total_plans_created": self._total_plans_created,
            "total_cost": self._total_cost,
            "current_resources": len(self._resources),
            "current_usage_records": len(self._usage_records),
            "current_savings_plans": len(self._savings_plans),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._resources.clear()
        self._name_index.clear()
        self._usage_records.clear()
        self._savings_plans.clear()
        self._plan_name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_resources_created = 0
        self._total_usage_recorded = 0
        self._total_plans_created = 0
        self._total_cost = 0.0

    # --- Internal ---

    def _record(self, action: str, resource_name: str, data: Dict[str, Any]) -> None:
        """Record an event to history."""
        self._seq += 1
        now = time.time()
        raw = f"{action}-{resource_name}-{now}-{self._seq}"
        eid = "cev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        evt = {
            "event_id": eid,
            "resource_name": resource_name,
            "action": action,
            "data": data,
            "timestamp": now,
        }
        self._history.append(evt)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
