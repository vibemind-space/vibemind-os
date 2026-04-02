"""Agent Task Promoter -- promotes tasks to higher priority.

Promotes agent tasks to higher priority levels, tracking promotion
records with reasons, metadata, and agent attribution.

Usage::

    promoter = AgentTaskPromoter()

    # Promote a task
    record_id = promoter.promote("task-1", "agent-1", new_priority=1, reason="urgent")

    # Query
    entry = promoter.get_promotion(record_id)
    entries = promoter.get_promotions(agent_id="agent-1")
    stats = promoter.get_stats()
"""

from __future__ import annotations

import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskPromoterState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskPromoter:
    """Promotes tasks to higher priority."""

    PREFIX = "atpm-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskPromoterState()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        to_remove = len(self._state.entries) - self.MAX_ENTRIES
        for key in sorted_keys[:to_remove]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        if value is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = value

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def promote(
        self,
        task_id: str,
        agent_id: str,
        new_priority: int = 1,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Promote a task to a higher priority.

        Args:
            task_id: Identifier of the task to promote.
            agent_id: Identifier of the agent requesting promotion.
            new_priority: The new priority level for the task.
            reason: Optional reason for the promotion.
            metadata: Optional additional metadata dict.

        Returns:
            The generated promotion ID (``atpm-...``), or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()

        now = time.time()
        promotion_id = self._generate_id()
        self._state.entries[promotion_id] = {
            "promotion_id": promotion_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "new_priority": new_priority,
            "reason": reason,
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("promotion_created", self._state.entries[promotion_id])
        logger.debug(
            "Promotion created: %s for task %s by agent %s (priority=%d)",
            promotion_id,
            task_id,
            agent_id,
            new_priority,
        )
        return promotion_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_promotion(self, promotion_id: str) -> Optional[dict]:
        """Return the promotion entry or None."""
        entry = self._state.entries.get(promotion_id)
        return dict(entry) if entry else None

    def get_promotions(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Query promotions, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_promotion_count(self, agent_id: str = "") -> int:
        """Return the number of promotions matching optional filter.

        Args:
            agent_id: If provided, count only promotions by this agent.
                If empty, count all promotions.
        """
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics.

        Keys: ``total_promotions``, ``unique_agents``.
        """
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_promotions": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskPromoterState()
        logger.debug("AgentTaskPromoter reset")
