"""Agent feedback collector.

Collects, aggregates, and analyzes feedback from agents about code quality,
pipeline performance, and collaboration effectiveness.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Feedback:
    """Feedback entry."""
    feedback_id: str = ""
    agent: str = ""
    target: str = ""  # what the feedback is about
    category: str = "general"
    rating: int = 0  # 1-5
    comment: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class _Survey:
    """A survey template."""
    survey_id: str = ""
    name: str = ""
    questions: List[str] = field(default_factory=list)
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    response_count: int = 0
    created_at: float = 0.0


@dataclass
class _SurveyResponse:
    """Response to a survey."""
    response_id: str = ""
    survey_id: str = ""
    agent: str = ""
    answers: Dict[str, str] = field(default_factory=dict)
    rating: int = 0
    timestamp: float = 0.0


class AgentFeedbackCollector:
    """Collects and analyzes agent feedback."""

    CATEGORIES = ("general", "code_quality", "performance",
                  "collaboration", "tooling", "process")
    VALID_RATINGS = (1, 2, 3, 4, 5)

    def __init__(self, max_feedback: int = 100000,
                 max_surveys: int = 1000,
                 max_responses: int = 50000):
        self._max_feedback = max_feedback
        self._max_surveys = max_surveys
        self._max_responses = max_responses
        self._feedback: Dict[str, _Feedback] = {}
        self._surveys: Dict[str, _Survey] = {}
        self._responses: Dict[str, _SurveyResponse] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_feedback_submitted": 0,
            "total_surveys_created": 0,
            "total_responses_collected": 0,
        }

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def submit_feedback(self, agent: str, target: str, rating: int,
                        category: str = "general", comment: str = "",
                        tags: Optional[List[str]] = None,
                        metadata: Optional[Dict] = None) -> str:
        """Submit feedback from an agent."""
        if not agent or not target:
            return ""
        if rating not in self.VALID_RATINGS:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if len(self._feedback) >= self._max_feedback:
            self._prune_feedback()

        fid = "fb-" + hashlib.md5(
            f"{agent}{target}{time.time()}{len(self._feedback)}".encode()
        ).hexdigest()[:12]

        self._feedback[fid] = _Feedback(
            feedback_id=fid,
            agent=agent,
            target=target,
            category=category,
            rating=rating,
            comment=comment,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=time.time(),
        )
        self._stats["total_feedback_submitted"] += 1
        self._fire("feedback_submitted", {
            "feedback_id": fid, "agent": agent, "target": target,
            "rating": rating,
        })
        return fid

    def get_feedback(self, feedback_id: str) -> Optional[Dict]:
        """Get feedback entry."""
        f = self._feedback.get(feedback_id)
        if not f:
            return None
        return {
            "feedback_id": f.feedback_id,
            "agent": f.agent,
            "target": f.target,
            "category": f.category,
            "rating": f.rating,
            "comment": f.comment,
            "tags": list(f.tags),
            "timestamp": f.timestamp,
        }

    def remove_feedback(self, feedback_id: str) -> bool:
        """Remove feedback."""
        if feedback_id not in self._feedback:
            return False
        del self._feedback[feedback_id]
        return True

    # ------------------------------------------------------------------
    # Surveys
    # ------------------------------------------------------------------

    def create_survey(self, name: str, questions: Optional[List[str]] = None,
                      category: str = "general",
                      tags: Optional[List[str]] = None) -> str:
        """Create a survey."""
        if not name:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if len(self._surveys) >= self._max_surveys:
            return ""

        sid = "srv-" + hashlib.md5(
            f"{name}{time.time()}{len(self._surveys)}".encode()
        ).hexdigest()[:12]

        self._surveys[sid] = _Survey(
            survey_id=sid,
            name=name,
            questions=questions or [],
            category=category,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_surveys_created"] += 1
        return sid

    def get_survey(self, survey_id: str) -> Optional[Dict]:
        """Get survey info."""
        s = self._surveys.get(survey_id)
        if not s:
            return None
        return {
            "survey_id": s.survey_id,
            "name": s.name,
            "questions": list(s.questions),
            "category": s.category,
            "tags": list(s.tags),
            "response_count": s.response_count,
        }

    def remove_survey(self, survey_id: str) -> bool:
        """Remove survey."""
        if survey_id not in self._surveys:
            return False
        del self._surveys[survey_id]
        return True

    def respond_to_survey(self, survey_id: str, agent: str,
                          answers: Optional[Dict[str, str]] = None,
                          rating: int = 3) -> str:
        """Submit a survey response."""
        s = self._surveys.get(survey_id)
        if not s or not agent:
            return ""
        if rating not in self.VALID_RATINGS:
            return ""
        if len(self._responses) >= self._max_responses:
            return ""

        rid = "sresp-" + hashlib.md5(
            f"{survey_id}{agent}{time.time()}{len(self._responses)}".encode()
        ).hexdigest()[:12]

        self._responses[rid] = _SurveyResponse(
            response_id=rid,
            survey_id=survey_id,
            agent=agent,
            answers=answers or {},
            rating=rating,
            timestamp=time.time(),
        )
        s.response_count += 1
        self._stats["total_responses_collected"] += 1
        return rid

    def get_survey_responses(self, survey_id: str) -> List[Dict]:
        """Get all responses for a survey."""
        result = []
        for r in self._responses.values():
            if r.survey_id != survey_id:
                continue
            result.append({
                "response_id": r.response_id,
                "agent": r.agent,
                "answers": dict(r.answers),
                "rating": r.rating,
                "timestamp": r.timestamp,
            })
        result.sort(key=lambda x: x["timestamp"])
        return result

    # ------------------------------------------------------------------
    # Queries & Analytics
    # ------------------------------------------------------------------

    def search_feedback(self, agent: Optional[str] = None,
                        target: Optional[str] = None,
                        category: Optional[str] = None,
                        tag: Optional[str] = None,
                        min_rating: int = 0,
                        limit: int = 100) -> List[Dict]:
        """Search feedback with filters."""
        result = []
        for f in self._feedback.values():
            if agent and f.agent != agent:
                continue
            if target and f.target != target:
                continue
            if category and f.category != category:
                continue
            if tag and tag not in f.tags:
                continue
            if f.rating < min_rating:
                continue
            result.append({
                "feedback_id": f.feedback_id,
                "agent": f.agent,
                "target": f.target,
                "category": f.category,
                "rating": f.rating,
                "comment": f.comment,
                "timestamp": f.timestamp,
            })
        result.sort(key=lambda x: -x["timestamp"])
        return result[:limit]

    def get_average_rating(self, target: Optional[str] = None,
                           category: Optional[str] = None) -> float:
        """Get average rating across feedback."""
        ratings = []
        for f in self._feedback.values():
            if target and f.target != target:
                continue
            if category and f.category != category:
                continue
            ratings.append(f.rating)

        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 2)

    def get_rating_distribution(self, target: Optional[str] = None) -> Dict[int, int]:
        """Get count of each rating value."""
        dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for f in self._feedback.values():
            if target and f.target != target:
                continue
            dist[f.rating] += 1
        return dist

    def get_top_targets(self, limit: int = 10,
                        min_feedback: int = 1) -> List[Dict]:
        """Get targets with highest average rating."""
        target_data: Dict[str, List[int]] = {}
        for f in self._feedback.values():
            if f.target not in target_data:
                target_data[f.target] = []
            target_data[f.target].append(f.rating)

        result = []
        for target, ratings in target_data.items():
            if len(ratings) < min_feedback:
                continue
            avg = sum(ratings) / len(ratings)
            result.append({
                "target": target,
                "avg_rating": round(avg, 2),
                "feedback_count": len(ratings),
            })
        result.sort(key=lambda x: -x["avg_rating"])
        return result[:limit]

    def get_worst_targets(self, limit: int = 10,
                          min_feedback: int = 1) -> List[Dict]:
        """Get targets with lowest average rating."""
        target_data: Dict[str, List[int]] = {}
        for f in self._feedback.values():
            if f.target not in target_data:
                target_data[f.target] = []
            target_data[f.target].append(f.rating)

        result = []
        for target, ratings in target_data.items():
            if len(ratings) < min_feedback:
                continue
            avg = sum(ratings) / len(ratings)
            result.append({
                "target": target,
                "avg_rating": round(avg, 2),
                "feedback_count": len(ratings),
            })
        result.sort(key=lambda x: x["avg_rating"])
        return result[:limit]

    def get_agent_feedback_summary(self, agent: str) -> Dict:
        """Get summary of feedback given by an agent."""
        given = [f for f in self._feedback.values() if f.agent == agent]
        received = [f for f in self._feedback.values() if f.target == agent]

        given_avg = (sum(f.rating for f in given) / len(given)
                     if given else 0.0)
        received_avg = (sum(f.rating for f in received) / len(received)
                        if received else 0.0)

        return {
            "agent": agent,
            "feedback_given": len(given),
            "avg_rating_given": round(given_avg, 2),
            "feedback_received": len(received),
            "avg_rating_received": round(received_avg, 2),
        }

    def list_surveys(self, category: Optional[str] = None,
                     tag: Optional[str] = None) -> List[Dict]:
        """List surveys."""
        result = []
        for s in self._surveys.values():
            if category and s.category != category:
                continue
            if tag and tag not in s.tags:
                continue
            result.append({
                "survey_id": s.survey_id,
                "name": s.name,
                "category": s.category,
                "response_count": s.response_count,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_feedback(self) -> None:
        """Remove oldest feedback."""
        items = sorted(self._feedback.items(), key=lambda x: x[1].timestamp)
        to_remove = len(items) // 4
        for k, _ in items[:to_remove]:
            del self._feedback[k]

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
            "current_feedback": len(self._feedback),
            "current_surveys": len(self._surveys),
            "current_responses": len(self._responses),
        }

    def reset(self) -> None:
        self._feedback.clear()
        self._surveys.clear()
        self._responses.clear()
        self._stats = {k: 0 for k in self._stats}
