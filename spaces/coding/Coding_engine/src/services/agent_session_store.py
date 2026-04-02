"""Agent Session Store – manages agent sessions (login/logout, tracking, expiry).

Provides creation, retrieval, refresh, and expiry-based pruning of agent
sessions.  Each session tracks its agent, timestamps, status, metadata,
and tags.  Supports active-session queries, duration calculation, and
configurable entry limits with automatic pruning.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SessionEntry:
    """A single agent session record."""

    session_id: str = ""
    agent_id: str = ""
    created_at: float = 0.0
    last_active: float = 0.0
    status: str = "active"  # active, ended
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class _StoreState:
    """Internal mutable state for the session store."""

    entries: Dict[str, SessionEntry] = field(default_factory=dict)
    # agent_id -> list of session_ids (chronological)
    agent_index: Dict[str, List[str]] = field(default_factory=dict)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    seq: int = 0
    total_created: int = 0
    total_ended: int = 0
    total_expired: int = 0
    total_refreshed: int = 0


class AgentSessionStore:
    """Manages agent sessions with login/logout, tracking, and expiry."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._state = _StoreState()
        logger.info("agent_session_store.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str) -> str:
        """Generate a collision-free session ID using SHA256 + seq counter."""
        self._state.seq += 1
        now = time.time()
        raw = f"{agent_id}-{now}-{self._state.seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"ass-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest ended sessions when at capacity."""
        if len(self._state.entries) < self._max_entries:
            return

        ended = [
            (sid, entry)
            for sid, entry in self._state.entries.items()
            if entry.status == "ended"
        ]
        ended.sort(key=lambda x: x[1].created_at)

        to_remove = len(ended) // 4 or 1
        for sid, entry in ended[:to_remove]:
            self._remove_from_index(entry.agent_id, sid)
            del self._state.entries[sid]

        logger.debug(
            "agent_session_store.pruned",
            removed=min(to_remove, len(ended)),
            remaining=len(self._state.entries),
        )

    def _remove_from_index(self, agent_id: str, session_id: str) -> None:
        """Remove a session ID from the agent index."""
        sids = self._state.agent_index.get(agent_id)
        if sids is None:
            return
        try:
            sids.remove(session_id)
        except ValueError:
            pass
        if not sids:
            del self._state.agent_index[agent_id]

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(
        self,
        agent_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new session for an agent.

        Returns the generated session_id, or empty string on invalid input.
        """
        if not agent_id:
            logger.warning("agent_session_store.create_session.missing_agent_id")
            return ""

        self._prune_if_needed()

        now = time.time()
        sid = self._generate_id(agent_id)

        entry = SessionEntry(
            session_id=sid,
            agent_id=agent_id,
            created_at=now,
            last_active=now,
            status="active",
            metadata=metadata or {},
            tags=list(tags) if tags else [],
        )

        self._state.entries[sid] = entry
        self._state.agent_index.setdefault(agent_id, []).append(sid)
        self._state.total_created += 1

        logger.info(
            "agent_session_store.session_created",
            session_id=sid,
            agent_id=agent_id,
        )
        self._fire("session_created", {
            "session_id": sid,
            "agent_id": agent_id,
        })
        return sid

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details as a dict, or None if not found."""
        entry = self._state.entries.get(session_id)
        if entry is None:
            return None
        return self._entry_to_dict(entry)

    def end_session(self, session_id: str) -> bool:
        """End an active session.  Returns True on success."""
        entry = self._state.entries.get(session_id)
        if entry is None:
            logger.warning(
                "agent_session_store.end_session.not_found",
                session_id=session_id,
            )
            return False

        if entry.status != "active":
            logger.warning(
                "agent_session_store.end_session.already_ended",
                session_id=session_id,
            )
            return False

        entry.status = "ended"
        entry.last_active = time.time()
        self._state.total_ended += 1

        logger.info(
            "agent_session_store.session_ended",
            session_id=session_id,
            agent_id=entry.agent_id,
            duration=round(entry.last_active - entry.created_at, 2),
        )
        self._fire("session_ended", {
            "session_id": session_id,
            "agent_id": entry.agent_id,
        })
        return True

    def refresh_session(self, session_id: str) -> bool:
        """Update last_active timestamp for a session.  Returns True on success."""
        entry = self._state.entries.get(session_id)
        if entry is None:
            logger.warning(
                "agent_session_store.refresh.not_found",
                session_id=session_id,
            )
            return False

        if entry.status != "active":
            logger.warning(
                "agent_session_store.refresh.not_active",
                session_id=session_id,
            )
            return False

        entry.last_active = time.time()
        self._state.total_refreshed += 1

        logger.debug(
            "agent_session_store.session_refreshed",
            session_id=session_id,
        )
        self._fire("session_refreshed", {
            "session_id": session_id,
            "agent_id": entry.agent_id,
        })
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_sessions(
        self, agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all active sessions, optionally filtered by agent_id."""
        results: List[Dict[str, Any]] = []

        if agent_id is not None:
            sids = self._state.agent_index.get(agent_id, [])
            for sid in sids:
                entry = self._state.entries.get(sid)
                if entry and entry.status == "active":
                    results.append(self._entry_to_dict(entry))
        else:
            for entry in self._state.entries.values():
                if entry.status == "active":
                    results.append(self._entry_to_dict(entry))

        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    def get_session_duration(self, session_id: str) -> float:
        """Get the duration of a session in seconds.

        For active sessions, returns time elapsed since creation.
        For ended sessions, returns total session time.
        Returns 0.0 if session not found.
        """
        entry = self._state.entries.get(session_id)
        if entry is None:
            return 0.0
        return self._calc_duration(entry)

    def list_agents_with_sessions(self) -> List[str]:
        """Return sorted list of agent IDs that have at least one session."""
        return sorted(self._state.agent_index.keys())

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    def purge_expired(self, max_age_seconds: float = 3600) -> int:
        """Remove sessions whose last_active exceeds max_age_seconds.

        Only purges sessions with status 'active' that have gone stale.
        Ended sessions are left for historical queries (pruned by capacity).
        Returns the number of sessions removed.
        """
        now = time.time()
        cutoff = now - max_age_seconds
        to_remove: List[str] = []

        for sid, entry in self._state.entries.items():
            if entry.last_active < cutoff:
                to_remove.append(sid)

        for sid in to_remove:
            entry = self._state.entries[sid]
            self._remove_from_index(entry.agent_id, sid)
            del self._state.entries[sid]

        removed = len(to_remove)
        if removed > 0:
            self._state.total_expired += removed
            logger.info(
                "agent_session_store.purge_expired",
                removed=removed,
                max_age_seconds=max_age_seconds,
            )
            self._fire("sessions_purged", {
                "count": removed,
                "max_age_seconds": max_age_seconds,
            })

        return removed

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback by name."""
        if name in self._state.callbacks:
            logger.warning(
                "agent_session_store.on_change.duplicate",
                name=name,
            )
        self._state.callbacks[name] = callback
        logger.debug("agent_session_store.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.  Returns True if it existed."""
        if name not in self._state.callbacks:
            return False
        del self._state.callbacks[name]
        logger.debug("agent_session_store.callback_removed", name=name)
        return True

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and data."""
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception(
                    "agent_session_store.callback_error",
                    callback=cb_name,
                    action=action,
                )

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        active_count = sum(
            1 for e in self._state.entries.values() if e.status == "active"
        )
        ended_count = sum(
            1 for e in self._state.entries.values() if e.status == "ended"
        )
        return {
            "total_created": self._state.total_created,
            "total_ended": self._state.total_ended,
            "total_expired": self._state.total_expired,
            "total_refreshed": self._state.total_refreshed,
            "current_entries": len(self._state.entries),
            "active_sessions": active_count,
            "ended_sessions": ended_count,
            "registered_agents": len(self._state.agent_index),
            "registered_callbacks": len(self._state.callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all sessions, indexes, callbacks, and counters."""
        self._state = _StoreState()
        logger.info("agent_session_store.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: SessionEntry) -> Dict[str, Any]:
        """Convert a SessionEntry dataclass to a plain dict."""
        return {
            "session_id": entry.session_id,
            "agent_id": entry.agent_id,
            "created_at": entry.created_at,
            "last_active": entry.last_active,
            "status": entry.status,
            "metadata": dict(entry.metadata),
            "tags": list(entry.tags),
            "duration": round(self._calc_duration(entry), 2),
        }

    def _calc_duration(self, entry: SessionEntry) -> float:
        """Calculate session duration in seconds."""
        if entry.status == "ended":
            return entry.last_active - entry.created_at
        return time.time() - entry.created_at
