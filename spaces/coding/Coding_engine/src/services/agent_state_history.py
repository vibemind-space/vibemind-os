"""Track agent state transitions over time for debugging and analysis."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentStateHistoryState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentStateHistory:
    """Track agent state transitions over time for debugging and analysis."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "ash-"

    def __init__(self):
        self._state = AgentStateHistoryState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _fire(self, event: str, **kwargs):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, **kwargs)
            except Exception as e:
                logger.warning("Callback error: %s", e)

    def on_change(self, name: str, callback) -> None:
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _prune(self):
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(entries.keys(), key=lambda k: entries[k]["_order"])
            to_remove = len(entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del entries[k]
            logger.info("Pruned %d entries", to_remove)

    def record_state(self, agent_id: str, state: str, reason: str = "") -> str:
        now = time.time()
        entry_id = self._generate_id(f"{agent_id}:{state}:{now}")

        # Determine previous state for transition tracking
        prev_state = self.get_current_state(agent_id)

        entry = {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "state": state,
            "previous_state": prev_state,
            "reason": reason,
            "timestamp": now,
            "_order": self._state._seq,
        }

        self._state.entries[entry_id] = entry
        self._prune()
        self._fire("state_recorded", entry=entry)
        logger.debug("Recorded state '%s' for agent '%s': %s", state, agent_id, entry_id)
        return entry_id

    def get_current_state(self, agent_id: str):
        agent_entries = [
            e for e in self._state.entries.values() if e["agent_id"] == agent_id
        ]
        if not agent_entries:
            return None
        latest = max(agent_entries, key=lambda e: e["_order"])
        return latest["state"]

    def get_history(self, agent_id: str, limit: int = 50) -> list:
        agent_entries = [
            e for e in self._state.entries.values() if e["agent_id"] == agent_id
        ]
        agent_entries.sort(key=lambda e: e["_order"], reverse=True)
        return agent_entries[:limit]

    def get_transitions(self, agent_id: str, from_state: str = "", to_state: str = "") -> list:
        agent_entries = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id and e["previous_state"] is not None
        ]
        if from_state:
            agent_entries = [e for e in agent_entries if e["previous_state"] == from_state]
        if to_state:
            agent_entries = [e for e in agent_entries if e["state"] == to_state]
        agent_entries.sort(key=lambda e: e["_order"], reverse=True)
        return agent_entries

    def get_state_duration(self, agent_id: str, state: str) -> float:
        agent_entries = [
            e for e in self._state.entries.values() if e["agent_id"] == agent_id
        ]
        if not agent_entries:
            return 0.0
        agent_entries.sort(key=lambda e: e["_order"])

        total = 0.0
        for i, entry in enumerate(agent_entries):
            if entry["state"] == state:
                if i + 1 < len(agent_entries):
                    total += agent_entries[i + 1]["timestamp"] - entry["timestamp"]
                else:
                    # Still in this state
                    total += time.time() - entry["timestamp"]
        return total

    def get_entry(self, entry_id: str):
        return self._state.entries.get(entry_id, None)

    def get_entry_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        agents = set()
        for e in self._state.entries.values():
            agents.add(e["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        agents = self.list_agents()
        return {
            "total_entries": len(self._state.entries),
            "agent_count": len(agents),
            "agents": agents,
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = AgentStateHistoryState()
        self._callbacks.clear()
        logger.info("AgentStateHistory reset")
