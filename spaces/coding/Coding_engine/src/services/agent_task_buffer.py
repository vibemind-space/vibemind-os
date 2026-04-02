"""Agent task buffer service for buffering tasks before processing (FIFO queue with capacity)."""

import time
import hashlib
import dataclasses
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskBufferState:
    """State container for the agent task buffer."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentTaskBuffer:
    """Buffer tasks for agents before processing (FIFO queue with capacity)."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "atb-"

    def __init__(self) -> None:
        self._state = AgentTaskBufferState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self) -> None:
        while len(self._state.entries) > self.MAX_ENTRIES:
            oldest_key = next(iter(self._state.entries))
            del self._state.entries[oldest_key]
            logger.debug("Pruned entry %s", oldest_key)

    def _fire(self, event: str, data: Any = None) -> None:
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb_id, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback %s error", cb_id)

    def on_change(self, callback: Callable) -> None:
        """Register a global change callback."""
        self._on_change = callback

    def register_callback(self, callback_id: str, callback: Callable) -> None:
        """Register a named callback."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a named callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def create_buffer(self, agent_id: str, capacity: int = 100) -> str:
        """Create a new task buffer for an agent. Returns buffer_id."""
        buffer_id = self._generate_id(agent_id)
        self._state.entries[buffer_id] = {
            "buffer_id": buffer_id,
            "agent_id": agent_id,
            "capacity": capacity,
            "tasks": deque(),
            "created_at": time.time(),
        }
        self._prune()
        self._fire("buffer_created", {"buffer_id": buffer_id, "agent_id": agent_id})
        logger.info("Created buffer %s for agent %s (capacity=%d)", buffer_id, agent_id, capacity)
        return buffer_id

    def push(self, buffer_id: str, task: Any) -> bool:
        """Push a task onto the buffer. Returns False if at capacity."""
        entry = self._state.entries.get(buffer_id)
        if entry is None:
            logger.warning("Buffer %s not found", buffer_id)
            return False
        if len(entry["tasks"]) >= entry["capacity"]:
            logger.warning("Buffer %s at capacity (%d)", buffer_id, entry["capacity"])
            return False
        entry["tasks"].append(task)
        self._fire("task_pushed", {"buffer_id": buffer_id, "task": task})
        return True

    def pop(self, buffer_id: str) -> Any:
        """Pop the oldest task from the buffer (FIFO). Returns None if empty."""
        entry = self._state.entries.get(buffer_id)
        if entry is None or len(entry["tasks"]) == 0:
            return None
        task = entry["tasks"].popleft()
        self._fire("task_popped", {"buffer_id": buffer_id, "task": task})
        return task

    def peek(self, buffer_id: str) -> Any:
        """Peek at the oldest task without removing it. Returns None if empty."""
        entry = self._state.entries.get(buffer_id)
        if entry is None or len(entry["tasks"]) == 0:
            return None
        return entry["tasks"][0]

    def get_size(self, buffer_id: str) -> int:
        """Get the number of tasks in the buffer."""
        entry = self._state.entries.get(buffer_id)
        if entry is None:
            return 0
        return len(entry["tasks"])

    def get_buffer(self, buffer_id: str) -> Optional[dict]:
        """Get buffer info. Returns None if not found."""
        entry = self._state.entries.get(buffer_id)
        if entry is None:
            return None
        return {
            "buffer_id": entry["buffer_id"],
            "agent_id": entry["agent_id"],
            "capacity": entry["capacity"],
            "size": len(entry["tasks"]),
            "created_at": entry["created_at"],
        }

    def get_buffers(self, agent_id: str) -> list:
        """Get all buffers for an agent."""
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                results.append({
                    "buffer_id": entry["buffer_id"],
                    "agent_id": entry["agent_id"],
                    "capacity": entry["capacity"],
                    "size": len(entry["tasks"]),
                    "created_at": entry["created_at"],
                })
        return results

    def flush(self, buffer_id: str) -> list:
        """Return all tasks from the buffer and clear it."""
        entry = self._state.entries.get(buffer_id)
        if entry is None:
            return []
        tasks = list(entry["tasks"])
        entry["tasks"].clear()
        self._fire("buffer_flushed", {"buffer_id": buffer_id, "count": len(tasks)})
        logger.info("Flushed %d tasks from buffer %s", len(tasks), buffer_id)
        return tasks

    def get_buffer_count(self, agent_id: str = "") -> int:
        """Get count of buffers, optionally filtered by agent_id."""
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        """List all unique agent IDs that have buffers."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        """Get statistics about the buffer system."""
        total_tasks = sum(len(e["tasks"]) for e in self._state.entries.values())
        agents = self.list_agents()
        return {
            "total_buffers": len(self._state.entries),
            "total_tasks": total_tasks,
            "total_agents": len(agents),
            "agents": agents,
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = AgentTaskBufferState()
        self._callbacks.clear()
        self._on_change = None
        logger.info("AgentTaskBuffer reset")
