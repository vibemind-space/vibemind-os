"""Agent Context Cache -- per-agent contextual memory cache for emergent pipelines.

Manages contextual memory caches per agent, storing conversation and task
context that agents can recall later.  Entries are keyed by agent_id and
context_type, supporting substring search, latest-context retrieval, and
automatic max-entries pruning.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class ContextEntry:
    """A single context record stored for an agent."""

    context_id: str
    agent_id: str
    context_type: str
    content: Any
    metadata: Dict[str, Any]
    created_at: float
    seq: int = 0


# ---------------------------------------------------------------------------
# AgentContextCache
# ---------------------------------------------------------------------------

class AgentContextCache:
    """Per-agent contextual memory cache with search, pruning, and callbacks."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max(1, max_entries)

        # Primary storage: context_id -> ContextEntry
        self._entries: Dict[str, ContextEntry] = {}

        # Secondary index: agent_id -> list of context_ids (insertion order)
        self._agent_index: Dict[str, List[str]] = {}

        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq = 0

        # Counters
        self._total_stores = 0
        self._total_gets = 0
        self._total_searches = 0
        self._total_deletes = 0
        self._total_pruned = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        """Generate a unique context ID with prefix ``acc-``."""
        self._seq += 1
        raw = f"{seed}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"acc-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.

        Returns False if a callback with this name is already registered.
        """
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns True if a callback was found and removed.
        """
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Notify all registered callbacks of a change event."""
        callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: ContextEntry) -> Dict[str, Any]:
        """Convert a ContextEntry dataclass to a plain dict."""
        return {
            "context_id": entry.context_id,
            "agent_id": entry.agent_id,
            "context_type": entry.context_type,
            "content": entry.content,
            "metadata": dict(entry.metadata),
            "created_at": entry.created_at,
            "seq": entry.seq,
        }

    def _prune_oldest(self) -> None:
        """Remove the oldest entry (by seq) to make room for a new one.

        Must be called while holding ``self._lock``.
        """
        if not self._entries:
            return

        oldest_id = min(self._entries, key=lambda cid: self._entries[cid].seq)
        entry = self._entries.pop(oldest_id)

        # Update agent index
        agent_ids_list = self._agent_index.get(entry.agent_id)
        if agent_ids_list is not None:
            try:
                agent_ids_list.remove(oldest_id)
            except ValueError:
                pass
            if not agent_ids_list:
                del self._agent_index[entry.agent_id]

        self._total_pruned += 1
        logger.debug(
            "context_entry_pruned",
            extra={"context_id": oldest_id, "agent_id": entry.agent_id},
        )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def store_context(
        self,
        agent_id: str,
        context_type: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a context entry for an agent.

        Parameters
        ----------
        agent_id:
            The owning agent identifier.
        context_type:
            A label categorising the context (e.g. ``"conversation"``,
            ``"task"``, ``"observation"``).
        content:
            Arbitrary content to cache -- may be a string, dict, list, etc.
        metadata:
            Optional additional metadata to attach to the entry.

        Returns
        -------
        str
            The generated context ID (prefixed ``acc-``).  Returns an empty
            string if *agent_id* or *context_type* are falsy.
        """
        if not agent_id or not context_type:
            logger.warning(
                "store_context_invalid_args",
                extra={"agent_id": agent_id, "context_type": context_type},
            )
            return ""

        resolved_metadata = dict(metadata) if metadata else {}
        now = time.time()

        with self._lock:
            # Prune if at capacity
            if len(self._entries) >= self._max_entries:
                self._prune_oldest()

            context_id = self._gen_id(f"{agent_id}:{context_type}")
            entry = ContextEntry(
                context_id=context_id,
                agent_id=agent_id,
                context_type=context_type,
                content=content,
                metadata=resolved_metadata,
                created_at=now,
                seq=self._seq,
            )
            self._entries[context_id] = entry

            # Update agent index
            if agent_id not in self._agent_index:
                self._agent_index[agent_id] = []
            self._agent_index[agent_id].append(context_id)

            self._total_stores += 1

        logger.debug(
            "context_stored",
            extra={
                "context_id": context_id,
                "agent_id": agent_id,
                "context_type": context_type,
            },
        )
        self._fire("context_stored", {
            "context_id": context_id,
            "agent_id": agent_id,
            "context_type": context_type,
        })
        return context_id

    def get_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single context entry by its ID.

        Returns None if not found.
        """
        self._total_gets += 1
        with self._lock:
            entry = self._entries.get(context_id)
            if entry is None:
                return None
            return self._entry_to_dict(entry)

    def get_agent_contexts(
        self,
        agent_id: str,
        context_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all context entries for an agent.

        Parameters
        ----------
        agent_id:
            The agent to query.
        context_type:
            If provided, only entries matching this type are returned.

        Returns
        -------
        list
            A list of context dicts ordered by creation sequence (oldest first).
        """
        with self._lock:
            cids = self._agent_index.get(agent_id, [])
            results: List[Dict[str, Any]] = []
            for cid in cids:
                entry = self._entries.get(cid)
                if entry is None:
                    continue
                if context_type is not None and entry.context_type != context_type:
                    continue
                results.append(self._entry_to_dict(entry))
        return results

    def get_latest_context(
        self,
        agent_id: str,
        context_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent context entry for an agent.

        Parameters
        ----------
        agent_id:
            The agent to query.
        context_type:
            If provided, only entries of this type are considered.

        Returns
        -------
        dict or None
            The latest context dict, or None if no matching entry exists.
        """
        with self._lock:
            cids = self._agent_index.get(agent_id, [])
            latest: Optional[ContextEntry] = None
            for cid in cids:
                entry = self._entries.get(cid)
                if entry is None:
                    continue
                if context_type is not None and entry.context_type != context_type:
                    continue
                if latest is None or entry.seq > latest.seq:
                    latest = entry
            if latest is None:
                return None
            return self._entry_to_dict(latest)

    def search_contexts(
        self,
        agent_id: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Search an agent's contexts by substring match on content.

        The *query* is matched case-insensitively against the string
        representation of each entry's content.

        Parameters
        ----------
        agent_id:
            The agent whose contexts to search.
        query:
            Substring to look for in ``str(content)``.

        Returns
        -------
        list
            Matching context dicts, ordered by creation sequence.
        """
        self._total_searches += 1
        if not query:
            return []

        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        with self._lock:
            cids = self._agent_index.get(agent_id, [])
            for cid in cids:
                entry = self._entries.get(cid)
                if entry is None:
                    continue
                content_str = (
                    entry.content if isinstance(entry.content, str)
                    else str(entry.content)
                )
                if query_lower in content_str.lower():
                    results.append(self._entry_to_dict(entry))

        return results

    def delete_context(self, context_id: str) -> bool:
        """Delete a context entry by ID.

        Returns True if the entry existed and was removed, False otherwise.
        """
        with self._lock:
            entry = self._entries.pop(context_id, None)
            if entry is None:
                return False

            # Update agent index
            agent_ids_list = self._agent_index.get(entry.agent_id)
            if agent_ids_list is not None:
                try:
                    agent_ids_list.remove(context_id)
                except ValueError:
                    pass
                if not agent_ids_list:
                    del self._agent_index[entry.agent_id]

            self._total_deletes += 1

        logger.debug(
            "context_deleted",
            extra={"context_id": context_id, "agent_id": entry.agent_id},
        )
        self._fire("context_deleted", {
            "context_id": context_id,
            "agent_id": entry.agent_id,
            "context_type": entry.context_type,
        })
        return True

    def clear_agent_contexts(self, agent_id: str) -> int:
        """Remove all context entries for an agent.

        Returns the number of entries deleted.
        """
        if not agent_id:
            return 0

        with self._lock:
            cids = self._agent_index.pop(agent_id, [])
            count = 0
            for cid in cids:
                if self._entries.pop(cid, None) is not None:
                    count += 1
            self._total_deletes += count

        if count > 0:
            logger.debug(
                "agent_contexts_cleared",
                extra={"agent_id": agent_id, "count": count},
            )
            self._fire("agent_contexts_cleared", {
                "agent_id": agent_id,
                "count": count,
            })
        return count

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_context_count(self, agent_id: str) -> int:
        """Return the number of context entries for an agent."""
        with self._lock:
            cids = self._agent_index.get(agent_id, [])
            return len(cids)

    def list_agents(self) -> List[str]:
        """Return a sorted list of all agent IDs that have stored contexts."""
        with self._lock:
            return sorted(
                aid for aid, cids in self._agent_index.items() if cids
            )

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate counters and current sizes."""
        with self._lock:
            current_entries = len(self._entries)
            current_agents = len(
                [aid for aid, cids in self._agent_index.items() if cids]
            )
            callbacks_count = len(self._callbacks)

        return {
            "current_entries": current_entries,
            "current_agents": current_agents,
            "max_entries": self._max_entries,
            "total_stores": self._total_stores,
            "total_gets": self._total_gets,
            "total_searches": self._total_searches,
            "total_deletes": self._total_deletes,
            "total_pruned": self._total_pruned,
            "callbacks": callbacks_count,
        }

    def reset(self) -> None:
        """Clear all state -- entries, indexes, callbacks, and counters."""
        with self._lock:
            self._entries.clear()
            self._agent_index.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_stores = 0
            self._total_gets = 0
            self._total_searches = 0
            self._total_deletes = 0
            self._total_pruned = 0
        logger.debug("agent_context_cache_reset")
