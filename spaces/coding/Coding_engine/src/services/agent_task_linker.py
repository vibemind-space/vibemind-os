"""Agent Task Linker -- links related agent tasks together.

Creates directional links between tasks with agent association,
link type, and metadata. Supports querying, filtering, and statistics.

Usage::

    linker = AgentTaskLinker()

    # Link tasks
    link_id = linker.link("task-1", "task-2", "agent-1", link_type="depends_on")

    # Query
    entry = linker.get_link(link_id)
    entries = linker.get_links(agent_id="agent-1")
    stats = linker.get_stats()
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
class AgentTaskLinkerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskLinker:
    """Links related agent tasks together."""

    PREFIX = "atln-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskLinkerState()
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
    # Link operations
    # ------------------------------------------------------------------

    def link(
        self,
        source_task_id: str,
        target_task_id: str,
        agent_id: str,
        link_type: str = "related",
        metadata: dict = None,
    ) -> str:
        """Create a link between two tasks.

        Returns the link ID on success or ``""`` on failure.
        """
        if not source_task_id or not target_task_id or not agent_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        link_id = self._generate_id()
        self._state.entries[link_id] = {
            "link_id": link_id,
            "source_task_id": source_task_id,
            "target_task_id": target_task_id,
            "agent_id": agent_id,
            "link_type": link_type,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("linked", self._state.entries[link_id])
        logger.debug(
            "Tasks linked: %s (source=%s, target=%s, agent=%s, type=%s)",
            link_id,
            source_task_id,
            target_task_id,
            agent_id,
            link_type,
        )
        return link_id

    def get_link(self, link_id: str) -> Optional[dict]:
        """Return the link entry or None."""
        entry = self._state.entries.get(link_id)
        return dict(entry) if entry else None

    def get_links(
        self, agent_id: str = "", link_type: str = "", limit: int = 50
    ) -> List[dict]:
        """Query links, newest first.

        Optionally filter by agent_id and/or link_type.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if link_type and entry["link_type"] != link_type:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_link_count(self, agent_id: str = "") -> int:
        """Return the number of link entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_agents = set()
        unique_sources = set()
        unique_targets = set()
        link_types: Dict[str, int] = {}
        for entry in self._state.entries.values():
            unique_agents.add(entry["agent_id"])
            unique_sources.add(entry["source_task_id"])
            unique_targets.add(entry["target_task_id"])
            lt = entry["link_type"]
            link_types[lt] = link_types.get(lt, 0) + 1
        return {
            "total_links": len(self._state.entries),
            "unique_agents": len(unique_agents),
            "unique_sources": len(unique_sources),
            "unique_targets": len(unique_targets),
            "link_types": dict(link_types),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskLinkerState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskLinker reset")
