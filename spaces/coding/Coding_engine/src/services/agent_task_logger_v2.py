"""AgentTaskLoggerV2 – lightweight task logging with callbacks."""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskLoggerV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskLoggerV2:
    PREFIX = "atlv-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskLoggerV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_ids = sorted(
                self._state.entries,
                key=lambda rid: (
                    self._state.entries[rid]["created_at"],
                    self._state.entries[rid]["_seq"],
                ),
            )
            remove_count = len(self._state.entries) // 4
            for rid in sorted_ids[:remove_count]:
                del self._state.entries[rid]

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Fire
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def log_v2(
        self,
        task_id: str,
        agent_id: str,
        level: str = "info",
        metadata: Optional[dict] = None,
    ) -> str:
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "level": level,
            "metadata": copy.deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("log_v2", task_id=task_id, record_id=record_id)
        return record_id

    def get_log(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_logs(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = list(self._state.entries.values())
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_log_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        unique_agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_logs": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        self._state = AgentTaskLoggerV2State()
        self._on_change = None
