"""Service module for emergent autonomous pipeline data sampling system."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

MAX_ENTRIES = 10000

VALID_STRATEGIES = ("first_n", "last_n", "every_nth")


@dataclass
class _State:
    samplers: Dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class PipelineDataSampler:
    """Autonomous pipeline data sampling service."""

    def __init__(self) -> None:
        self._state = _State()

    # ── ID generation ──────────────────────────────────────────────

    def _next_id(self, key: str) -> str:
        self._state._seq += 1
        raw = f"{key}-{self._state._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pdsa-{digest}"

    # ── Pruning ────────────────────────────────────────────────────

    def _prune(self) -> None:
        if len(self._state.samplers) > MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.samplers,
                key=lambda k: self._state.samplers[k].get("created_at", 0),
            )
            to_remove = len(self._state.samplers) - MAX_ENTRIES
            for k in sorted_keys[:to_remove]:
                del self._state.samplers[k]
            logger.info("pruned_samplers", removed=to_remove)

    # ── Callbacks ──────────────────────────────────────────────────

    def on_change(self, name: str, cb: Callable) -> None:
        self._state.callbacks[name] = cb

    def remove_callback(self, name: str) -> bool:
        if name in self._state.callbacks:
            del self._state.callbacks[name]
            return True
        return False

    def _fire(self, action: str, **detail: Any) -> None:
        for cb in list(self._state.callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error", action=action)

    # ── API ────────────────────────────────────────────────────────

    def create_sampler(
        self,
        pipeline_id: str,
        strategy: str = "first_n",
        sample_size: int = 10,
    ) -> str:
        """Create a sampler config and return its sampler_id."""
        sampler_id = self._next_id(pipeline_id)
        self._state.samplers[sampler_id] = {
            "sampler_id": sampler_id,
            "pipeline_id": pipeline_id,
            "strategy": strategy,
            "sample_size": sample_size,
            "created_at": time.time(),
            "sample_count": 0,
        }
        self._prune()
        logger.info("sampler_created", sampler_id=sampler_id, pipeline_id=pipeline_id)
        self._fire("create_sampler", sampler_id=sampler_id, pipeline_id=pipeline_id)
        return sampler_id

    def sample(self, sampler_id: str, data: list) -> list:
        """Sample data according to the sampler's strategy."""
        entry = self._state.samplers.get(sampler_id)
        if entry is None:
            logger.warning("sampler_not_found", sampler_id=sampler_id)
            return []
        strategy = entry["strategy"]
        sample_size = entry["sample_size"]
        if strategy == "first_n":
            result = data[:sample_size]
        elif strategy == "last_n":
            result = data[-sample_size:]
        elif strategy == "every_nth":
            step = max(1, len(data) // sample_size)
            result = data[::step]
        else:
            logger.warning("unknown_strategy", strategy=strategy)
            result = []
        entry["sample_count"] += 1
        self._fire("sample", sampler_id=sampler_id, count=len(result))
        return result

    def get_sampler(self, sampler_id: str) -> Optional[dict]:
        """Return a sampler config or None."""
        return self._state.samplers.get(sampler_id)

    def get_samplers(self, pipeline_id: str) -> list:
        """Return all samplers for a pipeline."""
        return [
            s for s in self._state.samplers.values()
            if s["pipeline_id"] == pipeline_id
        ]

    def get_sampler_count(self, pipeline_id: str = "") -> int:
        """Return the number of samplers, optionally filtered by pipeline."""
        if not pipeline_id:
            return len(self._state.samplers)
        return sum(
            1 for s in self._state.samplers.values()
            if s["pipeline_id"] == pipeline_id
        )

    def list_pipelines(self) -> list:
        """Return a list of distinct pipeline IDs."""
        return list({s["pipeline_id"] for s in self._state.samplers.values()})

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        total = len(self._state.samplers)
        pipelines = len({s["pipeline_id"] for s in self._state.samplers.values()})
        total_samples = sum(s["sample_count"] for s in self._state.samplers.values())
        return {
            "total_samplers": total,
            "total_pipelines": pipelines,
            "total_samples": total_samples,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._state.samplers.clear()
        self._state._seq = 0
        self._state.callbacks.clear()
        logger.info("state_reset")
