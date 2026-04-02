"""Agent Token Refresh -- manages agent authentication token refresh/rotation.

Tracks per-agent authentication tokens with TTL-based expiry.  Supports
registering tokens, checking expiry, refreshing with new values, and
notifying listeners on changes.

Usage::

    svc = AgentTokenRefresh()
    tid = svc.register_token("planner", "secret-abc", ttl_seconds=1800.0)
    token = svc.get_token("planner")
    if svc.is_expired("planner"):
        svc.refresh_token("planner", "secret-xyz")
    stats = svc.get_stats()
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data model
# ======================================================================

@dataclass
class _TokenEntry:
    """State for a single agent's refresh-managed token."""

    entry_id: str
    agent_id: str
    token: str
    ttl_seconds: float
    created_at: float
    expires_at: float
    refresh_count: int
    seq: int = 0


# ======================================================================
# Service
# ======================================================================

class AgentTokenRefresh:
    """Manages agent authentication token refresh and rotation."""

    def __init__(
        self,
        max_entries: int = 50000,
        default_ttl: float = 3600.0,
    ):
        self._tokens: Dict[str, _TokenEntry] = {}      # agent_id -> entry
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries
        self._default_ttl: float = default_ttl

        self._total_registered: int = 0
        self._total_refreshed: int = 0
        self._total_expired_checks: int = 0

        logger.debug("AgentTokenRefresh initialised max_entries=%d", max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, agent_id: str) -> str:
        self._seq += 1
        now = time.time()
        raw = f"{agent_id}-{now}-{self._seq}"
        return "atrf-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_token(
        self,
        agent_id: str,
        token: str,
        ttl_seconds: float = 3600.0,
    ) -> str:
        """Register a token for *agent_id* with a TTL.  Returns entry ID."""

        if not agent_id or not token:
            logger.warning("register_token called with empty agent_id or token")
            return ""
        if len(self._tokens) >= self._max_entries and agent_id not in self._tokens:
            logger.warning("max_entries reached, cannot register token for %s", agent_id)
            return ""

        now = time.time()
        ttl = ttl_seconds if ttl_seconds > 0 else self._default_ttl
        entry_id = self._next_id(agent_id)

        entry = _TokenEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            token=token,
            ttl_seconds=ttl,
            created_at=now,
            expires_at=now + ttl,
            refresh_count=0,
            seq=self._seq,
        )
        self._tokens[agent_id] = entry
        self._total_registered += 1

        logger.debug("registered token %s for agent %s ttl=%.1f", entry_id, agent_id, ttl)
        self._fire("token_registered", {"entry_id": entry_id, "agent_id": agent_id})
        return entry_id

    def get_token(self, agent_id: str) -> Optional[str]:
        """Return the current token for *agent_id*, or ``None``."""

        entry = self._tokens.get(agent_id)
        if entry is None:
            return None
        return entry.token

    def is_expired(self, agent_id: str) -> bool:
        """Return ``True`` if the token for *agent_id* has expired."""

        self._total_expired_checks += 1
        entry = self._tokens.get(agent_id)
        if entry is None:
            return True
        return time.time() >= entry.expires_at

    def refresh_token(self, agent_id: str, new_token: str) -> bool:
        """Replace the token for *agent_id* with *new_token*.

        Resets the TTL to the original value.  Returns ``False`` if the
        agent has no registered token or *new_token* is empty.
        """

        if not new_token:
            return False
        entry = self._tokens.get(agent_id)
        if entry is None:
            return False

        now = time.time()
        entry.token = new_token
        entry.expires_at = now + entry.ttl_seconds
        entry.refresh_count += 1
        self._seq += 1
        entry.seq = self._seq

        self._total_refreshed += 1
        logger.debug("refreshed token for agent %s (count=%d)", agent_id, entry.refresh_count)
        self._fire("token_refreshed", {"entry_id": entry.entry_id, "agent_id": agent_id})
        return True

    def get_remaining_ttl(self, agent_id: str) -> float:
        """Return seconds remaining until the token expires.

        Returns ``0.0`` if the agent is unknown or already expired.
        """

        entry = self._tokens.get(agent_id)
        if entry is None:
            return 0.0
        remaining = entry.expires_at - time.time()
        return max(0.0, remaining)

    def list_agents(self) -> List[str]:
        """Return a sorted list of all registered agent IDs."""

        return sorted(self._tokens.keys())

    def get_token_count(self) -> int:
        """Return the number of currently registered tokens."""

        return len(self._tokens)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback.  Returns ``False`` if *name* exists."""

        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by *name*.  Returns ``True`` if it existed."""

        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error for action=%s", action)

    # ------------------------------------------------------------------
    # Stats / admin
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""

        now = time.time()
        active = sum(1 for e in self._tokens.values() if now < e.expires_at)
        return {
            "current_tokens": len(self._tokens),
            "active_tokens": active,
            "expired_tokens": len(self._tokens) - active,
            "total_registered": self._total_registered,
            "total_refreshed": self._total_refreshed,
            "total_expired_checks": self._total_expired_checks,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all state."""

        self._tokens.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_registered = 0
        self._total_refreshed = 0
        self._total_expired_checks = 0
        logger.debug("AgentTokenRefresh reset")
