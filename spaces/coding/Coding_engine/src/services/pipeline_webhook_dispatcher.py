"""Pipeline webhook dispatcher — manages webhook endpoints and event dispatch."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class WebhookEndpoint:
    """A registered webhook endpoint."""
    endpoint_id: str
    name: str
    url: str
    events: Set[str] = field(default_factory=set)  # Empty = all events
    secret: str = ""
    enabled: bool = True
    max_retries: int = 3
    timeout_seconds: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    # Stats
    total_dispatched: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    last_dispatched_at: float = 0.0
    last_status: str = ""


@dataclass
class DispatchRecord:
    """Record of a webhook dispatch."""
    dispatch_id: str
    endpoint_id: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, success, failed
    attempts: int = 0
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


class PipelineWebhookDispatcher:
    """Manages webhook endpoints and dispatches events."""

    def __init__(self, max_endpoints: int = 200, max_records: int = 10000):
        self._endpoints: Dict[str, WebhookEndpoint] = {}
        self._records: Dict[str, DispatchRecord] = {}
        self._dispatch_handler: Optional[Callable] = None
        self._max_endpoints = max_endpoints
        self._max_records = max_records
        self._callbacks: Dict[str, Any] = {}

        # Stats
        self._total_endpoints_created = 0
        self._total_dispatches = 0
        self._total_successes = 0
        self._total_failures = 0

    # ── Endpoint Management ──

    def register_endpoint(self, name: str, url: str, events: Optional[Set[str]] = None,
                          secret: str = "", max_retries: int = 3,
                          timeout_seconds: float = 30.0, enabled: bool = True,
                          metadata: Optional[Dict] = None) -> str:
        """Register a webhook endpoint. Returns endpoint_id."""
        if not url:
            return ""
        if len(self._endpoints) >= self._max_endpoints:
            return ""

        endpoint_id = f"wh-{uuid.uuid4().hex[:8]}"
        self._endpoints[endpoint_id] = WebhookEndpoint(
            endpoint_id=endpoint_id,
            name=name,
            url=url,
            events=events or set(),
            secret=secret,
            enabled=enabled,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )
        self._total_endpoints_created += 1
        return endpoint_id

    def unregister_endpoint(self, endpoint_id: str) -> bool:
        """Remove a webhook endpoint."""
        if endpoint_id not in self._endpoints:
            return False
        del self._endpoints[endpoint_id]
        return True

    def get_endpoint(self, endpoint_id: str) -> Optional[Dict]:
        """Get endpoint info."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return None
        return {
            "endpoint_id": ep.endpoint_id,
            "name": ep.name,
            "url": ep.url,
            "events": list(ep.events),
            "enabled": ep.enabled,
            "max_retries": ep.max_retries,
            "timeout_seconds": ep.timeout_seconds,
            "total_dispatched": ep.total_dispatched,
            "total_succeeded": ep.total_succeeded,
            "total_failed": ep.total_failed,
            "last_dispatched_at": ep.last_dispatched_at,
            "last_status": ep.last_status,
            "metadata": dict(ep.metadata),
        }

    def enable_endpoint(self, endpoint_id: str) -> bool:
        """Enable an endpoint."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return False
        if ep.enabled:
            return False
        ep.enabled = True
        return True

    def disable_endpoint(self, endpoint_id: str) -> bool:
        """Disable an endpoint."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return False
        if not ep.enabled:
            return False
        ep.enabled = False
        return True

    def update_endpoint(self, endpoint_id: str, url: str = "",
                        max_retries: int = -1, timeout_seconds: float = -1.0) -> bool:
        """Update endpoint settings."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return False
        if url:
            ep.url = url
        if max_retries >= 0:
            ep.max_retries = max_retries
        if timeout_seconds >= 0:
            ep.timeout_seconds = timeout_seconds
        return True

    def add_event_filter(self, endpoint_id: str, event_type: str) -> bool:
        """Add an event filter to endpoint."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return False
        if event_type in ep.events:
            return False
        ep.events.add(event_type)
        return True

    def remove_event_filter(self, endpoint_id: str, event_type: str) -> bool:
        """Remove an event filter from endpoint."""
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            return False
        if event_type not in ep.events:
            return False
        ep.events.discard(event_type)
        return True

    def list_endpoints(self, enabled_only: bool = False) -> List[Dict]:
        """List all endpoints."""
        result = []
        for ep in self._endpoints.values():
            if enabled_only and not ep.enabled:
                continue
            info = self.get_endpoint(ep.endpoint_id)
            if info:
                result.append(info)
        return result

    # ── Dispatch ──

    def set_dispatch_handler(self, handler: Callable) -> None:
        """Set the actual HTTP dispatch handler (for testing/mocking).

        Handler signature: handler(url, event_type, payload, secret, timeout) -> bool
        """
        self._dispatch_handler = handler

    def dispatch(self, event_type: str, payload: Optional[Dict] = None) -> List[Dict]:
        """Dispatch an event to all matching endpoints. Returns dispatch results."""
        results = []
        payload = payload or {}

        for ep in self._endpoints.values():
            if not ep.enabled:
                continue
            # Check event filter (empty = all events)
            if ep.events and event_type not in ep.events:
                continue

            dispatch_id = self._dispatch_single(ep, event_type, payload)
            record = self._records.get(dispatch_id)
            if record:
                results.append({
                    "dispatch_id": dispatch_id,
                    "endpoint_id": ep.endpoint_id,
                    "endpoint_name": ep.name,
                    "status": record.status,
                    "attempts": record.attempts,
                })

        self._total_dispatches += 1
        return results

    def _dispatch_single(self, ep: WebhookEndpoint, event_type: str,
                         payload: Dict) -> str:
        """Dispatch to a single endpoint with retries."""
        # Prune records if at max
        if len(self._records) >= self._max_records:
            oldest = min(self._records.values(), key=lambda r: r.created_at)
            del self._records[oldest.dispatch_id]

        dispatch_id = f"disp-{uuid.uuid4().hex[:8]}"
        record = DispatchRecord(
            dispatch_id=dispatch_id,
            endpoint_id=ep.endpoint_id,
            event_type=event_type,
            payload=dict(payload),
        )

        success = False
        for attempt in range(1, ep.max_retries + 1):
            record.attempts = attempt
            if self._dispatch_handler:
                try:
                    success = self._dispatch_handler(
                        ep.url, event_type, payload, ep.secret, ep.timeout_seconds,
                    )
                except Exception as e:
                    record.error = str(e)
                    success = False
            else:
                # No handler = simulate success
                success = True

            if success:
                break

        now = time.time()
        record.completed_at = now
        ep.last_dispatched_at = now
        ep.total_dispatched += 1

        if success:
            record.status = "success"
            ep.total_succeeded += 1
            ep.last_status = "success"
            self._total_successes += 1
        else:
            record.status = "failed"
            ep.total_failed += 1
            ep.last_status = "failed"
            self._total_failures += 1

        self._records[dispatch_id] = record
        self._fire_callbacks(dispatch_id, ep.endpoint_id, event_type, record.status)
        return dispatch_id

    def retry_dispatch(self, dispatch_id: str) -> bool:
        """Retry a failed dispatch."""
        record = self._records.get(dispatch_id)
        if record is None or record.status != "failed":
            return False

        ep = self._endpoints.get(record.endpoint_id)
        if ep is None:
            return False

        success = False
        if self._dispatch_handler:
            try:
                success = self._dispatch_handler(
                    ep.url, record.event_type, record.payload, ep.secret, ep.timeout_seconds,
                )
            except Exception:
                success = False
        else:
            success = True

        record.attempts += 1
        record.completed_at = time.time()

        if success:
            record.status = "success"
            ep.total_succeeded += 1
            ep.last_status = "success"
            self._total_successes += 1
        return success

    # ── Records ──

    def get_dispatch(self, dispatch_id: str) -> Optional[Dict]:
        """Get dispatch record."""
        rec = self._records.get(dispatch_id)
        if rec is None:
            return None
        return {
            "dispatch_id": rec.dispatch_id,
            "endpoint_id": rec.endpoint_id,
            "event_type": rec.event_type,
            "status": rec.status,
            "attempts": rec.attempts,
            "error": rec.error,
            "created_at": rec.created_at,
            "completed_at": rec.completed_at,
        }

    def list_dispatches(self, endpoint_id: str = "", status: str = "",
                        event_type: str = "", limit: int = 50) -> List[Dict]:
        """List dispatch records with filters."""
        result = []
        for rec in sorted(self._records.values(), key=lambda r: -r.created_at):
            if endpoint_id and rec.endpoint_id != endpoint_id:
                continue
            if status and rec.status != status:
                continue
            if event_type and rec.event_type != event_type:
                continue
            info = self.get_dispatch(rec.dispatch_id)
            if info:
                result.append(info)
            if len(result) >= limit:
                break
        return result

    def get_failed_dispatches(self, limit: int = 50) -> List[Dict]:
        """Get all failed dispatches."""
        return self.list_dispatches(status="failed", limit=limit)

    # ── Callbacks ──

    def on_dispatch(self, name: str, callback) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire_callbacks(self, dispatch_id: str, endpoint_id: str,
                        event_type: str, status: str) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(dispatch_id, endpoint_id, event_type, status)
            except Exception:
                pass

    # ── Stats ──

    def get_stats(self) -> Dict:
        return {
            "total_endpoints": len(self._endpoints),
            "total_endpoints_created": self._total_endpoints_created,
            "total_enabled": sum(1 for ep in self._endpoints.values() if ep.enabled),
            "total_dispatches": self._total_dispatches,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "total_records": len(self._records),
            "success_rate": round(
                self._total_successes / max(1, self._total_successes + self._total_failures) * 100, 1
            ),
        }

    def reset(self) -> None:
        self._endpoints.clear()
        self._records.clear()
        self._callbacks.clear()
        self._dispatch_handler = None
        self._total_endpoints_created = 0
        self._total_dispatches = 0
        self._total_successes = 0
        self._total_failures = 0
