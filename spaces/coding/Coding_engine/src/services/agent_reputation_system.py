"""Agent reputation system.

Tracks agent performance and reliability through a reputation scoring system.
Agents earn or lose reputation based on task outcomes, quality of work,
and collaboration effectiveness.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _AgentProfile:
    """An agent's reputation profile."""
    profile_id: str = ""
    agent_name: str = ""
    reputation_score: float = 50.0  # 0-100 scale
    level: str = "novice"  # novice, junior, senior, expert, master
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_reviews: int = 0
    positive_reviews: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    seq: int = 0


@dataclass
class _ReputationEvent:
    """A reputation change event."""
    event_id: str = ""
    profile_id: str = ""
    event_type: str = ""  # task_success, task_failure, review, bonus, penalty
    delta: float = 0.0
    reason: str = ""
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class AgentReputationSystem:
    """Manages agent reputation scores."""

    LEVELS = ("novice", "junior", "senior", "expert", "master")
    LEVEL_THRESHOLDS = {"novice": 0, "junior": 25, "senior": 50,
                        "expert": 75, "master": 90}
    EVENT_TYPES = ("task_success", "task_failure", "review_positive",
                   "review_negative", "bonus", "penalty")

    def __init__(self, max_profiles: int = 10000,
                 max_events: int = 500000):
        self._max_profiles = max_profiles
        self._max_events = max_events
        self._profiles: Dict[str, _AgentProfile] = {}
        self._events: Dict[str, _ReputationEvent] = {}
        self._name_index: Dict[str, str] = {}  # agent_name -> profile_id
        self._profile_seq = 0
        self._event_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_profiles_created": 0,
            "total_events": 0,
            "total_promotions": 0,
            "total_demotions": 0,
        }

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def create_profile(self, agent_name: str,
                       initial_score: float = 50.0,
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> str:
        """Create an agent reputation profile."""
        if not agent_name:
            return ""
        if agent_name in self._name_index:
            return ""  # duplicate name
        if len(self._profiles) >= self._max_profiles:
            return ""

        self._profile_seq += 1
        pid = "rep-" + hashlib.md5(
            f"{agent_name}{time.time()}{self._profile_seq}{len(self._profiles)}".encode()
        ).hexdigest()[:12]

        score = max(0.0, min(100.0, initial_score))
        level = self._score_to_level(score)

        self._profiles[pid] = _AgentProfile(
            profile_id=pid,
            agent_name=agent_name,
            reputation_score=score,
            level=level,
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
            updated_at=time.time(),
            seq=self._profile_seq,
        )
        self._name_index[agent_name] = pid
        self._stats["total_profiles_created"] += 1
        self._fire("profile_created", {"profile_id": pid, "agent_name": agent_name})
        return pid

    def get_profile(self, profile_id: str) -> Optional[Dict]:
        """Get profile info."""
        p = self._profiles.get(profile_id)
        if not p:
            return None
        return {
            "profile_id": p.profile_id,
            "agent_name": p.agent_name,
            "reputation_score": p.reputation_score,
            "level": p.level,
            "total_tasks": p.total_tasks,
            "successful_tasks": p.successful_tasks,
            "failed_tasks": p.failed_tasks,
            "total_reviews": p.total_reviews,
            "positive_reviews": p.positive_reviews,
            "tags": list(p.tags),
            "seq": p.seq,
        }

    def get_profile_by_name(self, agent_name: str) -> Optional[Dict]:
        """Get profile by agent name."""
        pid = self._name_index.get(agent_name)
        if not pid:
            return None
        return self.get_profile(pid)

    def remove_profile(self, profile_id: str) -> bool:
        """Remove a profile and its events."""
        p = self._profiles.get(profile_id)
        if not p:
            return False
        del self._name_index[p.agent_name]
        del self._profiles[profile_id]
        # Cascade remove events
        to_remove = [eid for eid, e in self._events.items()
                     if e.profile_id == profile_id]
        for eid in to_remove:
            del self._events[eid]
        return True

    # ------------------------------------------------------------------
    # Reputation Events
    # ------------------------------------------------------------------

    def record_task_success(self, profile_id: str, delta: float = 2.0,
                            reason: str = "") -> str:
        """Record a successful task completion."""
        return self._record_event(profile_id, "task_success", delta,
                                  reason or "Task completed successfully",
                                  is_task=True, is_success=True)

    def record_task_failure(self, profile_id: str, delta: float = -3.0,
                            reason: str = "") -> str:
        """Record a task failure."""
        return self._record_event(profile_id, "task_failure", delta,
                                  reason or "Task failed",
                                  is_task=True, is_success=False)

    def record_review(self, profile_id: str, positive: bool = True,
                      delta: float = 0.0, reason: str = "") -> str:
        """Record a peer review."""
        if delta == 0.0:
            delta = 1.0 if positive else -1.5
        event_type = "review_positive" if positive else "review_negative"
        eid = self._record_event(profile_id, event_type, delta,
                                 reason or ("Positive review" if positive else "Negative review"),
                                 is_review=True, is_positive=positive)
        return eid

    def record_bonus(self, profile_id: str, delta: float = 5.0,
                     reason: str = "") -> str:
        """Award a reputation bonus."""
        return self._record_event(profile_id, "bonus", abs(delta),
                                  reason or "Bonus awarded")

    def record_penalty(self, profile_id: str, delta: float = -5.0,
                       reason: str = "") -> str:
        """Apply a reputation penalty."""
        return self._record_event(profile_id, "penalty", -abs(delta),
                                  reason or "Penalty applied")

    def _record_event(self, profile_id: str, event_type: str,
                      delta: float, reason: str,
                      is_task: bool = False, is_success: bool = False,
                      is_review: bool = False, is_positive: bool = False) -> str:
        """Internal: record a reputation event."""
        p = self._profiles.get(profile_id)
        if not p:
            return ""
        if len(self._events) >= self._max_events:
            return ""

        self._event_seq += 1
        eid = "revt-" + hashlib.md5(
            f"{profile_id}{event_type}{time.time()}{self._event_seq}{len(self._events)}".encode()
        ).hexdigest()[:12]

        self._events[eid] = _ReputationEvent(
            event_id=eid,
            profile_id=profile_id,
            event_type=event_type,
            delta=delta,
            reason=reason,
            created_at=time.time(),
            seq=self._event_seq,
        )

        # Update profile
        old_level = p.level
        p.reputation_score = max(0.0, min(100.0, p.reputation_score + delta))
        p.level = self._score_to_level(p.reputation_score)
        p.updated_at = time.time()

        if is_task:
            p.total_tasks += 1
            if is_success:
                p.successful_tasks += 1
            else:
                p.failed_tasks += 1

        if is_review:
            p.total_reviews += 1
            if is_positive:
                p.positive_reviews += 1

        # Track level changes
        if p.level != old_level:
            if self.LEVELS.index(p.level) > self.LEVELS.index(old_level):
                self._stats["total_promotions"] += 1
                self._fire("agent_promoted", {
                    "profile_id": profile_id, "old_level": old_level,
                    "new_level": p.level,
                })
            else:
                self._stats["total_demotions"] += 1

        self._stats["total_events"] += 1
        return eid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_profiles(self, level: Optional[str] = None,
                        tag: Optional[str] = None,
                        min_score: Optional[float] = None,
                        limit: int = 100) -> List[Dict]:
        """Search profiles."""
        result = []
        for p in self._profiles.values():
            if level and p.level != level:
                continue
            if tag and tag not in p.tags:
                continue
            if min_score is not None and p.reputation_score < min_score:
                continue
            result.append({
                "profile_id": p.profile_id,
                "agent_name": p.agent_name,
                "reputation_score": p.reputation_score,
                "level": p.level,
                "total_tasks": p.total_tasks,
                "successful_tasks": p.successful_tasks,
                "seq": p.seq,
            })
        result.sort(key=lambda x: -x["reputation_score"])
        return result[:limit]

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get top agents by reputation."""
        return self.search_profiles(limit=limit)

    def get_profile_events(self, profile_id: str,
                           event_type: Optional[str] = None,
                           limit: int = 100) -> List[Dict]:
        """Get events for a profile."""
        result = []
        for e in self._events.values():
            if e.profile_id != profile_id:
                continue
            if event_type and e.event_type != event_type:
                continue
            result.append({
                "event_id": e.event_id,
                "profile_id": e.profile_id,
                "event_type": e.event_type,
                "delta": e.delta,
                "reason": e.reason,
                "seq": e.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_success_rate(self, profile_id: str) -> Dict:
        """Get task success rate for a profile."""
        p = self._profiles.get(profile_id)
        if not p or p.total_tasks == 0:
            return {"total_tasks": 0, "success_rate": 0.0}
        rate = round((p.successful_tasks / p.total_tasks) * 100.0, 1)
        return {
            "total_tasks": p.total_tasks,
            "successful_tasks": p.successful_tasks,
            "failed_tasks": p.failed_tasks,
            "success_rate": rate,
        }

    def get_level_distribution(self) -> Dict[str, int]:
        """Get count of agents at each level."""
        dist = {level: 0 for level in self.LEVELS}
        for p in self._profiles.values():
            dist[p.level] = dist.get(p.level, 0) + 1
        return dist

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score_to_level(self, score: float) -> str:
        """Convert a score to a level."""
        if score >= 90:
            return "master"
        elif score >= 75:
            return "expert"
        elif score >= 50:
            return "senior"
        elif score >= 25:
            return "junior"
        return "novice"

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
            "current_profiles": len(self._profiles),
            "current_events": len(self._events),
            "avg_reputation": (
                round(sum(p.reputation_score for p in self._profiles.values()) /
                      len(self._profiles), 1)
                if self._profiles else 0.0
            ),
        }

    def reset(self) -> None:
        self._profiles.clear()
        self._events.clear()
        self._name_index.clear()
        self._profile_seq = 0
        self._event_seq = 0
        self._stats = {k: 0 for k in self._stats}
