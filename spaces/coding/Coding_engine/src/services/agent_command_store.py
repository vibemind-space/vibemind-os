"""Agent Command Store -- queue and track commands sent to agents.

Manages the full lifecycle of agent commands: pending -> acknowledged ->
completed | failed | cancelled, with priority-based ordering and per-agent
history queries.

Usage::

    store = AgentCommandStore()

    # Send a command
    cmd_id = store.send_command("builder", "build", payload={"target": "api"})

    # Agent picks it up
    store.acknowledge(cmd_id)
    store.complete_command(cmd_id, result={"status": "ok"})

    # Query
    pending = store.get_pending_commands("builder")
    history = store.get_command_history("builder")
    stats = store.get_stats()
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
class _CommandEntry:
    """A single command sent to an agent."""

    command_id: str = ""
    agent_id: str = ""
    command_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    status: str = "pending"  # pending | acknowledged | completed | failed | cancelled
    created_at: float = 0.0
    updated_at: float = 0.0
    result: Any = None
    error: Any = None
    seq: int = 0


# ======================================================================
# Store
# ======================================================================

class AgentCommandStore:
    """Manages agent commands with full lifecycle tracking.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()

        # primary storage
        self._commands: Dict[str, _CommandEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_sent: int = 0
        self._total_acknowledged: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_cancelled: int = 0
        self._total_lookups: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_command_store.init max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, agent_id: str, command_type: str) -> str:
        """Generate a unique command ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{agent_id}:{command_type}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acm-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when capacity is reached.

        Prefers removing terminal records (completed / failed / cancelled)
        first, falling back to the oldest overall entries if necessary.
        """
        if len(self._commands) < self._max_entries:
            return

        terminal = [
            (cid, entry)
            for cid, entry in self._commands.items()
            if entry.status in ("completed", "failed", "cancelled")
        ]
        terminal.sort(key=lambda pair: pair[1].seq)

        to_remove = max(1, len(self._commands) - self._max_entries + 1)

        if len(terminal) >= to_remove:
            victims = terminal[:to_remove]
        else:
            all_sorted = sorted(
                self._commands.items(), key=lambda pair: pair[1].seq,
            )
            victims = all_sorted[:to_remove]

        for cid, _entry in victims:
            del self._commands[cid]
            self._total_evictions += 1

        logger.debug(
            "agent_command_store.pruned removed=%d remaining=%d",
            len(victims),
            len(self._commands),
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
        logger.debug("agent_command_store.callback_registered name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("agent_command_store.callback_removed name=%s", name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break store operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "agent_command_store.callback_error callback=%s action=%s",
                    cb_name,
                    action,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _CommandEntry) -> Dict[str, Any]:
        """Convert a _CommandEntry to a plain dict for external use."""
        return {
            "command_id": entry.command_id,
            "agent_id": entry.agent_id,
            "command_type": entry.command_type,
            "payload": dict(entry.payload),
            "priority": entry.priority,
            "status": entry.status,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "result": entry.result,
            "error": entry.error,
        }

    # ------------------------------------------------------------------
    # Core API -- send command
    # ------------------------------------------------------------------

    def send_command(
        self,
        agent_id: str,
        command_type: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 5,
    ) -> str:
        """Queue a command for an agent.

        Parameters
        ----------
        agent_id:
            The target agent identifier.
        command_type:
            The command type / action to perform.
        payload:
            Optional payload data for the command.
        priority:
            Priority level (higher = more urgent). Defaults to 5.

        Returns
        -------
        str
            The generated command ID (prefix ``"acm-"``).
        """
        with self._lock:
            self._prune_if_needed()

            now = time.time()
            command_id = self._gen_id(agent_id, command_type)

            entry = _CommandEntry(
                command_id=command_id,
                agent_id=agent_id,
                command_type=command_type,
                payload=dict(payload) if payload else {},
                priority=priority,
                status="pending",
                created_at=now,
                updated_at=now,
                seq=self._seq,
            )
            self._commands[command_id] = entry
            self._total_sent += 1

            details = self._to_dict(entry)

        logger.debug(
            "agent_command_store.command_sent id=%s agent=%s command_type=%s",
            command_id,
            agent_id,
            command_type,
        )
        self._fire("command_sent", details)
        return command_id

    # ------------------------------------------------------------------
    # Core API -- lookup
    # ------------------------------------------------------------------

    def get_command(self, command_id: str) -> Optional[Dict[str, Any]]:
        """Return a command record as a dict, or ``None`` if not found."""
        with self._lock:
            self._total_lookups += 1
            entry = self._commands.get(command_id)
            if entry is None:
                return None
            return self._to_dict(entry)

    def get_pending_commands(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return pending commands for an agent, sorted by priority (highest first).

        Higher priority values are returned first (more urgent).
        """
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            pending = [
                entry
                for entry in self._commands.values()
                if entry.agent_id == agent_id and entry.status == "pending"
            ]
        pending.sort(key=lambda e: (-e.priority, e.created_at))
        return [self._to_dict(e) for e in pending]

    # ------------------------------------------------------------------
    # Core API -- lifecycle transitions
    # ------------------------------------------------------------------

    def acknowledge(self, command_id: str) -> bool:
        """Mark a command as acknowledged by the agent.

        Returns ``False`` if the command is not found or is not in
        ``"pending"`` status.
        """
        if not command_id:
            return False

        with self._lock:
            entry = self._commands.get(command_id)
            if entry is None:
                logger.debug(
                    "agent_command_store.acknowledge.not_found id=%s",
                    command_id,
                )
                return False

            if entry.status != "pending":
                logger.debug(
                    "agent_command_store.acknowledge.wrong_status id=%s status=%s",
                    command_id,
                    entry.status,
                )
                return False

            entry.status = "acknowledged"
            entry.updated_at = time.time()
            self._total_acknowledged += 1
            details = self._to_dict(entry)

        logger.debug(
            "agent_command_store.command_acknowledged id=%s", command_id,
        )
        self._fire("command_acknowledged", details)
        return True

    def complete_command(self, command_id: str, result: Any = None) -> bool:
        """Mark a command as completed.

        Returns ``False`` if the command is not found.
        """
        if not command_id:
            return False

        with self._lock:
            entry = self._commands.get(command_id)
            if entry is None:
                logger.debug(
                    "agent_command_store.complete.not_found id=%s",
                    command_id,
                )
                return False

            entry.status = "completed"
            entry.result = result
            entry.updated_at = time.time()
            self._total_completed += 1
            details = self._to_dict(entry)

        logger.debug(
            "agent_command_store.command_completed id=%s", command_id,
        )
        self._fire("command_completed", details)
        return True

    def fail_command(self, command_id: str, error: Any = None) -> bool:
        """Mark a command as failed.

        Returns ``False`` if the command is not found.
        """
        if not command_id:
            return False

        with self._lock:
            entry = self._commands.get(command_id)
            if entry is None:
                logger.debug(
                    "agent_command_store.fail.not_found id=%s",
                    command_id,
                )
                return False

            entry.status = "failed"
            entry.error = error
            entry.updated_at = time.time()
            self._total_failed += 1
            details = self._to_dict(entry)

        logger.debug(
            "agent_command_store.command_failed id=%s error=%s",
            command_id,
            error,
        )
        self._fire("command_failed", details)
        return True

    def cancel_command(self, command_id: str) -> bool:
        """Cancel a command.

        Returns ``False`` if the command is not found or is already
        in a terminal state (``"completed"`` or ``"failed"``).
        """
        if not command_id:
            return False

        with self._lock:
            entry = self._commands.get(command_id)
            if entry is None:
                logger.debug(
                    "agent_command_store.cancel.not_found id=%s",
                    command_id,
                )
                return False

            if entry.status in ("completed", "failed"):
                logger.debug(
                    "agent_command_store.cancel.terminal_status id=%s status=%s",
                    command_id,
                    entry.status,
                )
                return False

            entry.status = "cancelled"
            entry.updated_at = time.time()
            self._total_cancelled += 1
            details = self._to_dict(entry)

        logger.debug(
            "agent_command_store.command_cancelled id=%s", command_id,
        )
        self._fire("command_cancelled", details)
        return True

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_command_history(
        self, agent_id: str, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return command history for an agent, newest first.

        Parameters
        ----------
        agent_id:
            The agent to look up.
        limit:
            Maximum number of records to return.
        """
        with self._lock:
            self._total_lookups += 1
            if not agent_id:
                return []
            results = [
                self._to_dict(entry)
                for entry in self._commands.values()
                if entry.agent_id == agent_id
            ]
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results[:limit]

    def get_command_count(self, agent_id: Optional[str] = None) -> int:
        """Count commands, optionally filtered by agent.

        Parameters
        ----------
        agent_id:
            If provided, only count commands for this agent.
            Otherwise returns total count.
        """
        with self._lock:
            self._total_lookups += 1
            if agent_id is None:
                return len(self._commands)
            count = 0
            for entry in self._commands.values():
                if entry.agent_id == agent_id:
                    count += 1
            return count

    def list_agents(self) -> List[str]:
        """Return a sorted list of unique agent IDs that have commands."""
        with self._lock:
            self._total_lookups += 1
            agents: set[str] = set()
            for entry in self._commands.values():
                agents.add(entry.agent_id)
            return sorted(agents)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics about the store."""
        with self._lock:
            status_counts: Dict[str, int] = {}
            unique_agents: set[str] = set()

            for entry in self._commands.values():
                status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
                unique_agents.add(entry.agent_id)

            return {
                "current_entries": len(self._commands),
                "max_entries": self._max_entries,
                "status_counts": status_counts,
                "unique_agents": len(unique_agents),
                "total_sent": self._total_sent,
                "total_acknowledged": self._total_acknowledged,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_cancelled": self._total_cancelled,
                "total_lookups": self._total_lookups,
                "total_evictions": self._total_evictions,
                "registered_callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all command records, callbacks, and counters."""
        with self._lock:
            self._commands.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_sent = 0
            self._total_acknowledged = 0
            self._total_completed = 0
            self._total_failed = 0
            self._total_cancelled = 0
            self._total_lookups = 0
            self._total_evictions = 0

        logger.debug("agent_command_store.reset")
