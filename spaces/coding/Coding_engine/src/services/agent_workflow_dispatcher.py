"""Dispatches workflow tasks to target agents."""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000

VALID_PRIORITIES = ("low", "normal", "high", "critical")


@dataclasses.dataclass
class AgentWorkflowDispatcherState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowDispatcher:
    """Dispatches workflow tasks to target agents."""

    PREFIX = "awdi-"
    MAX_ENTRIES = MAX_ENTRIES

    def __init__(self):
        self._state = AgentWorkflowDispatcherState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None
        self._created_at = time.time()
        logger.info("AgentWorkflowDispatcher initialized")

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self, data: str = "") -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Callbacks ──────────────────────────────────────────────────

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception as exc:
                logger.error("Callback error: %s", exc)
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception as exc:
                logger.error("on_change error: %s", exc)

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    # ── API ────────────────────────────────────────────────────────

    def dispatch(
        self,
        workflow_id: str,
        agent_id: str,
        task: str,
        priority: str = "normal",
        metadata: dict = None,
    ) -> str:
        """Create a dispatch record assigning a task to an agent."""
        if priority not in VALID_PRIORITIES:
            priority = "normal"
        dispatch_id = self._generate_id(f"{workflow_id}:{agent_id}:{task}")
        entry = {
            "dispatch_id": dispatch_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "task": task,
            "priority": priority,
            "metadata": metadata or {},
            "status": "pending",
            "result": "",
            "completed_at": None,
            "created_at": time.time(),
        }
        self._state.entries[dispatch_id] = entry
        self._prune()
        self._fire("dispatch", entry)
        logger.info(
            "Dispatched %s to agent %s for workflow %s",
            dispatch_id,
            agent_id,
            workflow_id,
        )
        return dispatch_id

    def get_dispatch(self, dispatch_id: str) -> Optional[dict]:
        """Return a single dispatch record or None."""
        return self._state.entries.get(dispatch_id)

    def get_dispatches(
        self,
        workflow_id: str = "",
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return dispatches filtered by workflow and/or agent, newest first."""
        results = []
        for entry in self._state.entries.values():
            if workflow_id and entry["workflow_id"] != workflow_id:
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(entry)
        results.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        return results[:limit]

    def complete_dispatch(self, dispatch_id: str, result: str = "") -> bool:
        """Mark a dispatch as completed."""
        entry = self._state.entries.get(dispatch_id)
        if entry is None:
            return False
        entry["status"] = "completed"
        entry["result"] = result
        entry["completed_at"] = time.time()
        self._fire("complete_dispatch", entry)
        logger.info("Completed dispatch %s", dispatch_id)
        return True

    def get_dispatch_count(self, workflow_id: str = "", agent_id: str = "") -> int:
        """Count dispatches, optionally filtered."""
        if not workflow_id and not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if workflow_id and entry["workflow_id"] != workflow_id:
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total = len(self._state.entries)
        completed_count = sum(
            1 for e in self._state.entries.values() if e["status"] == "completed"
        )
        by_priority: Dict[str, int] = {}
        for e in self._state.entries.values():
            p = e["priority"]
            by_priority[p] = by_priority.get(p, 0) + 1
        return {
            "total_dispatches": total,
            "completed_count": completed_count,
            "by_priority": by_priority,
            "seq": self._state._seq,
            "uptime": time.time() - self._created_at,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowDispatcherState()
        self._callbacks.clear()
        self._on_change = None
        self._created_at = time.time()
        logger.info("AgentWorkflowDispatcher reset")
