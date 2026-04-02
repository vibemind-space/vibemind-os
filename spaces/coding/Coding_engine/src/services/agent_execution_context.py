"""Agent Execution Context -- track execution contexts for agent runs.

Manages per-agent execution contexts with scoped variables, status
tracking, and lifecycle management.

Usage::

    ctx = AgentExecutionContext()

    # Create a context for an agent run
    context_id = ctx.create_context("planner", "exec-001", metadata={"goal": "build API"})

    # Set and get variables within the context
    ctx.set_variable(context_id, "step", 3)
    step = ctx.get_variable(context_id, "step")

    # Update status
    ctx.update_status(context_id, "running")

    # Close when done
    ctx.close_context(context_id, final_status="completed")

    # Query
    active = ctx.get_active_contexts("planner")
    stats = ctx.get_stats()
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
class _ContextEntry:
    """A single execution context for an agent run."""

    context_id: str = ""
    agent_id: str = ""
    execution_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    status: str = "created"
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0


# ======================================================================
# Service
# ======================================================================

class AgentExecutionContext:
    """Manage execution contexts for agent runs.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage
        self._contexts: Dict[str, _ContextEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_created: int = 0
        self._total_closed: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_execution_context.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, agent_id: str, execution_id: str) -> str:
        """Generate a unique context ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{agent_id}:{execution_id}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"aec-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached.

        Prefers removing terminal records (completed / failed / closed)
        first, falling back to the oldest overall entries if necessary.
        """
        if len(self._contexts) < self._max_entries:
            return

        terminal = [
            (cid, entry)
            for cid, entry in self._contexts.items()
            if entry.status in ("completed", "failed", "closed")
        ]
        terminal.sort(key=lambda pair: pair[1].seq)

        to_remove = max(1, len(self._contexts) - self._max_entries + 1)

        if len(terminal) >= to_remove:
            victims = terminal[:to_remove]
        else:
            all_sorted = sorted(
                self._contexts.items(), key=lambda pair: pair[1].seq,
            )
            victims = all_sorted[:to_remove]

        for cid, _entry in victims:
            del self._contexts[cid]
            self._total_evictions += 1

        logger.debug(
            "agent_execution_context.pruned removed=%d remaining=%d",
            len(victims),
            len(self._contexts),
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
        logger.debug("agent_execution_context.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("agent_execution_context.callback_removed name=%s", name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break service operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "agent_execution_context.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _ContextEntry) -> Dict[str, Any]:
        """Convert a _ContextEntry to a plain dict for external use."""
        return {
            "context_id": entry.context_id,
            "agent_id": entry.agent_id,
            "execution_id": entry.execution_id,
            "metadata": dict(entry.metadata),
            "variables": dict(entry.variables),
            "status": entry.status,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    # ------------------------------------------------------------------
    # Core API -- create context
    # ------------------------------------------------------------------

    def create_context(
        self,
        agent_id: str,
        execution_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new execution context for an agent run.

        Parameters
        ----------
        agent_id:
            The agent identifier.
        execution_id:
            The execution / run identifier.
        metadata:
            Optional metadata to attach to the context.

        Returns
        -------
        str
            The generated context ID (prefix ``"aec-"``).
        """
        with self._lock:
            self._prune_if_needed()

            now = time.time()
            context_id = self._gen_id(agent_id, execution_id)

            entry = _ContextEntry(
                context_id=context_id,
                agent_id=agent_id,
                execution_id=execution_id,
                metadata=dict(metadata) if metadata else {},
                variables={},
                status="created",
                created_at=now,
                updated_at=now,
                seq=self._seq,
            )
            self._contexts[context_id] = entry
            self._total_created += 1

            details = self._to_dict(entry)

        logger.debug(
            "agent_execution_context.context_created id=%s agent=%s execution=%s",
            context_id,
            agent_id,
            execution_id,
        )
        self._fire("context_created", details)
        return context_id

    # ------------------------------------------------------------------
    # Core API -- lookup
    # ------------------------------------------------------------------

    def get_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Return a context record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            entry = self._contexts.get(context_id)
            if entry is None:
                return None
            return self._to_dict(entry)

    # ------------------------------------------------------------------
    # Core API -- variables
    # ------------------------------------------------------------------

    def set_variable(self, context_id: str, key: str, value: Any) -> bool:
        """Set a variable in the context.

        Returns ``False`` if the context is not found.
        """
        with self._lock:
            entry = self._contexts.get(context_id)
            if entry is None:
                return False
            entry.variables[key] = value
            entry.updated_at = time.time()
            details = self._to_dict(entry)

        self._fire("variable_set", details)
        return True

    def get_variable(self, context_id: str, key: str, default: Any = None) -> Any:
        """Get a variable from the context, returning *default* if not found."""
        with self._lock:
            entry = self._contexts.get(context_id)
            if entry is None:
                return default
            return entry.variables.get(key, default)

    def get_all_variables(self, context_id: str) -> Dict[str, Any]:
        """Return all variables for a context, or empty dict if not found."""
        with self._lock:
            entry = self._contexts.get(context_id)
            if entry is None:
                return {}
            return dict(entry.variables)

    # ------------------------------------------------------------------
    # Core API -- status management
    # ------------------------------------------------------------------

    def update_status(self, context_id: str, status: str) -> bool:
        """Update context status (e.g. "running", "completed", "failed").

        Returns ``False`` if the context is not found.
        """
        if not context_id:
            return False

        with self._lock:
            entry = self._contexts.get(context_id)
            if entry is None:
                logger.debug(
                    "agent_execution_context.update_status.not_found id=%s",
                    context_id,
                )
                return False

            entry.status = status
            entry.updated_at = time.time()
            details = self._to_dict(entry)

        logger.debug(
            "agent_execution_context.status_updated id=%s status=%s",
            context_id,
            status,
        )
        self._fire("status_updated", details)
        return True

    def close_context(self, context_id: str, final_status: str = "completed") -> bool:
        """Mark a context as closed with a final status.

        Returns ``False`` if the context is not found.
        """
        if not context_id:
            return False

        with self._lock:
            entry = self._contexts.get(context_id)
            if entry is None:
                logger.debug(
                    "agent_execution_context.close.not_found id=%s",
                    context_id,
                )
                return False

            entry.status = final_status
            entry.updated_at = time.time()
            self._total_closed += 1
            details = self._to_dict(entry)

        logger.debug(
            "agent_execution_context.context_closed id=%s final_status=%s",
            context_id,
            final_status,
        )
        self._fire("context_closed", details)
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_agent_contexts(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all contexts for a given agent, newest first."""
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            results = [
                self._to_dict(entry)
                for entry in self._contexts.values()
                if entry.agent_id == agent_id
            ]
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def get_active_contexts(
        self, agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return contexts that are not in a terminal state.

        Terminal states are ``"completed"``, ``"failed"``, and ``"closed"``.
        If *agent_id* is provided, only contexts for that agent are returned.
        """
        terminal = ("completed", "failed", "closed")
        with self._lock:
            self._total_lookups += 1
            results = []
            for entry in self._contexts.values():
                if entry.status in terminal:
                    continue
                if agent_id and entry.agent_id != agent_id:
                    continue
                results.append(self._to_dict(entry))
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def list_agents(self) -> List[str]:
        """Return a sorted list of unique agent IDs that have contexts."""
        with self._lock:
            self._total_lookups += 1
            agents: set[str] = set()
            for entry in self._contexts.values():
                agents.add(entry.agent_id)
            return sorted(agents)

    def get_context_count(self, agent_id: Optional[str] = None) -> int:
        """Count contexts, optionally filtered by agent.

        Parameters
        ----------
        agent_id:
            If provided, only count contexts for this agent.
            Otherwise returns total count.
        """
        with self._lock:
            self._total_lookups += 1
            if agent_id is None:
                return len(self._contexts)
            count = 0
            for entry in self._contexts.values():
                if entry.agent_id == agent_id:
                    count += 1
            return count

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the service."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            unique_agents: set[str] = set()

            for entry in self._contexts.values():
                status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
                unique_agents.add(entry.agent_id)

            return {
                "current_entries": len(self._contexts),
                "max_entries": self._max_entries,
                "status_counts": status_counts,
                "unique_agents": len(unique_agents),
                "total_created": self._total_created,
                "total_closed": self._total_closed,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all context records, callbacks, and counters."""
        with self._lock:
            self._contexts.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_created = 0
            self._total_closed = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("agent_execution_context.reset")
