"""Agent Task Estimator -- estimates task effort/duration for planning.

Stores estimation records with effort, unit, confidence, and metadata.
Supports querying, filtering, updating, and aggregate stats.

Usage::

    estimator = AgentTaskEstimator()

    # Create an estimate
    eid = estimator.estimate("task-1", "agent-a", effort=3.0, unit="hours")

    # Query
    entry = estimator.get_estimate(eid)
    entries = estimator.get_estimates(agent_id="agent-a")
    stats = estimator.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskEstimatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskEstimator:
    """Estimates task effort/duration for planning."""

    PREFIX = "ates-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskEstimatorState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Estimation operations
    # ------------------------------------------------------------------

    def estimate(
        self,
        task_id: str,
        agent_id: str,
        effort: float = 1.0,
        unit: str = "hours",
        confidence: float = 0.5,
        metadata: dict = None,
    ) -> str:
        """Create an estimate for a task.

        Returns the estimate ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        estimate_id = self._generate_id()
        self._state.entries[estimate_id] = {
            "estimate_id": estimate_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "effort": effort,
            "unit": unit,
            "confidence": confidence,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("estimated", self._state.entries[estimate_id])
        logger.debug(
            "Task estimated: %s (task=%s, agent=%s, effort=%s %s)",
            estimate_id,
            task_id,
            agent_id,
            effort,
            unit,
        )
        return estimate_id

    def get_estimate(self, estimate_id: str) -> Optional[dict]:
        """Return the estimate entry or None."""
        entry = self._state.entries.get(estimate_id)
        return dict(entry) if entry else None

    def get_estimates(
        self, agent_id: str = "", task_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query estimates, newest first.

        Optionally filter by agent_id and/or task_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if task_id and entry["task_id"] != task_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def update_estimate(
        self, estimate_id: str, effort: float = None, confidence: float = None
    ) -> bool:
        """Update the effort and/or confidence of an existing estimate."""
        entry = self._state.entries.get(estimate_id)
        if entry is None:
            return False
        if effort is not None:
            entry["effort"] = effort
        if confidence is not None:
            entry["confidence"] = confidence
        self._fire("estimate_updated", dict(entry))
        logger.debug("Estimate updated: %s", estimate_id)
        return True

    def get_estimate_count(self, agent_id: str = "") -> int:
        """Return the number of estimates, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if e["agent_id"] == agent_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        entries = list(self._state.entries.values())
        total = len(entries)
        if total == 0:
            return {
                "total_estimates": 0,
                "avg_effort": 0.0,
                "avg_confidence": 0.0,
                "unique_agents": 0,
            }
        avg_effort = sum(e["effort"] for e in entries) / total
        avg_confidence = sum(e["confidence"] for e in entries) / total
        unique_agents = len({e["agent_id"] for e in entries})
        return {
            "total_estimates": total,
            "avg_effort": round(avg_effort, 2),
            "avg_confidence": round(avg_confidence, 2),
            "unique_agents": unique_agents,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskEstimatorState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskEstimator reset")
