"""Coordinates workflow execution across agents."""

from __future__ import annotations

import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowCoordinatorState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowCoordinator:
    """Coordinates workflow execution across agents."""

    PREFIX = "awco-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowCoordinatorState()
        logger.info("AgentWorkflowCoordinator initialized")

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ── Callbacks ──────────────────────────────────────────────────

    @property
    def on_change(self) -> Optional[Callable]:
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        if cb is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: dict) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    # ── API ────────────────────────────────────────────────────────

    def coordinate(
        self,
        agent_id: str,
        workflow_name: str,
        participants: List[str] = None,
        strategy: str = "sequential",
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a coordination event and return its ID."""
        record_id = self._generate_id()
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "participants": participants if participants is not None else [],
            "strategy": strategy,
            "metadata": metadata or {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("coordinate", entry)
        logger.info(
            "Coordinated %s for agent %s workflow %s",
            record_id,
            agent_id,
            workflow_name,
        )
        return record_id

    def get_coordination(self, record_id: str) -> Optional[dict]:
        """Return a single coordination record or None."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_coordinations(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return coordinations filtered by agent_id, newest first."""
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return results[:limit]

    def get_coordination_count(self, agent_id: str = "") -> int:
        """Count coordinations, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                count += 1
        return count

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return {
            "total_coordinations": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowCoordinatorState()
        logger.info("AgentWorkflowCoordinator reset")
