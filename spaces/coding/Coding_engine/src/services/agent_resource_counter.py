"""Agent Resource Counter - Count resource usage per agent (API calls, tokens, operations)."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentResourceCounterState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentResourceCounter:
    """Count resource usage per agent (API calls, tokens, operations)."""

    PREFIX = "arco2-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self.state = AgentResourceCounterState()
        self.callbacks = {}
        self.created_at = time.time()

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self.state._seq}"
        self.state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self.callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self.callbacks:
            del self.callbacks[cb_id]
            return True
        return False

    def _fire(self, event_type: str, data: dict):
        for cb in list(self.callbacks.values()):
            try:
                cb(event_type, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def _prune(self):
        if len(self.state.entries) > self.MAX_ENTRIES:
            keys = sorted(self.state.entries.keys())
            excess = len(self.state.entries) - self.MAX_ENTRIES
            for k in keys[:excess]:
                del self.state.entries[k]
            logger.info("Pruned %d entries", excess)

    def _key(self, agent_id: str, resource: str) -> str:
        return f"{agent_id}::{resource}"

    def increment(self, agent_id: str, resource: str, amount: int = 1) -> int:
        key = self._key(agent_id, resource)
        current = self.state.entries.get(key, 0)
        new_val = current + amount
        self.state.entries[key] = new_val
        self._prune()
        self._fire("increment", {"agent_id": agent_id, "resource": resource, "amount": amount, "total": new_val})
        return new_val

    def decrement(self, agent_id: str, resource: str, amount: int = 1) -> int:
        key = self._key(agent_id, resource)
        current = self.state.entries.get(key, 0)
        new_val = max(0, current - amount)
        self.state.entries[key] = new_val
        self._fire("decrement", {"agent_id": agent_id, "resource": resource, "amount": amount, "total": new_val})
        return new_val

    def get_count(self, agent_id: str, resource: str) -> int:
        key = self._key(agent_id, resource)
        return self.state.entries.get(key, 0)

    def get_all_counts(self, agent_id: str) -> dict:
        prefix = f"{agent_id}::"
        result = {}
        for key, val in self.state.entries.items():
            if key.startswith(prefix):
                resource = key[len(prefix):]
                result[resource] = val
        return result

    def reset_count(self, agent_id: str, resource: str) -> bool:
        key = self._key(agent_id, resource)
        if key in self.state.entries:
            del self.state.entries[key]
            self._fire("reset", {"agent_id": agent_id, "resource": resource})
            return True
        return False

    def get_top_consumers(self, resource: str, limit: int = 5) -> list:
        suffix = f"::{resource}"
        consumers = []
        for key, val in self.state.entries.items():
            if key.endswith(suffix):
                agent_id = key[: key.index("::")]
                consumers.append({"agent_id": agent_id, "count": val})
        consumers.sort(key=lambda x: x["count"], reverse=True)
        return consumers[:limit]

    def get_counter_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self.state.entries)
        prefix = f"{agent_id}::"
        return sum(1 for k in self.state.entries if k.startswith(prefix))

    def list_agents(self) -> list:
        agents = set()
        for key in self.state.entries:
            agent_id = key[: key.index("::")]
            agents.add(agent_id)
        return sorted(agents)

    def list_resources(self) -> list:
        resources = set()
        for key in self.state.entries:
            resource = key[key.index("::") + 2:]
            resources.add(resource)
        return sorted(resources)

    def get_stats(self) -> dict:
        return {
            "total_entries": len(self.state.entries),
            "total_agents": len(self.list_agents()),
            "total_resources": len(self.list_resources()),
            "seq": self.state._seq,
            "created_at": self.created_at,
            "callbacks": len(self.callbacks),
        }

    def reset(self):
        self.state.entries.clear()
        self.state._seq = 0
        self.callbacks.clear()
        self._fire("reset_all", {})
