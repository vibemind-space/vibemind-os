"""Agent task router v2 -- routes agent tasks to destinations."""
from __future__ import annotations
import copy, hashlib, time, logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class AgentTaskRouterV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)

class AgentTaskRouterV2:
    PREFIX = "atrr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskRouterV2State()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(self._state.entries, key=lambda k: (self._state.entries[k].get("created_at", 0), self._state.entries[k].get("_seq", 0)))
        remove_count = len(sorted_keys) // 4
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
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

    def route_v2(self, task_id: str, agent_id: str, destination: str = "default", metadata: Optional[dict] = None) -> str:
        if not task_id or not agent_id:
            return ""
        record_id = self._generate_id()
        now = time.time()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "destination": destination,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("route_v2", record_id=record_id, task_id=task_id)
        return record_id

    def get_route(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_routes(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_route_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> dict:
        entries = list(self._state.entries.values())
        agents = set(e.get("agent_id", "") for e in entries)
        return {"total_routes": len(entries), "unique_agents": len(agents)}

    def reset(self) -> None:
        self._state = AgentTaskRouterV2State()
        self._on_change = None
