"""Agent Task Archiver -- archives completed agent tasks for long-term storage.

Stores completed task records with agent association, result reason,
and metadata. Supports querying, filtering, and counting.

Usage::

    archiver = AgentTaskArchiver()

    # Archive a completed task
    archive_id = archiver.archive("task-1", "agent-1", result="done", reason="completed")

    # Query
    entry = archiver.get_archived(archive_id)
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
class AgentTaskArchiverState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskArchiver:
    """Archives completed agent tasks for long-term storage."""

    PREFIX = "atar2-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskArchiverState()
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
    # Archive operations
    # ------------------------------------------------------------------

    def archive(
        self,
        task_id: str,
        agent_id: str,
        result: str = "",
        reason: str = "completed",
        metadata: dict = None,
    ) -> str:
        """Archive a completed task.

        Returns the archive ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        archive_id = self._generate_id()
        self._state.entries[archive_id] = {
            "archive_id": archive_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "result": result,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("archived", self._state.entries[archive_id])
        logger.debug(
            "Task archived: %s (task=%s, agent=%s, reason=%s)",
            archive_id,
            task_id,
            agent_id,
            reason,
        )
        return archive_id

    def get_archived(self, archive_id: str) -> Optional[dict]:
        """Return the archive entry or None."""
        entry = self._state.entries.get(archive_id)
        return dict(entry) if entry else None

    def get_archives(
        self, agent_id: str = "", reason: str = "", limit: int = 50
    ) -> List[dict]:
        """Query archives, newest first.

        Optionally filter by agent_id and/or reason.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if reason and entry["reason"] != reason:
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
        unique_tasks = set()
        reasons: Dict[str, int] = {}
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            unique_tasks.add(entry["task_id"])
            r = entry.get("reason", "")
            reasons[r] = reasons.get(r, 0) + 1
        return {
            "total_archived": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_tasks": len(unique_tasks),
            "reasons": reasons,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskArchiverState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskArchiver reset")
