"""Pipeline Chaos Tester – chaos testing framework for pipeline resilience.

Injects controlled failures (latency, errors, resource exhaustion, network
partitions) into pipeline stages to verify fault tolerance and measure
resilience scores.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _ChaosTarget:
    target_id: str
    name: str
    target_type: str  # stage, service, agent
    tags: List[str]
    created_at: float


@dataclass
class _ChaosExperiment:
    experiment_id: str
    name: str
    target: str
    chaos_type: str  # error, latency, resource, partition
    intensity: float
    duration: float
    status: str  # created, running, stopped, completed
    fault_count: int
    start_time: float
    stop_time: float
    tags: List[str]
    created_at: float


@dataclass
class _ChaosObservation:
    observation_id: str
    experiment_name: str
    metric_name: str
    value: float
    tags: List[str]
    timestamp: float


@dataclass
class _ChaosEvent:
    event_id: str
    experiment_name: str
    action: str
    data: Dict[str, Any]
    timestamp: float


class PipelineChaosTester:
    """Chaos testing framework for pipeline resilience."""

    TARGET_TYPES = ("stage", "service", "agent")
    CHAOS_TYPES = ("error", "latency", "resource", "partition")

    def __init__(self, max_experiments: int = 5000, max_history: int = 100000):
        self._targets: Dict[str, _ChaosTarget] = {}
        self._target_name_index: Dict[str, str] = {}
        self._experiments: Dict[str, _ChaosExperiment] = {}
        self._experiment_name_index: Dict[str, str] = {}
        self._observations: List[_ChaosObservation] = []
        self._history: List[Dict[str, Any]] = []
        self._callbacks: Dict[str, Callable] = {}
        self._max_experiments = max_experiments
        self._max_history = max_history
        self._seq = 0
        self._total_targets_created = 0
        self._total_experiments_created = 0
        self._total_observations_recorded = 0
        self._total_faults_injected = 0

    # ── Targets ──

    def register_target(self, name: str, target_type: str = "stage", tags: Optional[List[str]] = None) -> str:
        if not name or target_type not in self.TARGET_TYPES:
            return ""
        if name in self._target_name_index:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}"
        tid = "ctg-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        self._targets[tid] = _ChaosTarget(
            target_id=tid,
            name=name,
            target_type=target_type,
            tags=tags or [],
            created_at=now,
        )
        self._target_name_index[name] = tid
        self._total_targets_created += 1
        self._record("target_registered", name)
        self._fire("target_registered", {"name": name, "target_type": target_type})
        return tid

    def list_targets(self, target_type: str = "") -> List[Dict[str, Any]]:
        results = []
        for tgt in self._targets.values():
            if target_type and tgt.target_type != target_type:
                continue
            results.append({
                "target_id": tgt.target_id,
                "name": tgt.name,
                "target_type": tgt.target_type,
                "tags": list(tgt.tags),
                "created_at": tgt.created_at,
            })
        return results

    # ── Experiments ──

    def create_experiment(self, name: str, target: str, chaos_type: str = "error",
                          intensity: float = 50.0, duration: float = 60.0,
                          tags: Optional[List[str]] = None) -> str:
        if not name or not target:
            return ""
        if chaos_type not in self.CHAOS_TYPES:
            return ""
        if name in self._experiment_name_index:
            return ""
        if len(self._experiments) >= self._max_experiments:
            return ""
        if target not in self._target_name_index:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{name}-{target}-{now}-{self._seq}"
        eid = "cex-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        self._experiments[eid] = _ChaosExperiment(
            experiment_id=eid,
            name=name,
            target=target,
            chaos_type=chaos_type,
            intensity=max(0.0, min(100.0, intensity)),
            duration=max(0.0, duration),
            status="created",
            fault_count=0,
            start_time=0.0,
            stop_time=0.0,
            tags=tags or [],
            created_at=now,
        )
        self._experiment_name_index[name] = eid
        self._total_experiments_created += 1
        self._record("experiment_created", name)
        self._fire("experiment_created", {"name": name, "chaos_type": chaos_type, "target": target})
        return eid

    def start_experiment(self, name: str) -> bool:
        eid = self._experiment_name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "created":
            return False
        exp.status = "running"
        exp.start_time = time.time()
        self._record("experiment_started", name)
        self._fire("experiment_started", {"name": name})
        return True

    def stop_experiment(self, name: str) -> bool:
        eid = self._experiment_name_index.get(name)
        if not eid:
            return False
        exp = self._experiments[eid]
        if exp.status != "running":
            return False
        exp.status = "stopped"
        exp.stop_time = time.time()
        self._record("experiment_stopped", name)
        self._fire("experiment_stopped", {"name": name})
        return True

    def inject_fault(self, experiment_name: str) -> Dict[str, Any]:
        eid = self._experiment_name_index.get(experiment_name)
        if not eid:
            return {}
        exp = self._experiments[eid]
        if exp.status != "running":
            return {}
        exp.fault_count += 1
        self._total_faults_injected += 1
        result: Dict[str, Any] = {}
        if exp.chaos_type == "error":
            result = {"injected": True, "type": "error", "detail": "simulated_500"}
        elif exp.chaos_type == "latency":
            added_ms = exp.intensity * random.uniform(0.5, 1.5)
            result = {"injected": True, "type": "latency", "added_ms": round(added_ms, 2)}
        elif exp.chaos_type == "resource":
            result = {"injected": True, "type": "resource", "cpu_spike": exp.intensity}
        elif exp.chaos_type == "partition":
            result = {"injected": True, "type": "partition", "isolated": True}
        self._record("fault_injected", experiment_name)
        self._fire("fault_injected", {"name": experiment_name, "result": result})
        return result

    def record_observation(self, experiment_name: str, metric_name: str, value: float,
                           tags: Optional[List[str]] = None) -> str:
        eid = self._experiment_name_index.get(experiment_name)
        if not eid:
            return ""
        self._seq += 1
        now = time.time()
        raw = f"{experiment_name}-{metric_name}-{now}-{self._seq}"
        oid = "cob-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        self._observations.append(_ChaosObservation(
            observation_id=oid,
            experiment_name=experiment_name,
            metric_name=metric_name,
            value=value,
            tags=tags or [],
            timestamp=now,
        ))
        self._total_observations_recorded += 1
        self._record("observation_recorded", experiment_name)
        return oid

    def get_experiment(self, name: str) -> Optional[Dict[str, Any]]:
        eid = self._experiment_name_index.get(name)
        if not eid:
            return None
        exp = self._experiments[eid]
        obs_count = sum(1 for o in self._observations if o.experiment_name == name)
        return {
            "experiment_id": exp.experiment_id,
            "name": exp.name,
            "target": exp.target,
            "chaos_type": exp.chaos_type,
            "intensity": exp.intensity,
            "duration": exp.duration,
            "status": exp.status,
            "fault_count": exp.fault_count,
            "fault_injections": exp.fault_count,
            "observations_count": obs_count,
            "start_time": exp.start_time,
            "stop_time": exp.stop_time,
            "tags": list(exp.tags),
            "created_at": exp.created_at,
        }

    def get_experiment_report(self, name: str) -> Dict[str, Any]:
        eid = self._experiment_name_index.get(name)
        if not eid:
            return {}
        exp = self._experiments[eid]
        obs = [o for o in self._observations if o.experiment_name == name]
        total_faults = exp.fault_count
        total_observations = len(obs)
        values = [o.value for o in obs]
        mean_value = (sum(values) / len(values)) if values else 0.0
        # Resilience score: higher is better. Based on low error observations
        # relative to faults injected. If no faults, score is 100.
        if total_faults > 0:
            # Lower mean observation value relative to intensity = more resilient
            ratio = mean_value / max(exp.intensity, 1.0)
            resilience_score = max(0.0, min(100.0, 100.0 - ratio * 50.0))
        else:
            resilience_score = 100.0
        return {
            "name": name,
            "chaos_type": exp.chaos_type,
            "status": exp.status,
            "total_faults": total_faults,
            "total_observations": total_observations,
            "mean_observation_value": round(mean_value, 4),
            "resilience_score": round(resilience_score, 2),
        }

    def list_experiments(self, status: str = "", chaos_type: str = "") -> List[Dict[str, Any]]:
        results = []
        for exp in self._experiments.values():
            if status and exp.status != status:
                continue
            if chaos_type and exp.chaos_type != chaos_type:
                continue
            info = self.get_experiment(exp.name)
            if info:
                results.append(info)
        return results

    def remove_experiment(self, name: str) -> bool:
        eid = self._experiment_name_index.pop(name, None)
        if not eid:
            return False
        self._experiments.pop(eid, None)
        self._record("experiment_removed", name)
        self._fire("experiment_removed", {"name": name})
        return True

    # ── History ──

    def _record(self, action: str, experiment_name: str) -> None:
        self._seq += 1
        now = time.time()
        raw = f"{experiment_name}-{action}-{now}-{self._seq}"
        evid = "cev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append({
            "event_id": evid,
            "experiment_name": experiment_name,
            "action": action,
            "timestamp": now,
        })

    def get_history(self, limit: int = 50, experiment_name: str = "", action: str = "") -> List[Dict[str, Any]]:
        results = []
        for ev in reversed(self._history):
            if experiment_name and ev["experiment_name"] != experiment_name:
                continue
            if action and ev["action"] != action:
                continue
            results.append(ev)
            if len(results) >= limit:
                break
        return results

    # ── Callbacks ──

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

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        running = sum(1 for e in self._experiments.values() if e.status == "running")
        return {
            "current_targets": len(self._targets),
            "current_experiments": len(self._experiments),
            "running_experiments": running,
            "total_targets_created": self._total_targets_created,
            "total_experiments_created": self._total_experiments_created,
            "total_observations_recorded": self._total_observations_recorded,
            "total_faults_injected": self._total_faults_injected,
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._targets.clear()
        self._target_name_index.clear()
        self._experiments.clear()
        self._experiment_name_index.clear()
        self._observations.clear()
        self._history.clear()
        self._callbacks.clear()
        self._seq = 0
        self._total_targets_created = 0
        self._total_experiments_created = 0
        self._total_observations_recorded = 0
        self._total_faults_injected = 0
