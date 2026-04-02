"""Agent Workflow Timer -- tracks workflow execution timing.

Provides timing instrumentation for agent workflows.  Each timer records
the start and stop timestamps for a named workflow operation, computing
elapsed duration automatically.  Supports per-agent and per-workflow
queries, statistical summaries, and observer callbacks on every mutation.

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
class AgentWorkflowTimerState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentWorkflowTimer:
    """Tracks workflow execution timing for agents.

    Parameters
    ----------
    max_entries:
        Maximum number of timer entries to keep.  When the limit is
        reached the oldest quarter is pruned automatically.
    """

    PREFIX = "awt-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentWorkflowTimerState()
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
            key=lambda k: self._state.entries[k].get("started_at", 0),
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
    # Timer operations
    # ------------------------------------------------------------------

    def start_timer(
        self,
        agent_id: str,
        workflow_name: str,
        label: str = "",
    ) -> str:
        """Start timing a workflow operation.  Returns the timer ID."""
        timer_id = self._generate_id(f"{agent_id}{workflow_name}{time.time()}")
        now = time.time()
        entry = {
            "timer_id": timer_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "label": label,
            "started_at": now,
            "stopped_at": None,
            "elapsed": None,
            "status": "running",
        }
        self._state.entries[timer_id] = entry
        self._prune()
        self._fire("timer_started", {"timer_id": timer_id, "agent_id": agent_id, "workflow_name": workflow_name})
        return timer_id

    def stop_timer(self, timer_id: str) -> bool:
        """Stop a running timer and record elapsed time.

        Returns ``True`` if the timer was stopped, ``False`` if it was
        not found or already stopped.
        """
        entry = self._state.entries.get(timer_id)
        if entry is None:
            return False
        if entry["status"] != "running":
            return False
        now = time.time()
        entry["stopped_at"] = now
        entry["elapsed"] = now - entry["started_at"]
        entry["status"] = "completed"
        self._fire("timer_stopped", {"timer_id": timer_id, "elapsed": entry["elapsed"]})
        return True

    def get_timer(self, timer_id: str) -> Optional[dict]:
        """Return a timer dict or ``None`` if not found."""
        entry = self._state.entries.get(timer_id)
        if entry is None:
            return None
        return dict(entry)

    def get_timers(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Return timers filtered by agent and/or workflow, newest first."""
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if workflow_name and entry["workflow_name"] != workflow_name:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["started_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_timer_count(self, agent_id: str = "") -> int:
        """Count timers, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        entries = self._state.entries.values()
        completed = [e for e in entries if e["status"] == "completed"]
        unique_agents = {e["agent_id"] for e in entries}
        return {
            "total_timers": len(self._state.entries),
            "completed_count": len(completed),
            "unique_agents": len(unique_agents),
        }

    def reset(self) -> None:
        """Clear all timers, callbacks, and counters."""
        self._state = AgentWorkflowTimerState()
        self._callbacks = {}
        self._on_change = None
        logger.debug("agent_workflow_timer.reset")
