"""Pipeline data flow tracker.

Tracks data flowing through the pipeline — monitors data movement between
stages, records transformations, measures throughput, and detects bottlenecks.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Flow:
    """A data flow between components."""
    flow_id: str = ""
    name: str = ""
    source: str = ""
    target: str = ""
    data_type: str = "generic"  # generic, event, message, file, metric
    status: str = "active"  # active, paused, completed, failed
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0
    bytes_transferred: int = 0
    record_count: int = 0
    error_count: int = 0
    last_transfer_at: float = 0.0


@dataclass
class _Transfer:
    """A single data transfer event."""
    transfer_id: str = ""
    flow_id: str = ""
    bytes_count: int = 0
    record_count: int = 0
    duration_ms: float = 0.0
    status: str = "completed"  # completed, failed
    error: str = ""
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


class PipelineDataFlowTracker:
    """Tracks data flow through the pipeline."""

    DATA_TYPES = ("generic", "event", "message", "file", "metric")
    FLOW_STATUSES = ("active", "paused", "completed", "failed")
    TRANSFER_STATUSES = ("completed", "failed")

    def __init__(self, max_flows: int = 10000,
                 max_transfers: int = 500000):
        self._max_flows = max_flows
        self._max_transfers = max_transfers
        self._flows: Dict[str, _Flow] = {}
        self._transfers: Dict[str, _Transfer] = {}
        self._flow_seq = 0
        self._transfer_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_flows_created": 0,
            "total_transfers": 0,
            "total_bytes": 0,
            "total_records": 0,
            "total_errors": 0,
        }

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------

    def create_flow(self, name: str, source: str = "",
                    target: str = "", data_type: str = "generic",
                    tags: Optional[List[str]] = None,
                    metadata: Optional[Dict] = None) -> str:
        """Create a data flow."""
        if not name:
            return ""
        if data_type not in self.DATA_TYPES:
            return ""
        if len(self._flows) >= self._max_flows:
            return ""

        self._flow_seq += 1
        fid = "flow-" + hashlib.md5(
            f"{name}{time.time()}{self._flow_seq}{len(self._flows)}".encode()
        ).hexdigest()[:12]

        self._flows[fid] = _Flow(
            flow_id=fid,
            name=name,
            source=source,
            target=target,
            data_type=data_type,
            tags=tags or [],
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._flow_seq,
        )
        self._stats["total_flows_created"] += 1
        self._fire("flow_created", {"flow_id": fid, "name": name})
        return fid

    def get_flow(self, flow_id: str) -> Optional[Dict]:
        """Get flow info."""
        f = self._flows.get(flow_id)
        if not f:
            return None
        return {
            "flow_id": f.flow_id,
            "name": f.name,
            "source": f.source,
            "target": f.target,
            "data_type": f.data_type,
            "status": f.status,
            "tags": list(f.tags),
            "bytes_transferred": f.bytes_transferred,
            "record_count": f.record_count,
            "error_count": f.error_count,
            "last_transfer_at": f.last_transfer_at,
            "seq": f.seq,
        }

    def pause_flow(self, flow_id: str) -> bool:
        """Pause a flow."""
        f = self._flows.get(flow_id)
        if not f or f.status != "active":
            return False
        f.status = "paused"
        return True

    def resume_flow(self, flow_id: str) -> bool:
        """Resume a paused flow."""
        f = self._flows.get(flow_id)
        if not f or f.status != "paused":
            return False
        f.status = "active"
        return True

    def complete_flow(self, flow_id: str) -> bool:
        """Mark a flow as completed."""
        f = self._flows.get(flow_id)
        if not f or f.status in ("completed", "failed"):
            return False
        f.status = "completed"
        return True

    def fail_flow(self, flow_id: str) -> bool:
        """Mark a flow as failed."""
        f = self._flows.get(flow_id)
        if not f or f.status in ("completed", "failed"):
            return False
        f.status = "failed"
        return True

    def remove_flow(self, flow_id: str) -> bool:
        """Remove a flow and its transfers."""
        if flow_id not in self._flows:
            return False
        del self._flows[flow_id]
        # Cascade remove transfers
        to_remove = [tid for tid, t in self._transfers.items()
                     if t.flow_id == flow_id]
        for tid in to_remove:
            del self._transfers[tid]
        return True

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    def record_transfer(self, flow_id: str, bytes_count: int = 0,
                        record_count: int = 0, duration_ms: float = 0.0,
                        status: str = "completed", error: str = "",
                        metadata: Optional[Dict] = None) -> str:
        """Record a data transfer on a flow."""
        f = self._flows.get(flow_id)
        if not f:
            return ""
        if status not in self.TRANSFER_STATUSES:
            return ""
        if len(self._transfers) >= self._max_transfers:
            return ""

        self._transfer_seq += 1
        tid = "xfer-" + hashlib.md5(
            f"{flow_id}{time.time()}{self._transfer_seq}{len(self._transfers)}".encode()
        ).hexdigest()[:12]

        self._transfers[tid] = _Transfer(
            transfer_id=tid,
            flow_id=flow_id,
            bytes_count=bytes_count,
            record_count=record_count,
            duration_ms=duration_ms,
            status=status,
            error=error,
            metadata=metadata or {},
            created_at=time.time(),
            seq=self._transfer_seq,
        )

        # Update flow stats
        f.bytes_transferred += bytes_count
        f.record_count += record_count
        f.last_transfer_at = time.time()
        if status == "failed":
            f.error_count += 1
            self._stats["total_errors"] += 1

        self._stats["total_transfers"] += 1
        self._stats["total_bytes"] += bytes_count
        self._stats["total_records"] += record_count
        return tid

    def get_transfer(self, transfer_id: str) -> Optional[Dict]:
        """Get transfer info."""
        t = self._transfers.get(transfer_id)
        if not t:
            return None
        return {
            "transfer_id": t.transfer_id,
            "flow_id": t.flow_id,
            "bytes_count": t.bytes_count,
            "record_count": t.record_count,
            "duration_ms": t.duration_ms,
            "status": t.status,
            "error": t.error,
            "seq": t.seq,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_flows(self, source: Optional[str] = None,
                     target: Optional[str] = None,
                     data_type: Optional[str] = None,
                     status: Optional[str] = None,
                     tag: Optional[str] = None,
                     limit: int = 100) -> List[Dict]:
        """Search flows."""
        result = []
        for f in self._flows.values():
            if source and f.source != source:
                continue
            if target and f.target != target:
                continue
            if data_type and f.data_type != data_type:
                continue
            if status and f.status != status:
                continue
            if tag and tag not in f.tags:
                continue
            result.append({
                "flow_id": f.flow_id,
                "name": f.name,
                "source": f.source,
                "target": f.target,
                "data_type": f.data_type,
                "status": f.status,
                "bytes_transferred": f.bytes_transferred,
                "record_count": f.record_count,
                "error_count": f.error_count,
                "seq": f.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_flow_transfers(self, flow_id: str, status: Optional[str] = None,
                           limit: int = 100) -> List[Dict]:
        """Get transfers for a flow."""
        result = []
        for t in self._transfers.values():
            if t.flow_id != flow_id:
                continue
            if status and t.status != status:
                continue
            result.append({
                "transfer_id": t.transfer_id,
                "flow_id": t.flow_id,
                "bytes_count": t.bytes_count,
                "record_count": t.record_count,
                "duration_ms": t.duration_ms,
                "status": t.status,
                "seq": t.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_flow_throughput(self, flow_id: str) -> Dict:
        """Get throughput stats for a flow."""
        f = self._flows.get(flow_id)
        if not f:
            return {}
        transfers = [t for t in self._transfers.values()
                     if t.flow_id == flow_id and t.status == "completed"]
        total_duration = sum(t.duration_ms for t in transfers)
        total_bytes = sum(t.bytes_count for t in transfers)
        count = len(transfers)
        return {
            "flow_id": flow_id,
            "transfer_count": count,
            "total_bytes": total_bytes,
            "total_duration_ms": total_duration,
            "avg_bytes_per_transfer": total_bytes / count if count else 0.0,
            "avg_duration_ms": total_duration / count if count else 0.0,
            "bytes_per_ms": total_bytes / total_duration if total_duration else 0.0,
        }

    def get_component_flows(self, component: str) -> Dict:
        """Get all flows involving a component (as source or target)."""
        incoming = []
        outgoing = []
        for f in self._flows.values():
            if f.status != "active":
                continue
            if f.source == component:
                outgoing.append(f.flow_id)
            if f.target == component:
                incoming.append(f.flow_id)
        return {
            "component": component,
            "incoming": incoming,
            "outgoing": outgoing,
            "total": len(set(incoming + outgoing)),
        }

    def get_bottlenecks(self, limit: int = 10) -> List[Dict]:
        """Identify potential bottlenecks (flows with high error rates or slow throughput)."""
        results = []
        for f in self._flows.values():
            if f.status != "active":
                continue
            transfers = [t for t in self._transfers.values()
                         if t.flow_id == f.flow_id and t.status == "completed"]
            total_transfers = len(transfers) + f.error_count
            if total_transfers == 0:
                continue
            error_rate = (f.error_count / total_transfers) * 100.0 if total_transfers else 0.0
            avg_duration = (sum(t.duration_ms for t in transfers) / len(transfers)
                           if transfers else 0.0)
            results.append({
                "flow_id": f.flow_id,
                "name": f.name,
                "error_rate": round(error_rate, 1),
                "avg_duration_ms": round(avg_duration, 1),
                "total_transfers": total_transfers,
            })
        # Sort by error rate desc, then avg duration desc
        results.sort(key=lambda x: (-x["error_rate"], -x["avg_duration_ms"]))
        return results[:limit]

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
            "current_flows": len(self._flows),
            "current_transfers": len(self._transfers),
            "active_flows": sum(1 for f in self._flows.values()
                                if f.status == "active"),
        }

    def reset(self) -> None:
        self._flows.clear()
        self._transfers.clear()
        self._flow_seq = 0
        self._transfer_seq = 0
        self._stats = {k: 0 for k in self._stats}
