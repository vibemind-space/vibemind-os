"""Pipeline circuit manager.

Manages circuit breaker states for pipelines (closed/open/half-open).
Tracks failure counts and recovery timeouts to protect pipelines from
cascading failures by automatically tripping circuits when thresholds
are exceeded.
"""

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _CircuitEntry:
    """A circuit breaker entry for a pipeline."""
    circuit_id: str = ""
    pipeline_id: str = ""
    state: str = "closed"  # closed, open, half-open
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    failure_count: int = 0
    success_count: int = 0
    half_open_calls: int = 0
    half_open_max: int = 1
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_trips: int = 0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    last_state_change_at: float = 0.0
    opened_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


class PipelineCircuitManager:
    """Manages circuit breaker states for pipelines."""

    STATES = ("closed", "open", "half-open")

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _CircuitEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max_entries
        self._pipeline_index: Dict[str, str] = {}  # pipeline_id -> circuit_id
        self._stats = {
            "total_created": 0,
            "total_successes_recorded": 0,
            "total_failures_recorded": 0,
            "total_trips": 0,
            "total_resets": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, pipeline_id: str) -> str:
        raw = f"{pipeline_id}-{time.time()}-{self._seq}-{len(self._entries)}"
        return "pcm-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        if not name or not name.strip():
            return False
        if not callable(callback):
            return False
        self._callbacks[name.strip()] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if not name or not name.strip():
            return False
        key = name.strip()
        if key not in self._callbacks:
            return False
        del self._callbacks[key]
        return True

    def _fire(self, action: str, data: Any) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Circuit CRUD
    # ------------------------------------------------------------------

    def create_circuit(self, pipeline_id: str, failure_threshold: int = 5,
                       recovery_timeout: float = 30.0) -> str:
        """Create a circuit breaker for a pipeline. Returns circuit ID."""
        if not pipeline_id or not pipeline_id.strip():
            return ""
        pipeline_id = pipeline_id.strip()
        if failure_threshold < 1:
            return ""
        if recovery_timeout < 0:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        # If pipeline already has a circuit, return existing
        if pipeline_id in self._pipeline_index:
            return self._pipeline_index[pipeline_id]

        self._seq += 1
        now = time.time()
        cid = self._make_id(pipeline_id)

        entry = _CircuitEntry(
            circuit_id=cid,
            pipeline_id=pipeline_id,
            state="closed",
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            created_at=now,
            last_state_change_at=now,
            seq=self._seq,
        )
        self._entries[cid] = entry
        self._pipeline_index[pipeline_id] = cid
        self._stats["total_created"] += 1
        self._fire("create_circuit", asdict(entry))
        return cid

    def get_circuit(self, circuit_id: str) -> Optional[Dict]:
        """Get circuit by circuit ID."""
        if not circuit_id or not circuit_id.strip():
            return None
        entry = self._entries.get(circuit_id.strip())
        if entry is None:
            return None
        return asdict(entry)

    def get_circuit_for_pipeline(self, pipeline_id: str) -> Optional[Dict]:
        """Get circuit by pipeline ID."""
        if not pipeline_id or not pipeline_id.strip():
            return None
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return None
        entry = self._entries.get(cid)
        if entry is None:
            return None
        return asdict(entry)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _check_recovery(self, entry: _CircuitEntry) -> None:
        """If circuit is open and recovery timeout has elapsed, move to half-open."""
        if entry.state == "open" and entry.opened_at > 0:
            if time.time() - entry.opened_at >= entry.recovery_timeout:
                entry.state = "half-open"
                entry.half_open_calls = 0
                entry.last_state_change_at = time.time()

    def record_success(self, pipeline_id: str) -> bool:
        """Record a successful call. Resets failure count, closes circuit if half-open."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return False
        entry = self._entries.get(cid)
        if entry is None:
            return False

        self._seq += 1
        now = time.time()

        self._check_recovery(entry)

        entry.success_count += 1
        entry.total_calls += 1
        entry.total_successes += 1
        entry.last_success_at = now
        entry.seq = self._seq

        if entry.state == "half-open":
            entry.state = "closed"
            entry.failure_count = 0
            entry.half_open_calls = 0
            entry.last_state_change_at = now
            self._fire("circuit_closed", asdict(entry))
        elif entry.state == "closed":
            entry.failure_count = 0

        self._stats["total_successes_recorded"] += 1
        self._fire("record_success", asdict(entry))
        return True

    def record_failure(self, pipeline_id: str) -> bool:
        """Record a failure. Opens circuit if threshold reached."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return False
        entry = self._entries.get(cid)
        if entry is None:
            return False

        self._seq += 1
        now = time.time()

        self._check_recovery(entry)

        entry.failure_count += 1
        entry.total_calls += 1
        entry.total_failures += 1
        entry.last_failure_at = now
        entry.seq = self._seq

        if entry.state == "half-open":
            # Any failure in half-open reopens
            entry.state = "open"
            entry.opened_at = now
            entry.last_state_change_at = now
            entry.total_trips += 1
            entry.half_open_calls = 0
            self._stats["total_trips"] += 1
            self._fire("circuit_opened", asdict(entry))
        elif entry.state == "closed" and entry.failure_count >= entry.failure_threshold:
            entry.state = "open"
            entry.opened_at = now
            entry.last_state_change_at = now
            entry.total_trips += 1
            self._stats["total_trips"] += 1
            self._fire("circuit_opened", asdict(entry))

        self._stats["total_failures_recorded"] += 1
        self._fire("record_failure", asdict(entry))
        return True

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_state(self, pipeline_id: str) -> str:
        """Returns 'closed', 'open', 'half-open', or 'unknown'."""
        if not pipeline_id or not pipeline_id.strip():
            return "unknown"
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return "unknown"
        entry = self._entries.get(cid)
        if entry is None:
            return "unknown"
        self._check_recovery(entry)
        return entry.state

    def is_allowed(self, pipeline_id: str) -> bool:
        """Check if calls are allowed through the circuit."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return False
        entry = self._entries.get(cid)
        if entry is None:
            return False

        self._check_recovery(entry)

        if entry.state == "closed":
            return True
        if entry.state == "open":
            return False
        if entry.state == "half-open":
            if entry.half_open_calls < entry.half_open_max:
                entry.half_open_calls += 1
                return True
            return False
        return False

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_circuit(self, pipeline_id: str) -> bool:
        """Reset a circuit to closed state."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        cid = self._pipeline_index.get(pipeline_id)
        if cid is None:
            return False
        entry = self._entries.get(cid)
        if entry is None:
            return False

        self._seq += 1
        now = time.time()

        entry.state = "closed"
        entry.failure_count = 0
        entry.success_count = 0
        entry.half_open_calls = 0
        entry.opened_at = 0.0
        entry.last_state_change_at = now
        entry.seq = self._seq

        self._stats["total_resets"] += 1
        self._fire("reset_circuit", asdict(entry))
        return True

    # ------------------------------------------------------------------
    # Listing / stats
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs with circuits."""
        return list(self._pipeline_index.keys())

    def get_circuit_count(self) -> int:
        """Total number of circuits."""
        return len(self._entries)

    def get_stats(self) -> Dict:
        """Return manager statistics."""
        return {
            **self._stats,
            "active_circuits": len(self._entries),
            "open_circuits": sum(
                1 for e in self._entries.values() if e.state == "open"
            ),
            "half_open_circuits": sum(
                1 for e in self._entries.values() if e.state == "half-open"
            ),
            "closed_circuits": sum(
                1 for e in self._entries.values() if e.state == "closed"
            ),
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._entries.clear()
        self._pipeline_index.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {
            "total_created": 0,
            "total_successes_recorded": 0,
            "total_failures_recorded": 0,
            "total_trips": 0,
            "total_resets": 0,
        }
