"""Agent workflow planner - plans workflow execution sequences."""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowPlannerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowPlanner:
    PREFIX = "awpl-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowPlannerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                oldest = sorted_keys.pop(0)
                del self._state.entries[oldest]

    def _fire(self, action, data):
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                pass

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        self._on_change = value

    def remove_callback(self, name) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def create_plan(self, agent_id: str, workflow_name: str, steps: List[str], strategy: str = "sequential", metadata: dict = None) -> str:
        now = time.time()
        plan_id = self._generate_id(f"{agent_id}:{workflow_name}:{strategy}:{now}")
        entry = {
            "plan_id": plan_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "steps": list(steps),
            "strategy": strategy,
            "metadata": metadata or {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[plan_id] = entry
        self._prune()
        self._fire("create_plan", entry)
        return plan_id

    def get_plan(self, plan_id: str) -> Optional[dict]:
        return self._state.entries.get(plan_id)

    def update_plan(self, plan_id: str, steps: List[str] = None, strategy: str = "") -> bool:
        entry = self._state.entries.get(plan_id)
        if entry is None:
            return False
        if steps is not None:
            entry["steps"] = list(steps)
        if strategy:
            entry["strategy"] = strategy
        self._fire("update_plan", entry)
        return True

    def get_plans(self, agent_id: str = "", workflow_name: str = "", limit: int = 50) -> List[dict]:
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry.get("agent_id") != agent_id:
                continue
            if workflow_name and entry.get("workflow_name") != workflow_name:
                continue
            results.append(entry)
        results.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_plan_count(self, agent_id: str = "") -> int:
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry.get("agent_id") != agent_id:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        entries = self._state.entries.values()
        by_strategy: Dict[str, int] = {}
        agents = set()
        for e in entries:
            s = e.get("strategy", "")
            by_strategy[s] = by_strategy.get(s, 0) + 1
            agents.add(e.get("agent_id"))
        result = {
            "total_plans": len(self._state.entries),
            "unique_agents": len(agents),
            "by_strategy": by_strategy,
        }
        self._fire("get_stats", result)
        return result

    def reset(self) -> None:
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
