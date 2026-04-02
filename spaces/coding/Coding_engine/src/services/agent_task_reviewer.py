from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskReviewerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskReviewer:
    PREFIX = "atrv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskReviewerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        digest = sha256(f"{key}:{self._state._seq}".encode()).hexdigest()
        return self.PREFIX + digest[:12]

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k]["created_at"],
                    self._state.entries[k]["_seq"],
                ),
            )
            to_remove = len(self._state.entries) // 4
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail) -> None:
        if self._on_change is not None:
            self._on_change(action, **detail)
        for cb in self._state.callbacks.values():
            cb(action, **detail)

    def review(
        self,
        task_id: str,
        agent_id: str,
        verdict: str = "pending",
        metadata: Optional[dict] = None,
    ) -> str:
        if not task_id or not agent_id:
            return ""
        record_id = self._generate_id(f"{task_id}:{agent_id}")
        record = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "verdict": verdict,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("review")
        return record_id

    def get_review(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_reviews(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_review_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)
        return len(self._state.entries)

    def get_stats(self) -> dict:
        unique_agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_reviews": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        self._state = AgentTaskReviewerState()
        self._on_change = None
