"""Agent Permission Store -- fine-grained agent permissions with role-based access control.

Manages roles, permissions, and agent-to-role assignments.  Provides
collision-free IDs via SHA-256 plus a monotonic sequence counter, max-entry
pruning, change callbacks, and stats tracking.  Fully synchronous with no
external dependencies beyond the standard library (plus structlog for logging).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Internal dataclasses
# ------------------------------------------------------------------

@dataclass
class _Role:
    role_id: str
    name: str
    permissions: Set[str]
    description: str
    created_at: float


@dataclass
class _AgentBinding:
    agent_id: str
    roles: List[str]
    created_at: float
    updated_at: float


# ------------------------------------------------------------------
# Main class
# ------------------------------------------------------------------

class AgentPermissionStore:
    """Stores roles and agent-role bindings with fine-grained permission checks."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._roles: Dict[str, _Role] = {}
        self._role_name_index: Dict[str, str] = {}  # name -> role_id
        self._agents: Dict[str, _AgentBinding] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_entries = max_entries
        self._seq = 0

        # stats counters
        self._total_roles_created = 0
        self._total_roles_removed = 0
        self._total_assignments = 0
        self._total_revocations = 0
        self._total_permission_checks = 0
        self._total_permission_grants = 0
        self._total_permission_denials = 0

        logger.info("agent_permission_store.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, prefix: str, seed: str) -> str:
        self._seq += 1
        now = time.time()
        raw = f"{seed}-{now}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_roles(self) -> None:
        """Remove oldest roles when capacity is exceeded."""
        while len(self._roles) > self._max_entries:
            oldest_id = min(self._roles, key=lambda rid: self._roles[rid].created_at)
            oldest = self._roles.pop(oldest_id)
            self._role_name_index.pop(oldest.name, None)
            # cascade: remove from agents
            for binding in self._agents.values():
                if oldest.name in binding.roles:
                    binding.roles.remove(oldest.name)
            logger.debug("agent_permission_store.role_pruned", role_id=oldest_id, name=oldest.name)

    def _prune_agents(self) -> None:
        """Remove oldest agent bindings when capacity is exceeded."""
        while len(self._agents) > self._max_entries:
            oldest_id = min(self._agents, key=lambda aid: self._agents[aid].created_at)
            self._agents.pop(oldest_id)
            logger.debug("agent_permission_store.agent_pruned", agent_id=oldest_id)

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def create_role(
        self,
        role_name: str,
        permissions: Optional[List[str]] = None,
        description: str = "",
    ) -> str:
        """Create a new role.  Returns role_id, or '' if name is duplicate/empty."""
        if not role_name:
            logger.warning("agent_permission_store.create_role_empty_name")
            return ""
        if role_name in self._role_name_index:
            logger.warning("agent_permission_store.create_role_duplicate", role_name=role_name)
            return ""

        role_id = self._generate_id("aps-", role_name)
        now = time.time()

        role = _Role(
            role_id=role_id,
            name=role_name,
            permissions=set(permissions or []),
            description=description,
            created_at=now,
        )
        self._roles[role_id] = role
        self._role_name_index[role_name] = role_id
        self._total_roles_created += 1
        self._prune_roles()

        logger.info("agent_permission_store.role_created", role_id=role_id, role_name=role_name)
        self._fire("role_created", {"role_id": role_id, "role_name": role_name})
        return role_id

    def remove_role(self, role_name: str) -> bool:
        """Remove a role by name.  Cascades removal from all agent bindings."""
        rid = self._role_name_index.pop(role_name, None)
        if not rid:
            logger.warning("agent_permission_store.remove_role_not_found", role_name=role_name)
            return False

        self._roles.pop(rid, None)

        # cascade: strip role from every agent
        for binding in self._agents.values():
            if role_name in binding.roles:
                binding.roles.remove(role_name)
                binding.updated_at = time.time()

        self._total_roles_removed += 1
        logger.info("agent_permission_store.role_removed", role_name=role_name)
        self._fire("role_removed", {"role_id": rid, "role_name": role_name})
        return True

    def add_permission_to_role(self, role_name: str, permission: str) -> bool:
        """Add a single permission string to an existing role."""
        rid = self._role_name_index.get(role_name)
        if not rid or not permission:
            return False
        self._roles[rid].permissions.add(permission)
        logger.info(
            "agent_permission_store.permission_added",
            role_name=role_name,
            permission=permission,
        )
        self._fire("permission_added", {"role_name": role_name, "permission": permission})
        return True

    def list_roles(self) -> List[Dict[str, Any]]:
        """Return all roles as a list of dicts."""
        results: List[Dict[str, Any]] = []
        for role in self._roles.values():
            results.append({
                "role_id": role.role_id,
                "name": role.name,
                "permissions": sorted(role.permissions),
                "description": role.description,
                "created_at": role.created_at,
            })
        return results

    # ------------------------------------------------------------------
    # Agent-role assignment
    # ------------------------------------------------------------------

    def assign_role(self, agent_id: str, role_name: str) -> bool:
        """Assign a role to an agent.  Returns False if role doesn't exist or already assigned."""
        if not agent_id or role_name not in self._role_name_index:
            logger.warning(
                "agent_permission_store.assign_role_invalid",
                agent_id=agent_id,
                role_name=role_name,
            )
            return False

        if agent_id not in self._agents:
            now = time.time()
            self._agents[agent_id] = _AgentBinding(
                agent_id=agent_id,
                roles=[],
                created_at=now,
                updated_at=now,
            )
            self._prune_agents()

        binding = self._agents[agent_id]
        if role_name in binding.roles:
            logger.debug(
                "agent_permission_store.role_already_assigned",
                agent_id=agent_id,
                role_name=role_name,
            )
            return False

        binding.roles.append(role_name)
        binding.updated_at = time.time()
        self._total_assignments += 1

        logger.info(
            "agent_permission_store.role_assigned",
            agent_id=agent_id,
            role_name=role_name,
        )
        self._fire("role_assigned", {"agent_id": agent_id, "role_name": role_name})
        return True

    def revoke_role(self, agent_id: str, role_name: str) -> bool:
        """Revoke a role from an agent."""
        binding = self._agents.get(agent_id)
        if not binding or role_name not in binding.roles:
            return False

        binding.roles.remove(role_name)
        binding.updated_at = time.time()
        self._total_revocations += 1

        logger.info(
            "agent_permission_store.role_revoked",
            agent_id=agent_id,
            role_name=role_name,
        )
        self._fire("role_revoked", {"agent_id": agent_id, "role_name": role_name})
        return True

    # ------------------------------------------------------------------
    # Permission queries
    # ------------------------------------------------------------------

    def check_permission(self, agent_id: str, permission: str) -> bool:
        """Check whether an agent has a specific permission via any assigned role."""
        self._total_permission_checks += 1

        binding = self._agents.get(agent_id)
        if not binding:
            self._total_permission_denials += 1
            logger.debug(
                "agent_permission_store.check_denied_no_binding",
                agent_id=agent_id,
                permission=permission,
            )
            return False

        for role_name in binding.roles:
            rid = self._role_name_index.get(role_name)
            if not rid:
                continue
            role = self._roles[rid]
            if permission in role.permissions:
                self._total_permission_grants += 1
                logger.debug(
                    "agent_permission_store.check_granted",
                    agent_id=agent_id,
                    permission=permission,
                    via_role=role_name,
                )
                return True

        self._total_permission_denials += 1
        logger.debug(
            "agent_permission_store.check_denied",
            agent_id=agent_id,
            permission=permission,
        )
        return False

    def get_agent_permissions(self, agent_id: str) -> List[str]:
        """Return the full sorted list of permissions an agent holds across all roles."""
        binding = self._agents.get(agent_id)
        if not binding:
            return []

        perms: Set[str] = set()
        for role_name in binding.roles:
            rid = self._role_name_index.get(role_name)
            if not rid:
                continue
            perms |= self._roles[rid].permissions
        return sorted(perms)

    def get_agent_roles(self, agent_id: str) -> List[str]:
        """Return the list of role names assigned to an agent."""
        binding = self._agents.get(agent_id)
        if not binding:
            return []
        return list(binding.roles)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a named callback.  Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback.  Returns False if not found."""
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("agent_permission_store.callback_error", action=action)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            "current_roles": len(self._roles),
            "current_agents": len(self._agents),
            "total_roles_created": self._total_roles_created,
            "total_roles_removed": self._total_roles_removed,
            "total_assignments": self._total_assignments,
            "total_revocations": self._total_revocations,
            "total_permission_checks": self._total_permission_checks,
            "total_permission_grants": self._total_permission_grants,
            "total_permission_denials": self._total_permission_denials,
            "callbacks_registered": len(self._callbacks),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state and counters."""
        self._roles.clear()
        self._role_name_index.clear()
        self._agents.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_roles_created = 0
        self._total_roles_removed = 0
        self._total_assignments = 0
        self._total_revocations = 0
        self._total_permission_checks = 0
        self._total_permission_grants = 0
        self._total_permission_denials = 0
        logger.info("agent_permission_store.reset")
