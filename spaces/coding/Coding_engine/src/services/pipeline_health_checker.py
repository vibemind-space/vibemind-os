"""Pipeline Health Checker – performs periodic health checks on pipeline components.

Registers health check endpoints, runs checks with configurable intervals,
tracks check history, and raises alerts when components become unhealthy.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _HealthCheck:
    check_id: str
    name: str
    component: str
    check_fn: Optional[Callable]  # returns True/False
    interval_ms: float
    timeout_ms: float
    status: str  # healthy | unhealthy | degraded | unknown
    enabled: bool
    consecutive_failures: int
    failure_threshold: int
    last_checked: float
    last_result: bool
    tags: List[str]
    created_at: float
    seq: int


@dataclass
class _CheckResult:
    result_id: str
    check_id: str
    passed: bool
    duration_ms: float
    message: str
    timestamp: float
    seq: int


class PipelineHealthChecker:
    """Registers and runs health checks on pipeline components."""

    STATUSES = ("healthy", "unhealthy", "degraded", "unknown")

    def __init__(self, max_checks: int = 1000,
                 max_results: int = 500000) -> None:
        self._max_checks = max_checks
        self._max_results = max_results
        self._checks: Dict[str, _HealthCheck] = {}
        self._results: Dict[str, _CheckResult] = {}
        self._name_index: Dict[str, str] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_checks_created": 0,
            "total_runs": 0,
            "total_passes": 0,
            "total_failures": 0,
        }

    # ------------------------------------------------------------------
    # Check registration
    # ------------------------------------------------------------------

    def register_check(self, name: str, component: str = "",
                       check_fn: Optional[Callable] = None,
                       interval_ms: float = 30000.0,
                       timeout_ms: float = 5000.0,
                       failure_threshold: int = 3,
                       tags: Optional[List[str]] = None) -> str:
        if not name:
            return ""
        if name in self._name_index:
            return ""
        if len(self._checks) >= self._max_checks:
            return ""
        self._seq += 1
        raw = f"hc-{name}-{component}-{self._seq}-{len(self._checks)}"
        cid = "hc-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        hc = _HealthCheck(
            check_id=cid, name=name, component=component,
            check_fn=check_fn, interval_ms=interval_ms,
            timeout_ms=timeout_ms, status="unknown", enabled=True,
            consecutive_failures=0, failure_threshold=failure_threshold,
            last_checked=0.0, last_result=False,
            tags=list(tags or []), created_at=time.time(), seq=self._seq,
        )
        self._checks[cid] = hc
        self._name_index[name] = cid
        self._stats["total_checks_created"] += 1
        self._fire("check_registered", {"check_id": cid, "name": name})
        return cid

    def get_check(self, check_id: str) -> Optional[Dict]:
        hc = self._checks.get(check_id)
        if hc is None:
            return None
        return self._hc_to_dict(hc)

    def get_check_by_name(self, name: str) -> Optional[Dict]:
        cid = self._name_index.get(name)
        if cid is None:
            return None
        return self.get_check(cid)

    def remove_check(self, check_id: str) -> bool:
        hc = self._checks.get(check_id)
        if hc is None:
            return False
        self._name_index.pop(hc.name, None)
        del self._checks[check_id]
        # Cascade results
        to_remove = [r for r in self._results.values() if r.check_id == check_id]
        for r in to_remove:
            del self._results[r.result_id]
        return True

    def enable_check(self, check_id: str) -> bool:
        hc = self._checks.get(check_id)
        if hc is None or hc.enabled:
            return False
        hc.enabled = True
        return True

    def disable_check(self, check_id: str) -> bool:
        hc = self._checks.get(check_id)
        if hc is None or not hc.enabled:
            return False
        hc.enabled = False
        return True

    # ------------------------------------------------------------------
    # Run checks
    # ------------------------------------------------------------------

    def run_check(self, check_id: str, passed: bool,
                  duration_ms: float = 0.0, message: str = "") -> str:
        """Record a check result (manual or from check_fn)."""
        hc = self._checks.get(check_id)
        if hc is None:
            return ""
        if len(self._results) >= self._max_results:
            return ""
        self._seq += 1
        raw = f"cr-{check_id}-{self._seq}-{len(self._results)}"
        rid = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        cr = _CheckResult(
            result_id=rid, check_id=check_id, passed=passed,
            duration_ms=duration_ms, message=message,
            timestamp=time.time(), seq=self._seq,
        )
        self._results[rid] = cr
        hc.last_checked = cr.timestamp
        hc.last_result = passed
        self._stats["total_runs"] += 1
        if passed:
            hc.consecutive_failures = 0
            hc.status = "healthy"
            self._stats["total_passes"] += 1
        else:
            hc.consecutive_failures += 1
            self._stats["total_failures"] += 1
            if hc.consecutive_failures >= hc.failure_threshold:
                old_status = hc.status
                hc.status = "unhealthy"
                if old_status != "unhealthy":
                    self._fire("component_unhealthy", {
                        "check_id": check_id, "name": hc.name,
                        "consecutive_failures": hc.consecutive_failures,
                    })
            else:
                hc.status = "degraded"
        self._fire("check_completed", {"result_id": rid, "passed": passed})
        return rid

    def get_check_results(self, check_id: str, limit: int = 50) -> List[Dict]:
        results = []
        for cr in self._results.values():
            if cr.check_id != check_id:
                continue
            results.append(self._cr_to_dict(cr))
        results.sort(key=lambda x: x["seq"])
        if limit > 0:
            results = results[-limit:]
        return results

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_checks(self, status: str = "", component: str = "",
                    enabled: Optional[bool] = None,
                    tag: str = "") -> List[Dict]:
        results = []
        for hc in self._checks.values():
            if status and hc.status != status:
                continue
            if component and hc.component != component:
                continue
            if enabled is not None and hc.enabled != enabled:
                continue
            if tag and tag not in hc.tags:
                continue
            results.append(self._hc_to_dict(hc))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_overall_health(self) -> Dict:
        total = len(self._checks)
        healthy = sum(1 for hc in self._checks.values() if hc.status == "healthy")
        unhealthy = sum(1 for hc in self._checks.values() if hc.status == "unhealthy")
        degraded = sum(1 for hc in self._checks.values() if hc.status == "degraded")
        unknown = sum(1 for hc in self._checks.values() if hc.status == "unknown")
        if total == 0:
            overall = "unknown"
        elif unhealthy > 0:
            overall = "unhealthy"
        elif degraded > 0:
            overall = "degraded"
        elif unknown > 0 and healthy == 0:
            overall = "unknown"
        else:
            overall = "healthy"
        return {
            "overall": overall,
            "total": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "degraded": degraded,
            "unknown": unknown,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_checks": len(self._checks),
            "current_results": len(self._results),
        }

    def reset(self) -> None:
        self._checks.clear()
        self._results.clear()
        self._name_index.clear()
        self._seq = 0
        self._stats = {
            "total_checks_created": 0,
            "total_runs": 0,
            "total_passes": 0,
            "total_failures": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hc_to_dict(hc: _HealthCheck) -> Dict:
        return {
            "check_id": hc.check_id,
            "name": hc.name,
            "component": hc.component,
            "interval_ms": hc.interval_ms,
            "timeout_ms": hc.timeout_ms,
            "status": hc.status,
            "enabled": hc.enabled,
            "consecutive_failures": hc.consecutive_failures,
            "failure_threshold": hc.failure_threshold,
            "last_checked": hc.last_checked,
            "last_result": hc.last_result,
            "tags": list(hc.tags),
            "created_at": hc.created_at,
            "seq": hc.seq,
        }

    @staticmethod
    def _cr_to_dict(cr: _CheckResult) -> Dict:
        return {
            "result_id": cr.result_id,
            "check_id": cr.check_id,
            "passed": cr.passed,
            "duration_ms": cr.duration_ms,
            "message": cr.message,
            "timestamp": cr.timestamp,
            "seq": cr.seq,
        }
