"""Agent Tag Store -- tagging for agents with add/remove/search by tags.

Provides tag management for agents including assignment, removal, bulk
tagging, tag-based agent lookup, and tag enumeration with max-entries
pruning, callbacks, and structured logging.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TagAssignment:
    assignment_id: str
    agent_id: str
    tag: str
    metadata: Optional[Dict[str, Any]]
    created_at: float
    seq: int = 0


class AgentTagStore:
    """Manages tagging for agents (add/remove/search by tags)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, TagAssignment] = {}
        self._lookup: Dict[str, str] = {}  # "agent_id:tag" -> assignment_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_adds = 0
        self._total_removes = 0
        self._total_lookups = 0
        self._total_evictions = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"ats-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ats-{digest}"

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

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_lookup_key(agent_id: str, tag: str) -> str:
        return f"{agent_id}:{tag}"

    def _prune_if_needed(self) -> None:
        """Prune oldest entries when max_entries is exceeded."""
        if len(self._entries) < self._max_entries:
            return

        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.tag)
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug("tag_assignment_evicted", assignment_id=eid, agent_id=entry.agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add_tag(
        self,
        agent_id: str,
        tag: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Assign a tag to an agent. Returns assignment_id, or '' if duplicate."""
        if not agent_id or not tag:
            logger.warning("tag_add_invalid_args", agent_id=agent_id, tag=tag)
            return ""

        lk = self._make_lookup_key(agent_id, tag)

        # Duplicate check
        existing_eid = self._lookup.get(lk)
        if existing_eid and existing_eid in self._entries:
            logger.debug("tag_duplicate", agent_id=agent_id, tag=tag)
            return ""

        self._prune_if_needed()
        assignment_id = self._gen_id(f"{agent_id}-{tag}")
        now = time.time()
        entry = TagAssignment(
            assignment_id=assignment_id,
            agent_id=agent_id,
            tag=tag,
            metadata=metadata,
            created_at=now,
            seq=self._seq,
        )
        self._entries[assignment_id] = entry
        self._lookup[lk] = assignment_id
        self._total_adds += 1
        logger.debug(
            "tag_added", agent_id=agent_id, tag=tag,
            assignment_id=assignment_id,
        )
        self._fire("tag_added", {
            "assignment_id": assignment_id,
            "agent_id": agent_id,
            "tag": tag,
            "metadata": metadata,
        })
        return assignment_id

    def remove_tag(self, agent_id: str, tag: str) -> bool:
        """Remove a tag from an agent. Returns True if it existed."""
        if not agent_id or not tag:
            return False

        lk = self._make_lookup_key(agent_id, tag)
        eid = self._lookup.get(lk)
        if not eid or eid not in self._entries:
            return False

        entry = self._entries[eid]
        del self._entries[eid]
        del self._lookup[lk]
        self._total_removes += 1
        logger.debug("tag_removed", agent_id=agent_id, tag=tag)
        self._fire("tag_removed", {
            "assignment_id": eid,
            "agent_id": agent_id,
            "tag": tag,
            "metadata": entry.metadata,
        })
        return True

    def get_agent_tags(self, agent_id: str) -> List[str]:
        """Return all tags assigned to an agent."""
        self._total_lookups += 1
        if not agent_id:
            return []

        tags: List[str] = []
        for entry in self._entries.values():
            if entry.agent_id == agent_id:
                tags.append(entry.tag)
        return sorted(tags)

    def find_agents_by_tag(self, tag: str) -> List[str]:
        """Return all agent_ids that have the given tag."""
        self._total_lookups += 1
        if not tag:
            return []

        agent_ids: List[str] = []
        for entry in self._entries.values():
            if entry.tag == tag:
                agent_ids.append(entry.agent_id)
        return sorted(set(agent_ids))

    def has_tag(self, agent_id: str, tag: str) -> bool:
        """Check whether an agent has a specific tag."""
        if not agent_id or not tag:
            return False

        lk = self._make_lookup_key(agent_id, tag)
        eid = self._lookup.get(lk)
        return bool(eid and eid in self._entries)

    def list_all_tags(self) -> List[str]:
        """Return a sorted list of all unique tags across all agents."""
        self._total_lookups += 1
        tags = {entry.tag for entry in self._entries.values()}
        return sorted(tags)

    def get_tag_count(self, tag: str) -> int:
        """Return the number of agents that have the given tag."""
        if not tag:
            return 0

        count = 0
        for entry in self._entries.values():
            if entry.tag == tag:
                count += 1
        return count

    def bulk_tag(self, agent_ids: List[str], tag: str) -> int:
        """Assign a tag to multiple agents. Returns count of new assignments."""
        if not tag or not agent_ids:
            return 0

        count = 0
        for agent_id in agent_ids:
            result = self.add_tag(agent_id, tag)
            if result:
                count += 1
        if count:
            logger.debug(
                "bulk_tag_applied", tag=tag, count=count,
                total_agents=len(agent_ids),
            )
            self._fire("bulk_tag_applied", {
                "tag": tag,
                "count": count,
                "agent_ids": agent_ids,
            })
        return count

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        unique_agents = len({e.agent_id for e in self._entries.values()})
        unique_tags = len({e.tag for e in self._entries.values()})
        return {
            "current_entries": len(self._entries),
            "unique_agents": unique_agents,
            "unique_tags": unique_tags,
            "total_adds": self._total_adds,
            "total_removes": self._total_removes,
            "total_lookups": self._total_lookups,
            "total_evictions": self._total_evictions,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._lookup.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_adds = 0
        self._total_removes = 0
        self._total_lookups = 0
        self._total_evictions = 0
        logger.debug("agent_tag_store_reset")
