"""Agent Workflow Merger -- merges multiple workflow branches into one.

Combines separate workflow branches for an agent into a single merged
record.  Each merge captures the agent, workflow name, branch list,
merge strategy, and optional metadata.  When the store exceeds
``MAX_ENTRIES`` the oldest entries are pruned automatically.

Uses SHA-256-based IDs with an ``awmg-`` prefix.
"""

from __future__ import annotations

import hashlib, time, logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowMergerState:
    """Internal store for workflow merge entries."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowMerger:
    """Merges multiple workflow branches into one for agents.

    Each merge record tracks which agent merged which workflow branches,
    along with the strategy used and optional metadata.  Records can be
    queried by agent.
    """

    PREFIX = "awmg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowMergerState()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # on_change property
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._state.callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        if callback is None:
            self._state.callbacks.pop("__on_change__", None)
        else:
            self._state.callbacks["__on_change__"] = callback

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.  Returns ``True`` if removed."""
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are silently ignored."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    def _prune(self) -> None:
        """Remove oldest entries when store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._state.entries.items(),
            key=lambda kv: (kv[1].get("created_at", 0), kv[1].get("seq", 0)),
        )
        remove_count = len(self._state.entries) - self.MAX_ENTRIES
        if remove_count < 1:
            remove_count = 1
        for key, _ in sorted_entries[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # Core: merge
    # ------------------------------------------------------------------

    def merge(
        self,
        agent_id: str,
        workflow_name: str,
        branches: List[str] = None,
        strategy: str = "combine",
        metadata: Optional[dict] = None,
    ) -> str:
        """Merge workflow branches into a single record.

        Returns the merge record ID (``awmg-`` prefix).
        """
        record_id = self._generate_id()
        now = time.time()

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "branches": list(branches) if branches else [],
            "strategy": strategy,
            "metadata": dict(metadata) if metadata else {},
            "created_at": now,
            "seq": self._state._seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("merged", entry)
        logger.debug(
            "Workflow merged: %s agent=%s workflow=%s strategy=%s",
            record_id, agent_id, workflow_name, strategy,
        )
        return record_id

    # ------------------------------------------------------------------
    # Get merge by ID
    # ------------------------------------------------------------------

    def get_merge(self, record_id: str) -> Optional[dict]:
        """Get a merge record by its ID.  Returns dict or ``None``."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # Get merges (query)
    # ------------------------------------------------------------------

    def get_merges(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query merge records, newest first.

        Optionally filter by *agent_id* and cap results with *limit*.
        """
        candidates = [
            e
            for e in self._state.entries.values()
            if not agent_id or e["agent_id"] == agent_id
        ]
        candidates.sort(
            key=lambda e: (e.get("created_at", 0), e.get("seq", 0)), reverse=True
        )
        return [dict(c) for c in candidates[:limit]]

    # ------------------------------------------------------------------
    # Get merge count
    # ------------------------------------------------------------------

    def get_merge_count(self, agent_id: str = "") -> int:
        """Return the number of merge records, optionally filtered by *agent_id*."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics for the merger service."""
        total = len(self._state.entries)
        agents = set(e["agent_id"] for e in self._state.entries.values())
        return {
            "total_merges": total,
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored merge records, callbacks, and reset counters."""
        self._state.entries.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
