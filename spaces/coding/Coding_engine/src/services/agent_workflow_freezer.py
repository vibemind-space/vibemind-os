import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowFreezerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowFreezer:
    PREFIX = "awfz-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowFreezerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}"
        hex_hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + hex_hash[:12]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            remove_count = len(self._state.entries) // 4
            for key in sorted_keys[:remove_count]:
                del self._state.entries[key]

    def _fire(self, action: str, data: Any):
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback %s error", name)

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

    def freeze(
        self,
        agent_id: str,
        workflow_name: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("frozen", entry)
        return record_id

    def get_freeze(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_freezes(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        if agent_id:
            entries = [e for e in self._state.entries.values() if e.get("agent_id") == agent_id]
        else:
            entries = list(self._state.entries.values())
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return entries[:limit]

    def get_freeze_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)
        return len(self._state.entries)

    def get_stats(self) -> dict:
        unique_agents = set(e.get("agent_id") for e in self._state.entries.values())
        return {
            "total_freezes": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self):
        self._state = AgentWorkflowFreezerState()
        self._on_change = None
