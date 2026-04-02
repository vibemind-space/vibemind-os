"""Periodic health checks for agents with configurable probes."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentHealthCheckerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentHealthChecker:
    """Periodic health checks for agents with configurable probes."""

    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentHealthCheckerState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "ahc-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def on_change(self, name: str, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict):
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("Callback error in _fire")

    def _prune(self):
        entries = self._state.entries
        if len(entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(entries.keys(), key=lambda k: entries[k].get("_created", 0))
            while len(entries) > self.MAX_ENTRIES:
                del entries[sorted_keys.pop(0)]

    def register_check(self, agent_id: str, check_name: str, check_fn=None, interval_seconds: float = 30.0) -> str:
        check_id = self._generate_id(f"{agent_id}:{check_name}")
        self._state.entries[check_id] = {
            "_created": time.time(),
            "check_id": check_id,
            "agent_id": agent_id,
            "check_name": check_name,
            "check_fn": check_fn,
            "interval_seconds": interval_seconds,
            "history": [],
        }
        self._prune()
        self._fire("register_check", {"check_id": check_id, "agent_id": agent_id, "check_name": check_name})
        return check_id

    def run_check(self, agent_id: str, check_name: str) -> dict:
        entry = None
        for e in self._state.entries.values():
            if e.get("agent_id") == agent_id and e.get("check_name") == check_name:
                entry = e
                break
        if entry is None:
            return {"check_id": None, "status": "unhealthy", "timestamp": time.time(), "message": "Check not found"}

        check_fn = entry.get("check_fn")
        ts = time.time()
        if check_fn is None:
            result = {"check_id": entry["check_id"], "status": "healthy", "timestamp": ts, "message": "OK"}
        else:
            try:
                ret = check_fn()
                if isinstance(ret, dict):
                    status = ret.get("status", "healthy")
                    message = ret.get("message", "OK")
                elif isinstance(ret, bool):
                    status = "healthy" if ret else "unhealthy"
                    message = "OK" if ret else "Check failed"
                else:
                    status = "healthy" if ret else "unhealthy"
                    message = str(ret) if ret else "Check failed"
                result = {"check_id": entry["check_id"], "status": status, "timestamp": ts, "message": message}
            except Exception as exc:
                result = {"check_id": entry["check_id"], "status": "unhealthy", "timestamp": ts, "message": str(exc)}

        entry["history"].append(result)
        self._fire("run_check", result)
        return result

    def run_all_checks(self, agent_id: str) -> list:
        check_names = []
        for e in self._state.entries.values():
            if e.get("agent_id") == agent_id:
                check_names.append(e["check_name"])
        return [self.run_check(agent_id, name) for name in check_names]

    def get_health_status(self, agent_id: str) -> str:
        results = self.run_all_checks(agent_id)
        if not results:
            return "healthy"
        for r in results:
            if r.get("status") != "healthy":
                return "unhealthy"
        return "healthy"

    def get_check_history(self, agent_id: str, check_name: str, limit: int = 10) -> list:
        for e in self._state.entries.values():
            if e.get("agent_id") == agent_id and e.get("check_name") == check_name:
                return list(e["history"][-limit:])
        return []

    def remove_check(self, check_id: str) -> bool:
        if check_id in self._state.entries:
            del self._state.entries[check_id]
            self._fire("remove_check", {"check_id": check_id})
            return True
        return False

    def get_checks(self, agent_id: str) -> list:
        results = []
        for e in self._state.entries.values():
            if e.get("agent_id") == agent_id:
                results.append({
                    "check_id": e["check_id"],
                    "agent_id": e["agent_id"],
                    "check_name": e["check_name"],
                    "interval_seconds": e["interval_seconds"],
                })
        return results

    def get_check_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def list_agents(self) -> list:
        agents = set()
        for e in self._state.entries.values():
            agents.add(e.get("agent_id"))
        return sorted(agents)

    def get_stats(self) -> dict:
        return {
            "total_checks": len(self._state.entries),
            "agents": len(self.list_agents()),
            "seq": self._state._seq,
        }

    def reset(self):
        self._state = AgentHealthCheckerState()
        self._callbacks = {}
        self._fire("reset", {})
