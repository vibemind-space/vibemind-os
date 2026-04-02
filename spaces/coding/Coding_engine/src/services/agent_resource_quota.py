"""Manage resource quotas for agents (CPU, memory, API calls, etc.)."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentResourceQuotaState:
    entries: dict
    _seq: int = 0


class AgentResourceQuota:
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentResourceQuotaState(entries={})
        self._callbacks = {}

    def _make_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return "arq-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

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
            except Exception as e:
                logger.error("Callback error: %s", e)

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: self._state.entries[k].get("updated_at", 0),
            )
            excess = len(self._state.entries) - self.MAX_ENTRIES
            for k in sorted_keys[:excess]:
                del self._state.entries[k]
            logger.info("Pruned %d entries", excess)

    def _key(self, agent_id: str, resource: str) -> str:
        return f"{agent_id}::{resource}"

    def set_quota(self, agent_id: str, resource: str, limit: float) -> str:
        key = self._key(agent_id, resource)
        now = time.time()
        quota_id = self._make_id(key)
        entry = self._state.entries.get(key)
        if entry:
            entry["limit"] = limit
            entry["updated_at"] = now
            entry["quota_id"] = quota_id
        else:
            self._state.entries[key] = {
                "quota_id": quota_id,
                "agent_id": agent_id,
                "resource": resource,
                "limit": limit,
                "used": 0,
                "created_at": now,
                "updated_at": now,
            }
        self._prune()
        self._fire("set_quota", {"agent_id": agent_id, "resource": resource, "limit": limit, "quota_id": quota_id})
        logger.info("Set quota %s for agent=%s resource=%s limit=%s", quota_id, agent_id, resource, limit)
        return quota_id

    def consume(self, agent_id: str, resource: str, amount: float = 1) -> bool:
        key = self._key(agent_id, resource)
        entry = self._state.entries.get(key)
        if not entry:
            logger.warning("No quota found for agent=%s resource=%s", agent_id, resource)
            return False
        if entry["used"] + amount > entry["limit"]:
            self._fire("quota_exceeded", {"agent_id": agent_id, "resource": resource, "amount": amount})
            logger.warning("Quota exceeded for agent=%s resource=%s", agent_id, resource)
            return False
        entry["used"] += amount
        entry["updated_at"] = time.time()
        self._fire("consume", {"agent_id": agent_id, "resource": resource, "amount": amount})
        return True

    def get_usage(self, agent_id: str, resource: str) -> dict:
        key = self._key(agent_id, resource)
        entry = self._state.entries.get(key)
        if not entry:
            return {"used": 0, "limit": 0, "remaining": 0, "percent_used": 0.0}
        used = entry["used"]
        limit = entry["limit"]
        remaining = max(0, limit - used)
        percent_used = (used / limit * 100) if limit > 0 else 0.0
        return {"used": used, "limit": limit, "remaining": remaining, "percent_used": percent_used}

    def release(self, agent_id: str, resource: str, amount: float = 1) -> bool:
        key = self._key(agent_id, resource)
        entry = self._state.entries.get(key)
        if not entry:
            return False
        entry["used"] = max(0, entry["used"] - amount)
        entry["updated_at"] = time.time()
        self._fire("release", {"agent_id": agent_id, "resource": resource, "amount": amount})
        return True

    def reset_usage(self, agent_id: str, resource: str) -> bool:
        key = self._key(agent_id, resource)
        entry = self._state.entries.get(key)
        if not entry:
            return False
        entry["used"] = 0
        entry["updated_at"] = time.time()
        self._fire("reset_usage", {"agent_id": agent_id, "resource": resource})
        return True

    def get_quotas(self, agent_id: str) -> list:
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                results.append(dict(entry))
        return results

    def get_quota_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def is_within_quota(self, agent_id: str, resource: str) -> bool:
        key = self._key(agent_id, resource)
        entry = self._state.entries.get(key)
        if not entry:
            return False
        return entry["used"] < entry["limit"]

    def list_agents(self) -> list:
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        return {
            "total_entries": len(self._state.entries),
            "seq": self._state._seq,
            "agents": len(self.list_agents()),
            "callbacks": len(self._callbacks),
        }

    def reset(self):
        self._state.entries.clear()
        self._state._seq = 0
        self._callbacks.clear()
        self._fire("reset", {})
        logger.info("AgentResourceQuota reset")
