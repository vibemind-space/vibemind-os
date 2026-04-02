"""Agent Task Tracker V2 -- tracks task-to-agent bindings with metadata.

Records which agents are working on which tasks, with status tracking,
metadata storage, and change-notification callbacks.

Usage::

    tracker = AgentTaskTrackerV2()

    # Track a task
    record_id = tracker.track_v2("task-1", "agent-1", status="active")

    # Query
    entry = tracker.get_tracking(record_id)
    entries = tracker.get_trackings(agent_id="agent-1", limit=10)
    stats = tracker.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class AgentTaskTrackerV2State:
    """Primary state container for the v2 tracker."""

    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ======================================================================
# Agent Task Tracker V2
# ======================================================================

class AgentTaskTrackerV2:
    """Tracks task-to-agent bindings with metadata and change callbacks.

    Uses SHA-256-based IDs, automatic pruning, and dual callback
    mechanisms (single on_change + named callbacks).
    """

    PREFIX: str = "attv-"
    MAX_ENTRIES: int = 10_000

    def __init__(self) -> None:
        self._state = AgentTaskTrackerV2State()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        """Generate a unique record ID using SHA-256 + sequence counter."""
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest quarter of entries when capacity is exceeded."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return

        all_sorted = sorted(
            self._state.entries.items(),
            key=lambda pair: (pair[1].get("created_at", ""), pair[1].get("_seq", 0)),
        )

        to_remove = len(self._state.entries) // 4
        to_remove = max(to_remove, 1)
        victims = all_sorted[:to_remove]

        for key, _entry in victims:
            del self._state.entries[key]

        logger.debug(
            "agent_task_tracker_v2.pruned removed=%d remaining=%d",
            len(victims),
            len(self._state.entries),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback.  Returns ``False`` if not found."""
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    def _fire(self, action: str, **detail: object) -> None:
        """Invoke on_change and all named callbacks.

        Exceptions are logged and swallowed so that a misbehaving
        listener cannot break tracker operations.
        """
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

    def track_v2(
        self,
        task_id: str,
        agent_id: str,
        status: str = "active",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a tracking entry.  Returns the record ID, or '' if inputs are empty."""
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "status": status,
            "metadata": deepcopy(metadata) if metadata is not None else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()

        self._fire("track_v2", task_id=task_id, record_id=record_id)
        return record_id

    def get_tracking(self, record_id: str) -> Optional[dict]:
        """Get a single tracking entry by record ID.  Returns a deep copy or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return deepcopy(entry)

    def get_trackings(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Get tracking entries, optionally filtered by agent_id.

        Results are sorted by (created_at, _seq) descending.
        """
        results: List[dict] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(deepcopy(entry))

        results.sort(
            key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)),
            reverse=True,
        )
        return results[:limit]

    def get_tracking_count(self, agent_id: str = "") -> int:
        """Get total number of tracking entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        unique_agents = len({e["agent_id"] for e in self._state.entries.values()})
        return {
            "total_trackings": len(self._state.entries),
            "unique_agents": unique_agents,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskTrackerV2State()
        self._on_change = None
