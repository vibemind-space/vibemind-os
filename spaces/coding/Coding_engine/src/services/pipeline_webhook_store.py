"""Pipeline webhook store.

Manages webhook registrations for pipeline events. Tracks which
webhooks are registered for which pipeline events, supports
enable/disable, and provides event-matching queries.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class WebhookEntry:
    """A single webhook registration."""
    webhook_id: str = ""
    pipeline_name: str = ""
    url: str = ""
    events: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = 0.0
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline Webhook Store
# ---------------------------------------------------------------------------

class PipelineWebhookStore:
    """Manages webhook registrations for pipeline events."""

    def __init__(self, max_entries: int = 10000):
        self._max_entries = max_entries
        self._webhooks: Dict[str, WebhookEntry] = {}
        self._seq: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_registered": 0,
            "total_removed": 0,
            "total_enabled": 0,
            "total_disabled": 0,
            "total_events_fired": 0,
            "total_lookups": 0,
            "total_pruned": 0,
        }

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a collision-free ID with prefix 'pws-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pws-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._webhooks) < self._max_entries:
            return
        sorted_entries = sorted(
            self._webhooks.values(), key=lambda w: w.created_at
        )
        remove_count = len(self._webhooks) - self._max_entries + 1
        for entry in sorted_entries[:remove_count]:
            del self._webhooks[entry.webhook_id]
            self._stats["total_pruned"] += 1
            logger.debug("webhook_pruned", webhook_id=entry.webhook_id)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_webhook(
        self,
        pipeline_name: str,
        url: str,
        events: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Register a new webhook. Returns the webhook_id.

        If *events* is None or empty, the webhook matches all events
        for the given pipeline.
        """
        if not pipeline_name or not url:
            logger.warning(
                "register_webhook_invalid_input",
                pipeline_name=pipeline_name,
                url=url,
            )
            return ""

        self._prune_if_needed()

        webhook_id = self._next_id(f"{pipeline_name}:{url}")
        now = time.time()

        entry = WebhookEntry(
            webhook_id=webhook_id,
            pipeline_name=pipeline_name,
            url=url,
            events=list(events) if events else [],
            headers=dict(headers) if headers else {},
            enabled=True,
            created_at=now,
            tags=list(tags) if tags else [],
        )

        self._webhooks[webhook_id] = entry
        self._stats["total_registered"] += 1

        logger.info(
            "webhook_registered",
            webhook_id=webhook_id,
            pipeline_name=pipeline_name,
            url=url,
            events=entry.events,
        )
        self._fire("webhook_registered", self._entry_to_dict(entry))
        return webhook_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_webhook(self, webhook_id: str) -> Optional[Dict]:
        """Get a single webhook by ID. Returns None if not found."""
        self._stats["total_lookups"] += 1
        entry = self._webhooks.get(webhook_id)
        if not entry:
            return None
        return self._entry_to_dict(entry)

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def enable_webhook(self, webhook_id: str) -> bool:
        """Enable a webhook. Returns True on success."""
        entry = self._webhooks.get(webhook_id)
        if not entry:
            logger.warning("enable_webhook_not_found", webhook_id=webhook_id)
            return False
        if entry.enabled:
            return True
        entry.enabled = True
        self._stats["total_enabled"] += 1
        logger.info("webhook_enabled", webhook_id=webhook_id)
        self._fire("webhook_enabled", self._entry_to_dict(entry))
        return True

    def disable_webhook(self, webhook_id: str) -> bool:
        """Disable a webhook. Returns True on success."""
        entry = self._webhooks.get(webhook_id)
        if not entry:
            logger.warning("disable_webhook_not_found", webhook_id=webhook_id)
            return False
        if not entry.enabled:
            return True
        entry.enabled = False
        self._stats["total_disabled"] += 1
        logger.info("webhook_disabled", webhook_id=webhook_id)
        self._fire("webhook_disabled", self._entry_to_dict(entry))
        return True

    # ------------------------------------------------------------------
    # Event queries
    # ------------------------------------------------------------------

    def get_webhooks_for_event(
        self, pipeline_name: str, event: str
    ) -> List[Dict]:
        """Return enabled webhooks matching a pipeline event.

        A webhook matches if it is registered for the given pipeline and
        either has no event filter (empty events list) or the event is
        in its events list.
        """
        self._stats["total_lookups"] += 1
        results = []
        for entry in self._webhooks.values():
            if not entry.enabled:
                continue
            if entry.pipeline_name != pipeline_name:
                continue
            if entry.events and event not in entry.events:
                continue
            results.append(self._entry_to_dict(entry))
        results.sort(key=lambda x: x["created_at"])
        return results

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_webhooks(
        self, pipeline_name: Optional[str] = None
    ) -> List[Dict]:
        """List all webhooks, optionally filtered by pipeline_name."""
        self._stats["total_lookups"] += 1
        entries = list(self._webhooks.values())
        if pipeline_name:
            entries = [e for e in entries if e.pipeline_name == pipeline_name]
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return [self._entry_to_dict(e) for e in entries]

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove_webhook(self, webhook_id: str) -> bool:
        """Remove a webhook by ID. Returns True on success."""
        entry = self._webhooks.get(webhook_id)
        if not entry:
            logger.warning("remove_webhook_not_found", webhook_id=webhook_id)
            return False
        data = self._entry_to_dict(entry)
        del self._webhooks[webhook_id]
        self._stats["total_removed"] += 1
        logger.info("webhook_removed", webhook_id=webhook_id)
        self._fire("webhook_removed", data)
        return True

    # ------------------------------------------------------------------
    # Fire event
    # ------------------------------------------------------------------

    def fire_event(
        self,
        pipeline_name: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Track an event firing. Returns count of matched webhooks.

        This method does *not* perform HTTP requests; it identifies
        matching webhooks and logs the match for tracking purposes.
        """
        matched = self.get_webhooks_for_event(pipeline_name, event)
        count = len(matched)
        self._stats["total_events_fired"] += 1

        if count:
            logger.info(
                "event_fired",
                pipeline_name=pipeline_name,
                event_name=event,
                matched_webhooks=count,
            )
            self._fire(
                "event_fired",
                {
                    "pipeline_name": pipeline_name,
                    "event": event,
                    "payload": payload,
                    "matched_count": count,
                    "webhook_ids": [w["webhook_id"] for w in matched],
                },
            )
        return count

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already exists."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                logger.exception("callback_error", action=action)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry_to_dict(self, entry: WebhookEntry) -> Dict:
        """Convert a WebhookEntry to a plain dict."""
        return {
            "webhook_id": entry.webhook_id,
            "pipeline_name": entry.pipeline_name,
            "url": entry.url,
            "events": list(entry.events),
            "headers": dict(entry.headers),
            "enabled": entry.enabled,
            "created_at": entry.created_at,
            "tags": list(entry.tags),
        }

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Return store statistics."""
        enabled_count = sum(
            1 for e in self._webhooks.values() if e.enabled
        )
        return {
            **self._stats,
            "current_webhooks": len(self._webhooks),
            "current_enabled": enabled_count,
            "current_disabled": len(self._webhooks) - enabled_count,
            "max_entries": self._max_entries,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._webhooks.clear()
        self._callbacks.clear()
        self._seq = 0
        self._stats = {k: 0 for k in self._stats}
        logger.info("store_reset")
