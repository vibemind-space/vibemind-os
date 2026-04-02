"""Agent Task Cancellation – requesting, tracking, and confirming cancellations.

Manages the full lifecycle of task cancellation requests for agents,
from initial request through confirmation or rejection.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskCancellationState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskCancellation:
    """Manages task cancellation for agents."""

    PREFIX = "atc-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskCancellationState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Callable | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, task_name: str) -> str:
        self._state._seq += 1
        raw = f"{agent_id}-{task_name}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        non_requested = [
            k for k, v in self._state.entries.items() if v["status"] != "requested"
        ]
        for k in non_requested:
            del self._state.entries[k]
            if len(self._state.entries) <= self.MAX_ENTRIES:
                return

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("callback error")

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
        return self._callbacks.pop(callback_id, None) is not None

    # ------------------------------------------------------------------
    # Cancellation operations
    # ------------------------------------------------------------------

    def request_cancellation(
        self, agent_id: str, task_name: str, reason: str = ""
    ) -> str:
        """Request cancellation of a task for an agent.

        Returns the cancellation id on success or ``""`` on failure.
        """
        if not agent_id or not task_name:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        cancellation_id = self._generate_id(agent_id, task_name)
        self._state.entries[cancellation_id] = {
            "cancellation_id": cancellation_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "reason": reason,
            "status": "requested",
            "requested_at": now,
            "confirmed_at": None,
            "created_at": now,
        }
        self._fire("cancellation_requested", self._state.entries[cancellation_id])
        logger.debug(
            "Cancellation requested: %s for agent %s task %s",
            cancellation_id,
            agent_id,
            task_name,
        )
        return cancellation_id

    def confirm_cancellation(self, cancellation_id: str) -> bool:
        """Confirm a cancellation request."""
        entry = self._state.entries.get(cancellation_id)
        if entry is None or entry["status"] != "requested":
            return False
        entry["status"] = "confirmed"
        entry["confirmed_at"] = time.time()
        self._fire("cancellation_confirmed", entry)
        logger.debug("Cancellation confirmed: %s", cancellation_id)
        return True

    def reject_cancellation(self, cancellation_id: str, reason: str = "") -> bool:
        """Reject a cancellation request."""
        entry = self._state.entries.get(cancellation_id)
        if entry is None or entry["status"] != "requested":
            return False
        entry["status"] = "rejected"
        if reason:
            entry["rejection_reason"] = reason
        self._fire("cancellation_rejected", entry)
        logger.debug("Cancellation rejected: %s", cancellation_id)
        return True

    def get_cancellation(self, cancellation_id: str) -> dict:
        """Return the cancellation entry or empty dict."""
        entry = self._state.entries.get(cancellation_id)
        return dict(entry) if entry else {}

    def get_cancellations(self, agent_id: str, status: str = "") -> list:
        """Return cancellations matching agent_id and optional status filter."""
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            results.append(dict(entry))
        return results

    def is_cancelled(self, agent_id: str, task_name: str) -> bool:
        """Check if a task has a confirmed cancellation."""
        for entry in self._state.entries.values():
            if (
                entry["agent_id"] == agent_id
                and entry["task_name"] == task_name
                and entry["status"] == "confirmed"
            ):
                return True
        return False

    def get_cancellation_count(self, agent_id: str = "", status: str = "") -> int:
        """Return the number of cancellations matching optional filters."""
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if status and entry["status"] != status:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        total = len(self._state.entries)
        requested = sum(
            1 for e in self._state.entries.values() if e["status"] == "requested"
        )
        confirmed = sum(
            1 for e in self._state.entries.values() if e["status"] == "confirmed"
        )
        rejected = sum(
            1 for e in self._state.entries.values() if e["status"] == "rejected"
        )
        return {
            "total_cancellations": total,
            "requested": requested,
            "confirmed": confirmed,
            "rejected": rejected,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskCancellationState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskCancellation reset")
