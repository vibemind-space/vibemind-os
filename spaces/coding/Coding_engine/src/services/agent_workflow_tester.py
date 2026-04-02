"""Agent Workflow Tester -- service for testing agent workflows.

Records workflow test executions with their parameters and results.
Provides an in-memory store with rich querying, automatic pruning,
and change-notification callbacks.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.

Usage::

    tester = AgentWorkflowTester()

    # Run a test
    record_id = tester.test_workflow("agent-1", "deploy")

    # Query
    record = tester.get_test(record_id)
    records = tester.get_tests(agent_id="agent-1")
    stats = tester.get_stats()
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
class AgentWorkflowTesterState:
    """Holds the mutable state for the workflow tester."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowTester:
    """Service for testing agent workflows.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When the limit is reached the
        oldest quarter of entries is pruned automatically.
    """

    PREFIX = "awts-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowTesterState()
        self._on_change: Optional[Callable] = None

        logger.debug("agent_workflow_tester.init")

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, workflow_name: str) -> str:
        self._state._seq += 1
        raw = f"{agent_id}-{workflow_name}-{time.time()}-{self._state._seq}"
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
        logger.debug("agent_workflow_tester.pruned", extra={"removed": remove_count})

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
                logger.exception("agent_workflow_tester.on_change_error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_workflow_tester.callback_error")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def test_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        test_suite: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a workflow test and return its record ID (``awts-xxx``).

        Parameters
        ----------
        agent_id:
            Identifier of the agent being tested.
        workflow_name:
            Name of the workflow under test.
        test_suite:
            Name of the test suite to run.  Defaults to ``"default"``.
        metadata:
            Optional dictionary of additional metadata.

        Returns
        -------
        str
            The generated record ID, or ``""`` if *agent_id* or
            *workflow_name* is falsy.
        """
        if not agent_id or not workflow_name:
            return ""

        record_id = self._generate_id(agent_id, workflow_name)
        now = time.time()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "test_suite": test_suite,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()

        logger.debug(
            "agent_workflow_tester.test_workflow",
            extra={
                "record_id": record_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
                "test_suite": test_suite,
            },
        )
        self._fire("test_recorded", {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "test_suite": test_suite,
        })
        return record_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_test(self, record_id: str) -> Optional[dict]:
        """Return the test entry for *record_id*, or ``None`` if not found.

        Returns a copy of the entry dict.
        """
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_tests(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return test entries, optionally filtered by agent.

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
            result.append(copy.deepcopy(e))

        result.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return result[:limit]

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_test_count(self, agent_id: str = "") -> int:
        """Count test entries, optionally filtered to a single agent.

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
            "total_tests": len(self._state.entries),
            "unique_agents": unique_agents,
        }

    def reset(self) -> None:
        """Clear all state and reset to a fresh instance. Sets on_change to None."""
        self._state = AgentWorkflowTesterState()
        self._on_change = None
        logger.debug("agent_workflow_tester.reset")
