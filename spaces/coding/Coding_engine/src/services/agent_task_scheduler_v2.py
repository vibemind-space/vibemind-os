"""Enhanced task scheduler for agents with priority queuing, deadline tracking, and slot-based concurrency."""

import hashlib
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskSchedulerV2State:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentTaskSchedulerV2:
    PREFIX = "ats2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentTaskSchedulerV2State()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
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
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event, data):
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change callback error: %s", e)
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("callback '%s' error: %s", name, e)

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

    def schedule_task(self, agent_id, task_name, priority=5, deadline=0, metadata=None) -> str:
        task_id = self._generate_id(f"{agent_id}{task_name}")
        entry = {
            "task_id": task_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "priority": priority,
            "deadline": deadline,
            "status": "queued",
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "metadata": metadata,
        }
        self._state.entries[task_id] = entry
        self._prune()
        self._fire("task_scheduled", entry)
        return task_id

    def start_task(self, task_id) -> bool:
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        entry["status"] = "running"
        entry["started_at"] = time.time()
        self._fire("task_started", entry)
        return True

    def complete_task(self, task_id, result=None) -> bool:
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        entry["status"] = "completed"
        entry["completed_at"] = time.time()
        if result is not None:
            entry["result"] = result
        self._fire("task_completed", entry)
        return True

    def fail_task(self, task_id, error="") -> bool:
        entry = self._state.entries.get(task_id)
        if entry is None:
            return False
        entry["status"] = "failed"
        entry["error"] = error
        self._fire("task_failed", entry)
        return True

    def get_task(self, task_id) -> dict:
        return self._state.entries.get(task_id)

    def get_tasks(self, agent_id, status="") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(entry)
        return results

    def get_next_task(self, agent_id) -> dict:
        queued = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["status"] == "queued"
        ]
        if not queued:
            return None
        return min(queued, key=lambda e: e["priority"])

    def get_overdue_tasks(self) -> list:
        now = time.time()
        return [
            e for e in self._state.entries.values()
            if e["deadline"] > 0 and e["deadline"] < now and e["status"] in ("queued", "running")
        ]

    def get_task_count(self, agent_id="", status="") -> int:
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        stats = {"total_tasks": 0, "queued": 0, "running": 0, "completed": 0, "failed": 0}
        for entry in self._state.entries.values():
            stats["total_tasks"] += 1
            s = entry["status"]
            if s in stats:
                stats[s] += 1
        return stats

    def reset(self):
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._on_change = None
