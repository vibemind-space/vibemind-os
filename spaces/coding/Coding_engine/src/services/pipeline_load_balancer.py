"""Pipeline load balancer - distributes work across pipeline instances."""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class InstanceEntry:
    registration_id: str
    pipeline_id: str
    instance_id: str
    capacity: int
    current_load: float
    created_at: float


class PipelineLoadBalancer:
    """Distribute requests across pipeline instances based on current load."""

    def __init__(self, max_entries: int = 10000):
        self._instances: Dict[str, InstanceEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries: int = max_entries

    # ── ID Generation ──

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"plb-{self._seq}-{id(self)}"
        return "plb-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ── Instance Registration ──

    def register_instance(self, pipeline_id: str, instance_id: str,
                          capacity: int = 100) -> str:
        """Register a pipeline instance and return a registration_id."""
        if not pipeline_id or not instance_id:
            return ""
        if capacity < 1:
            return ""

        # Prune if over limit
        if len(self._instances) >= self._max_entries:
            self._prune()

        reg_id = self._generate_id()
        self._instances[reg_id] = InstanceEntry(
            registration_id=reg_id,
            pipeline_id=pipeline_id,
            instance_id=instance_id,
            capacity=capacity,
            current_load=0.0,
            created_at=time.time(),
        )
        self._fire("register", {"registration_id": reg_id, "pipeline_id": pipeline_id,
                                 "instance_id": instance_id})
        return reg_id

    def get_instance(self, registration_id: str) -> Optional[Dict]:
        """Get instance details by registration_id."""
        entry = self._instances.get(registration_id)
        if not entry:
            return None
        return {
            "registration_id": entry.registration_id,
            "pipeline_id": entry.pipeline_id,
            "instance_id": entry.instance_id,
            "capacity": entry.capacity,
            "current_load": entry.current_load,
            "created_at": entry.created_at,
        }

    def remove_instance(self, registration_id: str) -> bool:
        """Remove an instance by registration_id."""
        if registration_id not in self._instances:
            return False
        entry = self._instances.pop(registration_id)
        self._fire("remove", {"registration_id": registration_id,
                               "pipeline_id": entry.pipeline_id,
                               "instance_id": entry.instance_id})
        return True

    # ── Routing ──

    def route_request(self, pipeline_id: str) -> Optional[str]:
        """Route a request to the least loaded instance for the given pipeline."""
        candidates = [
            e for e in self._instances.values()
            if e.pipeline_id == pipeline_id and e.current_load < e.capacity
        ]
        if not candidates:
            return None
        # Pick instance with lowest utilization ratio
        best = min(candidates, key=lambda e: e.current_load / e.capacity if e.capacity > 0 else 0.0)
        return best.instance_id

    # ── Load Tracking ──

    def record_load(self, pipeline_id: str, instance_id: str, load: float) -> bool:
        """Record the current load for a specific pipeline instance."""
        for entry in self._instances.values():
            if entry.pipeline_id == pipeline_id and entry.instance_id == instance_id:
                entry.current_load = max(0.0, load)
                self._fire("load", {"pipeline_id": pipeline_id,
                                     "instance_id": instance_id, "load": load})
                return True
        return False

    def get_instance_load(self, pipeline_id: str, instance_id: str) -> float:
        """Get the current load for a specific pipeline instance."""
        for entry in self._instances.values():
            if entry.pipeline_id == pipeline_id and entry.instance_id == instance_id:
                return entry.current_load
        return 0.0

    # ── Queries ──

    def get_pipeline_instances(self, pipeline_id: str) -> List[Dict]:
        """Get all instances registered for a pipeline."""
        results = []
        for entry in self._instances.values():
            if entry.pipeline_id == pipeline_id:
                results.append({
                    "registration_id": entry.registration_id,
                    "pipeline_id": entry.pipeline_id,
                    "instance_id": entry.instance_id,
                    "capacity": entry.capacity,
                    "current_load": entry.current_load,
                    "created_at": entry.created_at,
                })
        return results

    def list_pipelines(self) -> List[str]:
        """List all unique pipeline IDs."""
        seen: set = set()
        result: List[str] = []
        for entry in self._instances.values():
            if entry.pipeline_id not in seen:
                seen.add(entry.pipeline_id)
                result.append(entry.pipeline_id)
        return result

    def get_instance_count(self) -> int:
        """Return total number of registered instances."""
        return len(self._instances)

    # ── Callbacks ──

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a callback for change events."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name."""
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

    # ── Pruning ──

    def _prune(self) -> None:
        """Remove oldest entries when over max_entries."""
        if len(self._instances) < self._max_entries:
            return
        sorted_entries = sorted(self._instances.values(), key=lambda e: e.created_at)
        remove_count = len(self._instances) - (self._max_entries // 2)
        for entry in sorted_entries[:remove_count]:
            self._instances.pop(entry.registration_id, None)

    # ── Stats ──

    def get_stats(self) -> Dict:
        """Return summary statistics."""
        total_capacity = sum(e.capacity for e in self._instances.values())
        total_load = sum(e.current_load for e in self._instances.values())
        pipelines = self.list_pipelines()
        return {
            "instance_count": len(self._instances),
            "pipeline_count": len(pipelines),
            "total_capacity": total_capacity,
            "total_load": total_load,
            "avg_utilization": total_load / total_capacity if total_capacity > 0 else 0.0,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._instances.clear()
        self._callbacks.clear()
        self._seq = 0
