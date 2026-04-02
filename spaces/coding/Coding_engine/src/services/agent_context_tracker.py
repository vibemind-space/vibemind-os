"""Agent Context Tracker – tracks conversation/task context for agents.

Manages context entries per agent, storing key-value context data with
TTL support, scoping, and history. Enables agents to maintain state
across multi-step interactions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ContextEntry:
    entry_id: str
    agent: str
    scope: str
    data: Dict[str, Any]
    ttl_seconds: float
    created_at: float
    updated_at: float
    access_count: int
    tags: List[str]


class AgentContextTracker:
    """Tracks context data for agents across interactions."""

    SCOPES = ("global", "task", "session", "step", "custom")

    def __init__(self, max_entries: int = 50000, max_history: int = 100000):
        self._entries: Dict[str, _ContextEntry] = {}
        self._agent_scope_index: Dict[str, str] = {}  # "agent:scope" -> entry_id
        self._agent_index: Dict[str, List[str]] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_reads = 0
        self._total_writes = 0
        self._total_expired = 0

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def create_context(
        self,
        agent: str,
        scope: str = "task",
        data: Optional[Dict[str, Any]] = None,
        ttl_seconds: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent or scope not in self.SCOPES:
            return ""
        key = f"{agent}:{scope}"
        if key in self._agent_scope_index:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{scope}-{now}-{self._seq}"
        eid = "ctx-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        entry = _ContextEntry(
            entry_id=eid,
            agent=agent,
            scope=scope,
            data=data or {},
            ttl_seconds=ttl_seconds,
            created_at=now,
            updated_at=now,
            access_count=0,
            tags=tags or [],
        )
        self._entries[eid] = entry
        self._agent_scope_index[key] = eid
        self._agent_index.setdefault(agent, []).append(eid)
        self._total_created += 1
        self._fire("context_created", {"entry_id": eid, "agent": agent, "scope": scope})
        return eid

    def get_context(self, entry_id: str) -> Optional[Dict[str, Any]]:
        e = self._entries.get(entry_id)
        if not e:
            return None
        if self._is_expired(e):
            self._expire(e)
            return None
        e.access_count += 1
        self._total_reads += 1
        return {
            "entry_id": e.entry_id,
            "agent": e.agent,
            "scope": e.scope,
            "data": dict(e.data),
            "ttl_seconds": e.ttl_seconds,
            "access_count": e.access_count,
            "tags": list(e.tags),
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }

    def get_by_agent_scope(self, agent: str, scope: str) -> Optional[Dict[str, Any]]:
        key = f"{agent}:{scope}"
        eid = self._agent_scope_index.get(key)
        if not eid:
            return None
        return self.get_context(eid)

    def remove_context(self, entry_id: str) -> bool:
        e = self._entries.pop(entry_id, None)
        if not e:
            return False
        key = f"{e.agent}:{e.scope}"
        self._agent_scope_index.pop(key, None)
        agent_list = self._agent_index.get(e.agent, [])
        if entry_id in agent_list:
            agent_list.remove(entry_id)
        return True

    # ------------------------------------------------------------------
    # Data operations
    # ------------------------------------------------------------------

    def set_value(self, entry_id: str, key: str, value: Any) -> bool:
        e = self._entries.get(entry_id)
        if not e or not key:
            return False
        if self._is_expired(e):
            self._expire(e)
            return False
        e.data[key] = value
        e.updated_at = time.time()
        self._total_writes += 1
        self._record("set_value", e, {"key": key})
        return True

    def get_value(self, entry_id: str, key: str, default: Any = None) -> Any:
        e = self._entries.get(entry_id)
        if not e:
            return default
        if self._is_expired(e):
            self._expire(e)
            return default
        e.access_count += 1
        self._total_reads += 1
        return e.data.get(key, default)

    def delete_value(self, entry_id: str, key: str) -> bool:
        e = self._entries.get(entry_id)
        if not e or key not in e.data:
            return False
        del e.data[key]
        e.updated_at = time.time()
        return True

    def merge_data(self, entry_id: str, data: Dict[str, Any]) -> bool:
        e = self._entries.get(entry_id)
        if not e:
            return False
        if self._is_expired(e):
            self._expire(e)
            return False
        e.data.update(data)
        e.updated_at = time.time()
        self._total_writes += 1
        return True

    def clear_data(self, entry_id: str) -> bool:
        e = self._entries.get(entry_id)
        if not e:
            return False
        e.data.clear()
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # TTL / Expiry
    # ------------------------------------------------------------------

    def _is_expired(self, entry: _ContextEntry) -> bool:
        if entry.ttl_seconds <= 0:
            return False
        return time.time() - entry.created_at > entry.ttl_seconds

    def _expire(self, entry: _ContextEntry) -> None:
        self._total_expired += 1
        self.remove_context(entry.entry_id)
        self._fire("context_expired", {"entry_id": entry.entry_id, "agent": entry.agent})

    def cleanup_expired(self) -> int:
        expired = []
        for e in list(self._entries.values()):
            if self._is_expired(e):
                expired.append(e)
        for e in expired:
            self._expire(e)
        return len(expired)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_agent_contexts(self, agent: str) -> List[Dict[str, Any]]:
        eids = self._agent_index.get(agent, [])
        results = []
        for eid in list(eids):
            info = self.get_context(eid)
            if info:
                results.append(info)
        return results

    def list_contexts(
        self,
        agent: str = "",
        scope: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in list(self._entries.values()):
            if agent and e.agent != agent:
                continue
            if scope and e.scope != scope:
                continue
            if tag and tag not in e.tags:
                continue
            if self._is_expired(e):
                continue
            results.append(self.get_context(e.entry_id))
        return [r for r in results if r is not None]

    def get_history(self, agent: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for h in reversed(self._history):
            if agent and h.get("agent") != agent:
                continue
            results.append(h)
            if len(results) >= limit:
                break
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record(self, action: str, entry: _ContextEntry, extra: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "action": action,
            "entry_id": entry.entry_id,
            "agent": entry.agent,
            "scope": entry.scope,
            "timestamp": time.time(),
        }
        if extra:
            record.update(extra)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(record)

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
        agents = set()
        for e in self._entries.values():
            agents.add(e.agent)
        return {
            "current_contexts": len(self._entries),
            "total_created": self._total_created,
            "total_reads": self._total_reads,
            "total_writes": self._total_writes,
            "total_expired": self._total_expired,
            "unique_agents": len(agents),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._agent_scope_index.clear()
        self._agent_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_reads = 0
        self._total_writes = 0
        self._total_expired = 0
