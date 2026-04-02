"""Agent task budget service for tracking resource budgets for agent tasks."""

import time
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskBudgetState:
    """State container for agent task budgets."""
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskBudget:
    """Tracks resource budgets for agent tasks."""

    PREFIX = "atbu-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskBudgetState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

    def _fire(self, action: str, data: Any = None) -> None:
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("Callback %s error", cb_id)

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def register_callback(self, callback_id: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def create_budget(self, task_id: str, agent_id: str, limit: float = 100.0, unit: str = "credits") -> str:
        """Create a new budget for a task. Returns budget_id."""
        budget_id = self._generate_id(f"{task_id}{agent_id}")
        self._state.entries[budget_id] = {
            "budget_id": budget_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "limit": limit,
            "spent": 0.0,
            "unit": unit,
            "transactions": [],
            "created_at": time.time(),
        }
        self._prune()
        self._fire("budget_created", {"budget_id": budget_id, "task_id": task_id, "agent_id": agent_id, "limit": limit, "unit": unit})
        logger.info("Created budget %s for task %s agent %s (limit=%.2f %s)", budget_id, task_id, agent_id, limit, unit)
        return budget_id

    def spend(self, budget_id: str, amount: float, description: str = "") -> bool:
        """Deduct from a budget. Returns False if budget not found or insufficient funds."""
        entry = self._state.entries.get(budget_id)
        if entry is None:
            logger.warning("Budget %s not found", budget_id)
            return False
        remaining = entry["limit"] - entry["spent"]
        if amount > remaining:
            logger.warning("Budget %s insufficient: need %.2f, have %.2f", budget_id, amount, remaining)
            return False
        entry["spent"] += amount
        entry["transactions"].append({
            "amount": amount,
            "description": description,
            "timestamp": time.time(),
        })
        self._fire("budget_spent", {"budget_id": budget_id, "amount": amount, "description": description, "remaining": entry["limit"] - entry["spent"]})
        return True

    def get_budget(self, budget_id: str) -> Optional[dict]:
        """Get budget info. Returns None if not found."""
        entry = self._state.entries.get(budget_id)
        if entry is None:
            return None
        return {
            "budget_id": entry["budget_id"],
            "task_id": entry["task_id"],
            "agent_id": entry["agent_id"],
            "limit": entry["limit"],
            "spent": entry["spent"],
            "remaining": entry["limit"] - entry["spent"],
            "unit": entry["unit"],
            "transactions": list(entry["transactions"]),
            "created_at": entry["created_at"],
        }

    def get_budgets(self, agent_id: str = "", task_id: str = "", limit: int = 50) -> List[dict]:
        """Get budgets filtered by agent_id and/or task_id, newest first."""
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if task_id and entry["task_id"] != task_id:
                continue
            results.append({
                "budget_id": entry["budget_id"],
                "task_id": entry["task_id"],
                "agent_id": entry["agent_id"],
                "limit": entry["limit"],
                "spent": entry["spent"],
                "remaining": entry["limit"] - entry["spent"],
                "unit": entry["unit"],
                "created_at": entry["created_at"],
            })
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    def get_remaining(self, budget_id: str) -> float:
        """Returns remaining budget. Returns -1 if not found."""
        entry = self._state.entries.get(budget_id)
        if entry is None:
            return -1
        return entry["limit"] - entry["spent"]

    def get_budget_count(self, agent_id: str = "") -> int:
        """Get count of budgets, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        """Get statistics about the budget system."""
        total_spent = sum(e["spent"] for e in self._state.entries.values())
        total_remaining = sum(e["limit"] - e["spent"] for e in self._state.entries.values())
        return {
            "total_budgets": len(self._state.entries),
            "total_spent": total_spent,
            "total_remaining": total_remaining,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = AgentTaskBudgetState()
        self._callbacks.clear()
        self._on_change = None
        self._fire("reset", {})
        logger.info("AgentTaskBudget reset")
