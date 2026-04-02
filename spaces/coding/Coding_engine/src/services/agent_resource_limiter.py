"""Agent resource limiter - manages resource limits for agents (CPU, memory, connections)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

VALID_RESOURCE_TYPES = {"cpu", "memory", "connections"}


@dataclass
class ResourceLimitEntry:
    """A single resource limit entry."""

    limit_id: str
    agent_id: str
    resource_type: str
    max_value: float
    created_at: float


@dataclass
class AgentResourceLimiter:
    """Manages resource limits for agents (CPU, memory, connections)."""

    max_entries: int = 10000
    _limits: Dict[str, ResourceLimitEntry] = field(default_factory=dict)
    _agent_index: Dict[str, Dict[str, str]] = field(default_factory=dict)
    _callbacks: Dict[str, Callable] = field(default_factory=dict)
    _seq: int = 0
    _total_sets: int = 0
    _total_checks: int = 0
    _total_removals: int = 0

    def _next_id(self, agent_id: str, resource_type: str) -> str:
        """Generate a collision-free ID using SHA256 and sequence counter."""
        self._seq += 1
        raw = f"{agent_id}-{resource_type}-{time.time()}-{self._seq}"
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"arl-{hash_part}"

    def _fire(self, event: str, data: Dict[str, Any]) -> None:
        """Fire all registered callbacks."""
        for name, cb in list(self._callbacks.items()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("callback_error", callback=name, event=event)

    def _prune_if_needed(self) -> None:
        """Prune oldest entries if max_entries exceeded."""
        if len(self._limits) <= self.max_entries:
            return
        sorted_entries = sorted(self._limits.values(), key=lambda e: e.created_at)
        to_remove = len(self._limits) - self.max_entries
        for entry in sorted_entries[:to_remove]:
            self._remove_entry(entry)
        logger.info("pruned_entries", removed=to_remove)

    def _remove_entry(self, entry: ResourceLimitEntry) -> None:
        """Remove a single entry from all indexes."""
        self._limits.pop(entry.limit_id, None)
        agent_map = self._agent_index.get(entry.agent_id)
        if agent_map:
            agent_map.pop(entry.resource_type, None)
            if not agent_map:
                del self._agent_index[entry.agent_id]

    def set_limit(self, agent_id: str, resource_type: str, max_value: float) -> str:
        """Set a resource limit for an agent.

        Args:
            agent_id: The agent identifier.
            resource_type: One of 'cpu', 'memory', 'connections'.
            max_value: The maximum allowed value.

        Returns:
            The limit ID (prefixed with 'arl-').
        """
        if resource_type not in VALID_RESOURCE_TYPES:
            raise ValueError(
                f"Invalid resource_type '{resource_type}'. Must be one of {VALID_RESOURCE_TYPES}"
            )

        # Remove existing limit for this agent/resource if present
        existing_id = self._agent_index.get(agent_id, {}).get(resource_type)
        if existing_id and existing_id in self._limits:
            old_entry = self._limits[existing_id]
            self._remove_entry(old_entry)
            logger.debug(
                "replaced_existing_limit",
                agent_id=agent_id,
                resource_type=resource_type,
            )

        limit_id = self._next_id(agent_id, resource_type)
        entry = ResourceLimitEntry(
            limit_id=limit_id,
            agent_id=agent_id,
            resource_type=resource_type,
            max_value=max_value,
            created_at=time.time(),
        )

        self._limits[limit_id] = entry

        if agent_id not in self._agent_index:
            self._agent_index[agent_id] = {}
        self._agent_index[agent_id][resource_type] = limit_id

        self._total_sets += 1
        self._prune_if_needed()

        logger.info(
            "limit_set",
            limit_id=limit_id,
            agent_id=agent_id,
            resource_type=resource_type,
            max_value=max_value,
        )

        self._fire(
            "limit_set",
            {
                "limit_id": limit_id,
                "agent_id": agent_id,
                "resource_type": resource_type,
                "max_value": max_value,
            },
        )

        return limit_id

    def check_limit(self, agent_id: str, resource_type: str, current_value: float) -> bool:
        """Check if a current value is within the agent's resource limit.

        Args:
            agent_id: The agent identifier.
            resource_type: One of 'cpu', 'memory', 'connections'.
            current_value: The current resource usage value.

        Returns:
            True if the current value is within the limit, False otherwise.
            Returns True if no limit is set.
        """
        self._total_checks += 1
        limit_id = self._agent_index.get(agent_id, {}).get(resource_type)
        if not limit_id or limit_id not in self._limits:
            logger.debug(
                "no_limit_found",
                agent_id=agent_id,
                resource_type=resource_type,
            )
            return True

        entry = self._limits[limit_id]
        within = current_value <= entry.max_value
        logger.debug(
            "limit_checked",
            agent_id=agent_id,
            resource_type=resource_type,
            current_value=current_value,
            max_value=entry.max_value,
            within=within,
        )
        return within

    def get_limit(self, agent_id: str, resource_type: str) -> Optional[float]:
        """Get the max value for an agent's resource limit.

        Args:
            agent_id: The agent identifier.
            resource_type: One of 'cpu', 'memory', 'connections'.

        Returns:
            The max value, or None if no limit is set.
        """
        limit_id = self._agent_index.get(agent_id, {}).get(resource_type)
        if not limit_id or limit_id not in self._limits:
            return None
        return self._limits[limit_id].max_value

    def get_usage_ratio(self, agent_id: str, resource_type: str, current_value: float) -> float:
        """Get the usage ratio (0.0 to 1.0) for an agent's resource.

        Args:
            agent_id: The agent identifier.
            resource_type: One of 'cpu', 'memory', 'connections'.
            current_value: The current resource usage value.

        Returns:
            A float between 0.0 and 1.0 representing usage ratio.
            Returns 0.0 if no limit is set.
        """
        limit_id = self._agent_index.get(agent_id, {}).get(resource_type)
        if not limit_id or limit_id not in self._limits:
            return 0.0

        entry = self._limits[limit_id]
        if entry.max_value <= 0:
            return 1.0

        ratio = current_value / entry.max_value
        return max(0.0, min(1.0, ratio))

    def remove_limit(self, agent_id: str, resource_type: str) -> bool:
        """Remove a resource limit for an agent.

        Args:
            agent_id: The agent identifier.
            resource_type: One of 'cpu', 'memory', 'connections'.

        Returns:
            True if the limit was removed, False if it didn't exist.
        """
        limit_id = self._agent_index.get(agent_id, {}).get(resource_type)
        if not limit_id or limit_id not in self._limits:
            logger.debug(
                "limit_not_found_for_removal",
                agent_id=agent_id,
                resource_type=resource_type,
            )
            return False

        entry = self._limits[limit_id]
        self._remove_entry(entry)
        self._total_removals += 1

        logger.info(
            "limit_removed",
            limit_id=limit_id,
            agent_id=agent_id,
            resource_type=resource_type,
        )

        self._fire(
            "limit_removed",
            {
                "limit_id": limit_id,
                "agent_id": agent_id,
                "resource_type": resource_type,
            },
        )

        return True

    def list_agents(self) -> List[str]:
        """List all agent IDs that have resource limits.

        Returns:
            A list of agent IDs.
        """
        return list(self._agent_index.keys())

    def get_limit_count(self) -> int:
        """Get the total number of active resource limits.

        Returns:
            The count of active limits.
        """
        return len(self._limits)

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback for change events.

        Args:
            name: A unique name for the callback.
            callback: A callable that receives (event, data) arguments.
        """
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.

        Args:
            name: The name of the callback to remove.
        """
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("callback_removed", name=name)
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the resource limiter.

        Returns:
            A dict with stats about current state and usage.
        """
        return {
            "total_limits": len(self._limits),
            "total_agents": len(self._agent_index),
            "total_sets": self._total_sets,
            "total_checks": self._total_checks,
            "total_removals": self._total_removals,
            "max_entries": self.max_entries,
            "callbacks_registered": len(self._callbacks),
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Reset all state to initial values."""
        self._limits.clear()
        self._agent_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_sets = 0
        self._total_checks = 0
        self._total_removals = 0
        logger.info("resource_limiter_reset")
