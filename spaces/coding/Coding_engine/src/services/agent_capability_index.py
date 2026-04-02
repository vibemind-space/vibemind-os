"""Agent capability index.

Indexes what capabilities each agent has for fast lookup.
Supports registering capabilities, querying by agent or capability,
and discovering which agents provide a given capability.
"""

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class CapabilityEntry:
    """A single agent-capability registration."""
    entry_id: str = ""
    agent_id: str = ""
    capability: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class AgentCapabilityIndex:
    """Indexes what capabilities each agent has for fast lookup."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, CapabilityEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # Secondary indexes for fast lookup
        self._agent_to_entries: Dict[str, Set[str]] = {}
        self._capability_to_entries: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique ID with prefix 'aci-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"aci-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._entries) < self._max_entries:
            return
        sorted_entries = sorted(
            self._entries.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._entries) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            self._remove_entry(entry.entry_id)

    def _remove_entry(self, entry_id: str) -> None:
        """Remove an entry and update secondary indexes."""
        entry = self._entries.pop(entry_id, None)
        if not entry:
            return
        agent_set = self._agent_to_entries.get(entry.agent_id)
        if agent_set:
            agent_set.discard(entry_id)
            if not agent_set:
                del self._agent_to_entries[entry.agent_id]
        cap_set = self._capability_to_entries.get(entry.capability)
        if cap_set:
            cap_set.discard(entry_id)
            if not cap_set:
                del self._capability_to_entries[entry.capability]

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def register_capability(self, agent_id: str, capability: str,
                            metadata: Optional[Dict] = None) -> str:
        """Register a capability for an agent. Returns entry ID.

        If the agent already has this capability, returns the existing
        entry ID without creating a duplicate.
        """
        if not agent_id or not capability:
            return ""

        # Check for existing registration
        existing_ids = self._agent_to_entries.get(agent_id, set())
        for eid in existing_ids:
            existing = self._entries.get(eid)
            if existing and existing.capability == capability:
                return existing.entry_id

        self._prune_if_needed()

        self._seq += 1
        entry_id = self._next_id(f"{agent_id}:{capability}")
        entry = CapabilityEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            capability=capability,
            metadata=dict(metadata) if metadata else {},
            created_at=time.time(),
            seq=self._seq,
        )
        self._entries[entry_id] = entry

        # Update secondary indexes
        self._agent_to_entries.setdefault(agent_id, set()).add(entry_id)
        self._capability_to_entries.setdefault(capability, set()).add(entry_id)

        self._fire("capability_registered", asdict(entry))
        return entry_id

    def get_capability(self, entry_id: str) -> Optional[Dict]:
        """Get capability entry by ID."""
        entry = self._entries.get(entry_id)
        if not entry:
            return None
        return asdict(entry)

    def get_agent_capabilities(self, agent_id: str) -> List[str]:
        """Get all capabilities for an agent."""
        entry_ids = self._agent_to_entries.get(agent_id, set())
        capabilities = []
        for eid in sorted(entry_ids):
            entry = self._entries.get(eid)
            if entry:
                capabilities.append(entry.capability)
        return sorted(capabilities)

    def find_agents_with_capability(self, capability: str) -> List[str]:
        """Find all agents that have a capability."""
        entry_ids = self._capability_to_entries.get(capability, set())
        agents: Set[str] = set()
        for eid in entry_ids:
            entry = self._entries.get(eid)
            if entry:
                agents.add(entry.agent_id)
        return sorted(agents)

    def has_capability(self, agent_id: str, capability: str) -> bool:
        """Check if agent has capability."""
        entry_ids = self._agent_to_entries.get(agent_id, set())
        for eid in entry_ids:
            entry = self._entries.get(eid)
            if entry and entry.capability == capability:
                return True
        return False

    def remove_capability(self, agent_id: str, capability: str) -> bool:
        """Remove a capability from an agent."""
        entry_ids = self._agent_to_entries.get(agent_id, set())
        for eid in list(entry_ids):
            entry = self._entries.get(eid)
            if entry and entry.capability == capability:
                self._seq += 1
                self._remove_entry(eid)
                self._fire("capability_removed", {
                    "agent_id": agent_id,
                    "capability": capability,
                })
                return True
        return False

    def list_capabilities(self) -> List[str]:
        """List all unique capabilities."""
        return sorted(self._capability_to_entries.keys())

    def list_agents(self) -> List[str]:
        """List all agents."""
        return sorted(self._agent_to_entries.keys())

    def get_entry_count(self) -> int:
        """Total entry count."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return index statistics."""
        return {
            "total_entries": len(self._entries),
            "total_agents": len(self._agent_to_entries),
            "total_capabilities": len(self._capability_to_entries),
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._entries.clear()
        self._callbacks.clear()
        self._agent_to_entries.clear()
        self._capability_to_entries.clear()
        self._seq = 0
