"""Pipeline Data Classifier -- classifies data within pipelines.

Classifies pipeline data entries, tracking classification records with
categories, metadata, and pipeline attribution.

Usage::

    classifier = PipelineDataClassifier()

    # Classify data
    record_id = classifier.classify("pipeline-1", "data-key-1", category="urgent")

    # Query
    entry = classifier.get_classification(record_id)
    entries = classifier.get_classifications(pipeline_id="pipeline-1")
    stats = classifier.get_stats()
"""

from __future__ import annotations

import copy, hashlib, logging, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineDataClassifierState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataClassifier:
    """Classifies data within pipelines."""

    PREFIX = "pdcf-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineDataClassifierState()
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        quarter = max(1, len(self._state.entries) // 4)
        for key in sorted_keys[:quarter]:
            del self._state.entries[key]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.debug("on_change callback error for action=%s", action)
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.debug("Callback error for action=%s", action)

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        return self._on_change

    @on_change.setter
    def on_change(self, value: Optional[Callable]) -> None:
        self._on_change = value

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name. Returns True if removed, False if not found."""
        return self._state.callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def classify(
        self,
        pipeline_id: str,
        data_key: str,
        category: str = "default",
        metadata: Optional[dict] = None,
    ) -> str:
        """Classify a data entry within a pipeline.

        Args:
            pipeline_id: Identifier of the pipeline.
            data_key: Key of the data to classify.
            category: Classification category.
            metadata: Optional additional metadata dict.

        Returns:
            The generated classification ID (``pdcf-...``), or ``""`` on failure.
        """
        if not pipeline_id or not data_key:
            return ""

        try:
            self._prune()

            now = time.time()
            record_id = self._generate_id()
            self._state.entries[record_id] = {
                "record_id": record_id,
                "pipeline_id": pipeline_id,
                "data_key": data_key,
                "category": category,
                "metadata": copy.deepcopy(metadata) if metadata else {},
                "created_at": now,
                "_seq": self._state._seq,
            }
            self._fire("classified", self._state.entries[record_id])
            logger.debug(
                "Classification created: %s for pipeline %s data_key %s",
                record_id,
                pipeline_id,
                data_key,
            )
            return record_id
        except Exception:
            logger.exception("Failed to classify data_key %s", data_key)
            return ""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_classification(self, record_id: str) -> Optional[dict]:
        """Return the classification entry or None."""
        entry = self._state.entries.get(record_id)
        return dict(entry) if entry else None

    def get_classifications(self, pipeline_id: str = "", limit: int = 50) -> List[dict]:
        """Query classifications, newest first.

        Optionally filter by pipeline_id.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if pipeline_id and entry["pipeline_id"] != pipeline_id:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def get_classification_count(self, pipeline_id: str = "") -> int:
        """Return the number of classifications matching optional filter.

        Args:
            pipeline_id: If provided, count only classifications for this pipeline.
                If empty, count all classifications.
        """
        if not pipeline_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["pipeline_id"] == pipeline_id:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics.

        Keys: ``total_classifications``, ``unique_pipelines``.
        """
        pipelines = set()
        for entry in self._state.entries.values():
            pipelines.add(entry["pipeline_id"])
        return {
            "total_classifications": len(self._state.entries),
            "unique_pipelines": len(pipelines),
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state."""
        self._state = PipelineDataClassifierState()
        self._on_change = None
        logger.debug("PipelineDataClassifier reset")
