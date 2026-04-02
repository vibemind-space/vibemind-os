"""Agent Task Timeout Handler -- handles task timeout events for agents."""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskTimeoutHandlerState:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskTimeoutHandler:
    """Handles task timeout events for agents."""

    PREFIX = "atth-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskTimeoutHandlerState()
        self._on_change: Optional[Callable] = None

    def _generate_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"{self.PREFIX}{digest}"

    def _prune(self) -> None:
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries,
                key=lambda k: (
                    self._state.entries[k].get("created_at", 0),
                    self._state.entries[k].get("_seq", 0),
                ),
            )
            quarter = len(self._state.entries) // 4
            for k in sorted_keys[:quarter]:
                del self._state.entries[k]
            logger.info("pruned_timeouts, removed=%d", quarter)

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, cb: Optional[Callable]) -> None:
        self._on_change = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, detail)
            except Exception:
                logger.exception("on_change callback error, action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error, action=%s", action)

    def handle_timeout(
        self,
        task_id: str,
        agent_id: str,
        timeout_seconds: int = 300,
        metadata: Optional[dict] = None,
    ) -> str:
        """Handle a task timeout event. Returns record_id or '' if invalid."""
        if not task_id or not agent_id:
            return ""
        record_id = self._generate_id(f"{task_id}-{agent_id}")
        self._state.entries[record_id] = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "timeout_seconds": timeout_seconds,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": time.time(),
            "_seq": self._state._seq,
        }
        self._prune()
        self._fire("handle_timeout", record_id=record_id, task_id=task_id)
        logger.info("timeout_handled, record_id=%s, task_id=%s", record_id, task_id)
        return record_id

    def get_timeout(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_timeouts(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        if agent_id:
            items = [e for e in self._state.entries.values() if e["agent_id"] == agent_id]
        else:
            items = list(self._state.entries.values())
        items.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return items[:limit]

    def get_timeout_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    def get_stats(self) -> dict:
        unique_agents = len({e["agent_id"] for e in self._state.entries.values()})
        return {
            "total_timeouts": len(self._state.entries),
            "unique_agents": unique_agents,
        }

    def reset(self) -> None:
        self._state = AgentTaskTimeoutHandlerState()
        self._on_change = None
        logger.info("state_reset")
