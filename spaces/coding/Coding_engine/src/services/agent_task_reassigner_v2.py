from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskReassignerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskReassignerV2:
    PREFIX = "atrv-"
    MAX_ENTRIES = 10_000

    def __init__(self, *, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentTaskReassignerV2State()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data: dict = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("_on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("state callback error")

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
    # Public API
    # ------------------------------------------------------------------

    def reassign_v2(
        self,
        task_id: str,
        agent_id: str,
        new_agent: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not task_id:
            return ""
        if not agent_id:
            return ""

        record_id = f"{self.PREFIX}{uuid.uuid4().hex[:12]}"
        self._state._seq += 1
        now = datetime.now(timezone.utc).isoformat()

        entry: dict = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "new_agent": new_agent,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("reassign", record_id=record_id, task_id=task_id, agent_id=agent_id)
        logger.debug("reassign_v2 created %s", record_id)
        return record_id

    def get_reassignment(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_reassignments(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        entries.sort(key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_reassignment_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> dict:
        agents = {e.get("agent_id") for e in self._state.entries.values()}
        return {
            "total_reassignments": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def register_callback(self, cb: Callable) -> str:
        cb_id = uuid.uuid4().hex[:8]
        self._state.callbacks[cb_id] = cb
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._state.callbacks.pop(cb_id, None) is not None

    def reset(self) -> None:
        self._state = AgentTaskReassignerV2State()
        self._on_change = None
        logger.info("AgentTaskReassignerV2 reset")
