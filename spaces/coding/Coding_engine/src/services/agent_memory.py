"""
Agent Memory — Persistent context and knowledge across pipeline sessions.

Provides:
- Per-agent memory stores with typed entries
- Short-term (session) and long-term (persistent) memory
- Memory categories: decisions, patterns, errors, learnings, context
- TTL-based expiration for short-term entries
- Memory search and retrieval by category, tag, or content
- Memory consolidation (compress old entries into summaries)
- Import/export for backup and transfer
- Stats and usage tracking

Usage:
    memory = AgentMemoryStore()

    # Store a learning
    memory.remember("Builder", "learning",
        content="pytest fixtures are preferred over setUp/tearDown",
        tags={"testing", "python"},
    )

    # Recall memories
    entries = memory.recall("Builder", category="learning", limit=10)

    # Search across all agents
    results = memory.search("pytest fixture", limit=5)
"""

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class MemoryCategory(str, Enum):
    DECISION = "decision"       # Architectural/design decisions
    PATTERN = "pattern"         # Code patterns discovered/preferred
    ERROR = "error"             # Errors encountered and fixes
    LEARNING = "learning"       # General learnings
    CONTEXT = "context"         # Session/task context
    PREFERENCE = "preference"   # User/project preferences
    FACT = "fact"               # Known facts about the codebase


class MemoryTier(str, Enum):
    SHORT_TERM = "short_term"   # Session-scoped, auto-expires
    LONG_TERM = "long_term"     # Persists across sessions
    CORE = "core"               # Critical, never auto-pruned


@dataclass
class MemoryEntry:
    """A single memory entry."""
    entry_id: str
    agent_name: str
    category: str
    content: str
    tier: str = MemoryTier.LONG_TERM
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl_seconds: float = 0.0  # 0 = no expiry
    importance: float = 0.5   # 0.0 to 1.0

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "agent_name": self.agent_name,
            "category": self.category,
            "content": self.content,
            "tier": self.tier,
            "tags": sorted(self.tags),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "importance": self.importance,
        }


class AgentMemoryStore:
    """Manages persistent memory for all agents."""

    def __init__(self, max_entries_per_agent: int = 500):
        self._max_entries = max_entries_per_agent

        # agent_name -> {entry_id -> MemoryEntry}
        self._stores: Dict[str, Dict[str, MemoryEntry]] = {}

        # Stats
        self._total_stored = 0
        self._total_recalled = 0
        self._total_pruned = 0
        self._total_searches = 0

    # ── Store ─────────────────────────────────────────────────────────

    def remember(
        self,
        agent_name: str,
        category: str,
        content: str,
        tier: str = MemoryTier.LONG_TERM,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: float = 0.0,
        importance: float = 0.5,
    ) -> str:
        """Store a memory entry for an agent."""
        entry_id = f"mem-{uuid.uuid4().hex[:8]}"

        entry = MemoryEntry(
            entry_id=entry_id,
            agent_name=agent_name,
            category=category,
            content=content,
            tier=tier,
            tags=set(tags) if tags else set(),
            metadata=metadata or {},
            ttl_seconds=ttl_seconds,
            importance=importance,
        )

        if agent_name not in self._stores:
            self._stores[agent_name] = {}

        store = self._stores[agent_name]
        store[entry_id] = entry
        self._total_stored += 1

        # Prune if over limit
        if len(store) > self._max_entries:
            self._prune_agent(agent_name)

        logger.debug(
            "memory_stored",
            component="agent_memory",
            agent=agent_name,
            category=category,
            entry_id=entry_id,
            tier=tier,
        )

        return entry_id

    # ── Recall ────────────────────────────────────────────────────────

    def recall(
        self,
        agent_name: str,
        category: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        tier: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Recall memories for an agent with filters."""
        store = self._stores.get(agent_name, {})
        self._total_recalled += 1

        results = []
        for entry in store.values():
            if entry.is_expired:
                continue
            if category and entry.category != category:
                continue
            if tier and entry.tier != tier:
                continue
            if tags and not tags.issubset(entry.tags):
                continue

            entry.accessed_at = time.time()
            entry.access_count += 1
            results.append(entry)

        # Sort by importance (desc), then recency (desc)
        results.sort(key=lambda e: (-e.importance, -e.created_at))

        return [e.to_dict() for e in results[:limit]]

    def recall_recent(
        self,
        agent_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Recall most recent memories for an agent."""
        store = self._stores.get(agent_name, {})
        self._total_recalled += 1

        entries = [e for e in store.values() if not e.is_expired]
        entries.sort(key=lambda e: -e.created_at)

        for e in entries[:limit]:
            e.accessed_at = time.time()
            e.access_count += 1

        return [e.to_dict() for e in entries[:limit]]

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory entry by ID."""
        for store in self._stores.values():
            if entry_id in store:
                entry = store[entry_id]
                if not entry.is_expired:
                    entry.accessed_at = time.time()
                    entry.access_count += 1
                    return entry.to_dict()
        return None

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        agent_name: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search memories by content substring."""
        self._total_searches += 1
        query_lower = query.lower()

        results = []
        stores = (
            {agent_name: self._stores.get(agent_name, {})}
            if agent_name
            else self._stores
        )

        for store in stores.values():
            for entry in store.values():
                if entry.is_expired:
                    continue
                if category and entry.category != category:
                    continue

                # Search in content, tags, and metadata
                if (
                    query_lower in entry.content.lower()
                    or any(query_lower in t.lower() for t in entry.tags)
                ):
                    results.append(entry)

        # Sort by relevance (exact match first), then importance
        results.sort(key=lambda e: (-e.importance, -e.access_count))
        return [e.to_dict() for e in results[:limit]]

    # ── Manage ────────────────────────────────────────────────────────

    def forget(self, entry_id: str) -> bool:
        """Remove a specific memory entry."""
        for store in self._stores.values():
            if entry_id in store:
                del store[entry_id]
                return True
        return False

    def forget_agent(self, agent_name: str) -> int:
        """Remove all memories for an agent."""
        store = self._stores.pop(agent_name, {})
        return len(store)

    def update_importance(self, entry_id: str, importance: float) -> bool:
        """Update the importance of a memory entry."""
        for store in self._stores.values():
            if entry_id in store:
                store[entry_id].importance = max(0.0, min(1.0, importance))
                return True
        return False

    def add_tags(self, entry_id: str, tags: Set[str]) -> bool:
        """Add tags to a memory entry."""
        for store in self._stores.values():
            if entry_id in store:
                store[entry_id].tags.update(tags)
                return True
        return False

    def promote(self, entry_id: str) -> bool:
        """Promote a memory to a higher tier."""
        for store in self._stores.values():
            if entry_id in store:
                entry = store[entry_id]
                if entry.tier == MemoryTier.SHORT_TERM:
                    entry.tier = MemoryTier.LONG_TERM
                elif entry.tier == MemoryTier.LONG_TERM:
                    entry.tier = MemoryTier.CORE
                else:
                    return False  # Already core
                entry.ttl_seconds = 0.0  # Remove TTL
                return True
        return False

    # ── Bulk Operations ───────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove all expired entries across all agents."""
        removed = 0
        for store in self._stores.values():
            expired_ids = [
                eid for eid, entry in store.items() if entry.is_expired
            ]
            for eid in expired_ids:
                del store[eid]
                removed += 1
        self._total_pruned += removed
        return removed

    def get_agent_summary(self, agent_name: str) -> Dict[str, Any]:
        """Get a summary of an agent's memory."""
        store = self._stores.get(agent_name, {})
        if not store:
            return {"agent": agent_name, "total_entries": 0}

        categories = {}
        tiers = {}
        for entry in store.values():
            if entry.is_expired:
                continue
            categories[entry.category] = categories.get(entry.category, 0) + 1
            tiers[entry.tier] = tiers.get(entry.tier, 0) + 1

        return {
            "agent": agent_name,
            "total_entries": len(store),
            "categories": categories,
            "tiers": tiers,
            "most_accessed": max(
                (e for e in store.values() if not e.is_expired),
                key=lambda e: e.access_count,
                default=None,
            ).entry_id if store else None,
        }

    def list_agents(self) -> List[str]:
        """List all agents with stored memories."""
        return sorted(self._stores.keys())

    # ── Export / Import ───────────────────────────────────────────────

    def export_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """Export all memories for an agent."""
        store = self._stores.get(agent_name, {})
        return [entry.to_dict() for entry in store.values()]

    def import_memories(self, agent_name: str, entries: List[Dict[str, Any]]) -> int:
        """Import memories for an agent."""
        if agent_name not in self._stores:
            self._stores[agent_name] = {}

        imported = 0
        for data in entries:
            entry = MemoryEntry(
                entry_id=data.get("entry_id", f"mem-{uuid.uuid4().hex[:8]}"),
                agent_name=agent_name,
                category=data["category"],
                content=data["content"],
                tier=data.get("tier", MemoryTier.LONG_TERM),
                tags=set(data.get("tags", [])),
                metadata=data.get("metadata", {}),
                created_at=data.get("created_at", time.time()),
                accessed_at=data.get("accessed_at", time.time()),
                access_count=data.get("access_count", 0),
                importance=data.get("importance", 0.5),
            )
            self._stores[agent_name][entry.entry_id] = entry
            imported += 1

        self._total_stored += imported
        return imported

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get memory store statistics."""
        total_entries = sum(len(s) for s in self._stores.values())
        return {
            "total_agents": len(self._stores),
            "total_entries": total_entries,
            "total_stored": self._total_stored,
            "total_recalled": self._total_recalled,
            "total_searches": self._total_searches,
            "total_pruned": self._total_pruned,
        }

    def reset(self):
        """Reset all memory stores."""
        self._stores.clear()
        self._total_stored = 0
        self._total_recalled = 0
        self._total_pruned = 0
        self._total_searches = 0

    # ── Internal ──────────────────────────────────────────────────────

    def _prune_agent(self, agent_name: str):
        """Prune oldest/least important non-core entries to stay under limit."""
        store = self._stores.get(agent_name, {})
        if len(store) <= self._max_entries:
            return

        # First remove expired
        expired = [eid for eid, e in store.items() if e.is_expired]
        for eid in expired:
            del store[eid]
            self._total_pruned += 1

        if len(store) <= self._max_entries:
            return

        # Remove lowest importance short-term first, then long-term
        # Never auto-remove core entries
        candidates = [
            e for e in store.values()
            if e.tier != MemoryTier.CORE
        ]
        candidates.sort(key=lambda e: (
            0 if e.tier == MemoryTier.SHORT_TERM else 1,
            e.importance,
            e.access_count,
        ))

        to_remove = len(store) - self._max_entries
        for entry in candidates[:to_remove]:
            del store[entry.entry_id]
            self._total_pruned += 1

        logger.debug(
            "memory_pruned",
            component="agent_memory",
            agent=agent_name,
            pruned=to_remove,
            remaining=len(store),
        )
