"""Pipeline data migrator service for migrating pipeline data between schema versions."""

import time
import hashlib
import dataclasses
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineDataMigratorState:
    """State container for the pipeline data migrator."""
    entries: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineDataMigrator:
    """Migrates pipeline data between schema versions."""

    PREFIX = "pdmg-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineDataMigratorState()
        self._callbacks: Dict[str, Callable] = {}
        logger.info("PipelineDataMigrator initialized")

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

    def register_callback(self, name: str, callback: Callable):
        """Register a callback for change events."""
        self._callbacks[name] = callback
        logger.info("Registered callback: %s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback by name. Returns True if found and removed."""
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def migrate(self, pipeline_id: str, data: Any, from_version: str, to_version: str,
                metadata: Optional[dict] = None) -> str:
        """Migrate pipeline data from one schema version to another.

        Args:
            pipeline_id: Identifier for the pipeline.
            data: The pipeline data to migrate.
            from_version: Source schema version.
            to_version: Target schema version.
            metadata: Optional metadata dict for the migration record.

        Returns:
            Migration record ID string.
        """
        record_id = self._generate_id(f"{pipeline_id}-{from_version}-{to_version}-{time.time()}")
        seq_val = self._state._seq - 1

        entry = {
            "id": record_id,
            "pipeline_id": pipeline_id,
            "data": data,
            "from_version": from_version,
            "to_version": to_version,
            "metadata": metadata if metadata is not None else {},
            "status": "completed",
            "created_at": time.time(),
            "_seq": seq_val,
        }

        self._state.entries[record_id] = entry
        self._prune()

        self._on_change("migrate", {
            "record_id": record_id,
            "pipeline_id": pipeline_id,
            "from_version": from_version,
            "to_version": to_version,
        })

        logger.info(
            "Migrated pipeline %s from %s to %s (id=%s)",
            pipeline_id, from_version, to_version, record_id,
        )
        return record_id

    def get_migration(self, record_id: str) -> Optional[dict]:
        """Get a single migration record by ID.

        Returns:
            Dict copy of the migration entry, or None if not found.
        """
        entry = self._state.entries.get(record_id)
        if entry is None:
            return None
        return dict(entry)

    def get_migrations(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Get migrations, optionally filtered by pipeline_id.

        Args:
            pipeline_id: If provided, filter by this pipeline ID.
            limit: Maximum number of results to return (default 50).

        Returns:
            List of migration dicts sorted by (created_at, _seq) descending.
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

    def get_migration_count(self, pipeline_id: str = "") -> int:
        """Get the number of migration records.

        Args:
            pipeline_id: If provided, count only for that pipeline.
                         If empty string, count across all pipelines.

        Returns:
            Number of migration entries.
        """
        if pipeline_id:
            return sum(
                1 for e in self._state.entries.values()
                if e["pipeline_id"] == pipeline_id
            )
        return len(self._state.entries)

    def get_stats(self) -> dict:
        """Get overall statistics for the migrator.

        Returns:
            Dict with total_migrations, pipeline_count, and callbacks_registered.
        """
        pipeline_ids = set(e["pipeline_id"] for e in self._state.entries.values())
        return {
            "total_migrations": len(self._state.entries),
            "pipeline_count": len(pipeline_ids),
            "callbacks_registered": len(self._callbacks),
        }

    def reset(self):
        """Reset all state and callbacks."""
        self._state = PipelineDataMigratorState()
        self._callbacks.clear()
        logger.info("PipelineDataMigrator reset")
