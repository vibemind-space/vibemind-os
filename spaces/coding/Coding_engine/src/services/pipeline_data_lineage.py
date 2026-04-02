"""Pipeline Data Lineage Tracking — data provenance and lineage through pipeline stages.

Tracks datasets and their transformations across pipeline stages, providing
upstream and downstream lineage queries to understand how data flows through
the system.

Thread-safe: all public methods are guarded by a threading lock.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DatasetRecord:
    """A registered dataset in the lineage graph."""

    dataset_id: str = ""
    name: str = ""
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


@dataclass
class TransformationRecord:
    """A data transformation linking an input dataset to an output dataset."""

    transform_id: str = ""
    input_dataset_id: str = ""
    output_dataset_id: str = ""
    pipeline_id: str = ""
    stage_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Data Lineage
# ---------------------------------------------------------------------------

class PipelineDataLineage:
    """Tracks data provenance and lineage through pipeline stages.

    All public methods acquire a lock before mutating or reading internal
    state, making the service safe for concurrent use from multiple threads.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._datasets: Dict[str, DatasetRecord] = {}
        self._transformations: Dict[str, TransformationRecord] = {}
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_datasets_registered": 0,
            "total_transformations_added": 0,
            "total_datasets_deleted": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, prefix: str, seed: str) -> str:
        """Generate a unique ID with the given prefix."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}{digest}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Evict the oldest dataset entries when the store exceeds *max_entries*."""
        if len(self._datasets) <= self._max_entries:
            return
        sorted_records = sorted(
            self._datasets.values(), key=lambda r: r.created_at
        )
        remove_count = len(self._datasets) - self._max_entries
        for record in sorted_records[:remove_count]:
            # Also remove related transformations
            self._remove_transformations_for(record.dataset_id)
            del self._datasets[record.dataset_id]
            self._stats["total_pruned"] += 1
            logger.debug(
                "dataset_pruned",
                dataset_id=record.dataset_id,
                name=record.name,
            )

    def _remove_transformations_for(self, dataset_id: str) -> None:
        """Remove all transformations referencing the given dataset."""
        to_remove = [
            tid
            for tid, t in self._transformations.items()
            if t.input_dataset_id == dataset_id or t.output_dataset_id == dataset_id
        ]
        for tid in to_remove:
            del self._transformations[tid]

    def _dataset_to_dict(self, record: DatasetRecord) -> Dict[str, Any]:
        """Convert a *DatasetRecord* dataclass to a plain dictionary."""
        return {
            "dataset_id": record.dataset_id,
            "name": record.name,
            "source": record.source,
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
        }

    def _transformation_to_dict(self, record: TransformationRecord) -> Dict[str, Any]:
        """Convert a *TransformationRecord* dataclass to a plain dictionary."""
        return {
            "transform_id": record.transform_id,
            "input_dataset_id": record.input_dataset_id,
            "output_dataset_id": record.output_dataset_id,
            "pipeline_id": record.pipeline_id,
            "stage_name": record.stage_name,
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
        }

    # ------------------------------------------------------------------
    # Register dataset
    # ------------------------------------------------------------------

    def register_dataset(
        self,
        name: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a dataset. Returns dataset_id (``pdl-`` prefix) or ``""`` if name already exists."""
        with self._lock:
            # Check for duplicate name
            for record in self._datasets.values():
                if record.name == name:
                    return ""

            self._prune_if_needed()
            dataset_id = self._generate_id("pdl-", f"{name}:{source}")
            now = time.time()

            record = DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                source=source,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                seq=self._seq,
            )
            self._datasets[dataset_id] = record
            self._stats["total_datasets_registered"] += 1
            logger.info(
                "dataset_registered",
                dataset_id=dataset_id,
                name=name,
                source=source,
            )
            detail = self._dataset_to_dict(record)

        self._fire("dataset_registered", detail)
        return dataset_id

    # ------------------------------------------------------------------
    # Get dataset
    # ------------------------------------------------------------------

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """Get dataset by ID. Returns dict or ``None``."""
        with self._lock:
            record = self._datasets.get(dataset_id)
            if record is None:
                return None
            return self._dataset_to_dict(record)

    # ------------------------------------------------------------------
    # Get dataset by name
    # ------------------------------------------------------------------

    def get_dataset_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get dataset by name. Returns dict or ``None``."""
        with self._lock:
            for record in self._datasets.values():
                if record.name == name:
                    return self._dataset_to_dict(record)
            return None

    # ------------------------------------------------------------------
    # Add transformation
    # ------------------------------------------------------------------

    def add_transformation(
        self,
        input_dataset_id: str,
        output_dataset_id: str,
        pipeline_id: str,
        stage_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a data transformation link. Returns transform_id (``pdl-`` prefix) or ``""`` if either dataset not found."""
        with self._lock:
            if input_dataset_id not in self._datasets:
                return ""
            if output_dataset_id not in self._datasets:
                return ""

            transform_id = self._generate_id(
                "pdl-", f"{input_dataset_id}:{output_dataset_id}:{pipeline_id}:{stage_name}"
            )
            now = time.time()

            record = TransformationRecord(
                transform_id=transform_id,
                input_dataset_id=input_dataset_id,
                output_dataset_id=output_dataset_id,
                pipeline_id=pipeline_id,
                stage_name=stage_name,
                metadata=dict(metadata) if metadata else {},
                created_at=now,
                seq=self._seq,
            )
            self._transformations[transform_id] = record
            self._stats["total_transformations_added"] += 1
            logger.info(
                "transformation_added",
                transform_id=transform_id,
                input_dataset_id=input_dataset_id,
                output_dataset_id=output_dataset_id,
                pipeline_id=pipeline_id,
                stage_name=stage_name,
            )
            detail = self._transformation_to_dict(record)

        self._fire("transformation_added", detail)
        return transform_id

    # ------------------------------------------------------------------
    # Get lineage (upstream)
    # ------------------------------------------------------------------

    def get_lineage(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Trace the dataset's origins (upstream transformations)."""
        with self._lock:
            results: List[Dict[str, Any]] = []
            visited: set = set()
            queue = [dataset_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                for t in self._transformations.values():
                    if t.output_dataset_id == current:
                        results.append(self._transformation_to_dict(t))
                        if t.input_dataset_id not in visited:
                            queue.append(t.input_dataset_id)

            return results

    # ------------------------------------------------------------------
    # Get downstream
    # ------------------------------------------------------------------

    def get_downstream(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Show what this dataset feeds into (downstream transformations)."""
        with self._lock:
            results: List[Dict[str, Any]] = []
            visited: set = set()
            queue = [dataset_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                for t in self._transformations.values():
                    if t.input_dataset_id == current:
                        results.append(self._transformation_to_dict(t))
                        if t.output_dataset_id not in visited:
                            queue.append(t.output_dataset_id)

            return results

    # ------------------------------------------------------------------
    # Get pipeline lineage
    # ------------------------------------------------------------------

    def get_pipeline_lineage(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return all transformations in a pipeline."""
        with self._lock:
            return [
                self._transformation_to_dict(t)
                for t in self._transformations.values()
                if t.pipeline_id == pipeline_id
            ]

    # ------------------------------------------------------------------
    # Delete dataset
    # ------------------------------------------------------------------

    def delete_dataset(self, dataset_id: str) -> bool:
        """Delete a dataset and its related transformations. Returns ``False`` if not found."""
        with self._lock:
            record = self._datasets.pop(dataset_id, None)
            if record is None:
                return False
            self._remove_transformations_for(dataset_id)
            self._stats["total_datasets_deleted"] += 1
            logger.info("dataset_deleted", dataset_id=dataset_id, name=record.name)
            detail = self._dataset_to_dict(record)

        self._fire("dataset_deleted", detail)
        return True

    # ------------------------------------------------------------------
    # List datasets
    # ------------------------------------------------------------------

    def list_datasets(self) -> List[Dict[str, Any]]:
        """Return all registered datasets."""
        with self._lock:
            return [
                self._dataset_to_dict(r)
                for r in self._datasets.values()
            ]

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def get_dataset_count(self) -> int:
        """Return the number of registered datasets."""
        with self._lock:
            return len(self._datasets)

    def get_transformation_count(self) -> int:
        """Return the number of recorded transformations."""
        with self._lock:
            return len(self._transformations)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named change-notification callback."""
        with self._lock:
            self._callbacks[name] = callback
        logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns ``True`` if removed."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
        logger.debug("callback_removed", name=name)
        return True

    def _fire(self, action: str, details: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        with self._lock:
            callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, details)
            except Exception as exc:
                logger.warning("callback_error", action=action, error=str(exc))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        with self._lock:
            return {
                **self._stats,
                "current_datasets": len(self._datasets),
                "current_transformations": len(self._transformations),
                "max_entries": self._max_entries,
                "registered_callbacks": len(self._callbacks),
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all stored datasets, transformations, callbacks, and reset counters."""
        with self._lock:
            self._datasets.clear()
            self._transformations.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_data_lineage_reset")
