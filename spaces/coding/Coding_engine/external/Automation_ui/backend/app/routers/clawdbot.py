"""
Clawdbot API Router

REST API endpoints for Clawdbot integration, enabling desktop automation
via WhatsApp, Telegram, Discord, Slack, Signal, and iMessage.

Endpoints:
- POST /command - Execute automation command
- POST /screenshot - Get current screenshot
- GET /status - Get bridge status
- GET /sessions - List active user sessions
- POST /webhook - Webhook for Clawdbot callbacks
"""

import base64
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..services.clawdbot_bridge import (
    ClawdbotBridgeService,
    ClawdbotMessage,
    ClawdbotResponse,
    get_clawdbot_bridge,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class CommandRequest(BaseModel):
    """Request to execute an automation command"""
    command: str = Field(..., description="Natural language command to execute")
    user_id: str = Field(default="api_user", description="User identifier")
    platform: str = Field(default="api", description="Source platform")
    message_id: Optional[str] = Field(None, description="Optional message ID")


class CommandResponse(BaseModel):
    """Response from command execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    image_base64: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float


class ScreenshotRequest(BaseModel):
    """Request for screenshot"""
    user_id: str = Field(default="api_user", description="User identifier")
    platform: str = Field(default="api", description="Source platform")
    quality: int = Field(default=85, ge=10, le=100, description="JPEG quality")


class StatusResponse(BaseModel):
    """Bridge status response"""
    status: str
    initialized: bool
    active_sessions: int
    capabilities: List[str]
    timestamp: str


class SessionInfo(BaseModel):
    """User session information"""
    user_id: str
    platform: str
    last_command: Optional[str] = None
    created_at: str
    updated_at: str


class WebhookPayload(BaseModel):
    """Incoming webhook payload from Clawdbot"""
    type: str = Field(..., description="Event type")
    user_id: str
    platform: str
    text: Optional[str] = None
    message_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/command", response_model=CommandResponse)
async def execute_command(request: CommandRequest):
    """
    Execute a desktop automation command.

    Takes a natural language command and executes it using the
    IntentParser and CommandExecutor from the voice module.

    Examples:
    - "öffne chrome" -> Opens Chrome browser
    - "tippe Hallo Welt" -> Types "Hallo Welt"
    - "scrolle nach unten" -> Scrolls down
    """
    try:
        bridge = await get_clawdbot_bridge()

        message = ClawdbotMessage(
            user_id=request.user_id,
            platform=request.platform,
            text=request.command,
            message_id=request.message_id,
        )

        response = await bridge.process_message(message)

        # Convert image to base64 if present
        image_base64 = None
        if response.image:
            image_base64 = base64.b64encode(response.image).decode()

        return CommandResponse(
            success=response.success,
            message=response.message,
            data=response.data,
            image_base64=image_base64,
            error=response.error,
            execution_time_ms=response.execution_time_ms,
        )

    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screenshot")
async def get_screenshot(request: ScreenshotRequest):
    """
    Take and return a screenshot of the current desktop.

    Returns JPEG image as binary response.
    """
    try:
        import io

        import pyautogui

        # Take screenshot
        screenshot = pyautogui.screenshot()

        # Convert to JPEG bytes
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=request.quality)
        image_bytes = buffer.getvalue()

        return Response(
            content=image_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": "inline; filename=screenshot.jpg",
                "X-User-Id": request.user_id,
                "X-Platform": request.platform,
            }
        )

    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot")
async def get_screenshot_simple():
    """
    Simple screenshot endpoint (GET, no params).

    Returns JPEG image as binary response.
    """
    try:
        import io

        import pyautogui

        screenshot = pyautogui.screenshot()

        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()

        return Response(
            content=image_bytes,
            media_type="image/jpeg",
            headers={"Content-Disposition": "inline; filename=screenshot.jpg"}
        )

    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get the current status of the Clawdbot bridge.

    Returns initialization state, active sessions, and capabilities.
    """
    try:
        bridge = await get_clawdbot_bridge()
        sessions = bridge.get_all_sessions()

        return StatusResponse(
            status="connected" if bridge._initialized else "initializing",
            initialized=bridge._initialized,
            active_sessions=len(sessions),
            capabilities=[
                "open_url",
                "click",
                "type_text",
                "scroll",
                "screenshot",
                "ocr",
                "key_press",
                "vision_analyze",
            ],
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=List[SessionInfo])
async def get_sessions():
    """
    List all active user sessions.

    Returns session info for each connected user.
    """
    try:
        bridge = await get_clawdbot_bridge()
        sessions = bridge.get_all_sessions()

        return [
            SessionInfo(
                user_id=s.user_id,
                platform=s.platform,
                last_command=s.last_command,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
            for s in sessions
        ]

    except Exception as e:
        logger.error(f"Sessions list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def webhook_handler(payload: WebhookPayload, request: Request):
    """
    Webhook endpoint for Clawdbot Gateway callbacks.

    Handles incoming messages from messaging platforms.
    """
    try:
        logger.info(f"Webhook received: {payload.type} from {payload.platform}")

        bridge = await get_clawdbot_bridge()

        if payload.type == "message" and payload.text:
            # Process incoming message
            message = ClawdbotMessage(
                user_id=payload.user_id,
                platform=payload.platform,
                text=payload.text,
                message_id=payload.message_id,
            )

            response = await bridge.process_message(message)

            # Publish result for Clawdbot to send back
            await bridge.publish_result(
                payload.user_id,
                payload.platform,
                response
            )

            return {
                "status": "processed",
                "success": response.success,
                "message": response.message,
            }

        elif payload.type == "status":
            # Status check from Clawdbot
            return {
                "status": "ok",
                "initialized": bridge._initialized,
            }

        else:
            return {"status": "ignored", "reason": f"Unknown type: {payload.type}"}

    except Exception as e:
        logger.error(f"Webhook handler failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notify")
async def send_notification(
    user_id: str,
    platform: str,
    message: str,
    notification_type: str = "info"
):
    """
    Send a notification to a user via Clawdbot.

    Args:
        user_id: Target user ID
        platform: Target platform (whatsapp, telegram, etc.)
        message: Notification message
        notification_type: Type of notification (info, success, warning, error)
    """
    try:
        bridge = await get_clawdbot_bridge()

        await bridge.send_notification(
            user_id=user_id,
            platform=platform,
            message=message,
            notification_type=notification_type
        )

        return {"status": "sent", "user_id": user_id, "platform": platform}

    except Exception as e:
        logger.error(f"Notification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "clawdbot"}


# ============================================================================
# Contact Management Endpoints
# ============================================================================


class ContactCreate(BaseModel):
    """Request to create/update a contact"""
    key: str = Field(..., description="Unique contact key (e.g., 'peter')")
    name: str = Field(..., description="Display name")
    whatsapp: Optional[str] = Field(None, description="WhatsApp number (+49...)")
    telegram: Optional[str] = Field(None, description="Telegram chat ID")
    discord: Optional[str] = Field(None, description="Discord user ID")
    email: Optional[str] = Field(None, description="Email address")
    signal: Optional[str] = Field(None, description="Signal number")
    imessage: Optional[str] = Field(None, description="iMessage ID")
    aliases: Optional[List[str]] = Field(default_factory=list, description="Alternative names")
    notes: Optional[str] = Field(None, description="Notes about this contact")


class ContactResponse(BaseModel):
    """Contact information response"""
    key: str
    name: str
    whatsapp: Optional[str] = None
    telegram: Optional[str] = None
    discord: Optional[str] = None
    email: Optional[str] = None
    signal: Optional[str] = None
    imessage: Optional[str] = None
    aliases: List[str] = []
    notes: Optional[str] = None


class ContactSearchResult(BaseModel):
    """Contact search result"""
    key: str
    contact: Dict[str, Any]
    score: float


@router.get("/contacts", response_model=Dict[str, Dict[str, Any]])
async def list_contacts():
    """
    List all contacts in the registry.

    Returns dictionary of contact_key -> contact_info.
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    return registry.list_contacts()


@router.get("/contacts/search")
async def search_contacts(q: str, limit: int = 5):
    """
    Search contacts by name/alias with fuzzy matching.

    Args:
        q: Search query
        limit: Maximum results to return
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    results = registry.search(q, limit=limit)

    return {
        "query": q,
        "results": results
    }


@router.get("/contacts/{key}")
async def get_contact(key: str):
    """
    Get a specific contact by key.

    Args:
        key: Contact key (e.g., 'peter')
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    contact = registry.resolve(key)

    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact '{key}' not found")

    return {"key": key, "contact": contact}


@router.post("/contacts", response_model=Dict[str, Any])
async def create_contact(request: ContactCreate):
    """
    Create or update a contact.

    If the key already exists, the contact will be updated.
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()

    contact_data = {
        "name": request.name,
        "aliases": request.aliases or [],
    }

    # Add optional fields if provided
    if request.whatsapp:
        contact_data["whatsapp"] = request.whatsapp
    if request.telegram:
        contact_data["telegram"] = request.telegram
    if request.discord:
        contact_data["discord"] = request.discord
    if request.email:
        contact_data["email"] = request.email
    if request.signal:
        contact_data["signal"] = request.signal
    if request.imessage:
        contact_data["imessage"] = request.imessage
    if request.notes:
        contact_data["notes"] = request.notes

    success = registry.add_contact(request.key, contact_data)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save contact")

    return {
        "status": "created",
        "key": request.key,
        "contact": contact_data
    }


@router.delete("/contacts/{key}")
async def delete_contact(key: str):
    """
    Delete a contact by key.

    Args:
        key: Contact key to delete
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    success = registry.remove_contact(key)

    if not success:
        raise HTTPException(status_code=404, detail=f"Contact '{key}' not found or delete failed")

    return {"status": "deleted", "key": key}


@router.post("/contacts/{key}/resolve")
async def resolve_contact(key: str, platform: Optional[str] = None):
    """
    Resolve a contact query to recipient info.

    Supports fuzzy matching by name or alias.

    Args:
        key: Name, alias, or fuzzy query
        platform: Optional platform to get specific ID for
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    contact = registry.resolve(key)

    if not contact:
        # Search for suggestions
        similar = registry.search(key, limit=3)
        if similar:
            suggestions = [s["contact"].get("name", s["key"]) for s in similar]
            return {
                "found": False,
                "query": key,
                "suggestions": suggestions
            }
        raise HTTPException(status_code=404, detail=f"Contact '{key}' not found")

    result = {
        "found": True,
        "query": key,
        "contact": contact
    }

    if platform:
        recipient_id = contact.get(platform.lower())
        result["platform"] = platform
        result["recipient_id"] = recipient_id

    return result


# ============================================================================
# Variables & Templates Endpoints
# ============================================================================


@router.get("/variables")
async def list_variables():
    """List all predefined variables."""
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    return registry.list_variables()


@router.post("/variables/{name}")
async def set_variable(name: str, value: str):
    """Set a variable value."""
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    success = registry.set_variable(name, value)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save variable")

    return {"status": "set", "name": name, "value": value}


@router.get("/templates")
async def list_templates():
    """List all message templates."""
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    return registry.list_templates()


@router.post("/templates/render")
async def render_template(name: str, values: Optional[Dict[str, str]] = None):
    """
    Render a template with provided values.

    Args:
        name: Template name
        values: Dictionary of values to substitute
    """
    from ..services.contact_registry import get_contact_registry

    registry = get_contact_registry()
    rendered = registry.render_template(name, **(values or {}))

    if rendered is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    return {"name": name, "rendered": rendered}
