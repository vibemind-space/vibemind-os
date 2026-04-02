"""Agent Workflow Limiter -- limits workflow execution rates for agents.

Provides rate-limiting instrumentation for agent workflows.  Each limit
record tracks the maximum allowed execution rate for a given agent and
workflow combination.  Supports per-agent queries, statistical summaries,
and observer callbacks on every mutation.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.
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
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class AgentWorkflowLimiterState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowLimiter:
    """Limits workflow execution rates for agents.

    Parameters
    ----------
    max_entries:
        Maximum number of limit entries to keep.  When the limit is
        reached the oldest quarter is pruned automatically.
    """

    PREFIX = "awlm-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowLimiterState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        self._state._seq += 1
        raw = f"{data}{self._state._seq}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        to_remove = max(1, len(sorted_keys) // 4)
        for k in sorted_keys[:to_remove]:
            del self._state.entries[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _fire(self, action: str, data: dict) -> None:
        if self._on_change:
            try:
                self._on_change(action, data)
            except Exception:
                logger.error("on_change callback error for action: %s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.error("Callback error for action: %s", action)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, fn: Optional[Callable]) -> None:
        self._on_change = fn

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Limit operations
    # ------------------------------------------------------------------

    def limit_workflow(
        self,
        agent_id: str,
        workflow_name: str,
        max_rate: int = 10,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a workflow rate limit for an agent.

        Returns the limit record ID, or empty string if validation fails.
        """
        if not agent_id or not workflow_name:
            return ""

        now = time.time()
        seq = self._state._seq
        record_id = self._generate_id(f"{agent_id}{workflow_name}{now}")
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "max_rate": max_rate,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire(
            "limited",
            {
                "record_id": record_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
            },
        )
        return record_id

    def get_limit(self, record_id: str) -> Optional[dict]:
        """Return a limit record dict or ``None`` if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_limits(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return limit records filtered by agent, newest first."""
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        results.sort(
            key=lambda e: (e["created_at"], e.get("_seq", 0)),
            reverse=True,
        )
        return results[:limit]

    def get_limit_count(self, agent_id: str = "") -> int:
        """Count limit records, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        entries = list(self._state.entries.values())
        unique_agents = {e["agent_id"] for e in entries}
        return {
            "total_limits": len(entries),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all limit records, callbacks, and counters."""
        self._state = AgentWorkflowLimiterState()
        self._on_change = None
        logger.debug("agent_workflow_limiter.reset")
