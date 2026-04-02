from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowDecoratorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowDecorator:
    PREFIX = "awdc-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentWorkflowDecoratorState()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: object) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            self._on_change(action, data)
        for cb in list(self._state.callbacks.values()):
            cb(action, data)

    def _next_seq(self) -> int:
        self._state._seq += 1
        return self._state._seq

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_ids = sorted(
            entries,
            key=lambda rid: (entries[rid].get("created_at", 0), entries[rid].get("_seq", 0)),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for rid in sorted_ids[:to_remove]:
            del entries[rid]
        logger.debug("Pruned %d decoration entries", to_remove)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def decorate(
        self,
        agent_id: str,
        workflow_name: str,
        decoration: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""

        raw = f"{agent_id}:{workflow_name}:{time.time()}:{self._state._seq}"
        record_id = self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

        seq = self._next_seq()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "decoration": decoration,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": seq,
        }

        self._state.entries[record_id] = entry
        self._prune()

        logger.info(
            "Decorated workflow %s for agent %s -> %s",
            workflow_name,
            agent_id,
            record_id,
        )
        self._fire("decorate", record_id=record_id, agent_id=agent_id)
        return record_id

    def get_decoration(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_decorations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        else:
            entries = list(entries)

        entries.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_decoration_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> dict:
        agents = {e.get("agent_id") for e in self._state.entries.values()}
        return {
            "total_decorations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowDecoratorState()
        self._on_change = None
        logger.info("AgentWorkflowDecorator reset")
