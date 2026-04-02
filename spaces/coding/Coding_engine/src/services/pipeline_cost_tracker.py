"""Pipeline cost tracker - track resource costs per pipeline, agent, and task."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CostEntry:
    """Single cost entry."""
    entry_id: str = ""
    resource_type: str = ""
    amount: float = 0.0
    unit_cost: float = 0.0
    total_cost: float = 0.0
    owner: str = ""
    owner_type: str = ""
    pipeline_id: str = ""
    task_id: str = ""
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class Budget:
    """Budget definition."""
    budget_id: str = ""
    name: str = ""
    owner: str = ""
    owner_type: str = ""
    limit: float = 0.0
    spent: float = 0.0
    remaining: float = 0.0
    period_seconds: float = 0.0
    period_start: float = 0.0
    created_at: float = 0.0


class PipelineCostTracker:
    """Track resource costs per pipeline, agent, and task."""

    RESOURCE_TYPES = (
        "compute", "memory", "storage", "network",
        "api_calls", "tokens", "gpu", "custom",
    )
    OWNER_TYPES = ("agent", "pipeline", "task", "team", "global")

    def __init__(self, max_entries: int = 100000, max_budgets: int = 5000):
        self._max_entries = max(1, max_entries)
        self._max_budgets = max(1, max_budgets)
        self._entries: Dict[str, CostEntry] = {}
        self._budgets: Dict[str, Budget] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries": 0,
            "total_cost": 0.0,
            "total_budgets_created": 0,
            "total_budget_exceeded": 0,
        }

    # --- Cost Entry ---

    def record_cost(
        self,
        resource_type: str,
        amount: float,
        unit_cost: float,
        owner: str,
        owner_type: str = "agent",
        pipeline_id: str = "",
        task_id: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Record a cost entry. Returns entry_id or empty on failure."""
        if not resource_type or resource_type not in self.RESOURCE_TYPES:
            return ""
        if amount <= 0 or unit_cost < 0:
            return ""
        if not owner:
            return ""
        if owner_type not in self.OWNER_TYPES:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        total = amount * unit_cost
        eid = f"cost-{uuid.uuid4().hex[:12]}"
        now = time.time()

        entry = CostEntry(
            entry_id=eid,
            resource_type=resource_type,
            amount=amount,
            unit_cost=unit_cost,
            total_cost=total,
            owner=owner,
            owner_type=owner_type,
            pipeline_id=pipeline_id,
            task_id=task_id,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=now,
        )
        self._entries[eid] = entry
        self._stats["total_entries"] += 1
        self._stats["total_cost"] += total

        # Check budgets for this owner
        for bid, b in self._budgets.items():
            if b.owner == owner:
                self._check_period_reset(b)
                b.spent += total
                b.remaining = max(0.0, b.limit - b.spent)
                if b.spent > b.limit:
                    self._stats["total_budget_exceeded"] += 1
                    self._fire("budget_exceeded", {"budget_id": bid, "entry_id": eid})

        self._fire("cost_recorded", {"entry_id": eid, "total_cost": total})
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a cost entry by ID."""
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "resource_type": e.resource_type,
            "amount": e.amount,
            "unit_cost": e.unit_cost,
            "total_cost": e.total_cost,
            "owner": e.owner,
            "owner_type": e.owner_type,
            "pipeline_id": e.pipeline_id,
            "task_id": e.task_id,
            "tags": list(e.tags),
            "metadata": dict(e.metadata),
            "created_at": e.created_at,
        }

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a cost entry."""
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        return True

    def list_entries(
        self,
        owner: str = "",
        resource_type: str = "",
        pipeline_id: str = "",
        task_id: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """List cost entries with optional filters."""
        results = []
        for e in self._entries.values():
            if owner and e.owner != owner:
                continue
            if resource_type and e.resource_type != resource_type:
                continue
            if pipeline_id and e.pipeline_id != pipeline_id:
                continue
            if task_id and e.task_id != task_id:
                continue
            if tag and tag not in e.tags:
                continue
            results.append({
                "entry_id": e.entry_id,
                "resource_type": e.resource_type,
                "amount": e.amount,
                "total_cost": e.total_cost,
                "owner": e.owner,
                "pipeline_id": e.pipeline_id,
                "created_at": e.created_at,
            })
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    # --- Budgets ---

    def create_budget(
        self,
        name: str,
        owner: str,
        limit: float,
        owner_type: str = "agent",
        period_seconds: float = 0.0,
    ) -> str:
        """Create a budget. Returns budget_id or empty on failure."""
        if not name or not owner:
            return ""
        if limit <= 0:
            return ""
        if owner_type not in self.OWNER_TYPES:
            return ""
        if len(self._budgets) >= self._max_budgets:
            return ""

        bid = f"budget-{uuid.uuid4().hex[:12]}"
        now = time.time()

        self._budgets[bid] = Budget(
            budget_id=bid,
            name=name,
            owner=owner,
            owner_type=owner_type,
            limit=limit,
            spent=0.0,
            remaining=limit,
            period_seconds=period_seconds,
            period_start=now,
            created_at=now,
        )
        self._stats["total_budgets_created"] += 1
        return bid

    def get_budget(self, budget_id: str) -> Optional[Dict]:
        """Get a budget by ID."""
        b = self._budgets.get(budget_id)
        if not b:
            return None
        self._check_period_reset(b)
        return {
            "budget_id": b.budget_id,
            "name": b.name,
            "owner": b.owner,
            "owner_type": b.owner_type,
            "limit": b.limit,
            "spent": b.spent,
            "remaining": b.remaining,
            "utilization": (b.spent / b.limit * 100) if b.limit > 0 else 0.0,
            "period_seconds": b.period_seconds,
            "created_at": b.created_at,
        }

    def remove_budget(self, budget_id: str) -> bool:
        """Remove a budget."""
        if budget_id not in self._budgets:
            return False
        del self._budgets[budget_id]
        return True

    def update_budget_limit(self, budget_id: str, new_limit: float) -> bool:
        """Update a budget's limit."""
        b = self._budgets.get(budget_id)
        if not b or new_limit <= 0:
            return False
        b.limit = new_limit
        b.remaining = max(0.0, b.limit - b.spent)
        return True

    def list_budgets(
        self, owner: str = "", owner_type: str = ""
    ) -> List[Dict]:
        """List budgets with optional filters."""
        results = []
        for b in self._budgets.values():
            if owner and b.owner != owner:
                continue
            if owner_type and b.owner_type != owner_type:
                continue
            self._check_period_reset(b)
            results.append({
                "budget_id": b.budget_id,
                "name": b.name,
                "owner": b.owner,
                "limit": b.limit,
                "spent": b.spent,
                "remaining": b.remaining,
            })
        return results

    # --- Analytics ---

    def get_owner_total(self, owner: str) -> float:
        """Get total cost for an owner."""
        total = 0.0
        for e in self._entries.values():
            if e.owner == owner:
                total += e.total_cost
        return total

    def get_cost_by_resource(self, owner: str = "") -> Dict[str, float]:
        """Get cost breakdown by resource type."""
        breakdown: Dict[str, float] = {}
        for e in self._entries.values():
            if owner and e.owner != owner:
                continue
            breakdown[e.resource_type] = breakdown.get(e.resource_type, 0.0) + e.total_cost
        return breakdown

    def get_cost_by_pipeline(self, limit: int = 10) -> List[Dict]:
        """Get cost per pipeline."""
        pipeline_costs: Dict[str, float] = {}
        for e in self._entries.values():
            if e.pipeline_id:
                pipeline_costs[e.pipeline_id] = pipeline_costs.get(e.pipeline_id, 0.0) + e.total_cost
        results = [{"pipeline_id": k, "total_cost": v} for k, v in pipeline_costs.items()]
        results.sort(key=lambda x: x["total_cost"], reverse=True)
        return results[:limit]

    def get_top_spenders(self, limit: int = 10) -> List[Dict]:
        """Get top cost owners."""
        owner_costs: Dict[str, float] = {}
        for e in self._entries.values():
            owner_costs[e.owner] = owner_costs.get(e.owner, 0.0) + e.total_cost
        results = [{"owner": k, "total_cost": v} for k, v in owner_costs.items()]
        results.sort(key=lambda x: x["total_cost"], reverse=True)
        return results[:limit]

    def get_over_budget(self) -> List[Dict]:
        """Get budgets that are over limit."""
        over = []
        for b in self._budgets.values():
            self._check_period_reset(b)
            if b.spent > b.limit:
                over.append({
                    "budget_id": b.budget_id,
                    "name": b.name,
                    "owner": b.owner,
                    "limit": b.limit,
                    "spent": b.spent,
                    "overage": b.spent - b.limit,
                })
        return over

    def get_owner_summary(self, owner: str) -> Dict:
        """Get cost summary for an owner."""
        entries = [e for e in self._entries.values() if e.owner == owner]
        if not entries:
            return {}
        total = sum(e.total_cost for e in entries)
        by_resource: Dict[str, float] = {}
        for e in entries:
            by_resource[e.resource_type] = by_resource.get(e.resource_type, 0.0) + e.total_cost
        budgets = [b for b in self._budgets.values() if b.owner == owner]
        return {
            "owner": owner,
            "entry_count": len(entries),
            "total_cost": total,
            "cost_by_resource": by_resource,
            "budget_count": len(budgets),
            "total_budget_limit": sum(b.limit for b in budgets),
            "total_budget_spent": sum(b.spent for b in budgets),
        }

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

    def get_stats(self) -> Dict:
        """Get tracker stats."""
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_budgets": len(self._budgets),
        }

    def reset(self) -> None:
        """Reset everything."""
        self._entries.clear()
        self._budgets.clear()
        self._callbacks.clear()
        self._stats = {
            "total_entries": 0,
            "total_cost": 0.0,
            "total_budgets_created": 0,
            "total_budget_exceeded": 0,
        }

    # --- Internal ---

    def _check_period_reset(self, b: Budget) -> None:
        """Auto-reset budget if period expired."""
        if b.period_seconds <= 0:
            return
        now = time.time()
        if now - b.period_start >= b.period_seconds:
            b.spent = 0.0
            b.remaining = b.limit
            b.period_start = now

    def _fire(self, action: str, data: Dict) -> None:
        """Fire callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
