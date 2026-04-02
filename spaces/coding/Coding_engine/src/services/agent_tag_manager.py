"""Agent tag manager — add/remove tags on agents, query by tag.

Manages a many-to-many mapping between agents and key-value tags.
Each tag assignment gets a unique ID for tracking.

Usage::

    mgr = AgentTagManager()
    tid = mgr.add_tag("agent-1", "env", "production")
    agents = mgr.find_by_tag("env")
    mgr.remove_tag("agent-1", "env")
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentTagManager:
    """Manages tags on agents."""

    max_entries: int = 10000
    # tags: dict mapping agent_id -> {tag_name -> {id, value}}
    _tags: Dict[str, Dict[str, Dict[str, str]]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_added: int = field(default=0)
    _total_removed: int = field(default=0)

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{seed}{self._seq}".encode()).hexdigest()[:12]
        return f"atg-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_tag_manager.callback_error",
                    callback=name,
                    event=event,
                )

    def _count_all(self) -> int:
        return sum(len(v) for v in self._tags.values())

    # -- public API ----------------------------------------------------------

    def add_tag(self, agent_id: str, tag: str, value: str = "") -> str:
        """Add a tag to an agent. Returns tag ID (atg-xxx).

        No-op if agent already has the tag (returns existing ID).
        """
        if not agent_id or not tag:
            return ""
        # Check for existing
        if agent_id in self._tags and tag in self._tags[agent_id]:
            return self._tags[agent_id][tag]["id"]
        if self._count_all() >= self.max_entries:
            return ""

        tid = self._next_id(f"{agent_id}{tag}")
        if agent_id not in self._tags:
            self._tags[agent_id] = {}
        self._tags[agent_id][tag] = {"id": tid, "value": value}

        self._total_added += 1
        logger.info(
            "agent_tag_manager.tag_added",
            agent_id=agent_id,
            tag=tag,
            value=value,
            tag_id=tid,
        )
        self._fire("tag_added", {
            "agent_id": agent_id,
            "tag": tag,
            "value": value,
            "tag_id": tid,
        })
        return tid

    def remove_tag(self, agent_id: str, tag: str) -> bool:
        """Remove a tag from an agent."""
        if agent_id not in self._tags:
            return False
        if tag not in self._tags[agent_id]:
            return False
        del self._tags[agent_id][tag]
        if not self._tags[agent_id]:
            del self._tags[agent_id]

        self._total_removed += 1
        logger.info(
            "agent_tag_manager.tag_removed",
            agent_id=agent_id,
            tag=tag,
        )
        self._fire("tag_removed", {
            "agent_id": agent_id,
            "tag": tag,
        })
        return True

    def get_tags(self, agent_id: str) -> list:
        """Get all tags for an agent as list of {tag, value} dicts."""
        if agent_id not in self._tags:
            return []
        return [
            {"tag": t, "value": info["value"]}
            for t, info in sorted(self._tags[agent_id].items())
        ]

    def has_tag(self, agent_id: str, tag: str) -> bool:
        """Check if an agent has a specific tag."""
        return agent_id in self._tags and tag in self._tags[agent_id]

    def get_tag_value(self, agent_id: str, tag: str) -> str:
        """Get tag value. Returns '' if not found."""
        if agent_id not in self._tags:
            return ""
        if tag not in self._tags[agent_id]:
            return ""
        return self._tags[agent_id][tag]["value"]

    def find_by_tag(self, tag: str) -> list:
        """Find all agent IDs with this tag."""
        result = []
        for agent_id, agent_tags in self._tags.items():
            if tag in agent_tags:
                result.append(agent_id)
        return sorted(result)

    def get_tag_count(self, agent_id: str = "") -> int:
        """Count tag assignments. If agent_id given, count for that agent; else total."""
        if agent_id:
            return len(self._tags.get(agent_id, {}))
        return self._count_all()

    def list_agents(self) -> list:
        """List all agents that have at least one tag."""
        return sorted(self._tags.keys())

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        logger.debug("agent_tag_manager.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("agent_tag_manager.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_tags": self._count_all(),
            "total_added": self._total_added,
            "total_removed": self._total_removed,
            "total_agents": len(self._tags),
            "max_entries": self.max_entries,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._tags.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_added = 0
        self._total_removed = 0
        logger.info("agent_tag_manager.reset")
