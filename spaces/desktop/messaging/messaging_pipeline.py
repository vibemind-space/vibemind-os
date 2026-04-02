"""
Messaging Pipeline — Voice → Rowboat → Clawdbot → Voice

Outgoing: User says "Schreib meiner Mutter dass ich spaeter komme"
  1. Rowboat: query_knowledge("Mutter") → context about the contact
  2. ContactRegistry: fuzzy-resolve "Mutter" → phone number
  3. Clawdbot: send_whatsapp(number, message)
  4. Return result → inject_system_message("Nachricht an Mutter gesendet")

Also provides read_messages() for checking recent incoming messages.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory log of recent messages (incoming + outgoing)
_message_log: List[Dict[str, Any]] = []
MAX_LOG_SIZE = 100


class MessagingPipeline:
    """Voice → Rowboat → Clawdbot → Voice messaging pipeline."""

    def __init__(self):
        self._rowboat_client = None
        self._contact_registry = None

    # ------------------------------------------------------------------
    # Lazy-loaded dependencies
    # ------------------------------------------------------------------

    def _get_rowboat(self):
        """Lazy-load RoarbootClient singleton."""
        if self._rowboat_client is None:
            try:
                from spaces.rowboat.tools.roarboot_client import get_roarboot_client
                self._rowboat_client = get_roarboot_client()
            except ImportError:
                logger.warning("MessagingPipeline: Rowboat client not available")
        return self._rowboat_client

    def _get_contacts(self):
        """Lazy-load ContactRegistry singleton."""
        if self._contact_registry is None:
            try:
                from spaces.desktop.Automation_ui.backend.app.services.contact_registry import (
                    get_contact_registry,
                )
                self._contact_registry = get_contact_registry()
            except ImportError:
                logger.warning("MessagingPipeline: ContactRegistry not available")
        return self._contact_registry

    # ------------------------------------------------------------------
    # OUTGOING: Voice → Rowboat → Clawdbot
    # ------------------------------------------------------------------

    async def send_message(
        self,
        recipient: str,
        message: str,
        platform: str = "auto",
    ) -> Dict[str, Any]:
        """
        Send a message through the full pipeline.

        Args:
            recipient: Name or alias ("Mutter", "Peter", "Boss")
            message: The message text
            platform: "whatsapp", "telegram", or "auto" (try whatsapp first)

        Returns:
            {"success": bool, "message": str, "platform": str, ...}
        """
        logger.info(f"MessagingPipeline.send: recipient={recipient}, platform={platform}")

        # 1. Resolve contact
        contacts = self._get_contacts()
        contact = None
        recipient_id = None
        resolved_platform = platform

        if contacts:
            contact = contacts.resolve(recipient)
            if contact:
                # Determine platform
                if platform == "auto":
                    for p in ["whatsapp", "telegram", "discord", "signal"]:
                        if contact.get(p):
                            resolved_platform = p
                            recipient_id = contact[p]
                            break
                else:
                    recipient_id = contact.get(platform)
                    resolved_platform = platform

        if not recipient_id:
            # Contact not found — try using the name directly as recipient
            # (maybe user gave a phone number or username)
            if recipient.startswith("+") or recipient.startswith("@"):
                recipient_id = recipient
                resolved_platform = platform if platform != "auto" else "whatsapp"
            else:
                return {
                    "success": False,
                    "message": f"Contact '{recipient}' not found.",
                    "response_hint": f"I could not find the contact {recipient}. "
                                     "Is the name saved in the contacts?",
                }

        contact_name = contact.get("name", recipient) if contact else recipient

        # 2. (Optional) Enrich message via Rowboat context
        enriched_message = message
        rowboat = self._get_rowboat()
        if rowboat:
            try:
                ctx = rowboat.query_knowledge(contact_name)
                if ctx.get("success") and ctx.get("response"):
                    # We have context — but we don't rewrite the message,
                    # we just log it for future reference
                    logger.debug(f"Rowboat context for {contact_name}: {ctx['response'][:100]}")
            except Exception as e:
                logger.debug(f"Rowboat context query skipped: {e}")

        # 3. Send via Clawdbot/Automation UI
        try:
            from spaces.desktop.automation_ui_client import get_automation_client
            client = get_automation_client()

            if not client.is_available():
                return {
                    "success": False,
                    "message": "Messaging not available. Automation_ui backend is not running.",
                    "response_hint": "The messaging backend is currently not reachable.",
                }

            result = client.clawdbot_send(recipient_id, enriched_message, resolved_platform)

            success = result.get("success", True)

            # Log the sent message
            _log_message(
                direction="outgoing",
                sender="user",
                recipient=contact_name,
                platform=resolved_platform,
                text=enriched_message,
                success=success,
            )

            if success:
                return {
                    "success": True,
                    "message": f"Message sent to {contact_name} ({resolved_platform}).",
                    "response_hint": f"I sent the message to {contact_name} via {resolved_platform}.",
                    "platform": resolved_platform,
                    "recipient": contact_name,
                }
            else:
                error = result.get("error", "Unknown error")
                return {
                    "success": False,
                    "message": f"Message failed: {error}",
                    "response_hint": f"The message to {contact_name} could not be sent: {error}",
                }

        except ImportError:
            return {
                "success": False,
                "message": "Automation UI Client not available.",
                "response_hint": "The messaging system is not installed.",
            }
        except Exception as e:
            logger.error(f"MessagingPipeline.send error: {e}")
            return {
                "success": False,
                "message": f"Error while sending: {e}",
                "response_hint": f"An error occurred while sending: {e}",
            }

    # ------------------------------------------------------------------
    # READ: Check recent messages
    # ------------------------------------------------------------------

    async def read_messages(self, limit: int = 5) -> Dict[str, Any]:
        """
        Return recent incoming messages from the log.

        Returns:
            {"success": bool, "messages": [...], "response_hint": str}
        """
        logger.debug("read_messages called: limit=%s", limit)
        incoming = [m for m in _message_log if m["direction"] == "incoming"]
        recent = incoming[-limit:] if incoming else []

        if not recent:
            return {
                "success": True,
                "messages": [],
                "response_hint": "No new messages.",
            }

        lines = []
        for m in reversed(recent):
            ts = m.get("timestamp", "?")
            lines.append(f"- {m['sender']} ({m['platform']}): {m['text'][:80]}")

        hint = f"You have {len(recent)} messages:\n" + "\n".join(lines)
        return {
            "success": True,
            "messages": recent,
            "response_hint": hint,
        }

    # ------------------------------------------------------------------
    # Sync wrappers (for IntentOrchestrator tool executors)
    # ------------------------------------------------------------------

    def send_message_sync(self, params: Dict[str, Any]) -> str:
        """Synchronous wrapper for send_message (called by IntentOrchestrator)."""
        logger.debug("send_message_sync called: params=%s", params)
        recipient = params.get("recipient", "")
        message = params.get("message", "")
        platform = params.get("platform", "auto")

        if not recipient:
            return "Error: No recipient provided."
        if not message:
            return "Error: No message provided."

        loop = _get_or_create_event_loop()
        result = loop.run_until_complete(
            self.send_message(recipient, message, platform)
        )
        return result.get("response_hint", result.get("message", "Done."))

    def read_messages_sync(self, params: Dict[str, Any]) -> str:
        """Synchronous wrapper for read_messages."""
        limit = params.get("limit", 5)
        loop = _get_or_create_event_loop()
        result = loop.run_until_complete(self.read_messages(limit))
        return result.get("response_hint", "No messages.")


# ======================================================================
# Module-level helpers
# ======================================================================

def _log_message(
    direction: str,
    sender: str,
    recipient: str,
    platform: str,
    text: str,
    success: bool = True,
):
    """Add a message to the in-memory log."""
    global _message_log
    _message_log.append({
        "direction": direction,
        "sender": sender,
        "recipient": recipient,
        "platform": platform,
        "text": text,
        "success": success,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Trim
    if len(_message_log) > MAX_LOG_SIZE:
        _message_log = _message_log[-MAX_LOG_SIZE:]


def log_incoming_message(
    sender: str,
    platform: str,
    text: str,
):
    """Public helper — called by IncomingMessageHandler to log arrivals."""
    _log_message(
        direction="incoming",
        sender=sender,
        recipient="user",
        platform=platform,
        text=text,
    )


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create an event loop for sync wrappers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.new_event_loop)
                return future.result()
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# Singleton
_pipeline: Optional[MessagingPipeline] = None


def get_messaging_pipeline() -> MessagingPipeline:
    """Get or create the global MessagingPipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = MessagingPipeline()
    return _pipeline
