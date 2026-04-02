import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentExecutionTrackerV2State:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentExecutionTrackerV2:
    PREFIX = "aet2-"

    def __init__(self):
        self._state = AgentExecutionTrackerV2State()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > 10000:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = sorted_keys[: len(sorted_keys) - 10000]
            for k in to_remove:
                del self._state.entries[k]

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._callbacks.pop(cb_id, None) is not None

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.warning("Callback error: %s", e)

    def start_execution(self, agent_id: str, task_name: str, phases=None) -> str:
        execution_id = self._generate_id(f"{agent_id}-{task_name}-{time.time()}")
        entry = {
            "execution_id": execution_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "phases": phases or [],
            "current_phase_index": -1,
            "status": "running",
            "created_at": time.time(),
            "started_at": time.time(),
            "completed_at": None,
        }
        self._state.entries[execution_id] = entry
        self._prune()
        self._fire("execution_started", entry)
        return execution_id

    def advance_phase(self, execution_id: str) -> dict:
        entry = self._state.entries.get(execution_id)
        if entry is None:
            raise KeyError(f"Execution not found: {execution_id}")
        phases = entry.get("phases", [])
        if not phases:
            raise ValueError("No phases defined for this execution")
        new_index = entry["current_phase_index"] + 1
        if new_index >= len(phases):
            raise ValueError("All phases already completed")
        entry["current_phase_index"] = new_index
        result = {
            "phase_name": phases[new_index],
            "phase_index": new_index,
            "total_phases": len(phases),
        }
        self._fire("phase_advanced", {"execution_id": execution_id, **result})
        return result

    def complete_execution(self, execution_id: str, status: str = "success") -> dict:
        entry = self._state.entries.get(execution_id)
        if entry is None:
            raise KeyError(f"Execution not found: {execution_id}")
        entry["status"] = status
        entry["completed_at"] = time.time()
        duration_ms = (entry["completed_at"] - entry["started_at"]) * 1000
        phases = entry.get("phases", [])
        phases_completed = entry["current_phase_index"] + 1 if phases else 0
        result = {
            "execution_id": execution_id,
            "duration_ms": duration_ms,
            "phases_completed": phases_completed,
        }
        self._fire("execution_completed", result)
        return result

    def get_execution(self, execution_id: str):
        entry = self._state.entries.get(execution_id)
        if entry is None:
            return None
        return dict(entry)

    def get_current_phase(self, execution_id: str):
        entry = self._state.entries.get(execution_id)
        if entry is None:
            return None
        phases = entry.get("phases", [])
        idx = entry.get("current_phase_index", -1)
        if idx < 0 or idx >= len(phases):
            return None
        return phases[idx]

    def get_executions(self, agent_id: str, status: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_execution_count(self, agent_id: str = "") -> int:
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
        by_status: dict = {}
        for entry in self._state.entries.values():
            s = entry["status"]
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_executions": total,
            "by_status": by_status,
            "agents": len(self.list_agents()),
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state = AgentExecutionTrackerV2State()
        self._callbacks.clear()
        self._fire("reset", {})
