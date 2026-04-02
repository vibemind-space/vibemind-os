"""Agent output collector.

Collects and aggregates outputs from agent executions, providing
per-agent storage, type-based filtering, and change notifications.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _OutputEntry:
    """A single collected output."""
    output_id: str = ""
    agent_id: str = ""
    output_type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    created_at: float = 0.0
    seq: int = 0


class AgentOutputCollector:
    """Collects and aggregates outputs from agent executions."""

    def __init__(self, max_entries: int = 100000) -> None:
        self._entries: Dict[str, _OutputEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max(1, max_entries)
        self._stats = {
            "total_collected": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # Collect
    # ------------------------------------------------------------------

    def collect(
        self,
        agent_id: str,
        output_type: str,
        data: Dict,
        task_id: str = "",
    ) -> str:
        """Store an output from an agent execution. Returns output ID."""
        if not agent_id or not output_type:
            return ""
        if len(self._entries) >= self._max_entries:
            self._prune()

        self._seq += 1
        now = time.time()

        raw = f"{agent_id}{output_type}{now}{self._seq}".encode()
        oid = "aoc-" + hashlib.sha256(raw).hexdigest()[:12]

        self._entries[oid] = _OutputEntry(
            output_id=oid,
            agent_id=agent_id,
            output_type=output_type,
            data=dict(data),
            task_id=task_id,
            created_at=now,
            seq=self._seq,
        )
        self._stats["total_collected"] += 1

        logger.debug("output_collected", output_id=oid, agent_id=agent_id,
                      output_type=output_type, task_id=task_id)
        self._fire("output_collected", {
            "output_id": oid,
            "agent_id": agent_id,
            "output_type": output_type,
            "task_id": task_id,
        })
        return oid

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_outputs(
        self,
        agent_id: str,
        output_type: str = "",
    ) -> List[Dict]:
        """Get outputs for an agent, optionally filtered by type."""
        results: List[Dict] = []
        for e in self._entries.values():
            if e.agent_id != agent_id:
                continue
            if output_type and e.output_type != output_type:
                continue
            results.append(self._to_dict(e))
        results.sort(key=lambda x: (x["created_at"], x["seq"]))
        return results

    def get_latest_output(self, agent_id: str) -> Optional[Dict]:
        """Get the most recent output for an agent."""
        latest: Optional[_OutputEntry] = None
        for e in self._entries.values():
            if e.agent_id != agent_id:
                continue
            if latest is None or (e.created_at, e.seq) > (latest.created_at, latest.seq):
                latest = e
        if latest is None:
            return None
        return self._to_dict(latest)

    def get_output(self, output_id: str) -> Optional[Dict]:
        """Get a specific output by ID."""
        e = self._entries.get(output_id)
        if not e:
            return None
        return self._to_dict(e)

    def get_output_count(self) -> int:
        """Return the number of stored outputs."""
        return len(self._entries)

    def list_agents(self) -> List[str]:
        """Return a sorted list of agent IDs that have outputs."""
        agents: set[str] = set()
        for e in self._entries.values():
            agents.add(e.agent_id)
        return sorted(agents)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        """Register a change callback. Returns False if name already taken."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return collector statistics."""
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "current_agents": len(self.list_agents()),
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all entries, callbacks, and stats."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(e: _OutputEntry) -> Dict:
        return {
            "output_id": e.output_id,
            "agent_id": e.agent_id,
            "output_type": e.output_type,
            "data": dict(e.data),
            "task_id": e.task_id,
            "created_at": e.created_at,
            "seq": e.seq,
        }

    def _prune(self) -> None:
        """Remove the oldest quarter of entries."""
        items = sorted(self._entries.items(),
                       key=lambda x: (x[1].created_at, x[1].seq))
        to_remove = max(1, len(items) // 4)
        for k, _ in items[:to_remove]:
            del self._entries[k]
        self._stats["total_pruned"] += to_remove
        logger.debug("outputs_pruned", count=to_remove)

    def _fire(self, action: str, detail: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.warning("callback_error", action=action, exc_info=True)
