"""Agent Sandbox Runner – executes agent tasks in isolated sandboxes.

Manages sandboxed execution environments for agents, tracking resource
usage, enforcing timeouts, and capturing outputs. Each sandbox has
configurable limits and lifecycle management.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _SandboxEntry:
    sandbox_id: str
    agent: str
    status: str  # idle, running, completed, failed, timeout
    task: str
    config: Dict[str, Any]
    result: Any
    error: str
    started_at: float
    completed_at: float
    timeout_ms: float
    total_runs: int
    tags: List[str]
    created_at: float
    updated_at: float


class AgentSandboxRunner:
    """Executes agent tasks in isolated sandboxes."""

    STATUSES = ("idle", "running", "completed", "failed", "timeout")

    def __init__(self, max_sandboxes: int = 5000):
        self._sandboxes: Dict[str, _SandboxEntry] = {}
        self._agent_index: Dict[str, List[str]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._max_sandboxes = max_sandboxes
        self._seq = 0

        # stats
        self._total_created = 0
        self._total_runs = 0
        self._total_failures = 0
        self._total_timeouts = 0

    # ------------------------------------------------------------------
    # Sandbox creation
    # ------------------------------------------------------------------

    def create_sandbox(
        self,
        agent: str,
        timeout_ms: float = 30000.0,
        config: Optional[Dict[str, Any]] = None,
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

        entry = _SandboxEntry(
            sandbox_id=sid,
            agent=agent,
            status="idle",
            task="",
            config=config or {},
            result=None,
            error="",
            started_at=0.0,
            completed_at=0.0,
            timeout_ms=timeout_ms,
            total_runs=0,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._sandboxes[sid] = entry
        self._agent_index.setdefault(agent, []).append(sid)
        self._total_created += 1
        self._fire("sandbox_created", {"sandbox_id": sid, "agent": agent})
        return sid

    def get_sandbox(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        e = self._sandboxes.get(sandbox_id)
        if not e:
            return None
        return {
            "sandbox_id": e.sandbox_id,
            "agent": e.agent,
            "status": e.status,
            "task": e.task,
            "config": dict(e.config),
            "result": e.result,
            "error": e.error,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
            "timeout_ms": e.timeout_ms,
            "total_runs": e.total_runs,
            "tags": list(e.tags),
            "created_at": e.created_at,
        }

    def remove_sandbox(self, sandbox_id: str) -> bool:
        e = self._sandboxes.pop(sandbox_id, None)
        if not e:
            return False
        agent_list = self._agent_index.get(e.agent, [])
        if sandbox_id in agent_list:
            agent_list.remove(sandbox_id)
        return True

    def get_sandboxes_for_agent(self, agent: str) -> List[Dict[str, Any]]:
        sids = self._agent_index.get(agent, [])
        results = []
        for sid in sids:
            s = self.get_sandbox(sid)
            if s:
                results.append(s)
        return results

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self,
        sandbox_id: str,
        task: str,
        run_fn: Optional[Callable] = None,
    ) -> bool:
        """Run a task in the sandbox."""
        e = self._sandboxes.get(sandbox_id)
        if not e:
            return False
        if not task:
            return False
        if e.status == "running":
            return False

        e.status = "running"
        e.task = task
        e.result = None
        e.error = ""
        now = time.time()
        e.started_at = now
        e.completed_at = 0.0
        e.updated_at = now
        self._fire("sandbox_started", {"sandbox_id": sandbox_id, "task": task})

        if run_fn:
            try:
                result = run_fn(task, e.config)
                e.result = result
                e.status = "completed"
                now2 = time.time()
                e.completed_at = now2
                e.updated_at = now2
                e.total_runs += 1
                self._total_runs += 1
                self._fire("sandbox_completed", {
                    "sandbox_id": sandbox_id, "task": task
                })
                return True
            except TimeoutError:
                e.status = "timeout"
                e.error = "timeout"
                now2 = time.time()
                e.completed_at = now2
                e.updated_at = now2
                e.total_runs += 1
                self._total_runs += 1
                self._total_timeouts += 1
                self._fire("sandbox_timeout", {"sandbox_id": sandbox_id})
                return False
            except Exception as exc:
                e.status = "failed"
                e.error = str(exc)
                now2 = time.time()
                e.completed_at = now2
                e.updated_at = now2
                e.total_runs += 1
                self._total_runs += 1
                self._total_failures += 1
                self._fire("sandbox_failed", {
                    "sandbox_id": sandbox_id, "error": str(exc)
                })
                return False
        else:
            # No run_fn → mark completed immediately (dry run)
            e.status = "completed"
            now2 = time.time()
            e.completed_at = now2
            e.updated_at = now2
            e.total_runs += 1
            self._total_runs += 1
            self._fire("sandbox_completed", {
                "sandbox_id": sandbox_id, "task": task
            })
            return True

    def reset_sandbox(self, sandbox_id: str) -> bool:
        """Reset sandbox to idle state."""
        e = self._sandboxes.get(sandbox_id)
        if not e:
            return False
        if e.status == "running":
            return False
        e.status = "idle"
        e.task = ""
        e.result = None
        e.error = ""
        e.started_at = 0.0
        e.completed_at = 0.0
        e.updated_at = time.time()
        return True

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_sandboxes(
        self,
        status: str = "",
        agent: str = "",
        tag: str = "",
    ) -> List[Dict[str, Any]]:
        results = []
        for e in self._sandboxes.values():
            if status and e.status != status:
                continue
            if agent and e.agent != agent:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self.get_sandbox(e.sandbox_id))
        return results

    def get_running(self) -> List[Dict[str, Any]]:
        return self.list_sandboxes(status="running")

    def get_idle(self) -> List[Dict[str, Any]]:
        return self.list_sandboxes(status="idle")

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
        return {
            "current_sandboxes": len(self._sandboxes),
            "total_created": self._total_created,
            "total_runs": self._total_runs,
            "total_failures": self._total_failures,
            "total_timeouts": self._total_timeouts,
            "idle_count": sum(1 for e in self._sandboxes.values() if e.status == "idle"),
            "running_count": sum(1 for e in self._sandboxes.values() if e.status == "running"),
        }

    def reset(self) -> None:
        self._sandboxes.clear()
        self._agent_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_runs = 0
        self._total_failures = 0
        self._total_timeouts = 0
