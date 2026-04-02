"""Click Automation Service for TRAE Backend

Provides click automation functionality using pyautogui.
"""

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

from ..logger_config import get_logger

logger = get_logger("click_automation_service")

try:
    import pyautogui

    # Disable pyautogui failsafe for automation
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    logger.warning("⚠️ pyautogui not available - click automation disabled")


class ClickAutomationService:
    """Service for performing automated clicks and mouse operations"""

    def __init__(self):
        self.initialized = False
        self.healthy = False

    async def initialize(self):
        """Initialize the click automation service"""
        try:
            logger.info("🔧 Initializing ClickAutomationService...")

            if not PYAUTOGUI_AVAILABLE:
                logger.error(
                    "❌ pyautogui not available - cannot initialize click automation"
                )
                self.initialized = False
                self.healthy = False
                return

            # Test basic functionality
            screen_size = pyautogui.size()
            logger.info(
                f"📺 Screen size detected: {screen_size.width}x{screen_size.height}"
            )

            self.initialized = True
            self.healthy = True
            logger.info("✅ ClickAutomationService initialized successfully")

        except Exception as e:
            logger.error(f"❌ ClickAutomationService initialization failed: {e}")
            self.initialized = False
            self.healthy = False
            raise

    def is_healthy(self) -> bool:
        """Check if the service is healthy"""
        return self.healthy and PYAUTOGUI_AVAILABLE

    def get_screen_size(self) -> Optional[Dict[str, int]]:
        """Get screen size"""
        if not PYAUTOGUI_AVAILABLE:
            return None

        try:
            size = pyautogui.size()
            return {"width": size.width, "height": size.height}
        except Exception as e:
            logger.error(f"❌ Error getting screen size: {e}")
            return None

    async def perform_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        click_type: str = "single",
        delay: float = 0.1,
    ) -> Dict[str, Any]:
        """Perform automated click"""
        start_time = time.time()

        try:
            if not self.is_healthy():
                return {
                    "success": False,
                    "clicked": False,
                    "error": "Click automation service not healthy",
                    "execution_time": 0,
                }

            logger.info(
                f"🖱️ Performing {click_type} {button} click at ({x}, {y}) with delay {delay}s"
            )

            # Validate coordinates
            screen_size = self.get_screen_size()
            if screen_size:
                if (
                    x < 0
                    or x > screen_size["width"]
                    or y < 0
                    or y > screen_size["height"]
                ):
                    logger.warning(
                        f"⚠️ Click coordinates ({x}, {y}) outside screen bounds {screen_size}"
                    )

            # Add delay before click
            if delay > 0:
                await asyncio.sleep(delay)

            # Perform click based on type
            if click_type == "double":
                pyautogui.doubleClick(x, y, button=button)
            else:  # single click
                pyautogui.click(x, y, button=button)

            execution_time = time.time() - start_time

            logger.info(f"✅ Click executed successfully in {execution_time:.3f}s")

            return {
                "success": True,
                "clicked": True,
                "coordinates": {"x": x, "y": y},
                "button": button,
                "click_type": click_type,
                "execution_time": execution_time,
            }

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Click execution failed: {e}")

            return {
                "success": False,
                "clicked": False,
                "error": str(e),
                "execution_time": execution_time,
            }

    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        return {
            "initialized": self.initialized,
            "healthy": self.healthy,
            "pyautogui_available": PYAUTOGUI_AVAILABLE,
            "screen_size": self.get_screen_size(),
        }

    async def cleanup(self):
        """Cleanup the service"""
        logger.info("🧹 Cleaning up ClickAutomationService...")
        self.initialized = False
        self.healthy = False
        logger.info("✅ ClickAutomationService cleanup completed")
