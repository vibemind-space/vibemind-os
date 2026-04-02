"""Agent environment manager - manage agent runtime environments with variables.

Provides per-agent isolated environments with key/value variable storage,
change callbacks, max-entries pruning, and structured logging via structlog.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EnvironmentEntry:
    """Single runtime environment for an agent."""

    env_id: str
    agent_id: str
    env_type: str
    variables: Dict[str, str]
    created_at: float = field(default_factory=time.time)
    seq: int = 0


def _generate_id(key: str, seq: int) -> str:
    """Return an ``aem-`` prefixed ID derived from *key*, a uuid, and *seq*."""
    raw = f"{key}{uuid.uuid4()}{seq}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"aem-{digest}"


class AgentEnvironmentManager:
    """Manage agent runtime environments with variable storage."""

    def __init__(self) -> None:
        self._environments: Dict[str, EnvironmentEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_environment(
        self, agent_id: str, env_type: str = "default", variables: Optional[Dict] = None
    ) -> str:
        """Create a new runtime environment for *agent_id* and return its ID."""
        if not agent_id:
            return ""
        if len(self._environments) >= self._max_entries:
            return ""

        self._seq += 1
        env_id = _generate_id(f"{agent_id}:{env_type}", self._seq)

        self._environments[env_id] = EnvironmentEntry(
            env_id=env_id,
            agent_id=agent_id,
            env_type=env_type,
            variables=dict(variables) if variables else {},
            seq=self._seq,
        )

        logger.info(
            "environment.created",
            agent_id=agent_id,
            env_type=env_type,
            env_id=env_id,
        )
        self._fire("create", {"agent_id": agent_id, "env_id": env_id, "env_type": env_type})
        return env_id

    def set_variable(self, env_id: str, key: str, value: str) -> bool:
        """Set a variable in the environment. Return ``True`` on success."""
        entry = self._environments.get(env_id)
        if entry is None:
            logger.warning("environment.set_variable_miss", env_id=env_id, key=key)
            return False

        entry.variables[key] = value
        logger.debug("environment.variable_set", env_id=env_id, key=key)
        self._fire("set_variable", {"env_id": env_id, "key": key})
        return True

    def get_variable(self, env_id: str, key: str) -> Optional[str]:
        """Retrieve a single variable value, or ``None`` if absent."""
        entry = self._environments.get(env_id)
        if entry is None:
            return None
        return entry.variables.get(key)

    def get_all_variables(self, env_id: str) -> Dict:
        """Return a copy of all variables in the environment."""
        entry = self._environments.get(env_id)
        if entry is None:
            return {}
        return dict(entry.variables)

    def destroy_environment(self, env_id: str) -> bool:
        """Destroy an environment. Return ``True`` if it existed."""
        entry = self._environments.get(env_id)
        if entry is None:
            logger.warning("environment.destroy_miss", env_id=env_id)
            return False

        agent_id = entry.agent_id
        del self._environments[env_id]

        logger.info("environment.destroyed", env_id=env_id, agent_id=agent_id)
        self._fire("destroy", {"env_id": env_id, "agent_id": agent_id})
        return True

    def get_agent_environments(self, agent_id: str) -> List[Dict]:
        """Return all environments belonging to *agent_id*."""
        result: List[Dict] = []
        for entry in self._environments.values():
            if entry.agent_id == agent_id:
                result.append({
                    "env_id": entry.env_id,
                    "agent_id": entry.agent_id,
                    "env_type": entry.env_type,
                    "variable_count": len(entry.variables),
                    "created_at": entry.created_at,
                })
        return result

    def list_agents(self) -> List[str]:
        """Return all distinct agent IDs that own environments."""
        seen: set[str] = set()
        result: List[str] = []
        for entry in self._environments.values():
            if entry.agent_id not in seen:
                seen.add(entry.agent_id)
                result.append(entry.agent_id)
        return result

    def get_environment_count(self) -> int:
        """Return total number of environments across all agents."""
        return len(self._environments)

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*."""
        self._callbacks[name] = callback
        logger.debug("callback.registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Return ``True`` if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        logger.debug("callback.removed", name=name)
        return True

    def get_stats(self) -> Dict:
        """Return a dictionary of manager statistics."""
        return {
            "total_environments": len(self._environments),
            "total_agents": len(self.list_agents()),
            "seq": self._seq,
            "max_entries": self._max_entries,
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all environments, callbacks, and counters."""
        self._environments.clear()
        self._callbacks.clear()
        self._seq = 0
        logger.info("environment_manager.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Invoke every registered callback with *action* and *detail*."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback.error", callback=cb_name, action=action)

    def _prune(self) -> None:
        """Remove oldest environments when count exceeds ``_max_entries``."""
        if len(self._environments) <= self._max_entries:
            return

        all_entries = sorted(self._environments.values(), key=lambda e: e.created_at)
        remove_count = len(self._environments) - self._max_entries

        for entry in all_entries[:remove_count]:
            if entry.env_id in self._environments:
                del self._environments[entry.env_id]

        logger.info("environment_manager.pruned", removed=remove_count)
