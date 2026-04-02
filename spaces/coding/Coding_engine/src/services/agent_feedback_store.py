"""Agent feedback store.

Collects and manages feedback on agent performance including ratings,
comments, and improvement suggestions. Provides aggregation and
analytics for agent performance tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FeedbackEntry:
    """Single feedback record."""
    feedback_id: str = ""
    agent_id: str = ""
    source: str = ""
    rating: int = 0
    comment: str = ""
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0


class AgentFeedbackStore:
    """Collects and manages feedback on agent performance."""

    VALID_RATINGS = (1, 2, 3, 4, 5)

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, FeedbackEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_submitted": 0,
            "total_pruned": 0,
            "total_purged": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'afs-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"afs-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._entries) < self._max_entries:
            return
        sorted_entries = sorted(
            self._entries.values(), key=lambda e: e.created_at
        )
        remove_count = len(self._entries) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._entries[entry.feedback_id]
            self._stats["total_pruned"] += 1
            logger.debug("feedback_pruned", feedback_id=entry.feedback_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def submit_feedback(
        self,
        agent_id: str,
        source: str,
        rating: int,
        comment: str = "",
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Submit feedback for an agent.

        Args:
            agent_id: The agent being rated.
            source: Who or what is providing the feedback.
            rating: Rating value (1-5).
            comment: Optional text comment.
            category: Feedback category (default 'general').
            tags: Optional list of tags.

        Returns:
            The feedback_id, or '' on validation failure.
        """
        if not agent_id or not source:
            logger.warning("submit_rejected_empty", agent_id=agent_id, source=source)
            return ""
        if rating not in self.VALID_RATINGS:
            logger.warning("submit_rejected_rating", rating=rating)
            return ""

        self._prune_if_needed()

        fid = self._next_id(f"{agent_id}:{source}:{rating}")
        now = time.time()

        self._entries[fid] = FeedbackEntry(
            feedback_id=fid,
            agent_id=agent_id,
            source=source,
            rating=rating,
            comment=comment,
            category=category,
            tags=list(tags) if tags else [],
            created_at=now,
        )
        self._stats["total_submitted"] += 1

        logger.info(
            "feedback_submitted",
            feedback_id=fid,
            agent_id=agent_id,
            source=source,
            rating=rating,
            category=category,
        )
        self._fire("feedback_submitted", {
            "feedback_id": fid,
            "agent_id": agent_id,
            "source": source,
            "rating": rating,
            "category": category,
        })
        return fid

    def get_feedback(self, feedback_id: str) -> Optional[Dict]:
        """Get a single feedback entry by ID."""
        entry = self._entries.get(feedback_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    def get_agent_feedback(
        self, agent_id: str, category: Optional[str] = None
    ) -> List[Dict]:
        """Get all feedback for a specific agent.

        Args:
            agent_id: Agent to look up.
            category: Optional category filter.

        Returns:
            List of feedback dicts, sorted newest first.
        """
        result = []
        for entry in self._entries.values():
            if entry.agent_id != agent_id:
                continue
            if category is not None and entry.category != category:
                continue
            result.append(self._entry_to_dict(entry))
        result.sort(key=lambda x: -x["created_at"])
        return result

    def get_average_rating(
        self, agent_id: str, category: Optional[str] = None
    ) -> float:
        """Get average rating for an agent.

        Args:
            agent_id: Agent to compute average for.
            category: Optional category filter.

        Returns:
            Average rating rounded to 2 decimals, or 0.0 if no feedback.
        """
        ratings = []
        for entry in self._entries.values():
            if entry.agent_id != agent_id:
                continue
            if category is not None and entry.category != category:
                continue
            ratings.append(entry.rating)

        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 2)

    def get_top_rated_agents(self, limit: int = 10) -> List[Dict]:
        """Get agents with highest average rating.

        Args:
            limit: Maximum number of agents to return.

        Returns:
            List of dicts with agent_id, avg_rating, count.
        """
        agent_ratings: Dict[str, List[int]] = {}
        for entry in self._entries.values():
            if entry.agent_id not in agent_ratings:
                agent_ratings[entry.agent_id] = []
            agent_ratings[entry.agent_id].append(entry.rating)

        result = []
        for aid, ratings in agent_ratings.items():
            avg = sum(ratings) / len(ratings)
            result.append({
                "agent_id": aid,
                "avg_rating": round(avg, 2),
                "count": len(ratings),
            })
        result.sort(key=lambda x: (-x["avg_rating"], -x["count"]))
        return result[:limit]

    def get_feedback_summary(self, agent_id: str) -> Dict:
        """Get a summary of all feedback for an agent.

        Returns dict with total count, average rating, breakdown by
        category, and the 10 most recent entries.
        """
        entries = [
            e for e in self._entries.values() if e.agent_id == agent_id
        ]

        if not entries:
            return {
                "total": 0,
                "avg_rating": 0.0,
                "by_category": {},
                "recent": [],
            }

        all_ratings = [e.rating for e in entries]
        avg = round(sum(all_ratings) / len(all_ratings), 2)

        by_category: Dict[str, Dict] = {}
        for entry in entries:
            cat = entry.category
            if cat not in by_category:
                by_category[cat] = {"count": 0, "total_rating": 0}
            by_category[cat]["count"] += 1
            by_category[cat]["total_rating"] += entry.rating

        category_summary: Dict[str, Dict] = {}
        for cat, data in by_category.items():
            category_summary[cat] = {
                "count": data["count"],
                "avg_rating": round(
                    data["total_rating"] / data["count"], 2
                ),
            }

        recent_entries = sorted(entries, key=lambda e: -e.created_at)[:10]
        recent = [self._entry_to_dict(e) for e in recent_entries]

        return {
            "total": len(entries),
            "avg_rating": avg,
            "by_category": category_summary,
            "recent": recent,
        }

    def list_agents_with_feedback(self) -> List[str]:
        """List all agent IDs that have received feedback."""
        agents = set()
        for entry in self._entries.values():
            agents.add(entry.agent_id)
        return sorted(agents)

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove feedback entries, optionally before a timestamp.

        Args:
            before_timestamp: If provided, only remove entries created
                before this time. If None, remove all entries.

        Returns:
            Number of entries removed.
        """
        if before_timestamp is None:
            count = len(self._entries)
            self._entries.clear()
            self._stats["total_purged"] += count
            logger.info("feedback_purged_all", count=count)
            self._fire("purged", {"count": count, "before": None})
            return count

        to_remove = [
            fid for fid, entry in self._entries.items()
            if entry.created_at < before_timestamp
        ]
        for fid in to_remove:
            del self._entries[fid]

        self._stats["total_purged"] += len(to_remove)
        logger.info(
            "feedback_purged",
            count=len(to_remove),
            before=before_timestamp,
        )
        self._fire("purged", {
            "count": len(to_remove),
            "before": before_timestamp,
        })
        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Args:
            name: Unique callback name.
            callback: Callable(action, data).

        Returns:
            True if registered, False if name already exists.
        """
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.

        Args:
            name: Callback name to remove.

        Returns:
            True if removed, False if not found.
        """
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        unique_agents = len(self.list_agents_with_feedback())
        unique_categories = set()
        for entry in self._entries.values():
            unique_categories.add(entry.category)
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "unique_agents": unique_agents,
            "unique_categories": len(unique_categories),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: FeedbackEntry) -> Dict:
        """Convert a FeedbackEntry to a plain dict."""
        return {
            "feedback_id": entry.feedback_id,
            "agent_id": entry.agent_id,
            "source": entry.source,
            "rating": entry.rating,
            "comment": entry.comment,
            "category": entry.category,
            "tags": list(entry.tags),
            "created_at": entry.created_at,
        }
