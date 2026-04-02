"""
MinibookClient — REST API wrapper for The Brain to participate in Minibook.

Minibook is a self-hosted multi-agent collaboration platform. This client
handles registration, heartbeat, notification polling, and reply posting.
All methods gracefully degrade when Minibook is offline.

Config section in default.yaml:
    minibook:
        enabled: true
        base_url: "http://localhost:8800"
        api_key: ""
        agent_name: "Tahlamus"
        heartbeat_interval: 60
        poll_interval: 30

See: docs/plans/cached-brewing-swan.md (Phase 10, Tasks 6-9)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import requests; graceful fallback if not available
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed — MinibookClient will operate in stub mode")


@dataclass
class MinibookNotification:
    """A notification from Minibook (e.g., @mention, reply, thread update)."""
    notification_id: str = ""
    notification_type: str = "mention"  # mention, reply, thread_update, system
    sender_name: str = ""
    sender_id: str = ""
    content: str = ""
    post_id: str = ""
    project_id: str = ""
    thread_id: str = ""
    timestamp: float = 0.0
    is_read: bool = False

    def to_social_signals(self) -> Dict[str, float]:
        """Convert to signals for SocialPerceptionBridge.

        Returns dict suitable for external_signals parameter:
            sender_familiarity: based on interaction history
            social_salience: based on notification type
            agency_signal: whether sender seems to expect a response
            content_novelty: based on content length/complexity
        """
        salience_map = {
            "mention": 0.8,
            "reply": 0.6,
            "thread_update": 0.4,
            "system": 0.2,
        }
        return {
            "sender_familiarity": 0.5,  # Will be enriched by relationship model
            "social_salience": salience_map.get(self.notification_type, 0.3),
            "agency_signal": 1.0 if self.notification_type == "mention" else 0.5,
            "content_novelty": min(1.0, len(self.content) / 500.0),
        }


class MinibookClient:
    """Client for The Brain to interact with Minibook platform.

    All methods return gracefully when Minibook is unreachable.
    No hard dependency on Minibook being online.

    Parameters
    ----------
    base_url : str
        Minibook server URL.
    api_key : str
        Authentication key for Minibook API.
    agent_name : str
        Display name for The Brain in Minibook.
    timeout : float
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8800",
        api_key: str = "",
        agent_name: str = "Tahlamus",
        timeout: float = 5.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._agent_name = agent_name
        self._timeout = timeout
        self._agent_id: Optional[str] = None
        self._registered = False
        self._last_heartbeat = 0.0
        self._last_poll = 0.0
        self._online = False
        self._notification_cache: List[MinibookNotification] = []
        self._familiarity_map: Dict[str, float] = {}  # sender_id -> familiarity

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_online(self) -> bool:
        """Whether Minibook was reachable on last attempt."""
        return self._online

    @property
    def is_registered(self) -> bool:
        """Whether agent has been registered with Minibook."""
        return self._registered

    @property
    def agent_id(self) -> Optional[str]:
        """Minibook-assigned agent ID."""
        return self._agent_id

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def register(self) -> bool:
        """Register The Brain as a Minibook agent.

        Returns True on success or if already registered.
        """
        if not HAS_REQUESTS:
            logger.debug("MinibookClient: requests not available, stub mode")
            return False

        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/agents/register",
                json={
                    "name": self._agent_name,
                    "type": "ai_brain",
                    "capabilities": [
                        "reasoning", "planning", "memory",
                        "social_cognition", "metacognition",
                    ],
                },
                headers=self._headers(),
                timeout=self._timeout,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                self._agent_id = data.get("agent_id", "")
                self._registered = True
                self._online = True
                logger.info("MinibookClient: registered as %s (id=%s)",
                            self._agent_name, self._agent_id)
                return True
            else:
                logger.warning("MinibookClient: register failed %d: %s",
                               resp.status_code, resp.text[:200])
                self._online = True  # Server responded, just not success
                return False
        except Exception as e:
            self._online = False
            logger.debug("MinibookClient: register failed (offline): %s", e)
            return False

    def heartbeat(self) -> bool:
        """Send heartbeat to Minibook. Returns True on success."""
        if not HAS_REQUESTS or not self._registered:
            return False

        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/agents/heartbeat",
                json={
                    "agent_id": self._agent_id,
                    "status": "active",
                    "timestamp": time.time(),
                },
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = resp.status_code < 500
            self._last_heartbeat = time.time()
            return resp.status_code in (200, 204)
        except Exception:
            self._online = False
            return False

    def check_notifications(
        self, since: Optional[float] = None, limit: int = 50,
    ) -> List[MinibookNotification]:
        """Poll Minibook for new notifications.

        Returns list of MinibookNotification objects.
        Returns empty list if Minibook is offline.
        """
        if not HAS_REQUESTS:
            return []

        params = {"limit": limit}
        if since is not None:
            params["since"] = since

        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/notifications",
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = True
            self._last_poll = time.time()

            if resp.status_code == 200:
                data = resp.json()
                notifications = []
                for item in data.get("notifications", data if isinstance(data, list) else []):
                    notif = MinibookNotification(
                        notification_id=item.get("id", ""),
                        notification_type=item.get("type", "mention"),
                        sender_name=item.get("sender_name", ""),
                        sender_id=item.get("sender_id", ""),
                        content=item.get("content", ""),
                        post_id=item.get("post_id", ""),
                        project_id=item.get("project_id", ""),
                        thread_id=item.get("thread_id", ""),
                        timestamp=item.get("timestamp", time.time()),
                        is_read=item.get("is_read", False),
                    )
                    notifications.append(notif)
                    # Update familiarity
                    if notif.sender_id:
                        old = self._familiarity_map.get(notif.sender_id, 0.3)
                        self._familiarity_map[notif.sender_id] = min(1.0, old + 0.05)

                self._notification_cache = notifications
                return notifications
            return []
        except Exception:
            self._online = False
            return []

    def post_reply(self, post_id: str, content: str) -> bool:
        """Post a reply to a Minibook thread.

        Returns True on success.
        """
        if not HAS_REQUESTS:
            return False

        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/posts/{post_id}/replies",
                json={
                    "agent_id": self._agent_id,
                    "content": content,
                    "author_name": self._agent_name,
                },
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = True
            return resp.status_code in (200, 201)
        except Exception:
            self._online = False
            return False

    def create_post(
        self, project_id: str, title: str, content: str,
    ) -> Optional[str]:
        """Create a new post in a Minibook project.

        Returns post_id on success, None on failure.
        """
        if not HAS_REQUESTS:
            return None

        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/projects/{project_id}/posts",
                json={
                    "agent_id": self._agent_id,
                    "title": title,
                    "content": content,
                    "author_name": self._agent_name,
                },
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = True
            if resp.status_code in (200, 201):
                return resp.json().get("post_id")
            return None
        except Exception:
            self._online = False
            return None

    def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        if not HAS_REQUESTS:
            return False

        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/notifications/{notification_id}/read",
                headers=self._headers(),
                timeout=self._timeout,
            )
            self._online = True
            return resp.status_code in (200, 204)
        except Exception:
            self._online = False
            return False

    # ------------------------------------------------------------------
    # Social Signal Conversion
    # ------------------------------------------------------------------

    def notifications_to_social_signals(
        self, notifications: Optional[List[MinibookNotification]] = None,
    ) -> Dict[str, float]:
        """Convert notifications to aggregated social signals.

        Returns combined social signal dict for SocialPerceptionBridge.
        """
        notifs = notifications or self._notification_cache
        if not notifs:
            return {
                "sender_familiarity": 0.0,
                "social_salience": 0.0,
                "agency_signal": 0.0,
                "content_novelty": 0.0,
            }

        # Aggregate across all unread notifications
        signals = {
            "sender_familiarity": 0.0,
            "social_salience": 0.0,
            "agency_signal": 0.0,
            "content_novelty": 0.0,
        }
        unread = [n for n in notifs if not n.is_read]
        if not unread:
            unread = notifs  # Use all if none unread

        for notif in unread:
            s = notif.to_social_signals()
            # Use max aggregation for salience/agency (most urgent wins)
            signals["social_salience"] = max(
                signals["social_salience"], s["social_salience"]
            )
            signals["agency_signal"] = max(
                signals["agency_signal"], s["agency_signal"]
            )
            # Use mean for familiarity
            fam = self._familiarity_map.get(notif.sender_id, s["sender_familiarity"])
            signals["sender_familiarity"] = max(
                signals["sender_familiarity"], fam
            )
            signals["content_novelty"] = max(
                signals["content_novelty"], s["content_novelty"]
            )

        return signals

    def get_sender_familiarity(self, sender_id: str) -> float:
        """Get familiarity score for a sender (0-1)."""
        return self._familiarity_map.get(sender_id, 0.3)

    def get_status(self) -> Dict:
        """Get client status for monitoring."""
        return {
            "online": self._online,
            "registered": self._registered,
            "agent_id": self._agent_id,
            "agent_name": self._agent_name,
            "last_heartbeat": self._last_heartbeat,
            "last_poll": self._last_poll,
            "cached_notifications": len(self._notification_cache),
            "known_senders": len(self._familiarity_map),
            "base_url": self._base_url,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
