"""Agent Sandbox Manager – manages isolated execution sandboxes for agents.

Creates, monitors, and tears down sandboxes that provide resource-limited
environments for agent code execution.  Tracks resource usage and enforces
limits on CPU time, memory, and concurrency.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Sandbox:
    sandbox_id: str
    agent: str
    status: str  # active, paused, terminated
    cpu_limit: float  # seconds
    memory_limit: int  # MB
    cpu_used: float
    memory_used: int
    tags: List[str]
    created_at: float
    updated_at: float


@dataclass
class _SandboxEvent:
    event_id: str
    sandbox_id: str
    agent: str
    action: str  # created, paused, resumed, terminated, limit_exceeded
    timestamp: float


class AgentSandboxManager:
    """Manages isolated execution sandboxes for agents."""

    STATUSES = ("active", "paused", "terminated")

    def __init__(
        self,
        max_sandboxes: int = 5000,
        max_history: int = 100000,
        default_cpu_limit: float = 60.0,
        default_memory_limit: int = 512,
    ):
        self._sandboxes: Dict[str, _Sandbox] = {}
        self._agent_index: Dict[str, List[str]] = {}  # agent -> [sandbox_ids]
        self._history: List[_SandboxEvent] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_sandboxes = max_sandboxes
        self._max_history = max_history
        self._default_cpu_limit = default_cpu_limit
        self._default_memory_limit = default_memory_limit
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_terminated = 0
        self._total_events = 0

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_sandbox(
        self,
        agent: str,
        cpu_limit: float = 0.0,
        memory_limit: int = 0,
        tags: Optional[List[str]] = None,
    ) -> str:
        if not agent:
            return ""
        if len(self._sandboxes) >= self._max_sandboxes:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{agent}-{now}-{self._seq}"
        sid = "sbx-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

        sb = _Sandbox(
            sandbox_id=sid,
            agent=agent,
            status="active",
            cpu_limit=cpu_limit if cpu_limit > 0 else self._default_cpu_limit,
            memory_limit=memory_limit if memory_limit > 0 else self._default_memory_limit,
            cpu_used=0.0,
            memory_used=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._sandboxes[sid] = sb
        self._agent_index.setdefault(agent, []).append(sid)
        self._total_created += 1
        self._record_event(sid, agent, "created")
        self._fire("sandbox_created", {"sandbox_id": sid, "agent": agent})
        return sid

    def get_sandbox(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            return None
        return {
            "sandbox_id": sb.sandbox_id,
            "agent": sb.agent,
            "status": sb.status,
            "cpu_limit": sb.cpu_limit,
            "memory_limit": sb.memory_limit,
            "cpu_used": sb.cpu_used,
            "memory_used": sb.memory_used,
            "tags": list(sb.tags),
            "created_at": sb.created_at,
            "updated_at": sb.updated_at,
        }

    def get_agent_sandboxes(self, agent: str) -> List[Dict[str, Any]]:
        sids = self._agent_index.get(agent, [])
        results = []
        for sid in sids:
            info = self.get_sandbox(sid)
            if info:
                results.append(info)
        return results

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def pause_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb or sb.status != "active":
            return False
        sb.status = "paused"
        sb.updated_at = time.time()
        self._record_event(sandbox_id, sb.agent, "paused")
        self._fire("sandbox_paused", {"sandbox_id": sandbox_id, "agent": sb.agent})
        return True

    def resume_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb or sb.status != "paused":
            return False
        sb.status = "active"
        sb.updated_at = time.time()
        self._record_event(sandbox_id, sb.agent, "resumed")
        self._fire("sandbox_resumed", {"sandbox_id": sandbox_id, "agent": sb.agent})
        return True

    def terminate_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb or sb.status == "terminated":
            return False
        sb.status = "terminated"
        sb.updated_at = time.time()
        self._total_terminated += 1
        self._record_event(sandbox_id, sb.agent, "terminated")
        self._fire("sandbox_terminated", {"sandbox_id": sandbox_id, "agent": sb.agent})
        return True

    def remove_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.pop(sandbox_id, None)
        if not sb:
            return False
        agent_list = self._agent_index.get(sb.agent, [])
        if sandbox_id in agent_list:
            agent_list.remove(sandbox_id)
        if not agent_list:
            self._agent_index.pop(sb.agent, None)
        return True

    # ------------------------------------------------------------------
    # Resource tracking
    # ------------------------------------------------------------------

    def report_usage(self, sandbox_id: str, cpu_used: float = 0.0, memory_used: int = 0) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb or sb.status == "terminated":
            return False
        sb.cpu_used = cpu_used
        sb.memory_used = memory_used
        sb.updated_at = time.time()

        exceeded = False
        if sb.cpu_used > sb.cpu_limit:
            exceeded = True
        if sb.memory_used > sb.memory_limit:
            exceeded = True

        if exceeded:
            self._record_event(sandbox_id, sb.agent, "limit_exceeded")
            self._fire("limit_exceeded", {
                "sandbox_id": sandbox_id, "agent": sb.agent,
                "cpu_used": sb.cpu_used, "cpu_limit": sb.cpu_limit,
                "memory_used": sb.memory_used, "memory_limit": sb.memory_limit,
            })
        return True

    def check_limits(self, sandbox_id: str) -> Dict[str, Any]:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            return {"exists": False}
        return {
            "exists": True,
            "cpu_ok": sb.cpu_used <= sb.cpu_limit,
            "memory_ok": sb.memory_used <= sb.memory_limit,
            "cpu_used": sb.cpu_used,
            "cpu_limit": sb.cpu_limit,
            "memory_used": sb.memory_used,
            "memory_limit": sb.memory_limit,
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_sandboxes(self, status: str = "", agent: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for sb in self._sandboxes.values():
            if status and sb.status != status:
                continue
            if agent and sb.agent != agent:
                continue
            if tag and tag not in sb.tags:
                continue
            results.append(self.get_sandbox(sb.sandbox_id))
        return results

    def get_active_count(self) -> int:
        return sum(1 for sb in self._sandboxes.values() if sb.status == "active")

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(
        self,
        sandbox_id: str = "",
        agent: str = "",
        action: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if sandbox_id and ev.sandbox_id != sandbox_id:
                continue
            if agent and ev.agent != agent:
                continue
            if action and ev.action != action:
                continue
            results.append({
                "event_id": ev.event_id,
                "sandbox_id": ev.sandbox_id,
                "agent": ev.agent,
                "action": ev.action,
                "timestamp": ev.timestamp,
            })
            if len(results) >= limit:
                break
        return results

    def _record_event(self, sandbox_id: str, agent: str, action: str) -> None:
        self._seq += 1
        self._total_events += 1
        now = time.time()
        raw = f"{sandbox_id}-{action}-{now}-{self._seq}"
        evid = "sev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        event = _SandboxEvent(
            event_id=evid, sandbox_id=sandbox_id, agent=agent,
            action=action, timestamp=now,
        )
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(event)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        active = sum(1 for sb in self._sandboxes.values() if sb.status == "active")
        paused = sum(1 for sb in self._sandboxes.values() if sb.status == "paused")
        return {
            "current_sandboxes": len(self._sandboxes),
            "active_sandboxes": active,
            "paused_sandboxes": paused,
            "total_created": self._total_created,
            "total_terminated": self._total_terminated,
            "total_events": self._total_events,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._sandboxes.clear()
        self._agent_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_terminated = 0
        self._total_events = 0
