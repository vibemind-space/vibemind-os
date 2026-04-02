"""Pipeline trigger store.

Manages pipeline execution triggers -- conditions and events that cause
pipelines to start.  Supports creating, enabling, disabling, and firing
triggers with fire-history tracking, callback notifications, thread-safe
access, and automatic max-entries pruning.
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
class TriggerRecord:
    """A single pipeline trigger definition."""

    trigger_id: str = ""
    pipeline_name: str = ""
    event_type: str = ""
    condition: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    fire_count: int = 0
    last_fired: Optional[float] = None
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class FiringRecord:
    """A single trigger-firing event."""

    fire_id: str = ""
    trigger_id: str = ""
    timestamp: float = 0.0
    context: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Pipeline Trigger Store
# ---------------------------------------------------------------------------

class PipelineTriggerStore:
    """Manages pipeline execution triggers with firing history, enable/disable
    toggling, callback notifications, and thread-safe access."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._triggers: Dict[str, TriggerRecord] = {}
        self._fire_history: Dict[str, List[FiringRecord]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._seq: int = 0
        self._fire_seq: int = 0
        self._stats = {
            "total_created": 0,
            "total_deleted": 0,
            "total_fired": 0,
            "total_enabled": 0,
            "total_disabled": 0,
            "total_lookups": 0,
            "total_fire_skipped": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str, prefix: str = "ptr-") -> str:
        """Generate a collision-free ID using SHA-256."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}{digest}"

    def _next_fire_id(self, trigger_id: str) -> str:
        """Generate a unique firing ID."""
        self._fire_seq += 1
        raw = f"{trigger_id}:fire:{time.time()}:{self._fire_seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"ptf-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity.  Caller must hold lock."""
        if len(self._triggers) < self._max_entries:
            return
        sorted_entries = sorted(
            self._triggers.values(), key=lambda t: t.created_at
        )
        remove_count = len(self._triggers) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            self._fire_history.pop(entry.trigger_id, None)
            del self._triggers[entry.trigger_id]
            logger.debug("trigger_pruned: %s", entry.trigger_id)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _record_to_dict(record: TriggerRecord) -> Dict[str, Any]:
        """Convert a TriggerRecord to a plain dict."""
        return {
            "trigger_id": record.trigger_id,
            "pipeline_name": record.pipeline_name,
            "event_type": record.event_type,
            "condition": record.condition,
            "metadata": dict(record.metadata),
            "enabled": record.enabled,
            "fire_count": record.fire_count,
            "last_fired": record.last_fired,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _firing_to_dict(firing: FiringRecord) -> Dict[str, Any]:
        """Convert a FiringRecord to a plain dict."""
        return {
            "fire_id": firing.fire_id,
            "trigger_id": firing.trigger_id,
            "timestamp": firing.timestamp,
            "context": dict(firing.context) if firing.context else None,
        }

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback under *name*.

        If a callback with the same name already exists it is silently
        replaced.
        """
        with self._lock:
            self._callbacks[name] = callback
            logger.debug("callback_registered: %s", name)

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback.  Returns False if *name* not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            logger.debug("callback_removed: %s", name)
            return True

    def _fire_callback(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with *action* and *detail*.

        Exceptions inside individual callbacks are logged but do not
        propagate.
        """
        # Snapshot the callbacks while holding the lock.
        with self._lock:
            cbs = list(self._callbacks.values())

        for cb in cbs:
            try:
                cb(action, detail)
            except Exception:
                logger.exception("callback_error: action=%s", action)

    # ------------------------------------------------------------------
    # create_trigger
    # ------------------------------------------------------------------

    def create_trigger(
        self,
        pipeline_name: str,
        event_type: str,
        condition: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new pipeline trigger.

        The trigger starts in the *enabled* state.  Returns the new
        ``trigger_id`` (prefixed ``ptr-``).
        """
        if not pipeline_name or not event_type:
            logger.warning(
                "create_trigger_invalid_input: pipeline_name=%s event_type=%s",
                pipeline_name,
                event_type,
            )
            return ""

        with self._lock:
            self._prune_if_needed()

            now = time.time()
            trigger_id = self._next_id(f"{pipeline_name}:{event_type}")

            record = TriggerRecord(
                trigger_id=trigger_id,
                pipeline_name=pipeline_name,
                event_type=event_type,
                condition=condition,
                metadata=dict(metadata) if metadata else {},
                enabled=True,
                fire_count=0,
                last_fired=None,
                created_at=now,
                updated_at=now,
            )

            self._triggers[trigger_id] = record
            self._fire_history[trigger_id] = []
            self._stats["total_created"] += 1

        logger.info(
            "trigger_created: id=%s pipeline=%s event=%s",
            trigger_id,
            pipeline_name,
            event_type,
        )
        self._fire_callback("trigger_created", self._record_to_dict(record))
        return trigger_id

    # ------------------------------------------------------------------
    # get_trigger
    # ------------------------------------------------------------------

    def get_trigger(self, trigger_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a trigger by ID.  Returns ``None`` if not found."""
        with self._lock:
            self._stats["total_lookups"] += 1
            record = self._triggers.get(trigger_id)
            if record is None:
                return None
            return self._record_to_dict(record)

    # ------------------------------------------------------------------
    # enable_trigger / disable_trigger
    # ------------------------------------------------------------------

    def enable_trigger(self, trigger_id: str) -> bool:
        """Enable a trigger.  Returns ``False`` if *trigger_id* not found."""
        with self._lock:
            record = self._triggers.get(trigger_id)
            if record is None:
                logger.warning("enable_trigger_not_found: %s", trigger_id)
                return False
            if record.enabled:
                return True
            record.enabled = True
            record.updated_at = time.time()
            self._stats["total_enabled"] += 1

        logger.info("trigger_enabled: %s", trigger_id)
        self._fire_callback("trigger_enabled", self._record_to_dict(record))
        return True

    def disable_trigger(self, trigger_id: str) -> bool:
        """Disable a trigger.  Returns ``False`` if *trigger_id* not found."""
        with self._lock:
            record = self._triggers.get(trigger_id)
            if record is None:
                logger.warning("disable_trigger_not_found: %s", trigger_id)
                return False
            if not record.enabled:
                return True
            record.enabled = False
            record.updated_at = time.time()
            self._stats["total_disabled"] += 1

        logger.info("trigger_disabled: %s", trigger_id)
        self._fire_callback("trigger_disabled", self._record_to_dict(record))
        return True

    # ------------------------------------------------------------------
    # fire_trigger
    # ------------------------------------------------------------------

    def fire_trigger(
        self,
        trigger_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fire a trigger if it exists and is enabled.

        Returns a firing-record dict containing ``fire_id``, ``timestamp``,
        and ``context``.  Returns ``None`` if the trigger is not found or
        is currently disabled.
        """
        with self._lock:
            record = self._triggers.get(trigger_id)
            if record is None:
                logger.warning("fire_trigger_not_found: %s", trigger_id)
                return None
            if not record.enabled:
                self._stats["total_fire_skipped"] += 1
                logger.warning("fire_trigger_disabled: %s", trigger_id)
                return None

            now = time.time()
            fire_id = self._next_fire_id(trigger_id)

            firing = FiringRecord(
                fire_id=fire_id,
                trigger_id=trigger_id,
                timestamp=now,
                context=dict(context) if context else None,
            )

            record.fire_count += 1
            record.last_fired = now
            record.updated_at = now
            self._stats["total_fired"] += 1

            history = self._fire_history.get(trigger_id)
            if history is None:
                history = []
                self._fire_history[trigger_id] = history
            history.append(firing)

            firing_dict = self._firing_to_dict(firing)

        logger.info(
            "trigger_fired: id=%s fire_id=%s count=%d",
            trigger_id,
            fire_id,
            record.fire_count,
        )
        self._fire_callback("trigger_fired", {
            "trigger": self._record_to_dict(record),
            "firing": firing_dict,
        })
        return firing_dict

    # ------------------------------------------------------------------
    # get_fire_history
    # ------------------------------------------------------------------

    def get_fire_history(self, trigger_id: str) -> List[Dict[str, Any]]:
        """Return the list of firing records for *trigger_id*.

        Returns an empty list if the trigger does not exist or has never
        been fired.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            history = self._fire_history.get(trigger_id, [])
            return [self._firing_to_dict(f) for f in history]

    # ------------------------------------------------------------------
    # get_triggers_for_pipeline
    # ------------------------------------------------------------------

    def get_triggers_for_pipeline(
        self, pipeline_name: str
    ) -> List[Dict[str, Any]]:
        """Return all triggers associated with *pipeline_name*.

        Results are sorted by ``created_at`` ascending.
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results = [
                self._record_to_dict(r)
                for r in self._triggers.values()
                if r.pipeline_name == pipeline_name
            ]
        results.sort(key=lambda d: d["created_at"])
        return results

    # ------------------------------------------------------------------
    # list_triggers
    # ------------------------------------------------------------------

    def list_triggers(
        self, enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List all triggers, optionally filtered to enabled ones only.

        Results are sorted by ``created_at`` descending (newest first).
        """
        with self._lock:
            self._stats["total_lookups"] += 1
            results: List[Dict[str, Any]] = []
            for record in self._triggers.values():
                if enabled_only and not record.enabled:
                    continue
                results.append(self._record_to_dict(record))
        results.sort(key=lambda d: d["created_at"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # delete_trigger
    # ------------------------------------------------------------------

    def delete_trigger(self, trigger_id: str) -> bool:
        """Delete a trigger and its fire history.

        Returns ``False`` if the *trigger_id* is not found.
        """
        with self._lock:
            record = self._triggers.get(trigger_id)
            if record is None:
                logger.warning("delete_trigger_not_found: %s", trigger_id)
                return False

            del self._triggers[trigger_id]
            self._fire_history.pop(trigger_id, None)
            self._stats["total_deleted"] += 1
            snapshot = self._record_to_dict(record)

        logger.info("trigger_deleted: %s", trigger_id)
        self._fire_callback("trigger_deleted", snapshot)
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics for the store."""
        with self._lock:
            enabled_count = sum(
                1 for r in self._triggers.values() if r.enabled
            )
            total_firings = sum(
                len(h) for h in self._fire_history.values()
            )
            return {
                **self._stats,
                "current_triggers": len(self._triggers),
                "current_enabled": enabled_count,
                "current_disabled": len(self._triggers) - enabled_count,
                "total_fire_history_entries": total_firings,
                "current_callbacks": len(self._callbacks),
                "max_entries": self._max_entries,
            }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all triggers, fire history, callbacks, and counters."""
        with self._lock:
            self._triggers.clear()
            self._fire_history.clear()
            self._callbacks.clear()
            self._seq = 0
            self._fire_seq = 0
            self._stats = {k: 0 for k in self._stats}
        logger.info("pipeline_trigger_store_reset")
