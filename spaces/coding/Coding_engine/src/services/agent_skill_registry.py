"""Agent skill registry.

Agent skill registration and lookup - manages skills that agents can perform.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillEntry:
    """A single skill registration for an agent."""
    skill_id: str
    agent_id: str
    skill_name: str
    proficiency: float
    created_at: float


class AgentSkillRegistry:
    """Manages skills that agents can perform, with proficiency tracking."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillEntry] = {}
        self._callbacks: Dict[str, Any] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # ID Generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"asr-{self._seq}-{id(self)}"
        return "asr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries if over capacity."""
        if len(self._skills) > self._max_entries:
            sorted_entries = sorted(
                self._skills.items(), key=lambda kv: kv[1].created_at
            )
            to_remove = len(self._skills) - self._max_entries
            for i in range(to_remove):
                del self._skills[sorted_entries[i][0]]

    # ------------------------------------------------------------------
    # Skill Management
    # ------------------------------------------------------------------

    def register_skill(self, agent_id: str, skill_name: str,
                       proficiency: float = 1.0) -> str:
        """Register a skill for an agent and return the skill_id."""
        skill_id = self._generate_id()
        now = time.time()
        self._skills[skill_id] = SkillEntry(
            skill_id=skill_id,
            agent_id=agent_id,
            skill_name=skill_name,
            proficiency=proficiency,
            created_at=now,
        )
        self._prune_if_needed()
        self._fire("register_skill", {
            "skill_id": skill_id,
            "agent_id": agent_id,
            "skill_name": skill_name,
            "proficiency": proficiency,
        })
        return skill_id

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        """Get skill info by id, or None if not found."""
        entry = self._skills.get(skill_id)
        if entry is None:
            return None
        return {
            "skill_id": entry.skill_id,
            "agent_id": entry.agent_id,
            "skill_name": entry.skill_name,
            "proficiency": entry.proficiency,
            "created_at": entry.created_at,
        }

    def get_agent_skills(self, agent_id: str) -> List[Dict]:
        """Get all skills for a given agent."""
        result = []
        for entry in self._skills.values():
            if entry.agent_id == agent_id:
                result.append({
                    "skill_id": entry.skill_id,
                    "agent_id": entry.agent_id,
                    "skill_name": entry.skill_name,
                    "proficiency": entry.proficiency,
                    "created_at": entry.created_at,
                })
        return result

    def find_agents_by_skill(self, skill_name: str) -> List[str]:
        """Find agent_ids that have a given skill, sorted by proficiency descending."""
        matches: List[SkillEntry] = []
        for entry in self._skills.values():
            if entry.skill_name == skill_name:
                matches.append(entry)
        matches.sort(key=lambda e: e.proficiency, reverse=True)
        return [e.agent_id for e in matches]

    def update_proficiency(self, skill_id: str, proficiency: float) -> bool:
        """Update the proficiency for a skill entry."""
        entry = self._skills.get(skill_id)
        if entry is None:
            return False
        entry.proficiency = proficiency
        self._fire("update_proficiency", {
            "skill_id": skill_id,
            "proficiency": proficiency,
        })
        return True

    def remove_skill(self, skill_id: str) -> bool:
        """Remove a skill entry by id."""
        if skill_id not in self._skills:
            return False
        del self._skills[skill_id]
        self._fire("remove_skill", {"skill_id": skill_id})
        return True

    def list_skills(self) -> List[str]:
        """Return a list of unique skill names."""
        names = set()
        for entry in self._skills.values():
            names.add(entry.skill_name)
        return sorted(names)

    def list_agents(self) -> List[str]:
        """Return a list of unique agent_ids."""
        agents = set()
        for entry in self._skills.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def get_skill_count(self) -> int:
        """Return total number of skill entries."""
        return len(self._skills)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> None:
        """Register a callback to be fired on changes."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Any) -> None:
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
        """Return registry statistics."""
        return {
            "total_skills": len(self._skills),
            "unique_skill_names": len(self.list_skills()),
            "unique_agents": len(self.list_agents()),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._skills.clear()
        self._callbacks.clear()
        self._seq = 0
