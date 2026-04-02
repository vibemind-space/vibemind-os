"""Agent workflow monitor - monitors agent workflow health, tracks active workflows, detects stalls, reports status."""

import hashlib
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowMonitorState:
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowMonitor:
    PREFIX = "awmo-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowMonitorState()
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

    def start_monitoring(self, agent_id, workflow_name, timeout_seconds=300) -> str:
        now = time.time()
        monitor_id = self._generate_id(f"{agent_id}:{workflow_name}:{now}")
        entry = {
            "monitor_id": monitor_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "timeout_seconds": timeout_seconds,
            "started_at": now,
            "status": "active",
            "heartbeat_at": now,
            "created_at": now,
        }
        self._state.entries[monitor_id] = entry
        self._prune()
        self._fire("start_monitoring", entry)
        return monitor_id

    def heartbeat(self, monitor_id) -> bool:
        entry = self._state.entries.get(monitor_id)
        if entry is None:
            return False
        entry["heartbeat_at"] = time.time()
        self._fire("heartbeat", entry)
        return True

    def complete_monitoring(self, monitor_id, status="success") -> bool:
        entry = self._state.entries.get(monitor_id)
        if entry is None:
            return False
        entry["status"] = status
        self._fire("complete_monitoring", entry)
        return True

    def get_monitor(self, monitor_id) -> dict:
        entry = self._state.entries.get(monitor_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_monitors(self, agent_id="", status="") -> list:
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def get_stalled(self, timeout_override=0) -> list:
        now = time.time()
        results = []
        for entry in self._state.entries.values():
            if entry["status"] != "active":
                continue
            timeout = timeout_override if timeout_override > 0 else entry["timeout_seconds"]
            if (now - entry["heartbeat_at"]) > timeout:
                results.append(dict(entry))
        return results

    def get_active_count(self, agent_id="") -> int:
        count = 0
        for entry in self._state.entries.values():
            if entry["status"] != "active":
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            count += 1
        return count

    def get_monitor_count(self, agent_id="") -> int:
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        total = len(self._state.entries)
        active = 0
        completed = 0
        stalled = self.get_stalled()
        for entry in self._state.entries.values():
            if entry["status"] == "active":
                active += 1
            elif entry["status"] in ("success", "failed", "completed"):
                completed += 1
        return {
            "total_monitors": total,
            "active": active,
            "completed": completed,
            "stalled_count": len(stalled),
        }

    def reset(self):
        self._state = AgentWorkflowMonitorState()
        self._callbacks = {}
        self._on_change = None
        self._fire("reset", {})
