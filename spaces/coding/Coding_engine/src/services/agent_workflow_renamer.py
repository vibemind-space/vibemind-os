from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowRenamerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowRenamer:
    PREFIX = "awrn-"
    MAX_ENTRIES = 10000

    def __init__(self, on_change: Optional[Callable] = None) -> None:
        self._state = AgentWorkflowRenamerState()
        self._on_change: Optional[Callable] = on_change

    def _generate_id(self) -> str:
        seq = self._state._seq
        self._state._seq += 1
        hash_val = hashlib.sha256(str(seq).encode()).hexdigest()
        return f"{self.PREFIX}{hash_val[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k]["_seq"],
            ),
        )
        remove_count = len(sorted_keys) // 4
        for k in sorted_keys[:remove_count]:
            del self._state.entries[k]
        logger.info("Pruned %d entries, %d remaining", remove_count, len(self._state.entries))

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

    def _fire(self, action: str, **detail: object) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, **detail)
            except Exception:
                logger.exception("on_change callback failed for action=%s", action)
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, **detail)
            except Exception:
                logger.exception("Callback %s failed for action=%s", cb_name, action)

    def rename(
        self,
        agent_id: str,
        workflow_name: str,
        new_name: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "new_name": new_name,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq - 1,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("rename", record_id=record_id, agent_id=agent_id)
        logger.debug("Renamed workflow %s for agent %s -> %s", workflow_name, agent_id, record_id)
        return record_id

    def get_rename(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_renames(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        if agent_id:
            items = [e for e in self._state.entries.values() if e["agent_id"] == agent_id]
        else:
            items = list(self._state.entries.values())
        items.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in items[:limit]]

    def get_rename_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)
        return len(self._state.entries)

    def get_stats(self) -> dict:
        agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_renames": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowRenamerState()
        self._on_change = None
        logger.info("AgentWorkflowRenamer reset")
