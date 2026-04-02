"""Pipeline step sampler — samples pipeline step outputs for monitoring/analysis.

Captures sampled output data from pipeline steps at configurable rates,
enabling monitoring, performance analysis, and debugging without
capturing every single execution.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepSamplerState:
    """Internal state for the PipelineStepSampler service."""

    entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _seq: int = 0
    _callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineStepSampler:
    """Samples pipeline step outputs for monitoring and analysis.

    Captures output data from pipeline steps at a configurable sample rate,
    allowing lightweight monitoring without the overhead of recording every
    execution.
    """

    PREFIX = "pssp-"
    MAX_ENTRIES = 10000

    def __init__(self) -> None:
        self._state = PipelineStepSamplerState()

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        self._state._seq += 1
        raw = f"{self.PREFIX}{self._state._seq}-{id(self)}"
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @property
    def on_change(self) -> Optional[Callable]:
        """Get the current on_change callback."""
        return self._state._callbacks.get("__on_change__")

    @on_change.setter
    def on_change(self, callback: Optional[Callable]) -> None:
        """Set the on_change callback."""
        if callback is None:
            self._state._callbacks.pop("__on_change__", None)
        else:
            self._state._callbacks["__on_change__"] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a previously registered callback. Returns True if removed."""
        if name in self._state._callbacks:
            del self._state._callbacks[name]
            return True
        return False

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        """Invoke all registered callbacks; exceptions are logged, not raised."""
        for cb in list(self._state._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        """Evict oldest quarter of entries when the store exceeds MAX_ENTRIES."""
        if len(self._state.entries) <= self.MAX_ENTRIES:
            return
        sorted_keys = sorted(
            self._state.entries.keys(),
            key=lambda k: (
                self._state.entries[k].get("created_at", 0),
                self._state.entries[k].get("_seq", 0),
            ),
        )
        remove_count = len(self._state.entries) // 4
        if remove_count < 1:
            remove_count = 1
        for key in sorted_keys[:remove_count]:
            del self._state.entries[key]

    # ------------------------------------------------------------------
    # sample
    # ------------------------------------------------------------------

    def sample(
        self,
        pipeline_id: str,
        step_name: str,
        value: Any,
        sample_rate: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Sample a pipeline step output. Returns sample ID.

        The sample_rate controls the probability of actually recording
        the sample (0.0 = never, 1.0 = always). When the sample is
        skipped due to rate, an empty string is returned.
        """
        if sample_rate < 1.0 and random.random() > sample_rate:
            return ""

        self._prune()
        sample_id = self._generate_id()
        now = time.time()
        entry = {
            "sample_id": sample_id,
            "pipeline_id": pipeline_id,
            "step_name": step_name,
            "value": value,
            "sample_rate": sample_rate,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "_seq": self._state._seq,
        }
        self._state.entries[sample_id] = entry
        self._fire("sampled", dict(entry))
        return sample_id

    # ------------------------------------------------------------------
    # get_sample
    # ------------------------------------------------------------------

    def get_sample(self, sample_id: str) -> Optional[dict]:
        """Get a single sample by ID. Returns None if not found."""
        entry = self._state.entries.get(sample_id)
        if entry is None:
            return None
        return dict(entry)

    # ------------------------------------------------------------------
    # get_samples
    # ------------------------------------------------------------------

    def get_samples(
        self, pipeline_id: str = "", step_name: str = "", limit: int = 50
    ) -> List[dict]:
        """Get samples, newest first. Optionally filter by pipeline_id and/or step_name."""
        entries = list(self._state.entries.values())
        if pipeline_id:
            entries = [e for e in entries if e.get("pipeline_id") == pipeline_id]
        if step_name:
            entries = [e for e in entries if e.get("step_name") == step_name]
        entries.sort(
            key=lambda e: (e.get("created_at", 0), e.get("_seq", 0)),
            reverse=True,
        )
        return [dict(e) for e in entries[:limit]]

    # ------------------------------------------------------------------
    # get_sample_count
    # ------------------------------------------------------------------

    def get_sample_count(self, pipeline_id: str = "") -> int:
        """Count samples, optionally filtering by pipeline_id."""
        if not pipeline_id:
            return len(self._state.entries)
        return sum(
            1
            for e in self._state.entries.values()
            if e.get("pipeline_id") == pipeline_id
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return operational statistics."""
        entries = list(self._state.entries.values())
        total = len(entries)
        pipelines = set(e.get("pipeline_id", "") for e in entries)
        steps = set(e.get("step_name", "") for e in entries)
        return {
            "total_samples": total,
            "unique_pipelines": len(pipelines),
            "unique_steps": len(steps),
        }

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence."""
        self._state.entries.clear()
        self._state._callbacks.clear()
        self._state._seq = 0
