"""Agent Task Execution History -- records and queries agent task execution history.

Tracks per-agent task executions with status, duration, and metadata.
Provides success-rate analytics, duration averaging, and searchable history.

Usage::

    history = AgentTaskHistory()

    # Record a task
    record_id = history.record_task("agent-1", "code_review", status="completed", duration=1.5)

    # Query
    record = history.get_record(record_id)
    agent_hist = history.get_agent_history("agent-1")
    rate = history.get_success_rate("agent-1")
    stats = history.get_stats()
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class _TaskRecord:
    """A single task execution record."""

    record_id: str = ""
    agent_id: str = ""
    task_type: str = ""
    status: str = "completed"
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


# ======================================================================
# Agent Task History
# ======================================================================

class AgentTaskHistory:
    """Records and queries agent task execution history.

    Thread-safe, callback-driven, with automatic max-entries pruning.
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries

        # primary storage: record_id -> _TaskRecord
        self._records: Dict[str, _TaskRecord] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # cumulative counters
        self._total_recorded: int = 0
        self._total_purged: int = 0
        self._total_evictions: int = 0

        logger.debug("agent_task_history.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, task_type: str) -> str:
        """Generate a unique record ID using SHA-256 + sequence counter."""
        self._seq += 1
        raw = f"{agent_id}:{task_type}:{self._seq}:{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ath-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when capacity is reached."""
        if len(self._records) < self._max_entries:
            return

        all_sorted = sorted(
            self._records.items(), key=lambda pair: pair[1].seq,
        )

        to_remove = max(1, len(self._records) - self._max_entries + 1)
        victims = all_sorted[:to_remove]

        for key, _entry in victims:
            del self._records[key]
            self._total_evictions += 1

        logger.debug(
            "agent_task_history.pruned",
            removed=len(victims),
            remaining=len(self._records),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change callback.

        If *name* already exists the callback is silently replaced.
        """
        self._callbacks[name] = callback
        logger.debug("agent_task_history.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns ``False`` if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("agent_task_history.callback_removed", name=name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke every registered callback with *action* and *details*.

        Exceptions inside callbacks are logged and swallowed so that a
        misbehaving listener cannot break history operations.
        """
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, details)
            except Exception:
                logger.exception(
                    "agent_task_history.callback_error",
                    callback=cb_name,
                    action=action,
                )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record_task(
        self,
        agent_id: str,
        task_type: str,
        duration: float = 0.0,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a task execution.  Returns the record_id."""
        record_id = self._generate_id(agent_id, task_type)
        record = _TaskRecord(
            record_id=record_id,
            agent_id=agent_id,
            task_type=task_type,
            status=status,
            duration=duration,
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._seq,
        )
        self._records[record_id] = record
        self._total_recorded += 1
        self._prune()

        self._fire("record_task", {
            "record_id": record_id,
            "agent_id": agent_id,
            "task_type": task_type,
            "status": status,
        })
        logger.debug(
            "agent_task_history.record_task",
            record_id=record_id,
            agent_id=agent_id,
            task_type=task_type,
        )
        return record_id

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get a single record by ID.  Returns dict or None."""
        record = self._records.get(record_id)
        if record is None:
            return None
        return self._record_to_dict(record)

    def get_agent_history(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get task history for a specific agent, newest first."""
        matching = [
            r for r in self._records.values()
            if r.agent_id == agent_id
        ]
        matching.sort(key=lambda r: r.created_at, reverse=True)
        return [self._record_to_dict(r) for r in matching]

    def get_task_types(self, agent_id: str) -> List[str]:
        """Get list of unique task types for a given agent."""
        types: set[str] = set()
        for record in self._records.values():
            if record.agent_id != agent_id:
                continue
            types.add(record.task_type)
        return sorted(types)

    def get_success_rate(self, agent_id: str) -> float:
        """Get success rate (0.0-1.0) for an agent.

        Counts records with status ``"completed"`` vs total.
        """
        total = 0
        completed = 0
        for record in self._records.values():
            if record.agent_id != agent_id:
                continue
            total += 1
            if record.status == "completed":
                completed += 1

        if total == 0:
            return 0.0
        return completed / total

    def get_average_duration(self, agent_id: str) -> float:
        """Get average duration for an agent's tasks."""
        durations: List[float] = []
        for record in self._records.values():
            if record.agent_id != agent_id:
                continue
            durations.append(record.duration)

        if not durations:
            return 0.0
        return sum(durations) / len(durations)

    def get_record_count(self, agent_id: Optional[str] = None) -> int:
        """Get total number of records, optionally filtered by agent."""
        if agent_id is None:
            return len(self._records)
        return sum(
            1 for r in self._records.values()
            if r.agent_id == agent_id
        )

    def purge(self, agent_id: str, keep_latest: int = 5) -> int:
        """Remove old records for an agent, keeping the latest N.

        Returns the number of records removed.
        """
        agent_records = [
            r for r in self._records.values()
            if r.agent_id == agent_id
        ]
        agent_records.sort(key=lambda r: r.created_at, reverse=True)

        to_remove = agent_records[keep_latest:]
        for record in to_remove:
            del self._records[record.record_id]

        removed = len(to_remove)
        self._total_purged += removed

        if removed > 0:
            self._fire("purge", {
                "agent_id": agent_id,
                "removed": removed,
                "kept": keep_latest,
            })
            logger.debug(
                "agent_task_history.purge",
                agent_id=agent_id,
                removed=removed,
            )
        return removed

    def list_agents(self) -> List[str]:
        """Get list of unique agent IDs."""
        agents: set[str] = set()
        for record in self._records.values():
            agents.add(record.agent_id)
        return sorted(agents)

    def search_history(
        self,
        agent_id: Optional[str] = None,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search records with optional filters, newest first."""
        results: List[_TaskRecord] = []
        for record in self._records.values():
            if agent_id is not None and record.agent_id != agent_id:
                continue
            if task_type is not None and record.task_type != task_type:
                continue
            if status is not None and record.status != status:
                continue
            results.append(record)

        results.sort(key=lambda r: r.created_at, reverse=True)
        return [self._record_to_dict(r) for r in results]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_to_dict(self, record: _TaskRecord) -> Dict[str, Any]:
        """Convert a task record to a plain dict."""
        return {
            "record_id": record.record_id,
            "agent_id": record.agent_id,
            "task_type": record.task_type,
            "status": record.status,
            "duration": record.duration,
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        agent_count = len({r.agent_id for r in self._records.values()})
        task_type_count = len({r.task_type for r in self._records.values()})
        return {
            "total_records": len(self._records),
            "total_recorded": self._total_recorded,
            "total_purged": self._total_purged,
            "total_evictions": self._total_evictions,
            "unique_agents": agent_count,
            "unique_task_types": task_type_count,
            "max_entries": self._max_entries,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._records.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_recorded = 0
        self._total_purged = 0
        self._total_evictions = 0
        logger.debug("agent_task_history.reset")
