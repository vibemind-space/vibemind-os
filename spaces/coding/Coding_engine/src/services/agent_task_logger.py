"""Agent Task Logger -- logs task execution events for auditing.

Records per-task, per-agent log entries at configurable severity levels.
Supports querying, filtering, counting, and summary statistics.

Usage::

    logger = AgentTaskLogger()

    # Log an event
    log_id = logger.log("task-1", "agent-1", level="info", message="Started")

    # Query
    entry = logger.get_log(log_id)
    logs = logger.get_logs(task_id="task-1", level="error")
    stats = logger.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

_logger = logging.getLogger(__name__)

VALID_LEVELS = {"debug", "info", "warning", "error"}


@dataclass
class AgentTaskLoggerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskLogger:
    """Logs task execution events for auditing."""

    PREFIX = "atlg-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskLoggerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                _logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                _logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def log(
        self,
        task_id: str,
        agent_id: str,
        level: str = "info",
        message: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a log entry for a task execution event.

        Returns the log ID on success or ``""`` on failure.
        Levels: debug, info, warning, error.
        """
        if not task_id or not agent_id:
            return ""

        if level not in VALID_LEVELS:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        log_id = self._generate_id()
        self._state.entries[log_id] = {
            "log_id": log_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "level": level,
            "message": message,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("logged", self._state.entries[log_id])
        _logger.debug(
            "Task logged: %s (task=%s, agent=%s, level=%s)",
            log_id,
            task_id,
            agent_id,
            level,
        )
        return log_id

    def get_log(self, log_id: str) -> Optional[dict]:
        """Return the log entry or None."""
        entry = self._state.entries.get(log_id)
        return dict(entry) if entry else None

    def get_logs(
        self,
        task_id: str = "",
        agent_id: str = "",
        level: str = "",
        limit: int = 100,
    ) -> List[dict]:
        """Query logs, newest first.

        Optionally filter by task_id, agent_id, and/or level.
        Sorted by created_at descending, then _seq descending.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if task_id and entry["task_id"] != task_id:
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if level and entry["level"] != level:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_log_count(self, task_id: str = "", level: str = "") -> int:
        """Return the number of log entries, optionally filtered."""
        if not task_id and not level:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if task_id and e["task_id"] != task_id:
                continue
            if level and e["level"] != level:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        unique_tasks: set = set()
        unique_agents: set = set()
        by_level: Dict[str, int] = {}
        for entry in self._state.entries.values():
            unique_tasks.add(entry["task_id"])
            unique_agents.add(entry["agent_id"])
            lvl = entry["level"]
            by_level[lvl] = by_level.get(lvl, 0) + 1
        return {
            "total_logs": len(self._state.entries),
            "unique_tasks": len(unique_tasks),
            "unique_agents": len(unique_agents),
            "by_level": by_level,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskLoggerState()
        self._callbacks.clear()
        self._on_change = None
        _logger.debug("AgentTaskLogger reset")
