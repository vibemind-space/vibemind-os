"""Resolve context variables for agent operations from multiple sources."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentContextResolverState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentContextResolver:
    """Resolve context variables for agent operations from multiple sources."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "acr-"

    def __init__(self):
        self._state = AgentContextResolverState()
        self._callbacks: dict = {}
        self._created_at = time.time()

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.ID_PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            entries = sorted(
                self._state.entries.items(),
                key=lambda x: x[1].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key, _ in entries[:to_remove]:
                del self._state.entries[key]
            logger.info("Pruned %d entries", to_remove)

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def register_source(self, agent_id: str, source_name: str, data: dict) -> str:
        source_id = self._generate_id(f"{agent_id}-{source_name}-{time.time()}")
        self._state.entries[source_id] = {
            "agent_id": agent_id,
            "source_name": source_name,
            "data": dict(data),
            "created_at": time.time(),
        }
        self._prune()
        self._fire("register", {"source_id": source_id, "agent_id": agent_id})
        return source_id

    def resolve(self, agent_id: str, key: str):
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and key in entry["data"]:
                return entry["data"][key]
        return None

    def resolve_template(self, agent_id: str, template: str) -> str:
        result = template
        # Find all {key} placeholders
        import re
        for match in re.finditer(r"\{(\w+)\}", template):
            key = match.group(1)
            value = self.resolve(agent_id, key)
            if value is not None:
                result = result.replace("{" + key + "}", str(value))
        return result

    def get_sources(self, agent_id: str) -> list:
        results = []
        for source_id, entry in self._state.entries.items():
            if entry["agent_id"] == agent_id:
                results.append({
                    "source_id": source_id,
                    "source_name": entry["source_name"],
                    "data": dict(entry["data"]),
                    "created_at": entry["created_at"],
                })
        return results

    def remove_source(self, source_id: str) -> bool:
        if source_id in self._state.entries:
            agent_id = self._state.entries[source_id]["agent_id"]
            del self._state.entries[source_id]
            self._fire("remove", {"source_id": source_id, "agent_id": agent_id})
            return True
        return False

    def update_source(self, source_id: str, data: dict) -> bool:
        if source_id in self._state.entries:
            self._state.entries[source_id]["data"].update(data)
            self._fire("update", {"source_id": source_id})
            return True
        return False

    def get_source_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(
            1 for e in self._state.entries.values() if e["agent_id"] == agent_id
        )

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        return {
            "total_sources": len(self._state.entries),
            "total_agents": len(self.list_agents()),
            "seq": self._state._seq,
            "uptime": time.time() - self._created_at,
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state = AgentContextResolverState()
        self._callbacks.clear()
        self._fire("reset", {})
