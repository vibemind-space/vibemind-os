"""Agent Group Store -- manages agent groups/teams for collaborative tasks.

Provides group creation, membership management, group lookup by tag or
agent, and enumeration with max-entries pruning, callbacks, and structured
logging.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GroupEntry:
    group_id: str
    name: str
    description: str
    members: List[str]
    max_members: int
    tags: List[str]
    created_at: float
    seq: int = 0


class AgentGroupStore:
    """Manages agent groups/teams for collaborative tasks."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, GroupEntry] = {}
        self._name_lookup: Dict[str, str] = {}  # name -> group_id
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_creates = 0
        self._total_removes = 0
        self._total_lookups = 0
        self._total_evictions = 0
        self._total_member_adds = 0
        self._total_member_removes = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"ags-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ags-{digest}"

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

    def _to_dict(self, entry: GroupEntry) -> Dict[str, Any]:
        return {
            "group_id": entry.group_id,
            "name": entry.name,
            "description": entry.description,
            "members": list(entry.members),
            "max_members": entry.max_members,
            "tags": list(entry.tags),
            "created_at": entry.created_at,
        }

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
            self._name_lookup.pop(entry.name, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug("group_evicted", group_id=eid, name=entry.name)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def create_group(
        self,
        name: str,
        description: str = "",
        max_members: int = 50,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new group. Returns group_id, or '' if duplicate name."""
        if not name:
            logger.warning("group_create_invalid_args", name=name)
            return ""

        # Duplicate name check
        existing = self._name_lookup.get(name)
        if existing and existing in self._entries:
            logger.debug("group_duplicate_name", name=name)
            return ""

        self._prune_if_needed()
        group_id = self._gen_id(name)
        now = time.time()
        entry = GroupEntry(
            group_id=group_id,
            name=name,
            description=description,
            members=[],
            max_members=max_members,
            tags=list(tags) if tags else [],
            created_at=now,
            seq=self._seq,
        )
        self._entries[group_id] = entry
        self._name_lookup[name] = group_id
        self._total_creates += 1
        logger.debug("group_created", group_id=group_id, name=name)
        self._fire("group_created", {
            "group_id": group_id,
            "name": name,
            "description": description,
            "max_members": max_members,
            "tags": entry.tags,
        })
        return group_id

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Return group data as a dict, or None if not found."""
        self._total_lookups += 1
        if not group_id:
            return None
        entry = self._entries.get(group_id)
        if not entry:
            return None
        return self._to_dict(entry)

    def add_member(self, group_id: str, agent_id: str) -> bool:
        """Add an agent to a group. Returns False if group missing, member
        already present, or group is at capacity."""
        if not group_id or not agent_id:
            return False

        entry = self._entries.get(group_id)
        if not entry:
            logger.debug("add_member_group_not_found", group_id=group_id)
            return False

        if agent_id in entry.members:
            logger.debug("add_member_duplicate", group_id=group_id, agent_id=agent_id)
            return False

        if len(entry.members) >= entry.max_members:
            logger.warning(
                "add_member_capacity_reached",
                group_id=group_id,
                max_members=entry.max_members,
            )
            return False

        entry.members.append(agent_id)
        self._total_member_adds += 1
        logger.debug("member_added", group_id=group_id, agent_id=agent_id)
        self._fire("member_added", {
            "group_id": group_id,
            "agent_id": agent_id,
            "member_count": len(entry.members),
        })
        return True

    def remove_member(self, group_id: str, agent_id: str) -> bool:
        """Remove an agent from a group. Returns True if the agent was present."""
        if not group_id or not agent_id:
            return False

        entry = self._entries.get(group_id)
        if not entry:
            return False

        if agent_id not in entry.members:
            return False

        entry.members.remove(agent_id)
        self._total_member_removes += 1
        logger.debug("member_removed", group_id=group_id, agent_id=agent_id)
        self._fire("member_removed", {
            "group_id": group_id,
            "agent_id": agent_id,
            "member_count": len(entry.members),
        })
        return True

    def get_members(self, group_id: str) -> List[str]:
        """Return the list of agent_ids in a group."""
        self._total_lookups += 1
        if not group_id:
            return []
        entry = self._entries.get(group_id)
        if not entry:
            return []
        return list(entry.members)

    def find_groups_for_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all groups that contain the given agent."""
        self._total_lookups += 1
        if not agent_id:
            return []

        results: List[Dict[str, Any]] = []
        for entry in self._entries.values():
            if agent_id in entry.members:
                results.append(self._to_dict(entry))
        return results

    def list_groups(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all groups, optionally filtered by tag."""
        self._total_lookups += 1
        results: List[Dict[str, Any]] = []
        for entry in self._entries.values():
            if tag is not None and tag not in entry.tags:
                continue
            results.append(self._to_dict(entry))
        return results

    def remove_group(self, group_id: str) -> bool:
        """Remove a group entirely. Returns True if it existed."""
        if not group_id:
            return False

        entry = self._entries.get(group_id)
        if not entry:
            return False

        self._name_lookup.pop(entry.name, None)
        del self._entries[group_id]
        self._total_removes += 1
        logger.debug("group_removed", group_id=group_id, name=entry.name)
        self._fire("group_removed", {
            "group_id": group_id,
            "name": entry.name,
            "members": list(entry.members),
        })
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        total_members = sum(len(e.members) for e in self._entries.values())
        unique_tags = set()
        for e in self._entries.values():
            unique_tags.update(e.tags)
        return {
            "current_groups": len(self._entries),
            "total_members_across_groups": total_members,
            "unique_tags": len(unique_tags),
            "total_creates": self._total_creates,
            "total_removes": self._total_removes,
            "total_lookups": self._total_lookups,
            "total_evictions": self._total_evictions,
            "total_member_adds": self._total_member_adds,
            "total_member_removes": self._total_member_removes,
            "callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._name_lookup.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_creates = 0
        self._total_removes = 0
        self._total_lookups = 0
        self._total_evictions = 0
        self._total_member_adds = 0
        self._total_member_removes = 0
        logger.debug("agent_group_store_reset")
