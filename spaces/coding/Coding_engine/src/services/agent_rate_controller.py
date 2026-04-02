"""Agent rate controller service for the emergent autonomous coding engine.

Controls the rate of operations per agent with configurable windows and limits.
"""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentRateControllerState:
    entries: dict
    _seq: int = 0


class AgentRateController:
    MAX_ENTRIES = 10000
    PRUNE_TARGET = 5000

    def __init__(self):
        self._state = AgentRateControllerState(entries={})
        self._callbacks = {}

    def _generate_id(self, data):
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "arco-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def on_change(self, name, cb):
        self._callbacks[name] = cb

    def remove_callback(self, name):
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def _fire(self, action, detail_dict):
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, detail_dict)
            except Exception as e:
                logger.error("Callback %s failed: %s", name, e)

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("timestamp", 0),
            )
            keys_to_remove = sorted_keys[: len(sorted_keys) - self.PRUNE_TARGET]
            for k in keys_to_remove:
                del self._state.entries[k]
            logger.info("Pruned entries to %d", len(self._state.entries))

    def set_limit(self, agent_id, operation, max_requests, window_seconds=60.0):
        """Set a rate limit for an agent's operation."""
        data = f"{agent_id}:{operation}:{max_requests}:{window_seconds}"
        limit_id = self._generate_id(data)
        entry = {
            "id": limit_id,
            "agent_id": agent_id,
            "operation": operation,
            "max_requests": max_requests,
            "window_seconds": window_seconds,
            "requests": [],
            "timestamp": time.time(),
        }
        self._state.entries[limit_id] = entry
        self._prune()
        self._fire("set_limit", {"limit_id": limit_id, "agent_id": agent_id, "operation": operation})
        logger.debug("Set limit %s for agent=%s op=%s max=%d window=%.1f",
                      limit_id, agent_id, operation, max_requests, window_seconds)
        return limit_id

    def _find_limit_entry(self, agent_id, operation):
        for entry in self._state.entries.values():
            if entry.get("agent_id") == agent_id and entry.get("operation") == operation:
                return entry
        return None

    def _count_in_window(self, entry):
        now = time.time()
        window = entry["window_seconds"]
        cutoff = now - window
        entry["requests"] = [t for t in entry["requests"] if t > cutoff]
        return len(entry["requests"])

    def check_rate(self, agent_id, operation):
        """Check if the agent can perform the operation."""
        entry = self._find_limit_entry(agent_id, operation)
        if entry is None:
            return {"allowed": True, "remaining": -1, "reset_at": 0.0}
        now = time.time()
        count = self._count_in_window(entry)
        allowed = count < entry["max_requests"]
        remaining = max(0, entry["max_requests"] - count)
        window = entry["window_seconds"]
        if entry["requests"]:
            reset_at = entry["requests"][0] + window
        else:
            reset_at = now + window
        return {"allowed": allowed, "remaining": remaining, "reset_at": reset_at}

    def record_request(self, agent_id, operation):
        """Record a request. Returns True if allowed, False if rate exceeded."""
        entry = self._find_limit_entry(agent_id, operation)
        if entry is None:
            return True
        count = self._count_in_window(entry)
        if count >= entry["max_requests"]:
            self._fire("rate_exceeded", {"agent_id": agent_id, "operation": operation})
            logger.warning("Rate exceeded for agent=%s op=%s", agent_id, operation)
            return False
        entry["requests"].append(time.time())
        entry["timestamp"] = time.time()
        self._fire("record_request", {"agent_id": agent_id, "operation": operation})
        return True

    def get_usage(self, agent_id, operation):
        """Get usage info for an agent's operation."""
        entry = self._find_limit_entry(agent_id, operation)
        if entry is None:
            return {"count": 0, "limit": 0, "window_seconds": 0.0, "remaining": 0}
        count = self._count_in_window(entry)
        remaining = max(0, entry["max_requests"] - count)
        return {
            "count": count,
            "limit": entry["max_requests"],
            "window_seconds": entry["window_seconds"],
            "remaining": remaining,
        }

    def get_limit(self, limit_id):
        """Get a limit by ID, or None if not found."""
        entry = self._state.entries.get(limit_id)
        if entry is None:
            return None
        return {
            "id": entry["id"],
            "agent_id": entry["agent_id"],
            "operation": entry["operation"],
            "max_requests": entry["max_requests"],
            "window_seconds": entry["window_seconds"],
        }

    def get_limits(self, agent_id):
        """Get all limits for an agent."""
        results = []
        for entry in self._state.entries.values():
            if entry.get("agent_id") == agent_id:
                results.append({
                    "id": entry["id"],
                    "agent_id": entry["agent_id"],
                    "operation": entry["operation"],
                    "max_requests": entry["max_requests"],
                    "window_seconds": entry["window_seconds"],
                })
        return results

    def remove_limit(self, limit_id):
        """Remove a limit by ID."""
        if limit_id in self._state.entries:
            detail = {"limit_id": limit_id, "agent_id": self._state.entries[limit_id].get("agent_id")}
            del self._state.entries[limit_id]
            self._fire("remove_limit", detail)
            return True
        return False

    def get_limit_count(self, agent_id=""):
        """Get count of limits, optionally filtered by agent_id."""
        if agent_id:
            return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)
        return len(self._state.entries)

    def list_agents(self):
        """List all unique agent IDs that have limits."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry.get("agent_id"))
        return sorted(agents)

    def get_stats(self):
        """Return stats dict with counts."""
        agents = set()
        operations = set()
        for entry in self._state.entries.values():
            agents.add(entry.get("agent_id"))
            operations.add(entry.get("operation"))
        return {
            "total_limits": len(self._state.entries),
            "total_agents": len(agents),
            "total_operations": len(operations),
            "seq": self._state._seq,
        }

    def reset(self):
        """Clear all state."""
        self._state = AgentRateControllerState(entries={})
        self._fire("reset", {})
        logger.info("AgentRateController reset")
