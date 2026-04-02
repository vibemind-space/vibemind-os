"""Agent workflow scheduler - schedules workflow executions with cron-like scheduling, delays, and recurring patterns."""

import hashlib
import time
from dataclasses import dataclass, field


@dataclass
class AgentWorkflowSchedulerState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowScheduler:
    PREFIX = "aws2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowSchedulerState()
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
                oldest = sorted_keys.pop(0)
                del self._state.entries[oldest]

    def _fire(self, event, data):
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                pass
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
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

    def schedule_workflow(
        self,
        agent_id,
        workflow_name,
        interval_seconds=0,
        delay_seconds=0,
        max_runs=0,
        metadata=None,
    ) -> str:
        now = time.time()
        schedule_id = self._generate_id(f"{agent_id}:{workflow_name}:{now}")
        entry = {
            "schedule_id": schedule_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "interval_seconds": interval_seconds,
            "delay_seconds": delay_seconds,
            "max_runs": max_runs,
            "run_count": 0,
            "status": "scheduled",
            "created_at": now,
            "next_run_at": now + delay_seconds,
            "metadata": metadata,
        }
        self._state.entries[schedule_id] = entry
        self._prune()
        self._fire("schedule_workflow", entry)
        return schedule_id

    def trigger_workflow(self, schedule_id) -> dict:
        entry = self._state.entries.get(schedule_id)
        if entry is None:
            raise KeyError(f"Schedule not found: {schedule_id}")
        entry["run_count"] += 1
        entry["last_run_at"] = time.time()
        if entry["interval_seconds"] > 0:
            entry["next_run_at"] = time.time() + entry["interval_seconds"]
        else:
            entry["next_run_at"] = 0
        if entry["max_runs"] > 0 and entry["run_count"] >= entry["max_runs"]:
            entry["status"] = "completed"
        result = {
            "schedule_id": schedule_id,
            "workflow_name": entry["workflow_name"],
            "run_count": entry["run_count"],
            "status": entry["status"],
        }
        self._fire("trigger_workflow", result)
        return result

    def get_schedule(self, schedule_id) -> dict:
        entry = self._state.entries.get(schedule_id)
        if entry is None:
            raise KeyError(f"Schedule not found: {schedule_id}")
        return dict(entry)

    def get_schedules(self, agent_id) -> list:
        return [
            dict(e)
            for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        ]

    def pause_schedule(self, schedule_id) -> bool:
        entry = self._state.entries.get(schedule_id)
        if entry is None:
            return False
        entry["status"] = "paused"
        self._fire("pause_schedule", {"schedule_id": schedule_id})
        return True

    def resume_schedule(self, schedule_id) -> bool:
        entry = self._state.entries.get(schedule_id)
        if entry is None:
            return False
        entry["status"] = "scheduled"
        self._fire("resume_schedule", {"schedule_id": schedule_id})
        return True

    def cancel_schedule(self, schedule_id) -> bool:
        entry = self._state.entries.get(schedule_id)
        if entry is None:
            return False
        entry["status"] = "cancelled"
        self._fire("cancel_schedule", {"schedule_id": schedule_id})
        return True

    def get_due_workflows(self) -> list:
        now = time.time()
        return [
            dict(e)
            for e in self._state.entries.values()
            if e["status"] == "scheduled" and e["next_run_at"] <= now
        ]

    def get_schedule_count(self, agent_id="") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        entries = list(self._state.entries.values())
        total_triggers = sum(e["run_count"] for e in entries)
        active = sum(1 for e in entries if e["status"] == "scheduled")
        paused = sum(1 for e in entries if e["status"] == "paused")
        return {
            "total_schedules": len(entries),
            "total_triggers": total_triggers,
            "active_schedules": active,
            "paused_schedules": paused,
        }

    def reset(self):
        self._state = AgentWorkflowSchedulerState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
