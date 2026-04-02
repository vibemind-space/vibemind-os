"""Agent Priority Manager - Manage priority levels for agents and their tasks."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentPriorityManagerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentPriorityManager:
    """Manage priority levels for agents and their tasks.

    Higher priority number = higher priority.
    """

    MAX_ENTRIES = 10000
    ID_PREFIX = "apm-"

    def __init__(self):
        self._state = AgentPriorityManagerState()
        self._callbacks: dict = {}
        logger.info("AgentPriorityManager initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in sorted_entries[:to_remove]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", to_remove)

    def on_change(self, name: str, callback) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        for cb in self._callbacks.values():
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def set_priority(self, agent_id: str, priority: int = 0, label: str = "") -> str:
        """Set priority for an agent. Returns priority_id."""
        priority_id = self._generate_id(agent_id)
        entry = {
            "priority_id": priority_id,
            "agent_id": agent_id,
            "priority": priority,
            "label": label,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._state.entries[priority_id] = entry
        self._prune()
        self._fire("set_priority", entry)
        logger.info("Set priority for agent %s: %d (id=%s)", agent_id, priority, priority_id)
        return priority_id

    def get_priority(self, agent_id: str) -> int:
        """Get the current priority for an agent. Returns 0 if not found."""
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                return entry["priority"]
        return 0

    def adjust_priority(self, agent_id: str, delta: int) -> int:
        """Adjust priority by delta. Returns new priority."""
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                entry["priority"] += delta
                entry["updated_at"] = time.time()
                self._fire("adjust_priority", entry)
                logger.info("Adjusted priority for agent %s by %d to %d", agent_id, delta, entry["priority"])
                return entry["priority"]
        # Agent not found, create with delta as priority
        self.set_priority(agent_id, delta)
        return delta

    def get_highest_priority(self, limit: int = 5) -> list:
        """Get top agents sorted by priority descending."""
        entries = sorted(
            self._state.entries.values(),
            key=lambda x: x["priority"],
            reverse=True,
        )
        return [
            {"agent_id": e["agent_id"], "priority": e["priority"], "label": e["label"]}
            for e in entries[:limit]
        ]

    def get_agents_by_priority(self, min_priority: int = 0) -> list:
        """Get agent_ids with priority >= min_priority."""
        return [
            e["agent_id"]
            for e in self._state.entries.values()
            if e["priority"] >= min_priority
        ]

    def get_priority_entry(self, priority_id: str) -> dict | None:
        """Get a priority entry by its ID."""
        return self._state.entries.get(priority_id)

    def get_priority_count(self) -> int:
        """Get total number of priority entries."""
        return len(self._state.entries)

    def list_agents(self) -> list:
        """List all agent_ids with priority entries."""
        return list({e["agent_id"] for e in self._state.entries.values()})

    def get_stats(self) -> dict:
        """Get statistics about priority entries."""
        entries = list(self._state.entries.values())
        if not entries:
            return {
                "total": 0,
                "min_priority": 0,
                "max_priority": 0,
                "avg_priority": 0.0,
                "unique_agents": 0,
            }
        priorities = [e["priority"] for e in entries]
        return {
            "total": len(entries),
            "min_priority": min(priorities),
            "max_priority": max(priorities),
            "avg_priority": sum(priorities) / len(priorities),
            "unique_agents": len({e["agent_id"] for e in entries}),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = AgentPriorityManagerState()
        self._callbacks.clear()
        logger.info("AgentPriorityManager reset")
