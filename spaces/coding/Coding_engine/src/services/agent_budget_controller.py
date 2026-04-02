"""Agent Budget Controller – manages cost budgets for agent operations.

Tracks spending against allocated budgets per agent/project, supports
alerts at threshold levels, and prevents overspending.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Budget:
    budget_id: str
    name: str
    owner: str
    total_budget: float
    spent: float
    reserved: float
    currency: str
    alert_threshold_pct: float
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _BudgetEvent:
    event_id: str
    budget_name: str
    action: str
    amount: float
    timestamp: float


class AgentBudgetController:
    """Manages cost budgets for agent operations."""

    def __init__(self, max_budgets: int = 10000, max_history: int = 100000, default_alert_pct: float = 80.0):
        self._budgets: Dict[str, _Budget] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[_BudgetEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_budgets = max_budgets
        self._max_history = max_history
        self._default_alert_pct = default_alert_pct
        self._seq = 0
        self._total_created = 0
        self._total_charges = 0

    def create_budget(self, name: str, total_budget: float, owner: str = "", currency: str = "USD", alert_threshold_pct: float = 0.0, tags: Optional[List[str]] = None) -> str:
        if not name or total_budget <= 0:
            return ""
        if name in self._name_index or len(self._budgets) >= self._max_budgets:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        bid = "bgt-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        alert = alert_threshold_pct if alert_threshold_pct > 0 else self._default_alert_pct
        budget = _Budget(budget_id=bid, name=name, owner=owner, total_budget=total_budget, spent=0.0, reserved=0.0, currency=currency, alert_threshold_pct=alert, tags=tags or [], created_at=now, updated_at=now)
        self._budgets[bid] = budget
        self._name_index[name] = bid
        self._total_created += 1
        self._record_event(name, "created", total_budget)
        self._fire("budget_created", {"budget_id": bid, "name": name, "total": total_budget})
        return bid

    def charge(self, name: str, amount: float, description: str = "") -> bool:
        bid = self._name_index.get(name)
        if not bid or amount <= 0:
            return False
        b = self._budgets[bid]
        if b.spent + amount > b.total_budget:
            self._fire("budget_exceeded", {"name": name, "amount": amount, "remaining": b.total_budget - b.spent})
            return False
        b.spent += amount
        b.updated_at = time.time()
        self._total_charges += 1
        self._record_event(name, "charged", amount)
        # Check alert threshold
        pct_used = (b.spent / b.total_budget * 100) if b.total_budget > 0 else 0
        if pct_used >= b.alert_threshold_pct:
            self._fire("budget_alert", {"name": name, "pct_used": pct_used, "threshold": b.alert_threshold_pct})
        return True

    def reserve(self, name: str, amount: float) -> bool:
        bid = self._name_index.get(name)
        if not bid or amount <= 0:
            return False
        b = self._budgets[bid]
        if b.spent + b.reserved + amount > b.total_budget:
            return False
        b.reserved += amount
        b.updated_at = time.time()
        self._record_event(name, "reserved", amount)
        return True

    def release_reservation(self, name: str, amount: float) -> bool:
        bid = self._name_index.get(name)
        if not bid or amount <= 0:
            return False
        b = self._budgets[bid]
        b.reserved = max(0.0, b.reserved - amount)
        b.updated_at = time.time()
        return True

    def get_remaining(self, name: str) -> float:
        bid = self._name_index.get(name)
        if not bid:
            return 0.0
        b = self._budgets[bid]
        return b.total_budget - b.spent - b.reserved

    def get_budget(self, name: str) -> Optional[Dict[str, Any]]:
        bid = self._name_index.get(name)
        if not bid:
            return None
        b = self._budgets[bid]
        pct = (b.spent / b.total_budget * 100) if b.total_budget > 0 else 0
        return {"budget_id": b.budget_id, "name": b.name, "owner": b.owner, "total_budget": b.total_budget, "spent": b.spent, "reserved": b.reserved, "remaining": b.total_budget - b.spent - b.reserved, "pct_used": pct, "currency": b.currency, "alert_threshold_pct": b.alert_threshold_pct, "tags": list(b.tags), "created_at": b.created_at, "updated_at": b.updated_at}

    def increase_budget(self, name: str, amount: float) -> bool:
        bid = self._name_index.get(name)
        if not bid or amount <= 0:
            return False
        self._budgets[bid].total_budget += amount
        self._budgets[bid].updated_at = time.time()
        self._record_event(name, "increased", amount)
        return True

    def remove_budget(self, name: str) -> bool:
        bid = self._name_index.pop(name, None)
        if not bid:
            return False
        self._budgets.pop(bid, None)
        return True

    def list_budgets(self, owner: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for b in self._budgets.values():
            if owner and b.owner != owner:
                continue
            if tag and tag not in b.tags:
                continue
            results.append(self.get_budget(b.name))
        return [r for r in results if r]

    def get_history(self, budget_name: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if budget_name and ev.budget_name != budget_name:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "budget_name": ev.budget_name, "action": ev.action, "amount": ev.amount, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, budget_name: str, action: str, amount: float) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{budget_name}-{action}-{now}-{self._seq}"
        evid = "bev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _BudgetEvent(event_id=evid, budget_name=budget_name, action=action, amount=amount, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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

    def get_stats(self) -> Dict[str, Any]:
        total_budget = sum(b.total_budget for b in self._budgets.values())
        total_spent = sum(b.spent for b in self._budgets.values())
        return {"current_budgets": len(self._budgets), "total_budget": total_budget, "total_spent": total_spent, "total_created": self._total_created, "total_charges": self._total_charges, "history_size": len(self._history)}

    def reset(self) -> None:
        self._budgets.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_charges = 0
