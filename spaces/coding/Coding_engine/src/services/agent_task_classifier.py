"""Agent Task Classifier -- classifies tasks by type and priority.

Stores task classification records with type, priority, tags,
and metadata. Supports querying, filtering, reclassification, and stats.

Usage::

    classifier = AgentTaskClassifier()

    # Classify a task
    cid = classifier.classify("task-1", task_type="build", priority="high")

    # Query
    entry = classifier.get_classification(cid)
    entries = classifier.get_classifications(task_type="build")
    stats = classifier.get_stats()
"""

from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTaskClassifierState:
    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0


class AgentTaskClassifier:
    """Classifies tasks by type and priority."""

    PREFIX = "atcl-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = AgentTaskClassifierState()
        self._callbacks: Dict[str, Callable] = {}
        self._on_change: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}-{self._state._seq}-{id(self)}-{time.time()}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _prune(self) -> None:
        if len(self._state.entries) < self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (self._state.entries[k]["created_at"], self._state.entries[k].get("_seq", 0)),
        )
        while len(self._state.entries) >= self.MAX_ENTRIES and sorted_keys:
            oldest = sorted_keys.pop(0)
            del self._state.entries[oldest]

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        if self._on_change is not None:
            try:
                self._on_change(action, data)
            except Exception:
                logger.exception("on_change callback error")
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback error")

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
        return self._callbacks.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Classification operations
    # ------------------------------------------------------------------

    def classify(
        self,
        task_id: str,
        task_type: str = "general",
        priority: str = "normal",
        tags: List[str] = None,
        metadata: dict = None,
    ) -> str:
        """Classify a task.

        Returns the classification ID on success or ``""`` on failure.
        """
        if not task_id:
            return ""

        self._prune()
        if len(self._state.entries) >= self.MAX_ENTRIES:
            return ""

        now = time.time()
        classification_id = self._generate_id()
        self._state.entries[classification_id] = {
            "classification_id": classification_id,
            "task_id": task_id,
            "task_type": task_type,
            "priority": priority,
            "tags": list(tags) if tags else [],
            "metadata": copy.deepcopy(metadata) if metadata else {},
            "created_at": now,
            "_seq": self._state._seq,
        }
        self._fire("classified", self._state.entries[classification_id])
        logger.debug(
            "Task classified: %s (task=%s, type=%s, priority=%s)",
            classification_id,
            task_id,
            task_type,
            priority,
        )
        return classification_id

    def get_classification(self, classification_id: str) -> Optional[dict]:
        """Return the classification entry or None."""
        entry = self._state.entries.get(classification_id)
        return dict(entry) if entry else None

    def get_classifications(
        self, task_type: str = "", priority: str = "", limit: int = 50
    ) -> List[dict]:
        """Query classifications, newest first.

        Optionally filter by task_type and/or priority.
        """
        results: List[Dict[str, Any]] = []
        for entry in self._state.entries.values():
            if task_type and entry["task_type"] != task_type:
                continue
            if priority and entry["priority"] != priority:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: (e["created_at"], e.get("_seq", 0)), reverse=True)
        return results[:limit]

    def reclassify(
        self, classification_id: str, task_type: str = "", priority: str = ""
    ) -> bool:
        """Update the type and/or priority of an existing classification."""
        entry = self._state.entries.get(classification_id)
        if entry is None:
            return False
        if task_type:
            entry["task_type"] = task_type
        if priority:
            entry["priority"] = priority
        self._fire("reclassified", dict(entry))
        logger.debug("Task reclassified: %s", classification_id)
        return True

    def get_classification_count(self, task_type: str = "", priority: str = "") -> int:
        """Return the number of classifications, optionally filtered."""
        if not task_type and not priority:
            return len(self._state.entries)
        count = 0
        for e in self._state.entries.values():
            if task_type and e["task_type"] != task_type:
                continue
            if priority and e["priority"] != priority:
                continue
            count += 1
        return count

    def get_stats(self) -> dict:
        """Return summary statistics."""
        by_type: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}
        for entry in self._state.entries.values():
            t = entry["task_type"]
            p = entry["priority"]
            by_type[t] = by_type.get(t, 0) + 1
            by_priority[p] = by_priority.get(p, 0) + 1
        return {
            "total_classifications": len(self._state.entries),
            "by_type": by_type,
            "by_priority": by_priority,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._state = AgentTaskClassifierState()
        self._callbacks.clear()
        self._on_change = None
        logger.debug("AgentTaskClassifier reset")
