"""Agent Decision Logger -- records agent decision-making processes.

Logs decisions with reasoning, alternatives considered, and outcomes.
Every logged decision captures the agent, decision text, reasoning,
alternatives, outcome, and timestamp. Supports per-agent queries,
outcome updates, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class AgentDecisionLoggerState:
    """Internal state for the decision logger."""

    decisions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentDecisionLogger:
    """In-memory logger for agent decision-making.

    Parameters
    ----------
    max_entries:
        Maximum number of decisions to keep.  When the limit is reached
        the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = AgentDecisionLoggerState()
        self._callbacks: Dict[str, Callable] = {}

        # stats counters
        self._stats: Dict[str, int] = {
            "total_logged": 0,
            "total_pruned": 0,
            "total_cleared": 0,
            "total_queries": 0,
            "total_updates": 0,
        }

        logger.debug("agent_decision_logger.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, decision: str, now: float) -> str:
        """Create a collision-free decision ID using SHA-256 + _seq."""
        raw = f"{agent_id}-{decision}-{now}-{self._state._seq}"
        return "adl-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Logging decisions
    # ------------------------------------------------------------------

    def log_decision(
        self,
        agent_id: str,
        decision: str,
        reasoning: str = "",
        alternatives: Optional[List[str]] = None,
        outcome: str = "",
    ) -> str:
        """Log a decision and return its ``decision_id``.

        Returns the generated ``adl-...`` identifier for the new entry.
        """
        with self._lock:
            # prune if at capacity
            if len(self._state.decisions) >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            decision_id = self._generate_id(agent_id, decision, now)

            record: Dict[str, Any] = {
                "decision_id": decision_id,
                "agent_id": agent_id,
                "decision": decision,
                "reasoning": reasoning,
                "alternatives": list(alternatives) if alternatives else [],
                "outcome": outcome,
                "timestamp": now,
                "seq": self._state._seq,
            }
            self._state.decisions[decision_id] = record
            self._stats["total_logged"] += 1

        logger.debug(
            "agent_decision_logger.log_decision",
            decision_id=decision_id,
            agent_id=agent_id,
            decision=decision,
        )
        self._fire("decision_logged", {
            "decision_id": decision_id,
            "agent_id": agent_id,
            "decision": decision,
        })
        return decision_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_decisions(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return decisions for *agent_id*, most recent first."""
        with self._lock:
            self._stats["total_queries"] += 1
            records = [
                r for r in self._state.decisions.values()
                if r["agent_id"] == agent_id
            ]
            records.sort(key=lambda r: r["timestamp"], reverse=True)
            return [self._to_dict(r) for r in records[:limit]]

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Return a single decision as a dict, or ``None``."""
        with self._lock:
            r = self._state.decisions.get(decision_id)
            if r is None:
                return None
            return self._to_dict(r)

    # ------------------------------------------------------------------
    # Update outcome
    # ------------------------------------------------------------------

    def update_outcome(self, decision_id: str, outcome: str) -> bool:
        """Update the outcome of a decision. Returns True if found."""
        with self._lock:
            r = self._state.decisions.get(decision_id)
            if r is None:
                return False
            r["outcome"] = outcome
            self._stats["total_updates"] += 1

        logger.debug(
            "agent_decision_logger.update_outcome",
            decision_id=decision_id,
            outcome=outcome,
        )
        self._fire("outcome_updated", {
            "decision_id": decision_id,
            "outcome": outcome,
        })
        return True

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_decision_count(self, agent_id: str = "") -> int:
        """Count decisions, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return len(self._state.decisions)
            return sum(
                1 for r in self._state.decisions.values()
                if r["agent_id"] == agent_id
            )

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear_decisions(self, agent_id: str) -> int:
        """Remove all decisions for *agent_id*. Returns the count removed."""
        with self._lock:
            to_remove = [
                did for did, r in self._state.decisions.items()
                if r["agent_id"] == agent_id
            ]
            for did in to_remove:
                del self._state.decisions[did]
            self._stats["total_cleared"] += len(to_remove)

        if to_remove:
            logger.debug(
                "agent_decision_logger.clear_decisions",
                agent_id=agent_id,
                removed=len(to_remove),
            )
            self._fire("decisions_cleared", {
                "agent_id": agent_id,
                "count": len(to_remove),
            })

        return len(to_remove)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one decision."""
        with self._lock:
            agents = set()
            for r in self._state.decisions.values():
                agents.add(r["agent_id"])
            return sorted(agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            agents = set()
            for r in self._state.decisions.values():
                agents.add(r["agent_id"])
            return {
                **self._stats,
                "current_entries": len(self._state.decisions),
                "unique_agents": len(agents),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.decisions.clear()
            self._state._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_decision_logger.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, r: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a decision record to a clean output dict."""
        return {
            "decision_id": r["decision_id"],
            "agent_id": r["agent_id"],
            "decision": r["decision"],
            "reasoning": r["reasoning"],
            "alternatives": list(r["alternatives"]),
            "outcome": r["outcome"],
            "timestamp": r["timestamp"],
        }

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        entries = sorted(self._state.decisions.values(), key=lambda r: r["seq"])
        to_remove = max(len(entries) // 4, 1)
        for r in entries[:to_remove]:
            del self._state.decisions[r["decision_id"]]
        self._stats["total_pruned"] += to_remove
        logger.debug("agent_decision_logger.prune", removed=to_remove)
