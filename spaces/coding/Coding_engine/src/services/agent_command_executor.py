import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentCommandExecutorState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentCommandExecutor:
    PREFIX = "ace-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentCommandExecutorState()
        self._callbacks = {}
        self._on_change = None

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{h}"

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            self._on_change(event, data)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, fn):
        self._on_change = fn

    def remove_callback(self, callback_id: str) -> bool:
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def register_command(self, agent_id: str, command_name: str, handler_fn=None, params=None) -> str:
        command_id = self._generate_id(f"{agent_id}:{command_name}")
        entry = {
            "command_id": command_id,
            "agent_id": agent_id,
            "command_name": command_name,
            "handler_fn": handler_fn,
            "params": params or [],
            "created_at": time.time(),
            "executions": [],
        }
        self._state.entries[command_id] = entry
        self._prune()
        self._fire("command_registered", {"command_id": command_id, "agent_id": agent_id, "command_name": command_name})
        return command_id

    def execute_command(self, agent_id: str, command_name: str, args=None) -> dict:
        args = args or {}
        # Find command
        cmd = None
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and entry["command_name"] == command_name:
                cmd = entry
                break
        if cmd is None:
            return {"command_id": None, "result": None, "status": "error", "duration_ms": 0}

        start = time.time()
        try:
            handler = cmd.get("handler_fn")
            if handler is None:
                result = args
            else:
                result = handler(**args)
            duration_ms = (time.time() - start) * 1000
            execution = {
                "command_id": cmd["command_id"],
                "args": args,
                "result": result,
                "status": "success",
                "duration_ms": duration_ms,
                "executed_at": time.time(),
            }
            cmd["executions"].append(execution)
            self._fire("command_executed", execution)
            return {"command_id": cmd["command_id"], "result": result, "status": "success", "duration_ms": duration_ms}
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            execution = {
                "command_id": cmd["command_id"],
                "args": args,
                "result": str(e),
                "status": "error",
                "duration_ms": duration_ms,
                "executed_at": time.time(),
            }
            cmd["executions"].append(execution)
            self._fire("command_error", execution)
            return {"command_id": cmd["command_id"], "result": str(e), "status": "error", "duration_ms": duration_ms}

    def get_command(self, command_id: str) -> dict:
        entry = self._state.entries.get(command_id)
        if entry is None:
            return None
        return {
            "command_id": entry["command_id"],
            "agent_id": entry["agent_id"],
            "command_name": entry["command_name"],
            "params": entry["params"],
            "created_at": entry["created_at"],
        }

    def get_commands(self, agent_id: str) -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                results.append({
                    "command_id": entry["command_id"],
                    "agent_id": entry["agent_id"],
                    "command_name": entry["command_name"],
                    "params": entry["params"],
                    "created_at": entry["created_at"],
                })
        return results

    def get_execution_history(self, agent_id: str, command_name: str = "", limit: int = 20) -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if command_name and entry["command_name"] != command_name:
                continue
            results.extend(entry["executions"])
        results.sort(key=lambda x: x.get("executed_at", 0), reverse=True)
        return results[:limit]

    def remove_command(self, command_id: str) -> bool:
        if command_id in self._state.entries:
            del self._state.entries[command_id]
            self._fire("command_removed", {"command_id": command_id})
            return True
        return False

    def get_command_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        total_executions = sum(len(e["executions"]) for e in self._state.entries.values())
        return {
            "total_commands": len(self._state.entries),
            "total_executions": total_executions,
            "total_agents": len(self.list_agents()),
        }

    def reset(self):
        self._state = AgentCommandExecutorState()
        self._callbacks = {}
        self._on_change = None
        self._fire = AgentCommandExecutor._fire.__get__(self, AgentCommandExecutor)
