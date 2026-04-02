"""Agent Workflow Deprioritizer -- deprioritizes workflows for agents.

Deprioritizes agent workflows, tracking deprioritization records with
reasons, metadata, and agent attribution.

Usage::

    deprioritizer = AgentWorkflowDeprioritizer()

    # Deprioritize a workflow
    record_id = deprioritizer.deprioritize("agent-1", "workflow-a", reason="low priority")

    # Query
    entry = deprioritizer.get_deprioritization(record_id)
    entries = deprioritizer.get_deprioritizations(agent_id="agent-1")
    stats = deprioritizer.get_stats()
"""

from __future__ import annotations

import copy, hashlib, logging, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowDeprioritizerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowDeprioritizer:
    """Deprioritizes workflows for agents."""

    PREFIX = "awdp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowDeprioritizerState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        quarter = max(1, len(self._state.entries) // 4)
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.debug("on_change callback error for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.debug("Callback error for action=%s", action)

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
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def deprioritize(
        self,
        agent_id: str,
        workflow_name: str,
        reason: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Deprioritize a workflow for an agent.

        Args:
            agent_id: Identifier of the agent.
            workflow_name: Name of the workflow to deprioritize.
            reason: Optional reason for the deprioritization.
            metadata: Optional additional metadata dict.

        Returns:
            The generated deprioritization ID (``awdp-...``), or ``""`` on failure.
        """
        if not agent_id or not workflow_name:
            return ""

        try:
            self._prune()

            now = time.time()
            record_id = self._generate_id()
            self._state.entries[record_id] = {
                "record_id": record_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
                "reason": reason,
                "metadata": copy.deepcopy(metadata) if metadata else {},
                "created_at": now,
                "_seq": self._state._seq,
            }
            self._fire("deprioritized", self._state.entries[record_id])
            logger.debug(
                "Deprioritization created: %s for agent %s workflow %s",
                record_id,
                agent_id,
                workflow_name,
            )
            return record_id
        except Exception:
            logger.exception("Failed to deprioritize workflow %s", workflow_name)
            return ""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_deprioritization(self, record_id: str) -> Optional[dict]:
        """Return the deprioritization entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_deprioritizations(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        """Query deprioritizations, newest first.

        Optionally filter by agent_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_deprioritization_count(self, agent_id: str = "") -> int:
        """Return the number of deprioritizations matching optional filter.

        Args:
            agent_id: If provided, count only deprioritizations by this agent.
                If empty, count all deprioritizations.
        """
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics.

        Keys: ``total_deprioritizations``, ``unique_agents``.
        """
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_deprioritizations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowDeprioritizerState()
        self._on_change = None
        logger.debug("AgentWorkflowDeprioritizer reset")
