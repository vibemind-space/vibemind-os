"""Agent Context Manager – agent execution context management.

Manages execution contexts for agents. Each context is bound to an
agent, holds arbitrary key/value data, and tracks open/closed status
with timestamps.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ContextEntry:
    """Single execution context belonging to an agent."""

    context_id: str
    agent_id: str
    data: Dict[str, Any]
    status: str = "open"
    created_at: float = 0.0
    closed_at: float = 0.0


class AgentContextManager:
    """Manages execution contexts for agents."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._contexts: Dict[str, ContextEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

        self._total_created: int = 0
        self._total_closed: int = 0
        self._total_removed: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"acm2-{self._seq}-{id(self)}"
        return "acm2-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, fn: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        if len(self._contexts) < self._max_entries:
            return
        # Remove oldest closed contexts first, then oldest open ones
        closed = sorted(
            [e for e in self._contexts.values() if e.status == "closed"],
            key=lambda e: e.created_at,
        )
        if closed:
            to_remove = len(self._contexts) - self._max_entries + 1
            for entry in closed[:to_remove]:
                del self._contexts[entry.context_id]
                self._total_removed += 1
            return
        # Fallback: remove oldest entries regardless of status
        oldest = sorted(self._contexts.values(), key=lambda e: e.created_at)
        to_remove = len(self._contexts) - self._max_entries + 1
        for entry in oldest[:to_remove]:
            del self._contexts[entry.context_id]
            self._total_removed += 1

    # ------------------------------------------------------------------
    # Context CRUD
    # ------------------------------------------------------------------

    def create_context(
        self,
        agent_id: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new execution context for *agent_id*.

        Returns the generated context id (``"acm2-..."``).
        """
        if not agent_id:
            return ""

        self._prune_if_needed()

        cid = self._generate_id()
        now = time.time()
        entry = ContextEntry(
            context_id=cid,
            agent_id=agent_id,
            data=dict(context_data) if context_data else {},
            status="open",
            created_at=now,
            closed_at=0.0,
        )
        self._contexts[cid] = entry
        self._total_created += 1
        self._fire("create_context", {"context_id": cid, "agent_id": agent_id})
        return cid

    def get_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Return context dict or ``None`` if not found."""
        entry = self._contexts.get(context_id)
        if entry is None:
            return None
        return {
            "context_id": entry.context_id,
            "agent_id": entry.agent_id,
            "data": dict(entry.data),
            "status": entry.status,
            "created_at": entry.created_at,
            "closed_at": entry.closed_at,
        }

    def update_context(self, context_id: str, key: str, value: Any) -> bool:
        """Set a key/value pair in the context's data dict."""
        entry = self._contexts.get(context_id)
        if entry is None or not key:
            return False
        entry.data[key] = value
        self._fire("update_context", {"context_id": context_id, "key": key})
        return True

    def get_context_value(self, context_id: str, key: str) -> Any:
        """Return a single value from the context data, or ``None``."""
        entry = self._contexts.get(context_id)
        if entry is None:
            return None
        return entry.data.get(key)

    def close_context(self, context_id: str) -> bool:
        """Mark a context as closed."""
        entry = self._contexts.get(context_id)
        if entry is None:
            return False
        if entry.status == "closed":
            return False
        entry.status = "closed"
        entry.closed_at = time.time()
        self._total_closed += 1
        self._fire("close_context", {"context_id": context_id, "agent_id": entry.agent_id})
        return True

    def remove_context(self, context_id: str) -> bool:
        """Permanently remove a context."""
        if context_id not in self._contexts:
            return False
        agent_id = self._contexts[context_id].agent_id
        del self._contexts[context_id]
        self._total_removed += 1
        self._fire("remove_context", {"context_id": context_id, "agent_id": agent_id})
        return True

    # ------------------------------------------------------------------
    # Agent queries
    # ------------------------------------------------------------------

    def get_agent_contexts(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return all contexts (open and closed) for *agent_id*."""
        results: List[Dict[str, Any]] = []
        for entry in self._contexts.values():
            if entry.agent_id == agent_id:
                results.append({
                    "context_id": entry.context_id,
                    "agent_id": entry.agent_id,
                    "data": dict(entry.data),
                    "status": entry.status,
                    "created_at": entry.created_at,
                    "closed_at": entry.closed_at,
                })
        results.sort(key=lambda x: x["created_at"])
        return results

    def get_active_contexts(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return only open (non-closed) contexts for *agent_id*."""
        return [
            ctx for ctx in self.get_agent_contexts(agent_id)
            if ctx["status"] == "open"
        ]

    def list_agents(self) -> List[str]:
        """Return a sorted list of unique agent ids with contexts."""
        agents = sorted({entry.agent_id for entry in self._contexts.values()})
        return agents

    def get_context_count(self) -> int:
        """Return the total number of contexts currently stored."""
        return len(self._contexts)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        open_count = sum(1 for e in self._contexts.values() if e.status == "open")
        closed_count = sum(1 for e in self._contexts.values() if e.status == "closed")
        agent_count = len({e.agent_id for e in self._contexts.values()})
        total_data_keys = sum(len(e.data) for e in self._contexts.values())
        return {
            "current_contexts": len(self._contexts),
            "open_contexts": open_count,
            "closed_contexts": closed_count,
            "unique_agents": agent_count,
            "total_data_keys": total_data_keys,
            "total_created": self._total_created,
            "total_closed": self._total_closed,
            "total_removed": self._total_removed,
            "callback_count": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all contexts, callbacks, and counters."""
        self._contexts.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_closed = 0
        self._total_removed = 0
