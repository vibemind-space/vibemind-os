"""Pipeline data comparator service for comparing pipeline data snapshots."""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataComparatorState:
    """State container for the pipeline data comparator."""
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataComparator:
    """Compares two pipeline data snapshots and records differences."""

    PREFIX = "pdcm-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataComparatorState()
        self._callbacks: Dict[str, Callable] = {}
        logger.info("PipelineDataComparator initialized")

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using SHA256 hash of data and sequence number."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.PREFIX}{hash_val}"

    def _prune(self):
        """Prune oldest quarter of entries when over MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        all_entries = []
        for eid, entry in self._state.entries.items():
            all_entries.append((eid, entry))
        all_entries.sort(key=lambda x: (x[1].get("created_at", 0), x[1].get("_seq", 0)))
        quarter = len(all_entries) // 4
        if quarter < 1:
            quarter = 1
        to_remove = all_entries[:quarter]
        for eid, _ in to_remove:
            del self._state.entries[eid]
        logger.info("Pruned %d entries", len(to_remove))

    def _fire(self, action: str, data: dict):
        """Fire all registered callbacks with the given action and data."""
        for cb_name, callback in list(self._callbacks.items()):
            try:
                callback({"action": action, "data": data})
            except Exception as e:
                logger.error("Callback %s failed: %s", cb_name, e)

    def _on_change(self, action: str, data: dict):
        """Internal change handler that fires callbacks."""
        self._fire(action, data)

    @property
    def on_change(self):
        """Property to access the on_change handler."""
        return self._on_change

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name. Returns True if found and removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_callback(self, name: str, callback: Callable):
        """Register a callback for change events."""
        self._callbacks[name] = callback
        logger.info("Registered callback: %s", name)

    def compare(self, pipeline_id: str, data_a: Any, data_b: Any, label: str = "") -> str:
        """Compare two pipeline data snapshots and record differences.

        Args:
            pipeline_id: Identifier for the pipeline.
            data_a: First data snapshot.
            data_b: Second data snapshot.
            label: Optional label for the comparison.

        Returns:
            Comparison ID string.
        """
        comp_id = self._generate_id(f"{pipeline_id}-{time.time()}")
        seq_val = self._state._seq - 1

        diffs = self._compute_diffs(data_a, data_b)

        entry = {
            "id": comp_id,
            "pipeline_id": pipeline_id,
            "label": label,
            "created_at": time.time(),
            "_seq": seq_val,
            "data_a": data_a,
            "data_b": data_b,
            "diffs": diffs,
            "diff_count": len(diffs),
            "identical": len(diffs) == 0,
        }

        self._state.entries[comp_id] = entry
        self._prune()

        self._on_change("compare", {"comp_id": comp_id, "pipeline_id": pipeline_id, "label": label})

        logger.info("Compared pipeline %s: %d differences (id=%s)", pipeline_id, len(diffs), comp_id)
        return comp_id

    def _compute_diffs(self, data_a: Any, data_b: Any) -> List[dict]:
        """Compute differences between two data snapshots."""
        diffs = []
        if isinstance(data_a, dict) and isinstance(data_b, dict):
            all_keys = set(list(data_a.keys()) + list(data_b.keys()))
            for key in sorted(all_keys):
                a_val = data_a.get(key)
                b_val = data_b.get(key)
                if key not in data_a:
                    diffs.append({"type": "added", "key": key, "value": b_val})
                elif key not in data_b:
                    diffs.append({"type": "removed", "key": key, "value": a_val})
                elif a_val != b_val:
                    diffs.append({"type": "changed", "key": key, "old": a_val, "new": b_val})
        elif data_a != data_b:
            diffs.append({"type": "replaced", "old": data_a, "new": data_b})
        return diffs

    def get_comparison(self, comp_id: str) -> Optional[dict]:
        """Get a single comparison by ID.

        Returns:
            Dict copy of the comparison entry, or None if not found.
        """
        entry = self._state.entries.get(comp_id)
        if entry is None:
            return None
        return dict(entry)

    def get_comparisons(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get comparisons, optionally filtered by pipeline_id.

        Args:
            pipeline_id: If provided, filter by this pipeline ID.
            limit: Maximum number of results to return (default 50).

        Returns:
            List of comparison dicts sorted by (created_at, _seq) descending.
        """
        if pipeline_id:
            entries = [
                dict(e) for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            ]
        else:
            entries = [dict(e) for e in self._state.entries.values()]

        entries.sort(key=lambda x: (x.get("created_at", 0), x.get("_seq", 0)), reverse=True)
        return entries[:limit]

    def get_comparison_count(self, pipeline_id: str = "") -> int:
        """Get the number of comparisons.

        Args:
            pipeline_id: If provided, count only for that pipeline.
                         If empty string, count across all pipelines.

        Returns:
            Number of comparison entries.
        """
        if pipeline_id:
            return sum(
                1 for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        """Get overall statistics for the comparator.

        Returns:
            Dict with total_comparisons, pipeline_count, and callbacks_registered.
        """
        pipeline_ids = set(e["pipeline_id"] for e in self._state.entries.values())
        return {
            "total_comparisons": len(self._state.entries),
            "pipeline_count": len(pipeline_ids),
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self):
        """Reset all state and callbacks."""
        self._state = PipelineDataComparatorState()
        self._callbacks.clear()
        logger.info("PipelineDataComparator reset")
