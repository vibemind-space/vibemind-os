"""Live Desktop Service for TRAE Backend

Provides desktop streaming, screenshot capture, and automation capabilities
for the Live Desktop System integration.
"""

import asyncio
import base64
import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..logger_config import get_logger

logger = get_logger("desktop_service")


class LiveDesktopService:
    """Service for managing live desktop streaming and automation"""

    def __init__(self):
        self.initialized = False
        self.streaming_active = False
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self.stream_config = {
            "quality": "medium",
            "frame_rate": 30,
            "compression": "jpeg",
            "scale_factor": 1.0,
        }
        self.screenshot_cache: Optional[bytes] = None
        self.last_screenshot_time = 0
        self.screenshot_cache_duration = 1.0  # Cache for 1 second

        # Stream callbacks for WebSocket connections
        self.frame_callbacks: List[Callable[[bytes], None]] = []

    async def initialize(self):
        """Initialize the desktop service"""
        if self.initialized:
            logger.warning("⚠️ LiveDesktopService already initialized")
            return

        try:
            logger.info("🖥️ Initializing LiveDesktopService...")

            # Initialize desktop capture capabilities
            await self._initialize_desktop_capture()

            # Test screenshot capability
            test_screenshot = await self.take_screenshot()
            if test_screenshot:
                logger.info("✅ Desktop screenshot capability verified")
            else:
                logger.warning(
                    "⚠️ Desktop screenshot test failed, but service will continue"
                )

            self.initialized = True
            logger.info("✅ LiveDesktopService initialized successfully")

        except Exception as e:
            logger.error(f"❌ LiveDesktopService initialization failed: {e}")
            raise

    async def _initialize_desktop_capture(self):
        """Initialize desktop capture system"""
        try:
            # Try to import required libraries for desktop capture
            # Note: This is a placeholder - actual implementation would depend on
            # the specific desktop capture library being used (e.g., PIL, opencv, etc.)

            # For now, we'll use a mock implementation
            logger.info("🔧 Desktop capture system initialized (mock implementation)")

        except ImportError as e:
            logger.warning(f"⚠️ Desktop capture library not available: {e}")
            logger.info("ℹ️ Service will run in mock mode")

    def get_status(self) -> Dict[str, Any]:
        """Get current service status"""
        return {
            "initialized": self.initialized,
            "streaming_active": self.streaming_active,
            "connected_clients": len(self.connected_clients),
            "client_list": list(self.connected_clients.keys()),
            "stream_config": self.stream_config.copy(),
            "last_screenshot_time": self.last_screenshot_time,
            "frame_callbacks_count": len(self.frame_callbacks),
        }

    async def configure_streaming(self, config: Dict[str, Any]) -> bool:
        """Configure streaming parameters"""
        try:
            logger.info(f"🔧 Configuring streaming with: {config}")

            # Validate and update configuration
            if "quality" in config and config["quality"] in ["low", "medium", "high"]:
                self.stream_config["quality"] = config["quality"]

            if "frame_rate" in config and 1 <= config["frame_rate"] <= 60:
                self.stream_config["frame_rate"] = config["frame_rate"]

            if "compression" in config and config["compression"] in [
                "jpeg",
                "png",
                "webp",
            ]:
                self.stream_config["compression"] = config["compression"]

            if "scale_factor" in config and 0.1 <= config["scale_factor"] <= 2.0:
                self.stream_config["scale_factor"] = config["scale_factor"]

            logger.info(f"✅ Streaming configuration updated: {self.stream_config}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to configure streaming: {e}")
            return False

    async def take_screenshot(
        self, encode_base64: bool = False
    ) -> Optional[str | bytes]:
        """Take a screenshot of the desktop"""
        try:
            current_time = time.time()

            # Use cached screenshot if recent enough
            if (
                self.screenshot_cache
                and current_time - self.last_screenshot_time
                < self.screenshot_cache_duration
            ):
                logger.debug("📸 Using cached screenshot")
                if encode_base64:
                    return base64.b64encode(self.screenshot_cache).decode("utf-8")
                return self.screenshot_cache

            # Take new screenshot
            screenshot_data = await self._capture_desktop()

            if screenshot_data:
                self.screenshot_cache = screenshot_data
                self.last_screenshot_time = current_time

                logger.debug(f"📸 Screenshot captured: {len(screenshot_data)} bytes")

                if encode_base64:
                    return base64.b64encode(screenshot_data).decode("utf-8")
                return screenshot_data

            logger.warning("⚠️ Screenshot capture returned no data")
            return None

        except Exception as e:
            logger.error(f"❌ Screenshot capture failed: {e}")
            return None

    async def _capture_desktop(self) -> Optional[bytes]:
        """Capture desktop screenshot using mss (real screen capture)."""
        try:
            import io
            import mss
            from PIL import Image

            loop = asyncio.get_event_loop()

            def _grab():
                with mss.mss() as sct:
                    # Grab the primary monitor (index 1); index 0 is "all monitors combined"
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    # Convert to PIL Image using .rgb (already in RGB byte order)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=70)
                    result = buf.getvalue()
                    logger.debug(
                        f"📸 Captured {sct_img.size.width}x{sct_img.size.height} → {len(result)} bytes JPEG"
                    )
                    return result

            return await loop.run_in_executor(None, _grab)

        except Exception as e:
            logger.error(f"❌ Desktop capture failed: {e}", exc_info=True)
            return None

    async def start_streaming(
        self, client_id: str, client_info: Dict[str, Any], monitor_id: str = "monitor_0"
    ) -> bool:
        """Start desktop streaming for a client on a specific monitor

        Args:
            client_id: Unique identifier for the client
            client_info: Arbitrary info about the client
            monitor_id: Target monitor identifier (e.g., 'monitor_0')
        """
        try:
            logger.info(
                f"🎬 Starting desktop streaming for client: {client_id} on monitor: {monitor_id}"
            )

            # Register or update client
            self.connected_clients[client_id] = {
                "client_info": client_info,
                "connected_at": datetime.now().isoformat(),
                "stream_active": True,
                "monitor_id": monitor_id,
            }

            # Start streaming if not already active
            if not self.streaming_active:
                await self._start_stream_loop()

            logger.info(
                f"✅ Desktop streaming started for client: {client_id} on {monitor_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"❌ Failed to start streaming for client {client_id} on {monitor_id}: {e}"
            )
            return False

    async def stop_streaming(
        self, client_id: str, monitor_id: Optional[str] = None
    ) -> bool:
        """Stop desktop streaming for a client

        Args:
            client_id: Unique client identifier
            monitor_id: Optional monitor identifier (ignored for now, kept for API compatibility)
        """
        try:
            logger.info(
                f"🛑 Stopping desktop streaming for client: {client_id}{' on ' + monitor_id if monitor_id else ''}"
            )

            # Remove client if exists
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]

            # Stop streaming loop if there are no clients left
            if not self.connected_clients:
                await self._stop_stream_loop()

            logger.info(
                f"✅ Desktop streaming stopped for client: {client_id}{' on ' + monitor_id if monitor_id else ''}"
            )
            return True

        except Exception as e:
            logger.error(
                f"❌ Failed to stop streaming for client {client_id}{' on ' + monitor_id if monitor_id else ''}: {e}"
            )
            return False

    async def _start_stream_loop(self):
        """Start the streaming loop"""
        if self.streaming_active:
            return

        self.streaming_active = True
        logger.info("🎬 Starting desktop stream loop")

        # Start streaming task
        asyncio.create_task(self._stream_loop())

    async def _stop_stream_loop(self):
        """Stop the streaming loop"""
        self.streaming_active = False
        logger.info("🛑 Desktop stream loop stopped")

    async def _stream_loop(self):
        """Main streaming loop"""
        frame_interval = 1.0 / self.stream_config["frame_rate"]

        while self.streaming_active and self.connected_clients:
            try:
                # Capture frame
                frame_data = await self.take_screenshot()

                if frame_data and self.frame_callbacks:
                    # Send frame to all registered callbacks
                    for callback in self.frame_callbacks:
                        try:
                            callback(frame_data)
                        except Exception as e:
                            logger.error(f"❌ Frame callback error: {e}")

                # Wait for next frame
                await asyncio.sleep(frame_interval)

            except Exception as e:
                logger.error(f"❌ Stream loop error: {e}")
                await asyncio.sleep(1.0)  # Error recovery delay

        self.streaming_active = False
        logger.info("🏁 Stream loop ended")

    def add_frame_callback(self, callback: Callable[[bytes], None]):
        """Add a callback for frame data"""
        self.frame_callbacks.append(callback)
        logger.debug(f"📡 Frame callback added, total: {len(self.frame_callbacks)}")

    def remove_frame_callback(self, callback: Callable[[bytes], None]):
        """Remove a frame callback"""
        if callback in self.frame_callbacks:
            self.frame_callbacks.remove(callback)
            logger.debug(
                f"📡 Frame callback removed, total: {len(self.frame_callbacks)}"
            )

    async def get_screen_info(self) -> Dict[str, Any]:
        """Get screen information"""
        try:
            # Mock screen information - in real implementation,
            # this would query actual screen properties
            screen_info = {
                "screens": [
                    {
                        "id": 0,
                        "primary": True,
                        "width": 1920,
                        "height": 1080,
                        "x": 0,
                        "y": 0,
                        "scale_factor": 1.0,
                    }
                ],
                "total_width": 1920,
                "total_height": 1080,
                "capture_available": True,
            }

            logger.debug(f"📺 Screen info: {screen_info}")
            return screen_info

        except Exception as e:
            logger.error(f"❌ Failed to get screen info: {e}")
            return {"error": str(e), "capture_available": False}

    async def get_available_monitors(self) -> List[Dict[str, Any]]:
        """Get list of available desktop monitors/clients for streaming

        Returns:
            List of available monitors with their metadata
        """
        try:
            logger.debug("🖥️ Getting available monitors for desktop streaming...")

            # In a real implementation, this would query actual monitor information
            # For now, we'll return mock data based on common multi-monitor setups
            monitors = [
                {
                    "id": "monitor_0",
                    "name": "Primary Monitor",
                    "status": "available",
                    "resolution": {"width": 1920, "height": 1080},
                    "isPrimary": True,
                    "x": 0,
                    "y": 0,
                    "scale_factor": 1.0,
                    "streaming": False,
                },
                {
                    "id": "monitor_1",
                    "name": "Secondary Monitor",
                    "status": "available",
                    "resolution": {"width": 1920, "height": 1080},
                    "isPrimary": False,
                    "x": 1920,
                    "y": 0,
                    "scale_factor": 1.0,
                    "streaming": False,
                },
            ]

            # Update streaming status based on connected clients
            for monitor in monitors:
                monitor_id = monitor["id"]
                # Check if any client is streaming from this monitor
                monitor["streaming"] = any(
                    client_info.get("stream_active", False)
                    and client_info.get("monitor_id") == monitor_id
                    for client_info in self.connected_clients.values()
                )

            logger.info(f"✅ Found {len(monitors)} available monitors")
            return monitors

        except Exception as e:
            logger.error(f"❌ Failed to get available monitors: {e}")
            # Return empty list on error to avoid breaking the WebSocket handler
            return []

    async def cleanup(self):
        """Cleanup the desktop service"""
        logger.info("🧹 Cleaning up LiveDesktopService...")

        try:
            # Stop streaming
            self.streaming_active = False

            # Clear connected clients
            self.connected_clients.clear()

            # Clear callbacks
            self.frame_callbacks.clear()

            # Clear cache
            self.screenshot_cache = None

            self.initialized = False
            logger.info("✅ LiveDesktopService cleanup completed")

        except Exception as e:
            logger.error(f"❌ LiveDesktopService cleanup error: {e}")
            raise


# Global service instance
_desktop_service_instance = None


def get_desktop_service() -> LiveDesktopService:
    """Get desktop service instance (singleton pattern)."""
    global _desktop_service_instance
    if _desktop_service_instance is None:
        _desktop_service_instance = LiveDesktopService()
    return _desktop_service_instance
