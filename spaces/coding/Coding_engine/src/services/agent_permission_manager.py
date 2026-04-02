"""Agent Permission Manager – controls agent access to resources and actions.

Defines roles and permissions, assigns roles to agents, and checks
whether an agent is authorised to perform a given action on a resource.
Supports hierarchical roles and explicit denials.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Role:
    role_id: str
    name: str
    permissions: Set[str]  # "resource:action" patterns
    parent_role: str  # inherits from parent
    tags: List[str]
    created_at: float


@dataclass
class _AgentAssignment:
    agent: str
    roles: List[str]  # role names
    explicit_grants: Set[str]  # extra "resource:action"
    explicit_denials: Set[str]  # deny overrides
    created_at: float
    updated_at: float


@dataclass
class _CheckEvent:
    event_id: str
    agent: str
    resource: str
    action: str
    allowed: bool
    reason: str
    timestamp: float


class AgentPermissionManager:
    """Controls agent access to resources and actions via role-based permissions."""

    def __init__(self, max_roles: int = 1000, max_agents: int = 10000, max_history: int = 100000):
        self._roles: Dict[str, _Role] = {}
        self._role_name_index: Dict[str, str] = {}  # name -> role_id
        self._agents: Dict[str, _AgentAssignment] = {}
        self._history: List[_CheckEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_roles = max_roles
        self._max_agents = max_agents
        self._max_history = max_history
        self._seq = 0

        # stats
        self._total_roles = 0
        self._total_checks = 0
        self._total_allowed = 0
        self._total_denied = 0

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def create_role(
        self,
        name: str,
        permissions: Optional[List[str]] = None,
        parent_role: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        if not name:
            return ""
        if name in self._role_name_index:
            return ""
        if len(self._roles) >= self._max_roles:
            return ""
        if parent_role and parent_role not in self._role_name_index:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        rid = "rol-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        role = _Role(
            role_id=rid,
            name=name,
            permissions=set(permissions or []),
            parent_role=parent_role,
            tags=tags or [],
            created_at=now,
        )
        self._roles[rid] = role
        self._role_name_index[name] = rid
        self._total_roles += 1
        self._fire("role_created", {"role_id": rid, "name": name})
        return rid

    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        rid = self._role_name_index.get(name)
        if not rid:
            return None
        r = self._roles[rid]
        return {
            "role_id": r.role_id,
            "name": r.name,
            "permissions": sorted(r.permissions),
            "parent_role": r.parent_role,
            "tags": list(r.tags),
            "created_at": r.created_at,
        }

    def remove_role(self, name: str) -> bool:
        rid = self._role_name_index.pop(name, None)
        if not rid:
            return False
        self._roles.pop(rid, None)
        # Remove role from all agents
        for assignment in self._agents.values():
            if name in assignment.roles:
                assignment.roles.remove(name)
        return True

    def add_permission_to_role(self, role_name: str, permission: str) -> bool:
        rid = self._role_name_index.get(role_name)
        if not rid or not permission:
            return False
        self._roles[rid].permissions.add(permission)
        return True

    def remove_permission_from_role(self, role_name: str, permission: str) -> bool:
        rid = self._role_name_index.get(role_name)
        if not rid:
            return False
        r = self._roles[rid]
        if permission not in r.permissions:
            return False
        r.permissions.discard(permission)
        return True

    def _get_effective_permissions(self, role_name: str, visited: Optional[Set[str]] = None) -> Set[str]:
        """Get all permissions for a role including inherited."""
        if visited is None:
            visited = set()
        if role_name in visited:
            return set()  # circular protection
        visited.add(role_name)

        rid = self._role_name_index.get(role_name)
        if not rid:
            return set()
        role = self._roles[rid]
        perms = set(role.permissions)
        if role.parent_role:
            perms |= self._get_effective_permissions(role.parent_role, visited)
        return perms

    # ------------------------------------------------------------------
    # Agent assignment
    # ------------------------------------------------------------------

    def assign_role(self, agent: str, role_name: str) -> bool:
        if not agent or role_name not in self._role_name_index:
            return False
        if agent not in self._agents:
            if len(self._agents) >= self._max_agents:
                return False
            self._agents[agent] = _AgentAssignment(
                agent=agent, roles=[], explicit_grants=set(),
                explicit_denials=set(), created_at=time.time(), updated_at=time.time(),
            )
        assignment = self._agents[agent]
        if role_name in assignment.roles:
            return False
        assignment.roles.append(role_name)
        assignment.updated_at = time.time()
        self._fire("role_assigned", {"agent": agent, "role": role_name})
        return True

    def revoke_role(self, agent: str, role_name: str) -> bool:
        assignment = self._agents.get(agent)
        if not assignment or role_name not in assignment.roles:
            return False
        assignment.roles.remove(role_name)
        assignment.updated_at = time.time()
        return True

    def grant_permission(self, agent: str, permission: str) -> bool:
        """Grant explicit permission to agent (beyond roles)."""
        if not agent or not permission:
            return False
        if agent not in self._agents:
            if len(self._agents) >= self._max_agents:
                return False
            self._agents[agent] = _AgentAssignment(
                agent=agent, roles=[], explicit_grants=set(),
                explicit_denials=set(), created_at=time.time(), updated_at=time.time(),
            )
        self._agents[agent].explicit_grants.add(permission)
        return True

    def deny_permission(self, agent: str, permission: str) -> bool:
        """Explicitly deny a permission (overrides role grants)."""
        if not agent or not permission:
            return False
        if agent not in self._agents:
            if len(self._agents) >= self._max_agents:
                return False
            self._agents[agent] = _AgentAssignment(
                agent=agent, roles=[], explicit_grants=set(),
                explicit_denials=set(), created_at=time.time(), updated_at=time.time(),
            )
        self._agents[agent].explicit_denials.add(permission)
        return True

    # ------------------------------------------------------------------
    # Check permissions
    # ------------------------------------------------------------------

    def check(self, agent: str, resource: str, action: str) -> bool:
        """Check if agent is allowed to perform action on resource."""
        perm = f"{resource}:{action}"
        self._total_checks += 1

        assignment = self._agents.get(agent)
        if not assignment:
            self._total_denied += 1
            self._record_event(agent, resource, action, False, "no_assignment")
            return False

        # Explicit denials override everything
        if perm in assignment.explicit_denials:
            self._total_denied += 1
            self._record_event(agent, resource, action, False, "explicit_denial")
            return False

        # Explicit grants
        if perm in assignment.explicit_grants:
            self._total_allowed += 1
            self._record_event(agent, resource, action, True, "explicit_grant")
            return True

        # Check wildcard grants
        wildcard = f"{resource}:*"
        if wildcard in assignment.explicit_grants:
            self._total_allowed += 1
            self._record_event(agent, resource, action, True, "wildcard_grant")
            return True

        # Role-based permissions
        for role_name in assignment.roles:
            effective = self._get_effective_permissions(role_name)
            if perm in effective or wildcard in effective or "*:*" in effective:
                self._total_allowed += 1
                self._record_event(agent, resource, action, True, f"role:{role_name}")
                return True

        self._total_denied += 1
        self._record_event(agent, resource, action, False, "no_permission")
        return False

    def get_agent_permissions(self, agent: str) -> List[str]:
        """Get all effective permissions for an agent."""
        assignment = self._agents.get(agent)
        if not assignment:
            return []
        perms: Set[str] = set(assignment.explicit_grants)
        for role_name in assignment.roles:
            perms |= self._get_effective_permissions(role_name)
        perms -= assignment.explicit_denials
        return sorted(perms)

    def get_agent_roles(self, agent: str) -> List[str]:
        assignment = self._agents.get(agent)
        if not assignment:
            return []
        return list(assignment.roles)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_roles(self, tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for r in self._roles.values():
            if tag and tag not in r.tags:
                continue
            results.append(self.get_role(r.name))
        return results

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def get_history(
        self,
        agent: str = "",
        allowed: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if agent and ev.agent != agent:
                continue
            if allowed is not None and ev.allowed != allowed:
                continue
            results.append({
                "event_id": ev.event_id,
                "agent": ev.agent,
                "resource": ev.resource,
                "action": ev.action,
                "allowed": ev.allowed,
                "reason": ev.reason,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, agent: str, resource: str, action: str, allowed: bool, reason: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{agent}-{resource}-{action}-{now}-{self._seq}"
        evid = "pev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _CheckEvent(
            event_id=evid, agent=agent, resource=resource,
            action=action, allowed=allowed, reason=reason, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

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
        return {
            "current_roles": len(self._roles),
            "current_agents": len(self._agents),
            "total_roles": self._total_roles,
            "total_checks": self._total_checks,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._roles.clear()
        self._role_name_index.clear()
        self._agents.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_roles = 0
        self._total_checks = 0
        self._total_allowed = 0
        self._total_denied = 0
