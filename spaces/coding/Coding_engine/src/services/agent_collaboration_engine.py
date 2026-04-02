"""Agent Collaboration Engine – manages collaborative sessions between agents.

Supports creating collaboration sessions, adding participants,
sharing artifacts, voting on decisions, and tracking session outcomes.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Session:
    session_id: str
    name: str
    topic: str
    status: str  # active | paused | completed | cancelled
    participants: List[str]
    max_participants: int
    tags: List[str]
    created_at: float
    updated_at: float
    seq: int


@dataclass
class _Artifact:
    artifact_id: str
    session_id: str
    name: str
    content: str
    author: str
    artifact_type: str  # code | doc | decision | note
    created_at: float
    seq: int


@dataclass
class _Vote:
    vote_id: str
    session_id: str
    proposal: str
    voter: str
    choice: str  # approve | reject | abstain
    reason: str
    created_at: float
    seq: int


class AgentCollaborationEngine:
    """Manages collaborative sessions between multiple agents."""

    STATUSES = ("active", "paused", "completed", "cancelled")
    ARTIFACT_TYPES = ("code", "doc", "decision", "note")
    VOTE_CHOICES = ("approve", "reject", "abstain")

    def __init__(self, max_sessions: int = 10000,
                 max_artifacts: int = 200000,
                 max_votes: int = 200000) -> None:
        self._max_sessions = max_sessions
        self._max_artifacts = max_artifacts
        self._max_votes = max_votes
        self._sessions: Dict[str, _Session] = {}
        self._artifacts: Dict[str, _Artifact] = {}
        self._votes: Dict[str, _Vote] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_sessions": 0,
            "total_artifacts": 0,
            "total_votes": 0,
            "total_completed": 0,
        }

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, name: str, topic: str = "",
                       max_participants: int = 20,
                       tags: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if len(self._sessions) >= self._max_sessions:
            return ""
        self._seq += 1
        raw = f"collab-{name}-{self._seq}-{len(self._sessions)}"
        sid = "collab-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        s = _Session(
            session_id=sid, name=name, topic=topic, status="active",
            participants=[], max_participants=max_participants,
            tags=list(tags or []),
            created_at=time.time(), updated_at=time.time(), seq=self._seq,
        )
        self._sessions[sid] = s
        self._stats["total_sessions"] += 1
        self._fire("session_created", {"session_id": sid, "name": name})
        return sid

    def get_session(self, session_id: str) -> Optional[Dict]:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        return self._s_to_dict(s)

    def remove_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        # Cascade
        to_rm_a = [a for a in self._artifacts.values() if a.session_id == session_id]
        for a in to_rm_a:
            del self._artifacts[a.artifact_id]
        to_rm_v = [v for v in self._votes.values() if v.session_id == session_id]
        for v in to_rm_v:
            del self._votes[v.vote_id]
        return True

    def join_session(self, session_id: str, agent: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status != "active":
            return False
        if agent in s.participants:
            return False
        if len(s.participants) >= s.max_participants:
            return False
        s.participants.append(agent)
        s.updated_at = time.time()
        self._fire("agent_joined", {"session_id": session_id, "agent": agent})
        return True

    def leave_session(self, session_id: str, agent: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or agent not in s.participants:
            return False
        s.participants.remove(agent)
        s.updated_at = time.time()
        return True

    def pause_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status != "active":
            return False
        s.status = "paused"
        s.updated_at = time.time()
        return True

    def resume_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status != "paused":
            return False
        s.status = "active"
        s.updated_at = time.time()
        return True

    def complete_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status not in ("active", "paused"):
            return False
        s.status = "completed"
        s.updated_at = time.time()
        self._stats["total_completed"] += 1
        self._fire("session_completed", {"session_id": session_id})
        return True

    def cancel_session(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status not in ("active", "paused"):
            return False
        s.status = "cancelled"
        s.updated_at = time.time()
        return True

    def search_sessions(self, status: str = "", tag: str = "",
                        participant: str = "") -> List[Dict]:
        results = []
        for s in self._sessions.values():
            if status and s.status != status:
                continue
            if tag and tag not in s.tags:
                continue
            if participant and participant not in s.participants:
                continue
            results.append(self._s_to_dict(s))
        results.sort(key=lambda x: x["seq"])
        return results

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def share_artifact(self, session_id: str, name: str, content: str,
                       author: str = "", artifact_type: str = "note") -> str:
        s = self._sessions.get(session_id)
        if s is None:
            return ""
        if not name:
            return ""
        if artifact_type not in self.ARTIFACT_TYPES:
            return ""
        if len(self._artifacts) >= self._max_artifacts:
            return ""
        self._seq += 1
        raw = f"art-{session_id}-{name}-{self._seq}-{len(self._artifacts)}"
        aid = "art-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        a = _Artifact(
            artifact_id=aid, session_id=session_id, name=name,
            content=content, author=author, artifact_type=artifact_type,
            created_at=time.time(), seq=self._seq,
        )
        self._artifacts[aid] = a
        self._stats["total_artifacts"] += 1
        self._fire("artifact_shared", {"artifact_id": aid, "session_id": session_id})
        return aid

    def get_artifact(self, artifact_id: str) -> Optional[Dict]:
        a = self._artifacts.get(artifact_id)
        if a is None:
            return None
        return self._a_to_dict(a)

    def get_session_artifacts(self, session_id: str,
                               artifact_type: str = "") -> List[Dict]:
        results = []
        for a in self._artifacts.values():
            if a.session_id != session_id:
                continue
            if artifact_type and a.artifact_type != artifact_type:
                continue
            results.append(self._a_to_dict(a))
        results.sort(key=lambda x: x["seq"])
        return results

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def cast_vote(self, session_id: str, proposal: str, voter: str,
                  choice: str = "approve", reason: str = "") -> str:
        s = self._sessions.get(session_id)
        if s is None or s.status != "active":
            return ""
        if choice not in self.VOTE_CHOICES:
            return ""
        if not proposal or not voter:
            return ""
        # Check duplicate vote
        for v in self._votes.values():
            if v.session_id == session_id and v.proposal == proposal and v.voter == voter:
                return ""
        if len(self._votes) >= self._max_votes:
            return ""
        self._seq += 1
        raw = f"vote-{session_id}-{proposal}-{voter}-{self._seq}-{len(self._votes)}"
        vid = "vote-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        v = _Vote(
            vote_id=vid, session_id=session_id, proposal=proposal,
            voter=voter, choice=choice, reason=reason,
            created_at=time.time(), seq=self._seq,
        )
        self._votes[vid] = v
        self._stats["total_votes"] += 1
        self._fire("vote_cast", {"vote_id": vid, "session_id": session_id})
        return vid

    def get_vote_results(self, session_id: str, proposal: str) -> Dict:
        approve = 0
        reject = 0
        abstain = 0
        for v in self._votes.values():
            if v.session_id != session_id or v.proposal != proposal:
                continue
            if v.choice == "approve":
                approve += 1
            elif v.choice == "reject":
                reject += 1
            else:
                abstain += 1
        total = approve + reject + abstain
        return {
            "proposal": proposal,
            "approve": approve,
            "reject": reject,
            "abstain": abstain,
            "total_votes": total,
            "approved": approve > reject,
        }

    def get_session_votes(self, session_id: str) -> List[Dict]:
        results = []
        for v in self._votes.values():
            if v.session_id != session_id:
                continue
            results.append(self._v_to_dict(v))
        results.sort(key=lambda x: x["seq"])
        return results

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
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
            "current_sessions": len(self._sessions),
            "current_artifacts": len(self._artifacts),
            "current_votes": len(self._votes),
            "active_sessions": sum(1 for s in self._sessions.values() if s.status == "active"),
        }

    def reset(self) -> None:
        self._sessions.clear()
        self._artifacts.clear()
        self._votes.clear()
        self._seq = 0
        self._stats = {
            "total_sessions": 0,
            "total_artifacts": 0,
            "total_votes": 0,
            "total_completed": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _s_to_dict(s: _Session) -> Dict:
        return {
            "session_id": s.session_id,
            "name": s.name,
            "topic": s.topic,
            "status": s.status,
            "participants": list(s.participants),
            "max_participants": s.max_participants,
            "tags": list(s.tags),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "seq": s.seq,
        }

    @staticmethod
    def _a_to_dict(a: _Artifact) -> Dict:
        return {
            "artifact_id": a.artifact_id,
            "session_id": a.session_id,
            "name": a.name,
            "content": a.content,
            "author": a.author,
            "artifact_type": a.artifact_type,
            "created_at": a.created_at,
            "seq": a.seq,
        }

    @staticmethod
    def _v_to_dict(v: _Vote) -> Dict:
        return {
            "vote_id": v.vote_id,
            "session_id": v.session_id,
            "proposal": v.proposal,
            "voter": v.voter,
            "choice": v.choice,
            "reason": v.reason,
            "created_at": v.created_at,
            "seq": v.seq,
        }
