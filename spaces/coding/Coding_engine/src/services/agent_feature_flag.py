"""Agent Feature Flag -- manages feature flags for agents.

Provides a central, in-memory feature flag service that allows
enabling and disabling features on a per-agent basis.  Each flag
tracks the agent, feature name, and enabled/disabled state.
The store supports querying by agent and feature, listing agents
and features, and automatic pruning when the entry limit is reached.

Thread-safe via ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import structlog

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

@dataclass
class _State:
    """Internal mutable state for the feature flag service."""

    flags: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class AgentFeatureFlag:
    """In-memory feature flag manager for agents.

    Parameters
    ----------
    max_entries:
        Maximum total number of flag entries to keep.  When the limit
        is reached the oldest quarter of entries is pruned automatically.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._state = _State()

        # stats counters
        self._stats: Dict[str, int] = {
            "total_set": 0,
            "total_removed": 0,
            "total_pruned": 0,
            "total_queries": 0,
        }

        logger.debug("agent_feature_flag.init", max_entries=max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, agent_id: str, feature: str, now: float) -> str:
        """Create a collision-free flag ID using SHA-256 + _seq."""
        raw = f"{agent_id}-{feature}-{now}-{self._state._seq}"
        return "aff-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Total entry count (internal)
    # ------------------------------------------------------------------

    def _total_entries(self) -> int:
        """Return the total number of flag entries across all agents."""
        return sum(len(v) for v in self._state.flags.values())

    # ------------------------------------------------------------------
    # Setting flags
    # ------------------------------------------------------------------

    def set_flag(
        self,
        agent_id: str,
        feature: str,
        enabled: bool = True,
    ) -> str:
        """Set a feature flag for an agent.

        Returns the generated ``aff-...`` identifier for the flag.
        """
        with self._lock:
            # prune if at capacity
            if self._total_entries() >= self._max_entries:
                self._prune()

            self._state._seq += 1
            now = time.time()
            flag_id = self._generate_id(agent_id, feature, now)

            entry: Dict[str, Any] = {
                "flag_id": flag_id,
                "agent_id": agent_id,
                "feature": feature,
                "enabled": enabled,
                "timestamp": now,
            }

            self._state.flags.setdefault(agent_id, {})[feature] = entry
            self._stats["total_set"] += 1

        logger.debug(
            "agent_feature_flag.set_flag",
            flag_id=flag_id,
            agent_id=agent_id,
            feature=feature,
            enabled=enabled,
        )
        self._fire("flag_set", {
            "flag_id": flag_id,
            "agent_id": agent_id,
            "feature": feature,
            "enabled": enabled,
        })
        return flag_id

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def is_enabled(self, agent_id: str, feature: str) -> bool:
        """Check if a feature is enabled for an agent.

        Returns ``False`` if the flag is not set.
        """
        with self._lock:
            self._stats["total_queries"] += 1
            agent_flags = self._state.flags.get(agent_id, {})
            entry = agent_flags.get(feature)
            if entry is None:
                return False
            return entry["enabled"]

    def get_flags(self, agent_id: str) -> Dict[str, bool]:
        """Return all flags for an agent as ``{feature: enabled}``."""
        with self._lock:
            self._stats["total_queries"] += 1
            agent_flags = self._state.flags.get(agent_id, {})
            return {
                feature: entry["enabled"]
                for feature, entry in agent_flags.items()
            }

    # ------------------------------------------------------------------
    # Removing flags
    # ------------------------------------------------------------------

    def remove_flag(self, agent_id: str, feature: str) -> bool:
        """Remove a flag for an agent.

        Returns ``True`` if the flag was removed, ``False`` otherwise.
        """
        with self._lock:
            agent_flags = self._state.flags.get(agent_id, {})
            if feature in agent_flags:
                del agent_flags[feature]
                if not agent_flags:
                    del self._state.flags[agent_id]
                self._stats["total_removed"] += 1
                removed = True
            else:
                removed = False

        if removed:
            logger.debug(
                "agent_feature_flag.remove_flag",
                agent_id=agent_id,
                feature=feature,
            )
            self._fire("flag_removed", {
                "agent_id": agent_id,
                "feature": feature,
            })

        return removed

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def get_flag_count(self, agent_id: str = "") -> int:
        """Count flags, optionally filtered to a single agent."""
        with self._lock:
            if not agent_id:
                return self._total_entries()
            return len(self._state.flags.get(agent_id, {}))

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return all unique agent IDs that have at least one flag."""
        with self._lock:
            return [
                aid
                for aid, flags in self._state.flags.items()
                if flags
            ]

    def list_features(self) -> List[str]:
        """Return all unique feature names across all agents."""
        with self._lock:
            features: set[str] = set()
            for agent_flags in self._state.flags.values():
                features.update(agent_flags.keys())
            return sorted(features)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        with self._lock:
            self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        with self._lock:
            if name in self._state.callbacks:
                del self._state.callbacks[name]
                return True
            else:
                return False

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks, swallowing exceptions."""
        with self._lock:
            cbs = list(self._state.callbacks.values())
        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            return {
                **self._stats,
                "current_entries": self._total_entries(),
                "unique_agents": len([
                    aid for aid, flags in self._state.flags.items()
                    if flags
                ]),
                "max_entries": self._max_entries,
            }

    def reset(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.flags.clear()
            self._state._seq = 0
            self._state.callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
        logger.debug("agent_feature_flag.reset")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Remove the oldest quarter of entries when at capacity."""
        all_entries: List[tuple] = []
        for aid, agent_flags in self._state.flags.items():
            for feature, entry in agent_flags.items():
                all_entries.append((aid, feature, entry))

        all_entries.sort(key=lambda x: x[2]["timestamp"])
        to_remove = max(len(all_entries) // 4, 1)

        for aid, feature, _entry in all_entries[:to_remove]:
            agent_flags = self._state.flags.get(aid, {})
            agent_flags.pop(feature, None)
            if not agent_flags and aid in self._state.flags:
                del self._state.flags[aid]

        self._stats["total_pruned"] += to_remove
        logger.debug("agent_feature_flag.prune", removed=to_remove)
