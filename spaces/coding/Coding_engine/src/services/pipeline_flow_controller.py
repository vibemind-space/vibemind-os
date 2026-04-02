"""Pipeline flow controller.

Controls execution flow of pipelines (pause, resume, stop, rate limiting).
Tracks pipeline states and enforces throughput limits to manage pipeline
execution lifecycle.
"""

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _PipelineEntry:
    """A pipeline flow control entry."""
    entry_id: str = ""
    pipeline_id: str = ""
    status: str = "running"  # running, paused, stopped
    max_throughput: float = 0.0  # 0 = unlimited
    current_throughput: float = 0.0
    total_pauses: int = 0
    total_resumes: int = 0
    total_stops: int = 0
    paused_at: float = 0.0
    stopped_at: float = 0.0
    resumed_at: float = 0.0
    created_at: float = 0.0
    seq: int = 0


class PipelineFlowController:
    """Controls execution flow of pipelines."""

    STATUSES = ("running", "paused", "stopped")

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, _PipelineEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max_entries
        self._pipeline_index: Dict[str, str] = {}  # pipeline_id -> entry_id
        self._stats = {
            "total_registered": 0,
            "total_paused": 0,
            "total_resumed": 0,
            "total_stopped": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, pipeline_id: str) -> str:
        raw = f"{pipeline_id}-{time.time()}-{self._seq}-{len(self._entries)}"
        return "pfc-" + hashlib.sha256(raw.encode()).hexdigest()[:16]

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
    # Pipeline registration
    # ------------------------------------------------------------------

    def register_pipeline(self, pipeline_id: str, max_throughput: float = 0.0) -> str:
        """Register a pipeline for flow control. Returns entry ID."""
        if not pipeline_id or not pipeline_id.strip():
            return ""
        pipeline_id = pipeline_id.strip()
        if max_throughput < 0:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""
        # If pipeline already registered, return existing
        if pipeline_id in self._pipeline_index:
            return self._pipeline_index[pipeline_id]

        self._seq += 1
        now = time.time()
        eid = self._make_id(pipeline_id)

        entry = _PipelineEntry(
            entry_id=eid,
            pipeline_id=pipeline_id,
            status="running",
            max_throughput=max_throughput,
            created_at=now,
            seq=self._seq,
        )
        self._entries[eid] = entry
        self._pipeline_index[pipeline_id] = eid
        self._stats["total_registered"] += 1
        self._fire("register_pipeline", asdict(entry))
        return eid

    def get_pipeline(self, entry_id: str) -> Optional[Dict]:
        """Get pipeline entry by ID."""
        if not entry_id or not entry_id.strip():
            return None
        entry = self._entries.get(entry_id.strip())
        if entry is None:
            return None
        return asdict(entry)

    # ------------------------------------------------------------------
    # Flow control
    # ------------------------------------------------------------------

    def pause_pipeline(self, pipeline_id: str) -> bool:
        """Pause a pipeline (set status to 'paused')."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        eid = self._pipeline_index.get(pipeline_id)
        if eid is None:
            return False
        entry = self._entries.get(eid)
        if entry is None:
            return False
        if entry.status != "running":
            return False

        self._seq += 1
        now = time.time()

        entry.status = "paused"
        entry.paused_at = now
        entry.total_pauses += 1
        entry.seq = self._seq

        self._stats["total_paused"] += 1
        self._fire("pause_pipeline", asdict(entry))
        return True

    def resume_pipeline(self, pipeline_id: str) -> bool:
        """Resume a paused pipeline (set status to 'running')."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        eid = self._pipeline_index.get(pipeline_id)
        if eid is None:
            return False
        entry = self._entries.get(eid)
        if entry is None:
            return False
        if entry.status != "paused":
            return False

        self._seq += 1
        now = time.time()

        entry.status = "running"
        entry.resumed_at = now
        entry.total_resumes += 1
        entry.seq = self._seq

        self._stats["total_resumed"] += 1
        self._fire("resume_pipeline", asdict(entry))
        return True

    def stop_pipeline(self, pipeline_id: str) -> bool:
        """Stop a pipeline (set status to 'stopped')."""
        if not pipeline_id or not pipeline_id.strip():
            return False
        pipeline_id = pipeline_id.strip()
        eid = self._pipeline_index.get(pipeline_id)
        if eid is None:
            return False
        entry = self._entries.get(eid)
        if entry is None:
            return False
        if entry.status == "stopped":
            return False

        self._seq += 1
        now = time.time()

        entry.status = "stopped"
        entry.stopped_at = now
        entry.total_stops += 1
        entry.seq = self._seq

        self._stats["total_stopped"] += 1
        self._fire("stop_pipeline", asdict(entry))
        return True

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_status(self, pipeline_id: str) -> str:
        """Returns 'running', 'paused', 'stopped', or 'unknown'."""
        if not pipeline_id or not pipeline_id.strip():
            return "unknown"
        pipeline_id = pipeline_id.strip()
        eid = self._pipeline_index.get(pipeline_id)
        if eid is None:
            return "unknown"
        entry = self._entries.get(eid)
        if entry is None:
            return "unknown"
        return entry.status

    def is_running(self, pipeline_id: str) -> bool:
        """Check if pipeline is running."""
        return self.get_status(pipeline_id) == "running"

    # ------------------------------------------------------------------
    # Listing / counts
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs."""
        return list(self._pipeline_index.keys())

    def get_pipeline_count(self) -> int:
        """Total pipeline count."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return controller statistics."""
        return {
            **self._stats,
            "active_pipelines": len(self._entries),
            "running_pipelines": sum(
                1 for e in self._entries.values() if e.status == "running"
            ),
            "paused_pipelines": sum(
                1 for e in self._entries.values() if e.status == "paused"
            ),
            "stopped_pipelines": sum(
                1 for e in self._entries.values() if e.status == "stopped"
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
            "total_registered": 0,
            "total_paused": 0,
            "total_resumed": 0,
            "total_stopped": 0,
        }
