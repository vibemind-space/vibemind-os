"""Define and evaluate triggers that start agent workflows."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


@dataclasses.dataclass
class AgentWorkflowTriggerState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowTrigger:
    """Define and evaluate triggers that start agent workflows."""

    PREFIX = "awt-"

    def __init__(self):
        self._state = AgentWorkflowTriggerState()
        self._callbacks: dict = {}
        self._created_at = time.time()
        logger.info("AgentWorkflowTrigger initialized")

    # ── ID generation ──────────────────────────────────────────────

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Callbacks ──────────────────────────────────────────────────

    def on_change(self, name: str, cb) -> None:
        self._callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action: str, detail: dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.entries) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            to_remove = len(self._state.entries) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    # ── API ────────────────────────────────────────────────────────

    def register_trigger(
        self,
        agent_id: str,
        trigger_name: str,
        trigger_type: str = "manual",
        condition: dict = None,
    ) -> str:
        trigger_id = self._generate_id(f"{agent_id}:{trigger_name}:{trigger_type}")
        entry = {
            "trigger_id": trigger_id,
            "agent_id": agent_id,
            "trigger_name": trigger_name,
            "trigger_type": trigger_type,
            "condition": condition,
            "fire_count": 0,
            "last_fired_at": None,
            "created_at": time.time(),
        }
        self._state.entries[trigger_id] = entry
        self._prune()
        self._fire("register_trigger", entry)
        logger.info("Registered trigger %s for agent %s", trigger_id, agent_id)
        return trigger_id

    def evaluate_trigger(
        self, agent_id: str, trigger_name: str, context: dict = None
    ) -> dict:
        # Find matching trigger
        matching = None
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and entry["trigger_name"] == trigger_name:
                matching = entry
                break
        if matching is None:
            return {"triggered": False, "trigger_id": None, "trigger_type": None}

        triggered = False
        t_type = matching["trigger_type"]

        if t_type == "manual":
            triggered = True
        elif t_type == "condition":
            triggered = self._evaluate_condition(matching.get("condition"), context)
        elif t_type in ("event", "schedule"):
            triggered = True

        return {
            "triggered": triggered,
            "trigger_id": matching["trigger_id"],
            "trigger_type": t_type,
        }

    def _evaluate_condition(self, condition: dict, context: dict) -> bool:
        if not condition or not context:
            return False
        for key, value in condition.items():
            if context.get(key) != value:
                return False
        return True

    def fire_trigger(self, trigger_id: str) -> dict:
        entry = self._state.entries.get(trigger_id)
        if entry is None:
            return {"trigger_id": trigger_id, "fired_at": None, "fire_count": 0}
        entry["fire_count"] += 1
        entry["last_fired_at"] = time.time()
        self._fire("fire_trigger", entry)
        return {
            "trigger_id": trigger_id,
            "fired_at": entry["last_fired_at"],
            "fire_count": entry["fire_count"],
        }

    def get_trigger(self, trigger_id: str) -> dict | None:
        return self._state.entries.get(trigger_id)

    def get_triggers(self, agent_id: str, trigger_type: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if trigger_type and entry["trigger_type"] != trigger_type:
                continue
            results.append(entry)
        return results

    def remove_trigger(self, trigger_id: str) -> bool:
        if trigger_id in self._state.entries:
            entry = self._state.entries.pop(trigger_id)
            self._fire("remove_trigger", entry)
            return True
        return False

    def get_trigger_count(self, agent_id: str = "") -> int:
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
        total = len(self._state.entries)
        total_fires = sum(e["fire_count"] for e in self._state.entries.values())
        return {
            "total_triggers": total,
            "total_fires": total_fires,
            "seq": self._state._seq,
            "uptime": time.time() - self._created_at,
        }

    def reset(self) -> None:
        self._state = AgentWorkflowTriggerState()
        self._callbacks.clear()
        self._created_at = time.time()
        logger.info("AgentWorkflowTrigger reset")
