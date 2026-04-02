"""Pipeline step rate limiter - rate limits pipeline step executions using a token bucket approach."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PipelineStepRateLimiterState:
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class PipelineStepRateLimiter:
    """Rate limit pipeline step executions using a token bucket algorithm."""

    PREFIX = "psrl-"
    MAX_ENTRIES = 10000

    def __init__(self):
        self._state = PipelineStepRateLimiterState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepRateLimiter initialized")

    def _generate_id(self, data: str) -> str:
        raw = f"{data}{self._state._seq}"
        self._state._seq += 1
        return self.PREFIX + hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _prune(self):
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0),
            )
            while len(self._state.entries) > self.MAX_ENTRIES:
                del self._state.entries[sorted_keys.pop(0)]

    def _fire(self, event: str, data: dict):
        if self._on_change:
            try:
                self._on_change(event, data)
            except Exception as e:
                logger.error("on_change error: %s", e)
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    @property
    def on_change(self):
        return self._on_change

    @on_change.setter
    def on_change(self, callback):
        self._on_change = callback

    def remove_callback(self, name: str) -> bool:
        if name in self._callbacks:
            del self._callbacks[name]
            return True
        return False

    def register_limiter(self, step_name: str, max_per_second: float = 10.0, burst: int = 20) -> str:
        limiter_id = self._generate_id(step_name)
        now = time.time()
        entry = {
            "limiter_id": limiter_id,
            "step_name": step_name,
            "max_per_second": max_per_second,
            "burst": burst,
            "tokens": float(burst),
            "last_refill": now,
            "total_allowed": 0,
            "total_denied": 0,
            "created_at": now,
        }
        self._state.entries[limiter_id] = entry
        self._prune()
        self._fire("limiter_registered", entry)
        logger.info("Limiter registered: %s for step '%s' (rate=%.1f/s, burst=%d)", limiter_id, step_name, max_per_second, burst)
        return limiter_id

    def allow(self, limiter_id: str) -> bool:
        entry = self._state.entries.get(limiter_id)
        if entry is None:
            return False
        now = time.time()
        elapsed = now - entry["last_refill"]
        entry["tokens"] = min(entry["burst"], entry["tokens"] + elapsed * entry["max_per_second"])
        entry["last_refill"] = now
        if entry["tokens"] >= 1.0:
            entry["tokens"] -= 1.0
            entry["total_allowed"] += 1
            self._fire("limiter_allowed", entry)
            return True
        else:
            entry["total_denied"] += 1
            self._fire("limiter_denied", entry)
            return False

    def get_limiter(self, limiter_id: str) -> dict:
        entry = self._state.entries.get(limiter_id)
        if entry is None:
            return {}
        return dict(entry)

    def get_limiters(self, step_name: str = "") -> list:
        results = []
        for entry in self._state.entries.values():
            if step_name and entry["step_name"] != step_name:
                continue
            results.append(dict(entry))
        return results

    def get_limiter_count(self) -> int:
        return len(self._state.entries)

    def remove_limiter(self, limiter_id: str) -> bool:
        if limiter_id in self._state.entries:
            entry = self._state.entries.pop(limiter_id)
            self._fire("limiter_removed", entry)
            logger.info("Limiter removed: %s", limiter_id)
            return True
        return False

    def reset_limiter(self, limiter_id: str) -> bool:
        entry = self._state.entries.get(limiter_id)
        if entry is None:
            return False
        entry["tokens"] = float(entry["burst"])
        entry["last_refill"] = time.time()
        self._fire("limiter_reset", entry)
        logger.info("Limiter reset: %s", limiter_id)
        return True

    def get_stats(self) -> dict:
        total_allowed = sum(e["total_allowed"] for e in self._state.entries.values())
        total_denied = sum(e["total_denied"] for e in self._state.entries.values())
        total = total_allowed + total_denied
        return {
            "total_limiters": len(self._state.entries),
            "total_allowed": total_allowed,
            "total_denied": total_denied,
            "denial_rate": total_denied / total if total > 0 else 0,
        }

    def reset(self):
        self._state = PipelineStepRateLimiterState()
        self._callbacks = {}
        self._on_change = None
        logger.info("PipelineStepRateLimiter reset")
