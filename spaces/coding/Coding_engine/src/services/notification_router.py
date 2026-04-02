"""
Notification/Alert Routing Service — routes alerts and notifications
to appropriate channels based on rules, severity, and subscriptions.

Features:
- Channel definitions (slack, whatsapp, email, webhook, log)
- Subscription rules: who gets what based on severity/source/tags
- Rate limiting per channel to prevent spam
- Notification history and deduplication
- Escalation chains (notify A, wait, escalate to B)
- Bulk notification support
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & data structures
# ---------------------------------------------------------------------------

class Severity(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class DeliveryStatus(str):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"
    DEDUPLICATED = "deduplicated"


@dataclass
class Channel:
    """A notification delivery channel."""
    name: str
    channel_type: str  # "slack", "whatsapp", "email", "webhook", "log", "custom"
    handler: Optional[Callable] = None  # (notification_dict) -> bool
    enabled: bool = True
    rate_limit: float = 0.0  # min seconds between notifications, 0 = no limit
    last_sent: float = 0.0
    sent_count: int = 0
    failed_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Subscription:
    """A subscription rule linking sources/severities to channels."""
    sub_id: str
    channel_name: str
    min_severity: Severity = Severity.INFO
    sources: Set[str] = field(default_factory=set)  # empty = all sources
    tags: Set[str] = field(default_factory=set)  # empty = all tags
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    """A notification record."""
    notif_id: str
    title: str
    message: str
    severity: Severity
    source: str
    tags: Set[str]
    data: Dict[str, Any]
    created_at: float
    deliveries: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class NotificationRouter:
    """Routes notifications to channels based on subscriptions."""

    def __init__(
        self,
        max_history: int = 1000,
        dedup_window: float = 60.0,
    ):
        self._max_history = max_history
        self._dedup_window = dedup_window

        # Channels: name → Channel
        self._channels: Dict[str, Channel] = {}

        # Subscriptions: sub_id → Subscription
        self._subscriptions: Dict[str, Subscription] = {}

        # Notification history
        self._history: List[Notification] = []

        # Dedup tracking: dedup_key → last_sent_time
        self._dedup_cache: Dict[str, float] = {}

        # Escalation chains: chain_name → [(channel, delay_seconds), ...]
        self._escalation_chains: Dict[str, List[tuple]] = {}

        # Stats
        self._stats = {
            "total_sent": 0,
            "total_failed": 0,
            "total_suppressed": 0,
            "total_deduplicated": 0,
            "total_notifications": 0,
        }

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def add_channel(
        self,
        name: str,
        channel_type: str = "log",
        handler: Optional[Callable] = None,
        rate_limit: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Add a notification channel. Returns False if name exists."""
        if name in self._channels:
            return False
        self._channels[name] = Channel(
            name=name,
            channel_type=channel_type,
            handler=handler,
            rate_limit=rate_limit,
            metadata=metadata or {},
        )
        return True

    def remove_channel(self, name: str) -> bool:
        """Remove a channel."""
        if name not in self._channels:
            return False
        del self._channels[name]
        # Remove subscriptions for this channel
        to_remove = [sid for sid, s in self._subscriptions.items()
                     if s.channel_name == name]
        for sid in to_remove:
            del self._subscriptions[sid]
        return True

    def enable_channel(self, name: str) -> bool:
        if name not in self._channels:
            return False
        self._channels[name].enabled = True
        return True

    def disable_channel(self, name: str) -> bool:
        if name not in self._channels:
            return False
        self._channels[name].enabled = False
        return True

    def get_channel(self, name: str) -> Optional[Dict]:
        if name not in self._channels:
            return None
        c = self._channels[name]
        return {
            "name": c.name,
            "channel_type": c.channel_type,
            "enabled": c.enabled,
            "rate_limit": c.rate_limit,
            "sent_count": c.sent_count,
            "failed_count": c.failed_count,
            "metadata": c.metadata,
        }

    def list_channels(self) -> List[Dict]:
        return [self.get_channel(n) for n in sorted(self._channels)]

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(
        self,
        channel_name: str,
        min_severity: str = "info",
        sources: Optional[Set[str]] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """Create a subscription. Returns sub_id or None if channel doesn't exist."""
        if channel_name not in self._channels:
            return None

        sid = f"sub-{uuid.uuid4().hex[:8]}"
        sev_map = {"debug": Severity.DEBUG, "info": Severity.INFO,
                    "warning": Severity.WARNING, "error": Severity.ERROR,
                    "critical": Severity.CRITICAL}
        sev = sev_map.get(min_severity, Severity.INFO)

        self._subscriptions[sid] = Subscription(
            sub_id=sid,
            channel_name=channel_name,
            min_severity=sev,
            sources=sources or set(),
            tags=tags or set(),
            metadata=metadata or {},
        )
        return sid

    def unsubscribe(self, sub_id: str) -> bool:
        if sub_id not in self._subscriptions:
            return False
        del self._subscriptions[sub_id]
        return True

    def get_subscription(self, sub_id: str) -> Optional[Dict]:
        s = self._subscriptions.get(sub_id)
        if not s:
            return None
        return {
            "sub_id": s.sub_id,
            "channel_name": s.channel_name,
            "min_severity": s.min_severity.name.lower(),
            "sources": sorted(s.sources),
            "tags": sorted(s.tags),
            "enabled": s.enabled,
            "metadata": s.metadata,
        }

    def list_subscriptions(self, channel_name: Optional[str] = None) -> List[Dict]:
        results = []
        for s in self._subscriptions.values():
            if channel_name and s.channel_name != channel_name:
                continue
            results.append(self.get_subscription(s.sub_id))
        return results

    # ------------------------------------------------------------------
    # Escalation chains
    # ------------------------------------------------------------------

    def define_escalation(self, chain_name: str, steps: List[tuple]) -> None:
        """Define an escalation chain: [(channel_name, delay_seconds), ...]"""
        self._escalation_chains[chain_name] = steps

    def get_escalation(self, chain_name: str) -> Optional[List[tuple]]:
        return self._escalation_chains.get(chain_name)

    def list_escalation_chains(self) -> List[str]:
        return sorted(self._escalation_chains.keys())

    # ------------------------------------------------------------------
    # Notification sending
    # ------------------------------------------------------------------

    def notify(
        self,
        title: str,
        message: str,
        severity: str = "info",
        source: str = "",
        tags: Optional[Set[str]] = None,
        data: Optional[Dict] = None,
        dedup_key: Optional[str] = None,
    ) -> str:
        """
        Send a notification. Routes to all matching subscriptions.
        Returns notification ID.
        """
        sev_map = {"debug": Severity.DEBUG, "info": Severity.INFO,
                    "warning": Severity.WARNING, "error": Severity.ERROR,
                    "critical": Severity.CRITICAL}
        sev = sev_map.get(severity, Severity.INFO)
        ntags = tags or set()

        nid = f"notif-{uuid.uuid4().hex[:8]}"
        now = time.time()

        self._stats["total_notifications"] += 1

        # Dedup check
        if dedup_key:
            last = self._dedup_cache.get(dedup_key, 0)
            if (now - last) < self._dedup_window:
                self._stats["total_deduplicated"] += 1
                notif = Notification(
                    notif_id=nid, title=title, message=message,
                    severity=sev, source=source, tags=ntags,
                    data=data or {}, created_at=now,
                    deliveries=[{"status": "deduplicated"}],
                )
                self._history.append(notif)
                self._prune_history()
                return nid
            self._dedup_cache[dedup_key] = now

        notif = Notification(
            notif_id=nid, title=title, message=message,
            severity=sev, source=source, tags=ntags,
            data=data or {}, created_at=now,
        )

        # Find matching subscriptions
        for sub in self._subscriptions.values():
            if not sub.enabled:
                continue
            if sev < sub.min_severity:
                continue
            if sub.sources and source not in sub.sources:
                continue
            if sub.tags and not sub.tags.issubset(ntags):
                continue

            channel = self._channels.get(sub.channel_name)
            if not channel or not channel.enabled:
                continue

            # Rate limit check
            if channel.rate_limit > 0:
                elapsed = now - channel.last_sent
                if elapsed < channel.rate_limit:
                    notif.deliveries.append({
                        "channel": channel.name,
                        "status": "suppressed",
                        "reason": "rate_limited",
                    })
                    self._stats["total_suppressed"] += 1
                    continue

            # Deliver
            delivery = self._deliver(channel, notif)
            notif.deliveries.append(delivery)

        self._history.append(notif)
        self._prune_history()
        return nid

    def _deliver(self, channel: Channel, notif: Notification) -> Dict:
        """Deliver notification to a channel."""
        payload = {
            "notif_id": notif.notif_id,
            "title": notif.title,
            "message": notif.message,
            "severity": notif.severity.name.lower(),
            "source": notif.source,
            "tags": sorted(notif.tags),
            "data": notif.data,
            "timestamp": notif.created_at,
        }

        if channel.handler:
            try:
                result = channel.handler(payload)
                channel.sent_count += 1
                channel.last_sent = time.time()
                self._stats["total_sent"] += 1
                return {
                    "channel": channel.name,
                    "status": "sent",
                    "result": result,
                }
            except Exception as e:
                channel.failed_count += 1
                self._stats["total_failed"] += 1
                return {
                    "channel": channel.name,
                    "status": "failed",
                    "error": str(e),
                }
        else:
            # Default: log-based delivery
            logger.info("notification_delivered",
                        channel=channel.name,
                        title=notif.title,
                        severity=notif.severity.name)
            channel.sent_count += 1
            channel.last_sent = time.time()
            self._stats["total_sent"] += 1
            return {
                "channel": channel.name,
                "status": "sent",
            }

    def notify_escalation(
        self,
        chain_name: str,
        title: str,
        message: str,
        severity: str = "critical",
        source: str = "",
        data: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Send through an escalation chain.
        Returns delivery results for each step.
        NOTE: In real use, delays would be async. Here we record steps immediately.
        """
        chain = self._escalation_chains.get(chain_name)
        if not chain:
            return []

        results = []
        for channel_name, delay_seconds in chain:
            channel = self._channels.get(channel_name)
            if not channel or not channel.enabled:
                results.append({
                    "channel": channel_name,
                    "status": "skipped",
                    "delay": delay_seconds,
                })
                continue

            sev_map = {"debug": Severity.DEBUG, "info": Severity.INFO,
                        "warning": Severity.WARNING, "error": Severity.ERROR,
                        "critical": Severity.CRITICAL}
            sev = sev_map.get(severity, Severity.CRITICAL)

            notif = Notification(
                notif_id=f"notif-{uuid.uuid4().hex[:8]}",
                title=title, message=message,
                severity=sev, source=source, tags=set(),
                data=data or {}, created_at=time.time(),
            )

            delivery = self._deliver(channel, notif)
            delivery["delay"] = delay_seconds
            delivery["escalation_chain"] = chain_name
            results.append(delivery)

            notif.deliveries.append(delivery)
            self._history.append(notif)

        self._prune_history()
        return results

    # ------------------------------------------------------------------
    # History & queries
    # ------------------------------------------------------------------

    def get_history(
        self,
        source: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get notification history."""
        sev_map = {"debug": Severity.DEBUG, "info": Severity.INFO,
                    "warning": Severity.WARNING, "error": Severity.ERROR,
                    "critical": Severity.CRITICAL}
        min_sev = sev_map.get(severity, Severity.DEBUG) if severity else Severity.DEBUG

        results = []
        for n in reversed(self._history):
            if source and n.source != source:
                continue
            if n.severity < min_sev:
                continue
            results.append({
                "notif_id": n.notif_id,
                "title": n.title,
                "message": n.message,
                "severity": n.severity.name.lower(),
                "source": n.source,
                "tags": sorted(n.tags),
                "created_at": n.created_at,
                "deliveries": n.deliveries,
            })
            if len(results) >= limit:
                break
        return results

    def get_notification(self, notif_id: str) -> Optional[Dict]:
        """Get a specific notification."""
        for n in self._history:
            if n.notif_id == notif_id:
                return {
                    "notif_id": n.notif_id,
                    "title": n.title,
                    "message": n.message,
                    "severity": n.severity.name.lower(),
                    "source": n.source,
                    "tags": sorted(n.tags),
                    "data": n.data,
                    "created_at": n.created_at,
                    "deliveries": n.deliveries,
                }
        return None

    def _prune_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    # ------------------------------------------------------------------
    # Stats & reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "total_channels": len(self._channels),
            "enabled_channels": sum(1 for c in self._channels.values() if c.enabled),
            "total_subscriptions": len(self._subscriptions),
            "escalation_chains": len(self._escalation_chains),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        self._channels.clear()
        self._subscriptions.clear()
        self._history.clear()
        self._dedup_cache.clear()
        self._escalation_chains.clear()
        self._stats = {k: 0 for k in self._stats}
