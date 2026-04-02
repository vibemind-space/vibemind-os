"""Agent label manager — attach labels to agents, query by label, remove labels.

Manages a many-to-many mapping between agents and string labels.
Each label assignment gets a unique ID for tracking.

Usage::

    mgr = AgentLabelManager()
    lid = mgr.add_label("agent-1", "gpu-enabled")
    agents = mgr.find_agents("gpu-enabled")
    mgr.remove_label("agent-1", "gpu-enabled")
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentLabelManager:
    """Manages labels/tags on agents."""

    max_entries: int = 10000
    # labels: dict mapping (agent_id, label) -> assignment_id
    _labels: Dict[str, Dict[str, str]] = field(default_factory=dict)
    _seq: int = field(default=0)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _total_added: int = field(default=0)
    _total_removed: int = field(default=0)

    def _next_id(self, seed: str) -> str:
        self._seq += 1
        raw = hashlib.sha256(f"{seed}{self._seq}".encode()).hexdigest()[:12]
        return f"alm2-{raw}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_label_manager.callback_error",
                    callback=name,
                    event=event,
                )

    def _count_all(self) -> int:
        return sum(len(v) for v in self._labels.values())

    # -- public API ----------------------------------------------------------

    def add_label(self, agent_id: str, label: str) -> str:
        """Add a label to an agent. Returns label assignment ID (alm2-xxx).

        No-op if agent already has the label (returns existing ID).
        """
        if not agent_id or not label:
            return ""
        # Check for existing
        if agent_id in self._labels and label in self._labels[agent_id]:
            return self._labels[agent_id][label]
        if self._count_all() >= self.max_entries:
            return ""

        lid = self._next_id(f"{agent_id}{label}")
        if agent_id not in self._labels:
            self._labels[agent_id] = {}
        self._labels[agent_id][label] = lid

        self._total_added += 1
        logger.info(
            "agent_label_manager.label_added",
            agent_id=agent_id,
            label=label,
            assignment_id=lid,
        )
        self._fire("label_added", {
            "agent_id": agent_id,
            "label": label,
            "assignment_id": lid,
        })
        return lid

    def remove_label(self, agent_id: str, label: str) -> bool:
        """Remove a label from an agent."""
        if agent_id not in self._labels:
            return False
        if label not in self._labels[agent_id]:
            return False
        del self._labels[agent_id][label]
        if not self._labels[agent_id]:
            del self._labels[agent_id]

        self._total_removed += 1
        logger.info(
            "agent_label_manager.label_removed",
            agent_id=agent_id,
            label=label,
        )
        self._fire("label_removed", {
            "agent_id": agent_id,
            "label": label,
        })
        return True

    def get_labels(self, agent_id: str) -> list:
        """Get all labels for an agent."""
        if agent_id not in self._labels:
            return []
        return sorted(self._labels[agent_id].keys())

    def has_label(self, agent_id: str, label: str) -> bool:
        """Check if an agent has a specific label."""
        return agent_id in self._labels and label in self._labels[agent_id]

    def find_agents(self, label: str) -> list:
        """Find all agents with a specific label."""
        result = []
        for agent_id, agent_labels in self._labels.items():
            if label in agent_labels:
                result.append(agent_id)
        return sorted(result)

    def get_label_count(self, agent_id: str = "") -> int:
        """Count label assignments. If agent_id given, count for that agent; else total."""
        if agent_id:
            return len(self._labels.get(agent_id, {}))
        return self._count_all()

    def list_agents(self) -> list:
        """List all agents that have at least one label."""
        return sorted(self._labels.keys())

    def list_all_labels(self) -> list:
        """List all unique labels used across all agents."""
        labels: Set[str] = set()
        for agent_labels in self._labels.values():
            labels.update(agent_labels.keys())
        return sorted(labels)

    # -- callbacks -----------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        logger.debug("agent_label_manager.callback_registered", name=name)
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("agent_label_manager.callback_removed", name=name)
        return True

    # -- stats / reset -------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_labels": self._count_all(),
            "total_added": self._total_added,
            "total_removed": self._total_removed,
            "total_agents": len(self._labels),
            "unique_labels": len(self.list_all_labels()),
            "max_entries": self.max_entries,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._labels.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_added = 0
        self._total_removed = 0
        logger.info("agent_label_manager.reset")
