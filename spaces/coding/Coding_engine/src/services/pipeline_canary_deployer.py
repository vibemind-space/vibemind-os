"""Pipeline Canary Deployer -- manages canary deployments with metric comparison.

Provides controlled canary rollouts for pipeline stages, tracking baseline and
canary metrics side-by-side.  Supports automatic rollback when error rate or
latency thresholds are exceeded.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _DeploymentEntry:
    deployment_id: str
    name: str
    baseline_version: str
    canary_version: str
    status: str  # active, promoted, rolled_back
    traffic_pct: float
    tags: List[str]
    metrics: Dict[str, Dict[str, List[float]]]  # {metric_name: {"baseline": [...], "canary": [...]}}
    created_at: float
    updated_at: float


class PipelineCanaryDeployer:
    """Manages canary deployments with metric tracking and automatic rollback."""

    def __init__(self, max_entries: int = 10000, max_history: int = 50000) -> None:
        self._entries: Dict[str, _DeploymentEntry] = {}
        self._name_index: Dict[str, str] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_entries = max_entries
        self._max_history = max_history
        self._seq = 0

        # counters
        self._total_created = 0
        self._total_promoted = 0
        self._total_rolled_back = 0
        self._total_removed = 0
        self._total_metrics_recorded = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, name: str) -> str:
        self._seq += 1
        raw = f"{name}-{time.time()}-{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pcd-{digest}"

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(self, action: str, detail: Dict[str, Any]) -> None:
        entry = {"action": action, "detail": detail, "ts": time.time()}
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._history[-limit:])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, fn: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = fn
        return True

    def remove_callback(self, name: str) -> bool:
        return self._callbacks.pop(name, None) is not None

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _maybe_prune(self) -> None:
        if len(self._entries) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._entries,
            key=lambda eid: self._entries[eid].updated_at,
        )
        to_remove = len(self._entries) - self._max_entries
        for eid in sorted_ids[:to_remove]:
            e = self._entries.pop(eid)
            self._name_index.pop(e.name, None)

    # ------------------------------------------------------------------
    # Deployment CRUD
    # ------------------------------------------------------------------

    def create_deployment(
        self,
        name: str,
        baseline_version: str,
        canary_version: str,
        traffic_pct: float = 10.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a canary deployment.  Returns deployment ID or '' on dup name."""
        if not name or not baseline_version or not canary_version:
            return ""
        if name in self._name_index:
            return ""
        if traffic_pct < 0.0 or traffic_pct > 100.0:
            return ""

        did = self._generate_id(name)
        now = time.time()
        entry = _DeploymentEntry(
            deployment_id=did,
            name=name,
            baseline_version=baseline_version,
            canary_version=canary_version,
            status="active",
            traffic_pct=traffic_pct,
            tags=list(tags) if tags else [],
            metrics={},
            created_at=now,
            updated_at=now,
        )
        self._entries[did] = entry
        self._name_index[name] = did
        self._total_created += 1
        self._maybe_prune()
        detail = {"deployment_id": did, "name": name, "traffic_pct": traffic_pct}
        self._record_history("create_deployment", detail)
        self._fire("create_deployment", detail)
        return did

    def get_deployment(self, name: str) -> Optional[Dict[str, Any]]:
        """Get deployment state by name."""
        did = self._name_index.get(name)
        if not did:
            return None
        e = self._entries.get(did)
        if not e:
            return None
        return self._entry_to_dict(e)

    def remove_deployment(self, name: str) -> bool:
        """Remove a deployment by name."""
        did = self._name_index.pop(name, None)
        if not did:
            return False
        e = self._entries.pop(did, None)
        if not e:
            return False
        self._total_removed += 1
        detail = {"deployment_id": did, "name": name}
        self._record_history("remove_deployment", detail)
        self._fire("remove_deployment", detail)
        return True

    def _entry_to_dict(self, e: _DeploymentEntry) -> Dict[str, Any]:
        return {
            "deployment_id": e.deployment_id,
            "name": e.name,
            "baseline_version": e.baseline_version,
            "canary_version": e.canary_version,
            "status": e.status,
            "traffic_pct": e.traffic_pct,
            "tags": list(e.tags),
            "metrics": {
                k: {"baseline": list(v.get("baseline", [])), "canary": list(v.get("canary", []))}
                for k, v in e.metrics.items()
            },
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }

    # ------------------------------------------------------------------
    # Traffic management
    # ------------------------------------------------------------------

    def update_traffic(self, name: str, traffic_pct: float) -> bool:
        """Adjust canary traffic percentage (0-100)."""
        did = self._name_index.get(name)
        if not did:
            return False
        e = self._entries.get(did)
        if not e or e.status != "active":
            return False
        if traffic_pct < 0.0 or traffic_pct > 100.0:
            return False
        old_pct = e.traffic_pct
        e.traffic_pct = traffic_pct
        e.updated_at = time.time()
        detail = {"deployment_id": did, "name": name, "old_pct": old_pct, "new_pct": traffic_pct}
        self._record_history("update_traffic", detail)
        self._fire("update_traffic", detail)
        return True

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def record_metric(self, name: str, version: str, metric_name: str, value: float) -> bool:
        """Record a performance metric for baseline or canary version."""
        did = self._name_index.get(name)
        if not did:
            return False
        e = self._entries.get(did)
        if not e:
            return False
        if version not in ("baseline", "canary"):
            return False
        if metric_name not in e.metrics:
            e.metrics[metric_name] = {"baseline": [], "canary": []}
        e.metrics[metric_name][version].append(value)
        e.updated_at = time.time()
        self._total_metrics_recorded += 1
        return True

    def compare(self, name: str) -> Dict[str, Any]:
        """Compare baseline vs canary metrics."""
        did = self._name_index.get(name)
        if not did:
            return {}
        e = self._entries.get(did)
        if not e:
            return {}
        result: Dict[str, Any] = {}
        for metric_name, versions in e.metrics.items():
            baseline_vals = versions.get("baseline", [])
            canary_vals = versions.get("canary", [])
            baseline_avg = sum(baseline_vals) / len(baseline_vals) if baseline_vals else 0.0
            canary_avg = sum(canary_vals) / len(canary_vals) if canary_vals else 0.0
            baseline_min = min(baseline_vals) if baseline_vals else 0.0
            baseline_max = max(baseline_vals) if baseline_vals else 0.0
            canary_min = min(canary_vals) if canary_vals else 0.0
            canary_max = max(canary_vals) if canary_vals else 0.0
            diff = canary_avg - baseline_avg
            pct_change = (diff / baseline_avg * 100.0) if baseline_avg != 0.0 else 0.0
            result[metric_name] = {
                "baseline": {
                    "count": len(baseline_vals),
                    "avg": baseline_avg,
                    "min": baseline_min,
                    "max": baseline_max,
                },
                "canary": {
                    "count": len(canary_vals),
                    "avg": canary_avg,
                    "min": canary_min,
                    "max": canary_max,
                },
                "diff": diff,
                "pct_change": pct_change,
            }
        return result

    # ------------------------------------------------------------------
    # Promote / Rollback
    # ------------------------------------------------------------------

    def promote(self, name: str) -> bool:
        """Promote canary to 100% traffic."""
        did = self._name_index.get(name)
        if not did:
            return False
        e = self._entries.get(did)
        if not e or e.status != "active":
            return False
        e.status = "promoted"
        e.traffic_pct = 100.0
        e.updated_at = time.time()
        self._total_promoted += 1
        detail = {"deployment_id": did, "name": name}
        self._record_history("promote", detail)
        self._fire("promote", detail)
        return True

    def rollback(self, name: str) -> bool:
        """Roll back canary to 0% traffic."""
        did = self._name_index.get(name)
        if not did:
            return False
        e = self._entries.get(did)
        if not e or e.status != "active":
            return False
        e.status = "rolled_back"
        e.traffic_pct = 0.0
        e.updated_at = time.time()
        self._total_rolled_back += 1
        detail = {"deployment_id": did, "name": name}
        self._record_history("rollback", detail)
        self._fire("rollback", detail)
        return True

    # ------------------------------------------------------------------
    # Auto-rollback check
    # ------------------------------------------------------------------

    def should_rollback(
        self,
        name: str,
        error_threshold: float = 5.0,
        latency_threshold: float = 200.0,
    ) -> bool:
        """Check if canary should be rolled back based on error rate and latency.

        error_threshold: maximum acceptable canary error_rate average.
        latency_threshold: maximum acceptable canary latency average.
        Returns True if any threshold is exceeded.
        """
        did = self._name_index.get(name)
        if not did:
            return False
        e = self._entries.get(did)
        if not e or e.status != "active":
            return False

        # Check error_rate metric
        error_data = e.metrics.get("error_rate", {})
        canary_errors = error_data.get("canary", [])
        if canary_errors:
            avg_error = sum(canary_errors) / len(canary_errors)
            if avg_error > error_threshold:
                return True

        # Check latency metric
        latency_data = e.metrics.get("latency", {})
        canary_latency = latency_data.get("canary", [])
        if canary_latency:
            avg_latency = sum(canary_latency) / len(canary_latency)
            if avg_latency > latency_threshold:
                return True

        return False

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_deployments(
        self,
        status: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List deployments, optionally filtered by status and/or tag."""
        results: List[Dict[str, Any]] = []
        for e in self._entries.values():
            if status and e.status != status:
                continue
            if tag and tag not in e.tags:
                continue
            results.append(self._entry_to_dict(e))
        return results

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "current_entries": len(self._entries),
            "total_created": self._total_created,
            "total_promoted": self._total_promoted,
            "total_rolled_back": self._total_rolled_back,
            "total_removed": self._total_removed,
            "total_metrics_recorded": self._total_metrics_recorded,
            "active_count": sum(1 for e in self._entries.values() if e.status == "active"),
            "promoted_count": sum(1 for e in self._entries.values() if e.status == "promoted"),
            "rolled_back_count": sum(
                1 for e in self._entries.values() if e.status == "rolled_back"
            ),
            "history_size": len(self._history),
            "callback_count": len(self._callbacks),
        }

    def reset(self) -> None:
        self._entries.clear()
        self._name_index.clear()
        self._callbacks.clear()
        self._history.clear()
        self._seq = 0
        self._total_created = 0
        self._total_promoted = 0
        self._total_rolled_back = 0
        self._total_removed = 0
        self._total_metrics_recorded = 0
