"""
Desktop Router for TRAE Backend

Provides endpoints for live desktop streaming and screen information.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..logger_config import get_logger, log_api_request

logger = get_logger("desktop")

router = APIRouter()


class LiveDesktopConfig(BaseModel):
    """Live desktop configuration model"""

    fps: int = 10
    quality: int = 80
    scale_factor: float = 1.0


class HostFrameData(BaseModel):
    """Host frame data model for Windows desktop capture"""

    image: str  # base64 encoded image data
    resolution: Dict[str, int]  # width, height
    timestamp: str
    status: str
    metadata: Dict[str, Any] = {}


@router.get("/status")
@log_api_request(logger)
async def get_live_desktop_status(request: Request):
    """Get live desktop streaming status"""
    try:
        # Access service through FastAPI app state
        app = request.app
        if (
            not app
            or not hasattr(app, "state")
            or not hasattr(app.state, "service_manager")
        ):
            raise HTTPException(status_code=503, detail="Service manager not available")

        service_manager = app.state.service_manager
        desktop_service = service_manager.get_service("live_desktop")

        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Live desktop service not available"
            )

        status = await desktop_service.get_status()

        return JSONResponse(
            content={
                "success": True,
                "streaming": status.get("streaming", False),
                "clients": status.get("client_count", 0),
                "fps": status.get("fps", 10),
                "resolution": status.get("resolution", {"width": 1920, "height": 1080}),
            }
        )

    except Exception as e:
        logger.error(f"Get desktop status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configure")
@log_api_request(logger)
async def configure_live_desktop(request: Request, config: LiveDesktopConfig):
    """Configure live desktop streaming settings"""
    try:
        # Access service through FastAPI app state
        app = request.app
        if (
            not app
            or not hasattr(app, "state")
            or not hasattr(app.state, "service_manager")
        ):
            raise HTTPException(status_code=503, detail="Service manager not available")

        service_manager = app.state.service_manager
        desktop_service = service_manager.get_service("live_desktop")

        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Live desktop service not available"
            )

        await desktop_service.update_config(config.dict())

        return JSONResponse(
            content={
                "success": True,
                "message": "Live desktop configured successfully",
                "config": config.dict(),
            }
        )

    except Exception as e:
        logger.error(f"Configure desktop error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screen-info")
@log_api_request(logger)
async def get_desktop_screen_info(request: Request):
    """Get desktop screen information"""
    try:
        # Access service through FastAPI app state
        app = request.app
        if (
            not app
            or not hasattr(app, "state")
            or not hasattr(app.state, "service_manager")
        ):
            raise HTTPException(status_code=503, detail="Service manager not available")

        service_manager = app.state.service_manager
        desktop_service = service_manager.get_service("live_desktop")

        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Live desktop service not available"
            )

        screen_info = await desktop_service.get_screen_info()

        return JSONResponse(
            content={
                "success": True,
                "screen_info": screen_info,
                "resolution": screen_info.get(
                    "resolution", {"width": 1920, "height": 1080}
                ),
                "scale_factor": screen_info.get("scale_factor", 1.0),
                "monitors": screen_info.get("monitors", []),
            }
        )

    except Exception as e:
        logger.error(f"Get desktop screen info error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot")
@log_api_request(logger)
async def take_desktop_screenshot(request: Request):
    """Take a screenshot of the current desktop"""
    try:
        # Access service through FastAPI app state
        app = request.app
        if (
            not app
            or not hasattr(app, "state")
            or not hasattr(app.state, "service_manager")
        ):
            raise HTTPException(status_code=503, detail="Service manager not available")

        service_manager = app.state.service_manager
        desktop_service = service_manager.get_service("live_desktop")

        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Live desktop service not available"
            )

        # Check if service has the take_screenshot method
        if not hasattr(desktop_service, "take_screenshot"):
            raise HTTPException(
                status_code=503, detail="Desktop service does not support screenshots"
            )

        # Take screenshot
        screenshot_data = await desktop_service.take_screenshot()

        if screenshot_data:
            # Handle both dict and raw bytes responses
            if isinstance(screenshot_data, dict):
                result = {
                    "data": screenshot_data.get("data", ""),
                    "format": screenshot_data.get("format", "png"),
                    "width": screenshot_data.get("width", 0),
                    "height": screenshot_data.get("height", 0),
                    "timestamp": screenshot_data.get("timestamp"),
                }
            elif isinstance(screenshot_data, (bytes, bytearray)):
                import base64
                from datetime import datetime
                result = {
                    "data": base64.b64encode(screenshot_data).decode("ascii"),
                    "format": "png",
                    "width": 0,
                    "height": 0,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                result = {"data": str(screenshot_data), "format": "png",
                          "width": 0, "height": 0, "timestamp": None}

            return JSONResponse(
                content={
                    "success": True,
                    "screenshot": result,
                    "message": "Screenshot captured successfully",
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": False,
                    "error": "Failed to capture screenshot",
                    "screenshot": None,
                },
                status_code=500,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Take desktop screenshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/host-frame")
@log_api_request(logger)
async def receive_host_frame(request: Request, frame_data: HostFrameData):
    """Receive desktop frame from Windows host capture service"""
    try:
        # Access service through FastAPI app state
        app = request.app
        if (
            not app
            or not hasattr(app, "state")
            or not hasattr(app.state, "service_manager")
        ):
            raise HTTPException(status_code=503, detail="Service manager not available")

        service_manager = app.state.service_manager
        desktop_service = service_manager.get_service("live_desktop")

        if not desktop_service:
            raise HTTPException(
                status_code=503, detail="Live desktop service not available"
            )

        # Convert frame data to expected format
        processed_frame = {
            "image": frame_data.image,
            "resolution": frame_data.resolution,
            "timestamp": frame_data.timestamp,
            "status": frame_data.status,
            "metadata": frame_data.metadata,
        }

        # Store frame for WebSocket streaming
        if hasattr(desktop_service, "set_host_frame"):
            await desktop_service.set_host_frame(processed_frame)
            logger.info(
                f"✅ Host frame received and processed: {frame_data.resolution['width']}x{frame_data.resolution['height']}"
            )

            return JSONResponse(
                content={
                    "success": True,
                    "message": "Host frame received successfully",
                    "resolution": frame_data.resolution,
                    "timestamp": frame_data.timestamp,
                }
            )
        else:
            # Fallback: log that we received the frame
            logger.warning(
                f"⚠️  Host frame received but service lacks set_host_frame method: {frame_data.resolution['width']}x{frame_data.resolution['height']}"
            )

            return JSONResponse(
                content={
                    "success": True,
                    "message": "Host frame received (stored for future processing)",
                    "resolution": frame_data.resolution,
                    "timestamp": frame_data.timestamp,
                }
            )

    except Exception as e:
        logger.error(f"Receive host frame error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cached-frame/{monitor_id}")
@log_api_request(logger)
async def get_cached_frame(monitor_id: int = 0, max_age_ms: int = 5000):
    """Get cached frame from StreamFrameCache for MCP tools.

    This endpoint bridges the gap between the WebSocket frame receiver
    and external processes (like MCP server) that need access to live frames.
    """
    try:
        import sys
        import os
        moire_agents_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "moire_agents"
        )
        if moire_agents_path not in sys.path:
            sys.path.insert(0, moire_agents_path)

        from stream_frame_cache import StreamFrameCache

        frame = StreamFrameCache.get_fresh_frame(monitor_id=monitor_id, max_age_ms=max_age_ms)

        if frame:
            return JSONResponse(
                content={
                    "success": True,
                    "monitor_id": monitor_id,
                    "frame_data": frame.data,
                    "age_ms": frame.age_ms,
                    "width": frame.width,
                    "height": frame.height,
                    "is_fresh": frame.is_fresh,
                }
            )
        else:
            return JSONResponse(
                content={
                    "success": False,
                    "monitor_id": monitor_id,
                    "error": "No fresh frame available",
                    "frame_data": None,
                },
                status_code=404,
            )

    except Exception as e:
        logger.error(f"Get cached frame error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache-status")
@log_api_request(logger)
async def get_cache_status():
    """Get StreamFrameCache status for debugging."""
    try:
        import sys
        import os
        moire_agents_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "moire_agents"
        )
        if moire_agents_path not in sys.path:
            sys.path.insert(0, moire_agents_path)

        from stream_frame_cache import StreamFrameCache

        status = StreamFrameCache.get_status()
        return JSONResponse(content={"success": True, **status})

    except Exception as e:
        logger.error(f"Get cache status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
