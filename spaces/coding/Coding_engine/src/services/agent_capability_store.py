"""Agent capability store.

Registers, queries, and matches agent capabilities. Provides
capability-based agent discovery and comparison utilities.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _AgentEntry:
    """Internal agent record."""
    agent_id: str = ""
    tags: List[str] = field(default_factory=list)
    capabilities: Dict[str, float] = field(default_factory=dict)
    registered_at: float = 0.0


class AgentCapabilityStore:
    """Registers, queries, and matches agent capabilities."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._agents: Dict[str, _AgentEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_agents_registered": 0,
            "total_agents_removed": 0,
            "total_capabilities_added": 0,
            "total_capabilities_removed": 0,
            "total_lookups": 0,
            "total_comparisons": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'acaps-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acaps-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._agents) < self._max_entries:
            return
        sorted_agents = sorted(
            self._agents.values(), key=lambda a: a.registered_at
        )
        remove_count = len(self._agents) - self._max_entries + 1
        for entry in sorted_agents[:remove_count]:
            del self._agents[entry.agent_id]
            self._stats["total_agents_removed"] += 1
            logger.debug("agent_pruned", agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str,
                       tags: Optional[List[str]] = None) -> str:
        """Register an agent. Returns agent_id or '' if duplicate."""
        if not agent_id:
            return ""
        if agent_id in self._agents:
            logger.warning("duplicate_agent", agent_id=agent_id)
            return ""

        self._prune_if_needed()

        entry = _AgentEntry(
            agent_id=agent_id,
            tags=list(tags) if tags else [],
            capabilities={},
            registered_at=time.time(),
        )
        self._agents[agent_id] = entry
        self._stats["total_agents_registered"] += 1

        logger.info("agent_registered", agent_id=agent_id, tags=entry.tags)
        self._fire("agent_registered", {
            "agent_id": agent_id, "tags": entry.tags
        })
        return agent_id

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent and all its capabilities."""
        if agent_id not in self._agents:
            return False
        cap_count = len(self._agents[agent_id].capabilities)
        del self._agents[agent_id]
        self._stats["total_agents_removed"] += 1
        self._stats["total_capabilities_removed"] += cap_count

        logger.info("agent_removed", agent_id=agent_id)
        self._fire("agent_removed", {"agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Capability management
    # ------------------------------------------------------------------

    def add_capability(self, agent_id: str, capability: str,
                       level: float = 1.0) -> bool:
        """Add or update a capability for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            logger.warning("agent_not_found", agent_id=agent_id)
            return False
        if not capability:
            return False
        if not (0.0 <= level <= 1.0):
            return False

        is_new = capability not in entry.capabilities
        entry.capabilities[capability] = level

        if is_new:
            self._stats["total_capabilities_added"] += 1

        logger.debug("capability_added", agent_id=agent_id,
                     capability=capability, level=level)
        self._fire("capability_added", {
            "agent_id": agent_id,
            "capability": capability,
            "level": level,
        })
        return True

    def remove_capability(self, agent_id: str, capability: str) -> bool:
        """Remove a capability from an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        if capability not in entry.capabilities:
            return False

        del entry.capabilities[capability]
        self._stats["total_capabilities_removed"] += 1

        logger.debug("capability_removed", agent_id=agent_id,
                     capability=capability)
        self._fire("capability_removed", {
            "agent_id": agent_id, "capability": capability
        })
        return True

    def get_capabilities(self, agent_id: str) -> List[Dict]:
        """Get all capabilities for an agent as list of dicts."""
        entry = self._agents.get(agent_id)
        if not entry:
            return []
        result = []
        for cap, lvl in sorted(entry.capabilities.items()):
            result.append({"capability": cap, "level": lvl})
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def find_agents_with(self, capability: str,
                         min_level: float = 0.0) -> List[Dict]:
        """Find agents that have a given capability at or above min_level."""
        self._stats["total_lookups"] += 1
        result = []
        for entry in self._agents.values():
            level = entry.capabilities.get(capability)
            if level is not None and level >= min_level:
                result.append({
                    "agent_id": entry.agent_id,
                    "level": level,
                })
        result.sort(key=lambda x: -x["level"])
        return result

    def get_best_agent(self, capability: str) -> Optional[Dict]:
        """Get the agent with the highest level for a capability."""
        self._stats["total_lookups"] += 1
        best: Optional[Dict] = None
        best_level = -1.0

        for entry in self._agents.values():
            level = entry.capabilities.get(capability)
            if level is not None and level > best_level:
                best_level = level
                best = {"agent_id": entry.agent_id, "level": level}

        return best

    def compare_agents(self, agent_id1: str, agent_id2: str) -> Dict:
        """Compare capabilities of two agents.

        Returns dict with shared capabilities (with both levels) and
        unique capabilities for each agent.
        """
        self._stats["total_comparisons"] += 1

        entry1 = self._agents.get(agent_id1)
        entry2 = self._agents.get(agent_id2)

        caps1: Dict[str, float] = entry1.capabilities if entry1 else {}
        caps2: Dict[str, float] = entry2.capabilities if entry2 else {}

        keys1 = set(caps1.keys())
        keys2 = set(caps2.keys())

        shared = []
        for cap in sorted(keys1 & keys2):
            shared.append({
                "capability": cap,
                "level_agent1": caps1[cap],
                "level_agent2": caps2[cap],
            })

        unique1 = []
        for cap in sorted(keys1 - keys2):
            unique1.append({"capability": cap, "level": caps1[cap]})

        unique2 = []
        for cap in sorted(keys2 - keys1):
            unique2.append({"capability": cap, "level": caps2[cap]})

        return {
            "agent_id1": agent_id1,
            "agent_id2": agent_id2,
            "shared": shared,
            "unique_to_agent1": unique1,
            "unique_to_agent2": unique2,
        }

    def list_agents(self, tag: Optional[str] = None) -> List[str]:
        """List agent IDs, optionally filtered by tag."""
        result = []
        for entry in self._agents.values():
            if tag is not None and tag not in entry.tags:
                continue
            result.append(entry.agent_id)
        return sorted(result)

    def get_all_capabilities(self) -> List[str]:
        """Get all unique capability strings across agents."""
        all_caps: Set[str] = set()
        for entry in self._agents.values():
            all_caps.update(entry.capabilities.keys())
        return sorted(all_caps)

    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Get full agent info including tags and capabilities."""
        entry = self._agents.get(agent_id)
        if not entry:
            return None
        return {
            "agent_id": entry.agent_id,
            "tags": list(entry.tags),
            "capabilities": [
                {"capability": cap, "level": lvl}
                for cap, lvl in sorted(entry.capabilities.items())
            ],
            "capability_count": len(entry.capabilities),
            "registered_at": entry.registered_at,
        }

    def find_agents_by_tag(self, tag: str) -> List[Dict]:
        """Find agents that have a specific tag, with capability summaries."""
        result = []
        for entry in self._agents.values():
            if tag not in entry.tags:
                continue
            avg_level = 0.0
            if entry.capabilities:
                avg_level = sum(entry.capabilities.values()) / len(
                    entry.capabilities
                )
            result.append({
                "agent_id": entry.agent_id,
                "tags": list(entry.tags),
                "capability_count": len(entry.capabilities),
                "avg_level": round(avg_level, 4),
            })
        result.sort(key=lambda x: x["agent_id"])
        return result

    def get_capability_summary(self) -> List[Dict]:
        """Get summary of each capability across all agents."""
        cap_data: Dict[str, List[float]] = {}
        for entry in self._agents.values():
            for cap, lvl in entry.capabilities.items():
                if cap not in cap_data:
                    cap_data[cap] = []
                cap_data[cap].append(lvl)

        result = []
        for cap in sorted(cap_data.keys()):
            levels = cap_data[cap]
            result.append({
                "capability": cap,
                "agent_count": len(levels),
                "min_level": round(min(levels), 4),
                "max_level": round(max(levels), 4),
                "avg_level": round(sum(levels) / len(levels), 4),
            })
        return result

    def bulk_add_capabilities(self, agent_id: str,
                              capabilities: Dict[str, float]) -> int:
        """Add multiple capabilities at once. Returns count of successes."""
        added = 0
        for cap, level in capabilities.items():
            if self.add_capability(agent_id, cap, level):
                added += 1
        return added

    def has_capability(self, agent_id: str, capability: str) -> bool:
        """Check if an agent has a specific capability."""
        entry = self._agents.get(agent_id)
        if not entry:
            return False
        return capability in entry.capabilities

    def get_capability_level(self, agent_id: str,
                             capability: str) -> Optional[float]:
        """Get the level of a specific capability for an agent."""
        entry = self._agents.get(agent_id)
        if not entry:
            return None
        return entry.capabilities.get(capability)

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
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        total_caps = sum(
            len(e.capabilities) for e in self._agents.values()
        )
        unique_caps = len(self.get_all_capabilities())
        return {
            **self._stats,
            "current_agents": len(self._agents),
            "current_capabilities": total_caps,
            "unique_capabilities": unique_caps,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._agents.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
