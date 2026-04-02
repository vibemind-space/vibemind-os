"""Agent workflow scheduler v2 - schedules agent workflows."""

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowSchedulerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowSchedulerV2:
    PREFIX = "awsv-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowSchedulerV2State()
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        self._state._seq += 1
        raw = f"{data}{self._state._seq}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:12]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k].get("created_at", ""),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(sorted_keys) // 4
            for key in sorted_keys[:quarter]:
                del self._state.entries[key]

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]):
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    def schedule_v2(
        self,
        agent_id: str,
        workflow_name: str,
        interval: int = 60,
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""
        record_id = self._generate_id(f"{agent_id}:{workflow_name}")
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "interval": interval,
            "metadata": copy.deepcopy(metadata) if metadata else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("schedule_v2", agent_id=agent_id, record_id=record_id)
        return record_id

    def get_schedule(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_schedules(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        entries.sort(key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_schedule_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        entries = list(self._state.entries.values())
        unique_agents = len(set(e["agent_id"] for e in entries))
        return {
            "total_schedules": len(entries),
            "unique_agents": unique_agents,
        }

    def reset(self):
        self._state = AgentWorkflowSchedulerV2State()
        self._on_change = None
