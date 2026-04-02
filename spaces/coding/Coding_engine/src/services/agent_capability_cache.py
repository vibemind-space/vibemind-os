"""Agent capability cache.

Caches agent capabilities for fast lookup and discovery. Tracks
capability levels per agent with callback notifications on changes.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _State:
    """Internal cache state."""
    capabilities: Dict[str, Dict[str, Dict[str, Any]]] = field(
        default_factory=dict
    )
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentCapabilityCache:
    """Caches agent capabilities for fast lookup and discovery."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._state = _State()
        self._stats = {
            "total_cached": 0,
            "total_removed": 0,
            "total_lookups": 0,
            "total_hits": 0,
            "total_misses": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'acc-'."""
        self._state._seq += 1
        raw = f"{seed}:{time.time()}:{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acc-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _total_capability_count(self) -> int:
        """Count all cached capabilities across agents."""
        return sum(
            len(caps) for caps in self._state.capabilities.values()
        )

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if self._total_capability_count() < self._max_entries:
            return
        all_entries = []
        for agent_id, caps in self._state.capabilities.items():
            for cap_name, entry in caps.items():
                all_entries.append((agent_id, cap_name, entry))
        all_entries.sort(key=lambda x: x[2]["created_at"])
        remove_count = self._total_capability_count() - self._max_entries + 1
        for agent_id, cap_name, _ in all_entries[:remove_count]:
            if agent_id in self._state.capabilities:
                self._state.capabilities[agent_id].pop(cap_name, None)
                if not self._state.capabilities[agent_id]:
                    del self._state.capabilities[agent_id]
            self._stats["total_removed"] += 1
            logger.debug("capability_pruned", agent_id=agent_id,
                         capability=cap_name)

    # ------------------------------------------------------------------
    # Capability caching
    # ------------------------------------------------------------------

    def cache_capability(self, agent_id: str, capability: str,
                         level: int = 1) -> str:
        """Cache a capability for an agent. Returns cap_id."""
        if not agent_id or not capability:
            return ""

        self._prune_if_needed()

        cap_id = self._next_id(f"{agent_id}:{capability}")
        if agent_id not in self._state.capabilities:
            self._state.capabilities[agent_id] = {}

        self._state.capabilities[agent_id][capability] = {
            "cap_id": cap_id,
            "agent_id": agent_id,
            "capability": capability,
            "level": level,
            "created_at": time.time(),
        }
        self._stats["total_cached"] += 1

        logger.info("capability_cached", agent_id=agent_id,
                     capability=capability, level=level, cap_id=cap_id)
        self._fire("capability_cached", {
            "agent_id": agent_id,
            "capability": capability,
            "level": level,
            "cap_id": cap_id,
        })
        return cap_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_capabilities(self, agent_id: str) -> List[Dict]:
        """Get all capabilities for an agent as list of dicts."""
        self._stats["total_lookups"] += 1
        caps = self._state.capabilities.get(agent_id)
        if not caps:
            self._stats["total_misses"] += 1
            return []
        self._stats["total_hits"] += 1
        result = []
        for entry in sorted(caps.values(), key=lambda e: e["capability"]):
            result.append({
                "capability": entry["capability"],
                "level": entry["level"],
                "cap_id": entry["cap_id"],
            })
        return result

    def has_capability(self, agent_id: str, capability: str) -> bool:
        """Check if an agent has a specific capability cached."""
        self._stats["total_lookups"] += 1
        caps = self._state.capabilities.get(agent_id)
        if not caps:
            self._stats["total_misses"] += 1
            return False
        found = capability in caps
        if found:
            self._stats["total_hits"] += 1
        else:
            self._stats["total_misses"] += 1
        return found

    def get_capability_level(self, agent_id: str, capability: str) -> int:
        """Get the level of a specific capability. Returns 0 if not found."""
        self._stats["total_lookups"] += 1
        caps = self._state.capabilities.get(agent_id)
        if not caps:
            self._stats["total_misses"] += 1
            return 0
        entry = caps.get(capability)
        if not entry:
            self._stats["total_misses"] += 1
            return 0
        self._stats["total_hits"] += 1
        return entry["level"]

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_capability(self, agent_id: str, capability: str) -> bool:
        """Remove a cached capability from an agent."""
        caps = self._state.capabilities.get(agent_id)
        if not caps:
            return False
        if capability not in caps:
            return False

        del caps[capability]
        if not caps:
            del self._state.capabilities[agent_id]
        self._stats["total_removed"] += 1

        logger.info("capability_removed", agent_id=agent_id,
                     capability=capability)
        self._fire("capability_removed", {
            "agent_id": agent_id,
            "capability": capability,
        })
        return True

    # ------------------------------------------------------------------
    # Counts and listing
    # ------------------------------------------------------------------

    def get_capability_count(self, agent_id: str = "") -> int:
        """Get count of cached capabilities. If agent_id given, for that agent only."""
        if agent_id:
            caps = self._state.capabilities.get(agent_id)
            return len(caps) if caps else 0
        return self._total_capability_count()

    def list_agents(self) -> List[str]:
        """List all agent IDs that have cached capabilities."""
        return sorted(self._state.capabilities.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback."""
        if name in self._state.callbacks:
            return False
        self._state.callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return cache statistics."""
        return {
            **self._stats,
            "current_agents": len(self._state.capabilities),
            "current_capabilities": self._total_capability_count(),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.capabilities.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("cache_reset")
