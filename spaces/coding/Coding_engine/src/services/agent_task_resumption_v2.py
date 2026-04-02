"""Agent Task Resumption V2 -- manages task resumption records for agents.

Tracks resumption events with metadata, supports callbacks and change
notifications, and provides query and statistics helpers.

Usage::

    svc = AgentTaskResumptionV2()

    # Resume a task
    record_id = svc.resume_v2("task-1", "agent-1", reason="ready")

    # Query
    entry = svc.get_resumption(record_id)
    entries = svc.get_resumptions(agent_id="agent-1")
    stats = svc.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskResumptionV2State:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskResumptionV2:
    """Manages task resumption records for agents (v2)."""

    PREFIX = "atrs-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskResumptionV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries.keys(),
            key=lambda k: (entries[k]["created_at"], entries[k].get("_seq", 0)),
        )
        remove_count = len(entries) // 4
        for key in sorted_keys[:remove_count]:
            del entries[key]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns *True* if it existed."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data: Dict[str, Any] = {"action": action, **detail}
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
    # Core operations
    # ------------------------------------------------------------------

    def resume_v2(
        self,
        task_id: str,
        agent_id: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a task resumption. Returns the record id, or ``""`` on empty input."""
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id()
        entry: Dict[str, Any] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("resume_v2", task_id=task_id, record_id=record_id)
        return record_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_resumption(self, record_id: str) -> Optional[Dict[str, Any]]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_resumptions(self, agent_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e.get("agent_id") == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return [copy.deepcopy(e) for e in entries[:limit]]

    def get_resumption_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> Dict[str, int]:
        entries = self._state.entries
        unique_agents = {e["agent_id"] for e in entries.values()}
        return {
            "total_resumptions": len(entries),
            "unique_agents": len(unique_agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._state = AgentTaskResumptionV2State()
        self._on_change = None
