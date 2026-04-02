"""Agent capability registry.

Tracks what capabilities each agent has, enables capability-based
task routing, and manages capability lifecycle.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Capability:
    """Internal capability record."""
    capability_id: str = ""
    name: str = ""
    agent: str = ""
    category: str = "general"
    proficiency: float = 1.0  # 0.0 - 1.0
    status: str = "active"  # active, deprecated, disabled
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    registered_at: float = 0.0
    updated_at: float = 0.0


class AgentCapabilityRegistry:
    """Tracks agent capabilities for routing and discovery."""

    CATEGORIES = ("general", "coding", "testing", "review", "design",
                  "analysis", "deployment", "monitoring", "custom")

    def __init__(self, max_capabilities: int = 50000):
        self._max_capabilities = max_capabilities
        self._capabilities: Dict[str, _Capability] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_deprecated": 0,
            "total_removed": 0,
            "total_lookups": 0,
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, agent: str, category: str = "general",
                 proficiency: float = 1.0, version: str = "1.0",
                 metadata: Optional[Dict] = None,
                 tags: Optional[List[str]] = None) -> str:
        """Register a capability for an agent."""
        if not name or not agent:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if not (0.0 <= proficiency <= 1.0):
            return ""
        if len(self._capabilities) >= self._max_capabilities:
            return ""

        cid = "cap-" + hashlib.md5(
            f"{name}{agent}{time.time()}".encode()
        ).hexdigest()[:12]
        now = time.time()

        self._capabilities[cid] = _Capability(
            capability_id=cid,
            name=name,
            agent=agent,
            category=category,
            proficiency=proficiency,
            version=version,
            metadata=dict(metadata or {}),
            tags=tags or [],
            registered_at=now,
            updated_at=now,
        )
        self._stats["total_registered"] += 1
        self._fire("capability_registered", {
            "capability_id": cid, "name": name, "agent": agent
        })
        return cid

    def get_capability(self, capability_id: str) -> Optional[Dict]:
        """Get capability info."""
        c = self._capabilities.get(capability_id)
        if not c:
            return None
        return {
            "capability_id": c.capability_id,
            "name": c.name,
            "agent": c.agent,
            "category": c.category,
            "proficiency": c.proficiency,
            "status": c.status,
            "version": c.version,
            "metadata": dict(c.metadata),
            "tags": list(c.tags),
            "usage_count": c.usage_count,
            "registered_at": c.registered_at,
            "updated_at": c.updated_at,
        }

    def update_capability(self, capability_id: str,
                          proficiency: Optional[float] = None,
                          version: Optional[str] = None,
                          tags: Optional[List[str]] = None,
                          metadata: Optional[Dict] = None) -> bool:
        """Update capability attributes."""
        c = self._capabilities.get(capability_id)
        if not c:
            return False
        if proficiency is not None:
            if not (0.0 <= proficiency <= 1.0):
                return False
            c.proficiency = proficiency
        if version:
            c.version = version
        if tags is not None:
            c.tags = list(tags)
        if metadata is not None:
            c.metadata.update(metadata)
        c.updated_at = time.time()
        return True

    def deprecate(self, capability_id: str) -> bool:
        """Deprecate a capability."""
        c = self._capabilities.get(capability_id)
        if not c or c.status != "active":
            return False
        c.status = "deprecated"
        c.updated_at = time.time()
        self._stats["total_deprecated"] += 1
        return True

    def disable(self, capability_id: str) -> bool:
        """Disable a capability."""
        c = self._capabilities.get(capability_id)
        if not c or c.status == "disabled":
            return False
        c.status = "disabled"
        c.updated_at = time.time()
        return True

    def enable(self, capability_id: str) -> bool:
        """Re-enable a capability."""
        c = self._capabilities.get(capability_id)
        if not c or c.status == "active":
            return False
        c.status = "active"
        c.updated_at = time.time()
        return True

    def remove(self, capability_id: str) -> bool:
        """Remove a capability."""
        if capability_id not in self._capabilities:
            return False
        del self._capabilities[capability_id]
        self._stats["total_removed"] += 1
        return True

    def record_usage(self, capability_id: str) -> bool:
        """Record that a capability was used."""
        c = self._capabilities.get(capability_id)
        if not c:
            return False
        c.usage_count += 1
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def find_agents(self, capability_name: str,
                    min_proficiency: float = 0.0) -> List[Dict]:
        """Find agents with a specific capability."""
        self._stats["total_lookups"] += 1
        result = []
        for c in self._capabilities.values():
            if c.name != capability_name or c.status != "active":
                continue
            if c.proficiency < min_proficiency:
                continue
            result.append({
                "capability_id": c.capability_id,
                "agent": c.agent,
                "proficiency": c.proficiency,
                "version": c.version,
            })
        result.sort(key=lambda x: -x["proficiency"])
        return result

    def get_agent_capabilities(self, agent: str,
                                active_only: bool = True) -> List[Dict]:
        """Get all capabilities for an agent."""
        result = []
        for c in self._capabilities.values():
            if c.agent != agent:
                continue
            if active_only and c.status != "active":
                continue
            result.append({
                "capability_id": c.capability_id,
                "name": c.name,
                "category": c.category,
                "proficiency": c.proficiency,
                "status": c.status,
                "version": c.version,
            })
        result.sort(key=lambda x: -x["proficiency"])
        return result

    def get_best_agent(self, capability_name: str) -> Optional[str]:
        """Get the agent with highest proficiency for a capability."""
        agents = self.find_agents(capability_name)
        if not agents:
            return None
        return agents[0]["agent"]

    def get_category_capabilities(self, category: str) -> List[Dict]:
        """Get all capabilities in a category."""
        result = []
        for c in self._capabilities.values():
            if c.category != category or c.status != "active":
                continue
            result.append({
                "capability_id": c.capability_id,
                "name": c.name,
                "agent": c.agent,
                "proficiency": c.proficiency,
            })
        return result

    def get_all_capability_names(self) -> List[str]:
        """Get unique capability names."""
        names: Set[str] = set()
        for c in self._capabilities.values():
            if c.status == "active":
                names.add(c.name)
        return sorted(names)

    def get_all_agents(self) -> List[str]:
        """Get all agents with capabilities."""
        agents: Set[str] = set()
        for c in self._capabilities.values():
            agents.add(c.agent)
        return sorted(agents)

    def get_agent_summary(self, agent: str) -> Dict:
        """Get summary of agent's capabilities."""
        caps = [c for c in self._capabilities.values() if c.agent == agent]
        if not caps:
            return {}

        by_category: Dict[str, int] = {}
        total_usage = 0
        avg_prof = 0.0

        for c in caps:
            by_category[c.category] = by_category.get(c.category, 0) + 1
            total_usage += c.usage_count
            avg_prof += c.proficiency

        return {
            "agent": agent,
            "total_capabilities": len(caps),
            "active": sum(1 for c in caps if c.status == "active"),
            "avg_proficiency": round(avg_prof / len(caps), 4),
            "total_usage": total_usage,
            "by_category": by_category,
        }

    def get_capability_coverage(self) -> List[Dict]:
        """Get how many agents can perform each capability."""
        coverage: Dict[str, Set[str]] = {}
        for c in self._capabilities.values():
            if c.status == "active":
                if c.name not in coverage:
                    coverage[c.name] = set()
                coverage[c.name].add(c.agent)

        result = [
            {"capability": name, "agent_count": len(agents)}
            for name, agents in coverage.items()
        ]
        result.sort(key=lambda x: -x["agent_count"])
        return result

    def list_capabilities(self, category: Optional[str] = None,
                          tag: Optional[str] = None,
                          status: Optional[str] = None) -> List[Dict]:
        """List capabilities with optional filters."""
        result = []
        for c in self._capabilities.values():
            if category and c.category != category:
                continue
            if tag and tag not in c.tags:
                continue
            if status and c.status != status:
                continue
            result.append({
                "capability_id": c.capability_id,
                "name": c.name,
                "agent": c.agent,
                "category": c.category,
                "proficiency": c.proficiency,
                "status": c.status,
            })
        return result

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_capabilities": len(self._capabilities),
            "active_capabilities": sum(
                1 for c in self._capabilities.values() if c.status == "active"
            ),
        }

    def reset(self) -> None:
        self._capabilities.clear()
        self._stats = {k: 0 for k in self._stats}
