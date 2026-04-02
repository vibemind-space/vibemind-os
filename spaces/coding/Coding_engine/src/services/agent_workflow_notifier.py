"""Agent workflow notifier - sends notifications for workflow lifecycle events."""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowNotifierState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentWorkflowNotifier:
    PREFIX = "awn-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = AgentWorkflowNotifierState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    def _generate_id(self, data: str) -> str:
        raw = f"{self.PREFIX}{self._state._seq}{id(self)}{time.time()}{data}"
        self._state._seq += 1
        h = hashlib.sha256(raw.encode()).hexdigest()
        return self.PREFIX + h[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                oldest = sorted_keys.pop(0)
                del self._state.entries[oldest]

    def _fire(self, action, data):
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                pass
        for name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                pass

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, value):
        self._on_change = value

    def remove_callback(self, name) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def notify(self, agent_id: str, workflow_name: str, event: str, message: str = "", metadata: dict = None) -> str:
        now = time.time()
        notification_id = self._generate_id(f"{agent_id}:{workflow_name}:{event}:{now}")
        entry = {
            "notification_id": notification_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "event": event,
            "message": message,
            "metadata": metadata or {},
            "read": False,
            "created_at": now,
        }
        self._state.entries[notification_id] = entry
        self._prune()
        self._fire("notify", entry)
        return notification_id

    def get_notification(self, notification_id: str) -> Optional[dict]:
        return self._state.entries.get(notification_id)

    def get_notifications(self, agent_id: str = "", workflow_name: str = "", limit: int = 50) -> List[dict]:
        results = []
        for entry in self._state.entries.values():
            if agent_id and entry.get("agent_id") != agent_id:
                continue
            if workflow_name and entry.get("workflow_name") != workflow_name:
                continue
            results.append(entry)
        results.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        return results[:limit]

    def mark_read(self, notification_id: str) -> bool:
        entry = self._state.entries.get(notification_id)
        if entry is None:
            return False
        entry["read"] = True
        self._fire("mark_read", entry)
        return True

    def get_notification_count(self, agent_id: str = "", read: bool = None) -> int:
        count = 0
        for entry in self._state.entries.values():
            if agent_id and entry.get("agent_id") != agent_id:
                continue
            if read is not None and entry.get("read") != read:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        entries = self._state.entries.values()
        unread = sum(1 for e in entries if not e.get("read", False))
        agents = set(e.get("agent_id") for e in entries)
        result = {
            "total_notifications": len(self._state.entries),
            "unread_count": unread,
            "unique_agents": len(agents),
        }
        self._fire("get_stats", result)
        return result

    def reset(self) -> None:
        self._state.entries.clear()
        self._state._seq = 0
        self._fire("reset", {})
