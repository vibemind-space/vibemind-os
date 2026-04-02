"""
Clawdbot Bridge Service for TRAE Backend

Bridges Clawdbot messaging gateway to desktop automation by reusing
the existing voice command infrastructure (IntentParser, CommandExecutor).

This allows controlling desktop automation via WhatsApp, Telegram,
Discord, Slack, Signal, and iMessage.
"""

import asyncio
import base64
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..services.redis_pubsub import redis_pubsub
from ..services.contact_registry import get_contact_registry

logger = logging.getLogger(__name__)


@dataclass
class ClawdbotMessage:
    """Incoming message from Clawdbot"""
    user_id: str
    platform: str  # whatsapp, telegram, discord, slack, signal, imessage
    text: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    message_id: Optional[str] = None
    reply_to: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ClawdbotResponse:
    """Response to send back to Clawdbot"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    image: Optional[bytes] = None
    error: Optional[str] = None
    execution_time_ms: float = 0


@dataclass
class UserSession:
    """Session state for a user"""
    user_id: str
    platform: str
    last_command: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class ClawdbotBridgeService:
    """
    Bridge service connecting Clawdbot Gateway to desktop automation.

    Reuses existing IntentParser and CommandExecutor from voice module.

    Usage:
        bridge = ClawdbotBridgeService()
        await bridge.initialize()
        response = await bridge.process_message(message)
    """

    # Redis PubSub channels
    CHANNEL_COMMANDS = "clawdbot:commands"
    CHANNEL_RESULTS = "clawdbot:results"
    CHANNEL_NOTIFICATIONS = "clawdbot:notifications"

    def __init__(
        self,
        on_notification: Optional[Callable[[str, str, str], None]] = None
    ):
        """
        Initialize ClawdbotBridgeService.

        Args:
            on_notification: Callback for notifications (user_id, platform, message)
        """
        self.on_notification = on_notification
        self._sessions: Dict[str, UserSession] = {}
        self._intent_parser = None
        self._executor = None
        self._initialized = False
        self._incoming_handler = None  # Set by messaging bridge startup

    def set_incoming_handler(self, handler):
        """Register an IncomingMessageHandler for voice-messaging pipeline."""
        self._incoming_handler = handler
        logger.info("ClawdbotBridge: IncomingMessageHandler registered")

    async def initialize(self):
        """Initialize the bridge service with lazy-loaded components."""
        if self._initialized:
            return

        try:
            # Import voice module components
            import sys
            import os

            # Add moire_agents to path if needed
            moire_agents_path = os.path.join(
                os.path.dirname(__file__),
                '..', '..', 'moire_agents'
            )
            if moire_agents_path not in sys.path:
                sys.path.insert(0, os.path.abspath(moire_agents_path))

            from voice.intent_parser import QuickIntentParser, IntentParser
            from voice.command_executor import CommandExecutor

            # Initialize parser with fallback to LLM
            self._intent_parser = QuickIntentParser(
                fallback_parser=IntentParser()
            )

            # Initialize executor with feedback callback
            self._executor = CommandExecutor(
                on_feedback=self._handle_feedback
            )

            # Subscribe to Redis channels
            if redis_pubsub.is_connected:
                await redis_pubsub.subscribe(
                    self.CHANNEL_COMMANDS,
                    self._handle_redis_command
                )
                logger.info("Subscribed to clawdbot:commands channel")

            self._initialized = True
            logger.info("ClawdbotBridgeService initialized")

        except ImportError as e:
            logger.warning(f"Voice module not available: {e}")
            # Continue without voice module - will use basic parsing
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize ClawdbotBridgeService: {e}")
            raise

    def _handle_feedback(self, message: str):
        """Handle feedback from CommandExecutor."""
        logger.info(f"Executor feedback: {message}")

    async def _handle_redis_command(self, data: Dict[str, Any]):
        """Handle incoming command from Redis PubSub."""
        try:
            message = ClawdbotMessage(
                user_id=data.get("user_id", "unknown"),
                platform=data.get("platform", "unknown"),
                text=data.get("text", ""),
                message_id=data.get("message_id"),
            )

            response = await self.process_message(message)

            # Publish result back
            await self.publish_result(
                message.user_id,
                message.platform,
                response
            )

        except Exception as e:
            logger.error(f"Error handling Redis command: {e}")

    async def process_message(self, message: ClawdbotMessage) -> ClawdbotResponse:
        """
        Process an incoming message from Clawdbot.

        Parses the message using IntentParser and executes via CommandExecutor.

        Args:
            message: Incoming Clawdbot message

        Returns:
            ClawdbotResponse with result
        """
        import time
        start_time = time.time()

        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        # Get or create session
        session = self._get_or_create_session(message.user_id, message.platform)
        session.last_command = message.text
        session.updated_at = datetime.utcnow()

        # --- Messaging Pipeline Hook ---
        # Forward incoming messages to IncomingMessageHandler for relevance
        # checking, Rowboat storage, and voice notification.
        # This runs in the background so it doesn't block command execution.
        if self._incoming_handler:
            try:
                asyncio.create_task(
                    self._incoming_handler.on_message(
                        user_id=message.user_id,
                        platform=message.platform,
                        text=message.text,
                        metadata={"message_id": message.message_id},
                    )
                )
            except Exception as e:
                logger.warning(f"IncomingHandler hook error: {e}")

        try:
            # Handle special commands
            text_lower = message.text.lower().strip()

            if text_lower in ["screenshot", "bildschirm", "screen"]:
                return await self._handle_screenshot_command()

            if text_lower in ["status", "hilfe", "help", "?"]:
                return await self._handle_status_command()

            if text_lower in ["ocr", "lesen", "read", "text"]:
                return await self._handle_ocr_command()

            # Handle contact lookup commands
            if text_lower.startswith(("kontakt ", "contact ", "wer ist ")):
                return await self._handle_contact_lookup(message.text)

            # Handle "send to X" commands with contact resolution
            if any(text_lower.startswith(p) for p in [
                "schick an ", "sende an ", "send to ", "nachricht an "
            ]):
                return await self._handle_send_to_contact(message.text, message.platform)

            # Handle skill execution commands
            if any(text_lower.startswith(p) for p in [
                "führe ", "fuehre ", "execute ", "skill ", "run skill "
            ]):
                return await self._handle_skill_command(message.text)

            # Handle skill listing
            if text_lower in ["skills", "meine skills", "my skills", "installed skills"]:
                return await self._handle_list_skills()

            # Resolve variables in message text
            registry = get_contact_registry()
            resolved_text = registry.resolve_variables(message.text)

            # Process with IntentParser + CommandExecutor
            if self._intent_parser and self._executor:
                # Parse intent
                intent = await self._intent_parser.parse(message.text)

                if intent.error:
                    return ClawdbotResponse(
                        success=False,
                        message=f"Konnte Befehl nicht verstehen: {intent.error}",
                        error=intent.error,
                        execution_time_ms=(time.time() - start_time) * 1000
                    )

                if not intent.actions:
                    return ClawdbotResponse(
                        success=False,
                        message="Keine ausführbare Aktion erkannt",
                        error="No actions parsed",
                        execution_time_ms=(time.time() - start_time) * 1000
                    )

                # Execute actions
                report = await self._executor.execute(intent)

                # Build response
                session.last_result = {
                    "success": report.success,
                    "actions": len(report.results),
                    "context": intent.context
                }

                return ClawdbotResponse(
                    success=report.success,
                    message=report.feedback_message,
                    data={
                        "actions_executed": len(report.results),
                        "context": intent.context,
                        "duration_ms": report.total_duration_ms
                    },
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            else:
                # Fallback: simple command handling without voice module
                return await self._handle_fallback_command(message.text)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return ClawdbotResponse(
                success=False,
                message=f"Fehler bei der Ausführung: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _handle_screenshot_command(self) -> ClawdbotResponse:
        """Take and return a screenshot."""
        import time
        start_time = time.time()

        try:
            import pyautogui

            # Take screenshot
            screenshot = pyautogui.screenshot()

            # Convert to bytes
            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=85)
            image_bytes = buffer.getvalue()

            return ClawdbotResponse(
                success=True,
                message="Screenshot aufgenommen",
                image=image_bytes,
                data={"size": len(image_bytes)},
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ClawdbotResponse(
                success=False,
                message=f"Screenshot fehlgeschlagen: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _handle_ocr_command(self) -> ClawdbotResponse:
        """Read screen text via OCR."""
        import time
        start_time = time.time()

        try:
            # Try using MCP handoff tools
            import sys
            import os

            moire_agents_path = os.path.join(
                os.path.dirname(__file__),
                '..', '..', 'moire_agents'
            )
            if moire_agents_path not in sys.path:
                sys.path.insert(0, os.path.abspath(moire_agents_path))

            from mcp_server_handoff import handle_read_screen

            result = await handle_read_screen()

            return ClawdbotResponse(
                success=True,
                message="Bildschirmtext gelesen",
                data=result,
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except ImportError:
            # Fallback: simple tesseract
            try:
                import pyautogui
                import pytesseract

                screenshot = pyautogui.screenshot()
                text = pytesseract.image_to_string(screenshot, lang='deu+eng')

                return ClawdbotResponse(
                    success=True,
                    message="Bildschirmtext gelesen",
                    data={"text": text[:2000]},  # Limit length
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            except Exception as e:
                return ClawdbotResponse(
                    success=False,
                    message=f"OCR fehlgeschlagen: {str(e)}",
                    error=str(e),
                    execution_time_ms=(time.time() - start_time) * 1000
                )

        except Exception as e:
            return ClawdbotResponse(
                success=False,
                message=f"OCR fehlgeschlagen: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _handle_status_command(self) -> ClawdbotResponse:
        """Return status and help information."""
        import time
        start_time = time.time()

        help_text = """🤖 Desktop Automation via Clawdbot

Verfügbare Befehle:
• "öffne [app/url]" - Öffne App oder Website
• "klick [ziel]" - Klicke auf Element
• "tippe [text]" - Text eingeben
• "screenshot" - Screenshot senden
• "lesen" / "ocr" - Bildschirmtext lesen
• "scrolle [hoch/runter]" - Scrollen
• Tastenkombinationen: "strg+c", "strg+v", etc.

Skills (ClawHub):
• "skills" - Installierte Skills anzeigen
• "führe [skill-name] aus" - Skill ausführen
• "skill [name]" - Skill ausführen

Beispiele:
• "öffne chrome"
• "öffne google.com"
• "tippe Hallo Welt"
• "führe browser-automation aus"
• "skills"

Status: ✅ Verbunden"""

        return ClawdbotResponse(
            success=True,
            message=help_text,
            data={
                "status": "connected",
                "capabilities": [
                    "open_url", "click", "type_text", "scroll",
                    "screenshot", "ocr", "key_press"
                ]
            },
            execution_time_ms=(time.time() - start_time) * 1000
        )

    async def _handle_fallback_command(self, text: str) -> ClawdbotResponse:
        """Handle command without voice module (basic parsing)."""
        import time
        start_time = time.time()

        text_lower = text.lower().strip()

        try:
            import pyautogui
            import webbrowser

            # Basic URL opening
            if text_lower.startswith(("öffne ", "open ", "oeffne ")):
                target = text[text.find(" "):].strip()

                if "." in target or target.startswith("http"):
                    url = target if target.startswith("http") else f"https://{target}"
                    webbrowser.open(url)
                    return ClawdbotResponse(
                        success=True,
                        message=f"Öffne {url}",
                        execution_time_ms=(time.time() - start_time) * 1000
                    )
                else:
                    # Open via Windows Start menu
                    pyautogui.press("win")
                    await asyncio.sleep(0.5)
                    pyautogui.write(target, interval=0.02)
                    await asyncio.sleep(0.5)
                    pyautogui.press("enter")
                    return ClawdbotResponse(
                        success=True,
                        message=f"Öffne {target}",
                        execution_time_ms=(time.time() - start_time) * 1000
                    )

            # Scroll commands
            if "scroll" in text_lower:
                direction = -5 if any(w in text_lower for w in ["up", "hoch", "oben"]) else 5
                pyautogui.scroll(direction)
                return ClawdbotResponse(
                    success=True,
                    message="Gescrollt",
                    execution_time_ms=(time.time() - start_time) * 1000
                )

            return ClawdbotResponse(
                success=False,
                message=f"Befehl nicht erkannt: {text}",
                error="Unknown command",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return ClawdbotResponse(
                success=False,
                message=f"Fehler: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _handle_contact_lookup(self, text: str) -> ClawdbotResponse:
        """
        Handle contact lookup commands.

        Examples:
            "kontakt peter" -> Shows Peter's contact info
            "contact müller" -> Shows Müller's contact info
            "wer ist pm" -> Shows contact with alias "pm"
        """
        import time
        start_time = time.time()

        # Extract the query part
        for prefix in ["kontakt ", "contact ", "wer ist "]:
            if text.lower().startswith(prefix):
                query = text[len(prefix):].strip()
                break
        else:
            query = text.strip()

        if not query:
            return ClawdbotResponse(
                success=False,
                message="Bitte gib einen Namen an. Beispiel: 'kontakt Peter'",
                error="No query provided",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        registry = get_contact_registry()
        contact = registry.resolve(query)

        if contact:
            # Format contact info
            name = contact.get("name", query)
            lines = [f"📇 Kontakt: {name}"]

            if contact.get("whatsapp"):
                lines.append(f"📱 WhatsApp: {contact['whatsapp']}")
            if contact.get("telegram"):
                lines.append(f"✈️ Telegram: {contact['telegram']}")
            if contact.get("discord"):
                lines.append(f"🎮 Discord: {contact['discord']}")
            if contact.get("email"):
                lines.append(f"📧 Email: {contact['email']}")
            if contact.get("notes"):
                lines.append(f"📝 Notiz: {contact['notes']}")

            # Show aliases
            aliases = contact.get("aliases", [])
            if aliases:
                lines.append(f"🏷️ Aliase: {', '.join(aliases)}")

            return ClawdbotResponse(
                success=True,
                message="\n".join(lines),
                data={"contact": contact, "query": query},
                execution_time_ms=(time.time() - start_time) * 1000
            )
        else:
            # Search for similar contacts
            similar = registry.search(query, limit=3)
            if similar:
                suggestions = [s["contact"].get("name", s["key"]) for s in similar]
                return ClawdbotResponse(
                    success=False,
                    message=f"Kontakt '{query}' nicht gefunden.\n\nMeintest du vielleicht: {', '.join(suggestions)}?",
                    data={"suggestions": suggestions},
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            else:
                return ClawdbotResponse(
                    success=False,
                    message=f"Kontakt '{query}' nicht gefunden.",
                    error="Contact not found",
                    execution_time_ms=(time.time() - start_time) * 1000
                )

    async def _handle_send_to_contact(self, text: str, platform: str) -> ClawdbotResponse:
        """
        Handle "send to X" commands with contact resolution.

        Examples:
            "schick an peter hallo wie gehts" -> Resolves peter and prepares message
            "sende an mama ich bin unterwegs" -> Resolves mama and prepares message
            "send to boss meeting update" -> Resolves boss and prepares message
        """
        import time
        start_time = time.time()

        # Parse the command to extract recipient and message
        text_lower = text.lower()
        original_text = text

        # Find the prefix and extract the rest
        prefixes = ["schick an ", "sende an ", "send to ", "nachricht an "]
        rest = None
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                rest = original_text[len(prefix):].strip()
                break

        if not rest:
            return ClawdbotResponse(
                success=False,
                message="Format: 'schick an [Name] [Nachricht]'",
                error="Invalid command format",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        # Split into recipient and message
        # Try to find the first word as recipient, rest as message
        parts = rest.split(" ", 1)
        if len(parts) < 2:
            return ClawdbotResponse(
                success=False,
                message="Format: 'schick an [Name] [Nachricht]'\nBeispiel: 'schick an peter hallo wie gehts'",
                error="Missing message",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        recipient_query = parts[0]
        message_text = parts[1]

        # Resolve the recipient
        registry = get_contact_registry()
        contact = registry.resolve(recipient_query)

        if not contact:
            # Try with two words as recipient (for "an mama papa")
            if " " in parts[1]:
                two_word_parts = rest.split(" ", 2)
                if len(two_word_parts) >= 3:
                    two_word_query = f"{two_word_parts[0]} {two_word_parts[1]}"
                    contact = registry.resolve(two_word_query)
                    if contact:
                        recipient_query = two_word_query
                        message_text = two_word_parts[2]

        if not contact:
            # Search for suggestions
            similar = registry.search(recipient_query, limit=3)
            if similar:
                suggestions = [s["contact"].get("name", s["key"]) for s in similar]
                return ClawdbotResponse(
                    success=False,
                    message=f"Kontakt '{recipient_query}' nicht gefunden.\n\nMeintest du: {', '.join(suggestions)}?",
                    data={"suggestions": suggestions, "original_message": message_text},
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            return ClawdbotResponse(
                success=False,
                message=f"Kontakt '{recipient_query}' nicht gefunden.",
                error="Contact not found",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        # Resolve variables in the message
        resolved_message = registry.resolve_variables(message_text)

        # Get recipient ID for the platform
        recipient_id = contact.get(platform.lower())
        if not recipient_id:
            # Try alternative platforms
            for alt_platform in ["whatsapp", "telegram", "discord", "signal", "imessage"]:
                if contact.get(alt_platform):
                    recipient_id = contact.get(alt_platform)
                    platform = alt_platform
                    break

        name = contact.get("name", recipient_query)

        if recipient_id:
            return ClawdbotResponse(
                success=True,
                message=f"📤 Nachricht an {name} vorbereitet\n\n"
                        f"Platform: {platform}\n"
                        f"Empfänger: {recipient_id}\n"
                        f"Nachricht: {resolved_message}",
                data={
                    "action": "send_message",
                    "recipient": name,
                    "recipient_id": recipient_id,
                    "platform": platform,
                    "message": resolved_message,
                    "contact": contact
                },
                execution_time_ms=(time.time() - start_time) * 1000
            )
        else:
            available = []
            for p in ["whatsapp", "telegram", "discord", "email", "signal"]:
                if contact.get(p):
                    available.append(p)

            return ClawdbotResponse(
                success=False,
                message=f"Kontakt '{name}' hat keine {platform} ID.\n\n"
                        f"Verfügbare Kanäle: {', '.join(available) if available else 'keine'}",
                error="Platform not available for contact",
                data={"contact": contact, "available_platforms": available},
                execution_time_ms=(time.time() - start_time) * 1000
            )

    async def _handle_skill_command(self, text: str) -> ClawdbotResponse:
        """
        Handle skill execution commands from messaging.

        Examples:
            "führe browser-automation aus" -> Executes browser-automation skill
            "skill screenshot-ocr" -> Executes screenshot-ocr skill
            "execute github-manager" -> Executes github-manager skill
        """
        import time
        start_time = time.time()

        # Extract skill name from command
        text_lower = text.lower().strip()
        skill_name = None

        for prefix in ["führe ", "fuehre ", "execute ", "skill ", "run skill "]:
            if text_lower.startswith(prefix):
                rest = text[len(prefix):].strip()
                # Remove trailing " aus" (German)
                if rest.lower().endswith(" aus"):
                    rest = rest[:-4].strip()
                skill_name = rest
                break

        if not skill_name:
            return ClawdbotResponse(
                success=False,
                message="Format: 'führe [skill-name] aus' oder 'skill [name]'",
                error="Invalid skill command",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            from ..services.skill_manager import get_skill_manager

            manager = get_skill_manager()
            result = await manager.execute_skill(skill_name, {})

            return ClawdbotResponse(
                success=result.success,
                message=result.message,
                data=result.data,
                error=result.error,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Skill execution failed: {e}")
            return ClawdbotResponse(
                success=False,
                message=f"Skill-Ausführung fehlgeschlagen: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def _handle_list_skills(self) -> ClawdbotResponse:
        """List all installed skills."""
        import time
        start_time = time.time()

        try:
            from ..services.skill_manager import get_skill_manager

            manager = get_skill_manager()
            installed = manager.list_installed()

            if not installed:
                return ClawdbotResponse(
                    success=True,
                    message="Keine Skills installiert.\n\nInstalliere Skills über die Web-UI unter /api/clawhub/search",
                    data={"skills": []},
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            lines = ["📦 Installierte Skills:\n"]
            for skill in installed:
                status = "✅" if skill.enabled else "⏸️"
                lines.append(f"{status} {skill.name} v{skill.version}")
                if skill.execution_count > 0:
                    lines.append(f"   Ausführungen: {skill.execution_count}")

            lines.append(f"\nGesamt: {len(installed)} Skills")

            return ClawdbotResponse(
                success=True,
                message="\n".join(lines),
                data={"skills": [s.model_dump() for s in installed]},
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return ClawdbotResponse(
                success=False,
                message=f"Fehler: {str(e)}",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _get_or_create_session(self, user_id: str, platform: str) -> UserSession:
        """Get or create a user session."""
        session_key = f"{platform}:{user_id}"

        if session_key not in self._sessions:
            self._sessions[session_key] = UserSession(
                user_id=user_id,
                platform=platform
            )

        return self._sessions[session_key]

    def get_session(self, user_id: str, platform: str) -> Optional[UserSession]:
        """Get a user session if it exists."""
        session_key = f"{platform}:{user_id}"
        return self._sessions.get(session_key)

    def get_all_sessions(self) -> List[UserSession]:
        """Get all active sessions."""
        return list(self._sessions.values())

    async def publish_result(
        self,
        user_id: str,
        platform: str,
        response: ClawdbotResponse
    ):
        """Publish execution result to Redis for Clawdbot to pick up."""
        if not redis_pubsub.is_connected:
            logger.warning("Redis not connected, cannot publish result")
            return

        result_data = {
            "user_id": user_id,
            "platform": platform,
            "success": response.success,
            "message": response.message,
            "data": response.data,
            "error": response.error,
            "execution_time_ms": response.execution_time_ms,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Include image as base64 if present
        if response.image:
            result_data["image_base64"] = base64.b64encode(response.image).decode()

        await redis_pubsub.publish(self.CHANNEL_RESULTS, result_data)

    async def send_notification(
        self,
        user_id: str,
        platform: str,
        message: str,
        notification_type: str = "info"
    ):
        """Send a notification to a user via Clawdbot."""
        if not redis_pubsub.is_connected:
            logger.warning("Redis not connected, cannot send notification")
            return

        notification = {
            "user_id": user_id,
            "platform": platform,
            "message": message,
            "type": notification_type,
            "timestamp": datetime.utcnow().isoformat()
        }

        await redis_pubsub.publish(self.CHANNEL_NOTIFICATIONS, notification)

        if self.on_notification:
            self.on_notification(user_id, platform, message)

    async def broadcast_notification(
        self,
        message: str,
        notification_type: str = "info"
    ):
        """Broadcast notification to all active sessions."""
        for session in self._sessions.values():
            await self.send_notification(
                session.user_id,
                session.platform,
                message,
                notification_type
            )

    async def send_callback(
        self,
        user_id: str,
        platform: str,
        response: ClawdbotResponse,
        callback_url: Optional[str] = None
    ):
        """
        Send response back to Clawdbot Gateway via HTTP callback.

        This enables async operations to send results back to users
        after the initial HTTP response has already been sent.

        Args:
            user_id: Target user ID
            platform: Target platform (whatsapp, telegram, etc.)
            response: The ClawdbotResponse to send back
            callback_url: Optional custom callback URL (defaults to Gateway plugin)
        """
        if callback_url is None:
            callback_url = "http://localhost:18789/plugins/automation-ui/results"

        payload = {
            "user_id": user_id,
            "platform": platform,
            "success": response.success,
            "message": response.message,
            "data": response.data,
            "error": response.error,
            "execution_time_ms": response.execution_time_ms,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Include image as base64 if present
        if response.image:
            payload["image_base64"] = base64.b64encode(response.image).decode()

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    callback_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Callback sent to {user_id}@{platform}")
                    else:
                        logger.warning(
                            f"Callback failed: {resp.status} - {await resp.text()}"
                        )

        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            # Fallback: try with httpx or requests
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    resp = await client.post(callback_url, json=payload, timeout=10)
                    if resp.status_code == 200:
                        logger.info(f"Callback sent via httpx to {user_id}@{platform}")
                    else:
                        logger.warning(f"Callback failed: {resp.status_code}")

            except ImportError:
                logger.error("Neither aiohttp nor httpx available for callback")

        except Exception as e:
            logger.error(f"Failed to send callback: {e}")

    async def send_message_to_user(
        self,
        user_id: str,
        platform: str,
        message: str,
        image: Optional[bytes] = None
    ):
        """
        Convenience method to send a message to a user via callback.

        Args:
            user_id: Target user ID
            platform: Target platform
            message: Message text to send
            image: Optional image bytes (JPEG/PNG)
        """
        response = ClawdbotResponse(
            success=True,
            message=message,
            image=image,
            execution_time_ms=0
        )
        await self.send_callback(user_id, platform, response)


# Global singleton instance
_clawdbot_bridge: Optional[ClawdbotBridgeService] = None


async def get_clawdbot_bridge() -> ClawdbotBridgeService:
    """Get the global ClawdbotBridgeService instance."""
    global _clawdbot_bridge

    if _clawdbot_bridge is None:
        _clawdbot_bridge = ClawdbotBridgeService()
        await _clawdbot_bridge.initialize()

    return _clawdbot_bridge
