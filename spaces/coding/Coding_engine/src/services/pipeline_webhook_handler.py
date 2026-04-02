"""Pipeline Webhook Handler – manages outbound webhook registrations and deliveries.

Registers webhooks with URL endpoints, filters events by type,
tracks delivery attempts with success/failure status, and supports
retry logic for failed deliveries.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _Webhook:
    webhook_id: str
    name: str
    url: str
    events: List[str]  # event types to trigger on (empty = all)
    status: str  # active | disabled
    secret: str
    headers: Dict[str, str]
    max_retries: int
    timeout_ms: float
    tags: List[str]
    created_at: float
    seq: int


@dataclass
class _Delivery:
    delivery_id: str
    webhook_id: str
    event_type: str
    payload_summary: str
    status: str  # pending | success | failed | retrying
    attempts: int
    last_status_code: int
    last_error: str
    created_at: float
    completed_at: float
    seq: int


class PipelineWebhookHandler:
    """Manages webhook registrations and delivery tracking."""

    STATUSES = ("active", "disabled")
    DELIVERY_STATUSES = ("pending", "success", "failed", "retrying")

    def __init__(self, max_webhooks: int = 1000,
                 max_deliveries: int = 500000) -> None:
        self._max_webhooks = max_webhooks
        self._max_deliveries = max_deliveries
        self._webhooks: Dict[str, _Webhook] = {}
        self._deliveries: Dict[str, _Delivery] = {}
        self._name_index: Dict[str, str] = {}
        self._seq = 0
        self._callbacks: Dict[str, Any] = {}
        self._stats = {
            "total_webhooks_created": 0,
            "total_deliveries": 0,
            "total_successes": 0,
            "total_failures": 0,
        }

    # ------------------------------------------------------------------
    # Webhook CRUD
    # ------------------------------------------------------------------

    def register_webhook(self, name: str, url: str, events: Optional[List[str]] = None,
                         secret: str = "", headers: Optional[Dict[str, str]] = None,
                         max_retries: int = 3, timeout_ms: float = 5000.0,
                         tags: Optional[List[str]] = None) -> str:
        if not name or not url:
            return ""
        if name in self._name_index:
            return ""
        if len(self._webhooks) >= self._max_webhooks:
            return ""
        self._seq += 1
        raw = f"wh-{name}-{url}-{self._seq}-{len(self._webhooks)}"
        wid = "wh-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        wh = _Webhook(
            webhook_id=wid, name=name, url=url,
            events=list(events or []), status="active", secret=secret,
            headers=dict(headers or {}), max_retries=max_retries,
            timeout_ms=timeout_ms, tags=list(tags or []),
            created_at=time.time(), seq=self._seq,
        )
        self._webhooks[wid] = wh
        self._name_index[name] = wid
        self._stats["total_webhooks_created"] += 1
        self._fire("webhook_registered", {"webhook_id": wid, "name": name})
        return wid

    def get_webhook(self, webhook_id: str) -> Optional[Dict]:
        wh = self._webhooks.get(webhook_id)
        if wh is None:
            return None
        return self._wh_to_dict(wh)

    def get_webhook_by_name(self, name: str) -> Optional[Dict]:
        wid = self._name_index.get(name)
        if wid is None:
            return None
        return self.get_webhook(wid)

    def remove_webhook(self, webhook_id: str) -> bool:
        wh = self._webhooks.get(webhook_id)
        if wh is None:
            return False
        self._name_index.pop(wh.name, None)
        del self._webhooks[webhook_id]
        # Cascade: remove deliveries
        to_remove = [d for d in self._deliveries.values() if d.webhook_id == webhook_id]
        for d in to_remove:
            del self._deliveries[d.delivery_id]
        return True

    def disable_webhook(self, webhook_id: str) -> bool:
        wh = self._webhooks.get(webhook_id)
        if wh is None or wh.status == "disabled":
            return False
        wh.status = "disabled"
        return True

    def enable_webhook(self, webhook_id: str) -> bool:
        wh = self._webhooks.get(webhook_id)
        if wh is None or wh.status == "active":
            return False
        wh.status = "active"
        return True

    def update_webhook(self, webhook_id: str, url: str = "",
                       events: Optional[List[str]] = None,
                       max_retries: int = -1) -> bool:
        wh = self._webhooks.get(webhook_id)
        if wh is None:
            return False
        if url:
            wh.url = url
        if events is not None:
            wh.events = list(events)
        if max_retries >= 0:
            wh.max_retries = max_retries
        return True

    def list_webhooks(self, status: str = "", tag: str = "") -> List[Dict]:
        results = []
        for wh in self._webhooks.values():
            if status and wh.status != status:
                continue
            if tag and tag not in wh.tags:
                continue
            results.append(self._wh_to_dict(wh))
        results.sort(key=lambda x: x["seq"])
        return results

    # ------------------------------------------------------------------
    # Deliveries
    # ------------------------------------------------------------------

    def create_delivery(self, webhook_id: str, event_type: str,
                        payload_summary: str = "") -> str:
        wh = self._webhooks.get(webhook_id)
        if wh is None:
            return ""
        if wh.status != "active":
            return ""
        if wh.events and event_type not in wh.events:
            return ""
        if len(self._deliveries) >= self._max_deliveries:
            return ""
        self._seq += 1
        raw = f"dlv-{webhook_id}-{event_type}-{self._seq}-{len(self._deliveries)}"
        did = "dlv-" + hashlib.sha256(raw.encode()).hexdigest()[:12]
        d = _Delivery(
            delivery_id=did, webhook_id=webhook_id, event_type=event_type,
            payload_summary=payload_summary, status="pending", attempts=0,
            last_status_code=0, last_error="",
            created_at=time.time(), completed_at=0.0, seq=self._seq,
        )
        self._deliveries[did] = d
        self._stats["total_deliveries"] += 1
        self._fire("delivery_created", {"delivery_id": did, "webhook_id": webhook_id})
        return did

    def record_attempt(self, delivery_id: str, success: bool,
                       status_code: int = 0, error: str = "") -> bool:
        d = self._deliveries.get(delivery_id)
        if d is None:
            return False
        if d.status in ("success", "failed"):
            return False
        d.attempts += 1
        d.last_status_code = status_code
        d.last_error = error
        if success:
            d.status = "success"
            d.completed_at = time.time()
            self._stats["total_successes"] += 1
            self._fire("delivery_succeeded", {"delivery_id": delivery_id})
        else:
            wh = self._webhooks.get(d.webhook_id)
            max_retries = wh.max_retries if wh else 0
            if d.attempts >= max_retries:
                d.status = "failed"
                d.completed_at = time.time()
                self._stats["total_failures"] += 1
                self._fire("delivery_failed", {"delivery_id": delivery_id})
            else:
                d.status = "retrying"
        return True

    def get_delivery(self, delivery_id: str) -> Optional[Dict]:
        d = self._deliveries.get(delivery_id)
        if d is None:
            return None
        return self._dlv_to_dict(d)

    def get_webhook_deliveries(self, webhook_id: str,
                                status: str = "") -> List[Dict]:
        results = []
        for d in self._deliveries.values():
            if d.webhook_id != webhook_id:
                continue
            if status and d.status != status:
                continue
            results.append(self._dlv_to_dict(d))
        results.sort(key=lambda x: x["seq"])
        return results

    def search_deliveries(self, webhook_id: str = "", event_type: str = "",
                          status: str = "") -> List[Dict]:
        results = []
        for d in self._deliveries.values():
            if webhook_id and d.webhook_id != webhook_id:
                continue
            if event_type and d.event_type != event_type:
                continue
            if status and d.status != status:
                continue
            results.append(self._dlv_to_dict(d))
        results.sort(key=lambda x: x["seq"])
        return results

    def get_webhook_delivery_stats(self, webhook_id: str) -> Dict:
        total = 0
        successes = 0
        failures = 0
        pending = 0
        for d in self._deliveries.values():
            if d.webhook_id != webhook_id:
                continue
            total += 1
            if d.status == "success":
                successes += 1
            elif d.status == "failed":
                failures += 1
            elif d.status in ("pending", "retrying"):
                pending += 1
        return {
            "webhook_id": webhook_id,
            "total": total,
            "successes": successes,
            "failures": failures,
            "pending": pending,
            "success_rate": round(successes / total * 100, 1) if total else 0.0,
        }

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast_event(self, event_type: str,
                        payload_summary: str = "") -> List[str]:
        delivery_ids = []
        for wh in self._webhooks.values():
            if wh.status != "active":
                continue
            if wh.events and event_type not in wh.events:
                continue
            did = self.create_delivery(wh.webhook_id, event_type, payload_summary)
            if did:
                delivery_ids.append(did)
        return delivery_ids

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Any) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_webhooks": len(self._webhooks),
            "current_deliveries": len(self._deliveries),
            "active_webhooks": sum(1 for w in self._webhooks.values() if w.status == "active"),
        }

    def reset(self) -> None:
        self._webhooks.clear()
        self._deliveries.clear()
        self._name_index.clear()
        self._seq = 0
        self._stats = {
            "total_webhooks_created": 0,
            "total_deliveries": 0,
            "total_successes": 0,
            "total_failures": 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wh_to_dict(wh: _Webhook) -> Dict:
        return {
            "webhook_id": wh.webhook_id,
            "name": wh.name,
            "url": wh.url,
            "events": list(wh.events),
            "status": wh.status,
            "secret": wh.secret,
            "headers": dict(wh.headers),
            "max_retries": wh.max_retries,
            "timeout_ms": wh.timeout_ms,
            "tags": list(wh.tags),
            "created_at": wh.created_at,
            "seq": wh.seq,
        }

    @staticmethod
    def _dlv_to_dict(d: _Delivery) -> Dict:
        return {
            "delivery_id": d.delivery_id,
            "webhook_id": d.webhook_id,
            "event_type": d.event_type,
            "payload_summary": d.payload_summary,
            "status": d.status,
            "attempts": d.attempts,
            "last_status_code": d.last_status_code,
            "last_error": d.last_error,
            "created_at": d.created_at,
            "completed_at": d.completed_at,
            "seq": d.seq,
        }
