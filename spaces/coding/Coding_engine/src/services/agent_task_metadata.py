"""Agent Task Metadata -- stores and manages metadata associated with agent tasks.

Provides an in-memory store for recording key-value metadata attached to
agent tasks.  Supports querying by agent and task name, with automatic
pruning when capacity is reached.

Usage::

    meta = AgentTaskMetadata()

    entry_id = meta.set_metadata("agent-1", "build", "version", "1.2.3")
    value = meta.get_metadata("agent-1", "build", "version")
    all_meta = meta.get_all_metadata("agent-1", "build")
    stats = meta.get_stats()
"""

import hashlib
import logging
import time
import dataclasses

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentTaskMetadataState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentTaskMetadata:
    """In-memory store for agent task metadata."""

    PREFIX = "atm2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentTaskMetadataState()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{h}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, fn):
        self._on_change = fn

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def _find_entry(self, agent_id: str, task_name: str, key: str):
        """Return (entry_id, entry) for the matching metadata entry, or (None, None)."""
        for eid, entry in self._state.entries.items():
            if (entry["agent_id"] == agent_id
                    and entry["task_name"] == task_name
                    and entry["key"] == key):
                return eid, entry
        return None, None

    def set_metadata(self, agent_id: str, task_name: str, key: str, value) -> str:
        """Set a metadata key-value for an agent task. Returns the entry ID."""
        eid, existing = self._find_entry(agent_id, task_name, key)
        if existing is not None:
            existing["value"] = value
            existing["updated_at"] = time.time()
            self._fire("metadata_updated", existing)
            return eid
        entry_id = self._generate_id(f"{agent_id}:{task_name}:{key}:{time.time()}")
        now = time.time()
        entry = {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "task_name": task_name,
            "key": key,
            "value": value,
            "created_at": now,
            "updated_at": now,
        }
        self._state.entries[entry_id] = entry
        self._prune()
        self._fire("metadata_set", entry)
        return entry_id

    def get_metadata(self, agent_id: str, task_name: str, key: str):
        """Return the value for a metadata key, or None if not found."""
        _, entry = self._find_entry(agent_id, task_name, key)
        if entry is not None:
            return entry["value"]
        return None

    def get_all_metadata(self, agent_id: str, task_name: str) -> dict:
        """Return all metadata as {key: value} dict for an agent task."""
        result = {}
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and entry["task_name"] == task_name:
                result[entry["key"]] = entry["value"]
        return result

    def delete_metadata(self, agent_id: str, task_name: str, key: str) -> bool:
        """Remove a specific metadata entry. Return True if it existed."""
        eid, _ = self._find_entry(agent_id, task_name, key)
        if eid is not None:
            del self._state.entries[eid]
            self._fire("metadata_deleted", {"agent_id": agent_id, "task_name": task_name, "key": key})
            return True
        return False

    def clear_metadata(self, agent_id: str, task_name: str) -> int:
        """Remove all metadata for an agent+task. Return count removed."""
        to_remove = [
            k for k, v in self._state.entries.items()
            if v["agent_id"] == agent_id and v["task_name"] == task_name
        ]
        for k in to_remove:
            del self._state.entries[k]
        if to_remove:
            self._fire("metadata_cleared", {"agent_id": agent_id, "task_name": task_name, "count": len(to_remove)})
        return len(to_remove)

    def get_metadata_count(self, agent_id: str = "") -> int:
        """Return the number of metadata entries, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        )

    def list_tasks_with_metadata(self, agent_id: str) -> list:
        """Return unique task_names that have metadata for the given agent."""
        tasks = set()
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                tasks.add(entry["task_name"])
        return sorted(tasks)

    def get_stats(self) -> dict:
        """Return summary statistics."""
        entries = list(self._state.entries.values())
        agents = set(e["agent_id"] for e in entries)
        tasks = set((e["agent_id"], e["task_name"]) for e in entries)
        return {
            "total_entries": len(entries),
            "unique_agents": len(agents),
            "unique_tasks": len(tasks),
        }

    def reset(self):
        """Clear all state."""
        self._state = AgentTaskMetadataState()
        self._callbacks = {}
        self._on_change = None
