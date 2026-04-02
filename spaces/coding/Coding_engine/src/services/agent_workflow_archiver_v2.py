from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowArchiverV2State:
    entries: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class AgentWorkflowArchiverV2:
    PREFIX = "awav-"
    MAX_ENTRIES = 10000

    def __init__(self, _on_change: Optional[Callable] = None) -> None:
        self._state = AgentWorkflowArchiverV2State()
        self._on_change = _on_change
        logger.debug("AgentWorkflowArchiverV2 initialised")

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self._state._seq}-{datetime.now(timezone.utc).isoformat()}"
        h = hashlib.sha256(raw.encode()).hexdigest()
        return f"{self.PREFIX}{h[:12]}"

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries,
            key=lambda k: (
                self._state.entries[k].get("created_at", ""),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        quarter = len(sorted_keys) // 4
        to_remove = sorted_keys[:quarter]
        for k in to_remove:
            del self._state.entries[k]
        logger.info("Pruned %d archive entries", len(to_remove))
        self._fire("prune", removed=len(to_remove))

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            logger.debug("Removed callback %s", name)
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        data = {"action": action, **detail}
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

    def archive_v2(
        self,
        agent_id: str,
        workflow_name: str,
        destination: str = "cold",
        metadata: Optional[dict] = None,
    ) -> str:
        if not agent_id or not workflow_name:
            logger.warning("archive_v2 called with empty agent_id or workflow_name")
            return ""
        record_id = self._generate_id()
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "record_id": record_id,
            "agent_id": agent_id,
            "workflow_name": workflow_name,
            "destination": destination,
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[record_id] = record
        logger.info("Archived workflow %s for agent %s -> %s", workflow_name, agent_id, record_id)
        self._prune()
        self._fire("archive", record_id=record_id, agent_id=agent_id)
        return record_id

    def get_archive(self, record_id: str) -> Optional[dict]:
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return copy.deepcopy(entry)

    def get_archives(self, agent_id: str = "", limit: int = 50) -> List[dict]:
        results = [
            copy.deepcopy(e)
            for e in self._state.entries.values()
            if not agent_id or e.get("agent_id") == agent_id
        ]
        results.sort(key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_archive_count(self, agent_id: str = "") -> int:
        if not agent_id:
            return len(self._state.entries)
        return sum(1 for e in self._state.entries.values() if e.get("agent_id") == agent_id)

    def get_stats(self) -> dict:
        agents = {e.get("agent_id") for e in self._state.entries.values()}
        return {
            "total_archives": len(self._state.entries),
            "unique_agents": len(agents),
        }

    def reset(self) -> None:
        self._state = AgentWorkflowArchiverV2State()
        self._on_change = None
        logger.info("AgentWorkflowArchiverV2 reset")
