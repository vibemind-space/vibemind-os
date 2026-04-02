"""Agent Task Escalation – managing escalation records and events.

Manages task escalation rules and escalation events, tracking
escalation records with levels, resolution status, and metadata.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskEscalationState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskEscalation:
    """Manages task escalation rules and escalation events."""

    PREFIX = "ate-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskEscalationState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        # Evict oldest entries first to make room
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

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
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Escalation operations
    # ------------------------------------------------------------------

    def escalate(
        self,
        task_id: str,
        reason: str,
        level: str = "warning",
        metadata: dict = None,
    ) -> str:
        """Create an escalation record.

        Levels: "info", "warning", "critical".
        Returns the escalation ID on success or ``""`` on failure.
        """
        if not task_id or not reason:
            return ""

        valid_levels = ("info", "warning", "critical")
        if level not in valid_levels:
            level = "warning"

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        escalation_id = self._generate_id()
        self._state.entries[escalation_id] = {
            "escalation_id": escalation_id,
            "task_id": task_id,
            "reason": reason,
            "level": level,
            "metadata": dict(metadata) if metadata else {},
            "resolved": False,
            "resolution": "",
            "created_at": now,
            "resolved_at": None,
            "_seq": self._state._seq,
        }
        self._fire("escalation_created", self._state.entries[escalation_id])
        logger.debug(
            "Escalation created: %s for task %s (level=%s)",
            escalation_id,
            task_id,
            level,
        )
        return escalation_id

    def get_escalation(self, escalation_id: str) -> Optional[dict]:
        """Return the escalation entry or None."""
        entry = self._state.entries.get(escalation_id)
        return dict(entry) if entry else None

    def get_escalations(
        self, task_id: str = "", level: str = "", limit: int = 50
    ) -> List[dict]:
        """Query escalations, newest first.

        Optionally filter by task_id and/or level.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if task_id and entry["task_id"] != task_id:
                continue
            if level and entry["level"] != level:
                continue
            results.append(dict(entry))
        # Sort newest first
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def resolve_escalation(self, escalation_id: str, resolution: str = "") -> bool:
        """Mark an escalation as resolved."""
        entry = self._state.entries.get(escalation_id)
        if entry is None:
            return False
        if entry["resolved"]:
            return False
        entry["resolved"] = True
        entry["resolution"] = resolution
        entry["resolved_at"] = time.time()
        self._fire("escalation_resolved", entry)
        logger.debug("Escalation resolved: %s", escalation_id)
        return True

    def get_escalation_count(self, task_id: str = "", level: str = "") -> int:
        """Return the number of escalations matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if task_id and entry["task_id"] != task_id:
                continue
            if level and entry["level"] != level:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total_escalations = len(self._state.entries)
        resolved_count = sum(
            1 for e in self._state.entries.values() if e["resolved"]
        )
        by_level: Dict[str, int] = {}
        for entry in self._state.entries.values():
            lvl = entry["level"]
            by_level[lvl] = by_level.get(lvl, 0) + 1
        return {
            "total_escalations": total_escalations,
            "resolved_count": resolved_count,
            "by_level": by_level,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskEscalationState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskEscalation reset")
