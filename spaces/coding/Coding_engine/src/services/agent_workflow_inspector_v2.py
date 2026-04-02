"""Agent workflow inspector v2 service."""

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowInspectorV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowInspectorV2:
    PREFIX = "awiv2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowInspectorV2State()
        self._on_change: Optional[Callable] = None

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            quarter = len(sorted_keys) // 4
            for key in sorted_keys[:quarter]:
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

    def _fire(self, action: str, **detail) -> None:
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

    def inspect_v2(
        self,
        agent_id: str,
        workflow_name: str,
        depth: int = 1,
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "depth": depth,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("inspect_v2", agent_id=agent_id, record_id=record_id)
        return record_id

    def get_inspection(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_inspections(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        if agent_id:
            entries = [
                e for e in self._state.entries.values() if e["agent_id"] == agent_id
            ]
        else:
            entries = list(self._state.entries.values())
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [deepcopy(e) for e in entries[:limit]]

    def get_inspection_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(
                1 for e in self._state.entries.values() if e["agent_id"] == agent_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        unique_agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_inspections": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowInspectorV2State()
        self._on_change = None
