"""Agent Task Scorer -- scores task completion quality.

Tracks score records per task/agent with criteria, supporting querying,
filtering, updating, and aggregate statistics.

Usage::

    scorer = AgentTaskScorer()

    # Create a score
    score_id = scorer.score("task-1", "agent-1", score=0.85, criteria="accuracy")

    # Query
    entry = scorer.get_score(score_id)
    scores = scorer.get_scores(agent_id="agent-1")
    stats = scorer.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskScorerState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskScorer:
    """Scores task completion quality."""

    PREFIX = "atsc-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskScorerState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Score operations
    # ------------------------------------------------------------------

    def score(
        self,
        task_id: str,
        agent_id: str,
        score: float = 0.0,
        criteria: str = "overall",
        notes: str = "",
        metadata: dict = None,
    ) -> str:
        """Create a score record for a task.

        Score must be in range 0.0-1.0.
        Returns the score ID on success or ``""`` on failure.
        """
        if not task_id or not agent_id:
            return ""

        score = max(0.0, min(1.0, score))

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        score_id = self._generate_id()
        self._state.entries[score_id] = {
            "score_id": score_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "score": score,
            "criteria": criteria,
            "notes": notes,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._fire("score_created", self._state.entries[score_id])
        logger.debug(
            "Score created: %s (task=%s, agent=%s, score=%.2f)",
            score_id,
            task_id,
            agent_id,
            score,
        )
        return score_id

    def get_score(self, score_id: str) -> Optional[dict]:
        """Return the score entry or None."""
        entry = self._state.entries.get(score_id)
        return dict(entry) if entry else None

    def get_scores(
        self,
        agent_id: str = "",
        task_id: str = "",
        criteria: str = "",
        limit: int = 50,
    ) -> List[dict]:
        """Query scores, newest first.

        Optionally filter by agent_id, task_id, and/or criteria.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if agent_id and entry["agent_id"] != agent_id:
                continue
            if task_id and entry["task_id"] != task_id:
                continue
            if criteria and entry["criteria"] != criteria:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def update_score(
        self,
        score_id: str,
        score: float = None,
        notes: str = "",
    ) -> bool:
        """Update an existing score record.

        Returns True if the score was found and updated, False otherwise.
        """
        entry = self._state.entries.get(score_id)
        if entry is None:
            return False

        if score is not None:
            entry["score"] = max(0.0, min(1.0, score))
        if notes:
            entry["notes"] = notes
        entry["updated_at"] = time.time()

        self._fire("score_updated", entry)
        logger.debug("Score updated: %s", score_id)
        return True

    def get_score_count(self, agent_id: str = "", criteria: str = "") -> int:
        """Return the number of scores, optionally filtered."""
        if not agent_id and not criteria:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if agent_id and e["agent_id"] != agent_id:
                continue
            if criteria and e["criteria"] != criteria:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        by_criteria: Dict[str, int] = {}
        total_score = 0.0
        agents = set()
        for entry in self._state.entries.values():
            c = entry["criteria"]
            by_criteria[c] = by_criteria.get(c, 0) + 1
            total_score += entry["score"]
            agents.add(entry["agent_id"])
        total = len(self._state.entries)
        return {
            "total_scores": total,
            "avg_score": total_score / total if total > 0 else 0.0,
            "unique_agents": len(agents),
            "by_criteria": by_criteria,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskScorerState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskScorer reset")
