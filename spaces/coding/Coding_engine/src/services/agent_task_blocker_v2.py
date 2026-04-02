from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskBlockerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskBlockerV2:
    PREFIX = "atbv-"
    MAX_ENTRIES = 10000

    def __init__(
        self,
        _state: Optional[AgentTaskBlockerV2State] = None,
        _on_change: Optional[Callable] = None,
    ) -> None:
        self._state = _state or AgentTaskBlockerV2State()
        self._on_change = _on_change

    # ------------------------------------------------------------------
    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            cb(action, data)

    # ------------------------------------------------------------------
    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries,
            key=lambda k: (entries[k].get("created_at", ""), entries[k].get("_seq", 0)),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for key in sorted_keys[:to_remove]:
            del entries[key]
        logger.info("Pruned %d entries", to_remove)

    # ------------------------------------------------------------------
    def block_v2(
        self,
        task_id: str,
        agent_id: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not task_id or not agent_id:
            return ""

        record_id = f"{self.PREFIX}{uuid.uuid4().hex}"
        self._state._seq += 1
        entry: dict = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "reason": reason,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("block_v2", record_id=record_id, entry=entry)
        logger.debug("Blocked task %s for agent %s -> %s", task_id, agent_id, record_id)
        return record_id

    # ------------------------------------------------------------------
    def get_block(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    # ------------------------------------------------------------------
    def get_blocks(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    def get_block_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)
        return len(self._state.entries)

    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        agents = {e.get("agent_id") for e in self._state.entries.values()}
        return {
            "total_blocks": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._state = AgentTaskBlockerV2State()
        self._on_change = None
        logger.info("AgentTaskBlockerV2 reset")
