from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowFinalizerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowFinalizerV2:
    PREFIX = "awfv-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentWorkflowFinalizerV2State()
        self._on_change = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: object) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            cb(action, data)

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
        logger.debug("Pruned %d entries", to_remove)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def finalize_v2(
        self,
        agent_id: str,
        workflow_name: str,
        status: str = "completed",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""

        self._state._seq += 1
        record_id = f"{self.PREFIX}{uuid.uuid4().hex}"

        record = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "status": status,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }

        self._state.entries[record_id] = record
        self._prune()
        self._fire("finalize", record_id=record_id, agent_id=agent_id)
        logger.info("Finalized workflow %s for agent %s -> %s", workflow_name, agent_id, record_id)
        return record_id

    def get_finalization(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        return copy.deepcopy(entry) if entry is not None else None

    def get_finalizations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        entries.sort(key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_finalization_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> dict:
        agents = {e.get("agent_id") for e in self._state.entries.values()}
        return {
            "total_finalizations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowFinalizerV2State()
        self._on_change = None
        logger.info("State reset")
