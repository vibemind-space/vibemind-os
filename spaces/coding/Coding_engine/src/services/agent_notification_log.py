"""Agent notification log service for tracking notifications sent to/from agents."""

import time
import hashlib
import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class AgentNotificationLogState:
    """State container for the agent notification log."""
    entries: dict = dataclasses.field(default_factory=dict)
    _seq: int = 0


class AgentNotificationLog:
    """Log notifications sent to/from agents with read/unread tracking."""

    MAX_ENTRIES = 10000
    ID_PREFIX = "anl-"

    def __init__(self):
        self._state = AgentNotificationLogState()
        self._callbacks = {}

    def _generate_id(self, data: str) -> str:
        """Generate a unique ID using sha256 hash of data and sequence number."""
        raw = f"{data}{self._state._seq}"
        hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
        self._state._seq += 1
        return f"{self.ID_PREFIX}{hash_val}"

    def _prune(self):
        """Prune entries if exceeding MAX_ENTRIES, removing oldest first."""
        if len(self._state.entries) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._state.entries.keys(),
                key=lambda k: self._state.entries[k].get("created_at", 0)
            )
            to_remove = len(self._state.entries) - self.MAX_ENTRIES
            for key in sorted_keys[:to_remove]:
                del self._state.entries[key]

    def on_change(self, callback_id: str, callback):
        """Register a change callback."""
        self._callbacks[callback_id] = callback

    def remove_callback(self, callback_id: str) -> bool:
        """Remove a registered callback. Returns True if it existed."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            return True
        return False

    def _fire(self, event: str, data: dict):
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(event, data)
            except Exception as e:
                logger.error("Callback error: %s", e)

    def send_notification(self, agent_id: str, title: str, message: str, severity: str = "info") -> str:
        """Send a notification to an agent. Returns the notification ID."""
        nid = self._generate_id(f"{agent_id}{title}{message}")
        entry = {
            "id": nid,
            "agent_id": agent_id,
            "title": title,
            "message": message,
            "severity": severity,
            "read": False,
            "dismissed": False,
            "created_at": time.time(),
        }
        self._state.entries[nid] = entry
        self._prune()
        self._fire("notification_sent", entry)
        logger.info("Notification sent: %s to agent %s", nid, agent_id)
        return nid

    def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read. Returns True if found."""
        entry = self._state.entries.get(notification_id)
        if entry is None:
            return False
        entry["read"] = True
        self._fire("notification_read", entry)
        return True

    def get_notifications(self, agent_id: str, unread_only: bool = False, severity: str = "") -> list:
        """Get notifications for an agent, optionally filtered."""
        results = []
        for entry in self._state.entries.values():
            if entry["agent_id"] != agent_id:
                continue
            if entry.get("dismissed"):
                continue
            if unread_only and entry["read"]:
                continue
            if severity and entry["severity"] != severity:
                continue
            results.append(dict(entry))
        results.sort(key=lambda e: e["created_at"], reverse=True)
        return results

    def get_unread_count(self, agent_id: str) -> int:
        """Get the count of unread notifications for an agent."""
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id and not entry["read"] and not entry.get("dismissed"):
                count += 1
        return count

    def get_notification(self, notification_id: str) -> dict or None:
        """Get a single notification by ID."""
        entry = self._state.entries.get(notification_id)
        if entry is None:
            return None
        return dict(entry)

    def dismiss_notification(self, notification_id: str) -> bool:
        """Dismiss a notification. Returns True if found."""
        entry = self._state.entries.get(notification_id)
        if entry is None:
            return False
        entry["dismissed"] = True
        self._fire("notification_dismissed", entry)
        return True

    def get_notification_count(self, agent_id: str = "") -> int:
        """Get total notification count, optionally filtered by agent."""
        if not agent_id:
            return len(self._state.entries)
        count = 0
        for entry in self._state.entries.values():
            if entry["agent_id"] == agent_id:
                count += 1
        return count

    def list_agents(self) -> list:
        """List all agent IDs that have notifications."""
        agents = set()
        for entry in self._state.entries.values():
            agents.add(entry["agent_id"])
        return sorted(agents)

    def get_stats(self) -> dict:
        """Get statistics about the notification log."""
        total = len(self._state.entries)
        read_count = sum(1 for e in self._state.entries.values() if e["read"])
        unread_count = sum(1 for e in self._state.entries.values() if not e["read"])
        dismissed_count = sum(1 for e in self._state.entries.values() if e.get("dismissed"))
        agents = self.list_agents()
        severity_counts = {}
        for entry in self._state.entries.values():
            sev = entry["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        return {
            "total": total,
            "read": read_count,
            "unread": unread_count,
            "dismissed": dismissed_count,
            "agents": len(agents),
            "severity_counts": severity_counts,
        }

    def reset(self):
        """Reset the notification log to initial state."""
        self._state = AgentNotificationLogState()
        self._callbacks.clear()
        logger.info("Agent notification log reset")
