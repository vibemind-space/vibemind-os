"""Pipeline notification router.

Routes notifications to appropriate channels and subscribers.
Supports multiple delivery channels, priority routing, filtering,
and delivery tracking.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class _Channel:
    """A notification channel."""
    channel_id: str = ""
    name: str = ""
    channel_type: str = "log"  # log, webhook, email, slack, custom
    config: Dict = field(default_factory=dict)
    status: str = "active"  # active, disabled
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _Subscription:
    """A subscription linking a subscriber to channels."""
    sub_id: str = ""
    subscriber: str = ""
    channel_id: str = ""
    filter_severity: str = ""  # filter by min severity
    filter_category: str = ""  # filter by category
    status: str = "active"  # active, paused
    created_at: float = 0.0
    seq: int = 0


@dataclass
class _Notification:
    """A notification record."""
    notif_id: str = ""
    title: str = ""
    message: str = ""
    severity: str = "info"  # debug, info, warning, error, critical
    category: str = ""
    source: str = ""
    metadata: Dict = field(default_factory=dict)
    deliveries: List[str] = field(default_factory=list)  # channel_ids delivered to
    created_at: float = 0.0
    seq: int = 0


class PipelineNotificationRouter:
    """Routes notifications across the pipeline."""

    CHANNEL_TYPES = ("log", "webhook", "email", "slack", "custom")
    SEVERITIES = ("debug", "info", "warning", "error", "critical")
    SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}

    def __init__(self, max_channels: int = 1000,
                 max_subscriptions: int = 10000,
                 max_notifications: int = 100000):
        self._max_channels = max_channels
        self._max_subscriptions = max_subscriptions
        self._max_notifications = max_notifications
        self._channels: Dict[str, _Channel] = {}
        self._subscriptions: Dict[str, _Subscription] = {}
        self._notifications: Dict[str, _Notification] = {}
        self._channel_seq = 0
        self._sub_seq = 0
        self._notif_seq = 0
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_channels_created": 0,
            "total_subscriptions": 0,
            "total_notifications": 0,
            "total_deliveries": 0,
        }

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def create_channel(self, name: str, channel_type: str = "log",
                       config: Optional[Dict] = None,
                       tags: Optional[List[str]] = None) -> str:
        """Create a notification channel."""
        if not name:
            return ""
        if channel_type not in self.CHANNEL_TYPES:
            return ""
        if len(self._channels) >= self._max_channels:
            return ""

        self._channel_seq += 1
        cid = "nch-" + hashlib.md5(
            f"{name}{time.time()}{self._channel_seq}{len(self._channels)}".encode()
        ).hexdigest()[:12]

        self._channels[cid] = _Channel(
            channel_id=cid,
            name=name,
            channel_type=channel_type,
            config=config or {},
            tags=tags or [],
            created_at=time.time(),
            seq=self._channel_seq,
        )
        self._stats["total_channels_created"] += 1
        return cid

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """Get channel info."""
        c = self._channels.get(channel_id)
        if not c:
            return None
        return {
            "channel_id": c.channel_id,
            "name": c.name,
            "channel_type": c.channel_type,
            "status": c.status,
            "tags": list(c.tags),
            "seq": c.seq,
        }

    def disable_channel(self, channel_id: str) -> bool:
        c = self._channels.get(channel_id)
        if not c or c.status == "disabled":
            return False
        c.status = "disabled"
        return True

    def enable_channel(self, channel_id: str) -> bool:
        c = self._channels.get(channel_id)
        if not c or c.status == "active":
            return False
        c.status = "active"
        return True

    def remove_channel(self, channel_id: str) -> bool:
        if channel_id not in self._channels:
            return False
        del self._channels[channel_id]
        # Remove subscriptions for this channel
        to_remove = [sid for sid, s in self._subscriptions.items()
                     if s.channel_id == channel_id]
        for sid in to_remove:
            del self._subscriptions[sid]
        return True

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, subscriber: str, channel_id: str,
                  filter_severity: str = "",
                  filter_category: str = "") -> str:
        """Subscribe to a channel."""
        if not subscriber or channel_id not in self._channels:
            return ""
        if len(self._subscriptions) >= self._max_subscriptions:
            return ""

        # Check duplicate
        for s in self._subscriptions.values():
            if s.subscriber == subscriber and s.channel_id == channel_id \
               and s.status == "active":
                return ""

        self._sub_seq += 1
        sid = "nsub-" + hashlib.md5(
            f"{subscriber}{channel_id}{time.time()}{self._sub_seq}".encode()
        ).hexdigest()[:12]

        self._subscriptions[sid] = _Subscription(
            sub_id=sid,
            subscriber=subscriber,
            channel_id=channel_id,
            filter_severity=filter_severity,
            filter_category=filter_category,
            created_at=time.time(),
            seq=self._sub_seq,
        )
        self._stats["total_subscriptions"] += 1
        return sid

    def unsubscribe(self, sub_id: str) -> bool:
        if sub_id not in self._subscriptions:
            return False
        del self._subscriptions[sub_id]
        return True

    def pause_subscription(self, sub_id: str) -> bool:
        s = self._subscriptions.get(sub_id)
        if not s or s.status == "paused":
            return False
        s.status = "paused"
        return True

    def resume_subscription(self, sub_id: str) -> bool:
        s = self._subscriptions.get(sub_id)
        if not s or s.status == "active":
            return False
        s.status = "active"
        return True

    # ------------------------------------------------------------------
    # Sending Notifications
    # ------------------------------------------------------------------

    def send(self, title: str, message: str = "",
             severity: str = "info", category: str = "",
             source: str = "",
             metadata: Optional[Dict] = None) -> str:
        """Send a notification, routing to matching channels."""
        if not title:
            return ""
        if severity not in self.SEVERITIES:
            return ""
        if len(self._notifications) >= self._max_notifications:
            return ""

        self._notif_seq += 1
        nid = "notif-" + hashlib.md5(
            f"{title}{time.time()}{self._notif_seq}{len(self._notifications)}".encode()
        ).hexdigest()[:12]

        # Find matching channels through subscriptions
        delivered_channels: Set[str] = set()
        for s in self._subscriptions.values():
            if s.status != "active":
                continue
            ch = self._channels.get(s.channel_id)
            if not ch or ch.status != "active":
                continue
            # Check severity filter
            if s.filter_severity:
                min_sev = self.SEVERITY_ORDER.get(s.filter_severity, 0)
                msg_sev = self.SEVERITY_ORDER.get(severity, 0)
                if msg_sev < min_sev:
                    continue
            # Check category filter
            if s.filter_category and s.filter_category != category:
                continue
            delivered_channels.add(s.channel_id)

        self._notifications[nid] = _Notification(
            notif_id=nid,
            title=title,
            message=message,
            severity=severity,
            category=category,
            source=source,
            metadata=metadata or {},
            deliveries=list(delivered_channels),
            created_at=time.time(),
            seq=self._notif_seq,
        )

        self._stats["total_notifications"] += 1
        self._stats["total_deliveries"] += len(delivered_channels)
        self._fire("notification_sent", {
            "notif_id": nid, "channels": len(delivered_channels),
        })
        return nid

    def get_notification(self, notif_id: str) -> Optional[Dict]:
        n = self._notifications.get(notif_id)
        if not n:
            return None
        return {
            "notif_id": n.notif_id,
            "title": n.title,
            "message": n.message,
            "severity": n.severity,
            "category": n.category,
            "source": n.source,
            "deliveries": list(n.deliveries),
            "seq": n.seq,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search_notifications(self, severity: Optional[str] = None,
                             category: Optional[str] = None,
                             source: Optional[str] = None,
                             limit: int = 100) -> List[Dict]:
        result = []
        for n in self._notifications.values():
            if severity and n.severity != severity:
                continue
            if category and n.category != category:
                continue
            if source and n.source != source:
                continue
            result.append({
                "notif_id": n.notif_id,
                "title": n.title,
                "severity": n.severity,
                "category": n.category,
                "deliveries_count": len(n.deliveries),
                "seq": n.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

    def get_subscriber_channels(self, subscriber: str) -> List[Dict]:
        result = []
        for s in self._subscriptions.values():
            if s.subscriber != subscriber or s.status != "active":
                continue
            ch = self._channels.get(s.channel_id)
            if ch:
                result.append({
                    "sub_id": s.sub_id,
                    "channel_id": s.channel_id,
                    "channel_name": ch.name,
                    "filter_severity": s.filter_severity,
                })
        return result

    def list_channels(self, status: Optional[str] = None,
                      channel_type: Optional[str] = None,
                      limit: int = 100) -> List[Dict]:
        result = []
        for c in self._channels.values():
            if status and c.status != status:
                continue
            if channel_type and c.channel_type != channel_type:
                continue
            result.append({
                "channel_id": c.channel_id,
                "name": c.name,
                "channel_type": c.channel_type,
                "status": c.status,
                "seq": c.seq,
            })
        result.sort(key=lambda x: -x["seq"])
        return result[:limit]

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
            "current_channels": len(self._channels),
            "current_subscriptions": len(self._subscriptions),
            "current_notifications": len(self._notifications),
        }

    def reset(self) -> None:
        self._channels.clear()
        self._subscriptions.clear()
        self._notifications.clear()
        self._channel_seq = 0
        self._sub_seq = 0
        self._notif_seq = 0
        self._stats = {k: 0 for k in self._stats}
