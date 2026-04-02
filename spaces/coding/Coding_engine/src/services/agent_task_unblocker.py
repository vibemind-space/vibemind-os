"""Agent Task Unblocker – unblocks tasks for agents with tracking and callbacks."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskUnblockerState:
    """State container for the agent task unblocker."""
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskUnblocker:
    """Unblocks tasks for agents, tracking unblock records with metadata."""

    PREFIX = "atub-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskUnblockerState()
        self._on_change: Callable | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        self._state._seq += 1
        raw = f"{data}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

    def _fire(self, event: str, data: Any = None) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb_id, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s error", cb_id)

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Callable | None:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Callable | None) -> None:
        self._on_change = value

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        return self._state.callbacks.pop(callback_id, None) is not None

    # ------------------------------------------------------------------
    # Unblock operations
    # ------------------------------------------------------------------

    def unblock(
        self,
        task_id: str,
        agent_id: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Unblock a task for an agent. Returns the record_id or '' on invalid input."""
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id(f"{task_id}-{agent_id}")
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata is not None else None,
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("unblocked", self._state.entries[record_id])
        logger.debug("Unblocked task %s for agent %s: %s", task_id, agent_id, record_id)
        return record_id

    def get_unblock(self, record_id: str) -> Optional[dict]:
        """Return the unblock entry or None if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_unblocks(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Return unblock records, optionally filtered by agent_id, newest first."""
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(copy.deepcopy(entry))
        results.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return results[:limit]

    def get_unblock_count(self, agent_id: str = "") -> int:
        """Return the number of unblocks, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        """Return summary statistics."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_unblocks": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskUnblockerState()
        self._on_change = None
        logger.debug("AgentTaskUnblocker reset")
