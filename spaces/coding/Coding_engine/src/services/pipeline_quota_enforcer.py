"""Pipeline quota enforcer - enforces usage quotas on pipelines.

Enforces usage quotas on pipelines such as max executions per hour.
Each quota tracks a pipeline+resource combination with a configurable
limit and time period.  Usage is automatically reset when the period
elapses.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class _QuotaEntry:
    """A single pipeline quota."""

    quota_id: str = ""
    pipeline_id: str = ""
    resource: str = ""
    limit: int = 0
    period: str = "hour"
    usage: int = 0
    period_start: float = 0.0
    created_at: float = 0.0
    seq: int = 0


# Period durations in seconds
_PERIOD_SECONDS: Dict[str, float] = {
    "minute": 60.0,
    "hour": 3600.0,
    "day": 86400.0,
}


# ---------------------------------------------------------------------------
# Pipeline Quota Enforcer
# ---------------------------------------------------------------------------

class PipelineQuotaEnforcer:
    """Enforces usage quotas on pipelines.

    Parameters
    ----------
    max_entries:
        Maximum number of quota entries allowed.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._entries: Dict[str, _QuotaEntry] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0

        # secondary index: (pipeline_id, resource) -> quota_id
        self._key_index: Dict[tuple, str] = {}

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _make_id(self, pipeline_id: str, resource: str) -> str:
        raw = f"{pipeline_id}-{resource}-{time.time()}-{self._seq}"
        return "pqe-" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Period reset helper
    # ------------------------------------------------------------------

    def _check_period_reset(self, entry: _QuotaEntry) -> None:
        """Reset usage if the current period has elapsed."""
        period_secs = _PERIOD_SECONDS.get(entry.period, 3600.0)
        elapsed = time.time() - entry.period_start
        if elapsed >= period_secs:
            entry.usage = 0
            entry.period_start = time.time()
            self._seq += 1
            entry.seq = self._seq

    # ------------------------------------------------------------------
    # Lookup helper
    # ------------------------------------------------------------------

    def _find_entry(self, pipeline_id: str, resource: str) -> Optional[_QuotaEntry]:
        """Find a quota entry by pipeline_id and resource, with period reset."""
        key = (pipeline_id, resource)
        quota_id = self._key_index.get(key)
        if quota_id is None:
            return None
        entry = self._entries.get(quota_id)
        if entry is None:
            # stale index entry
            del self._key_index[key]
            return None
        self._check_period_reset(entry)
        return entry

    # ------------------------------------------------------------------
    # Quota CRUD
    # ------------------------------------------------------------------

    def create_quota(
        self,
        pipeline_id: str,
        resource: str,
        limit: int,
        period: str = "hour",
    ) -> str:
        """Create a quota for a pipeline+resource combination.

        Returns the quota ID, or empty string on failure.
        """
        if not pipeline_id or not resource:
            return ""
        if limit <= 0:
            return ""
        if period not in _PERIOD_SECONDS:
            return ""
        if len(self._entries) >= self._max_entries:
            return ""

        # If a quota already exists for this combination, update it
        key = (pipeline_id, resource)
        existing_id = self._key_index.get(key)
        if existing_id and existing_id in self._entries:
            entry = self._entries[existing_id]
            entry.limit = limit
            entry.period = period
            self._seq += 1
            entry.seq = self._seq
            self._fire("quota_updated", asdict(entry))
            return existing_id

        self._seq += 1
        now = time.time()
        quota_id = self._make_id(pipeline_id, resource)

        entry = _QuotaEntry(
            quota_id=quota_id,
            pipeline_id=pipeline_id,
            resource=resource,
            limit=limit,
            period=period,
            usage=0,
            period_start=now,
            created_at=now,
            seq=self._seq,
        )
        self._entries[quota_id] = entry
        self._key_index[key] = quota_id
        self._fire("quota_created", asdict(entry))
        return quota_id

    def get_quota(self, quota_id: str) -> Optional[Dict]:
        """Get quota details by ID."""
        entry = self._entries.get(quota_id)
        if entry is None:
            return None
        self._check_period_reset(entry)
        return asdict(entry)

    # ------------------------------------------------------------------
    # Usage enforcement
    # ------------------------------------------------------------------

    def check_quota(self, pipeline_id: str, resource: str) -> bool:
        """Check if quota is available (usage < limit).

        Returns True if usage is under the limit or no quota exists.
        """
        entry = self._find_entry(pipeline_id, resource)
        if entry is None:
            return True
        return entry.usage < entry.limit

    def consume_quota(
        self,
        pipeline_id: str,
        resource: str,
        amount: int = 1,
    ) -> bool:
        """Consume quota.  Returns False if it would exceed the limit."""
        if amount <= 0:
            return False
        entry = self._find_entry(pipeline_id, resource)
        if entry is None:
            return False
        if entry.usage + amount > entry.limit:
            self._fire("quota_exceeded", asdict(entry))
            return False

        entry.usage += amount
        self._seq += 1
        entry.seq = self._seq
        self._fire("quota_consumed", asdict(entry))
        return True

    def get_usage(self, pipeline_id: str, resource: str) -> int:
        """Get current usage for a pipeline+resource quota."""
        entry = self._find_entry(pipeline_id, resource)
        if entry is None:
            return 0
        return entry.usage

    def get_remaining(self, pipeline_id: str, resource: str) -> int:
        """Get remaining quota for a pipeline+resource combination."""
        entry = self._find_entry(pipeline_id, resource)
        if entry is None:
            return 0
        remaining = entry.limit - entry.usage
        return max(0, remaining)

    def reset_quota(self, pipeline_id: str, resource: str) -> bool:
        """Reset usage to 0 for a pipeline+resource quota."""
        entry = self._find_entry(pipeline_id, resource)
        if entry is None:
            return False
        entry.usage = 0
        entry.period_start = time.time()
        self._seq += 1
        entry.seq = self._seq
        self._fire("quota_reset", asdict(entry))
        return True

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_pipelines(self) -> List[str]:
        """List all unique pipeline IDs that have quotas."""
        pipelines: set = set()
        for entry in self._entries.values():
            pipelines.add(entry.pipeline_id)
        return sorted(pipelines)

    def get_quota_count(self) -> int:
        """Return the total number of quota entries."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a callback.  Returns False if name already registered."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a callback by name.  Returns False if not found."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Any) -> None:
        """Fire all registered callbacks with the given action and data."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return aggregate statistics."""
        total_usage = sum(e.usage for e in self._entries.values())
        total_limit = sum(e.limit for e in self._entries.values())
        return {
            "total_quotas": len(self._entries),
            "total_usage": total_usage,
            "total_limit": total_limit,
            "total_pipelines": len(set(e.pipeline_id for e in self._entries.values())),
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Clear all entries, callbacks, and reset sequence counter."""
        self._entries.clear()
        self._key_index.clear()
        self._callbacks.clear()
        self._seq = 0
