"""Agent work journal - structured logging of agent activities and decisions."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class JournalEntry:
    """A single journal entry."""
    entry_id: str = ""
    agent: str = ""
    entry_type: str = ""
    title: str = ""
    content: str = ""
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    parent_id: str = ""
    created_at: float = 0.0


class AgentWorkJournal:
    """Structured activity journal for agent work tracking."""

    ENTRY_TYPES = (
        "decision", "action", "observation", "error",
        "milestone", "note", "question", "result",
    )

    def __init__(self, max_entries: int = 100000, max_entries_per_agent: int = 10000):
        self._max_entries = max(1, max_entries)
        self._max_per_agent = max(1, max_entries_per_agent)
        self._entries: Dict[str, JournalEntry] = {}
        self._agent_entries: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries": 0,
            "total_agents": 0,
        }

    # --- Entry Management ---

    def add_entry(
        self,
        agent: str,
        entry_type: str,
        title: str,
        content: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        parent_id: str = "",
    ) -> str:
        """Add a journal entry. Returns entry_id."""
        if not agent or not title:
            return ""
        if entry_type not in self.ENTRY_TYPES:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        if parent_id and parent_id not in self._entries:
            return ""

        agent_list = self._agent_entries.get(agent, [])
        if len(agent_list) >= self._max_per_agent:
            return ""

        eid = f"journal-{uuid.uuid4().hex[:12]}"
        now = time.time()

        self._entries[eid] = JournalEntry(
            entry_id=eid,
            agent=agent,
            entry_type=entry_type,
            title=title,
            content=content,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            parent_id=parent_id,
            created_at=now,
        )

        if agent not in self._agent_entries:
            self._agent_entries[agent] = []
            self._stats["total_agents"] += 1
        self._agent_entries[agent].append(eid)
        self._stats["total_entries"] += 1

        self._fire("entry_added", {"entry_id": eid, "agent": agent, "type": entry_type})
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a journal entry."""
        e = self._entries.get(entry_id)
        if not e:
            return None
        return {
            "entry_id": e.entry_id,
            "agent": e.agent,
            "entry_type": e.entry_type,
            "title": e.title,
            "content": e.content,
            "tags": list(e.tags),
            "metadata": dict(e.metadata),
            "parent_id": e.parent_id,
            "created_at": e.created_at,
        }

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a journal entry."""
        e = self._entries.get(entry_id)
        if not e:
            return False
        agent_list = self._agent_entries.get(e.agent, [])
        if entry_id in agent_list:
            agent_list.remove(entry_id)
        del self._entries[entry_id]
        return True

    # --- Queries ---

    def get_agent_journal(
        self,
        agent: str,
        entry_type: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Get journal entries for an agent (newest first)."""
        eids = self._agent_entries.get(agent, [])
        results = []
        for eid in reversed(eids):
            e = self._entries.get(eid)
            if not e:
                continue
            if entry_type and e.entry_type != entry_type:
                continue
            if tag and tag not in e.tags:
                continue
            results.append({
                "entry_id": e.entry_id,
                "entry_type": e.entry_type,
                "title": e.title,
                "created_at": e.created_at,
            })
            if len(results) >= limit:
                break
        return results

    def search_entries(
        self,
        query: str,
        agent: str = "",
        entry_type: str = "",
        limit: int = 50,
    ) -> List[Dict]:
        """Search entries by title or content."""
        if not query:
            return []
        query_lower = query.lower()
        results = []
        for e in self._entries.values():
            if agent and e.agent != agent:
                continue
            if entry_type and e.entry_type != entry_type:
                continue
            if query_lower not in e.title.lower() and query_lower not in e.content.lower():
                continue
            results.append({
                "entry_id": e.entry_id,
                "agent": e.agent,
                "entry_type": e.entry_type,
                "title": e.title,
                "created_at": e.created_at,
            })
            if len(results) >= limit:
                break
        return results

    def get_thread(self, entry_id: str) -> List[Dict]:
        """Get a thread of related entries (parent chain)."""
        results = []
        current = entry_id
        seen = set()
        while current and current not in seen:
            seen.add(current)
            e = self._entries.get(current)
            if not e:
                break
            results.append({
                "entry_id": e.entry_id,
                "entry_type": e.entry_type,
                "title": e.title,
                "created_at": e.created_at,
            })
            current = e.parent_id
        results.reverse()
        return results

    def get_children(self, entry_id: str) -> List[Dict]:
        """Get direct child entries."""
        results = []
        for e in self._entries.values():
            if e.parent_id == entry_id:
                results.append({
                    "entry_id": e.entry_id,
                    "entry_type": e.entry_type,
                    "title": e.title,
                    "created_at": e.created_at,
                })
        return results

    def list_entries(
        self,
        entry_type: str = "",
        tag: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """List all entries with filters."""
        results = []
        for e in self._entries.values():
            if entry_type and e.entry_type != entry_type:
                continue
            if tag and tag not in e.tags:
                continue
            results.append({
                "entry_id": e.entry_id,
                "agent": e.agent,
                "entry_type": e.entry_type,
                "title": e.title,
                "created_at": e.created_at,
            })
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results[:limit]

    # --- Analytics ---

    def get_agent_summary(self, agent: str) -> Dict:
        """Get activity summary for an agent."""
        eids = self._agent_entries.get(agent, [])
        if not eids:
            return {}
        by_type: Dict[str, int] = {}
        for eid in eids:
            e = self._entries.get(eid)
            if e:
                by_type[e.entry_type] = by_type.get(e.entry_type, 0) + 1
        return {
            "agent": agent,
            "total_entries": len(eids),
            "by_type": by_type,
        }

    def get_type_distribution(self) -> Dict[str, int]:
        """Get entry count per type."""
        dist: Dict[str, int] = {}
        for e in self._entries.values():
            dist[e.entry_type] = dist.get(e.entry_type, 0) + 1
        return dist

    def get_active_agents(self) -> List[str]:
        """Get agents with journal entries."""
        return list(self._agent_entries.keys())

    def get_recent_activity(self, limit: int = 20) -> List[Dict]:
        """Get most recent entries across all agents."""
        return self.list_entries(limit=limit)

    # --- Callbacks ---

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

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_agents": len(self._agent_entries),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._agent_entries.clear()
        self._callbacks.clear()
        self._stats = {
            "total_entries": 0,
            "total_agents": 0,
        }

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
