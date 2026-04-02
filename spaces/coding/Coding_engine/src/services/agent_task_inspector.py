"""Agent Task Inspector -- inspects agent tasks.

Records inspection findings for agent tasks, providing a central,
in-memory inspection store with rich querying, automatic pruning,
and change-notification callbacks.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.

Usage::

    inspector = AgentTaskInspector()

    # Record an inspection
    record_id = inspector.inspect("task-42", "agent-1", "no issues found")

    # Query
    entry = inspector.get_inspection(record_id)
    entries = inspector.get_inspections(agent_id="agent-1")
    stats = inspector.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# State dataclass
# ------------------------------------------------------------------

@dataclass
class AgentTaskInspectorState:
    """Holds the mutable state for the task inspector."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentTaskInspector:
    """Inspects agent tasks.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    PREFIX = "atin-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskInspectorState()
        self._on_change: Optional[Callable] = None

        logger.debug("agent_task_inspector.init")

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, task_id: str, agent_id: str) -> str:
        self._state._seq += 1
        raw = f"{task_id}-{agent_id}-{time.time()}-{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k]["created_at"],
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = max(1, len(sorted_keys) // 4)
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]
        logger.debug("agent_task_inspector.pruned", extra={"removed": remove_count})

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Return the current on_change callback."""
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        """Set the on_change callback."""
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns ``True`` if removed, ``False`` if not found."""
        return self._state.callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke on_change first, then all registered callbacks, silencing exceptions."""
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("agent_task_inspector.on_change_error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_task_inspector.callback_error")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def inspect(
        self,
        task_id: str,
        agent_id: str,
        findings: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record an inspection entry and return its record ID (``atin-xxx``).

        Parameters
        ----------
        task_id:
            Identifier of the task being inspected.
        agent_id:
            Identifier of the agent performing the inspection.
        findings:
            Description of the inspection findings.
        metadata:
            Optional dictionary of additional metadata.

        Returns
        -------
        str
            The generated record ID, or ``""`` if *task_id* or *agent_id*
            is falsy.
        """
        if not task_id or not agent_id:
            return ""

        record_id = self._generate_id(task_id, agent_id)
        now = time.time()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "findings": findings,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()

        logger.debug(
            "agent_task_inspector.inspect",
            extra={
                "record_id": record_id,
                "task_id": task_id,
                "agent_id": agent_id,
            },
        )
        self._fire("inspection_recorded", {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
        })
        return record_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_inspection(self, record_id: str) -> Optional[dict]:
        """Return the inspection entry for *record_id*, or ``None`` if not found.

        Returns a copy of the entry dict.
        """
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_inspections(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return inspection entries, optionally filtered by agent.

        Results are sorted newest-first by ``(created_at, _seq)`` for
        deterministic tie-breaking.

        Parameters
        ----------
        agent_id:
            Filter to entries for this agent.  Empty string means no filter.
        limit:
            Maximum number of entries to return.
        """
        result = []
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            result.append(dict(e))

        result.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return result[:limit]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_inspection_count(self, agent_id: str = "") -> int:
        """Count inspection entries, optionally filtered to a single agent.

        Parameters
        ----------
        agent_id:
            If non-empty, count only entries for this agent.
        """
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        unique_agents = len({
            e["agent_id"] for e in self._state.entries.values()
        })
        return {
            "total_inspections": len(self._state.entries),
            "unique_agents": unique_agents,
        }

    def reset(self) -> None:
        """Clear all state and reset to a fresh instance."""
        self._state = AgentTaskInspectorState()
        self._on_change = None
        logger.debug("agent_task_inspector.reset")
