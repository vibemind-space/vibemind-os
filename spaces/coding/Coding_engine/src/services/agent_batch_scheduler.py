"""Schedule and manage batches of tasks for agents."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class AgentBatchSchedulerState:
    entries: dict
    _seq: int = 0


class AgentBatchScheduler:
    def __init__(self):
        self._state = AgentBatchSchedulerState(entries={})
        self._callbacks = {}

    def _next_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self._state._seq += 1
        return f"abs-{h}"

    def on_change(self, name: str, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail_dict: dict):
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error("Callback %s failed: %s", name, e)

    def _prune(self):
        entries = self._state.entries
        if len(entries) > MAX_ENTRIES:
            sorted_keys = sorted(entries, key=lambda k: entries[k].get("created_at", 0))
            to_remove = len(entries) - MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del entries[key]
            logger.info("Pruned %d entries", to_remove)

    def create_batch(self, agent_id: str, tasks: list, priority: int = 0) -> str:
        batch_id = self._next_id(f"{agent_id}{tasks}")
        now = time.time()
        entry = {
            "batch_id": batch_id,
            "agent_id": agent_id,
            "tasks": [{"index": i, "data": t, "completed": False, "result": None} for i, t in enumerate(tasks)],
            "priority": priority,
            "status": "pending",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }
        self._state.entries[batch_id] = entry
        self._prune()
        self._fire("create_batch", {"batch_id": batch_id, "agent_id": agent_id})
        logger.info("Created batch %s for agent %s with %d tasks", batch_id, agent_id, len(tasks))
        return batch_id

    def start_batch(self, batch_id: str) -> bool:
        entry = self._state.entries.get(batch_id)
        if not entry:
            return False
        if entry["status"] != "pending":
            return False
        entry["status"] = "running"
        entry["started_at"] = time.time()
        self._fire("start_batch", {"batch_id": batch_id})
        logger.info("Started batch %s", batch_id)
        return True

    def complete_task(self, batch_id: str, task_index: int, result=None) -> bool:
        entry = self._state.entries.get(batch_id)
        if not entry:
            return False
        if task_index < 0 or task_index >= len(entry["tasks"]):
            return False
        task = entry["tasks"][task_index]
        if task["completed"]:
            return False
        task["completed"] = True
        task["result"] = result
        self._fire("complete_task", {"batch_id": batch_id, "task_index": task_index})
        logger.info("Completed task %d in batch %s", task_index, batch_id)
        return True

    def get_batch(self, batch_id: str) -> dict | None:
        entry = self._state.entries.get(batch_id)
        if not entry:
            return None
        return dict(entry)

    def get_progress(self, batch_id: str) -> dict:
        entry = self._state.entries.get(batch_id)
        if not entry:
            return {"total": 0, "completed": 0, "remaining": 0, "percent": 0.0}
        total = len(entry["tasks"])
        completed = sum(1 for t in entry["tasks"] if t["completed"])
        remaining = total - completed
        percent = (completed / total * 100.0) if total > 0 else 0.0
        return {"total": total, "completed": completed, "remaining": remaining, "percent": percent}

    def complete_batch(self, batch_id: str) -> bool:
        entry = self._state.entries.get(batch_id)
        if not entry:
            return False
        if entry["status"] == "completed":
            return False
        entry["status"] = "completed"
        entry["completed_at"] = time.time()
        self._fire("complete_batch", {"batch_id": batch_id})
        logger.info("Completed batch %s", batch_id)
        return True

    def get_batches(self, agent_id: str, status: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_batch_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        total = len(self._state.entries)
        by_status = {}
        for entry in self._state.entries.values():
            s = entry["status"]
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_batches": total,
            "by_status": by_status,
            "total_agents": len(self.list_agents()),
            "seq": self._state._seq,
        }

    def reset(self):
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("Reset agent batch scheduler")
