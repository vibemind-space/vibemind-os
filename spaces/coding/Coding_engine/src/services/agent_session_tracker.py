"""Agent Session Tracker – tracks active agent sessions with start/end times and metadata.

Provides session lifecycle management including starting, ending, and querying
sessions.  Each session records its agent, type, timestamps, status, and
arbitrary metadata.  Supports filtering by agent and computing durations.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _SessionEntry:
    """A single tracked agent session."""

    session_id: str = ""
    agent_id: str = ""
    session_type: str = "default"
    status: str = "active"  # active, ended
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


class AgentSessionTracker:
    """Tracks active agent sessions with start/end times and metadata."""

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _SessionEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max_entries

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str) -> str:
        raw = f"{agent_id}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"ast2-{digest}"

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        agent_id: str,
        session_type: str = "default",
        metadata: Optional[Dict] = None,
    ) -> str:
        """Start a new session for an agent. Returns the session ID."""
        if not agent_id:
            return ""
        if len(self._entries) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()
        sid = self._generate_id(agent_id)

        entry = _SessionEntry(
            session_id=sid,
            agent_id=agent_id,
            session_type=session_type,
            status="active",
            metadata=metadata or {},
            started_at=now,
            ended_at=0.0,
            created_at=now,
            seq=self._seq,
        )
        self._entries[sid] = entry
        self._fire("session_started", {"session_id": sid, "agent_id": agent_id})
        return sid

    def end_session(self, session_id: str) -> bool:
        """End a session (set status to 'ended' and record ended_at)."""
        entry = self._entries.get(session_id)
        if not entry or entry.status != "active":
            return False

        self._seq += 1
        entry.status = "ended"
        entry.ended_at = time.time()
        entry.seq = self._seq
        self._fire("session_ended", {"session_id": session_id, "agent_id": entry.agent_id})
        return True

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get a session by its ID."""
        entry = self._entries.get(session_id)
        if not entry:
            return None
        return asdict(entry)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_sessions(self, agent_id: str = "") -> List[Dict]:
        """Get active sessions, optionally filtered by agent_id."""
        results: List[Dict] = []
        for entry in self._entries.values():
            if entry.status != "active":
                continue
            if agent_id and entry.agent_id != agent_id:
                continue
            results.append(asdict(entry))
        results.sort(key=lambda x: -x["started_at"])
        return results

    def get_session_duration(self, session_id: str) -> float:
        """Get session duration in seconds. Returns 0.0 if session not found or not ended."""
        entry = self._entries.get(session_id)
        if not entry:
            return 0.0
        if entry.status != "ended" or entry.ended_at <= 0.0:
            return 0.0
        return entry.ended_at - entry.started_at

    def get_agent_sessions(self, agent_id: str) -> List[Dict]:
        """Get all sessions (active and ended) for a given agent."""
        results: List[Dict] = []
        for entry in self._entries.values():
            if entry.agent_id != agent_id:
                continue
            results.append(asdict(entry))
        results.sort(key=lambda x: -x["started_at"])
        return results

    def list_agents(self) -> List[str]:
        """List all distinct agent IDs that have sessions."""
        return sorted({entry.agent_id for entry in self._entries.values()})

    def get_session_count(self) -> int:
        """Return total number of tracked sessions."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
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
        """Return tracker statistics."""
        active = sum(1 for e in self._entries.values() if e.status == "active")
        ended = sum(1 for e in self._entries.values() if e.status == "ended")
        return {
            "total_sessions": len(self._entries),
            "active_sessions": active,
            "ended_sessions": ended,
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all sessions and reset state."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest ended sessions when at capacity."""
        ended = [
            (sid, e) for sid, e in self._entries.items() if e.status == "ended"
        ]
        ended.sort(key=lambda x: x[1].started_at)
        to_remove = len(ended) // 4 or 1
        for sid, _ in ended[:to_remove]:
            del self._entries[sid]
