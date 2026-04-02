"""AgentScopeManager - Manage scopes (namespaces) for agent operations and data isolation."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentScopeManagerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentScopeManager:
    """Manage scopes (namespaces) for agent operations and data isolation."""

    PREFIX = "asm-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentScopeManagerState()
        self._callbacks: dict = {}
        # Track active scopes per agent: agent_id -> list of scope_names (stack)
        self._active_scopes: dict = {}
        logger.info("AgentScopeManager initialized")

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("created_at", 0),
            )
            excess = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in sorted_entries[:excess]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", excess)

    def on_change(self, callback_id: str, callback) -> None:
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: str, data: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def create_scope(self, agent_id: str, scope_name: str, parent_scope: str = "") -> str:
        scope_id = self._generate_id(f"{agent_id}:{scope_name}")
        entry = {
            "scope_id": scope_id,
            "agent_id": agent_id,
            "scope_name": scope_name,
            "parent_scope": parent_scope,
            "variables": {},
            "created_at": time.time(),
        }
        self._state.entries[scope_id] = entry
        self._prune()
        # Initialize active scope stack if needed
        if agent_id not in self._active_scopes:
            self._active_scopes[agent_id] = []
        self._fire("scope_created", entry)
        logger.info("Created scope %s for agent %s", scope_name, agent_id)
        return scope_id

    def enter_scope(self, agent_id: str, scope_name: str) -> bool:
        # Verify scope exists for this agent
        found = any(
            e["scope_name"] == scope_name and e["agent_id"] == agent_id
            for e in self._state.entries.values()
        )
        if not found:
            return False
        if agent_id not in self._active_scopes:
            self._active_scopes[agent_id] = []
        self._active_scopes[agent_id].append(scope_name)
        self._fire("scope_entered", {"agent_id": agent_id, "scope_name": scope_name})
        return True

    def exit_scope(self, agent_id: str) -> str:
        stack = self._active_scopes.get(agent_id, [])
        if not stack:
            return ""
        stack.pop()
        if stack:
            parent = stack[-1]
        else:
            parent = ""
        self._fire("scope_exited", {"agent_id": agent_id, "returned_to": parent})
        return parent

    def get_active_scope(self, agent_id: str) -> str:
        stack = self._active_scopes.get(agent_id, [])
        if stack:
            return stack[-1]
        return ""

    def set_variable(self, agent_id: str, key: str, value) -> bool:
        active = self.get_active_scope(agent_id)
        if not active:
            return False
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and entry["scope_name"] == active:
                entry["variables"][key] = value
                self._fire("variable_set", {"agent_id": agent_id, "key": key})
                return True
        return False

    def get_variable(self, agent_id: str, key: str):
        """Look up variable through scope chain (active scope first, then parents)."""
        stack = self._active_scopes.get(agent_id, [])
        # Walk from active scope back through parents
        for scope_name in reversed(stack):
            for entry in self._state.entries.values():
                if entry["agent_id"] == agent_id and entry["scope_name"] == scope_name:
                    if key in entry["variables"]:
                        return entry["variables"][key]
        return None

    def get_scope(self, scope_id: str) -> dict | None:
        return self._state.entries.get(scope_id)

    def get_scopes(self, agent_id: str) -> list:
        return [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        ]

    def get_scope_count(self, agent_id: str = "") -> int:
        if agent_id:
            return sum(
                1 for e in self._state.entries.values()
                if e["agent_id"] == agent_id
            )
        return len(self._state.entries)

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        return {
            "total_scopes": len(self._state.entries),
            "total_agents": len(self.list_agents()),
            "active_sessions": len(self._active_scopes),
            "callbacks": len(self._callbacks),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = AgentScopeManagerState()
        self._callbacks.clear()
        self._active_scopes.clear()
        logger.info("AgentScopeManager reset")
