"""Agent Task Migrator -- migrates tasks between agents.

Transfers task ownership from one agent to another with reason tracking,
metadata, and migration history. Supports querying, filtering, and statistics.

Usage::

    migrator = AgentTaskMigrator()

    # Migrate a task
    record_id = migrator.migrate("task-1", "agent-a", "agent-b", reason="overload")

    # Query
    entry = migrator.get_migration(record_id)
    entries = migrator.get_migrations(from_agent="agent-a")
    stats = migrator.get_stats()
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
class AgentTaskMigratorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskMigrator:
    """Migrates tasks between agents."""

    PREFIX = "atmr-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskMigratorState()
        self._on_change: Optional[Callable] = None

    @property
    def _callbacks(self) -> Dict[str, Callable]:
        return self._state.callbacks

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
        quarter = max(1, len(sorted_keys) // 4)
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
    # Migration operations
    # ------------------------------------------------------------------

    def migrate(
        self,
        task_id: str,
        from_agent: str,
        to_agent: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Migrate a task from one agent to another.

        Returns the record ID on success or ``""`` on failure.
        """
        if not task_id or not from_agent or not to_agent:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("migrated", self._state.entries[record_id])
        logger.debug(
            "Task migrated: %s (task=%s, from=%s, to=%s)",
            record_id,
            task_id,
            from_agent,
            to_agent,
        )
        return record_id

    def get_migration(self, record_id: str) -> Optional[dict]:
        """Return the migration entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_migrations(
        self, from_agent: str = "", limit: int = 50
    ) -> List[dict]:
        """Query migrations, newest first.

        Optionally filter by from_agent.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if from_agent and entry["from_agent"] != from_agent:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_migration_count(self, from_agent: str = "") -> int:
        """Return the number of migration entries, optionally filtered by from_agent."""
        if not from_agent:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["from_agent"] == from_agent
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents: set = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["from_agent"])
            unique_agents.add(entry["to_agent"])
        return {
            "total_migrations": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskMigratorState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskMigrator reset")
