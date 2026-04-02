"""Agent Workflow Throttler -- throttles workflow execution rate per agent.

Provides rate-limiting instrumentation for agent workflows.  Each throttle
record tracks whether a workflow execution should be allowed or denied
based on configurable rate limits within a sliding time window.  Supports
per-agent queries, statistical summaries, and observer callbacks on every
mutation.

Collision-free IDs are generated with SHA-256 + a monotonic sequence
counter.  Automatic pruning removes the oldest quarter of entries when
the configurable maximum is reached.
"""

import hashlib
import time
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclasses.dataclass
class AgentWorkflowThrottlerState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowThrottler:
    """Throttles workflow execution rate per agent.

    Parameters
    ----------
    max_entries:
        Maximum number of throttle entries to keep.  When the limit is
        reached the oldest quarter is pruned automatically.
    """

    PREFIX = "awth-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowThrottlerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

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
        for cb in list(self._callbacks.values()):
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
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Throttle operations
    # ------------------------------------------------------------------

    def throttle(
        self,
        agent_id: str,
        workflow_name: str,
        max_rate: int = 10,
        window_seconds: float = 60,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record a throttle check for a workflow execution.

        Returns the throttle record ID.  The record captures whether the
        execution was allowed or denied based on how many executions for
        the same ``agent_id`` and ``workflow_name`` occurred within the
        sliding ``window_seconds``.
        """
        now = time.time()
        cutoff = now - window_seconds

        # Count recent executions in the window for this agent+workflow
        recent_count = 0
        for entry in self._state.entries.values():
            if (
                entry["agent_id"] == agent_id
                and entry["workflow_name"] == workflow_name
                and entry["created_at"] >= cutoff
            ):
                recent_count += 1

        allowed = recent_count < max_rate
        seq = self._state._seq
        record_id = self._generate_id(f"{agent_id}{workflow_name}{now}")
        entry = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "max_rate": max_rate,
            "window_seconds": window_seconds,
            "created_at": now,
            "allowed": allowed,
            "recent_count": recent_count,
            "metadata": metadata or {},
            "_seq": seq,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire(
            "throttle_checked",
            {
                "record_id": record_id,
                "agent_id": agent_id,
                "workflow_name": workflow_name,
                "allowed": allowed,
            },
        )
        return record_id

    def get_throttle(self, record_id: str) -> Optional[dict]:
        """Return a throttle record dict or ``None`` if not found."""
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_throttles(
        self,
        agent_id: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return throttle records filtered by agent, newest first."""
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

    def get_throttle_count(self, agent_id: str = "") -> int:
        """Count throttle records, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        entries = list(self._state.entries.values())
        allowed = [e for e in entries if e["allowed"]]
        denied = [e for e in entries if not e["allowed"]]
        unique_agents = {e["agent_id"] for e in entries}
        return {
            "total_records": len(entries),
            "allowed_count": len(allowed),
            "denied_count": len(denied),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all throttle records, callbacks, and counters."""
        self._state = AgentWorkflowThrottlerState()
        self._callbacks = {}
        self._on_change = None
        logger.debug("agent_workflow_throttler.reset")
