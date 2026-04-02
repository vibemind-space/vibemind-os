"""Agent Error Buffer -- buffered error storage for the emergent autonomous pipeline.

Provides an in-memory error buffering system that records, queries, and manages
errors raised by agents during autonomous pipeline execution.  Errors are stored
per-agent and can be filtered by type and severity.  Automatic pruning keeps the
buffer within configurable limits.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal state
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the error buffer."""

    buffers: Dict[str, list] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentErrorBuffer:
    """Buffered error storage for agents in the autonomous pipeline.

    Parameters
    ----------
    max_entries:
        Maximum total error entries across all agents.  When the limit is
        reached the oldest entries are pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._state = _State()
        logger.debug("agent_error_buffer.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns True if removed, False if not found."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_error(
        self,
        agent_id: str,
        error_type: str,
        message: str,
        severity: str = "error",
    ) -> str:
        """Record an error for an agent.  Returns the error_id (aeb-...)."""
        self._state._seq += 1
        raw = f"{agent_id}{error_type}{message}{time.time()}{self._state._seq}"
        error_id = "aeb-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = {
            "error_id": error_id,
            "agent_id": agent_id,
            "error_type": error_type,
            "message": message,
            "severity": severity,
            "timestamp": time.time(),
        }

        if agent_id not in self._state.buffers:
            self._state.buffers[agent_id] = []
        self._state.buffers[agent_id].append(entry)

        # Prune if over limit
        total = sum(len(v) for v in self._state.buffers.values())
        if total > self._max_entries:
            self._prune()

        logger.debug(
            "agent_error_buffer.record",
            error_id=error_id,
            agent_id=agent_id,
            error_type=error_type,
            severity=severity,
        )
        self._fire("record_error", error_id=error_id, agent_id=agent_id)
        return error_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_errors(
        self,
        agent_id: str,
        error_type: str = "",
        severity: str = "",
    ) -> list:
        """Get errors for an agent, optionally filtered by type and/or severity."""
        entries = self._state.buffers.get(agent_id, [])
        result = []
        for e in entries:
            if error_type and e["error_type"] != error_type:
                continue
            if severity and e["severity"] != severity:
                continue
            result.append(dict(e))
        return result

    def get_latest_error(self, agent_id: str) -> Optional[dict]:
        """Get the most recent error for an agent, or None."""
        entries = self._state.buffers.get(agent_id, [])
        if not entries:
            return None
        return dict(entries[-1])

    def get_error_count(self, agent_id: str = "") -> int:
        """Count errors.  If agent_id is given, count only that agent's errors."""
        if agent_id:
            return len(self._state.buffers.get(agent_id, []))
        return sum(len(v) for v in self._state.buffers.values())

    def clear_errors(self, agent_id: str) -> int:
        """Clear all errors for an agent.  Returns the number of entries cleared."""
        entries = self._state.buffers.get(agent_id, [])
        count = len(entries)
        if agent_id in self._state.buffers:
            del self._state.buffers[agent_id]
        if count:
            self._fire("clear_errors", agent_id=agent_id, count=count)
        return count

    def list_agents(self) -> list:
        """List all agent IDs that have buffered errors."""
        return list(self._state.buffers.keys())

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Get summary statistics."""
        total = sum(len(v) for v in self._state.buffers.values())
        return {
            "total_errors": total,
            "agent_count": len(self._state.buffers),
            "max_entries": self._max_entries,
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state.buffers.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.debug("agent_error_buffer.reset")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries across all agents until under max_entries."""
        all_entries: list = []
        for agent_id, entries in self._state.buffers.items():
            for e in entries:
                all_entries.append((agent_id, e))
        all_entries.sort(key=lambda x: x[1]["timestamp"])

        total = len(all_entries)
        to_remove = total - self._max_entries
        if to_remove <= 0:
            return

        remove_set: set = set()
        for i in range(to_remove):
            remove_set.add(all_entries[i][1]["error_id"])

        for agent_id in list(self._state.buffers.keys()):
            self._state.buffers[agent_id] = [
                e for e in self._state.buffers[agent_id]
                if e["error_id"] not in remove_set
            ]
            if not self._state.buffers[agent_id]:
                del self._state.buffers[agent_id]

        logger.debug("agent_error_buffer.prune", removed=len(remove_set))
