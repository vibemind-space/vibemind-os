"""
Vision Handoff Agent - Handles visual element detection

Concrete agent that finds UI elements via OCR and vision analysis.
Part of the handoff pattern multi-agent system.
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseHandoffAgent, AgentConfig
from .messages import UserTask, HandoffRequest

logger = logging.getLogger(__name__)


class VisionHandoffAgent(BaseHandoffAgent):
    """
    Agent that handles visual element detection.

    Capabilities:
    - Find elements by text (OCR)
    - Find elements by description (Vision API)
    - Validate screen state
    - Return coordinates for execution

    Integrates with MoireServer for OCR and vision analysis.
    """

    def __init__(
        self,
        moire_host: str = "localhost",
        moire_port: int = 8765
    ):
        """
        Initialize the vision agent.

        Args:
            moire_host: MoireServer host
            moire_port: MoireServer port
        """
        config = AgentConfig(
            name="vision",
            description="Finds UI elements via OCR and vision analysis",
            topic_type="vision",
            timeout=30.0
        )
        super().__init__(config)

        self.moire_host = moire_host
        self.moire_port = moire_port
        self._moire_client = None
        self._vision_agent = None

    def _register_default_tools(self):
        """Register delegate tools."""
        self.register_delegate_tool(
            name="return_to_orchestrator",
            target_agent="orchestrator",
            description="Return control with found element coordinates"
        )

        self.register_delegate_tool(
            name="delegate_to_execution",
            target_agent="execution",
            description="Send click action to execution agent"
        )

    async def _get_moire_client(self):
        """Get or create MoireServer client."""
        if self._moire_client is None:
            try:
                from bridge.websocket_client import MoireWebSocketClient
                self._moire_client = MoireWebSocketClient(
                    host=self.moire_host,
                    port=self.moire_port
                )
                await self._moire_client.connect()
            except Exception as e:
                logger.warning(f"Could not connect to MoireServer: {e}")
                self._moire_client = None

        return self._moire_client

    async def _get_vision_agent(self):
        """Get or create Vision Agent for Claude-based detection."""
        if self._vision_agent is None:
            try:
                from agents.vision_agent import VisionAnalystAgent
                self._vision_agent = VisionAnalystAgent()
            except Exception as e:
                logger.warning(f"Could not create VisionAgent: {e}")
                self._vision_agent = None

        return self._vision_agent

    async def _process_task(self, task: UserTask) -> Any:
        """
        Process a vision task.

        Expected context:
        - find_target: str - Text or description to find
        - find_method: str - "ocr", "vision", or "auto"
        - return_mode: str - "coordinates" or "execute_click"
        """
        target = task.context.get("find_target", "")
        method = task.context.get("find_method", "auto")
        return_mode = task.context.get("return_mode", "coordinates")

        if not target:
            return {"success": False, "error": "No find_target specified"}

        await self.report_progress(task, 25.0, f"Finding: {target}")

        # Try to find the element
        result = await self._find_element(target, method, task)

        if not result.get("found"):
            await self.report_progress(task, 100.0, f"Not found: {target}")

            # Return to orchestrator with failure
            task.context["vision_result"] = result
            return await self.hand_off_to(
                "orchestrator",
                task,
                reason=f"Element not found: {target}"
            )

        await self.report_progress(task, 75.0, f"Found at ({result['x']}, {result['y']})")

        # Handle based on return mode
        if return_mode == "execute_click":
            # Hand off to execution agent for click
            task.context["action"] = {
                "type": "click",
                "x": result["x"],
                "y": result["y"]
            }
            task.context["vision_result"] = result
            return await self.hand_off_to(
                "execution",
                task,
                reason=f"Click element: {target}"
            )
        else:
            # Return coordinates to orchestrator
            task.context["vision_result"] = result
            return await self.hand_off_to(
                "orchestrator",
                task,
                reason=f"Found element: {target}"
            )

    async def _find_element(
        self,
        target: str,
        method: str,
        task: UserTask
    ) -> Dict[str, Any]:
        """
        Find an element on screen.

        Args:
            target: Text or description to find
            method: "ocr", "vision", or "auto"
            task: Task context with optional screenshot

        Returns:
            Dict with found, x, y, confidence
        """
        # Try OCR first if method is "auto" or "ocr"
        if method in ("auto", "ocr"):
            ocr_result = await self._find_via_ocr(target, task)
            if ocr_result.get("found"):
                return ocr_result

        # Try vision if method is "auto" or "vision"
        if method in ("auto", "vision"):
            vision_result = await self._find_via_vision(target, task)
            if vision_result.get("found"):
                return vision_result

        # Fallback: center of screen
        if task.context.get("use_fallback", True):
            import pyautogui
            screen_width, screen_height = pyautogui.size()
            return {
                "found": True,
                "x": screen_width // 2,
                "y": int(screen_height * 0.85),
                "confidence": 0.3,
                "method": "fallback"
            }

        return {"found": False, "error": f"Could not find: {target}"}

    async def _find_via_ocr(
        self,
        target: str,
        task: UserTask
    ) -> Dict[str, Any]:
        """Find element using OCR via MoireServer."""
        try:
            client = await self._get_moire_client()
            if not client:
                return {"found": False, "error": "MoireServer not available"}

            # Capture screen
            result = await client.capture_and_wait_for_complete(timeout=10.0)

            if not result.success:
                return {"found": False, "error": "Screen capture failed"}

            # Search in OCR results
            element = client.find_element_by_text(target, exact=False)

            if element:
                x = element.center.get("x", 0)
                y = element.center.get("y", 0)
                return {
                    "found": True,
                    "x": x,
                    "y": y,
                    "confidence": 0.8,
                    "method": "ocr",
                    "text": element.text
                }

            return {"found": False, "method": "ocr"}

        except Exception as e:
            logger.error(f"OCR search failed: {e}")
            return {"found": False, "error": str(e)}

    async def _find_via_vision(
        self,
        target: str,
        task: UserTask
    ) -> Dict[str, Any]:
        """Find element using Claude Vision API."""
        try:
            vision_agent = await self._get_vision_agent()
            if not vision_agent:
                return {"found": False, "error": "Vision agent not available"}

            # Get screenshot
            screenshot_bytes = None

            # Try task screenshot first
            if task.screenshot_base64:
                screenshot_bytes = self._decode_base64(task.screenshot_base64)

            # Otherwise capture fresh
            if not screenshot_bytes:
                client = await self._get_moire_client()
                if client:
                    result = await client.capture_and_wait_for_complete(timeout=10.0)
                    if result.success and result.screenshot_base64:
                        screenshot_bytes = self._decode_base64(result.screenshot_base64)

            if not screenshot_bytes:
                return {"found": False, "error": "No screenshot available"}

            # Use vision agent to find element
            location = await vision_agent.find_element_from_screenshot(
                screenshot_bytes,
                target
            )

            if location.found:
                return {
                    "found": True,
                    "x": location.x,
                    "y": location.y,
                    "confidence": location.confidence,
                    "method": "vision"
                }

            return {"found": False, "method": "vision"}

        except Exception as e:
            logger.error(f"Vision search failed: {e}")
            return {"found": False, "error": str(e)}

    def _decode_base64(self, data: str) -> Optional[bytes]:
        """Decode base64 string, handling data URI prefix."""
        if not data:
            return None

        # Handle data URI prefix
        if ',' in data:
            data = data.split(',', 1)[1]

        # Fix padding
        missing = len(data) % 4
        if missing:
            data += '=' * (4 - missing)

        return base64.b64decode(data)

    async def stop(self):
        """Clean up resources."""
        if self._moire_client:
            await self._moire_client.disconnect()
            self._moire_client = None

        await super().stop()
