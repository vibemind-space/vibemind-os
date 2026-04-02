"""
Agent Capability Registry — Dynamic discovery and routing of agent skills.

Provides:
- Registration of agent capabilities (languages, frameworks, task types)
- Skill-based routing: find best agent for a given task
- Priority/affinity scoring for agent selection
- Runtime capability updates (agents can learn new skills)
- Agent availability tracking (online/offline/busy)

Usage::

    registry = AgentCapabilityRegistry()

    registry.register_agent("FrontendAgent", AgentCapability(
        agent_name="FrontendAgent",
        languages={"typescript", "javascript", "css", "html"},
        frameworks={"react", "nextjs", "tailwind"},
        task_types={"ui_component", "page_layout", "styling"},
        priority=1,
    ))

    # Find best agent for a task
    best = registry.find_best_agent(
        language="typescript",
        framework="react",
        task_type="ui_component",
    )
    # => "FrontendAgent"
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class AgentAvailability(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class AgentCapability:
    """Describes what an agent can do."""
    agent_name: str
    languages: Set[str] = field(default_factory=set)
    frameworks: Set[str] = field(default_factory=set)
    task_types: Set[str] = field(default_factory=set)
    specialties: Set[str] = field(default_factory=set)  # e.g., "security", "performance"
    max_concurrent_tasks: int = 1
    priority: int = 5  # Lower = higher priority
    description: str = ""

    def matches(self, language: str = "", framework: str = "", task_type: str = "") -> float:
        """
        Score how well this agent matches a task request.
        Returns 0.0 (no match) to 1.0 (perfect match).
        """
        score = 0.0
        checks = 0

        if language:
            checks += 1
            if language.lower() in {l.lower() for l in self.languages}:
                score += 1.0

        if framework:
            checks += 1
            if framework.lower() in {f.lower() for f in self.frameworks}:
                score += 1.0

        if task_type:
            checks += 1
            if task_type.lower() in {t.lower() for t in self.task_types}:
                score += 1.0

        if checks == 0:
            return 0.0
        return score / checks

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "languages": sorted(self.languages),
            "frameworks": sorted(self.frameworks),
            "task_types": sorted(self.task_types),
            "specialties": sorted(self.specialties),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "priority": self.priority,
            "description": self.description,
        }


@dataclass
class AgentStatus:
    """Runtime status of an agent."""
    agent_name: str
    availability: AgentAvailability = AgentAvailability.ONLINE
    current_tasks: int = 0
    total_tasks_completed: int = 0
    last_active_at: Optional[float] = None
    error_message: Optional[str] = None
    registered_at: float = field(default_factory=time.time)


class AgentCapabilityRegistry:
    """
    Central registry for agent capabilities and availability.
    """

    def __init__(self):
        self._capabilities: Dict[str, AgentCapability] = {}
        self._status: Dict[str, AgentStatus] = {}
        self.logger = logger.bind(component="agent_registry")

    def register_agent(self, agent_name: str, capability: AgentCapability):
        """Register an agent with its capabilities."""
        self._capabilities[agent_name] = capability
        if agent_name not in self._status:
            self._status[agent_name] = AgentStatus(agent_name=agent_name)

        self.logger.info(
            "agent_registered",
            agent=agent_name,
            languages=len(capability.languages),
            frameworks=len(capability.frameworks),
            task_types=len(capability.task_types),
        )

    def unregister_agent(self, agent_name: str):
        """Remove an agent from the registry."""
        self._capabilities.pop(agent_name, None)
        self._status.pop(agent_name, None)

    def update_capability(self, agent_name: str, **updates):
        """Update specific capability fields for an agent."""
        cap = self._capabilities.get(agent_name)
        if not cap:
            return False

        for key, value in updates.items():
            if hasattr(cap, key):
                current = getattr(cap, key)
                if isinstance(current, set) and isinstance(value, (set, list)):
                    current.update(value)
                else:
                    setattr(cap, key, value)
        return True

    def set_availability(self, agent_name: str, availability: AgentAvailability, error: str = ""):
        """Update agent availability status."""
        status = self._status.get(agent_name)
        if status:
            status.availability = availability
            status.error_message = error if error else None
            status.last_active_at = time.time()

    def mark_busy(self, agent_name: str):
        """Mark agent as busy (processing a task)."""
        status = self._status.get(agent_name)
        if status:
            status.availability = AgentAvailability.BUSY
            status.current_tasks += 1
            status.last_active_at = time.time()

    def mark_free(self, agent_name: str):
        """Mark agent as done with a task."""
        status = self._status.get(agent_name)
        if status:
            status.current_tasks = max(0, status.current_tasks - 1)
            status.total_tasks_completed += 1
            status.last_active_at = time.time()
            cap = self._capabilities.get(agent_name)
            if status.current_tasks == 0 or (cap and status.current_tasks < cap.max_concurrent_tasks):
                status.availability = AgentAvailability.ONLINE

    def find_best_agent(
        self,
        language: str = "",
        framework: str = "",
        task_type: str = "",
        specialty: str = "",
        require_available: bool = True,
    ) -> Optional[str]:
        """
        Find the best agent for a task based on capabilities and availability.

        Scoring:
        1. Capability match (0.0 - 1.0)
        2. Priority (lower is better)
        3. Availability (available agents preferred)
        4. Current load (less busy preferred)
        """
        candidates = []

        for name, cap in self._capabilities.items():
            status = self._status.get(name)

            # Filter by availability
            if require_available and status:
                if status.availability not in (AgentAvailability.ONLINE, AgentAvailability.BUSY):
                    continue
                if cap.max_concurrent_tasks > 0 and status.current_tasks >= cap.max_concurrent_tasks:
                    continue

            # Calculate match score
            match_score = cap.matches(language, framework, task_type)

            # Check specialty
            if specialty and specialty.lower() not in {s.lower() for s in cap.specialties}:
                match_score *= 0.5  # Penalize but don't exclude

            if match_score == 0.0:
                continue

            # Calculate composite score (higher is better)
            priority_score = 1.0 / max(cap.priority, 1)
            load_score = 1.0 / (1 + (status.current_tasks if status else 0))

            composite = match_score * 0.6 + priority_score * 0.25 + load_score * 0.15

            candidates.append((name, composite, match_score))

        if not candidates:
            return None

        # Sort by composite score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def find_agents_for_task(
        self,
        language: str = "",
        framework: str = "",
        task_type: str = "",
        min_score: float = 0.3,
    ) -> List[dict]:
        """Find all agents matching a task, ranked by fit."""
        results = []

        for name, cap in self._capabilities.items():
            score = cap.matches(language, framework, task_type)
            if score >= min_score:
                status = self._status.get(name)
                results.append({
                    "agent_name": name,
                    "match_score": round(score, 2),
                    "priority": cap.priority,
                    "availability": status.availability.value if status else "unknown",
                    "current_tasks": status.current_tasks if status else 0,
                })

        results.sort(key=lambda x: (-x["match_score"], x["priority"]))
        return results

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_agent(self, agent_name: str) -> Optional[dict]:
        """Get full info about an agent."""
        cap = self._capabilities.get(agent_name)
        if not cap:
            return None

        status = self._status.get(agent_name)
        return {
            "capability": cap.to_dict(),
            "status": {
                "availability": status.availability.value if status else "unknown",
                "current_tasks": status.current_tasks if status else 0,
                "total_completed": status.total_tasks_completed if status else 0,
                "last_active_at": status.last_active_at if status else None,
            },
        }

    def list_agents(self, availability: Optional[AgentAvailability] = None) -> List[dict]:
        """List all registered agents, optionally filtered by availability."""
        results = []
        for name, cap in self._capabilities.items():
            status = self._status.get(name)
            if availability and status and status.availability != availability:
                continue
            results.append({
                "agent_name": name,
                "languages": sorted(cap.languages),
                "task_types": sorted(cap.task_types),
                "priority": cap.priority,
                "availability": status.availability.value if status else "unknown",
                "current_tasks": status.current_tasks if status else 0,
            })
        return results

    def get_capability_matrix(self) -> dict:
        """Get a matrix of all agents vs capabilities."""
        all_languages = set()
        all_frameworks = set()
        all_task_types = set()

        for cap in self._capabilities.values():
            all_languages.update(cap.languages)
            all_frameworks.update(cap.frameworks)
            all_task_types.update(cap.task_types)

        matrix = {}
        for name, cap in self._capabilities.items():
            matrix[name] = {
                "languages": {l: l in cap.languages for l in sorted(all_languages)},
                "frameworks": {f: f in cap.frameworks for f in sorted(all_frameworks)},
                "task_types": {t: t in cap.task_types for t in sorted(all_task_types)},
            }

        return {
            "agents": matrix,
            "all_languages": sorted(all_languages),
            "all_frameworks": sorted(all_frameworks),
            "all_task_types": sorted(all_task_types),
        }

    def get_stats(self) -> dict:
        """Get registry statistics."""
        online = sum(1 for s in self._status.values() if s.availability == AgentAvailability.ONLINE)
        busy = sum(1 for s in self._status.values() if s.availability == AgentAvailability.BUSY)
        offline = sum(1 for s in self._status.values() if s.availability == AgentAvailability.OFFLINE)

        return {
            "total_agents": len(self._capabilities),
            "online": online,
            "busy": busy,
            "offline": offline,
            "total_tasks_in_progress": sum(s.current_tasks for s in self._status.values()),
            "total_tasks_completed": sum(s.total_tasks_completed for s in self._status.values()),
        }
