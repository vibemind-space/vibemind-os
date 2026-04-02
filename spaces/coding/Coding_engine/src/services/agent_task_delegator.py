"""Agent Task Delegator -- delegates tasks from one agent to another.

Tracks delegation records with status lifecycle (pending -> accepted -> completed),
supporting querying, filtering, and aggregate statistics.

Usage::

    delegator = AgentTaskDelegator()

    # Create a delegation
    dlg_id = delegator.delegate("task-1", "planner", "builder", reason="needs implementation")

    # Accept and complete
    delegator.accept_delegation(dlg_id)
    delegator.complete_delegation(dlg_id, result="implemented successfully")

    # Query
    entry = delegator.get_delegation(dlg_id)
    delegations = delegator.get_delegations(from_agent="planner")
    stats = delegator.get_stats()
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
class AgentTaskDelegatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskDelegator:
    """Delegates tasks from one agent to another."""

    PREFIX = "atdl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskDelegatorState()
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
    # Delegation operations
    # ------------------------------------------------------------------

    def delegate(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a delegation from one agent to another.

        Returns the delegation ID on success or ``""`` on failure.
        """
        if not task_id or not from_agent or not to_agent:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        delegation_id = self._generate_id()
        self._state.entries[delegation_id] = {
            "delegation_id": delegation_id,
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "status": "pending",
            "result": "",
            "created_at": now,
            "updated_at": now,
            "accepted_at": None,
            "completed_at": None,
            "_seq": self._state._seq,
        }
        self._fire("delegation_created", self._state.entries[delegation_id])
        logger.debug(
            "Delegation created: %s (task=%s, from=%s, to=%s)",
            delegation_id,
            task_id,
            from_agent,
            to_agent,
        )
        return delegation_id

    def get_delegation(self, delegation_id: str) -> Optional[dict]:
        """Return the delegation entry or None."""
        entry = self._state.entries.get(delegation_id)
        return dict(entry) if entry else None

    def accept_delegation(self, delegation_id: str) -> bool:
        """Mark a delegation as accepted.

        Returns True if the delegation was found and accepted, False otherwise.
        """
        entry = self._state.entries.get(delegation_id)
        if entry is None:
            return False
        if entry["status"] != "pending":
            return False

        now = time.time()
        entry["status"] = "accepted"
        entry["accepted_at"] = now
        entry["updated_at"] = now

        self._fire("delegation_accepted", entry)
        logger.debug("Delegation accepted: %s", delegation_id)
        return True

    def complete_delegation(self, delegation_id: str, result: str = "") -> bool:
        """Mark a delegation as completed.

        Returns True if the delegation was found and completed, False otherwise.
        """
        entry = self._state.entries.get(delegation_id)
        if entry is None:
            return False
        if entry["status"] not in ("pending", "accepted"):
            return False

        now = time.time()
        entry["status"] = "completed"
        entry["result"] = result
        entry["completed_at"] = now
        entry["updated_at"] = now

        self._fire("delegation_completed", entry)
        logger.debug("Delegation completed: %s", delegation_id)
        return True

    def get_delegations(
        self,
        from_agent: str = "",
        to_agent: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query delegations, newest first.

        Optionally filter by from_agent and/or to_agent.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if from_agent and entry["from_agent"] != from_agent:
                continue
            if to_agent and entry["to_agent"] != to_agent:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_delegation_count(self, from_agent: str = "", to_agent: str = "") -> int:
        """Return the number of delegations, optionally filtered."""
        if not from_agent and not to_agent:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if from_agent and e["from_agent"] != from_agent:
                continue
            if to_agent and e["to_agent"] != to_agent:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        accepted_count = 0
        completed_count = 0
        agents = set()
        for entry in self._state.entries.values():
            if entry["status"] in ("accepted", "completed"):
                accepted_count += 1
            if entry["status"] == "completed":
                completed_count += 1
            agents.add(entry["from_agent"])
            agents.add(entry["to_agent"])
        return {
            "total_delegations": len(self._state.entries),
            "accepted_count": accepted_count,
            "completed_count": completed_count,
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskDelegatorState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskDelegator reset")
