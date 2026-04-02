"""Agent Env Config – manages environment configuration per agent.

Provides per-agent key-value configuration storage with change callbacks,
pruning, and comprehensive statistics.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _ConfigEntry:
    config_id: str
    agent_id: str
    key: str
    value: Any
    created_at: float
    seq: int


@dataclass
class _StoreState:
    configs: Dict[str, _ConfigEntry] = field(default_factory=dict)
    agent_index: Dict[str, Dict[str, str]] = field(default_factory=dict)
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    max_entries: int = 10000
    _seq: int = 0
    total_sets: int = 0
    total_gets: int = 0
    total_deletes: int = 0


class AgentEnvConfig:
    """Manages environment configuration per agent.

    Each configuration entry is identified by a unique config_id with
    prefix 'aec-'. Entries are indexed by agent_id and key for fast lookup.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._state = _StoreState(max_entries=max_entries)
        logger.info("agent_env_config.initialized", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        """Generate a collision-free config ID using SHA256 and sequence counter."""
        self._state._seq += 1
        raw = f"{seed}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"aec-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback for configuration changes."""
        self._state.callbacks[name] = callback
        logger.debug("agent_env_config.callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            logger.debug("agent_env_config.callback_removed", name=name)
            return True
        return False

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks with the given event."""
        for name, cb in list(self._state.callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception(
                    "agent_env_config.callback_error",
                    callback_name=name,
                    event=event,
                )

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Prune oldest entries if max_entries is exceeded."""
        if len(self._state.configs) <= self._state.max_entries:
            return

        sorted_entries = sorted(
            self._state.configs.values(),
            key=lambda e: e.seq,
        )
        to_remove = len(self._state.configs) - self._state.max_entries
        for entry in sorted_entries[:to_remove]:
            del self._state.configs[entry.config_id]
            agent_keys = self._state.agent_index.get(entry.agent_id, {})
            if entry.key in agent_keys and agent_keys[entry.key] == entry.config_id:
                del agent_keys[entry.key]
                if not agent_keys:
                    del self._state.agent_index[entry.agent_id]

        logger.debug("agent_env_config.pruned", removed=to_remove)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set_config(self, agent_id: str, key: str, value: Any) -> str:
        """Set a configuration value for an agent.

        Args:
            agent_id: The agent identifier.
            key: The configuration key.
            value: The configuration value.

        Returns:
            The config_id (prefix 'aec-') of the stored entry.
        """
        now = time.time()
        self._state.total_sets += 1

        # Check for existing entry
        existing_id = self._state.agent_index.get(agent_id, {}).get(key)
        if existing_id and existing_id in self._state.configs:
            entry = self._state.configs[existing_id]
            old_value = entry.value
            entry.value = value
            entry.created_at = now
            self._state._seq += 1
            entry.seq = self._state._seq
            logger.debug(
                "agent_env_config.updated",
                config_id=existing_id,
                agent_id=agent_id,
                key=key,
            )
            self._fire("config_updated", {
                "config_id": existing_id,
                "agent_id": agent_id,
                "key": key,
                "old_value": old_value,
                "new_value": value,
            })
            return existing_id

        # Create new entry
        self._prune_if_needed()
        config_id = self._gen_id(f"{agent_id}:{key}")
        entry = _ConfigEntry(
            config_id=config_id,
            agent_id=agent_id,
            key=key,
            value=value,
            created_at=now,
            seq=self._state._seq,
        )
        self._state.configs[config_id] = entry

        if agent_id not in self._state.agent_index:
            self._state.agent_index[agent_id] = {}
        self._state.agent_index[agent_id][key] = config_id

        logger.debug(
            "agent_env_config.set",
            config_id=config_id,
            agent_id=agent_id,
            key=key,
        )
        self._fire("config_set", {
            "config_id": config_id,
            "agent_id": agent_id,
            "key": key,
            "value": value,
        })
        return config_id

    def get_config(self, agent_id: str, key: str, default: Any = None) -> Any:
        """Get a configuration value for an agent.

        Args:
            agent_id: The agent identifier.
            key: The configuration key.
            default: Default value if key not found.

        Returns:
            The configuration value, or default if not found.
        """
        self._state.total_gets += 1
        config_id = self._state.agent_index.get(agent_id, {}).get(key)
        if config_id is None or config_id not in self._state.configs:
            return default
        return self._state.configs[config_id].value

    def get_all_config(self, agent_id: str) -> Dict[str, Any]:
        """Get all configuration key-value pairs for an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            Dictionary of all key-value pairs for the agent.
        """
        agent_keys = self._state.agent_index.get(agent_id, {})
        result: Dict[str, Any] = {}
        for key, config_id in agent_keys.items():
            if config_id in self._state.configs:
                result[key] = self._state.configs[config_id].value
        return result

    def delete_config(self, agent_id: str, key: str) -> bool:
        """Delete a configuration entry for an agent.

        Args:
            agent_id: The agent identifier.
            key: The configuration key.

        Returns:
            True if the entry was deleted, False if not found.
        """
        config_id = self._state.agent_index.get(agent_id, {}).get(key)
        if config_id is None or config_id not in self._state.configs:
            return False

        entry = self._state.configs.pop(config_id)
        del self._state.agent_index[agent_id][key]
        if not self._state.agent_index[agent_id]:
            del self._state.agent_index[agent_id]

        self._state.total_deletes += 1
        logger.debug(
            "agent_env_config.deleted",
            config_id=config_id,
            agent_id=agent_id,
            key=key,
        )
        self._fire("config_deleted", {
            "config_id": config_id,
            "agent_id": agent_id,
            "key": key,
            "value": entry.value,
        })
        return True

    def get_config_count(self, agent_id: str = "") -> int:
        """Get the number of configuration entries.

        Args:
            agent_id: If provided, count only entries for this agent.
                      If empty, count all entries.

        Returns:
            Number of configuration entries.
        """
        if agent_id:
            agent_keys = self._state.agent_index.get(agent_id, {})
            return len(agent_keys)
        return len(self._state.configs)

    def list_agents(self) -> List[str]:
        """List all agent IDs that have configuration entries.

        Returns:
            Sorted list of agent IDs.
        """
        return sorted(self._state.agent_index.keys())

    def list_keys(self, agent_id: str) -> List[str]:
        """List all configuration keys for an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            Sorted list of configuration keys.
        """
        agent_keys = self._state.agent_index.get(agent_id, {})
        return sorted(agent_keys.keys())

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the env config store.

        Returns:
            Dictionary with store statistics.
        """
        return {
            "total_entries": len(self._state.configs),
            "total_agents": len(self._state.agent_index),
            "max_entries": self._state.max_entries,
            "seq": self._state._seq,
            "total_sets": self._state.total_sets,
            "total_gets": self._state.total_gets,
            "total_deletes": self._state.total_deletes,
            "callbacks_registered": len(self._state.callbacks),
        }

    def reset(self) -> None:
        """Reset the store to its initial state."""
        self._state.configs.clear()
        self._state.agent_index.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        self._state.total_sets = 0
        self._state.total_gets = 0
        self._state.total_deletes = 0
        logger.info("agent_env_config.reset")
