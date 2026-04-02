"""Agent capability profile management service.

Manages capability profiles for agents - what they can do and how well.
"""

import time
import hashlib
import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclass
class AgentCapabilityProfileState:
    """State container for AgentCapabilityProfile."""
    entries: dict = field(default_factory=dict)
    _seq: int = 0


class AgentCapabilityProfile:
    """Manage capability profiles for agents - what they can do and how well."""

    PREFIX = "acp2-"

    def __init__(self) -> None:
        self._state = AgentCapabilityProfileState()
        self._callbacks: Dict[str, Callable] = {}

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def on_change(self, name: str, cb: Callable) -> None:
        """Register a change callback."""
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: Any = None) -> None:
        """Fire all registered callbacks."""
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail)
            except Exception as e:
                logger.error(f"Callback '{name}' error: {e}")

    def _prune(self) -> None:
        """Prune entries if exceeding MAX_ENTRIES."""
        if len(self._state.entries) > MAX_ENTRIES:
            entries = self._state.entries
            sorted_keys = sorted(
                entries.keys(),
                key=lambda k: entries[k].get("created_at", 0),
            )
            excess = len(entries) - MAX_ENTRIES
            for key in sorted_keys[:excess]:
                del entries[key]
            logger.info(f"Pruned {excess} entries")

    def create_profile(self, agent_id: str, capabilities: Optional[Dict[str, float]] = None) -> str:
        """Create a capability profile for an agent.

        Args:
            agent_id: Unique identifier for the agent.
            capabilities: Dict of {capability_name: skill_level (0.0-1.0)}.

        Returns:
            Profile ID string.
        """
        profile_id = self._generate_id(agent_id)
        caps = {}
        if capabilities:
            for cap_name, level in capabilities.items():
                caps[cap_name] = max(0.0, min(1.0, float(level)))

        self._state.entries[agent_id] = {
            "profile_id": profile_id,
            "agent_id": agent_id,
            "capabilities": caps,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._prune()
        self._fire("create_profile", {"agent_id": agent_id, "profile_id": profile_id})
        logger.info(f"Created profile {profile_id} for agent {agent_id}")
        return profile_id

    def add_capability(self, agent_id: str, capability: str, skill_level: float = 0.5) -> bool:
        """Add a capability to an agent's profile.

        Returns:
            True if added successfully, False if agent not found.
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return False
        clamped = max(0.0, min(1.0, float(skill_level)))
        profile["capabilities"][capability] = clamped
        profile["updated_at"] = time.time()
        self._fire("add_capability", {"agent_id": agent_id, "capability": capability, "skill_level": clamped})
        return True

    def remove_capability(self, agent_id: str, capability: str) -> bool:
        """Remove a capability from an agent's profile.

        Returns:
            True if removed, False if agent or capability not found.
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return False
        if capability not in profile["capabilities"]:
            return False
        del profile["capabilities"][capability]
        profile["updated_at"] = time.time()
        self._fire("remove_capability", {"agent_id": agent_id, "capability": capability})
        return True

    def get_capability(self, agent_id: str, capability: str) -> Optional[float]:
        """Get the skill level for a specific capability.

        Returns:
            Float skill level or None if not found.
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return None
        return profile["capabilities"].get(capability)

    def update_skill_level(self, agent_id: str, capability: str, skill_level: float) -> bool:
        """Update the skill level for an existing capability.

        Returns:
            True if updated, False if agent or capability not found.
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return False
        if capability not in profile["capabilities"]:
            return False
        clamped = max(0.0, min(1.0, float(skill_level)))
        profile["capabilities"][capability] = clamped
        profile["updated_at"] = time.time()
        self._fire("update_skill_level", {"agent_id": agent_id, "capability": capability, "skill_level": clamped})
        return True

    def get_profile(self, agent_id: str) -> Optional[dict]:
        """Get the full profile for an agent.

        Returns:
            Profile dict or None if not found.
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return None
        return dict(profile)

    def match_requirements(self, agent_id: str, requirements: Dict[str, float]) -> dict:
        """Match an agent's capabilities against requirements.

        Args:
            agent_id: The agent to check.
            requirements: Dict of {capability: minimum_skill_level}.

        Returns:
            Dict with matches (bool), met (list), unmet (list), score (float).
        """
        profile = self._state.entries.get(agent_id)
        if profile is None:
            return {"matches": False, "met": [], "unmet": list(requirements.keys()), "score": 0.0}

        caps = profile["capabilities"]
        met = []
        unmet = []
        for cap, min_level in requirements.items():
            agent_level = caps.get(cap)
            if agent_level is not None and agent_level >= min_level:
                met.append(cap)
            else:
                unmet.append(cap)

        total = len(requirements)
        score = len(met) / total if total > 0 else 0.0
        return {
            "matches": len(unmet) == 0,
            "met": met,
            "unmet": unmet,
            "score": score,
        }

    def get_profile_count(self) -> int:
        """Return the number of stored profiles."""
        return len(self._state.entries)

    def list_agents(self) -> list:
        """Return a list of all agent IDs with profiles."""
        return list(self._state.entries.keys())

    def get_stats(self) -> dict:
        """Return statistics about the profile store."""
        entries = self._state.entries
        total_caps = sum(len(p["capabilities"]) for p in entries.values())
        return {
            "profile_count": len(entries),
            "total_capabilities": total_caps,
            "seq": self._state._seq,
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state = AgentCapabilityProfileState()
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("AgentCapabilityProfile reset")
