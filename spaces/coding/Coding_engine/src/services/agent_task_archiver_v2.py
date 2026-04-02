"""Agent Task Archiver V2 -- archives agent tasks to cold/warm storage.

Stores task archive records with agent association, destination,
and metadata. Supports querying, filtering, and counting.

Usage::

    archiver = AgentTaskArchiverV2()

    # Archive a task
    record_id = archiver.archive_v2("task-1", "agent-1", destination="cold")

    # Query
    entry = archiver.get_archive(record_id)
    entries = archiver.get_archives(agent_id="agent-1")
    stats = archiver.get_stats()
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
class AgentTaskArchiverV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskArchiverV2:
    """Archives agent tasks with destination-based storage."""

    PREFIX = "atav-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskArchiverV2State()
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
        # Remove oldest quarter
        quarter = max(1, len(self._state.entries) // 4)
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k].get("_seq", 0),
            ),
        )
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action)
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
    # Archive operations
    # ------------------------------------------------------------------

    def archive_v2(
        self,
        task_id: str,
        agent_id: str,
        destination: str = "cold",
        metadata: Optional[dict] = None,
    ) -> str:
        """Archive a task to the specified destination.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "destination": destination,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("archive_v2")
        logger.debug(
            "Task archived: %s (task=%s, agent=%s, destination=%s)",
            record_id,
            task_id,
            agent_id,
            destination,
        )
        return record_id

    def get_archive(self, record_id: str) -> Optional[dict]:
        """Return the archive entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_archives(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Query archives, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(
            key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True
        )
        return results[:limit]

    def get_archive_count(self, agent_id: str = "") -> int:
        """Return the number of archived entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
        return {
            "total_archives": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskArchiverV2State()
        self._on_change = None
        logger.debug("AgentTaskArchiverV2 reset")
