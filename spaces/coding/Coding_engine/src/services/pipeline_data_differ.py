"""Pipeline data differ service for comparing pipeline record sets."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataDifferState:
    """State container for the pipeline data differ."""
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataDiffer:
    """Compare two sets of pipeline records and find differences."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "pdd2-"

    def __init__(self):
        self._state = PipelineDataDifferState()
        self._callbacks = {}
        logger.info("PipelineDataDiffer initialized")

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash of data and sequence number."""
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        """Prune entries if total count exceeds MAX_ENTRIES."""
        total = sum(len(v) for v in self._state.entries.values())
        if total > self.MAX_ENTRIES:
            # Collect all entries with their pipeline_id for sorting
            all_entries = []
            for pid, entries in self._state.entries.items():
                for entry in entries:
                    all_entries.append((pid, entry))
            all_entries.sort(key=lambda x: x[1].get("timestamp", 0))
            to_remove = total - self.MAX_ENTRIES
            for pid, entry in all_entries[:to_remove]:
                self._state.entries[pid].remove(entry)
            # Clean up empty pipeline keys
            empty_keys = [k for k, v in self._state.entries.items() if not v]
            for k in empty_keys:
                del self._state.entries[k]
            logger.info("Pruned %d entries", to_remove)

    def on_change(self, callback) -> str:
        """Register a callback for change events. Returns callback ID."""
        cb_id = self._generate_id(f"cb-{time.time()}")
        self._callbacks[cb_id] = callback
        return cb_id

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a registered callback. Returns True if found and removed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: dict):
        """Fire all registered callbacks with the given event."""
        for cb_id, callback in list(self._callbacks.items()):
            try:
                callback(event)
            except Exception as e:
                logger.error("Callback %s failed: %s", cb_id, e)

    def compare(self, pipeline_id: str, old_records: list, new_records: list, key_field: str) -> dict:
        """Compare old and new record sets and find differences.

        Args:
            pipeline_id: Identifier for the pipeline.
            old_records: List of dicts representing old records.
            new_records: List of dicts representing new records.
            key_field: The field name to use as the unique key for matching.

        Returns:
            Dict with keys: added, removed, changed, unchanged.
        """
        old_map = {r[key_field]: r for r in old_records if key_field in r}
        new_map = {r[key_field]: r for r in new_records if key_field in r}

        old_keys = set(old_map.keys())
        new_keys = set(new_map.keys())

        added = [new_map[k] for k in sorted(new_keys - old_keys)]
        removed = [old_map[k] for k in sorted(old_keys - new_keys)]

        changed = []
        unchanged_count = 0
        for k in sorted(old_keys & new_keys):
            if old_map[k] != new_map[k]:
                changed.append({"key": k, "old": old_map[k], "new": new_map[k]})
            else:
                unchanged_count += 1

        result = {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged_count,
        }

        diff_id = self._generate_id(f"{pipeline_id}-{time.time()}")
        entry = {
            "id": diff_id,
            "pipeline_id": pipeline_id,
            "timestamp": time.time(),
            "summary": {
                "added_count": len(added),
                "removed_count": len(removed),
                "changed_count": len(changed),
                "unchanged_count": unchanged_count,
            },
            "result": result,
        }

        if pipeline_id not in self._state.entries:
            self._state.entries[pipeline_id] = []
        self._state.entries[pipeline_id].append(entry)

        self._prune()

        self._fire({
            "type": "diff_completed",
            "pipeline_id": pipeline_id,
            "diff_id": diff_id,
            "summary": entry["summary"],
        })

        logger.info("Compared pipeline %s: +%d -%d ~%d =%d",
                     pipeline_id, len(added), len(removed), len(changed), unchanged_count)

        return result

    def get_diff_summary(self, pipeline_id: str) -> dict | None:
        """Get the last comparison summary for a pipeline.

        Returns:
            Dict with summary info, or None if no comparisons exist.
        """
        entries = self._state.entries.get(pipeline_id)
        if not entries:
            return None
        last = entries[-1]
        return {
            "id": last["id"],
            "pipeline_id": last["pipeline_id"],
            "timestamp": last["timestamp"],
            "summary": last["summary"],
        }

    def get_history(self, pipeline_id: str, limit: int = 10) -> list:
        """Get past diff entries for a pipeline.

        Args:
            pipeline_id: The pipeline identifier.
            limit: Maximum number of entries to return (default 10).

        Returns:
            List of diff entries (most recent last), limited to `limit`.
        """
        entries = self._state.entries.get(pipeline_id, [])
        return entries[-limit:]

    def get_diff_count(self, pipeline_id: str = "") -> int:
        """Get the total number of diffs recorded.

        Args:
            pipeline_id: If provided, count only for that pipeline.
                         If empty string, count across all pipelines.

        Returns:
            Number of diff entries.
        """
        if pipeline_id:
            return len(self._state.entries.get(pipeline_id, []))
        return sum(len(v) for v in self._state.entries.values())

    def list_pipelines(self) -> list:
        """List all pipeline IDs that have recorded diffs.

        Returns:
            Sorted list of pipeline ID strings.
        """
        return sorted(self._state.entries.keys())

    def get_stats(self) -> dict:
        """Get overall statistics for the differ.

        Returns:
            Dict with pipeline_count, total_diffs, and callbacks_registered.
        """
        return {
            "pipeline_count": len(self._state.entries),
            "total_diffs": sum(len(v) for v in self._state.entries.values()),
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self):
        """Reset all state and callbacks."""
        self._state = PipelineDataDifferState()
        self._callbacks.clear()
        logger.info("PipelineDataDiffer reset")
