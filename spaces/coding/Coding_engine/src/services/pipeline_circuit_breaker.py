"""Pipeline circuit breaker.

Implements the circuit breaker pattern to prevent cascading failures
in the pipeline. Monitors failure rates and automatically opens/closes
circuits to protect downstream services.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Circuit:
    """A circuit breaker."""
    circuit_id: str = ""
    name: str = ""
    service: str = ""
    state: str = "closed"  # closed, open, half_open
    failure_threshold: int = 5
    recovery_timeout_ms: float = 30000.0
    half_open_max_calls: int = 1
    success_count: int = 0
    failure_count: int = 0
    half_open_calls: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_trips: int = 0
    last_failure_at: float = 0.0
    last_state_change_at: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class PipelineCircuitBreaker:
    """Circuit breaker for pipeline resilience."""

    STATES = ("closed", "open", "half_open")

    def __init__(self, max_circuits: int = 10000):
        self._max_circuits = max_circuits
        self._circuits: Dict[str, _Circuit] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_circuits_created": 0,
            "total_calls": 0,
            "total_failures": 0,
            "total_trips": 0,
        }

    # ------------------------------------------------------------------
    # Circuits
    # ------------------------------------------------------------------

    def create_circuit(self, name: str, service: str = "",
                       failure_threshold: int = 5,
                       recovery_timeout_ms: float = 30000.0,
                       half_open_max_calls: int = 1,
                       tags: Optional[List[str]] = None,
                       metadata: Optional[Dict] = None) -> str:
        if not name or not name.strip():
            return ""
        if failure_threshold < 1:
            return ""
        if len(self._circuits) >= self._max_circuits:
            return ""

        self._seq += 1
        now = time.time()
        raw = f"{name}-{now}-{self._seq}-{len(self._circuits)}"
        cid = "cb-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

        self._circuits[cid] = _Circuit(
            circuit_id=cid,
            name=name,
            service=service,
            failure_threshold=failure_threshold,
            recovery_timeout_ms=recovery_timeout_ms,
            half_open_max_calls=half_open_max_calls,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            created_at=now,
            last_state_change_at=now,
            seq=self._seq,
        )
        self._stats["total_circuits_created"] += 1
        self._fire("circuit_created", {"circuit_id": cid, "name": name})
        return cid

    def get_circuit(self, circuit_id: str) -> Optional[Dict]:
        c = self._circuits.get(circuit_id)
        if not c:
            return None
        return {
            "circuit_id": c.circuit_id, "name": c.name,
            "service": c.service, "state": c.state,
            "failure_threshold": c.failure_threshold,
            "recovery_timeout_ms": c.recovery_timeout_ms,
            "half_open_max_calls": c.half_open_max_calls,
            "success_count": c.success_count,
            "failure_count": c.failure_count,
            "total_calls": c.total_calls,
            "total_failures": c.total_failures,
            "total_successes": c.total_successes,
            "total_trips": c.total_trips,
            "tags": list(c.tags), "metadata": dict(c.metadata),
            "created_at": c.created_at,
        }

    def remove_circuit(self, circuit_id: str) -> bool:
        if circuit_id not in self._circuits:
            return False
        del self._circuits[circuit_id]
        return True

    # ------------------------------------------------------------------
    # Call tracking
    # ------------------------------------------------------------------

    def allow_call(self, circuit_id: str) -> bool:
        """Check if a call is allowed through the circuit."""
        c = self._circuits.get(circuit_id)
        if not c:
            return False

        if c.state == "closed":
            return True
        elif c.state == "open":
            # Check if recovery timeout elapsed
            elapsed_ms = (time.time() - c.last_state_change_at) * 1000
            if elapsed_ms >= c.recovery_timeout_ms:
                c.state = "half_open"
                c.half_open_calls = 0
                c.last_state_change_at = time.time()
                self._fire("circuit_half_open", {"circuit_id": circuit_id})
                return True
            return False
        else:  # half_open
            return c.half_open_calls < c.half_open_max_calls

    def record_success(self, circuit_id: str) -> bool:
        """Record a successful call."""
        c = self._circuits.get(circuit_id)
        if not c:
            return False

        c.total_calls += 1
        c.total_successes += 1
        c.success_count += 1
        self._stats["total_calls"] += 1

        if c.state == "half_open":
            c.half_open_calls += 1
            if c.half_open_calls >= c.half_open_max_calls:
                # Reset to closed
                c.state = "closed"
                c.failure_count = 0
                c.success_count = 0
                c.last_state_change_at = time.time()
                self._fire("circuit_closed", {"circuit_id": circuit_id})
        elif c.state == "closed":
            # Reset failure count on success
            c.failure_count = 0

        return True

    def record_failure(self, circuit_id: str) -> bool:
        """Record a failed call."""
        c = self._circuits.get(circuit_id)
        if not c:
            return False

        c.total_calls += 1
        c.total_failures += 1
        c.failure_count += 1
        c.last_failure_at = time.time()
        self._stats["total_calls"] += 1
        self._stats["total_failures"] += 1

        if c.state == "half_open":
            # Trip back to open
            c.state = "open"
            c.last_state_change_at = time.time()
            c.total_trips += 1
            self._stats["total_trips"] += 1
            self._fire("circuit_opened", {"circuit_id": circuit_id})
        elif c.state == "closed":
            if c.failure_count >= c.failure_threshold:
                c.state = "open"
                c.last_state_change_at = time.time()
                c.total_trips += 1
                self._stats["total_trips"] += 1
                self._fire("circuit_opened", {"circuit_id": circuit_id})

        return True

    def force_open(self, circuit_id: str) -> bool:
        """Force circuit open."""
        c = self._circuits.get(circuit_id)
        if not c or c.state == "open":
            return False
        c.state = "open"
        c.last_state_change_at = time.time()
        c.total_trips += 1
        self._stats["total_trips"] += 1
        self._fire("circuit_opened", {"circuit_id": circuit_id})
        return True

    def force_close(self, circuit_id: str) -> bool:
        """Force circuit closed."""
        c = self._circuits.get(circuit_id)
        if not c or c.state == "closed":
            return False
        c.state = "closed"
        c.failure_count = 0
        c.success_count = 0
        c.last_state_change_at = time.time()
        self._fire("circuit_closed", {"circuit_id": circuit_id})
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_circuits(self, state: str = "", service: str = "",
                      tag: str = "") -> List[Dict]:
        results = []
        for c in self._circuits.values():
            if state and c.state != state:
                continue
            if service and c.service != service:
                continue
            if tag and tag not in c.tags:
                continue
            results.append(self.get_circuit(c.circuit_id))
        results.sort(key=lambda x: x["created_at"])
        return results

    def get_open_circuits(self) -> List[Dict]:
        """Get all open circuits."""
        return self.list_circuits(state="open")

    def get_circuit_health(self) -> Dict:
        """Get overall circuit health summary."""
        total = len(self._circuits)
        closed = sum(1 for c in self._circuits.values()
                     if c.state == "closed")
        opened = sum(1 for c in self._circuits.values()
                     if c.state == "open")
        half = sum(1 for c in self._circuits.values()
                   if c.state == "half_open")
        health_pct = (closed / total * 100.0) if total > 0 else 100.0
        return {
            "total_circuits": total,
            "closed": closed,
            "open": opened,
            "half_open": half,
            "health_percentage": round(health_pct, 1),
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
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
            "current_circuits": len(self._circuits),
            "open_circuits": sum(1 for c in self._circuits.values()
                                 if c.state == "open"),
        }

    def reset(self) -> None:
        self._circuits.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
