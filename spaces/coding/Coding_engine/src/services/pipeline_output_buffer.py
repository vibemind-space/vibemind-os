"""Pipeline Output Buffer — buffers pipeline step outputs before they are
consumed or flushed downstream.

Features:
- Create named output buffers for pipeline steps
- Write data into buffers with configurable max size
- Read (FIFO), peek, and flush operations
- Query buffers by pipeline ID
- Change callbacks for reactive integrations
- Max entries pruning with oldest-first eviction

All methods are synchronous with no external dependencies beyond stdlib.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _BufferEntry:
    """A single output buffer for a pipeline step."""
    buffer_id: str = ""
    pipeline_id: str = ""
    step_name: str = ""
    max_size: int = 100
    items: deque = field(default_factory=deque)
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Output Buffer
# ---------------------------------------------------------------------------

class PipelineOutputBuffer:
    """Buffers pipeline step outputs before downstream consumption."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._buffers: Dict[str, _BufferEntry] = {}
        self._seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_created": 0,
            "total_writes": 0,
            "total_reads": 0,
            "total_flushes": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, pipeline_id: str, step_name: str) -> str:
        """Generate a collision-free ID using SHA256 + sequence counter."""
        self._seq += 1
        raw = f"{pipeline_id}:{step_name}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pob-{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # Buffer operations
    # ------------------------------------------------------------------

    def create_buffer(
        self,
        pipeline_id: str,
        step_name: str,
        max_size: int = 100,
    ) -> str:
        """Create an output buffer for a pipeline step.

        Returns the generated buffer ID (pob-xxx).
        """
        if not pipeline_id or not step_name:
            logger.warning(
                "create_buffer_rejected_empty_key",
                pipeline_id=pipeline_id,
                step_name=step_name,
            )
            return ""

        buffer_id = self._next_id(pipeline_id, step_name)

        entry = _BufferEntry(
            buffer_id=buffer_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            max_size=max_size,
            items=deque(),
            created_at=time.time(),
            seq=self._seq,
        )

        self._buffers[buffer_id] = entry
        self._stats["total_created"] += 1

        logger.debug(
            "buffer_created",
            buffer_id=buffer_id,
            pipeline_id=pipeline_id,
            step_name=step_name,
            max_size=max_size,
        )

        self._prune()
        self._fire("create", {"buffer_id": buffer_id, "pipeline_id": pipeline_id})

        return buffer_id

    def write(self, buffer_id: str, data: Any) -> bool:
        """Write data to a buffer.

        Returns True if written, False if buffer full or not found.
        """
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return False
        if len(entry.items) >= entry.max_size:
            return False

        entry.items.append(data)
        self._stats["total_writes"] += 1

        logger.debug(
            "buffer_write",
            buffer_id=buffer_id,
            size=len(entry.items),
        )

        self._fire("write", {"buffer_id": buffer_id, "data": data})
        return True

    def read(self, buffer_id: str, count: int = -1) -> list:
        """Read items from buffer (FIFO).

        If count=-1, read all. Items are removed after reading.
        """
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return []

        if count < 0:
            count = len(entry.items)

        results = []
        for _ in range(min(count, len(entry.items))):
            results.append(entry.items.popleft())

        self._stats["total_reads"] += len(results)

        logger.debug(
            "buffer_read",
            buffer_id=buffer_id,
            count=len(results),
        )

        self._fire("read", {"buffer_id": buffer_id, "count": len(results)})
        return results

    def peek(self, buffer_id: str, count: int = 1) -> list:
        """Peek at items without removing them."""
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return []

        actual = min(count, len(entry.items))
        results = [entry.items[i] for i in range(actual)]
        return results

    def flush(self, buffer_id: str) -> list:
        """Read and remove all items from buffer."""
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return []

        results = list(entry.items)
        entry.items.clear()
        self._stats["total_flushes"] += 1

        logger.debug(
            "buffer_flushed",
            buffer_id=buffer_id,
            count=len(results),
        )

        self._fire("flush", {"buffer_id": buffer_id, "count": len(results)})
        return results

    def get_buffer_size(self, buffer_id: str) -> int:
        """Get current number of items in buffer. 0 if not found."""
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return 0
        return len(entry.items)

    def get_buffer(self, buffer_id: str) -> Optional[Dict]:
        """Get buffer info/metadata. Returns dict or None."""
        entry = self._buffers.get(buffer_id)
        if entry is None:
            return None
        return self._to_dict(entry)

    def get_buffers(self, pipeline_id: str) -> List[Dict]:
        """Get all buffers for a pipeline."""
        results = [
            self._to_dict(e)
            for e in sorted(self._buffers.values(), key=lambda e: e.created_at)
            if e.pipeline_id == pipeline_id
        ]
        return results

    def get_buffer_count(self, pipeline_id: str = "") -> int:
        """Count buffers.

        If pipeline_id given, count for that pipeline only.
        """
        if not pipeline_id:
            return len(self._buffers)
        return sum(
            1 for e in self._buffers.values()
            if e.pipeline_id == pipeline_id
        )

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs with buffers."""
        return sorted({e.pipeline_id for e in self._buffers.values()})

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest entries when max_entries is exceeded."""
        if len(self._buffers) <= self._max_entries:
            return
        sorted_entries = sorted(self._buffers.values(), key=lambda e: e.created_at)
        overage = len(self._buffers) - self._max_entries
        for entry in sorted_entries[:overage]:
            del self._buffers[entry.buffer_id]
            self._stats["total_pruned"] += 1
        logger.debug("buffers_pruned", count=overage)

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

    def _to_dict(self, entry: _BufferEntry) -> Dict:
        """Convert an entry to a plain dict."""
        return {
            "buffer_id": entry.buffer_id,
            "pipeline_id": entry.pipeline_id,
            "step_name": entry.step_name,
            "max_size": entry.max_size,
            "current_size": len(entry.items),
            "created_at": entry.created_at,
        }

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return operational statistics."""
        return {
            **self._stats,
            "current_buffers": len(self._buffers),
            "max_entries": self._max_entries,
            "unique_pipelines": len(self.list_pipelines()),
            "registered_callbacks": len(self._callbacks),
        }

    def reset(self) -> None:
        """Clear all buffers, callbacks, and reset counters."""
        self._buffers.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.debug("output_buffer_reset")
