"""Pipeline Notification Store – manages pipeline notifications with channels.

Provides channel-based notification management with subscriptions,
delivery tracking, severity filtering, and read/unread state per subscriber.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class _Channel:
    channel_id: str
    name: str
    channel_type: str
    tags: List[str]
    created_at: float
    notification_ids: List[str]
    subscriber_ids: List[str]
    seq: int


@dataclass
class _Notification:
    notification_id: str
    channel_name: str
    message: str
    severity: str
    data: Dict[str, Any]
    created_at: float
    seq: int


@dataclass
class _Subscription:
    channel_name: str
    subscriber_id: str
    handler: Optional[Callable]
    created_at: float
    read_notifications: List[str]


class PipelineNotificationStore:
    """Manages notification channels, subscriptions, and delivery tracking."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._channels: Dict[str, _Channel] = {}  # channel_id -> _Channel
        self._channel_names: Dict[str, str] = {}  # name -> channel_id
        self._notifications: Dict[str, _Notification] = {}  # notif_id -> _Notification
        self._subscriptions: Dict[str, _Subscription] = {}  # "chan:sub" -> _Subscription
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_channels_created = 0
        self._total_channels_removed = 0
        self._total_notifications_sent = 0
        self._total_subscriptions = 0
        self._total_unsubscriptions = 0
        self._total_marked_read = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, prefix: str = "pns-") -> str:
        self._seq += 1
        raw = f"{prefix}{self._seq}{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}{digest}_{self._seq}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_notifications(self) -> None:
        if len(self._notifications) <= self._max_entries:
            return
        sorted_ids = sorted(
            self._notifications,
            key=lambda nid: self._notifications[nid].seq,
        )
        to_remove = len(self._notifications) - self._max_entries
        for nid in sorted_ids[:to_remove]:
            notif = self._notifications.pop(nid)
            # remove from channel's notification list
            cid = self._channel_names.get(notif.channel_name)
            if cid and cid in self._channels:
                ch = self._channels[cid]
                if nid in ch.notification_ids:
                    ch.notification_ids.remove(nid)
        logger.debug("pruned_notifications", removed=to_remove)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> None:
        """Register a change callback."""
        if name and callback:
            self._callbacks[name] = callback
            logger.debug("callback_registered", name=name)

    def remove_callback(self, name: str) -> None:
        """Remove a change callback."""
        self._callbacks.pop(name, None)
        logger.debug("callback_removed", name=name)

    def _fire(self, action: str, data: Dict[str, Any]) -> None:
        for cb_name, cb in list(self._callbacks.items()):
            try:
                cb(action, data)
            except Exception:
                logger.warning("callback_error", callback=cb_name, action=action)

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def create_channel(
        self,
        name: str,
        channel_type: str = "default",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a notification channel. Returns channel_id or '' on dup."""
        if not name:
            return ""
        if name in self._channel_names:
            logger.debug("channel_duplicate", name=name)
            return ""

        channel_id = self._next_id("pns-")
        now = time.time()
        channel = _Channel(
            channel_id=channel_id,
            name=name,
            channel_type=channel_type,
            tags=list(tags) if tags else [],
            created_at=now,
            notification_ids=[],
            subscriber_ids=[],
            seq=self._seq,
        )
        self._channels[channel_id] = channel
        self._channel_names[name] = channel_id
        self._total_channels_created += 1

        logger.info("channel_created", channel_id=channel_id, name=name)
        self._fire("channel_created", {"channel_id": channel_id, "name": name})
        return channel_id

    def remove_channel(self, channel_name: str) -> bool:
        """Remove a channel and its notifications. Returns True on success."""
        cid = self._channel_names.get(channel_name)
        if not cid:
            return False

        channel = self._channels.pop(cid, None)
        if not channel:
            return False

        del self._channel_names[channel_name]

        # remove all notifications in this channel
        for nid in list(channel.notification_ids):
            self._notifications.pop(nid, None)

        # remove subscriptions
        keys_to_remove = [
            k for k, s in self._subscriptions.items()
            if s.channel_name == channel_name
        ]
        for k in keys_to_remove:
            del self._subscriptions[k]

        self._total_channels_removed += 1
        logger.info("channel_removed", name=channel_name)
        self._fire("channel_removed", {"name": channel_name})
        return True

    def list_channels(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all channels, optionally filtered by tag."""
        results: List[Dict[str, Any]] = []
        for channel in self._channels.values():
            if tag and tag not in channel.tags:
                continue
            results.append({
                "channel_id": channel.channel_id,
                "name": channel.name,
                "channel_type": channel.channel_type,
                "tags": list(channel.tags),
                "created_at": channel.created_at,
                "notification_count": len(channel.notification_ids),
                "subscriber_count": len(channel.subscriber_ids),
            })
        return results

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def send(
        self,
        channel_name: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a notification to a channel. Returns notification_id or ''."""
        if not channel_name or not message:
            return ""
        cid = self._channel_names.get(channel_name)
        if not cid:
            logger.debug("send_unknown_channel", channel_name=channel_name)
            return ""

        channel = self._channels[cid]
        notification_id = self._next_id("pns-")
        now = time.time()

        notif = _Notification(
            notification_id=notification_id,
            channel_name=channel_name,
            message=message,
            severity=severity,
            data=dict(data) if data else {},
            created_at=now,
            seq=self._seq,
        )
        self._notifications[notification_id] = notif
        channel.notification_ids.append(notification_id)
        self._total_notifications_sent += 1

        # invoke subscriber handlers
        for sub_key, sub in list(self._subscriptions.items()):
            if sub.channel_name == channel_name and sub.handler:
                try:
                    sub.handler(self._notif_to_dict(notif))
                except Exception:
                    logger.warning(
                        "handler_error",
                        subscriber_id=sub.subscriber_id,
                        notification_id=notification_id,
                    )

        self._prune_notifications()
        logger.info(
            "notification_sent",
            notification_id=notification_id,
            channel=channel_name,
            severity=severity,
        )
        self._fire("notification_sent", {
            "notification_id": notification_id,
            "channel_name": channel_name,
        })
        return notification_id

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """Get a single notification by ID."""
        notif = self._notifications.get(notification_id)
        if not notif:
            return None
        return self._notif_to_dict(notif)

    def get_channel_messages(
        self,
        channel_name: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get recent messages from a channel."""
        cid = self._channel_names.get(channel_name)
        if not cid:
            return []
        channel = self._channels[cid]
        recent_ids = channel.notification_ids[-limit:]
        results: List[Dict[str, Any]] = []
        for nid in recent_ids:
            notif = self._notifications.get(nid)
            if notif:
                results.append(self._notif_to_dict(notif))
        return results

    def _notif_to_dict(self, notif: _Notification) -> Dict[str, Any]:
        return {
            "notification_id": notif.notification_id,
            "channel_name": notif.channel_name,
            "message": notif.message,
            "severity": notif.severity,
            "data": dict(notif.data),
            "created_at": notif.created_at,
        }

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(
        self,
        channel_name: str,
        subscriber_id: str,
        handler: Optional[Callable] = None,
    ) -> bool:
        """Subscribe to a channel. Returns True on success."""
        if not channel_name or not subscriber_id:
            return False
        cid = self._channel_names.get(channel_name)
        if not cid:
            return False

        sub_key = f"{channel_name}:{subscriber_id}"
        if sub_key in self._subscriptions:
            return False

        channel = self._channels[cid]
        now = time.time()
        sub = _Subscription(
            channel_name=channel_name,
            subscriber_id=subscriber_id,
            handler=handler,
            created_at=now,
            read_notifications=[],
        )
        self._subscriptions[sub_key] = sub
        if subscriber_id not in channel.subscriber_ids:
            channel.subscriber_ids.append(subscriber_id)

        self._total_subscriptions += 1
        logger.info(
            "subscribed",
            channel=channel_name,
            subscriber_id=subscriber_id,
        )
        self._fire("subscribed", {
            "channel_name": channel_name,
            "subscriber_id": subscriber_id,
        })
        return True

    def unsubscribe(self, channel_name: str, subscriber_id: str) -> bool:
        """Unsubscribe from a channel. Returns True on success."""
        sub_key = f"{channel_name}:{subscriber_id}"
        sub = self._subscriptions.pop(sub_key, None)
        if not sub:
            return False

        cid = self._channel_names.get(channel_name)
        if cid and cid in self._channels:
            channel = self._channels[cid]
            if subscriber_id in channel.subscriber_ids:
                channel.subscriber_ids.remove(subscriber_id)

        self._total_unsubscriptions += 1
        logger.info(
            "unsubscribed",
            channel=channel_name,
            subscriber_id=subscriber_id,
        )
        self._fire("unsubscribed", {
            "channel_name": channel_name,
            "subscriber_id": subscriber_id,
        })
        return True

    # ------------------------------------------------------------------
    # Read tracking
    # ------------------------------------------------------------------

    def get_unread(self, subscriber_id: str) -> List[Dict[str, Any]]:
        """Get all unread notifications for a subscriber across channels."""
        if not subscriber_id:
            return []

        unread: List[Dict[str, Any]] = []
        for sub_key, sub in self._subscriptions.items():
            if sub.subscriber_id != subscriber_id:
                continue
            cid = self._channel_names.get(sub.channel_name)
            if not cid or cid not in self._channels:
                continue
            channel = self._channels[cid]
            read_set = set(sub.read_notifications)
            for nid in channel.notification_ids:
                if nid not in read_set:
                    notif = self._notifications.get(nid)
                    if notif:
                        unread.append(self._notif_to_dict(notif))
        return unread

    def mark_read(self, subscriber_id: str, notification_id: str) -> bool:
        """Mark a notification as read for a subscriber. Returns True on success."""
        if not subscriber_id or not notification_id:
            return False

        notif = self._notifications.get(notification_id)
        if not notif:
            return False

        sub_key = f"{notif.channel_name}:{subscriber_id}"
        sub = self._subscriptions.get(sub_key)
        if not sub:
            return False

        if notification_id not in sub.read_notifications:
            sub.read_notifications.append(notification_id)

        self._total_marked_read += 1
        logger.debug(
            "marked_read",
            subscriber_id=subscriber_id,
            notification_id=notification_id,
        )
        self._fire("marked_read", {
            "subscriber_id": subscriber_id,
            "notification_id": notification_id,
        })
        return True

    # ------------------------------------------------------------------
    # Stats and reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return current store statistics."""
        return {
            "total_channels": len(self._channels),
            "total_notifications": len(self._notifications),
            "total_subscriptions": len(self._subscriptions),
            "total_channels_created": self._total_channels_created,
            "total_channels_removed": self._total_channels_removed,
            "total_notifications_sent": self._total_notifications_sent,
            "total_subscriptions_added": self._total_subscriptions,
            "total_unsubscriptions": self._total_unsubscriptions,
            "total_marked_read": self._total_marked_read,
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Reset all internal state."""
        self._channels.clear()
        self._channel_names.clear()
        self._notifications.clear()
        self._subscriptions.clear()
        self._callbacks.clear()
        self._seq = 0

        self._total_channels_created = 0
        self._total_channels_removed = 0
        self._total_notifications_sent = 0
        self._total_subscriptions = 0
        self._total_unsubscriptions = 0
        self._total_marked_read = 0

        logger.info("store_reset")
