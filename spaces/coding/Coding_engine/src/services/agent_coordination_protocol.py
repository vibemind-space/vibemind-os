"""
Agent Coordination Protocol — manages multi-agent coordination with locks, barriers, and elections.

Features:
- Distributed locking (mutex) for resource coordination
- Barriers for synchronization points
- Leader election among agent groups
- Coordination sessions with join/leave
- Lock timeout and automatic release
- Coordination event history
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Lock:
    """A distributed lock."""
    name: str
    holder: str  # agent name
    acquired_at: float
    timeout_seconds: float  # 0 = no timeout
    metadata: Dict[str, Any]


@dataclass
class Barrier:
    """A synchronization barrier."""
    name: str
    required: int
    arrived: Set[str]  # agent names
    released: bool
    created_at: float
    released_at: float


@dataclass
class CoordinationSession:
    """A multi-agent coordination session."""
    session_id: str
    name: str
    leader: str
    members: Set[str]
    status: str  # "active", "completed", "cancelled"
    created_at: float
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Agent Coordination Protocol
# ---------------------------------------------------------------------------

class AgentCoordinationProtocol:
    """Manages multi-agent coordination primitives."""

    def __init__(
        self,
        default_lock_timeout: float = 60.0,
        max_locks: int = 1000,
        max_barriers: int = 500,
        max_sessions: int = 500,
    ):
        self._default_lock_timeout = default_lock_timeout
        self._max_locks = max_locks
        self._max_barriers = max_barriers
        self._max_sessions = max_sessions

        self._locks: Dict[str, Lock] = {}
        self._barriers: Dict[str, Barrier] = {}
        self._sessions: Dict[str, CoordinationSession] = {}

        self._stats = {
            "total_locks_acquired": 0,
            "total_locks_released": 0,
            "total_lock_failures": 0,
            "total_barriers_created": 0,
            "total_barriers_released": 0,
            "total_sessions_created": 0,
            "total_elections": 0,
        }

    # ------------------------------------------------------------------
    # Locks
    # ------------------------------------------------------------------

    def acquire_lock(
        self,
        name: str,
        holder: str,
        timeout_seconds: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Acquire a named lock. Returns False if already held."""
        # Check and release expired locks
        self._check_lock_timeout(name)

        if name in self._locks:
            self._stats["total_lock_failures"] += 1
            return False

        self._locks[name] = Lock(
            name=name,
            holder=holder,
            acquired_at=time.time(),
            timeout_seconds=timeout_seconds or self._default_lock_timeout,
            metadata=metadata or {},
        )
        self._stats["total_locks_acquired"] += 1
        return True

    def release_lock(self, name: str, holder: str) -> bool:
        """Release a lock. Only the holder can release."""
        lock = self._locks.get(name)
        if not lock:
            return False
        if lock.holder != holder:
            return False
        del self._locks[name]
        self._stats["total_locks_released"] += 1
        return True

    def force_release_lock(self, name: str) -> bool:
        """Force release a lock regardless of holder."""
        if name not in self._locks:
            return False
        del self._locks[name]
        self._stats["total_locks_released"] += 1
        return True

    def get_lock(self, name: str) -> Optional[Dict]:
        """Get lock info."""
        self._check_lock_timeout(name)
        lock = self._locks.get(name)
        if not lock:
            return None
        return {
            "name": lock.name,
            "holder": lock.holder,
            "acquired_at": lock.acquired_at,
            "timeout_seconds": lock.timeout_seconds,
            "held_seconds": round(time.time() - lock.acquired_at, 2),
            "metadata": lock.metadata,
        }

    def is_locked(self, name: str) -> bool:
        """Check if a lock is held."""
        self._check_lock_timeout(name)
        return name in self._locks

    def list_locks(self, holder: Optional[str] = None) -> List[Dict]:
        """List all active locks."""
        self._cleanup_expired_locks()
        results = []
        for lock in self._locks.values():
            if holder and lock.holder != holder:
                continue
            results.append({
                "name": lock.name,
                "holder": lock.holder,
                "acquired_at": lock.acquired_at,
                "held_seconds": round(time.time() - lock.acquired_at, 2),
            })
        return results

    def _check_lock_timeout(self, name: str) -> None:
        """Release lock if timed out."""
        lock = self._locks.get(name)
        if lock and lock.timeout_seconds > 0:
            if time.time() - lock.acquired_at >= lock.timeout_seconds:
                del self._locks[name]

    def _cleanup_expired_locks(self) -> None:
        """Remove all expired locks."""
        now = time.time()
        expired = [
            name for name, lock in self._locks.items()
            if lock.timeout_seconds > 0 and now - lock.acquired_at >= lock.timeout_seconds
        ]
        for name in expired:
            del self._locks[name]

    # ------------------------------------------------------------------
    # Barriers
    # ------------------------------------------------------------------

    def create_barrier(self, name: str, required: int) -> bool:
        """Create a synchronization barrier."""
        if name in self._barriers:
            return False
        if required < 1:
            return False
        self._barriers[name] = Barrier(
            name=name,
            required=required,
            arrived=set(),
            released=False,
            created_at=time.time(),
            released_at=0.0,
        )
        self._stats["total_barriers_created"] += 1
        return True

    def arrive_at_barrier(self, name: str, agent: str) -> Dict:
        """Agent arrives at barrier. Returns status."""
        barrier = self._barriers.get(name)
        if not barrier:
            return {"arrived": False, "reason": "barrier_not_found"}
        if barrier.released:
            return {"arrived": True, "released": True, "was_already_released": True}

        barrier.arrived.add(agent)

        if len(barrier.arrived) >= barrier.required:
            barrier.released = True
            barrier.released_at = time.time()
            self._stats["total_barriers_released"] += 1
            return {"arrived": True, "released": True, "agents": list(barrier.arrived)}

        return {
            "arrived": True,
            "released": False,
            "waiting_count": barrier.required - len(barrier.arrived),
        }

    def get_barrier(self, name: str) -> Optional[Dict]:
        """Get barrier info."""
        barrier = self._barriers.get(name)
        if not barrier:
            return None
        return {
            "name": barrier.name,
            "required": barrier.required,
            "arrived_count": len(barrier.arrived),
            "arrived": list(barrier.arrived),
            "released": barrier.released,
            "created_at": barrier.created_at,
            "released_at": barrier.released_at,
        }

    def remove_barrier(self, name: str) -> bool:
        """Remove a barrier."""
        if name not in self._barriers:
            return False
        del self._barriers[name]
        return True

    def list_barriers(self, released: Optional[bool] = None) -> List[Dict]:
        """List barriers."""
        results = []
        for b in self._barriers.values():
            if released is not None and b.released != released:
                continue
            results.append({
                "name": b.name,
                "required": b.required,
                "arrived_count": len(b.arrived),
                "released": b.released,
            })
        return results

    # ------------------------------------------------------------------
    # Coordination sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        name: str,
        creator: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a coordination session. Creator is initial leader."""
        session_id = f"cs-{uuid.uuid4().hex[:8]}"
        self._sessions[session_id] = CoordinationSession(
            session_id=session_id,
            name=name,
            leader=creator,
            members={creator},
            status="active",
            created_at=time.time(),
            metadata=metadata or {},
        )
        self._stats["total_sessions_created"] += 1
        return session_id

    def join_session(self, session_id: str, agent: str) -> bool:
        """Join a session."""
        session = self._sessions.get(session_id)
        if not session or session.status != "active":
            return False
        session.members.add(agent)
        return True

    def leave_session(self, session_id: str, agent: str) -> bool:
        """Leave a session."""
        session = self._sessions.get(session_id)
        if not session or agent not in session.members:
            return False
        session.members.discard(agent)

        # If leader leaves, elect new one
        if agent == session.leader and session.members:
            session.leader = min(session.members)  # Deterministic selection

        if not session.members:
            session.status = "completed"

        return True

    def complete_session(self, session_id: str) -> bool:
        """Complete a session."""
        session = self._sessions.get(session_id)
        if not session or session.status != "active":
            return False
        session.status = "completed"
        return True

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a session."""
        session = self._sessions.get(session_id)
        if not session or session.status != "active":
            return False
        session.status = "cancelled"
        return True

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session info."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "name": session.name,
            "leader": session.leader,
            "members": list(session.members),
            "member_count": len(session.members),
            "status": session.status,
            "created_at": session.created_at,
            "metadata": session.metadata,
        }

    def list_sessions(self, status: Optional[str] = None) -> List[Dict]:
        """List sessions."""
        results = []
        for s in self._sessions.values():
            if status and s.status != status:
                continue
            results.append({
                "session_id": s.session_id,
                "name": s.name,
                "leader": s.leader,
                "member_count": len(s.members),
                "status": s.status,
            })
        return results

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    def elect_leader(self, session_id: str) -> Optional[str]:
        """Elect a new leader for a session (simple: lowest name)."""
        session = self._sessions.get(session_id)
        if not session or not session.members or session.status != "active":
            return None
        session.leader = min(session.members)
        self._stats["total_elections"] += 1
        return session.leader

    def get_leader(self, session_id: str) -> Optional[str]:
        """Get current leader."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        return session.leader

    def is_leader(self, session_id: str, agent: str) -> bool:
        """Check if agent is leader."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        return session.leader == agent

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_active_locks": len(self._locks),
            "total_barriers": len(self._barriers),
            "total_sessions": len(self._sessions),
            "active_sessions": sum(1 for s in self._sessions.values() if s.status == "active"),
        }

    def reset(self) -> None:
        self._locks.clear()
        self._barriers.clear()
        self._sessions.clear()
        self._stats = {k: 0 for k in self._stats}
