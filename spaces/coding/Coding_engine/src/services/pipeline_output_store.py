"""Pipeline Output Store — stores and retrieves pipeline execution outputs
with versioning and querying.

Features:
- Store pipeline outputs with version and tag metadata
- Retrieve by output ID, pipeline name, or execution ID
- History tracking per pipeline with configurable limits
- Purge by pipeline name or timestamp
- Change callbacks for reactive integrations
- Max entries pruning with oldest-first eviction

All methods are synchronous with no external dependencies beyond stdlib.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _OutputEntry:
    """A single stored pipeline output."""
    output_id: str = ""
    pipeline_name: str = ""
    execution_id: str = ""
    output: Any = None
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)
    stored_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Output Store
# ---------------------------------------------------------------------------

class PipelineOutputStore:
    """Stores and manages pipeline execution outputs."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._entries: Dict[str, _OutputEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_stored": 0,
            "total_retrieved": 0,
            "total_removed": 0,
            "total_purged": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, pipeline_name: str, execution_id: str) -> str:
        """Generate a collision-free ID using SHA256 + sequence counter."""
        self._seq += 1
        raw = f"{pipeline_name}:{execution_id}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pos-{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # Store operations
    # ------------------------------------------------------------------

    def store(
        self,
        pipeline_name: str,
        execution_id: str,
        output: Any,
        version: str = "1.0",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a pipeline execution output.

        Returns the generated output_id string.
        """
        if not pipeline_name or not execution_id:
            logger.warning(
                "store_rejected_empty_key",
                pipeline_name=pipeline_name,
                execution_id=execution_id,
            )
            return ""

        output_id = self._next_id(pipeline_name, execution_id)

        entry = _OutputEntry(
            output_id=output_id,
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            output=output,
            version=version,
            tags=list(tags) if tags else [],
            stored_at=time.time(),
            seq=self._seq,
        )

        self._entries[output_id] = entry
        self._stats["total_stored"] += 1

        logger.debug(
            "output_stored",
            output_id=output_id,
            pipeline_name=pipeline_name,
            execution_id=execution_id,
            version=version,
        )

        self._prune()
        self._fire("store", {"output_id": output_id, "pipeline_name": pipeline_name})

        return output_id

    def get(self, output_id: str) -> Optional[Dict]:
        """Get a stored output by its ID. Returns dict or None."""
        entry = self._entries.get(output_id)
        if entry is None:
            return None
        self._stats["total_retrieved"] += 1
        return self._to_dict(entry)

    def get_latest(self, pipeline_name: str) -> Optional[Dict]:
        """Get the most recent output for a pipeline. Returns dict or None."""
        candidates = [
            e for e in self._entries.values()
            if e.pipeline_name == pipeline_name
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda e: e.stored_at)
        self._stats["total_retrieved"] += 1
        return self._to_dict(latest)

    def get_by_execution(self, execution_id: str) -> List[Dict]:
        """Get all outputs for a given execution ID."""
        results = [
            self._to_dict(e)
            for e in sorted(self._entries.values(), key=lambda e: e.stored_at)
            if e.execution_id == execution_id
        ]
        self._stats["total_retrieved"] += len(results)
        return results

    def get_history(
        self,
        pipeline_name: str,
        limit: int = 100,
    ) -> List[Dict]:
        """Get output history for a pipeline, newest first.

        Returns up to *limit* output dicts ordered by descending stored_at.
        """
        candidates = [
            e for e in self._entries.values()
            if e.pipeline_name == pipeline_name
        ]
        candidates.sort(key=lambda e: e.stored_at, reverse=True)
        results = [self._to_dict(e) for e in candidates[:limit]]
        self._stats["total_retrieved"] += len(results)
        return results

    def list_pipelines(self) -> List[str]:
        """List all unique pipeline names that have stored outputs."""
        names = sorted({e.pipeline_name for e in self._entries.values()})
        return names

    # ------------------------------------------------------------------
    # Remove / purge
    # ------------------------------------------------------------------

    def remove(self, output_id: str) -> bool:
        """Remove a single output by ID. Returns True if removed."""
        entry = self._entries.pop(output_id, None)
        if entry is None:
            return False
        self._stats["total_removed"] += 1
        logger.debug("output_removed", output_id=output_id)
        self._fire("remove", {"output_id": output_id})
        return True

    def purge(
        self,
        pipeline_name: Optional[str] = None,
        before_timestamp: Optional[float] = None,
    ) -> int:
        """Purge outputs matching the given criteria.

        - If *pipeline_name* is given, only outputs for that pipeline.
        - If *before_timestamp* is given, only outputs stored before that time.
        - If both are given, both conditions must be satisfied.
        - If neither is given, all outputs are purged.

        Returns the number of outputs purged.
        """
        to_remove: List[str] = []
        for oid, entry in self._entries.items():
            match = True
            if pipeline_name is not None and entry.pipeline_name != pipeline_name:
                match = False
            if before_timestamp is not None and entry.stored_at >= before_timestamp:
                match = False
            if match:
                to_remove.append(oid)

        for oid in to_remove:
            del self._entries[oid]

        count = len(to_remove)
        if count:
            self._stats["total_purged"] += count
            logger.debug(
                "outputs_purged",
                count=count,
                pipeline_name=pipeline_name,
                before_timestamp=before_timestamp,
            )
            self._fire("purge", {"count": count, "pipeline_name": pipeline_name})

        return count

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when max_entries is exceeded."""
        if len(self._entries) <= self._max_entries:
            return
        sorted_entries = sorted(self._entries.values(), key=lambda e: e.stored_at)
        overage = len(self._entries) - self._max_entries
        for entry in sorted_entries[:overage]:
            del self._entries[entry.output_id]
            self._stats["total_pruned"] += 1
        logger.debug("outputs_pruned", count=overage)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback by name."""
        self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        if name in self._callbacks:
            del self._callbacks[name]
            logger.debug("callback_removed", name=name)
            return True
        return False

    def _fire(self, action: str, data: Dict) -> None:
        """Invoke all registered callbacks."""
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.exception(
                    "callback_error",
                    callback_name=cb_name,
                    action=action,
                )

    # ------------------------------------------------------------------
    # Serialisation helper
    # ------------------------------------------------------------------

    def _to_dict(self, entry: _OutputEntry) -> Dict:
        """Convert an entry to a plain dict."""
        return {
            "output_id": entry.output_id,
            "pipeline_name": entry.pipeline_name,
            "execution_id": entry.execution_id,
            "output": entry.output,
            "version": entry.version,
            "tags": list(entry.tags),
            "stored_at": entry.stored_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_entries": len(self._entries),
            "max_entries": self._max_entries,
            "unique_pipelines": len(self.list_pipelines()),
            "registered_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all stored outputs, callbacks, and reset counters."""
        self._entries.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.debug("output_store_reset")
