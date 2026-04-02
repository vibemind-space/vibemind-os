"""Agent Skill Matcher – match agents to tasks based on skill profiles.

Maintains agent skill profiles with proficiency levels and task profiles
with required skills. Finds the best agent for a task based on skill
overlap and proficiency scoring.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _AgentProfile:
    profile_id: str
    agent_id: str
    skills: Dict[str, float]  # skill_name -> proficiency (0-100)
    tags: List[str]
    created_at: float


@dataclass
class _TaskProfile:
    task_id: str
    task_name: str
    required_skills: List[str]
    min_proficiency: float
    tags: List[str]
    created_at: float


@dataclass
class _MatchEvent:
    event_id: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class AgentSkillMatcher:
    """Match agents to tasks based on skill profiles and proficiency."""

    def __init__(self, max_agents: int = 5000, max_history: int = 100000):
        self._max_agents = max_agents
        self._max_history = max_history
        self._agents: Dict[str, _AgentProfile] = {}
        self._tasks: Dict[str, _TaskProfile] = {}
        self._history: List[_MatchEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_agents_registered = 0
        self._total_tasks_created = 0
        self._total_matches_performed = 0
        self._total_skills_added = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, prefix: str, label: str) -> str:
        self._seq += 1
        raw = f"{label}-{self._seq}-{time.time()}"
        return prefix + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Agent Management
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, tags: Optional[List[str]] = None) -> str:
        """Register an agent with an optional tag list. Returns profile ID."""
        if not agent_id:
            return ""
        if agent_id in self._agents:
            return self._agents[agent_id].profile_id
        if len(self._agents) >= self._max_agents:
            return ""

        profile_id = self._make_id("asm-", agent_id)
        profile = _AgentProfile(
            profile_id=profile_id,
            agent_id=agent_id,
            skills={},
            tags=list(tags or []),
            created_at=time.time(),
        )
        self._agents[agent_id] = profile
        self._total_agents_registered += 1
        self._record("agent_registered", {"profile_id": profile_id, "agent_id": agent_id})
        return profile_id

    def add_skill(self, agent_id: str, skill_name: str, proficiency: float = 50.0) -> bool:
        """Add or update a skill on an agent. Proficiency 0-100."""
        if agent_id not in self._agents:
            return False
        if not skill_name:
            return False
        proficiency = max(0.0, min(100.0, proficiency))
        self._agents[agent_id].skills[skill_name] = proficiency
        self._total_skills_added += 1
        self._record("skill_added", {
            "agent_id": agent_id, "skill_name": skill_name,
            "proficiency": proficiency,
        })
        return True

    def remove_skill(self, agent_id: str, skill_name: str) -> bool:
        """Remove a skill from an agent."""
        if agent_id not in self._agents:
            return False
        if skill_name not in self._agents[agent_id].skills:
            return False
        del self._agents[agent_id].skills[skill_name]
        self._record("skill_removed", {"agent_id": agent_id, "skill_name": skill_name})
        return True

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent profile entirely."""
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        self._record("agent_removed", {"agent_id": agent_id})
        return True

    def get_agent_profile(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return agent profile including skills dict and skill_count."""
        profile = self._agents.get(agent_id)
        if not profile:
            return None
        return {
            "profile_id": profile.profile_id,
            "agent_id": profile.agent_id,
            "skills": dict(profile.skills),
            "skill_count": len(profile.skills),
            "tags": list(profile.tags),
            "created_at": profile.created_at,
        }

    def get_agent_utilization(self, agent_id: str) -> Dict[str, Any]:
        """How many tasks this agent is matched to and skills coverage."""
        profile = self._agents.get(agent_id)
        if not profile:
            return {"agent_id": agent_id, "matched_tasks": 0, "skills_coverage": {}}

        matched_tasks = 0
        coverage: Dict[str, int] = {}
        for task in self._tasks.values():
            overlap = [s for s in task.required_skills if s in profile.skills]
            if overlap:
                matched_tasks += 1
                for s in overlap:
                    coverage[s] = coverage.get(s, 0) + 1
        return {
            "agent_id": agent_id,
            "matched_tasks": matched_tasks,
            "skills_coverage": coverage,
        }

    def list_agents(self, skill: str = "", tag: str = "") -> List[Dict[str, Any]]:
        """List agents, optionally filtered by skill or tag."""
        results = []
        for profile in self._agents.values():
            if skill and skill not in profile.skills:
                continue
            if tag and tag not in profile.tags:
                continue
            results.append({
                "profile_id": profile.profile_id,
                "agent_id": profile.agent_id,
                "skill_count": len(profile.skills),
                "tags": list(profile.tags),
                "created_at": profile.created_at,
            })
        return results

    # ------------------------------------------------------------------
    # Task Profile Management
    # ------------------------------------------------------------------

    def create_task_profile(
        self,
        task_name: str,
        required_skills: Optional[List[str]] = None,
        min_proficiency: float = 30.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a task profile with required skills. Returns task ID."""
        if not task_name:
            return ""
        if task_name in self._tasks:
            return self._tasks[task_name].task_id

        task_id = self._make_id("atp-", task_name)
        tp = _TaskProfile(
            task_id=task_id,
            task_name=task_name,
            required_skills=list(required_skills or []),
            min_proficiency=max(0.0, min(100.0, min_proficiency)),
            tags=list(tags or []),
            created_at=time.time(),
        )
        self._tasks[task_name] = tp
        self._total_tasks_created += 1
        self._record("task_created", {"task_id": task_id, "task_name": task_name})
        return task_id

    def get_task_profile(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Return task profile dict."""
        tp = self._tasks.get(task_name)
        if not tp:
            return None
        return {
            "task_id": tp.task_id,
            "task_name": tp.task_name,
            "required_skills": list(tp.required_skills),
            "min_proficiency": tp.min_proficiency,
            "tags": list(tp.tags),
            "created_at": tp.created_at,
        }

    def remove_task_profile(self, task_name: str) -> bool:
        """Remove a task profile."""
        if task_name not in self._tasks:
            return False
        del self._tasks[task_name]
        self._record("task_removed", {"task_name": task_name})
        return True

    def list_task_profiles(self, tag: str = "") -> List[Dict[str, Any]]:
        """List task profiles, optionally filtered by tag."""
        results = []
        for tp in self._tasks.values():
            if tag and tag not in tp.tags:
                continue
            results.append({
                "task_id": tp.task_id,
                "task_name": tp.task_name,
                "required_skills": list(tp.required_skills),
                "min_proficiency": tp.min_proficiency,
                "tags": list(tp.tags),
                "created_at": tp.created_at,
            })
        return results

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(self, task_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return top matching agents for a task sorted by match_score desc.

        match_score = average proficiency across required skills.
        Agents missing a required skill score 0 for that skill.
        """
        tp = self._tasks.get(task_name)
        if not tp or not tp.required_skills:
            return []

        scored: List[Dict[str, Any]] = []
        for profile in self._agents.values():
            total = 0.0
            for skill in tp.required_skills:
                total += profile.skills.get(skill, 0.0)
            match_score = total / len(tp.required_skills)
            scored.append({
                "agent_id": profile.agent_id,
                "profile_id": profile.profile_id,
                "match_score": round(match_score, 2),
                "skills_matched": sum(
                    1 for s in tp.required_skills if s in profile.skills
                ),
                "skills_required": len(tp.required_skills),
            })

        scored.sort(key=lambda x: x["match_score"], reverse=True)
        self._total_matches_performed += 1
        self._record("match_performed", {
            "task_name": task_name, "candidates": len(scored),
        })
        return scored[:limit]

    def get_best_match(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Return the single best agent for a task, or None."""
        results = self.match(task_name, limit=1)
        if not results:
            return None
        return results[0]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record(self, action: str, data: Dict[str, Any]) -> None:
        event_id = self._make_id("evt-", action)
        self._history.append(_MatchEvent(
            event_id=event_id,
            action=action,
            data=data,
            timestamp=time.time(),
        ))
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._fire(action, data)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent history events."""
        limit = max(1, min(limit, len(self._history)))
        results = []
        for evt in self._history[-limit:]:
            results.append({
                "event_id": evt.event_id,
                "action": evt.action,
                "data": evt.data,
                "timestamp": evt.timestamp,
            })
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_agents": len(self._agents),
            "current_tasks": len(self._tasks),
            "total_agents_registered": self._total_agents_registered,
            "total_tasks_created": self._total_tasks_created,
            "total_matches_performed": self._total_matches_performed,
            "total_skills_added": self._total_skills_added,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._agents.clear()
        self._tasks.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_agents_registered = 0
        self._total_tasks_created = 0
        self._total_matches_performed = 0
        self._total_skills_added = 0
