"""Agent capability matcher - match tasks to agents based on required capabilities."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class AgentProfile:
    """Agent capability profile."""
    name: str = ""
    capabilities: set = field(default_factory=set)
    proficiency: dict = field(default_factory=dict)  # capability -> 0.0-1.0
    max_concurrent: int = 5
    current_load: int = 0
    available: bool = True
    tags: list = field(default_factory=list)
    registered_at: float = 0.0


@dataclass
class TaskRequirement:
    """Task capability requirements."""
    task_id: str = ""
    name: str = ""
    required_capabilities: set = field(default_factory=set)
    preferred_capabilities: set = field(default_factory=set)
    min_proficiency: float = 0.0
    tags: list = field(default_factory=list)
    created_at: float = 0.0


class AgentCapabilityMatcher:
    """Match tasks to agents based on capabilities and proficiency."""

    def __init__(self, max_agents: int = 1000, max_tasks: int = 50000):
        self._max_agents = max(1, max_agents)
        self._max_tasks = max(1, max_tasks)
        self._agents: Dict[str, AgentProfile] = {}
        self._tasks: Dict[str, TaskRequirement] = {}
        self._assignments: Dict[str, str] = {}  # task_id -> agent_name
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_tasks_created": 0,
            "total_matched": 0,
            "total_no_match": 0,
        }

    # --- Agent Management ---

    def register_agent(
        self,
        name: str,
        capabilities: Optional[List[str]] = None,
        proficiency: Optional[Dict[str, float]] = None,
        max_concurrent: int = 5,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Register an agent with capabilities."""
        if not name or name in self._agents:
            return False
        if max_concurrent < 1:
            return False
        if len(self._agents) >= self._max_agents:
            return False

        caps = set(capabilities or [])
        prof = {}
        for c in caps:
            prof[c] = (proficiency or {}).get(c, 1.0)

        self._agents[name] = AgentProfile(
            name=name,
            capabilities=caps,
            proficiency=prof,
            max_concurrent=max_concurrent,
            tags=list(tags or []),
            registered_at=time.time(),
        )
        self._stats["total_registered"] += 1
        return True

    def unregister_agent(self, name: str) -> bool:
        """Unregister an agent."""
        if name not in self._agents:
            return False
        del self._agents[name]
        return True

    def get_agent(self, name: str) -> Optional[Dict]:
        """Get agent profile."""
        a = self._agents.get(name)
        if not a:
            return None
        return {
            "name": a.name,
            "capabilities": sorted(a.capabilities),
            "proficiency": dict(a.proficiency),
            "max_concurrent": a.max_concurrent,
            "current_load": a.current_load,
            "available": a.available,
            "tags": list(a.tags),
        }

    def add_capability(self, name: str, capability: str, proficiency: float = 1.0) -> bool:
        """Add a capability to an agent."""
        a = self._agents.get(name)
        if not a or not capability:
            return False
        if capability in a.capabilities:
            return False
        a.capabilities.add(capability)
        a.proficiency[capability] = max(0.0, min(1.0, proficiency))
        return True

    def remove_capability(self, name: str, capability: str) -> bool:
        """Remove a capability from an agent."""
        a = self._agents.get(name)
        if not a or capability not in a.capabilities:
            return False
        a.capabilities.discard(capability)
        a.proficiency.pop(capability, None)
        return True

    def set_proficiency(self, name: str, capability: str, level: float) -> bool:
        """Set proficiency level for a capability."""
        a = self._agents.get(name)
        if not a or capability not in a.capabilities:
            return False
        if level < 0.0 or level > 1.0:
            return False
        a.proficiency[capability] = level
        return True

    def set_available(self, name: str, available: bool) -> bool:
        """Set agent availability."""
        a = self._agents.get(name)
        if not a:
            return False
        a.available = available
        return True

    def list_agents(self, capability: str = "", tag: str = "", available_only: bool = False) -> List[Dict]:
        """List agents with filters."""
        results = []
        for a in self._agents.values():
            if capability and capability not in a.capabilities:
                continue
            if tag and tag not in a.tags:
                continue
            if available_only and not a.available:
                continue
            results.append({
                "name": a.name,
                "capabilities": sorted(a.capabilities),
                "current_load": a.current_load,
                "available": a.available,
            })
        return results

    # --- Task Management ---

    def create_task(
        self,
        name: str,
        required: Optional[List[str]] = None,
        preferred: Optional[List[str]] = None,
        min_proficiency: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a task with capability requirements."""
        if not name:
            return ""
        if len(self._tasks) >= self._max_tasks:
            return ""

        tid = f"match-{uuid.uuid4().hex[:12]}"
        self._tasks[tid] = TaskRequirement(
            task_id=tid,
            name=name,
            required_capabilities=set(required or []),
            preferred_capabilities=set(preferred or []),
            min_proficiency=max(0.0, min(1.0, min_proficiency)),
            tags=list(tags or []),
            created_at=time.time(),
        )
        self._stats["total_tasks_created"] += 1
        return tid

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task requirements."""
        t = self._tasks.get(task_id)
        if not t:
            return None
        return {
            "task_id": t.task_id,
            "name": t.name,
            "required_capabilities": sorted(t.required_capabilities),
            "preferred_capabilities": sorted(t.preferred_capabilities),
            "min_proficiency": t.min_proficiency,
            "tags": list(t.tags),
            "assigned_to": self._assignments.get(t.task_id, ""),
        }

    def remove_task(self, task_id: str) -> bool:
        """Remove a task."""
        if task_id not in self._tasks:
            return False
        self._assignments.pop(task_id, None)
        del self._tasks[task_id]
        return True

    # --- Matching ---

    def find_matches(self, task_id: str, limit: int = 10) -> List[Dict]:
        """Find agents matching task requirements, scored by fit."""
        t = self._tasks.get(task_id)
        if not t:
            return []

        candidates = []
        for a in self._agents.values():
            if not a.available:
                continue
            if a.current_load >= a.max_concurrent:
                continue
            # Must have all required capabilities
            if not t.required_capabilities.issubset(a.capabilities):
                continue
            # Check min proficiency on required capabilities
            if t.min_proficiency > 0:
                meets_prof = all(
                    a.proficiency.get(c, 0.0) >= t.min_proficiency
                    for c in t.required_capabilities
                )
                if not meets_prof:
                    continue

            # Score: required match (base) + preferred overlap + avg proficiency
            preferred_overlap = len(t.preferred_capabilities & a.capabilities)
            preferred_total = max(1, len(t.preferred_capabilities))
            preferred_score = preferred_overlap / preferred_total

            req_caps = t.required_capabilities or a.capabilities
            avg_prof = sum(a.proficiency.get(c, 0.0) for c in req_caps) / max(1, len(req_caps))

            load_ratio = 1.0 - (a.current_load / a.max_concurrent)
            score = (avg_prof * 0.4) + (preferred_score * 0.3) + (load_ratio * 0.3)

            candidates.append({
                "name": a.name,
                "score": round(score, 3),
                "preferred_match": preferred_overlap,
                "avg_proficiency": round(avg_prof, 3),
                "current_load": a.current_load,
            })

        candidates.sort(key=lambda x: -x["score"])
        return candidates[:limit]

    def auto_assign(self, task_id: str) -> str:
        """Assign task to best matching agent. Returns agent name or empty."""
        matches = self.find_matches(task_id, limit=1)
        if not matches:
            self._stats["total_no_match"] += 1
            return ""

        agent_name = matches[0]["name"]
        a = self._agents.get(agent_name)
        if not a:
            return ""

        a.current_load += 1
        self._assignments[task_id] = agent_name
        self._stats["total_matched"] += 1
        self._fire("task_assigned", {"task_id": task_id, "agent": agent_name})
        return agent_name

    def release_assignment(self, task_id: str) -> bool:
        """Release a task assignment."""
        agent_name = self._assignments.pop(task_id, "")
        if not agent_name:
            return False
        a = self._agents.get(agent_name)
        if a and a.current_load > 0:
            a.current_load -= 1
        return True

    def get_agent_assignments(self, name: str) -> List[str]:
        """Get task IDs assigned to an agent."""
        return [tid for tid, aname in self._assignments.items() if aname == name]

    # --- Analytics ---

    def get_capability_coverage(self) -> Dict[str, int]:
        """How many agents have each capability."""
        coverage: Dict[str, int] = {}
        for a in self._agents.values():
            for c in a.capabilities:
                coverage[c] = coverage.get(c, 0) + 1
        return coverage

    def get_unmatched_capabilities(self, task_id: str) -> List[str]:
        """Get required capabilities no agent can satisfy."""
        t = self._tasks.get(task_id)
        if not t:
            return []
        all_caps: Set[str] = set()
        for a in self._agents.values():
            all_caps.update(a.capabilities)
        return sorted(t.required_capabilities - all_caps)

    # --- Callbacks ---

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

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_agents": len(self._agents),
            "current_tasks": len(self._tasks),
            "current_assignments": len(self._assignments),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._tasks.clear()
        self._assignments.clear()
        self._callbacks.clear()
        self._stats = {
            "total_registered": 0,
            "total_tasks_created": 0,
            "total_matched": 0,
            "total_no_match": 0,
        }

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
