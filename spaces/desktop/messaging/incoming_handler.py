"""
Incoming Message Handler — Clawdbot Webhook → Ollama → Rowboat → Voice

When a message arrives via WhatsApp/Telegram:
  1. Ollama: Check relevance (is this worth interrupting the user?)
  2. If relevant:
     a. Rowboat: Store in Knowledge Graph via process_voice_note()
     b. Voice: inject_system_message() so Rachel tells the user
  3. If not relevant:
     → Log only, no voice interrupt

This handler is registered with ClawdbotBridgeService and called
whenever a message arrives from the Clawdbot Gateway webhook.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from .relevance_filter import RelevanceFilter
from .messaging_pipeline import log_incoming_message

logger = logging.getLogger(__name__)


class IncomingMessageHandler:
    """
    Processes incoming Clawdbot messages.

    Wired into ClawdbotBridgeService.process_message() as a hook
    and also callable from the /api/clawdbot/webhook endpoint directly.
    """

    def __init__(
        self,
        relevance_filter: Optional[RelevanceFilter] = None,
        rowboat_client=None,
        voice_session_getter: Optional[Callable] = None,
    ):
        """
        Args:
            relevance_filter: RelevanceFilter instance (creates one if None)
            rowboat_client: RoarbootClient instance (lazy-loads if None)
            voice_session_getter: Callable that returns the current
                OpenAIRealtimeVoiceSession (or None if not connected).
                Uses a getter because the session can be created/destroyed.
        """
        self._relevance_filter = relevance_filter or RelevanceFilter()
        self._rowboat_client = rowboat_client
        self._voice_session_getter = voice_session_getter
        self._recent_context: str = ""  # Updated by send pipeline

        logger.info("IncomingMessageHandler initialized")

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def update_context(self, context: str):
        """Update conversation context (called after outgoing messages)."""
        self._recent_context = context

    # ------------------------------------------------------------------
    # Core handler
    # ------------------------------------------------------------------

    async def on_message(
        self,
        user_id: str,
        platform: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process an incoming message from Clawdbot.

        Called by ClawdbotBridgeService when a webhook message arrives.

        Args:
            user_id: Sender user ID (phone number, username, etc.)
            platform: whatsapp, telegram, discord, etc.
            text: Message text
            metadata: Optional extra data (message_id, attachments, etc.)

        Returns:
            {"handled": bool, "relevant": bool, "score": float, "action": str}
        """
        if not text or not text.strip():
            return {"handled": False, "relevant": False, "score": 0, "action": "empty"}

        sender_name = self._resolve_sender_name(user_id, platform)
        logger.info(f"Incoming message: [{sender_name}@{platform}] {text[:80]}")

        # Always log the message
        log_incoming_message(sender=sender_name, platform=platform, text=text)

        # 1. Check relevance via Ollama
        relevance = await self._relevance_filter.check(
            message=text,
            sender=sender_name,
            platform=platform,
            context=self._recent_context,
        )

        score = relevance.get("score", 0.5)
        is_relevant = relevance.get("relevant", False)
        reason = relevance.get("reason", "")

        if not is_relevant:
            logger.info(
                f"Message NOT relevant (score={score:.2f}): {reason} — logging only"
            )
            return {
                "handled": True,
                "relevant": False,
                "score": score,
                "action": "logged",
                "reason": reason,
            }

        # 2. Relevant! Store in Rowboat Knowledge Graph
        rowboat_stored = False
        try:
            rowboat = self._get_rowboat()
            if rowboat:
                note = f"{sender_name} ({platform}): {text}"
                result = rowboat.process_voice_note(note)
                rowboat_stored = result.get("success", False)
                if rowboat_stored:
                    logger.info(f"Stored in Rowboat: {sender_name} message")
                else:
                    logger.warning(f"Rowboat store failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Rowboat storage error: {e}")

        # 3. Notify voice session via inject_system_message
        voice_notified = False
        try:
            voice_notified = await self._notify_voice(sender_name, platform, text)
        except Exception as e:
            logger.error(f"Voice notification error: {e}")

        action = "notified" if voice_notified else "stored"
        logger.info(
            f"Message RELEVANT (score={score:.2f}): "
            f"rowboat={rowboat_stored}, voice={voice_notified}"
        )

        return {
            "handled": True,
            "relevant": True,
            "score": score,
            "action": action,
            "reason": reason,
            "rowboat_stored": rowboat_stored,
            "voice_notified": voice_notified,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_rowboat(self):
        """Lazy-load Rowboat client."""
        if self._rowboat_client is None:
            try:
                from spaces.rowboat.tools.roarboot_client import get_roarboot_client
                self._rowboat_client = get_roarboot_client()
            except ImportError:
                logger.warning("IncomingHandler: Rowboat client not available")
        return self._rowboat_client

    async def _notify_voice(self, sender: str, platform: str, text: str) -> bool:
        """Inject a system message into the voice session so Rachel speaks it."""
        if not self._voice_session_getter:
            logger.debug("No voice session getter — cannot notify")
            return False

        session = self._voice_session_getter()
        if session is None:
            logger.debug("No active voice session — cannot notify")
            return False

        # Build a concise notification
        # Limit message length to avoid overwhelming the voice
        short_text = text[:200] + ("..." if len(text) > 200 else "")
        notification = (
            f"Du hast eine neue Nachricht von {sender} auf {platform}: "
            f"\"{short_text}\""
        )

        try:
            await session.inject_system_message(notification)
            logger.info(f"Voice notified about message from {sender}")
            return True
        except Exception as e:
            logger.error(f"inject_system_message failed: {e}")
            return False

    def _resolve_sender_name(self, user_id: str, platform: str) -> str:
        """Try to resolve a user_id to a human-readable name via ContactRegistry."""
        try:
            from spaces.desktop.Automation_ui.backend.app.services.contact_registry import (
                get_contact_registry,
            )
            registry = get_contact_registry()

            # Search contacts by phone/telegram/discord ID
            for key, contact in registry.list_contacts().items():
                for field in ["whatsapp", "telegram", "discord", "signal", "email"]:
                    if contact.get(field) == user_id:
                        return contact.get("name", key)

            # Not found — return user_id as-is
            return user_id

        except ImportError:
            return user_id
        except Exception:
            return user_id


# Global singleton
_handler: Optional[IncomingMessageHandler] = None


def get_incoming_handler() -> Optional[IncomingMessageHandler]:
    """Get the global IncomingMessageHandler (None if not initialized)."""
    return _handler


def set_incoming_handler(handler: IncomingMessageHandler):
    """Set the global IncomingMessageHandler (called during startup)."""
    global _handler
    _handler = handler
    logger.info("IncomingMessageHandler registered globally")
