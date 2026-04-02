"""Agent Task Result Store -- stores and retrieves results from agent task executions.

Provides an in-memory store for recording agent task outcomes including
status, metadata, and timestamps.  Supports querying by agent, task name,
and status with automatic pruning when capacity is reached.

Usage::

    store = AgentTaskResultStore()

    result_id = store.store_result("agent-1", "code_review", {"score": 95})
    result = store.get_result(result_id)
    latest = store.get_latest_result("agent-1", "code_review")
    stats = store.get_stats()
"""

import hashlib
import logging
import time
import dataclasses

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentTaskResultStoreState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentTaskResultStore:
    """In-memory store for agent task execution results."""

    PREFIX = "atrs-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentTaskResultStoreState()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{h}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, fn):
        self._on_change = fn

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def store_result(self, agent_id: str, task_name: str, result, status: str = "success", metadata=None) -> str:
        """Store a task result and return its unique ID."""
        result_id = self._generate_id(f"{agent_id}:{task_name}:{time.time()}")
        entry = {
            "result_id": result_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "result": result,
            "status": status,
            "metadata": metadata or {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[result_id] = entry
        self._prune()
        self._fire("result_stored", entry)
        return result_id

    def get_result(self, result_id: str) -> dict:
        """Return a stored result by ID, or None if not found."""
        return self._state.entries.get(result_id)

    def get_results(self, agent_id: str, task_name: str = "", status: str = "", limit: int = 50) -> list:
        """Query results with optional filters, newest first."""
        results = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
            and (not task_name or e["task_name"] == task_name)
            and (not status or e["status"] == status)
        ]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_latest_result(self, agent_id: str, task_name: str) -> dict:
        """Return the most recent result for an agent+task, or None."""
        matches = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["task_name"] == task_name
        ]
        if not matches:
            return None
        return max(matches, key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)))

    def get_result_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of results matching optional filters."""
        if not agent_id and not status:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if (not agent_id or e["agent_id"] == agent_id)
            and (not status or e["status"] == status)
        )

    def remove_result(self, result_id: str) -> bool:
        """Remove a single result by ID. Return True if it existed."""
        if result_id in self._state.entries:
            del self._state.entries[result_id]
            self._fire("result_removed", {"result_id": result_id})
            return True
        return False

    def clear_results(self, agent_id: str) -> int:
        """Remove all results for an agent. Return count removed."""
        to_remove = [
            k for k, v in self._state.entries.items()
            if v["agent_id"] == agent_id
        ]
        for k in to_remove:
            del self._state.entries[k]
        if to_remove:
            self._fire("results_cleared", {"agent_id": agent_id, "count": len(to_remove)})
        return len(to_remove)

    def get_stats(self) -> dict:
        """Return summary statistics."""
        entries = list(self._state.entries.values())
        agents = set(e["agent_id"] for e in entries)
        success_count = sum(1 for e in entries if e["status"] == "success")
        error_count = sum(1 for e in entries if e["status"] == "error")
        return {
            "total_results": len(entries),
            "unique_agents": len(agents),
            "success_count": success_count,
            "error_count": error_count,
        }

    def reset(self):
        """Clear all state."""
        self._state = AgentTaskResultStoreState()
        self._callbacks = {}
        self._on_change = None
