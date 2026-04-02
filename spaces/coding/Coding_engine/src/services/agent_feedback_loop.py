"""Agent Feedback Loop – collects and applies agent performance feedback.

Manages feedback entries from agent outputs, calculates quality scores,
and enables iterative improvement by tracking feedback trends over time.
Supports feedback categories, scoring, and aggregation.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _FeedbackEntry:
    feedback_id: str
    agent: str
    category: str  # quality, speed, accuracy, relevance, custom
    score: float  # 0.0 to 1.0
    comment: str
    source: str  # who gave feedback
    task_ref: str  # reference to task/workflow
    created_at: float


class AgentFeedbackLoop:
    """Collects and aggregates agent performance feedback."""

    CATEGORIES = ("quality", "speed", "accuracy", "relevance", "custom")

    def __init__(self, max_entries: int = 500000):
        self._entries: List[_FeedbackEntry] = []
        self._entry_index: Dict[str, _FeedbackEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats
        self._total_entries = 0

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def submit_feedback(
        self,
        agent: str,
        score: float,
        category: str = "custom",
        comment: str = "",
        source: str = "",
        task_ref: str = "",
    ) -> str:
        if not agent:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if score < 0.0 or score > 1.0:
            return ""
        if len(self._entries) >= self._max_entries:
            # evict oldest 10%
            trim = max(1, self._max_entries // 10)
            for e in self._entries[:trim]:
                self._entry_index.pop(e.feedback_id, None)
            self._entries = self._entries[trim:]

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{category}-{now}-{self._seq}"
        fid = "fbk-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _FeedbackEntry(
            feedback_id=fid,
            agent=agent,
            category=category,
            score=score,
            comment=comment,
            source=source,
            task_ref=task_ref,
            created_at=now,
        )
        self._entries.append(entry)
        self._entry_index[fid] = entry
        self._total_entries += 1
        self._fire("feedback_submitted", {"feedback_id": fid, "agent": agent, "score": score})
        return fid

    def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        e = self._entry_index.get(feedback_id)
        if not e:
            return None
        return {
            "feedback_id": e.feedback_id,
            "agent": e.agent,
            "category": e.category,
            "score": e.score,
            "comment": e.comment,
            "source": e.source,
            "task_ref": e.task_ref,
            "created_at": e.created_at,
        }

    def remove_feedback(self, feedback_id: str) -> bool:
        e = self._entry_index.pop(feedback_id, None)
        if not e:
            return False
        self._entries = [x for x in self._entries if x.feedback_id != feedback_id]
        return True

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_agent_score(
        self,
        agent: str,
        category: str = "",
        limit: int = 0,
    ) -> Dict[str, Any]:
        """Get aggregated score for an agent."""
        scores = []
        for e in reversed(self._entries):
            if e.agent != agent:
                continue
            if category and e.category != category:
                continue
            scores.append(e.score)
            if limit > 0 and len(scores) >= limit:
                break

        if not scores:
            return {"agent": agent, "count": 0, "avg_score": 0.0,
                    "min_score": 0.0, "max_score": 0.0}
        return {
            "agent": agent,
            "count": len(scores),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
        }

    def get_agent_trend(self, agent: str, window: int = 10) -> Dict[str, Any]:
        """Get trend: compare recent vs older scores."""
        scores = [e.score for e in self._entries if e.agent == agent]
        if len(scores) < window * 2:
            return {"agent": agent, "trend": "insufficient_data",
                    "recent_avg": 0.0, "older_avg": 0.0}
        recent = scores[-window:]
        older = scores[-window*2:-window]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if recent_avg > older_avg + 0.05:
            trend = "improving"
        elif recent_avg < older_avg - 0.05:
            trend = "declining"
        else:
            trend = "stable"
        return {"agent": agent, "trend": trend,
                "recent_avg": recent_avg, "older_avg": older_avg}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search_feedback(
        self,
        agent: str = "",
        category: str = "",
        source: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for e in reversed(self._entries):
            if agent and e.agent != agent:
                continue
            if category and e.category != category:
                continue
            if source and e.source != source:
                continue
            results.append(self.get_feedback(e.feedback_id))
            if len(results) >= limit:
                break
        return results

    def get_category_breakdown(self, agent: str) -> Dict[str, float]:
        """Get average score per category for an agent."""
        cat_scores: Dict[str, List[float]] = {}
        for e in self._entries:
            if e.agent != agent:
                continue
            if e.category not in cat_scores:
                cat_scores[e.category] = []
            cat_scores[e.category].append(e.score)
        return {cat: sum(scores) / len(scores)
                for cat, scores in cat_scores.items()}

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
            "current_entries": len(self._entries),
            "total_entries": self._total_entries,
            "unique_agents": len(set(e.agent for e in self._entries)),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._entry_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_entries = 0
