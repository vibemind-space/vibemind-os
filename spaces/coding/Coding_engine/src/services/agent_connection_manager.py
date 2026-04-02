import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentConnectionManagerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentConnectionManager:
    ID_PREFIX = "acm-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentConnectionManagerState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_part = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_part}"

    def _prune(self):
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(entries, key=lambda k: entries[k].get("created_at", 0))
            to_remove = len(entries) - self.MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del entries[key]
            logger.info("Pruned %d entries", to_remove)

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        if cb_id in self._callbacks:
            del self._callbacks[cb_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception:
                logger.exception("Callback error")

    def connect(self, from_agent: str, to_agent: str, connection_type: str = "default") -> str:
        conn_id = self._generate_id(f"{from_agent}->{to_agent}")
        entry = {
            "id": conn_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "connection_type": connection_type,
            "created_at": time.time(),
        }
        self._state.entries[conn_id] = entry
        self._prune()
        self._fire("connect", entry)
        logger.debug("Connected %s -> %s as %s", from_agent, to_agent, conn_id)
        return conn_id

    def disconnect(self, connection_id: str) -> bool:
        entry = self._state.entries.pop(connection_id, None)
        if entry is None:
            return False
        self._fire("disconnect", entry)
        logger.debug("Disconnected %s", connection_id)
        return True

    def is_connected(self, from_agent: str, to_agent: str) -> bool:
        for entry in self._state.entries.values():
            if entry["from_agent"] == from_agent and entry["to_agent"] == to_agent:
                return True
        return False

    def get_connections(self, agent_id: str, direction: str = "both") -> list:
        results = []
        for entry in self._state.entries.values():
            if direction in ("outgoing", "both") and entry["from_agent"] == agent_id:
                results.append(entry)
            elif direction in ("incoming", "both") and entry["to_agent"] == agent_id:
                if entry not in results:
                    results.append(entry)
        return results

    def get_peers(self, agent_id: str) -> list:
        peers = set()
        for entry in self._state.entries.values():
            if entry["from_agent"] == agent_id:
                peers.add(entry["to_agent"])
            elif entry["to_agent"] == agent_id:
                peers.add(entry["from_agent"])
        return list(peers)

    def get_connection(self, connection_id: str) -> dict | None:
        return self._state.entries.get(connection_id)

    def get_connection_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["from_agent"] == agent_id or entry["to_agent"] == agent_id:
                count += 1
        return count

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["from_agent"])
            agents.add(entry["to_agent"])
        return list(agents)

    def get_stats(self) -> dict:
        return {
            "total_connections": len(self._state.entries),
            "total_agents": len(self.list_agents()),
            "seq": self._state._seq,
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state = AgentConnectionManagerState()
        self._callbacks.clear()
        logger.info("Reset AgentConnectionManager")
