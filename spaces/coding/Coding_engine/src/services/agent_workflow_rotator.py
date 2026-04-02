from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowRotatorState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowRotator:
    PREFIX = "awrt-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowRotatorState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        digest = hashlib.sha256(str(self._state._seq).encode()).hexdigest()
        return f"{self.PREFIX}{digest[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries,
            key=lambda k: self._state.entries[k]["_seq"],
        )
        quarter = len(sorted_keys) // 4
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]
        logger.info("Pruned %d entries", quarter)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, event: str, data: Any = None) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback failed")
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s failed", cb_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rotate(
        self,
        agent_id: str,
        workflow_name: str,
        direction: str = "forward",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id()
        record = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "direction": direction,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        self._prune()
        self._fire("rotate", record)
        return record_id

    def get_rotation(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_rotations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        items = list(self._state.entries.values())
        if agent_id:
            items = [e for e in items if e["agent_id"] == agent_id]
        items.sort(key=lambda e: e["_seq"], reverse=True)
        return [deepcopy(e) for e in items[:limit]]

    def get_rotation_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_rotations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowRotatorState()
        self._on_change = None
