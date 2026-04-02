"""Agent Memory Store -- agent long-term memory storage.

Stores and retrieves memories for agents, keyed by agent_id and a
user-defined key.  Each memory carries a type label (default "general")
so callers can partition and search by category.  All data lives
in-memory with automatic pruning when the entry limit is reached.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class MemoryEntry:
    """A single stored memory."""
    memory_id: str
    agent_id: str
    key: str
    value: Any
    memory_type: str
    created_at: float
    seq: int = 0


# ------------------------------------------------------------------
# AgentMemoryStore
# ------------------------------------------------------------------

class AgentMemoryStore:
    """In-memory long-term memory store for agents."""

    def __init__(self, max_entries: int = 10000):
        self._memories: Dict[str, MemoryEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"ams-{self._seq}-{id(self)}"
        return "ams-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def store_memory(
        self,
        agent_id: str,
        key: str,
        value: Any,
        memory_type: str = "general",
    ) -> str:
        """Store a memory for an agent.  Returns a memory_id starting with 'ams-'."""
        if not agent_id or not key:
            return ""

        # Prune if over capacity
        if len(self._memories) >= self._max_entries:
            self._prune()

        mid = self._generate_id()
        entry = MemoryEntry(
            memory_id=mid,
            agent_id=agent_id,
            key=key,
            value=value,
            memory_type=memory_type,
            created_at=time.time(),
            seq=self._seq,
        )
        self._memories[mid] = entry
        self._fire("store_memory", {
            "memory_id": mid,
            "agent_id": agent_id,
            "key": key,
            "memory_type": memory_type,
        })
        return mid

    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single memory by its ID.  Returns None if not found."""
        entry = self._memories.get(memory_id)
        if entry is None:
            return None
        return self._to_dict(entry)

    def recall(self, agent_id: str, key: str) -> Any:
        """Get the latest value stored under *key* for *agent_id*.

        Returns None if no matching memory exists.
        """
        latest: Optional[MemoryEntry] = None
        for entry in self._memories.values():
            if entry.agent_id == agent_id and entry.key == key:
                if latest is None or (entry.created_at, entry.seq) > (latest.created_at, latest.seq):
                    latest = entry
        if latest is None:
            return None
        return latest.value

    def get_agent_memories(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all memories belonging to *agent_id*, newest first."""
        results = [
            self._to_dict(e)
            for e in self._memories.values()
            if e.agent_id == agent_id
        ]
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def search_memories(
        self,
        agent_id: str,
        memory_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search memories for *agent_id*, optionally filtered by *memory_type*."""
        results: List[Dict[str, Any]] = []
        for entry in self._memories.values():
            if entry.agent_id != agent_id:
                continue
            if memory_type is not None and entry.memory_type != memory_type:
                continue
            results.append(self._to_dict(entry))
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def forget(self, memory_id: str) -> bool:
        """Delete a single memory by ID.  Returns True if it existed."""
        entry = self._memories.pop(memory_id, None)
        if entry is None:
            return False
        self._fire("forget", {"memory_id": memory_id, "agent_id": entry.agent_id})
        return True

    def forget_all(self, agent_id: str) -> int:
        """Delete every memory belonging to *agent_id*.  Returns the count deleted."""
        to_remove = [
            mid for mid, e in self._memories.items()
            if e.agent_id == agent_id
        ]
        for mid in to_remove:
            del self._memories[mid]
        count = len(to_remove)
        if count > 0:
            self._fire("forget_all", {"agent_id": agent_id, "count": count})
        return count

    def list_agents(self) -> List[str]:
        """Return a sorted list of all agent IDs that have stored memories."""
        agents: set[str] = set()
        for entry in self._memories.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def get_memory_count(self) -> int:
        """Return the total number of stored memories."""
        return len(self._memories)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.  Returns True if it existed."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Notify all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a summary of the store's current state."""
        types: Dict[str, int] = {}
        for entry in self._memories.values():
            types[entry.memory_type] = types.get(entry.memory_type, 0) + 1
        return {
            "total_memories": len(self._memories),
            "total_agents": len(self.list_agents()),
            "max_entries": self._max_entries,
            "memory_types": types,
            "callbacks": len(self._callbacks),
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all memories, callbacks, and counters."""
        self._memories.clear()
        self._callbacks.clear()
        self._seq = 0

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest entries to make room when at capacity."""
        if not self._memories:
            return
        entries = sorted(self._memories.values(), key=lambda e: e.created_at)
        to_remove = max(len(entries) // 4, 1)
        for entry in entries[:to_remove]:
            del self._memories[entry.memory_id]
        self._fire("prune", {"count": to_remove})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_dict(self, entry: MemoryEntry) -> Dict[str, Any]:
        """Convert a MemoryEntry to a plain dict."""
        return {
            "memory_id": entry.memory_id,
            "agent_id": entry.agent_id,
            "key": entry.key,
            "value": entry.value,
            "memory_type": entry.memory_type,
            "created_at": entry.created_at,
        }
