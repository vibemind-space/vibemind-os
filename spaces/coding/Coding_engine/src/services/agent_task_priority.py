"""Manage task priorities within an agent's task queue with dynamic re-prioritization."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class AgentTaskPriorityState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentTaskPriority:
    ID_PREFIX = "atp-"

    def __init__(self):
        self._state = AgentTaskPriorityState()
        self._callbacks: dict = {}

    # --- ID generation ---

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_part}"

    # --- Callbacks ---

    def on_change(self, name: str, fn) -> None:
        self._callbacks[name] = fn

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as exc:
                logger.warning("Callback error: %s", exc)

    # --- Pruning ---

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= MAX_ENTRIES:
            return
        completed = [
            (tid, e) for tid, e in entries.items() if e["status"] == "completed"
        ]
        completed.sort(key=lambda x: x[1].get("completed_at", 0))
        while len(entries) > MAX_ENTRIES and completed:
            tid, _ = completed.pop(0)
            del entries[tid]

    # --- API ---

    def add_task(self, agent_id: str, task_name: str, priority: int = 0, metadata=None) -> str:
        task_id = self._generate_id(f"{agent_id}{task_name}{time.time()}")
        entry = {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "priority": priority,
            "metadata": metadata or {},
            "status": "pending",
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
        }
        self._state.entries[task_id] = entry
        self._prune()
        self._fire("task_added", entry)
        logger.debug("Task added: %s for agent %s", task_id, agent_id)
        return task_id

    def get_next(self, agent_id: str):
        pending = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["status"] == "pending"
        ]
        if not pending:
            return None
        pending.sort(key=lambda e: (-e["priority"], e["created_at"]))
        task = pending[0]
        task["status"] = "in_progress"
        task["started_at"] = time.time()
        self._fire("task_started", task)
        return dict(task)

    def complete_task(self, task_id: str) -> bool:
        entry = self._state.entries.get(task_id)
        if entry is None or entry["status"] == "completed":
            return False
        entry["status"] = "completed"
        entry["completed_at"] = time.time()
        self._fire("task_completed", entry)
        return True

    def reprioritize(self, task_id: str, new_priority: int) -> bool:
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        old_priority = entry["priority"]
        entry["priority"] = new_priority
        self._fire("task_reprioritized", {**entry, "old_priority": old_priority})
        return True

    def get_task(self, task_id: str):
        entry = self._state.entries.get(task_id)
        if entry is None:
            return None
        return dict(entry)

    def get_tasks(self, agent_id: str, status: str = "") -> list:
        results = [
            dict(e) for e in self._state.entries.values()
            if e["agent_id"] == agent_id and (not status or e["status"] == status)
        ]
        return results

    def get_task_count(self, agent_id: str = "", status: str = "") -> int:
        count = 0
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            if status and e["status"] != status:
                continue
            count += 1
        return count

    def list_agents(self) -> list:
        agents = set()
        for e in self._state.entries.values():
            agents.add(e["agent_id"])
        return sorted(agents)

    # --- Stats / Reset ---

    def get_stats(self) -> dict:
        entries = self._state.entries
        statuses: dict = {}
        agents: set = set()
        for e in entries.values():
            statuses[e["status"]] = statuses.get(e["status"], 0) + 1
            agents.add(e["agent_id"])
        return {
            "total_tasks": len(entries),
            "agents": len(agents),
            "statuses": statuses,
            "callbacks": len(self._callbacks),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = AgentTaskPriorityState()
        self._callbacks.clear()
        logger.debug("AgentTaskPriority reset")
