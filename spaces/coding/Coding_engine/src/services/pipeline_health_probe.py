"""Pipeline health probing - monitors pipeline health status."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ProbeEntry:
    """Represents a registered health probe for a pipeline."""

    probe_id: str
    pipeline_id: str
    check_interval: int
    timeout: int
    checks: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class PipelineHealthProbe:
    """Monitors pipeline health status through periodic probing."""

    def __init__(self) -> None:
        self._probes: Dict[str, ProbeEntry] = {}
        self._pipeline_map: Dict[str, str] = {}
        self._callbacks: Dict[str, List[Callable]] = {
            "on_change": [],
            "on_remove": [],
        }
        self._seq: int = 0
        self._max_entries: int = 10000

    # ------------------------------------------------------------------ #
    #  ID generation
    # ------------------------------------------------------------------ #

    def _generate_id(self) -> str:
        self._seq += 1
        raw = f"php-{self._seq}-{id(self)}"
        return "php-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------ #
    #  Callback infrastructure
    # ------------------------------------------------------------------ #

    def on_change(self, callback: Callable) -> None:
        """Register a callback invoked when a probe check is recorded."""
        self._callbacks["on_change"].append(callback)

    def remove_callback(self, callback: Callable) -> None:
        """Remove a previously registered callback."""
        for key in self._callbacks:
            if callback in self._callbacks[key]:
                self._callbacks[key].remove(callback)

    def _fire(self, event: str, data: Any) -> None:
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  Pruning
    # ------------------------------------------------------------------ #

    def _prune(self) -> None:
        """Remove oldest probes when the store exceeds *_max_entries*."""
        if len(self._probes) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._probes,
            key=lambda pid: self._probes[pid].created_at,
        )
        to_remove = len(self._probes) - self._max_entries
        for probe_id in sorted_ids[:to_remove]:
            entry = self._probes.pop(probe_id)
            self._pipeline_map.pop(entry.pipeline_id, None)
            self._fire("on_remove", {"probe_id": probe_id, "pipeline_id": entry.pipeline_id})

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def register_probe(
        self,
        pipeline_id: str,
        check_interval: int = 60,
        timeout: int = 10,
    ) -> str:
        """Register a health probe for *pipeline_id*.

        Returns the generated probe id (``"php-..."``).
        """
        if pipeline_id in self._pipeline_map:
            return self._pipeline_map[pipeline_id]

        probe_id = self._generate_id()
        entry = ProbeEntry(
            probe_id=probe_id,
            pipeline_id=pipeline_id,
            check_interval=check_interval,
            timeout=timeout,
        )
        self._probes[probe_id] = entry
        self._pipeline_map[pipeline_id] = probe_id
        self._prune()
        return probe_id

    def get_probe(self, probe_id: str) -> Optional[Dict[str, Any]]:
        """Return probe information or ``None`` if not found."""
        entry = self._probes.get(probe_id)
        if entry is None:
            return None
        return {
            "probe_id": entry.probe_id,
            "pipeline_id": entry.pipeline_id,
            "check_interval": entry.check_interval,
            "timeout": entry.timeout,
            "checks": list(entry.checks),
            "created_at": entry.created_at,
        }

    def record_check(
        self,
        pipeline_id: str,
        healthy: bool,
        latency: float = 0.0,
    ) -> Dict[str, Any]:
        """Record a health-check result for *pipeline_id*.

        If no probe is registered for the pipeline, one is created
        automatically with default settings.
        """
        if pipeline_id not in self._pipeline_map:
            self.register_probe(pipeline_id)

        probe_id = self._pipeline_map[pipeline_id]
        entry = self._probes[probe_id]

        check_info: Dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "probe_id": probe_id,
            "healthy": healthy,
            "latency": latency,
            "timestamp": time.time(),
        }
        entry.checks.append(check_info)
        self._fire("on_change", check_info)
        return check_info

    def get_health_status(self, pipeline_id: str) -> str:
        """Return the current health status of *pipeline_id*.

        Possible values: ``"healthy"``, ``"unhealthy"``, ``"unknown"``.
        """
        probe_id = self._pipeline_map.get(pipeline_id)
        if probe_id is None:
            return "unknown"

        entry = self._probes.get(probe_id)
        if entry is None or not entry.checks:
            return "unknown"

        last_check = entry.checks[-1]
        return "healthy" if last_check.get("healthy") else "unhealthy"

    def get_check_history(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return the list of recorded checks for *pipeline_id*."""
        probe_id = self._pipeline_map.get(pipeline_id)
        if probe_id is None:
            return []

        entry = self._probes.get(probe_id)
        if entry is None:
            return []

        return list(entry.checks)

    def get_uptime(self, pipeline_id: str) -> float:
        """Return the uptime percentage (0.0-100.0) for *pipeline_id*."""
        probe_id = self._pipeline_map.get(pipeline_id)
        if probe_id is None:
            return 0.0

        entry = self._probes.get(probe_id)
        if entry is None or not entry.checks:
            return 0.0

        healthy_count = sum(1 for c in entry.checks if c.get("healthy"))
        return (healthy_count / len(entry.checks)) * 100.0

    def remove_probe(self, probe_id: str) -> bool:
        """Remove a probe by its id. Returns ``True`` if it existed."""
        entry = self._probes.pop(probe_id, None)
        if entry is None:
            return False

        self._pipeline_map.pop(entry.pipeline_id, None)
        self._fire("on_remove", {"probe_id": probe_id, "pipeline_id": entry.pipeline_id})
        return True

    def list_pipelines(self) -> List[str]:
        """Return a list of all monitored pipeline ids."""
        return list(self._pipeline_map.keys())

    def get_probe_count(self) -> int:
        """Return the number of registered probes."""
        return len(self._probes)

    # ------------------------------------------------------------------ #
    #  Stats / reset
    # ------------------------------------------------------------------ #

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about the probe store."""
        total_checks = sum(len(e.checks) for e in self._probes.values())
        return {
            "probe_count": len(self._probes),
            "pipeline_count": len(self._pipeline_map),
            "total_checks": total_checks,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all probes and pipeline mappings."""
        self._probes.clear()
        self._pipeline_map.clear()
        self._seq = 0
