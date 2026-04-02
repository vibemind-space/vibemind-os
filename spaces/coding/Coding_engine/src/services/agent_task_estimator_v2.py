from __future__ import annotations

import hashlib
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskEstimatorV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentTaskEstimatorV2:
    PREFIX = "atev-"
    MAX_ENTRIES = 10000

    def __init__(self, on_change: Optional[Callable] = None) -> None:
        self._state = AgentTaskEstimatorV2State()
        self._on_change: Optional[Callable] = on_change

    # ------------------------------------------------------------------
    def _generate_id(self) -> str:
        seq = self._state._seq
        self._state._seq += 1
        raw = hashlib.sha256(str(seq).encode()).hexdigest()
        return f"{self.PREFIX}{raw[:12]}"

    # ------------------------------------------------------------------
    def _prune(self) -> None:
        entries = self._state.entries
        if len(entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            entries,
            key=lambda k: (entries[k]["created_at"], entries[k]["_seq"]),
        )
        quarter = len(entries) // 4
        for k in sorted_keys[:quarter]:
            del entries[k]
        logger.debug("Pruned %d entries", quarter)

    # ------------------------------------------------------------------
    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    # ------------------------------------------------------------------
    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    def _fire(self, action: str, **detail: Any) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, **detail)
            except Exception:
                logger.exception("on_change callback error")
        for cb_name, cb in list(self._state.callbacks.items()):
            try:
                cb(action, **detail)
            except Exception:
                logger.exception("callback %s error", cb_name)

    # ------------------------------------------------------------------
    def estimate_v2(
        self,
        task_id: str,
        agent_id: str,
        effort: float = 1.0,
        metadata: Any = None,
    ) -> str:
        if not task_id or not agent_id:
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "record_id": record_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "effort": effort,
            "metadata": deepcopy(metadata),
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq - 1,
        }
        self._state.entries[record_id] = entry
        self._prune()
        self._fire("estimate_v2", record_id=record_id)
        logger.info("Created estimate %s for task=%s agent=%s", record_id, task_id, agent_id)
        return record_id

    # ------------------------------------------------------------------
    def get_estimate(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    def get_estimates(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        entries = self._state.entries.values()
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        else:
            entries = list(entries)
        entries.sort(key=lambda e: (e["created_at"], e["_seq"]), reverse=True)
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    def get_estimate_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e["agent_id"] == agent_id)

    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        agents = {e["agent_id"] for e in self._state.entries.values()}
        return {
            "total_estimates": len(self._state.entries),
            "unique_agents": len(agents),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._state = AgentTaskEstimatorV2State()
        self._on_change = None
        logger.info("AgentTaskEstimatorV2 reset")
