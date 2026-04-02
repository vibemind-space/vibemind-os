"""Pipeline notification dispatcher.

Dispatches notifications to agents and external channels based on
configurable rules, severity filters, and delivery preferences.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _Notification:
    """A notification entry."""
    notification_id: str = ""
    title: str = ""
    message: str = ""
    severity: str = "info"
    source: str = ""
    channel: str = "internal"
    recipients: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, delivered, failed, dismissed
    tags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: float = 0.0
    delivered_at: float = 0.0
    seq: int = 0


@dataclass
class _Subscription:
    """A notification subscription."""
    subscription_id: str = ""
    agent: str = ""
    channel: str = ""
    severity_filter: str = "info"  # minimum severity
    source_filter: str = ""
    tag_filter: str = ""
    enabled: bool = True
    created_at: float = 0.0


class PipelineNotificationDispatcher:
    """Dispatches notifications to agents and channels."""

    SEVERITIES = ("debug", "info", "warning", "error", "critical")
    CHANNELS = ("internal", "email", "slack", "webhook", "log")
    STATUSES = ("pending", "delivered", "failed", "dismissed")

    def __init__(self, max_notifications: int = 100000,
                 max_subscriptions: int = 10000):
        self._max_notifications = max_notifications
        self._max_subscriptions = max_subscriptions
        self._notifications: Dict[str, _Notification] = {}
        self._subscriptions: Dict[str, _Subscription] = {}
        self._notif_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_dispatched": 0,
            "total_delivered": 0,
            "total_failed": 0,
            "total_dismissed": 0,
        }

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def dispatch(self, title: str, message: str,
                 severity: str = "info", source: str = "",
                 channel: str = "internal",
                 recipients: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None,
                 metadata: Optional[Dict] = None) -> str:
        """Dispatch a notification."""
        if not title or not message:
            return ""
        if severity not in self.SEVERITIES:
            return ""
        if channel not in self.CHANNELS:
            return ""
        if len(self._notifications) >= self._max_notifications:
            self._prune_notifications()

        self._notif_seq += 1
        nid = "notif-" + hashlib.md5(
            f"{title}{time.time()}{self._notif_seq}".encode()
        ).hexdigest()[:12]

        # Auto-add subscribers as recipients
        actual_recipients = list(recipients or [])
        for sub in self._subscriptions.values():
            if not sub.enabled:
                continue
            if sub.channel and sub.channel != channel:
                continue
            if sub.severity_filter:
                min_idx = self.SEVERITIES.index(sub.severity_filter)
                curr_idx = self.SEVERITIES.index(severity)
                if curr_idx < min_idx:
                    continue
            if sub.source_filter and sub.source_filter != source:
                continue
            if sub.tag_filter and sub.tag_filter not in (tags or []):
                continue
            if sub.agent not in actual_recipients:
                actual_recipients.append(sub.agent)

        self._notifications[nid] = _Notification(
            notification_id=nid,
            title=title,
            message=message,
            severity=severity,
            source=source,
            channel=channel,
            recipients=actual_recipients,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=time.time(),
            seq=self._notif_seq,
        )
        self._stats["total_dispatched"] += 1
        self._fire("notification_dispatched", {
            "notification_id": nid, "title": title,
            "severity": severity, "recipient_count": len(actual_recipients),
        })
        return nid

    def get_notification(self, notification_id: str) -> Optional[Dict]:
        """Get notification info."""
        n = self._notifications.get(notification_id)
        if not n:
            return None
        return {
            "notification_id": n.notification_id,
            "title": n.title,
            "message": n.message,
            "severity": n.severity,
            "source": n.source,
            "channel": n.channel,
            "recipients": list(n.recipients),
            "status": n.status,
            "tags": list(n.tags),
            "timestamp": n.timestamp,
        }

    def mark_delivered(self, notification_id: str) -> bool:
        """Mark notification as delivered."""
        n = self._notifications.get(notification_id)
        if not n or n.status != "pending":
            return False
        n.status = "delivered"
        n.delivered_at = time.time()
        self._stats["total_delivered"] += 1
        return True

    def mark_failed(self, notification_id: str, reason: str = "") -> bool:
        """Mark notification as failed."""
        n = self._notifications.get(notification_id)
        if not n or n.status != "pending":
            return False
        n.status = "failed"
        if reason:
            n.metadata["fail_reason"] = reason
        self._stats["total_failed"] += 1
        return True

    def dismiss(self, notification_id: str) -> bool:
        """Dismiss a notification."""
        n = self._notifications.get(notification_id)
        if not n or n.status == "dismissed":
            return False
        n.status = "dismissed"
        self._stats["total_dismissed"] += 1
        return True

    def remove_notification(self, notification_id: str) -> bool:
        """Remove notification."""
        if notification_id not in self._notifications:
            return False
        del self._notifications[notification_id]
        return True

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, agent: str, channel: str = "",
                  severity_filter: str = "info",
                  source_filter: str = "",
                  tag_filter: str = "") -> str:
        """Subscribe an agent to notifications."""
        if not agent:
            return ""
        if severity_filter not in self.SEVERITIES:
            return ""
        if len(self._subscriptions) >= self._max_subscriptions:
            return ""

        sid = "sub-" + hashlib.md5(
            f"{agent}{channel}{time.time()}{len(self._subscriptions)}".encode()
        ).hexdigest()[:12]

        self._subscriptions[sid] = _Subscription(
            subscription_id=sid,
            agent=agent,
            channel=channel,
            severity_filter=severity_filter,
            source_filter=source_filter,
            tag_filter=tag_filter,
            created_at=time.time(),
        )
        return sid

    def get_subscription(self, subscription_id: str) -> Optional[Dict]:
        """Get subscription info."""
        s = self._subscriptions.get(subscription_id)
        if not s:
            return None
        return {
            "subscription_id": s.subscription_id,
            "agent": s.agent,
            "channel": s.channel,
            "severity_filter": s.severity_filter,
            "source_filter": s.source_filter,
            "tag_filter": s.tag_filter,
            "enabled": s.enabled,
        }

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove subscription."""
        if subscription_id not in self._subscriptions:
            return False
        del self._subscriptions[subscription_id]
        return True

    def enable_subscription(self, subscription_id: str) -> bool:
        """Enable subscription."""
        s = self._subscriptions.get(subscription_id)
        if not s or s.enabled:
            return False
        s.enabled = True
        return True

    def disable_subscription(self, subscription_id: str) -> bool:
        """Disable subscription."""
        s = self._subscriptions.get(subscription_id)
        if not s or not s.enabled:
            return False
        s.enabled = False
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_notifications(self, severity: Optional[str] = None,
                             channel: Optional[str] = None,
                             status: Optional[str] = None,
                             source: Optional[str] = None,
                             tag: Optional[str] = None,
                             limit: int = 100) -> List[Dict]:
        """Search notifications."""
        result = []
        for n in self._notifications.values():
            if severity and n.severity != severity:
                continue
            if channel and n.channel != channel:
                continue
            if status and n.status != status:
                continue
            if source and n.source != source:
                continue
            if tag and tag not in n.tags:
                continue
            result.append({
                "notification_id": n.notification_id,
                "title": n.title,
                "severity": n.severity,
                "channel": n.channel,
                "status": n.status,
                "recipient_count": len(n.recipients),
                "seq": n.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_agent_notifications(self, agent: str,
                                unread_only: bool = False,
                                limit: int = 50) -> List[Dict]:
        """Get notifications for an agent."""
        result = []
        for n in self._notifications.values():
            if agent not in n.recipients:
                continue
            if unread_only and n.status != "pending":
                continue
            result.append({
                "notification_id": n.notification_id,
                "title": n.title,
                "severity": n.severity,
                "status": n.status,
                "timestamp": n.timestamp,
                "seq": n.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_severity_counts(self) -> Dict[str, int]:
        """Get notification counts by severity."""
        counts = {s: 0 for s in self.SEVERITIES}
        for n in self._notifications.values():
            counts[n.severity] += 1
        return counts

    def list_subscriptions(self, agent: Optional[str] = None,
                           enabled_only: bool = False) -> List[Dict]:
        """List subscriptions."""
        result = []
        for s in self._subscriptions.values():
            if agent and s.agent != agent:
                continue
            if enabled_only and not s.enabled:
                continue
            result.append({
                "subscription_id": s.subscription_id,
                "agent": s.agent,
                "channel": s.channel,
                "severity_filter": s.severity_filter,
                "enabled": s.enabled,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune_notifications(self) -> None:
        """Remove oldest delivered/failed/dismissed notifications."""
        prunable = [(k, v) for k, v in self._notifications.items()
                    if v.status in ("delivered", "failed", "dismissed")]
        prunable.sort(key=lambda x: x[1].seq)
        to_remove = max(len(prunable) // 2, len(self._notifications) // 4)
        for k, _ in prunable[:to_remove]:
            del self._notifications[k]

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
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
            "current_notifications": len(self._notifications),
            "pending_notifications": sum(
                1 for n in self._notifications.values() if n.status == "pending"
            ),
            "current_subscriptions": len(self._subscriptions),
            "active_subscriptions": sum(
                1 for s in self._subscriptions.values() if s.enabled
            ),
        }

    def reset(self) -> None:
        self._notifications.clear()
        self._subscriptions.clear()
        self._notif_seq = 0
        self._stats = {k: 0 for k in self._stats}
