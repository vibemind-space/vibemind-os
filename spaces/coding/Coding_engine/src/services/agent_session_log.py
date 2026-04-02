import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentSessionLogState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentSessionLog:
    PREFIX = "asl-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentSessionLogState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries.keys(),
            key=lambda k: entries[k].get("created_at", 0),
        )
        to_remove = len(entries) - self.MAX_ENTRIES
        for k in sorted_keys[:to_remove]:
            del entries[k]
        logger.info("Pruned %d entries", to_remove)

    def _fire(self, event_name: str, data: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(event_name, data)
            except Exception:
                logger.exception("Callback error")

    def on_change(self, callback) -> str:
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, cb_id: str) -> bool:
        return self._callbacks.pop(cb_id, None) is not None

    # ---- API ----

    def start_session(self, agent_id: str, metadata: dict = None) -> str:
        session_id = self._generate_id(f"session-{agent_id}-{time.time()}")
        now = time.time()
        self._state.entries[session_id] = {
            "type": "session",
            "session_id": session_id,
            "agent_id": agent_id,
            "started_at": now,
            "ended_at": None,
            "metadata": metadata or {},
            "events": [],
            "created_at": now,
        }
        self._prune()
        self._fire("session_started", {"session_id": session_id, "agent_id": agent_id})
        logger.info("Started session %s for agent %s", session_id, agent_id)
        return session_id

    def end_session(self, session_id: str) -> dict:
        session = self._state.entries.get(session_id)
        if session is None or session.get("type") != "session":
            raise KeyError(f"Session not found: {session_id}")
        now = time.time()
        session["ended_at"] = now
        duration = now - session["started_at"]
        result = {"session_id": session_id, "duration_seconds": duration}
        self._fire("session_ended", result)
        logger.info("Ended session %s (%.2fs)", session_id, duration)
        return result

    def log_event(self, session_id: str, event_type: str, message: str = "") -> str:
        session = self._state.entries.get(session_id)
        if session is None or session.get("type") != "session":
            raise KeyError(f"Session not found: {session_id}")
        event_id = self._generate_id(f"event-{session_id}-{event_type}-{time.time()}")
        now = time.time()
        event = {
            "event_id": event_id,
            "session_id": session_id,
            "event_type": event_type,
            "message": message,
            "timestamp": now,
        }
        session["events"].append(event)
        self._fire("event_logged", event)
        return event_id

    def get_session(self, session_id: str):
        entry = self._state.entries.get(session_id)
        if entry is None or entry.get("type") != "session":
            return None
        return dict(entry)

    def get_sessions(self, agent_id: str, active_only: bool = False) -> list:
        results = []
        for entry in self._state.entries.values():
            if entry.get("type") != "session":
                continue
            if entry["agent_id"] != agent_id:
                continue
            if active_only and entry["ended_at"] is not None:
                continue
            results.append(dict(entry))
        return results

    def get_events(self, session_id: str) -> list:
        session = self._state.entries.get(session_id)
        if session is None or session.get("type") != "session":
            return []
        return list(session["events"])

    def get_active_sessions(self, agent_id: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry.get("type") != "session":
                continue
            if entry["ended_at"] is not None:
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            results.append(dict(entry))
        return results

    def get_session_count(self, agent_id: str = "") -> int:
        count = 0
        for entry in self._state.entries.values():
            if entry.get("type") != "session":
                continue
            if agent_id and entry["agent_id"] != agent_id:
                continue
            count += 1
        return count

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            if entry.get("type") == "session":
                agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        total = 0
        active = 0
        agents = set()
        total_events = 0
        for entry in self._state.entries.values():
            if entry.get("type") != "session":
                continue
            total += 1
            if entry["ended_at"] is None:
                active += 1
            agents.add(entry["agent_id"])
            total_events += len(entry.get("events", []))
        return {
            "total_sessions": total,
            "active_sessions": active,
            "total_agents": len(agents),
            "total_events": total_events,
        }

    def reset(self):
        self._state = AgentSessionLogState()
        self._callbacks.clear()
        logger.info("AgentSessionLog reset")
