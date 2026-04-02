"""Structured logging for agent workflow executions."""

import copy
import time
import hashlib
import dataclasses
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentWorkflowLoggerState:
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowLogger:
    """Structured logging for agent workflow executions."""

    PREFIX = "awlo-"
    MAX_ENTRIES = 10000
    VALID_LEVELS = ("debug", "info", "warning", "error")

    def __init__(self):
        self._state = AgentWorkflowLoggerState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("_seq_num", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._callbacks

    @on_change.setter
    def on_change(self, value: dict):
        self._callbacks = value

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def log(
        self,
        agent_id: str,
        workflow_name: str,
        level: str = "info",
        message: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a log entry. Returns the log ID."""
        if not agent_id or not workflow_name:
            return ""
        if level not in self.VALID_LEVELS:
            return ""
        log_id = self._generate_id(f"{agent_id}{workflow_name}{time.time()}")
        seq_num = self._state._seq
        entry = {
            "log_id": log_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "level": level,
            "message": message,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[log_id] = entry
        self._prune()
        self._fire("log_created", entry)
        return log_id

    def get_log(self, log_id: str) -> Optional[dict]:
        """Retrieve a single log entry by ID."""
        return self._state.entries.get(log_id)

    def get_logs(
        self,
        agent_id: str = "",
        workflow_name: str = "",
        level: str = "",
        limit: int = 100,
    ) -> List[dict]:
        """Retrieve logs filtered by criteria, newest first."""
        results = list(self._state.entries.values())
        if agent_id:
            results = [e for e in results if e["agent_id"] == agent_id]
        if workflow_name:
            results = [e for e in results if e["workflow_name"] == workflow_name]
        if level:
            results = [e for e in results if e["level"] == level]
        results.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq_num", 0)), reverse=True)
        return results[:limit]

    def get_log_count(self, agent_id: str = "", level: str = "") -> int:
        """Count logs matching optional filters."""
        if not agent_id and not level:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            if level and e["level"] != level:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        agents = set()
        levels: Dict[str, int] = {}
        for e in self._state.entries.values():
            agents.add(e["agent_id"])
            lvl = e["level"]
            levels[lvl] = levels.get(lvl, 0) + 1
        return {
            "total_logs": len(self._state.entries),
            "unique_agents": len(agents),
            "logs_by_level": levels,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentWorkflowLoggerState()
        self._callbacks.clear()
        self._fire("reset", {})
