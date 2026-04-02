"""Agent Permission Cache -- caches agent permission lookups for fast repeated checks.

Stores permission grants and denials so that repeated permission checks can be
resolved quickly without re-evaluating the full permission chain.  Provides
collision-free IDs via SHA-256 plus a monotonic sequence counter, max-entry
pruning, change callbacks, and stats tracking.  Fully synchronous with no
external dependencies beyond the standard library (plus structlog for logging).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclass
# ------------------------------------------------------------------

@dataclass
class _PermissionEntry:
    permission_id: str
    agent_id: str
    resource: str
    action: str
    granted_at: float


# ------------------------------------------------------------------
# Main class
# ------------------------------------------------------------------

class AgentPermissionCache:
    """Caches agent permission lookups for fast repeated checks."""

    def __init__(self, max_entries: int = 10000) -> None:
        self.permissions: Dict[str, _PermissionEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries

        # stats counters
        self._total_grants = 0
        self._total_revocations = 0
        self._total_checks = 0
        self._total_hits = 0
        self._total_misses = 0

        logger.info("agent_permission_cache.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, seed: str) -> str:
        self._seq += 1
        now = time.time()
        raw = f"{seed}-{now}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"apc-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove oldest entries when capacity is exceeded."""
        while len(self.permissions) > self._max_entries:
            oldest_id = min(self.permissions, key=lambda pid: self.permissions[pid].granted_at)
            self.permissions.pop(oldest_id)
            logger.debug("agent_permission_cache.pruned", permission_id=oldest_id)

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _make_key(self, agent_id: str, resource: str, action: str) -> str:
        return f"{agent_id}::{resource}::{action}"

    def _find_entry(self, agent_id: str, resource: str, action: str) -> Optional[_PermissionEntry]:
        key = self._make_key(agent_id, resource, action)
        for entry in self.permissions.values():
            if self._make_key(entry.agent_id, entry.resource, entry.action) == key:
                return entry
        return None

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def grant(self, agent_id: str, resource: str, action: str = "read") -> str:
        """Grant permission. Returns permission ID (apc-xxx)."""
        existing = self._find_entry(agent_id, resource, action)
        if existing:
            logger.debug(
                "agent_permission_cache.grant_exists",
                agent_id=agent_id,
                resource=resource,
                action=action,
            )
            return existing.permission_id

        perm_id = self._generate_id(f"{agent_id}-{resource}-{action}")
        now = time.time()

        entry = _PermissionEntry(
            permission_id=perm_id,
            agent_id=agent_id,
            resource=resource,
            action=action,
            granted_at=now,
        )
        self.permissions[perm_id] = entry
        self._total_grants += 1
        self._prune()

        logger.info(
            "agent_permission_cache.granted",
            permission_id=perm_id,
            agent_id=agent_id,
            resource=resource,
            action=action,
        )
        self._fire("granted", {
            "permission_id": perm_id,
            "agent_id": agent_id,
            "resource": resource,
            "action": action,
        })
        return perm_id

    def revoke(self, agent_id: str, resource: str, action: str = "read") -> bool:
        """Revoke a specific permission. Returns True if revoked, False if not found."""
        entry = self._find_entry(agent_id, resource, action)
        if not entry:
            logger.debug(
                "agent_permission_cache.revoke_not_found",
                agent_id=agent_id,
                resource=resource,
                action=action,
            )
            return False

        self.permissions.pop(entry.permission_id, None)
        self._total_revocations += 1

        logger.info(
            "agent_permission_cache.revoked",
            permission_id=entry.permission_id,
            agent_id=agent_id,
            resource=resource,
            action=action,
        )
        self._fire("revoked", {
            "permission_id": entry.permission_id,
            "agent_id": agent_id,
            "resource": resource,
            "action": action,
        })
        return True

    def is_allowed(self, agent_id: str, resource: str, action: str = "read") -> bool:
        """Check if agent has permission."""
        self._total_checks += 1
        entry = self._find_entry(agent_id, resource, action)
        if entry:
            self._total_hits += 1
            logger.debug(
                "agent_permission_cache.allowed",
                agent_id=agent_id,
                resource=resource,
                action=action,
            )
            return True

        self._total_misses += 1
        logger.debug(
            "agent_permission_cache.denied",
            agent_id=agent_id,
            resource=resource,
            action=action,
        )
        return False

    def get_permissions(self, agent_id: str) -> list:
        """Get all permissions for agent."""
        results: List[Dict[str, Any]] = []
        for entry in self.permissions.values():
            if entry.agent_id == agent_id:
                results.append({
                    "permission_id": entry.permission_id,
                    "resource": entry.resource,
                    "action": entry.action,
                    "granted_at": entry.granted_at,
                })
        return results

    def get_permission_count(self, agent_id: str = "") -> int:
        """Count permissions total or per agent."""
        if not agent_id:
            return len(self.permissions)
        return sum(1 for e in self.permissions.values() if e.agent_id == agent_id)

    def list_agents(self) -> list:
        """List agents with permissions."""
        agents = sorted({e.agent_id for e in self.permissions.values()})
        return agents

    def list_resources(self) -> list:
        """List all resources that have permissions."""
        resources = sorted({e.resource for e in self.permissions.values()})
        return resources

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns True if removed, False if not found."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail_dict: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail_dict)
            except Exception:
                logger.exception("agent_permission_cache.callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        return {
            "current_entries": len(self.permissions),
            "total_grants": self._total_grants,
            "total_revocations": self._total_revocations,
            "total_checks": self._total_checks,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "callbacks_registered": len(self._callbacks),
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self.permissions.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_grants = 0
        self._total_revocations = 0
        self._total_checks = 0
        self._total_hits = 0
        self._total_misses = 0
        logger.info("agent_permission_cache.reset")
