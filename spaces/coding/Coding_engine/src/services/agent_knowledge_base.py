"""Agent knowledge base.

Stores, indexes, and retrieves knowledge entries for agents.
Supports categorization, tagging, relevance scoring, and cross-referencing.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Entry:
    """Internal knowledge entry."""
    entry_id: str = ""
    title: str = ""
    content: str = ""
    category: str = "general"
    source: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    access_count: int = 0
    relevance_score: float = 1.0
    created_at: float = 0.0
    updated_at: float = 0.0


class AgentKnowledgeBase:
    """Stores and retrieves knowledge entries for agents."""

    CATEGORIES = ("general", "technical", "process", "domain", "pattern",
                  "error", "solution", "architecture", "custom")

    def __init__(self, max_entries: int = 50000):
        self._max_entries = max_entries
        self._entries: Dict[str, _Entry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_entries_created": 0,
            "total_queries": 0,
            "total_updates": 0,
            "total_deleted": 0,
        }

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    def add_entry(self, title: str, content: str, category: str = "general",
                  source: str = "", author: str = "",
                  tags: Optional[List[str]] = None,
                  references: Optional[List[str]] = None,
                  relevance_score: float = 1.0) -> str:
        """Add a knowledge entry."""
        if not title or not content:
            return ""
        if category not in self.CATEGORIES:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        eid = "kb-" + hashlib.md5(f"{title}{time.time()}".encode()).hexdigest()[:12]
        now = time.time()
        self._entries[eid] = _Entry(
            entry_id=eid,
            title=title,
            content=content,
            category=category,
            source=source,
            author=author,
            tags=tags or [],
            references=references or [],
            relevance_score=relevance_score,
            created_at=now,
            updated_at=now,
        )
        self._stats["total_entries_created"] += 1
        self._fire("entry_added", {"entry_id": eid, "title": title})
        return eid

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get a knowledge entry and increment access count."""
        e = self._entries.get(entry_id)
        if not e:
            return None
        e.access_count += 1
        return {
            "entry_id": e.entry_id,
            "title": e.title,
            "content": e.content,
            "category": e.category,
            "source": e.source,
            "author": e.author,
            "tags": list(e.tags),
            "references": list(e.references),
            "access_count": e.access_count,
            "relevance_score": e.relevance_score,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }

    def update_entry(self, entry_id: str, title: Optional[str] = None,
                     content: Optional[str] = None,
                     category: Optional[str] = None,
                     tags: Optional[List[str]] = None,
                     relevance_score: Optional[float] = None) -> bool:
        """Update a knowledge entry."""
        e = self._entries.get(entry_id)
        if not e:
            return False
        if category and category not in self.CATEGORIES:
            return False

        if title:
            e.title = title
        if content:
            e.content = content
        if category:
            e.category = category
        if tags is not None:
            e.tags = list(tags)
        if relevance_score is not None:
            e.relevance_score = relevance_score
        e.updated_at = time.time()
        self._stats["total_updates"] += 1
        return True

    def remove_entry(self, entry_id: str) -> bool:
        """Remove a knowledge entry."""
        if entry_id not in self._entries:
            return False
        # Remove references to this entry
        for other in self._entries.values():
            if entry_id in other.references:
                other.references.remove(entry_id)
        del self._entries[entry_id]
        self._stats["total_deleted"] += 1
        return True

    # ------------------------------------------------------------------
    # Search and query
    # ------------------------------------------------------------------

    def search(self, query: str, category: Optional[str] = None,
               tag: Optional[str] = None, author: Optional[str] = None,
               limit: int = 20) -> List[Dict]:
        """Search entries by text matching in title and content."""
        if not query:
            return []
        self._stats["total_queries"] += 1

        query_lower = query.lower()
        results = []

        for e in self._entries.values():
            if category and e.category != category:
                continue
            if tag and tag not in e.tags:
                continue
            if author and e.author != author:
                continue

            # Score based on matches
            score = 0.0
            if query_lower in e.title.lower():
                score += 2.0
            if query_lower in e.content.lower():
                score += 1.0
            for t in e.tags:
                if query_lower in t.lower():
                    score += 0.5

            if score > 0:
                score *= e.relevance_score
                results.append({
                    "entry_id": e.entry_id,
                    "title": e.title,
                    "category": e.category,
                    "score": round(score, 4),
                    "tags": list(e.tags),
                    "author": e.author,
                })

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def get_by_category(self, category: str, limit: int = 50) -> List[Dict]:
        """Get entries by category."""
        result = []
        for e in self._entries.values():
            if e.category != category:
                continue
            result.append({
                "entry_id": e.entry_id,
                "title": e.title,
                "tags": list(e.tags),
                "relevance_score": e.relevance_score,
                "access_count": e.access_count,
            })
        result.sort(key=lambda x: -x["relevance_score"])
        return result[:limit]

    def get_by_tag(self, tag: str, limit: int = 50) -> List[Dict]:
        """Get entries by tag."""
        result = []
        for e in self._entries.values():
            if tag not in e.tags:
                continue
            result.append({
                "entry_id": e.entry_id,
                "title": e.title,
                "category": e.category,
                "relevance_score": e.relevance_score,
            })
        result.sort(key=lambda x: -x["relevance_score"])
        return result[:limit]

    def get_by_author(self, author: str, limit: int = 50) -> List[Dict]:
        """Get entries by author."""
        result = []
        for e in self._entries.values():
            if e.author != author:
                continue
            result.append({
                "entry_id": e.entry_id,
                "title": e.title,
                "category": e.category,
            })
        return result[:limit]

    def get_references(self, entry_id: str) -> List[Dict]:
        """Get referenced entries."""
        e = self._entries.get(entry_id)
        if not e:
            return []
        result = []
        for ref_id in e.references:
            ref = self._entries.get(ref_id)
            if ref:
                result.append({
                    "entry_id": ref.entry_id,
                    "title": ref.title,
                    "category": ref.category,
                })
        return result

    def get_referencing(self, entry_id: str) -> List[Dict]:
        """Get entries that reference this entry."""
        result = []
        for e in self._entries.values():
            if entry_id in e.references:
                result.append({
                    "entry_id": e.entry_id,
                    "title": e.title,
                    "category": e.category,
                })
        return result

    def get_most_accessed(self, limit: int = 10) -> List[Dict]:
        """Get most frequently accessed entries."""
        entries = [
            {
                "entry_id": e.entry_id,
                "title": e.title,
                "category": e.category,
                "access_count": e.access_count,
            }
            for e in self._entries.values()
            if e.access_count > 0
        ]
        entries.sort(key=lambda x: -x["access_count"])
        return entries[:limit]

    def get_category_summary(self) -> List[Dict]:
        """Get entry counts by category."""
        counts: Dict[str, int] = {}
        for e in self._entries.values():
            counts[e.category] = counts.get(e.category, 0) + 1

        return [
            {"category": cat, "count": cnt}
            for cat, cnt in sorted(counts.items(), key=lambda x: -x[1])
        ]

    def get_all_tags(self) -> Dict[str, int]:
        """Get all tags with usage counts."""
        tag_counts: Dict[str, int] = {}
        for e in self._entries.values():
            for t in e.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))

    def list_entries(self, limit: int = 100) -> List[Dict]:
        """List all entries (basic info)."""
        result = []
        for e in self._entries.values():
            result.append({
                "entry_id": e.entry_id,
                "title": e.title,
                "category": e.category,
                "tags": list(e.tags),
            })
        return result[:limit]

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
            "current_entries": len(self._entries),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._stats = {k: 0 for k in self._stats}
