"""Agent Learning Engine – tracks agent learning from experiences.

Records learning episodes (successes, failures, feedback), extracts
lessons, builds a knowledge base per agent, and tracks skill acquisition
over time.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Episode:
    episode_id: str
    agent: str
    episode_type: str  # success | failure | feedback | observation
    context: str
    lesson: str
    confidence: float  # 0.0-1.0
    tags: List[str]
    source: str
    created_at: float
    seq: int


@dataclass
class _Skill:
    skill_id: str
    agent: str
    name: str
    proficiency: float  # 0.0-100.0
    practice_count: int
    last_practiced: float
    created_at: float
    seq: int


class AgentLearningEngine:
    """Tracks agent learning from episodes and skill acquisition."""

    EPISODE_TYPES = ("success", "failure", "feedback", "observation")

    def __init__(self, max_episodes: int = 500000,
                 max_skills: int = 50000) -> None:
        self._max_episodes = max_episodes
        self._max_skills = max_skills
        self._episodes: Dict[str, _Episode] = {}
        self._skills: Dict[str, _Skill] = {}
        self._skill_index: Dict[str, Dict[str, str]] = {}  # agent -> {name: skill_id}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_episodes": 0,
            "total_skills": 0,
            "total_practice": 0,
        }

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def record_episode(self, agent: str, episode_type: str = "observation",
                       context: str = "", lesson: str = "",
                       confidence: float = 0.5, tags: Optional[List[str]] = None,
                       source: str = "") -> str:
        if not agent:
            return ""
        if episode_type not in self.EPISODE_TYPES:
            return ""
        if len(self._episodes) >= self._max_episodes:
            return ""
        confidence = max(0.0, min(1.0, confidence))
        self._seq += 1
        raw = f"ep-{agent}-{episode_type}-{self._seq}-{len(self._episodes)}"
        eid = "ep-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        ep = _Episode(
            episode_id=eid, agent=agent, episode_type=episode_type,
            context=context, lesson=lesson, confidence=confidence,
            tags=list(tags or []), source=source,
            created_at=time.time(), seq=self._seq,
        )
        self._episodes[eid] = ep
        self._stats["total_episodes"] += 1
        self._fire("episode_recorded", {"episode_id": eid, "agent": agent})
        return eid

    def get_episode(self, episode_id: str) -> Optional[Dict]:
        ep = self._episodes.get(episode_id)
        if ep is None:
            return None
        return self._ep_to_dict(ep)

    def remove_episode(self, episode_id: str) -> bool:
        if episode_id not in self._episodes:
            return False
        del self._episodes[episode_id]
        return True

    def search_episodes(self, agent: str = "", episode_type: str = "",
                        tag: str = "", source: str = "",
                        min_confidence: float = 0.0) -> List[Dict]:
        results = []
        for ep in self._episodes.values():
            if agent and ep.agent != agent:
                continue
            if episode_type and ep.episode_type != episode_type:
                continue
            if tag and tag not in ep.tags:
                continue
            if source and ep.source != source:
                continue
            if ep.confidence < min_confidence:
                continue
            results.append(self._ep_to_dict(ep))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_agent_lessons(self, agent: str,
                          min_confidence: float = 0.0) -> List[Dict]:
        results = []
        for ep in self._episodes.values():
            if ep.agent != agent:
                continue
            if not ep.lesson:
                continue
            if ep.confidence < min_confidence:
                continue
            results.append({
                "episode_id": ep.episode_id,
                "lesson": ep.lesson,
                "confidence": ep.confidence,
                "episode_type": ep.episode_type,
                "tags": list(ep.tags),
            })
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def get_agent_episode_summary(self, agent: str) -> Dict:
        counts: Dict[str, int] = {t: 0 for t in self.EPISODE_TYPES}
        total = 0
        total_conf = 0.0
        for ep in self._episodes.values():
            if ep.agent != agent:
                continue
            counts[ep.episode_type] = counts.get(ep.episode_type, 0) + 1
            total += 1
            total_conf += ep.confidence
        return {
            "agent": agent,
            "total_episodes": total,
            "by_type": counts,
            "avg_confidence": round(total_conf / total, 3) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def register_skill(self, agent: str, name: str,
                       initial_proficiency: float = 0.0) -> str:
        if not agent or not name:
            return ""
        if len(self._skills) >= self._max_skills:
            return ""
        idx = self._skill_index.get(agent, {})
        if name in idx:
            return ""  # duplicate
        self._seq += 1
        raw = f"sk-{agent}-{name}-{self._seq}-{len(self._skills)}"
        sid = "sk-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        initial_proficiency = max(0.0, min(100.0, initial_proficiency))
        sk = _Skill(
            skill_id=sid, agent=agent, name=name,
            proficiency=initial_proficiency, practice_count=0,
            last_practiced=0.0, created_at=time.time(), seq=self._seq,
        )
        self._skills[sid] = sk
        if agent not in self._skill_index:
            self._skill_index[agent] = {}
        self._skill_index[agent][name] = sid
        self._stats["total_skills"] += 1
        self._fire("skill_registered", {"skill_id": sid, "agent": agent})
        return sid

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        sk = self._skills.get(skill_id)
        if sk is None:
            return None
        return self._sk_to_dict(sk)

    def remove_skill(self, skill_id: str) -> bool:
        sk = self._skills.get(skill_id)
        if sk is None:
            return False
        idx = self._skill_index.get(sk.agent, {})
        idx.pop(sk.name, None)
        if not idx:
            self._skill_index.pop(sk.agent, None)
        del self._skills[skill_id]
        return True

    def practice_skill(self, skill_id: str, delta: float = 1.0) -> bool:
        sk = self._skills.get(skill_id)
        if sk is None:
            return False
        sk.proficiency = max(0.0, min(100.0, sk.proficiency + delta))
        sk.practice_count += 1
        sk.last_practiced = time.time()
        self._stats["total_practice"] += 1
        self._fire("skill_practiced", {"skill_id": skill_id, "proficiency": sk.proficiency})
        return True

    def get_agent_skills(self, agent: str) -> List[Dict]:
        results = []
        for sk in self._skills.values():
            if sk.agent != agent:
                continue
            results.append(self._sk_to_dict(sk))
        results.sort(key=lambda x: x["proficiency"], reverse=True)
        return results

    def search_skills(self, agent: str = "", name: str = "",
                      min_proficiency: float = 0.0) -> List[Dict]:
        results = []
        for sk in self._skills.values():
            if agent and sk.agent != agent:
                continue
            if name and sk.name != name:
                continue
            if sk.proficiency < min_proficiency:
                continue
            results.append(self._sk_to_dict(sk))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_skill_by_name(self, agent: str, name: str) -> Optional[Dict]:
        idx = self._skill_index.get(agent, {})
        sid = idx.get(name)
        if sid is None:
            return None
        return self.get_skill(sid)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
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
            "current_episodes": len(self._episodes),
            "current_skills": len(self._skills),
        }

    def reset(self) -> None:
        self._episodes.clear()
        self._skills.clear()
        self._skill_index.clear()
        self._seq = 0
        self._stats = {
            "total_episodes": 0,
            "total_skills": 0,
            "total_practice": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ep_to_dict(ep: _Episode) -> Dict:
        return {
            "episode_id": ep.episode_id,
            "agent": ep.agent,
            "episode_type": ep.episode_type,
            "context": ep.context,
            "lesson": ep.lesson,
            "confidence": ep.confidence,
            "tags": list(ep.tags),
            "source": ep.source,
            "created_at": ep.created_at,
            "seq": ep.seq,
        }

    @staticmethod
    def _sk_to_dict(sk: _Skill) -> Dict:
        return {
            "skill_id": sk.skill_id,
            "agent": sk.agent,
            "name": sk.name,
            "proficiency": sk.proficiency,
            "practice_count": sk.practice_count,
            "last_practiced": sk.last_practiced,
            "created_at": sk.created_at,
            "seq": sk.seq,
        }
