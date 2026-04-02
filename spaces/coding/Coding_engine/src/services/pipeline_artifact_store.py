"""Pipeline Artifact Store — manages build artifacts produced by pipeline executions.

Provides storage, retrieval, querying, and lifecycle management for artifacts
generated during pipeline runs.  Supports content storage, type-based filtering,
name-pattern search, timestamp-based purging, and change-notification callbacks.

Thread-safe: all public methods are guarded by a threading lock.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ArtifactRecord:
    """A single stored artifact produced by a pipeline execution."""

    artifact_id: str = ""
    pipeline_name: str = ""
    execution_id: str = ""
    artifact_name: str = ""
    content: Any = None
    artifact_type: str = "file"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline Artifact Store
# ---------------------------------------------------------------------------

class PipelineArtifactStore:
    """Stores and manages build artifacts produced by pipeline executions.

    All public methods acquire a lock before mutating or reading internal
    state, making the store safe for concurrent use from multiple threads.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._artifacts: Dict[str, ArtifactRecord] = {}
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_stored": 0,
            "total_retrieved": 0,
            "total_deleted": 0,
            "total_purged": 0,
            "total_pruned": 0,
            "total_searches": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique artifact ID with prefix ``par-``.

        Uses SHA-256 of the seed combined with the current timestamp and
        an incrementing sequence counter to guarantee uniqueness.
        """
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"par-{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest entries when the store exceeds *max_entries*.

        Must be called while the lock is held.
        """
        if len(self._artifacts) < self._max_entries:
            return
        sorted_records = sorted(
            self._artifacts.values(), key=lambda r: r.created_at
        )
        remove_count = len(self._artifacts) - self._max_entries + 1
        for record in sorted_records[:remove_count]:
            del self._artifacts[record.artifact_id]
            self._stats["total_pruned"] += 1
            logger.debug(
                "artifact_pruned: artifact_id=%s pipeline=%s",
                record.artifact_id,
                record.pipeline_name,
            )

    def _record_to_dict(self, record: ArtifactRecord) -> Dict[str, Any]:
        """Convert an *ArtifactRecord* dataclass to a plain dictionary."""
        return {
            "artifact_id": record.artifact_id,
            "pipeline_name": record.pipeline_name,
            "execution_id": record.execution_id,
            "artifact_name": record.artifact_name,
            "content": record.content,
            "artifact_type": record.artifact_type,
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
        }

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store_artifact(
        self,
        pipeline_name: str,
        execution_id: str,
        artifact_name: str,
        content: Any,
        artifact_type: str = "file",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a new artifact record.

        Parameters
        ----------
        pipeline_name:
            Name of the pipeline that produced the artifact.
        execution_id:
            Identifier of the specific pipeline execution.
        artifact_name:
            Human-readable name for the artifact (e.g. ``"build.tar.gz"``).
        content:
            The artifact payload.  Can be bytes, str, or any serialisable
            object — the store is agnostic to the content type.
        artifact_type:
            A free-form type label.  Common values: ``"file"``, ``"log"``,
            ``"report"``, ``"binary"``.
        metadata:
            Optional dictionary of additional key-value pairs to attach.

        Returns
        -------
        str
            The generated ``artifact_id`` (prefixed with ``par-``).
            Returns an empty string if required fields are missing.
        """
        if not pipeline_name or not artifact_name:
            logger.warning(
                "store_artifact_rejected: pipeline_name=%s artifact_name=%s",
                pipeline_name,
                artifact_name,
            )
            return ""

        with self._lock:
            self._prune_if_needed()

            artifact_id = self._next_id(
                f"{pipeline_name}:{execution_id}:{artifact_name}"
            )
            now = time.time()

            record = ArtifactRecord(
                artifact_id=artifact_id,
                pipeline_name=pipeline_name,
                execution_id=execution_id,
                artifact_name=artifact_name,
                content=content,
                artifact_type=artifact_type,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
            )

            self._artifacts[artifact_id] = record
            self._stats["total_stored"] += 1

            logger.info(
                "artifact_stored: id=%s pipeline=%s execution=%s name=%s type=%s",
                artifact_id,
                pipeline_name,
                execution_id,
                artifact_name,
                artifact_type,
            )

            detail = self._record_to_dict(record)

        self._fire("artifact_stored", detail)
        return artifact_id

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an artifact record by its ID.

        Returns a dict representation of the record (including ``content``),
        or ``None`` if no artifact with the given ID exists.
        """
        with self._lock:
            record = self._artifacts.get(artifact_id)
            if record is None:
                return None
            self._stats["total_retrieved"] += 1
            return self._record_to_dict(record)

    def get_artifacts_for_execution(
        self, pipeline_name: str, execution_id: str
    ) -> List[Dict[str, Any]]:
        """Return all artifacts produced by a specific pipeline execution.

        Results are sorted by ``created_at`` ascending.
        """
        with self._lock:
            self._stats["total_retrieved"] += 1
            results: List[Dict[str, Any]] = []
            for record in self._artifacts.values():
                if (
                    record.pipeline_name == pipeline_name
                    and record.execution_id == execution_id
                ):
                    results.append(self._record_to_dict(record))
            results.sort(key=lambda d: d["created_at"])
            return results

    def get_artifacts_by_type(
        self, artifact_type: str
    ) -> List[Dict[str, Any]]:
        """Return all artifacts matching the given *artifact_type*.

        Results are sorted by ``created_at`` descending (newest first).
        """
        with self._lock:
            self._stats["total_retrieved"] += 1
            results: List[Dict[str, Any]] = []
            for record in self._artifacts.values():
                if record.artifact_type == artifact_type:
                    results.append(self._record_to_dict(record))
            results.sort(key=lambda d: d["created_at"], reverse=True)
            return results

    def get_artifact_content(self, artifact_id: str) -> Any:
        """Return only the *content* payload of the specified artifact.

        Returns ``None`` if the artifact is not found.
        """
        with self._lock:
            record = self._artifacts.get(artifact_id)
            if record is None:
                return None
            self._stats["total_retrieved"] += 1
            return record.content

    # ------------------------------------------------------------------
    # List / search
    # ------------------------------------------------------------------

    def list_artifacts(
        self, pipeline_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all stored artifacts, optionally filtered by pipeline name.

        Results are sorted by ``created_at`` descending (newest first).
        """
        with self._lock:
            self._stats["total_retrieved"] += 1
            results: List[Dict[str, Any]] = []
            for record in self._artifacts.values():
                if pipeline_name is not None and record.pipeline_name != pipeline_name:
                    continue
                results.append(self._record_to_dict(record))
            results.sort(key=lambda d: d["created_at"], reverse=True)
            return results

    def search_artifacts(self, name_pattern: str) -> List[Dict[str, Any]]:
        """Search for artifacts whose *artifact_name* contains *name_pattern*.

        The match is case-insensitive.  Results are sorted by ``created_at``
        descending (newest first).
        """
        pattern_lower = name_pattern.lower()
        with self._lock:
            self._stats["total_searches"] += 1
            results: List[Dict[str, Any]] = []
            for record in self._artifacts.values():
                if pattern_lower in record.artifact_name.lower():
                    results.append(self._record_to_dict(record))
            results.sort(key=lambda d: d["created_at"], reverse=True)
            return results

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by its ID.

        Returns ``True`` if the artifact existed and was removed, ``False``
        otherwise.
        """
        with self._lock:
            record = self._artifacts.pop(artifact_id, None)
            if record is None:
                return False
            self._stats["total_deleted"] += 1
            detail = self._record_to_dict(record)

        logger.info("artifact_deleted: id=%s", artifact_id)
        self._fire("artifact_deleted", detail)
        return True

    # ------------------------------------------------------------------
    # Purge
    # ------------------------------------------------------------------

    def purge(self, before_timestamp: Optional[float] = None) -> int:
        """Remove artifacts older than *before_timestamp*.

        If *before_timestamp* is ``None``, **all** artifacts are removed.

        Returns the number of artifacts purged.
        """
        with self._lock:
            to_remove: List[str] = []
            for aid, record in self._artifacts.items():
                if before_timestamp is None or record.created_at < before_timestamp:
                    to_remove.append(aid)

            purged_details: List[Dict[str, Any]] = []
            for aid in to_remove:
                record = self._artifacts.pop(aid)
                self._stats["total_purged"] += 1
                purged_details.append(self._record_to_dict(record))

        if to_remove:
            logger.info("artifacts_purged: count=%d", len(to_remove))
            self._fire(
                "artifacts_purged",
                {"count": len(to_remove), "artifact_ids": to_remove},
            )

        return len(to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback.

        If a callback with the same *name* already exists it is silently
        replaced.  The callback signature is ``callback(action, detail)``
        where *action* is a string label and *detail* is a dict of event
        data.
        """
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("callback_registered: name=%s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback.

        Returns ``True`` if the callback existed and was removed.
        """
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("callback_removed: name=%s", name)
        return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given *action* and *detail*.

        Exceptions raised by individual callbacks are logged but do not
        propagate; remaining callbacks are still invoked.
        """
        with self._lock:
            callbacks = list(self._callbacks.values())

        for cb in callbacks:
            try:
                cb(action, detail)
            except Exception:
                logger.exception(
                    "callback_error: action=%s", action
                )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of operational statistics.

        The returned dict includes cumulative counters (stores, retrieves,
        deletes, purges, prunes, searches) as well as current-state gauges
        (number of artifacts, breakdown by type and pipeline).
        """
        with self._lock:
            type_counts: Dict[str, int] = {}
            pipeline_counts: Dict[str, int] = {}
            for record in self._artifacts.values():
                type_counts[record.artifact_type] = (
                    type_counts.get(record.artifact_type, 0) + 1
                )
                pipeline_counts[record.pipeline_name] = (
                    pipeline_counts.get(record.pipeline_name, 0) + 1
                )

            return {
                **self._stats,
                "current_artifacts": len(self._artifacts),
                "max_entries": self._max_entries,
                "by_type": dict(sorted(type_counts.items())),
                "by_pipeline": dict(sorted(pipeline_counts.items())),
                "registered_callbacks": len(self._callbacks),
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored artifacts, callbacks, and reset counters.

        Intended for testing or controlled teardown scenarios.
        """
        with self._lock:
            self._artifacts.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_artifact_store_reset")
