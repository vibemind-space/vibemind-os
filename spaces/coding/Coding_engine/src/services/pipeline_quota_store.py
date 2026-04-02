"""Pipeline Quota Store — manage per-pipeline resource quotas with consumption tracking.

Provides quota management keyed by (pipeline_id, resource_type) pairs,
supporting consume/release semantics, utilization queries, and change
callbacks for downstream subscribers.

Thread-safe: all public methods are guarded by a threading lock.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class QuotaRecord:
    """A single resource quota for a pipeline."""

    quota_id: str = ""
    pipeline_id: str = ""
    resource_type: str = ""
    max_amount: float = 0.0
    used_amount: float = 0.0
    created_at: float = 0.0
    seq: int = 0


# ---------------------------------------------------------------------------
# Pipeline Quota Store
# ---------------------------------------------------------------------------

class PipelineQuotaStore:
    """Manage per-pipeline resource quotas with consume/release tracking.

    Quotas are keyed by (pipeline_id, resource_type) tuples. Each combination
    can have at most one quota record. Setting a quota for an existing combo
    updates the max_amount and returns the existing quota_id.

    All public methods acquire a lock before mutating or reading internal
    state, making the service safe for concurrent use from multiple threads.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._quotas: Dict[Tuple[str, str], QuotaRecord] = {}
        self._seq: int = 0
        self._lock = threading.Lock()
        self._callbacks: Dict[str, Callable] = {}
        self._stats: Dict[str, int] = {
            "total_quotas_created": 0,
            "total_quotas_updated": 0,
            "total_quotas_removed": 0,
            "total_consumes": 0,
            "total_releases": 0,
            "total_resets": 0,
            "total_exceeded": 0,
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

    def _quota_to_dict(self, rec: QuotaRecord) -> Dict[str, Any]:
        """Convert a QuotaRecord to a plain dict."""
        return {
            "quota_id": rec.quota_id,
            "pipeline_id": rec.pipeline_id,
            "resource_type": rec.resource_type,
            "max_amount": rec.max_amount,
            "used_amount": rec.used_amount,
            "created_at": rec.created_at,
        }

    def _fire(self, action: str, key: Tuple[str, str]) -> None:
        """Invoke all registered callbacks with the given action and key."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, key)
            except Exception:
                logger.warning("pipeline_quota_store.callback_error", action=action, key=key)

    # ------------------------------------------------------------------
    # Quota management
    # ------------------------------------------------------------------

    def set_quota(self, pipeline_id: str, resource_type: str, max_amount: float) -> str:
        """Set or update a quota for a pipeline/resource pair.

        If the combination already exists the max_amount is updated and the
        existing quota_id is returned. Otherwise a new quota is created.

        Returns the quota_id (``pqs-...``).
        """
        with self._lock:
            key = (pipeline_id, resource_type)
            existing = self._quotas.get(key)
            if existing is not None:
                existing.max_amount = max_amount
                self._stats["total_quotas_updated"] += 1
                logger.info(
                    "pipeline_quota_store.quota_updated",
                    quota_id=existing.quota_id,
                    pipeline_id=pipeline_id,
                    resource_type=resource_type,
                    max_amount=max_amount,
                )
                self._fire("quota_updated", key)
                return existing.quota_id

            quota_id = self._generate_id("pqs-", f"{pipeline_id}:{resource_type}")
            now = time.time()
            rec = QuotaRecord(
                quota_id=quota_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
                max_amount=max_amount,
                used_amount=0.0,
                created_at=now,
                seq=self._seq,
            )
            self._quotas[key] = rec
            self._stats["total_quotas_created"] += 1
            logger.info(
                "pipeline_quota_store.quota_created",
                quota_id=quota_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
                max_amount=max_amount,
            )
            self._fire("quota_created", key)
            return quota_id

    def get_quota(self, pipeline_id: str, resource_type: str) -> Optional[Dict[str, Any]]:
        """Return the quota dict for a pipeline/resource pair, or ``None``."""
        with self._lock:
            rec = self._quotas.get((pipeline_id, resource_type))
            if rec is None:
                return None
            return self._quota_to_dict(rec)

    def consume(self, pipeline_id: str, resource_type: str, amount: float) -> bool:
        """Consume *amount* from the quota.

        Returns ``True`` if enough remaining capacity exists, ``False`` if
        the consumption would exceed *max_amount*.
        """
        with self._lock:
            key = (pipeline_id, resource_type)
            rec = self._quotas.get(key)
            if rec is None:
                return False
            if amount <= 0:
                return False
            if rec.used_amount + amount > rec.max_amount:
                self._stats["total_exceeded"] += 1
                logger.debug(
                    "pipeline_quota_store.consume_exceeded",
                    pipeline_id=pipeline_id,
                    resource_type=resource_type,
                    amount=amount,
                    used=rec.used_amount,
                    max=rec.max_amount,
                )
                return False
            rec.used_amount += amount
            self._stats["total_consumes"] += 1
            self._fire("quota_consumed", key)
            return True

    def release(self, pipeline_id: str, resource_type: str, amount: float) -> bool:
        """Release *amount* back into the quota (won't go below 0).

        Returns ``True`` if the quota exists and was released, ``False`` if
        the quota was not found.
        """
        with self._lock:
            key = (pipeline_id, resource_type)
            rec = self._quotas.get(key)
            if rec is None:
                return False
            if amount <= 0:
                return False
            rec.used_amount = max(0.0, rec.used_amount - amount)
            self._stats["total_releases"] += 1
            self._fire("quota_released", key)
            return True

    def get_remaining(self, pipeline_id: str, resource_type: str) -> float:
        """Return remaining quota (max - used), or ``0.0`` if not found."""
        with self._lock:
            rec = self._quotas.get((pipeline_id, resource_type))
            if rec is None:
                return 0.0
            return rec.max_amount - rec.used_amount

    def get_utilization(self, pipeline_id: str, resource_type: str) -> float:
        """Return the used/max ratio. ``0.0`` if not found."""
        with self._lock:
            rec = self._quotas.get((pipeline_id, resource_type))
            if rec is None:
                return 0.0
            if rec.max_amount <= 0:
                return 0.0
            return rec.used_amount / rec.max_amount

    def reset_quota(self, pipeline_id: str, resource_type: str) -> bool:
        """Reset used_amount to 0. Returns ``True`` if reset, ``False`` if not found."""
        with self._lock:
            key = (pipeline_id, resource_type)
            rec = self._quotas.get(key)
            if rec is None:
                return False
            rec.used_amount = 0.0
            self._stats["total_resets"] += 1
            logger.info(
                "pipeline_quota_store.quota_reset",
                quota_id=rec.quota_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
            )
            self._fire("quota_reset", key)
            return True

    def remove_quota(self, pipeline_id: str, resource_type: str) -> bool:
        """Remove a quota entirely. Returns ``True`` if removed, ``False`` if not found."""
        with self._lock:
            key = (pipeline_id, resource_type)
            if key not in self._quotas:
                return False
            removed = self._quotas.pop(key)
            self._stats["total_quotas_removed"] += 1
            logger.info(
                "pipeline_quota_store.quota_removed",
                quota_id=removed.quota_id,
                pipeline_id=pipeline_id,
                resource_type=resource_type,
            )
            self._fire("quota_removed", key)
            return True

    # ------------------------------------------------------------------
    # Listing / querying
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """Return a list of unique pipeline_ids that have quotas."""
        with self._lock:
            seen: set = set()
            result: List[str] = []
            for (pid, _rt) in self._quotas:
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)
            return result

    def get_pipeline_quotas(self, pipeline_id: str) -> List[Dict[str, Any]]:
        """Return all quota dicts for a given pipeline."""
        with self._lock:
            result: List[Dict[str, Any]] = []
            for (pid, _rt), rec in self._quotas.items():
                if pid == pipeline_id:
                    result.append(self._quota_to_dict(rec))
            return result

    def get_quota_count(self) -> int:
        """Return the total number of tracked quotas."""
        with self._lock:
            return len(self._quotas)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a named callback for quota mutations."""
        self._callbacks[name] = callback

    def remove_callback(self, name: str) -> bool:
        """Remove a named callback. Returns ``True`` if it existed."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / lifecycle
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        with self._lock:
            total_max = sum(r.max_amount for r in self._quotas.values())
            total_used = sum(r.used_amount for r in self._quotas.values())
            return {
                **self._stats,
                "active_quotas": len(self._quotas),
                "total_max_amount": total_max,
                "total_used_amount": total_used,
                "overall_utilization": total_used / total_max if total_max > 0 else 0.0,
            }

    def reset(self) -> None:
        """Clear all quotas, callbacks, and stats."""
        with self._lock:
            self._quotas.clear()
            self._callbacks.clear()
            self._seq = 0
            self._stats = {k: 0 for k in self._stats}
            logger.info("pipeline_quota_store.reset")
