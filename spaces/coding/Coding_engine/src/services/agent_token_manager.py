"""Agent Token Manager – manages authentication tokens for agents.

Issues, validates, and revokes tokens.  Supports token expiry,
refresh, and scope-based permissions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Token:
    token_id: str
    agent: str
    token_hash: str
    scopes: Set[str]
    issued_at: float
    expires_at: float
    revoked: bool
    refresh_count: int
    tags: List[str]


@dataclass
class _TokenEvent:
    event_id: str
    agent: str
    action: str  # issued, validated, refreshed, revoked, expired
    timestamp: float


class AgentTokenManager:
    """Manages authentication tokens for agents."""

    def __init__(
        self,
        max_tokens: int = 50000,
        max_history: int = 100000,
        default_ttl: float = 3600.0,
        max_refreshes: int = 10,
    ):
        self._tokens: Dict[str, _Token] = {}
        self._agent_index: Dict[str, List[str]] = {}  # agent -> [token_ids]
        self._history: List[_TokenEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_tokens = max_tokens
        self._max_history = max_history
        self._default_ttl = default_ttl
        self._max_refreshes = max_refreshes
        self._seq = 0

        self._total_issued = 0
        self._total_validated = 0
        self._total_revoked = 0

    def issue_token(
        self,
        agent: str,
        scopes: Optional[List[str]] = None,
        ttl: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent:
            return ""
        if len(self._tokens) >= self._max_tokens:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{now}-{self._seq}"
        tid = "tok-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        token_hash = hashlib.sha256(tid.encode()).hexdigest()[:20]
        ttl_val = ttl if ttl > 0 else self._default_ttl

        token = _Token(
            token_id=tid, agent=agent, token_hash=token_hash,
            scopes=set(scopes or []), issued_at=now,
            expires_at=now + ttl_val, revoked=False,
            refresh_count=0, tags=tags or [],
        )
        self._tokens[tid] = token
        self._agent_index.setdefault(agent, []).append(tid)
        self._total_issued += 1
        self._record_event(agent, "issued")
        self._fire("token_issued", {"token_id": tid, "agent": agent})
        return tid

    def validate_token(self, token_id: str, required_scope: str = "") -> Dict[str, Any]:
        token = self._tokens.get(token_id)
        if not token:
            return {"valid": False, "reason": "not_found"}
        if token.revoked:
            return {"valid": False, "reason": "revoked"}
        if time.time() >= token.expires_at:
            return {"valid": False, "reason": "expired"}
        if required_scope and required_scope not in token.scopes:
            return {"valid": False, "reason": "insufficient_scope"}

        self._total_validated += 1
        self._record_event(token.agent, "validated")
        return {"valid": True, "agent": token.agent, "scopes": sorted(token.scopes)}

    def refresh_token(self, token_id: str, ttl: float = 0.0) -> bool:
        token = self._tokens.get(token_id)
        if not token or token.revoked:
            return False
        if time.time() >= token.expires_at:
            return False
        if token.refresh_count >= self._max_refreshes:
            return False

        ttl_val = ttl if ttl > 0 else self._default_ttl
        token.expires_at = time.time() + ttl_val
        token.refresh_count += 1
        self._record_event(token.agent, "refreshed")
        self._fire("token_refreshed", {"token_id": token_id, "agent": token.agent})
        return True

    def revoke_token(self, token_id: str) -> bool:
        token = self._tokens.get(token_id)
        if not token or token.revoked:
            return False
        token.revoked = True
        self._total_revoked += 1
        self._record_event(token.agent, "revoked")
        self._fire("token_revoked", {"token_id": token_id, "agent": token.agent})
        return True

    def revoke_agent_tokens(self, agent: str) -> int:
        tids = self._agent_index.get(agent, [])
        count = 0
        for tid in tids:
            if self.revoke_token(tid):
                count += 1
        return count

    def get_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        t = self._tokens.get(token_id)
        if not t:
            return None
        now = time.time()
        return {
            "token_id": t.token_id, "agent": t.agent,
            "scopes": sorted(t.scopes), "issued_at": t.issued_at,
            "expires_at": t.expires_at, "revoked": t.revoked,
            "remaining": max(0.0, t.expires_at - now),
            "refresh_count": t.refresh_count, "tags": list(t.tags),
        }

    def get_agent_tokens(self, agent: str) -> List[Dict[str, Any]]:
        tids = self._agent_index.get(agent, [])
        return [self.get_token(tid) for tid in tids if self.get_token(tid)]

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [tid for tid, t in self._tokens.items() if now >= t.expires_at and not t.revoked]
        for tid in expired:
            self._tokens[tid].revoked = True
            self._record_event(self._tokens[tid].agent, "expired")
        return len(expired)

    def list_tokens(self, agent: str = "", active_only: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        results = []
        for t in self._tokens.values():
            if agent and t.agent != agent:
                continue
            if active_only and (t.revoked or now >= t.expires_at):
                continue
            results.append(self.get_token(t.token_id))
        return [r for r in results if r]

    def get_history(self, agent: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if agent and ev.agent != agent:
                continue
            if action and ev.action != action:
                continue
            results.append({"event_id": ev.event_id, "agent": ev.agent, "action": ev.action, "timestamp": ev.timestamp})
            if len(results) >= limit:
                break
        return results

    def _record_event(self, agent: str, action: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{agent}-{action}-{now}-{self._seq}"
        evid = "tkev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _TokenEvent(event_id=evid, agent=agent, action=action, timestamp=now)
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for t in self._tokens.values() if not t.revoked and now < t.expires_at)
        return {
            "current_tokens": len(self._tokens),
            "active_tokens": active,
            "total_issued": self._total_issued,
            "total_validated": self._total_validated,
            "total_revoked": self._total_revoked,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._tokens.clear()
        self._agent_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_issued = 0
        self._total_validated = 0
        self._total_revoked = 0
