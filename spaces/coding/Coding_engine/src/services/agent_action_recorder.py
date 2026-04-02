"""Agent action recorder for replay, debugging, and auditing."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentActionRecorderState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentActionRecorder:
    """Record agent actions for replay, debugging, and auditing."""

    ID_PREFIX = "aar2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentActionRecorderState()
        self._callbacks: dict = {}

    def _generate_id(self, data: str) -> str:
        hash_input = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("_seq_num", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

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

    def record_action(self, agent_id: str, action_type: str, params=None, result=None) -> str:
        action_id = self._generate_id(f"{agent_id}{action_type}{time.time()}")
        seq_num = self._state._seq
        entry = {
            "action_id": action_id,
            "agent_id": agent_id,
            "action_type": action_type,
            "params": params,
            "result": result,
            "timestamp": time.time(),
            "_seq_num": seq_num,
        }
        self._state.entries[action_id] = entry
        self._prune()
        self._fire("action_recorded", entry)
        return action_id

    def get_actions(self, agent_id: str, action_type: str = "", limit: int = 50) -> list:
        results = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
            and (not action_type or e["action_type"] == action_type)
        ]
        results.sort(key=lambda x: x.get("_seq_num", 0))
        return results[:limit]

    def get_action(self, action_id: str) -> dict | None:
        return self._state.entries.get(action_id)

    def get_latest_action(self, agent_id: str) -> dict | None:
        actions = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        ]
        if not actions:
            return None
        return max(actions, key=lambda x: x.get("_seq_num", 0))

    def get_action_sequence(self, agent_id: str, from_index: int = 0, to_index: int = -1) -> list:
        actions = [
            e for e in self._state.entries.values()
            if e["agent_id"] == agent_id
        ]
        actions.sort(key=lambda x: x.get("_seq_num", 0))
        if to_index == -1:
            return actions[from_index:]
        return actions[from_index:to_index]

    def get_action_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def clear_actions(self, agent_id: str) -> bool:
        keys_to_remove = [
            k for k, v in self._state.entries.items()
            if v["agent_id"] == agent_id
        ]
        if not keys_to_remove:
            return False
        for k in keys_to_remove:
            del self._state.entries[k]
        self._fire("actions_cleared", {"agent_id": agent_id})
        return True

    def list_agents(self) -> list:
        return sorted(set(e["agent_id"] for e in self._state.entries.values()))

    def get_stats(self) -> dict:
        agents = self.list_agents()
        return {
            "total_actions": len(self._state.entries),
            "total_agents": len(agents),
            "agents": agents,
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        self._state = AgentActionRecorderState()
        self._callbacks.clear()
        self._fire("reset", {})
