"""Pipeline output aggregator.

Collects, merges, and manages outputs from pipeline stages including
generated code, test results, verification reports, and artifacts.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Output:
    """A pipeline output entry."""
    output_id: str = ""
    stage: str = ""
    output_type: str = "code"  # code, test_result, report, artifact, log
    content: str = ""
    source: str = ""
    status: str = "pending"  # pending, accepted, rejected, merged
    quality_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    seq: int = 0


@dataclass
class _Collection:
    """A named collection of outputs."""
    collection_id: str = ""
    name: str = ""
    outputs: List[str] = field(default_factory=list)
    status: str = "open"  # open, finalized, archived
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    finalized_at: float = 0.0


class PipelineOutputAggregator:
    """Aggregates pipeline outputs from multiple stages."""

    OUTPUT_TYPES = ("code", "test_result", "report", "artifact", "log")
    OUTPUT_STATUSES = ("pending", "accepted", "rejected", "merged")

    def __init__(self, max_outputs: int = 100000,
                 max_collections: int = 5000):
        self._max_outputs = max_outputs
        self._max_collections = max_collections
        self._outputs: Dict[str, _Output] = {}
        self._collections: Dict[str, _Collection] = {}
        self._output_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_outputs_added": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_merged": 0,
            "total_collections_created": 0,
        }

    # ------------------------------------------------------------------
    # Output management
    # ------------------------------------------------------------------

    def add_output(self, stage: str, content: str,
                   output_type: str = "code", source: str = "",
                   quality_score: float = 0.0,
                   tags: Optional[List[str]] = None,
                   metadata: Optional[Dict] = None) -> str:
        """Add a pipeline output."""
        if not stage or not content:
            return ""
        if output_type not in self.OUTPUT_TYPES:
            return ""
        if len(self._outputs) >= self._max_outputs:
            self._prune_outputs()

        oid = "out-" + hashlib.md5(
            f"{stage}{time.time()}{len(self._outputs)}".encode()
        ).hexdigest()[:12]

        self._output_seq += 1
        self._outputs[oid] = _Output(
            output_id=oid,
            stage=stage,
            output_type=output_type,
            content=content,
            source=source,
            quality_score=quality_score,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=time.time(),
            seq=self._output_seq,
        )
        self._stats["total_outputs_added"] += 1
        self._fire("output_added", {
            "output_id": oid, "stage": stage,
            "output_type": output_type,
        })
        return oid

    def get_output(self, output_id: str) -> Optional[Dict]:
        """Get output info."""
        o = self._outputs.get(output_id)
        if not o:
            return None
        return {
            "output_id": o.output_id,
            "stage": o.stage,
            "output_type": o.output_type,
            "content": o.content,
            "source": o.source,
            "status": o.status,
            "quality_score": o.quality_score,
            "tags": list(o.tags),
            "timestamp": o.timestamp,
        }

    def remove_output(self, output_id: str) -> bool:
        """Remove an output."""
        if output_id not in self._outputs:
            return False
        del self._outputs[output_id]
        return True

    def accept_output(self, output_id: str) -> bool:
        """Accept an output."""
        o = self._outputs.get(output_id)
        if not o or o.status != "pending":
            return False
        o.status = "accepted"
        self._stats["total_accepted"] += 1
        return True

    def reject_output(self, output_id: str, reason: str = "") -> bool:
        """Reject an output."""
        o = self._outputs.get(output_id)
        if not o or o.status != "pending":
            return False
        o.status = "rejected"
        if reason:
            o.metadata["reject_reason"] = reason
        self._stats["total_rejected"] += 1
        return True

    def merge_output(self, output_id: str) -> bool:
        """Mark output as merged into final result."""
        o = self._outputs.get(output_id)
        if not o or o.status not in ("pending", "accepted"):
            return False
        o.status = "merged"
        self._stats["total_merged"] += 1
        return True

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def create_collection(self, name: str,
                          tags: Optional[List[str]] = None) -> str:
        """Create a named output collection."""
        if not name:
            return ""
        if len(self._collections) >= self._max_collections:
            return ""

        cid = "coll-" + hashlib.md5(
            f"{name}{time.time()}{len(self._collections)}".encode()
        ).hexdigest()[:12]

        self._collections[cid] = _Collection(
            collection_id=cid,
            name=name,
            tags=tags or [],
            created_at=time.time(),
        )
        self._stats["total_collections_created"] += 1
        return cid

    def get_collection(self, collection_id: str) -> Optional[Dict]:
        """Get collection info."""
        c = self._collections.get(collection_id)
        if not c:
            return None
        return {
            "collection_id": c.collection_id,
            "name": c.name,
            "output_count": len(c.outputs),
            "status": c.status,
            "tags": list(c.tags),
        }

    def remove_collection(self, collection_id: str) -> bool:
        """Remove a collection."""
        if collection_id not in self._collections:
            return False
        del self._collections[collection_id]
        return True

    def add_to_collection(self, collection_id: str,
                          output_id: str) -> bool:
        """Add output to collection."""
        c = self._collections.get(collection_id)
        if not c or c.status != "open":
            return False
        if output_id not in self._outputs:
            return False
        if output_id in c.outputs:
            return False
        c.outputs.append(output_id)
        return True

    def finalize_collection(self, collection_id: str) -> bool:
        """Finalize a collection (no more additions)."""
        c = self._collections.get(collection_id)
        if not c or c.status != "open":
            return False
        if not c.outputs:
            return False
        c.status = "finalized"
        c.finalized_at = time.time()
        return True

    def archive_collection(self, collection_id: str) -> bool:
        """Archive a collection."""
        c = self._collections.get(collection_id)
        if not c or c.status == "archived":
            return False
        c.status = "archived"
        return True

    def get_collection_outputs(self, collection_id: str) -> List[Dict]:
        """Get outputs in a collection."""
        c = self._collections.get(collection_id)
        if not c:
            return []
        result = []
        for oid in c.outputs:
            o = self._outputs.get(oid)
            if o:
                result.append({
                    "output_id": o.output_id,
                    "stage": o.stage,
                    "output_type": o.output_type,
                    "status": o.status,
                    "quality_score": o.quality_score,
                    "seq": o.seq,
                })
        result.sort(key=lambda x: x["seq"])
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_outputs(self, stage: Optional[str] = None,
                       output_type: Optional[str] = None,
                       status: Optional[str] = None,
                       source: Optional[str] = None,
                       tag: Optional[str] = None,
                       min_quality: float = 0.0,
                       limit: int = 100) -> List[Dict]:
        """Search outputs with filters."""
        result = []
        for o in self._outputs.values():
            if stage and o.stage != stage:
                continue
            if output_type and o.output_type != output_type:
                continue
            if status and o.status != status:
                continue
            if source and o.source != source:
                continue
            if tag and tag not in o.tags:
                continue
            if o.quality_score < min_quality:
                continue
            result.append({
                "output_id": o.output_id,
                "stage": o.stage,
                "output_type": o.output_type,
                "status": o.status,
                "quality_score": o.quality_score,
                "source": o.source,
                "seq": o.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_stage_summary(self) -> Dict[str, Dict]:
        """Get output counts by stage."""
        summary: Dict[str, Dict] = {}
        for o in self._outputs.values():
            if o.stage not in summary:
                summary[o.stage] = {"total": 0, "accepted": 0,
                                     "rejected": 0, "merged": 0,
                                     "pending": 0}
            summary[o.stage]["total"] += 1
            summary[o.stage][o.status] += 1
        return summary

    def get_quality_summary(self) -> Dict:
        """Get quality score summary."""
        scores = [o.quality_score for o in self._outputs.values()]
        if not scores:
            return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": len(scores),
            "avg": round(sum(scores) / len(scores), 2),
            "min": min(scores),
            "max": max(scores),
        }

    def list_collections(self, status: Optional[str] = None,
                         tag: Optional[str] = None) -> List[Dict]:
        """List collections with filters."""
        result = []
        for c in self._collections.values():
            if status and c.status != status:
                continue
            if tag and tag not in c.tags:
                continue
            result.append({
                "collection_id": c.collection_id,
                "name": c.name,
                "output_count": len(c.outputs),
                "status": c.status,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_outputs(self) -> None:
        """Remove oldest rejected/merged outputs."""
        prunable = [(k, v) for k, v in self._outputs.items()
                    if v.status in ("rejected", "merged")]
        prunable.sort(key=lambda x: x[1].timestamp)
        to_remove = max(len(prunable) // 2, len(self._outputs) // 4)
        for k, _ in prunable[:to_remove]:
            del self._outputs[k]

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
            "current_outputs": len(self._outputs),
            "current_collections": len(self._collections),
            "open_collections": sum(
                1 for c in self._collections.values() if c.status == "open"
            ),
        }

    def reset(self) -> None:
        self._outputs.clear()
        self._collections.clear()
        self._output_seq = 0
        self._stats = {k: 0 for k in self._stats}
