"""Pipeline data splitter service.

Splits pipeline data according to configurable strategies.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _SplitterState:
    """Internal state for the pipeline data splitter."""
    splitters: Dict[str, Dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataSplitter:
    """Splits pipeline data according to configurable strategies."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max(1, max_entries)
        self._state = _SplitterState()

    # ------------------------------------------------------------------
    # Splitter Management
    # ------------------------------------------------------------------

    def create_splitter(
        self,
        pipeline_id: str,
        strategy: str = "chunks",
        chunk_size: int = 10,
    ) -> str:
        """Create a splitter config for a pipeline.

        Returns the splitter ID (pds-...) or empty string on failure.
        """
        if not pipeline_id:
            return ""
        if len(self._state.splitters) >= self._max_entries:
            logger.warning("max_entries_reached", max_entries=self._max_entries)
            return ""

        self._state._seq += 1
        now = time.time()
        raw = f"{pipeline_id}{strategy}{chunk_size}{now}{self._state._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        splitter_id = f"pds-{digest}"

        self._state.splitters[splitter_id] = {
            "splitter_id": splitter_id,
            "pipeline_id": pipeline_id,
            "strategy": strategy,
            "chunk_size": chunk_size,
            "created_at": now,
            "split_count": 0,
        }

        logger.info(
            "splitter_created",
            splitter_id=splitter_id,
            pipeline_id=pipeline_id,
            strategy=strategy,
            chunk_size=chunk_size,
        )
        self._fire("splitter_created", splitter_id=splitter_id, pipeline_id=pipeline_id)
        return splitter_id

    def split(self, splitter_id: str, data: list) -> list:
        """Split data according to splitter config.

        Returns list of lists for 'chunks' strategy.
        """
        entry = self._state.splitters.get(splitter_id)
        if not entry:
            return []

        strategy = entry["strategy"]
        chunk_size = entry["chunk_size"]

        if strategy == "chunks":
            result = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
        else:
            result = [data]

        entry["split_count"] += 1

        logger.info(
            "data_split",
            splitter_id=splitter_id,
            strategy=strategy,
            input_size=len(data),
            output_chunks=len(result),
        )
        self._fire("data_split", splitter_id=splitter_id, chunks=len(result))
        return result

    def get_splitter(self, splitter_id: str) -> Optional[Dict]:
        """Get splitter config by ID. Returns dict or None."""
        entry = self._state.splitters.get(splitter_id)
        if not entry:
            return None
        return dict(entry)

    def get_splitters(self, pipeline_id: str) -> List[Dict]:
        """Get all splitters for a given pipeline."""
        result: List[Dict] = []
        for entry in self._state.splitters.values():
            if entry["pipeline_id"] == pipeline_id:
                result.append(dict(entry))
        return result

    def get_splitter_count(self, pipeline_id: str = "") -> int:
        """Count splitters, optionally filtered by pipeline_id."""
        if not pipeline_id:
            return len(self._state.splitters)
        count = 0
        for entry in self._state.splitters.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a deduplicated list of pipeline IDs."""
        seen: Dict[str, bool] = {}
        result: List[str] = []
        for entry in self._state.splitters.values():
            pid = entry["pipeline_id"]
            if pid not in seen:
                seen[pid] = True
                result.append(pid)
        return result

    def get_stats(self) -> Dict:
        """Return service statistics."""
        total_splits = 0
        for entry in self._state.splitters.values():
            total_splits += entry["split_count"]
        return {
            "splitters": len(self._state.splitters),
            "total_splits": total_splits,
            "callbacks": len(self._state.callbacks),
            "seq": self._state._seq,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state.splitters.clear()
        self._state.callbacks.clear()
        self._state._seq = 0
        logger.info("splitter_reset")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        self._state.callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, **detail: Any) -> None:
        """Invoke all registered callbacks."""
        detail_dict = dict(detail)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail_dict)
            except Exception:
                logger.exception("callback_error", action=action)
