"""Agent Capability Evaluator -- evaluate and score agent capabilities.

Tracks per-agent capability scores through repeated evaluations, maintains
running averages, and provides ranking and querying across agents and
capabilities.

Usage::

    evaluator = AgentCapabilityEvaluator()

    # Register a capability
    eval_id = evaluator.register_capability("agent-1", "code_review")

    # Record evaluations
    evaluator.evaluate("agent-1", "code_review", 0.9, evaluator="human")
    evaluator.evaluate("agent-1", "code_review", 0.8)

    # Query
    cap = evaluator.get_capability("agent-1", "code_review")
    top = evaluator.get_top_agents("code_review", limit=5)
    stats = evaluator.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class _CapabilityEntry:
    """A single agent-capability evaluation record."""

    eval_id: str = ""
    agent_id: str = ""
    capability_name: str = ""
    score: float = 0.5
    evaluations_count: int = 0
    last_evaluated_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


# ======================================================================
# Evaluator
# ======================================================================

class AgentCapabilityEvaluator:
    """Evaluates and scores agent capabilities.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage: (agent_id, capability_name) -> _CapabilityEntry
        self._entries: Dict[tuple, _CapabilityEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_registered: int = 0
        self._total_evaluations: int = 0
        self._total_removals: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_capability_evaluator.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, agent_id: str, capability_name: str) -> str:
        """Generate a unique eval ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{agent_id}:{capability_name}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ace-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached."""
        if len(self._entries) < self._max_entries:
            return

        all_sorted = sorted(
            self._entries.items(), key=lambda pair: pair[1].seq,
        )

        to_remove = max(1, len(self._entries) - self._max_entries + 1)
        victims = all_sorted[:to_remove]

        for key, _entry in victims:
            del self._entries[key]
            self._total_evictions += 1

        logger.debug(
            "agent_capability_evaluator.pruned removed=%d remaining=%d",
            len(victims),
            len(self._entries),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback.

        If *name* already exists the callback is silently replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("agent_capability_evaluator.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("agent_capability_evaluator.callback_removed name=%s", name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break evaluator operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "agent_capability_evaluator.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _CapabilityEntry) -> Dict[str, Any]:
        """Convert a _CapabilityEntry to a plain dict for external use."""
        return {
            "eval_id": entry.eval_id,
            "agent_id": entry.agent_id,
            "capability_name": entry.capability_name,
            "score": entry.score,
            "evaluations_count": entry.evaluations_count,
            "last_evaluated_at": entry.last_evaluated_at,
        }

    # ------------------------------------------------------------------
    # Core API -- register capability
    # ------------------------------------------------------------------

    def register_capability(
        self,
        agent_id: str,
        capability_name: str,
        initial_score: float = 0.5,
    ) -> str:
        """Register a capability for an agent.

        Parameters
        ----------
        agent_id:
            The agent identifier.
        capability_name:
            The capability to register.
        initial_score:
            Starting score (default 0.5).

        Returns
        -------
        str
            The generated eval ID (prefix ``"ace-"``), or ``""`` if the
            agent already has this capability registered.
        """
        with self._lock:
            key = (agent_id, capability_name)
            if key in self._entries:
                logger.debug(
                    "agent_capability_evaluator.register.duplicate agent=%s capability=%s",
                    agent_id,
                    capability_name,
                )
                return ""

            self._prune_if_needed()

            now = time.time()
            eval_id = self._gen_id(agent_id, capability_name)

            entry = _CapabilityEntry(
                eval_id=eval_id,
                agent_id=agent_id,
                capability_name=capability_name,
                score=initial_score,
                evaluations_count=0,
                last_evaluated_at=0.0,
                created_at=now,
                seq=self._seq,
            )
            self._entries[key] = entry
            self._total_registered += 1

            details = self._to_dict(entry)

        logger.debug(
            "agent_capability_evaluator.capability_registered id=%s agent=%s capability=%s",
            eval_id,
            agent_id,
            capability_name,
        )
        self._fire("capability_registered", details)
        return eval_id

    # ------------------------------------------------------------------
    # Core API -- get capability
    # ------------------------------------------------------------------

    def get_capability(
        self, agent_id: str, capability_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Return a capability record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            entry = self._entries.get((agent_id, capability_name))
            if entry is None:
                return None
            return self._to_dict(entry)

    # ------------------------------------------------------------------
    # Core API -- evaluate
    # ------------------------------------------------------------------

    def evaluate(
        self,
        agent_id: str,
        capability_name: str,
        score: float,
        evaluator: str = "system",
    ) -> bool:
        """Record an evaluation for a capability.

        Updates the score as a running average.  Returns ``False`` if
        the capability is not registered.

        Parameters
        ----------
        agent_id:
            The agent identifier.
        capability_name:
            The capability being evaluated.
        score:
            The evaluation score (0.0 - 1.0).
        evaluator:
            Who performed the evaluation (default ``"system"``).
        """
        with self._lock:
            key = (agent_id, capability_name)
            entry = self._entries.get(key)
            if entry is None:
                logger.debug(
                    "agent_capability_evaluator.evaluate.not_found agent=%s capability=%s",
                    agent_id,
                    capability_name,
                )
                return False

            now = time.time()
            count = entry.evaluations_count
            # Running average: new_avg = (old_avg * count + new_score) / (count + 1)
            entry.score = (entry.score * count + score) / (count + 1)
            entry.evaluations_count += 1
            entry.last_evaluated_at = now
            self._total_evaluations += 1

            details = self._to_dict(entry)
            details["evaluator"] = evaluator
            details["raw_score"] = score

        logger.debug(
            "agent_capability_evaluator.evaluated agent=%s capability=%s score=%.4f evaluator=%s",
            agent_id,
            capability_name,
            entry.score,
            evaluator,
        )
        self._fire("capability_evaluated", details)
        return True

    # ------------------------------------------------------------------
    # Core API -- get agent capabilities
    # ------------------------------------------------------------------

    def get_agent_capabilities(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all capability records for an agent."""
        with self._lock:
            self._total_lookups += 1
            results = [
                self._to_dict(entry)
                for entry in self._entries.values()
                if entry.agent_id == agent_id
            ]
        results.sort(key=lambda d: d["capability_name"])
        return results

    # ------------------------------------------------------------------
    # Core API -- get top agents
    # ------------------------------------------------------------------

    def get_top_agents(
        self, capability_name: str, limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return top agents for a capability, sorted by score descending.

        Parameters
        ----------
        capability_name:
            The capability to rank agents for.
        limit:
            Maximum number of results.

        Returns
        -------
        list
            List of ``{"agent_id": ..., "score": ...}`` dicts.
        """
        with self._lock:
            self._total_lookups += 1
            results = [
                {"agent_id": entry.agent_id, "score": entry.score}
                for entry in self._entries.values()
                if entry.capability_name == capability_name
            ]
        results.sort(key=lambda d: d["score"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Core API -- get agent score
    # ------------------------------------------------------------------

    def get_agent_score(self, agent_id: str) -> float:
        """Return the average score across all capabilities for an agent.

        Returns ``0.0`` if the agent has no capabilities registered.
        """
        with self._lock:
            self._total_lookups += 1
            scores = [
                entry.score
                for entry in self._entries.values()
                if entry.agent_id == agent_id
            ]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    # ------------------------------------------------------------------
    # Core API -- remove capability
    # ------------------------------------------------------------------

    def remove_capability(self, agent_id: str, capability_name: str) -> bool:
        """Remove a capability registration.

        Returns ``False`` if the capability is not found.
        """
        with self._lock:
            key = (agent_id, capability_name)
            entry = self._entries.get(key)
            if entry is None:
                logger.debug(
                    "agent_capability_evaluator.remove.not_found agent=%s capability=%s",
                    agent_id,
                    capability_name,
                )
                return False

            details = self._to_dict(entry)
            del self._entries[key]
            self._total_removals += 1

        logger.debug(
            "agent_capability_evaluator.capability_removed agent=%s capability=%s",
            agent_id,
            capability_name,
        )
        self._fire("capability_removed", details)
        return True

    # ------------------------------------------------------------------
    # Core API -- list capabilities
    # ------------------------------------------------------------------

    def list_capabilities(self) -> List[str]:
        """Return a sorted list of unique capability names across all agents."""
        with self._lock:
            self._total_lookups += 1
            capabilities: set[str] = set()
            for entry in self._entries.values():
                capabilities.add(entry.capability_name)
            return sorted(capabilities)

    # ------------------------------------------------------------------
    # Core API -- list agents
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return a sorted list of unique agent IDs."""
        with self._lock:
            self._total_lookups += 1
            agents: set[str] = set()
            for entry in self._entries.values():
                agents.add(entry.agent_id)
            return sorted(agents)

    # ------------------------------------------------------------------
    # Core API -- get evaluation count
    # ------------------------------------------------------------------

    def get_evaluation_count(self, agent_id: Optional[str] = None) -> int:
        """Return the total number of evaluations recorded.

        Parameters
        ----------
        agent_id:
            If provided, only count evaluations for this agent.
            Otherwise returns the global total.
        """
        with self._lock:
            self._total_lookups += 1
            if agent_id is None:
                return sum(
                    entry.evaluations_count
                    for entry in self._entries.values()
                )
            return sum(
                entry.evaluations_count
                for entry in self._entries.values()
                if entry.agent_id == agent_id
            )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the evaluator."""
        with self._lock:
            unique_agents: set[str] = set()
            unique_capabilities: set[str] = set()

            for entry in self._entries.values():
                unique_agents.add(entry.agent_id)
                unique_capabilities.add(entry.capability_name)

            return {
                "current_entries": len(self._entries),
                "max_entries": self._max_entries,
                "unique_agents": len(unique_agents),
                "unique_capabilities": len(unique_capabilities),
                "total_registered": self._total_registered,
                "total_evaluations": self._total_evaluations,
                "total_removals": self._total_removals,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all entries, callbacks, and counters."""
        with self._lock:
            self._entries.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_registered = 0
            self._total_evaluations = 0
            self._total_removals = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("agent_capability_evaluator.reset")
