"""Pipeline Deployment Manager – manages pipeline deployments.

Tracks deployment history, supports blue-green and canary strategies,
and manages rollback to previous deployments.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Deployment:
    deployment_id: str
    name: str
    version: str
    strategy: str  # direct, blue_green, canary
    status: str  # pending, deploying, active, rolled_back, failed
    environment: str
    config: Dict[str, Any]
    tags: List[str]
    created_at: float
    updated_at: float


class PipelineDeploymentManager:
    """Manages pipeline deployments."""

    STRATEGIES = ("direct", "blue_green", "canary")
    STATUSES = ("pending", "deploying", "active", "rolled_back", "failed")

    def __init__(self, max_deployments: int = 50000, max_history: int = 100000):
        self._deployments: Dict[str, _Deployment] = {}
        self._active: Dict[str, str] = {}  # environment -> deployment_id
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_deployments = max_deployments
        self._max_history = max_history
        self._seq = 0
        self._total_created = 0
        self._total_rollbacks = 0

    def create_deployment(self, name: str, version: str, strategy: str = "direct", environment: str = "production", config: Optional[Dict[str, Any]] = None, tags: Optional[List[str]] = None) -> str:
        if not name or not version:
            return ""
        if strategy not in self.STRATEGIES:
            return ""
        if len(self._deployments) >= self._max_deployments:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{version}-{now}-{self._seq}"
        did = "dep-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        dep = _Deployment(deployment_id=did, name=name, version=version, strategy=strategy, status="pending", environment=environment, config=config or {}, tags=tags or [], created_at=now, updated_at=now)
        self._deployments[did] = dep
        self._total_created += 1
        self._record("created", did, name)
        self._fire("deployment_created", {"deployment_id": did, "name": name, "version": version})
        return did

    def deploy(self, deployment_id: str) -> bool:
        dep = self._deployments.get(deployment_id)
        if not dep or dep.status != "pending":
            return False
        # Deactivate current active in same environment
        old_active = self._active.get(dep.environment)
        if old_active and old_active in self._deployments:
            self._deployments[old_active].status = "rolled_back"
        dep.status = "active"
        dep.updated_at = time.time()
        self._active[dep.environment] = deployment_id
        self._record("deployed", deployment_id, dep.name)
        self._fire("deployment_active", {"deployment_id": deployment_id, "name": dep.name, "environment": dep.environment})
        return True

    def rollback(self, environment: str) -> bool:
        current_id = self._active.get(environment)
        if not current_id:
            return False
        dep = self._deployments.get(current_id)
        if not dep:
            return False
        dep.status = "rolled_back"
        dep.updated_at = time.time()
        self._active.pop(environment, None)
        self._total_rollbacks += 1
        self._record("rolled_back", current_id, dep.name)
        self._fire("deployment_rolled_back", {"deployment_id": current_id, "environment": environment})
        return True

    def fail_deployment(self, deployment_id: str) -> bool:
        dep = self._deployments.get(deployment_id)
        if not dep or dep.status not in ("pending", "deploying"):
            return False
        dep.status = "failed"
        dep.updated_at = time.time()
        self._record("failed", deployment_id, dep.name)
        return True

    def get_deployment(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        dep = self._deployments.get(deployment_id)
        if not dep:
            return None
        return {"deployment_id": dep.deployment_id, "name": dep.name, "version": dep.version, "strategy": dep.strategy, "status": dep.status, "environment": dep.environment, "config": dict(dep.config), "tags": list(dep.tags), "created_at": dep.created_at, "updated_at": dep.updated_at}

    def get_active(self, environment: str) -> Optional[Dict[str, Any]]:
        did = self._active.get(environment)
        if not did:
            return None
        return self.get_deployment(did)

    def list_deployments(self, name: str = "", environment: str = "", status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for dep in self._deployments.values():
            if name and dep.name != name:
                continue
            if environment and dep.environment != environment:
                continue
            if status and dep.status != status:
                continue
            if tag and tag not in dep.tags:
                continue
            results.append(self.get_deployment(dep.deployment_id))
        return [r for r in results if r]

    def _record(self, action: str, deployment_id: str, name: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{name}-{action}-{now}-{self._seq}"
        evid = "dev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append({"event_id": evid, "deployment_id": deployment_id, "name": name, "action": action, "timestamp": now})

    def get_history(self, name: str = "", action: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if name and ev["name"] != name:
                continue
            if action and ev["action"] != action:
                continue
            results.append(ev)
            if len(results) >= limit:
                break
        return results

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

    def get_stats(self) -> Dict[str, Any]:
        active = sum(1 for d in self._deployments.values() if d.status == "active")
        return {"current_deployments": len(self._deployments), "active_deployments": active, "total_created": self._total_created, "total_rollbacks": self._total_rollbacks, "history_size": len(self._history)}

    def reset(self) -> None:
        self._deployments.clear()
        self._active.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
        self._total_rollbacks = 0
