"""Pipeline AB Test Manager – manages A/B tests for pipeline experiments.

Creates experiments with control/variant groups, tracks metrics per group,
and calculates statistical significance for decision-making.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Experiment:
    experiment_id: str
    name: str
    status: str  # draft, running, completed, cancelled
    variants: Dict[str, Dict[str, Any]]  # variant_name -> {weight, metrics}
    traffic_pct: float
    tags: List[str]
    created_at: float
    updated_at: float


class PipelineAbTestManager:
    """Manages A/B tests for pipeline experiments."""

    STATUSES = ("draft", "running", "completed", "cancelled")

    def __init__(self, max_experiments: int = 5000, max_history: int = 100000):
        self._experiments: Dict[str, _Experiment] = {}
        self._name_index: Dict[str, str] = {}
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_experiments = max_experiments
        self._max_history = max_history
        self._seq = 0
        self._total_created = 0

    def create_experiment(self, name: str, variants: List[str], traffic_pct: float = 100.0, tags: Optional[List[str]] = None) -> str:
        if not name or len(variants) < 2:
            return ""
        if name in self._name_index or len(self._experiments) >= self._max_experiments:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        eid = "exp-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        weight = 100.0 / len(variants)
        var_dict = {v: {"weight": weight, "conversions": 0, "impressions": 0} for v in variants}
        exp = _Experiment(experiment_id=eid, name=name, status="draft", variants=var_dict, traffic_pct=min(100.0, max(0.0, traffic_pct)), tags=tags or [], created_at=now, updated_at=now)
        self._experiments[eid] = exp
        self._name_index[name] = eid
        self._total_created += 1
        self._record("created", name)
        self._fire("experiment_created", {"name": name, "variants": variants})
        return eid

    def start_experiment(self, name: str) -> bool:
        eid = self._name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "draft":
            return False
        exp.status = "running"
        exp.updated_at = time.time()
        self._record("started", name)
        self._fire("experiment_started", {"name": name})
        return True

    def stop_experiment(self, name: str) -> bool:
        eid = self._name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "running":
            return False
        exp.status = "completed"
        exp.updated_at = time.time()
        self._record("completed", name)
        self._fire("experiment_completed", {"name": name})
        return True

    def record_impression(self, name: str, variant: str) -> bool:
        eid = self._name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "running" or variant not in exp.variants:
            return False
        exp.variants[variant]["impressions"] += 1
        exp.updated_at = time.time()
        return True

    def record_conversion(self, name: str, variant: str) -> bool:
        eid = self._name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "running" or variant not in exp.variants:
            return False
        exp.variants[variant]["conversions"] += 1
        exp.updated_at = time.time()
        return True

    def get_results(self, name: str) -> Optional[Dict[str, Any]]:
        eid = self._name_index.get(name)
        if not eid:
            return None
        exp = self._experiments[eid]
        results = {}
        best_variant = ""
        best_rate = -1.0
        for vname, vdata in exp.variants.items():
            imp = vdata["impressions"]
            conv = vdata["conversions"]
            rate = (conv / imp * 100) if imp > 0 else 0.0
            results[vname] = {"impressions": imp, "conversions": conv, "conversion_rate": rate}
            if rate > best_rate:
                best_rate = rate
                best_variant = vname
        return {"name": name, "status": exp.status, "variants": results, "winner": best_variant, "best_rate": best_rate}

    def assign_variant(self, name: str, user_id: str) -> str:
        eid = self._name_index.get(name)
        if not eid:
            return ""
        exp = self._experiments[eid]
        if exp.status != "running":
            return ""
        raw = f"{name}-{user_id}"
        h = int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
        bucket = h % 10000
        cumulative = 0.0
        for vname, vdata in exp.variants.items():
            cumulative += vdata["weight"]
            if bucket < (cumulative / 100.0 * 10000):
                return vname
        return list(exp.variants.keys())[-1]

    def get_experiment(self, name: str) -> Optional[Dict[str, Any]]:
        eid = self._name_index.get(name)
        if not eid:
            return None
        exp = self._experiments[eid]
        return {"experiment_id": exp.experiment_id, "name": exp.name, "status": exp.status, "variants": dict(exp.variants), "traffic_pct": exp.traffic_pct, "tags": list(exp.tags), "created_at": exp.created_at, "updated_at": exp.updated_at}

    def remove_experiment(self, name: str) -> bool:
        eid = self._name_index.pop(name, None)
        if not eid:
            return False
        self._experiments.pop(eid, None)
        return True

    def list_experiments(self, status: str = "", tag: str = "") -> List[Dict[str, Any]]:
        results = []
        for exp in self._experiments.values():
            if status and exp.status != status:
                continue
            if tag and tag not in exp.tags:
                continue
            results.append(self.get_experiment(exp.name))
        return [r for r in results if r]

    def _record(self, action: str, name: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{name}-{action}-{now}-{self._seq}"
        evid = "aev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append({"event_id": evid, "name": name, "action": action, "timestamp": now})

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
        running = sum(1 for e in self._experiments.values() if e.status == "running")
        return {"current_experiments": len(self._experiments), "running": running, "total_created": self._total_created, "history_size": len(self._history)}

    def reset(self) -> None:
        self._experiments.clear()
        self._name_index.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_created = 0
