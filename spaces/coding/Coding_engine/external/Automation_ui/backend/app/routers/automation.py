"""
Automation Router for TRAE Backend

Provides endpoints for click automation, keyboard, scroll and mouse operations."""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..logger_config import get_logger, log_api_request
from ..services import get_click_automation_service

logger = get_logger("automation")

router = APIRouter()

# ============================================================
# Request Models
# ============================================================


class ClickRequest(BaseModel):
    x: float
    y: float
    button: str = "left"
    click_type: str = "single"
    delay: float = 0.1


class TypeTextRequest(BaseModel):
    text: str
    interval: float = 0.02


class KeyPressRequest(BaseModel):
    key: str
    modifiers: List[str] = []


class HotkeyRequest(BaseModel):
    keys: List[str]


class ScrollRequest(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    amount: int = 3
    direction: str = "vertical"  # "vertical" or "horizontal"


class MouseMoveRequest(BaseModel):
    x: float
    y: float
    duration: float = 0.2


class MouseDragRequest(BaseModel):
    startX: float
    startY: float
    endX: float
    endY: float
    button: str = "left"
    duration: float = 0.5


# ============================================================
# Status & Capabilities Endpoints
# ============================================================


@router.get("/status")
@log_api_request(logger)
async def get_automation_status(request: Request):
    """Get automation service status"""
    try:
        click_service = get_click_automation_service()

        status_info = {
            "available": click_service is not None,
            "healthy": True,
            "initialized": True,
            "screen_size": {"width": 0, "height": 0},
            "capabilities": [],
        }

        if click_service:
            if hasattr(click_service, "is_healthy"):
                status_info["healthy"] = click_service.is_healthy()

            if hasattr(click_service, "get_screen_size"):
                screen_size = click_service.get_screen_size()
                if screen_size:
                    status_info["screen_size"] = screen_size

            # Get capabilities
            status_info["capabilities"] = [
                "click",
                "double_click",
                "right_click",
                "mouse_move",
                "mouse_drag",
                "scroll",
                "key_press",
                "hotkey",
                "type_text",
            ]
        else:
            status_info["healthy"] = False
            status_info["initialized"] = False

        return JSONResponse(
            content={
                "success": True,
                "status": status_info,
                "service_name": "click_automation_service",
            }
        )

    except Exception as e:
        logger.error(f"Automation status error: {e}", exc_info=True)
        return JSONResponse(
            content={
                "success": False,
                "status": {
                    "available": False,
                    "healthy": False,
                    "initialized": False,
                    "error": str(e),
                },
                "service_name": "click_automation_service",
            }
        )


@router.get("/capabilities")
@log_api_request(logger)
async def get_automation_capabilities(request: Request):
    """Get automation capabilities"""
    try:
        click_service = get_click_automation_service()

        capabilities = {
            "mouse_actions": [
                {
                    "name": "click",
                    "description": "Perform single click",
                    "endpoint": "/api/automation/click",
                },
                {
                    "name": "double_click",
                    "description": "Perform double click",
                    "endpoint": "/api/automation/click",
                },
                {
                    "name": "right_click",
                    "description": "Perform right click",
                    "endpoint": "/api/automation/click",
                },
                {
                    "name": "middle_click",
                    "description": "Perform middle click",
                    "endpoint": "/api/automation/click",
                },
                {
                    "name": "mouse_move",
                    "description": "Move mouse cursor",
                    "endpoint": "/api/automation/move",
                },
                {
                    "name": "mouse_drag",
                    "description": "Drag and drop",
                    "endpoint": "/api/automation/drag",
                },
                {
                    "name": "scroll",
                    "description": "Scroll mouse wheel",
                    "endpoint": "/api/automation/scroll",
                },
            ],
            "keyboard_actions": [
                {
                    "name": "key_press",
                    "description": "Press single key",
                    "endpoint": "/api/automation/key",
                },
                {
                    "name": "hotkey",
                    "description": "Press key combination",
                    "endpoint": "/api/automation/hotkey",
                },
                {
                    "name": "type_text",
                    "description": "Type text string",
                    "endpoint": "/api/automation/type",
                },
            ],
            "supported_buttons": ["left", "right", "middle"],
            "click_types": ["single", "double"],
            "available": click_service is not None,
        }

        if click_service and hasattr(click_service, "get_screen_size"):
            screen_size = click_service.get_screen_size()
            if screen_size:
                capabilities["screen_resolution"] = screen_size

        return JSONResponse(
            content={
                "success": True,
                "capabilities": capabilities,
                "service_available": click_service is not None,
            }
        )

    except Exception as e:
        logger.error(f"Get automation capabilities error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Mouse Action Endpoints
# ============================================================


@router.post("/click")
@log_api_request(logger)
async def execute_click(request: ClickRequest):
    """Execute automated click"""
    try:
        click_service = get_click_automation_service()

        if click_service is None:
            logger.error(
                "Click automation service not available - service not initialized"
            )
            raise HTTPException(
                status_code=503,
                detail="Click automation service not available. Please check service initialization.",
            )

        if not click_service.initialized:
            logger.info("Initializing click automation service...")
            await click_service.initialize()

        if hasattr(click_service, "is_healthy") and not click_service.is_healthy():
            logger.error("Click automation service is not healthy")
            raise HTTPException(
                status_code=503,
                detail="Click automation service is not healthy. Please check system dependencies.",
            )

        result = await click_service.perform_click(
            x=request.x,
            y=request.y,
            button=request.button,
            click_type=request.click_type,
            delay=request.delay,
        )

        return JSONResponse(
            content={
                "success": result.get("success", False),
                "clicked": result.get("clicked", False),
                "coordinates": result.get("coordinates", {}),
                "execution_time": result.get("execution_time", 0),
                "error": result.get("error"),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Click automation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/move")
@log_api_request(logger)
async def execute_mouse_move(request: MouseMoveRequest):
    """Move mouse cursor to specified position"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(
            f"🖱️ Moving mouse to ({request.x}, {request.y}) duration={request.duration}s"
        )

        pyautogui.moveTo(request.x, request.y, duration=request.duration)

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "coordinates": {"x": request.x, "y": request.y},
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Mouse move error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drag")
@log_api_request(logger)
async def execute_mouse_drag(request: MouseDragRequest):
    """Perform mouse drag from start to end position"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(
            f"🖱️ Dragging from ({request.startX}, {request.startY}) to ({request.endX}, {request.endY})"
        )

        # Move to start position
        pyautogui.moveTo(request.startX, request.startY, duration=0.1)

        # Perform drag
        pyautogui.drag(
            request.endX - request.startX,
            request.endY - request.startY,
            duration=request.duration,
            button=request.button,
        )

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "start": {"x": request.startX, "y": request.startY},
                "end": {"x": request.endX, "y": request.endY},
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Mouse drag error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scroll")
@log_api_request(logger)
async def execute_scroll(request: ScrollRequest):
    """Perform scroll action"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(
            f"🖱️ Scrolling {request.amount} clicks {request.direction} at ({request.x}, {request.y})"
        )

        # Move to position if specified
        if request.x is not None and request.y is not None:
            pyautogui.moveTo(request.x, request.y, duration=0.1)

        # Perform scroll
        if request.direction == "horizontal":
            pyautogui.hscroll(request.amount)
        else:
            pyautogui.scroll(request.amount)

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "amount": request.amount,
                "direction": request.direction,
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Scroll error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Keyboard Action Endpoints
# ============================================================


@router.post("/type")
@log_api_request(logger)
async def execute_type_text(request: TypeTextRequest):
    """Type text string"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(
            f"⌨️ Typing text: '{request.text[:30]}...' (interval={request.interval}s)"
        )

        pyautogui.write(request.text, interval=request.interval)

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "text_length": len(request.text),
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Type text error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/key")
@log_api_request(logger)
async def execute_key_press(request: KeyPressRequest):
    """Press a single key with optional modifiers"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(f"⌨️ Pressing key: {request.key} (modifiers={request.modifiers})")

        if request.modifiers:
            # Use hotkey for key with modifiers
            keys = request.modifiers + [request.key]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(request.key)

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "key": request.key,
                "modifiers": request.modifiers,
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Key press error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hotkey")
@log_api_request(logger)
async def execute_hotkey(request: HotkeyRequest):
    """Execute hotkey combination (e.g., Ctrl+C, Alt+Tab)"""
    import time

    start_time = time.time()

    try:
        import pyautogui

        logger.info(f"⌨️ Pressing hotkey: {'+'.join(request.keys)}")

        pyautogui.hotkey(*request.keys)

        execution_time = time.time() - start_time

        return JSONResponse(
            content={
                "success": True,
                "keys": request.keys,
                "execution_time": execution_time,
            }
        )

    except ImportError:
        logger.error("pyautogui not available")
        raise HTTPException(status_code=503, detail="pyautogui not available")
    except Exception as e:
        logger.error(f"Hotkey error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
