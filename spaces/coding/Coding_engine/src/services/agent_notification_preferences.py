"""Agent Notification Preferences -- manages agent notification channel preferences.

Provides subscription-based notification preference management for agents,
tracking which channels and notification types each agent wants to receive,
with quiet hours support, max-entries pruning, callbacks, and thread-safe access.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionRecord:
    sub_id: str
    agent_id: str
    channel: str
    notification_type: str
    metadata: Optional[Dict[str, Any]]
    created_at: float
    seq: int


@dataclass
class QuietHoursRecord:
    agent_id: str
    start_hour: int
    end_hour: int


class AgentNotificationPreferences:
    """Manages agent notification channel preferences (subscriptions, quiet hours)."""

    def __init__(self, max_entries: int = 10000) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[str, SubscriptionRecord] = {}
        self._lookup: Dict[str, str] = {}  # "agent_id:channel:type" -> sub_id
        self._quiet_hours: Dict[str, QuietHoursRecord] = {}  # agent_id -> record
        self._callbacks: Dict[str, Callable] = {}
        self._seq = 0

        # stats
        self._total_subscribes = 0
        self._total_unsubscribes = 0
        self._total_queries = 0
        self._total_clears = 0
        self._total_evictions = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _gen_id(self, seed: str) -> str:
        self._seq += 1
        raw = f"anp-{seed}-{self._seq}-{time.time()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"anp-{digest}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, callback: Callable) -> bool:
        """Register a change callback. Returns False if name already registered."""
        with self._lock:
            if name in self._callbacks:
                return False
            self._callbacks[name] = callback
            return True

    def remove_callback(self, name: str) -> bool:
        """Remove a change callback by name. Returns False if not found."""
        with self._lock:
            if name not in self._callbacks:
                return False
            del self._callbacks[name]
            return True

    def _fire(self, action: str, detail: Dict[str, Any]) -> None:
        """Invoke all registered callbacks with the given action and detail."""
        with self._lock:
            callbacks = list(self._callbacks.values())
        for cb in callbacks:
            try:
                cb(action, detail)
            except Exception:
                logger.debug("callback_error", exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_lookup_key(agent_id: str, channel: str, notification_type: str) -> str:
        return f"{agent_id}:{channel}:{notification_type}"

    def _prune_if_needed(self) -> None:
        """Prune oldest entries when max_entries is exceeded. Caller must hold lock."""
        if len(self._entries) < self._max_entries:
            return

        sorted_ids = sorted(
            self._entries.keys(),
            key=lambda eid: self._entries[eid].seq,
        )
        to_remove = len(self._entries) - self._max_entries + 1
        for eid in sorted_ids[:to_remove]:
            entry = self._entries[eid]
            lk = self._make_lookup_key(entry.agent_id, entry.channel, entry.notification_type)
            self._lookup.pop(lk, None)
            del self._entries[eid]
            self._total_evictions += 1
            logger.debug("subscription_evicted sub_id=%s agent_id=%s", eid, entry.agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def subscribe(
        self,
        agent_id: str,
        channel: str,
        notification_type: str = "all",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Subscribe an agent to a notification channel. Returns sub_id or '' if duplicate."""
        if not agent_id or not channel:
            logger.warning(
                "subscribe_invalid_args agent_id=%s channel=%s",
                agent_id, channel,
            )
            return ""

        lk = self._make_lookup_key(agent_id, channel, notification_type)
        now = time.time()

        with self._lock:
            existing_eid = self._lookup.get(lk)
            if existing_eid and existing_eid in self._entries:
                logger.debug(
                    "subscribe_duplicate agent_id=%s channel=%s type=%s",
                    agent_id, channel, notification_type,
                )
                return ""

            self._prune_if_needed()
            sub_id = self._gen_id(f"{agent_id}-{channel}-{notification_type}")
            entry = SubscriptionRecord(
                sub_id=sub_id,
                agent_id=agent_id,
                channel=channel,
                notification_type=notification_type,
                metadata=metadata,
                created_at=now,
                seq=self._seq,
            )
            self._entries[sub_id] = entry
            self._lookup[lk] = sub_id
            self._total_subscribes += 1

        logger.debug(
            "subscribed agent_id=%s channel=%s type=%s sub_id=%s",
            agent_id, channel, notification_type, sub_id,
        )
        self._fire("subscribed", {
            "sub_id": sub_id,
            "agent_id": agent_id,
            "channel": channel,
            "notification_type": notification_type,
            "metadata": metadata,
        })
        return sub_id

    def unsubscribe(
        self,
        agent_id: str,
        channel: str,
        notification_type: str = "all",
    ) -> bool:
        """Unsubscribe an agent from a channel. Returns False if not found."""
        if not agent_id or not channel:
            return False

        lk = self._make_lookup_key(agent_id, channel, notification_type)

        with self._lock:
            eid = self._lookup.get(lk)
            if not eid or eid not in self._entries:
                return False

            entry = self._entries[eid]
            detail = asdict(entry)
            del self._entries[eid]
            del self._lookup[lk]
            self._total_unsubscribes += 1

        logger.debug(
            "unsubscribed agent_id=%s channel=%s type=%s",
            agent_id, channel, notification_type,
        )
        self._fire("unsubscribed", detail)
        return True

    def get_subscriptions(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all subscriptions for an agent."""
        if not agent_id:
            return []

        with self._lock:
            self._total_queries += 1
            results: List[Dict[str, Any]] = []
            for entry in self._entries.values():
                if entry.agent_id == agent_id:
                    results.append(asdict(entry))
        return results

    def get_subscribers(
        self,
        channel: str,
        notification_type: Optional[str] = None,
    ) -> List[str]:
        """Get all agent_ids subscribed to a channel, optionally filtered by type."""
        if not channel:
            return []

        with self._lock:
            self._total_queries += 1
            agents: List[str] = []
            for entry in self._entries.values():
                if entry.channel != channel:
                    continue
                if notification_type is not None and entry.notification_type != notification_type:
                    continue
                if entry.agent_id not in agents:
                    agents.append(entry.agent_id)
        return agents

    def is_subscribed(
        self,
        agent_id: str,
        channel: str,
        notification_type: str = "all",
    ) -> bool:
        """Check if an agent is subscribed to a channel with a given type."""
        if not agent_id or not channel:
            return False

        lk = self._make_lookup_key(agent_id, channel, notification_type)
        with self._lock:
            self._total_queries += 1
            eid = self._lookup.get(lk)
            return bool(eid and eid in self._entries)

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def set_quiet_hours(self, agent_id: str, start_hour: int, end_hour: int) -> bool:
        """Set quiet hours for an agent (0-23). Always returns True."""
        if not agent_id:
            return False

        start_hour = max(0, min(23, start_hour))
        end_hour = max(0, min(23, end_hour))

        with self._lock:
            self._quiet_hours[agent_id] = QuietHoursRecord(
                agent_id=agent_id,
                start_hour=start_hour,
                end_hour=end_hour,
            )

        logger.debug(
            "quiet_hours_set agent_id=%s start=%d end=%d",
            agent_id, start_hour, end_hour,
        )
        self._fire("quiet_hours_set", {
            "agent_id": agent_id,
            "start_hour": start_hour,
            "end_hour": end_hour,
        })
        return True

    def get_quiet_hours(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get quiet hours for an agent. Returns None if not set."""
        if not agent_id:
            return None

        with self._lock:
            record = self._quiet_hours.get(agent_id)
            if record is None:
                return None
            return {
                "start_hour": record.start_hour,
                "end_hour": record.end_hour,
            }

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def clear_subscriptions(self, agent_id: str) -> int:
        """Clear all subscriptions for an agent. Returns count deleted."""
        if not agent_id:
            return 0

        with self._lock:
            to_delete: List[str] = []
            for eid, entry in self._entries.items():
                if entry.agent_id == agent_id:
                    to_delete.append(eid)

            for eid in to_delete:
                entry = self._entries[eid]
                lk = self._make_lookup_key(entry.agent_id, entry.channel, entry.notification_type)
                self._lookup.pop(lk, None)
                del self._entries[eid]
            self._total_clears += len(to_delete)

        if to_delete:
            logger.debug(
                "subscriptions_cleared agent_id=%s count=%d",
                agent_id, len(to_delete),
            )
            self._fire("subscriptions_cleared", {
                "agent_id": agent_id,
                "count": len(to_delete),
            })
        return len(to_delete)

    def list_channels(self) -> List[str]:
        """List all channels that have at least one subscription."""
        with self._lock:
            channels: set[str] = set()
            for entry in self._entries.values():
                channels.add(entry.channel)
        return sorted(channels)

    # ------------------------------------------------------------------
    # Stats / Reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return service statistics."""
        with self._lock:
            unique_agents = len({e.agent_id for e in self._entries.values()})
            unique_channels = len({e.channel for e in self._entries.values()})
            return {
                "current_subscriptions": len(self._entries),
                "unique_agents": unique_agents,
                "unique_channels": unique_channels,
                "quiet_hours_configured": len(self._quiet_hours),
                "max_entries": self._max_entries,
                "total_subscribes": self._total_subscribes,
                "total_unsubscribes": self._total_unsubscribes,
                "total_queries": self._total_queries,
                "total_clears": self._total_clears,
                "total_evictions": self._total_evictions,
                "callbacks": len(self._callbacks),
            }

    def reset(self) -> None:
        """Clear all state and counters."""
        with self._lock:
            self._entries.clear()
            self._lookup.clear()
            self._quiet_hours.clear()
            self._callbacks.clear()
            self._seq = 0
            self._total_subscribes = 0
            self._total_unsubscribes = 0
            self._total_queries = 0
            self._total_clears = 0
            self._total_evictions = 0
        logger.debug("agent_notification_preferences_reset")
