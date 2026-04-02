from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowAcceleratorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowAccelerator:
    PREFIX = "awac-"
    MAX_ENTRIES = 10000

    def __init__(self, *, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentWorkflowAcceleratorState()
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
        sorted_ids = sorted(
            entries,
            key=lambda rid: (entries[rid]["created_at"], entries[rid]["_seq"]),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for rid in sorted_ids[:to_remove]:
            del entries[rid]
        logger.debug("Pruned %d entries", to_remove)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def accelerate(
        self,
        agent_id: str,
        workflow_name: str,
        factor: float = 2.0,
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""

        record_id = f"{self.PREFIX}{uuid.uuid4().hex}"
        self._state._seq += 1
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "factor": factor,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("accelerate", record_id=record_id, agent_id=agent_id)
        logger.info("Accelerated workflow %s for agent %s (id=%s)", workflow_name, agent_id, record_id)
        return record_id

    def get_acceleration(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_accelerations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_acceleration_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)
        return len(self._state.entries)

    def get_stats(self) -> dict:
        entries = self._state.entries
        unique_agents = {e["agent_id"] for e in entries.values()}
        return {
            "total_accelerations": len(entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowAcceleratorState()
        self._on_change = None
        logger.info("AgentWorkflowAccelerator reset")
