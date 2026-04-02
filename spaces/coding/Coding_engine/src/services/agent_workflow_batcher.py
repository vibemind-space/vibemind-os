from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowBatcherState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowBatcher:
    PREFIX = "awbt-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowBatcherState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
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
            quarter = len(sorted_keys) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]

    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    def batch(
        self,
        agent_id: str,
        workflow_name: str,
        batch_size: int = 10,
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id(f"{agent_id}:{workflow_name}")
        now = datetime.now(timezone.utc).isoformat()

        self._state.entries[record_id] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "batch_size": batch_size,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": now,
            "_seq": self._state._seq,
        }

        self._prune()
        self._fire("batch")
        return record_id

    # ------------------------------------------------------------------
    def get_batch(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_batches(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    def get_batch_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(
                1 for e in self._state.entries.values() if e["agent_id"] == agent_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_batches": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._state = AgentWorkflowBatcherState()
        self._on_change = None
