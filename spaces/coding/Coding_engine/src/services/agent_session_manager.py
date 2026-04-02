"""Agent session manager - track agent work sessions with state and history."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Session:
    session_id: str
    agent: str
    status: str  # active, paused, completed, failed, expired
    started_at: float
    ended_at: float
    timeout: float  # seconds until auto-expire (0 = no timeout)
    context: Dict[str, Any]
    events: List[Dict]
    tags: List[str]
    metadata: Dict = field(default_factory=dict)


class AgentSessionManager:
    """Manage agent work sessions with context, state tracking, and history."""

    STATUSES = ("active", "paused", "completed", "failed", "expired")

    def __init__(self, max_sessions: int = 10000, max_events_per_session: int = 1000):
        self._max_sessions = max_sessions
        self._max_events = max_events_per_session
        self._sessions: Dict[str, _Session] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_expired": 0,
        }

    # ── Session Lifecycle ──

    def create_session(self, agent: str, timeout: float = 0.0,
                       context: Optional[Dict] = None,
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> str:
        """Create a new session for an agent."""
        if not agent:
            return ""
        if len(self._sessions) >= self._max_sessions:
            return ""

        sid = f"sess-{uuid.uuid4().hex[:10]}"
        self._sessions[sid] = _Session(
            session_id=sid,
            agent=agent,
            status="active",
            started_at=time.time(),
            ended_at=0.0,
            timeout=timeout,
            context=context or {},
            events=[],
            tags=tags or [],
            metadata=metadata or {},
        )
        self._stats["total_created"] += 1
        self._fire_callbacks("session_created", sid)
        return sid

    def get_session(self, session_id: str) -> Optional[Dict]:
        s = self._sessions.get(session_id)
        if not s:
            return None
        self._check_expired(s)
        return {
            "session_id": s.session_id,
            "agent": s.agent,
            "status": s.status,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "duration": (s.ended_at or time.time()) - s.started_at,
            "event_count": len(s.events),
            "tags": list(s.tags),
            "context_keys": list(s.context.keys()),
        }

    def complete_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s or s.status not in ("active", "paused"):
            return False
        s.status = "completed"
        s.ended_at = time.time()
        self._stats["total_completed"] += 1
        self._fire_callbacks("session_completed", session_id)
        return True

    def fail_session(self, session_id: str, reason: str = "") -> bool:
        s = self._sessions.get(session_id)
        if not s or s.status not in ("active", "paused"):
            return False
        s.status = "failed"
        s.ended_at = time.time()
        if reason:
            s.metadata["failure_reason"] = reason
        self._stats["total_failed"] += 1
        self._fire_callbacks("session_failed", session_id)
        return True

    def pause_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s or s.status != "active":
            return False
        s.status = "paused"
        self._fire_callbacks("session_paused", session_id)
        return True

    def resume_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if not s or s.status != "paused":
            return False
        s.status = "active"
        self._fire_callbacks("session_resumed", session_id)
        return True

    def remove_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        return True

    # ── Context Management ──

    def set_context(self, session_id: str, key: str, value: Any) -> bool:
        """Set a context value in a session."""
        s = self._sessions.get(session_id)
        if not s or s.status not in ("active", "paused"):
            return False
        s.context[key] = value
        return True

    def get_context(self, session_id: str, key: str) -> Optional[Any]:
        s = self._sessions.get(session_id)
        if not s:
            return None
        return s.context.get(key)

    def get_all_context(self, session_id: str) -> Dict[str, Any]:
        s = self._sessions.get(session_id)
        if not s:
            return {}
        return dict(s.context)

    def remove_context(self, session_id: str, key: str) -> bool:
        s = self._sessions.get(session_id)
        if not s or key not in s.context:
            return False
        del s.context[key]
        return True

    # ── Session Events ──

    def add_event(self, session_id: str, event_type: str,
                  data: Optional[Dict] = None) -> bool:
        """Add an event to a session's timeline."""
        s = self._sessions.get(session_id)
        if not s or s.status not in ("active", "paused"):
            return False
        if len(s.events) >= self._max_events:
            return False

        s.events.append({
            "event_type": event_type,
            "data": data or {},
            "timestamp": time.time(),
        })
        return True

    def get_events(self, session_id: str, event_type: str = "",
                   limit: int = 50) -> List[Dict]:
        s = self._sessions.get(session_id)
        if not s:
            return []
        result = []
        for e in s.events:
            if event_type and e["event_type"] != event_type:
                continue
            result.append(e)
            if len(result) >= limit:
                break
        return result

    # ── Queries ──

    def list_sessions(self, agent: str = "", status: str = "",
                      tag: str = "") -> List[Dict]:
        result = []
        for s in self._sessions.values():
            self._check_expired(s)
            if agent and s.agent != agent:
                continue
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            result.append({
                "session_id": s.session_id,
                "agent": s.agent,
                "status": s.status,
                "event_count": len(s.events),
                "duration": (s.ended_at or time.time()) - s.started_at,
            })
        return result

    def get_active_sessions(self, agent: str = "") -> List[str]:
        result = []
        for s in self._sessions.values():
            self._check_expired(s)
            if s.status == "active":
                if agent and s.agent != agent:
                    continue
                result.append(s.session_id)
        return result

    def get_agent_sessions(self, agent: str, limit: int = 50) -> List[Dict]:
        result = []
        for s in self._sessions.values():
            if s.agent == agent:
                result.append({
                    "session_id": s.session_id,
                    "status": s.status,
                    "started_at": s.started_at,
                    "duration": (s.ended_at or time.time()) - s.started_at,
                })
                if len(result) >= limit:
                    break
        return result

    def get_agent_active_count(self, agent: str) -> int:
        count = 0
        for s in self._sessions.values():
            self._check_expired(s)
            if s.agent == agent and s.status == "active":
                count += 1
        return count

    # ── Internal ──

    def _check_expired(self, s: _Session) -> None:
        if s.status == "active" and s.timeout > 0:
            elapsed = time.time() - s.started_at
            if elapsed >= s.timeout:
                s.status = "expired"
                s.ended_at = time.time()
                self._stats["total_expired"] += 1

    # ── Callbacks ──

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

    def _fire_callbacks(self, action: str, session_id: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, session_id)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        active = sum(1 for s in self._sessions.values() if s.status == "active")
        return {
            **self._stats,
            "total_sessions": len(self._sessions),
            "active_sessions": active,
        }

    def reset(self) -> None:
        self._sessions.clear()
        self._callbacks.clear()
        self._stats = {k: 0 for k in self._stats}
