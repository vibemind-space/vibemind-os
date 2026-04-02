"""Agent Task Tagger -- tags tasks for agents.

Associates tags with agent tasks, supporting querying, filtering, and statistics.

Usage::

    tagger = AgentTaskTagger()

    # Tag a task
    record_id = tagger.tag("task-1", "agent-1", tag_name="urgent")

    # Query
    entry = tagger.get_tag(record_id)
    entries = tagger.get_tags(agent_id="agent-1")
    stats = tagger.get_stats()
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
class AgentTaskTaggerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskTagger:
    """Tags tasks for agents."""

    PREFIX = "attg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskTaggerState()
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
        quarter = max(1, len(sorted_keys) // 4)
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
    # Tag operations
    # ------------------------------------------------------------------

    def tag(
        self,
        task_id: str,
        agent_id: str,
        tag_name: str = "",
        metadata: dict = None,
    ) -> str:
        """Tag a task for an agent.

        Returns the record ID on success or ``""`` if task_id or agent_id is empty.
        """
        if not task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        record_id = self._generate_id()
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "tag_name": tag_name,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("tagged", self._state.entries[record_id])
        logger.debug(
            "Task tagged: %s (task=%s, agent=%s, tag=%s)",
            record_id,
            task_id,
            agent_id,
            tag_name,
        )
        return record_id

    def get_tag(self, record_id: str) -> Optional[dict]:
        """Return the tag entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_tags(
        self, agent_id: str = "", limit: int = 50
    ) -> List[dict]:
        """Query tags, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_tag_count(self, agent_id: str = "") -> int:
        """Return the number of tag entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
        return {
            "total_tags": len(self._state.entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskTaggerState()
        self._on_change = None
        logger.debug("AgentTaskTagger reset")
