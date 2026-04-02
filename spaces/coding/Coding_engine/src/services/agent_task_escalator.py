"""Agent Task Escalator – escalating agent tasks between agents.

Manages task escalation routing between agents, tracking
escalation records with severity, agent routing, and metadata.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskEscalatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskEscalator:
    """Escalates agent tasks between agents with severity tracking."""

    PREFIX = "ates-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskEscalatorState()
        self._on_change: Optional[Callable] = None

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
        quarter = len(sorted_keys) // 4
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
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
    # Escalation operations
    # ------------------------------------------------------------------

    def escalate(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        severity: str = "medium",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create an escalation record.

        Routes a task from one agent to another with a severity level.
        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not from_agent or not to_agent:
            return ""

        now = time.time()
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "severity": severity,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("escalated", entry)
        logger.debug(
            "Task escalated: %s from %s to %s (severity=%s)",
            record_id,
            from_agent,
            to_agent,
            severity,
        )
        return record_id

    def get_escalation(self, record_id: str) -> Optional[dict]:
        """Return the escalation entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_escalations(
        self, from_agent: str = "", limit: int = 50
    ) -> List[dict]:
        """Query escalations, newest first.

        Optionally filter by from_agent.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if from_agent and entry["from_agent"] != from_agent:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_escalation_count(self, from_agent: str = "") -> int:
        """Return the number of escalations matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if from_agent and entry["from_agent"] != from_agent:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total_escalations = len(self._state.entries)
        unique_agents: set = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["from_agent"])
            unique_agents.add(entry["to_agent"])
        return {
            "total_escalations": total_escalations,
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskEscalatorState()
        self._on_change = None
        logger.debug("AgentTaskEscalator reset")
