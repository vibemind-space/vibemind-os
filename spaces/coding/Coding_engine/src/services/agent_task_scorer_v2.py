from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskScorerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskScorerV2:
    PREFIX = "atsv-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentTaskScorerV2State()
        self._on_change: Optional[Callable] = _on_change

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        data: dict = {"action": action, **detail}
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

    def score_v2(
        self,
        task_id: str,
        agent_id: str,
        score: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> str:
        if not task_id or not agent_id:
            return ""

        record_id = f"{self.PREFIX}{uuid.uuid4().hex[:12]}"
        self._state._seq += 1
        entry: dict = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "score": score,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("score_added", record_id=record_id, task_id=task_id, agent_id=agent_id)
        logger.info("Scored task %s for agent %s -> %s", task_id, agent_id, record_id)
        return record_id

    def get_score(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_scores(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_score_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_scores": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentTaskScorerV2State()
        self._on_change = None
        logger.info("AgentTaskScorerV2 reset")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def register_callback(self, name: str, cb: Callable) -> None:
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False
