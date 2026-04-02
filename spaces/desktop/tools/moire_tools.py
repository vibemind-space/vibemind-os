"""
Moire Server Tools for VibeMind Voice Dialog

Direct integration with MoireServer (WebSocket) for advanced OCR and UI detection.
Provides higher quality UI context than local pytesseract OCR.

Tools:
- moire_scan - Full screen OCR via MoireServer
- moire_find_element - Find UI element by description
- moire_get_ui_context - Get structured UI tree with all elements

Prerequisites:
- MoireServer running on ws://localhost:8766
- Start with: cd MoireTracker_v2 && npm start
"""

import asyncio
import logging
import json
import time
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import websockets
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    logger.warning("websockets not available. Install with: pip install websockets")
    HAS_WEBSOCKETS = False


@dataclass
class UIElement:
    """A detected UI element with OCR text and coordinates."""
    id: str
    text: Optional[str]
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    confidence: float
    category: Optional[str] = None


@dataclass
class ScanResult:
    """Result from MoireServer scan."""
    success: bool
    elements: List[UIElement]
    screenshot_base64: Optional[str]
    processing_time_ms: float
    error: Optional[str] = None


class MoireServerClient:
    """
    WebSocket client for MoireServer.

    Provides direct access to MoireServer's detection and OCR capabilities.
    """

    def __init__(self, host: str = "localhost", port: int = 8766):
        self.uri = f"ws://{host}:{port}"
        self.websocket = None
        self.is_connected = False
        self._current_context = None
        self._screenshot = None
        self._capture_event = None  # Created lazily in connect()
        self._receiver_task = None

    async def connect(self) -> bool:
        """Connect to MoireServer."""
        if not HAS_WEBSOCKETS:
            logger.error("websockets not installed")
            return False

        try:
            # Create event in current loop (fixes "bound to different event loop" error)
            self._capture_event = asyncio.Event()

            self.websocket = await websockets.connect(
                self.uri,
                ping_interval=15,
                ping_timeout=30,
                max_size=50 * 1024 * 1024  # 50MB for screenshots
            )
            self.is_connected = True

            # Send handshake
            await self.websocket.send(json.dumps({"type": "handshake"}))

            # Start receiver
            self._receiver_task = asyncio.create_task(self._receive_messages())

            logger.info(f"Connected to MoireServer at {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MoireServer: {e}")
            self.is_connected = False
            return False

    async def disconnect(self):
        """Disconnect from MoireServer."""
        self.is_connected = False
        if self._receiver_task:
            self._receiver_task.cancel()
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def _receive_messages(self):
        """Background task to receive messages from server."""
        try:
            while self.is_connected and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=60.0
                    )
                    data = json.loads(message)
                    await self._handle_message(data)
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self.is_connected = False

    async def _handle_message(self, msg: Dict[str, Any]):
        """Handle incoming messages from MoireServer."""
        msg_type = msg.get("type")

        if msg_type == "moire_detection_result":
            # Full detection result with boxes and OCR
            boxes = msg.get("boxes", [])
            self._screenshot = msg.get("backgroundImage")

            elements = []
            for box in boxes:
                x = box.get("x", 0)
                y = box.get("y", 0)
                w = box.get("width", 0)
                h = box.get("height", 0)

                elements.append(UIElement(
                    id=box.get("id", ""),
                    text=box.get("text"),
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    center_x=x + w // 2,
                    center_y=y + h // 2,
                    confidence=box.get("confidence", 0.5),
                    category=box.get("category")
                ))

            self._current_context = elements
            self._capture_event.set()
            logger.info(f"Received {len(elements)} UI elements from MoireServer")

        elif msg_type in ["state_changed", "state_change"]:
            # State update with UI context
            ui_context = msg.get("uiContext", {})
            elements = []

            for elem in ui_context.get("elements", []):
                bounds = elem.get("bounds", {})
                center = elem.get("center", {})

                elements.append(UIElement(
                    id=elem.get("id", ""),
                    text=elem.get("text"),
                    x=bounds.get("x", 0),
                    y=bounds.get("y", 0),
                    width=bounds.get("width", 0),
                    height=bounds.get("height", 0),
                    center_x=center.get("x", 0),
                    center_y=center.get("y", 0),
                    confidence=elem.get("confidence", 0.5),
                    category=elem.get("category")
                ))

            self._current_context = elements
            self._capture_event.set()

    async def capture(self, timeout: float = 30.0) -> ScanResult:
        """
        Trigger capture and wait for results.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            ScanResult with detected elements
        """
        if not self.is_connected:
            if not await self.connect():
                return ScanResult(
                    success=False,
                    elements=[],
                    screenshot_base64=None,
                    processing_time_ms=0,
                    error="Not connected to MoireServer"
                )

        start = time.time()
        self._capture_event.clear()

        try:
            # Request scan
            await self.websocket.send(json.dumps({"type": "scan_desktop"}))

            # Wait for response
            await asyncio.wait_for(self._capture_event.wait(), timeout=timeout)

            processing_time_ms = (time.time() - start) * 1000

            return ScanResult(
                success=True,
                elements=self._current_context or [],
                screenshot_base64=self._screenshot,
                processing_time_ms=processing_time_ms
            )
        except asyncio.TimeoutError:
            return ScanResult(
                success=False,
                elements=[],
                screenshot_base64=None,
                processing_time_ms=(time.time() - start) * 1000,
                error=f"Timeout after {timeout}s"
            )
        except Exception as e:
            return ScanResult(
                success=False,
                elements=[],
                screenshot_base64=None,
                processing_time_ms=(time.time() - start) * 1000,
                error=str(e)
            )

    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find element by matching text."""
        if not self._current_context:
            return None

        text_lower = text.lower()
        for elem in self._current_context:
            if elem.text:
                if exact and elem.text == text:
                    return elem
                elif not exact and text_lower in elem.text.lower():
                    return elem
        return None

    def get_all_texts(self) -> List[str]:
        """Get all recognized texts."""
        if not self._current_context:
            return []
        return [elem.text for elem in self._current_context if elem.text]


# Singleton client (for direct async usage)
_moire_client: Optional[MoireServerClient] = None


def get_moire_client() -> MoireServerClient:
    """Get singleton MoireServer client (for test scripts only)."""
    global _moire_client
    if _moire_client is None:
        _moire_client = MoireServerClient()
    return _moire_client


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

async def moire_scan(timeout: float = 30.0) -> Dict[str, Any]:
    """
    Capture screen and run OCR via MoireServer.

    Returns full UI context with all detected elements and their text.

    Args:
        timeout: Maximum wait time in seconds

    Returns:
        Dict with texts, elements, and metadata
    """
    # Create fresh client to avoid event loop binding issues
    client = MoireServerClient()

    try:
        result = await client.capture(timeout=timeout)

        if result.success:
            texts = [e.text for e in result.elements if e.text]
            # Limit to top 20 unique texts to avoid overwhelming the voice response
            unique_texts = list(dict.fromkeys(texts))[:20]

            return {
                "success": True,
                "texts": unique_texts,
                "text_count": len(texts),
                "element_count": len(result.elements),
                "sample_elements": [
                    {"text": e.text, "x": e.center_x, "y": e.center_y}
                    for e in result.elements if e.text
                ][:10],  # Only first 10 elements
                "processing_time_ms": round(result.processing_time_ms, 1)
            }
        else:
            return {
                "success": False,
                "error": result.error,
                "message": "MoireServer scan failed. Is MoireServer running on port 8766?"
            }
    except Exception as e:
        logger.error(f"moire_scan failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await client.disconnect()


async def moire_find_element(description: str, scan_if_needed: bool = True) -> Dict[str, Any]:
    """
    Find a UI element by description/text.

    Uses MoireServer's OCR to locate the element and returns clickable coordinates.

    Args:
        description: Text or description to search for
        scan_if_needed: If True, trigger new scan if no context available

    Returns:
        Dict with element location and details
    """
    # Create fresh client to avoid event loop binding issues
    client = MoireServerClient()

    try:
        # Always scan to get current context
        result = await client.capture(timeout=30.0)
        if not result.success:
            return {
                "success": False,
                "found": False,
                "error": result.error
            }

        # Search for element
        element = client.find_element_by_text(description, exact=False)

        if element:
            return {
                "success": True,
                "found": True,
                "text": element.text,
                "x": element.center_x,
                "y": element.center_y,
                "message": f"Found '{element.text}' at ({element.center_x}, {element.center_y})"
            }
        else:
            return {
                "success": True,
                "found": False,
                "message": f"Element '{description}' not found. Available texts: {client.get_all_texts()[:10]}"
            }
    except Exception as e:
        logger.error(f"moire_find_element failed: {e}")
        return {"success": False, "found": False, "error": str(e)}
    finally:
        await client.disconnect()


async def moire_get_ui_context() -> Dict[str, Any]:
    """
    Get the full structured UI context from MoireServer.

    Returns all detected elements organized by regions and categories.

    Returns:
        Dict with complete UI tree
    """
    # Create fresh client to avoid event loop binding issues
    client = MoireServerClient()

    try:
        result = await client.capture(timeout=30.0)

        if result.success:
            # Group by category (limit to avoid large payloads)
            by_category = {}
            for elem in result.elements:
                cat = elem.category or "unknown"
                if cat not in by_category:
                    by_category[cat] = []
                # Max 5 elements per category
                if len(by_category[cat]) < 5:
                    by_category[cat].append({
                        "text": elem.text,
                        "x": elem.center_x,
                        "y": elem.center_y
                    })

            # Limit to 3 categories with most elements
            sorted_cats = sorted(by_category.items(), key=lambda x: len(x[1]), reverse=True)[:3]
            limited_categories = dict(sorted_cats)

            # Limit texts to 15
            all_texts = client.get_all_texts()[:15]

            return {
                "success": True,
                "total_elements": len(result.elements),
                "with_text": len([e for e in result.elements if e.text]),
                "categories": list(by_category.keys()),  # Just category names
                "sample_by_category": limited_categories,  # Top 3 categories, 5 elements each
                "sample_texts": all_texts,  # Limited to 15
                "processing_time_ms": round(result.processing_time_ms, 1)
            }
        else:
            return {"success": False, "error": result.error}
    except Exception as e:
        logger.error(f"moire_get_ui_context failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await client.disconnect()


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

MOIRE_TOOLS = [
    {
        "name": "moire_scan",
        "description": "Capture screen and run OCR using MoireServer. Returns all visible text and UI elements. Better quality than local OCR.",
        "parameters": {
            "type": "object",
            "properties": {
                "timeout": {"type": "number", "default": 30.0, "description": "Max wait time in seconds"}
            },
            "required": []
        }
    },
    {
        "name": "moire_find_element",
        "description": "Find a UI element by text using MoireServer OCR. Returns clickable coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Text to search for on screen"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "moire_get_ui_context",
        "description": "Get complete UI context with all elements organized by category. Useful for understanding current screen state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


# =============================================================================
# REGISTRATION
# =============================================================================

def register_moire_tools(tools_manager) -> None:
    """
    Register Moire Server tools with the ClientToolsManager.

    Args:
        tools_manager: ClientToolsManager instance
    """
    print("Registering Moire Server tools...")

    def create_wrapper(async_func):
        def wrapper(params):
            import asyncio
            # Filter out tool_call_id - voice layer passes it but our functions don't need it
            filtered_params = {k: v for k, v in params.items() if k != 'tool_call_id'}
            try:
                # Try to get existing event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in a running loop, we need to run in a new thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        def run_in_new_loop():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                return new_loop.run_until_complete(async_func(**filtered_params))
                            finally:
                                new_loop.close()
                        future = executor.submit(run_in_new_loop)
                        return future.result(timeout=60)
                except RuntimeError:
                    # No running loop - we can use asyncio.run() directly
                    # But first ensure we have an event loop for this thread
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_closed():
                            raise RuntimeError("Loop is closed")
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    return asyncio.run(async_func(**filtered_params))
            except Exception as e:
                logger.error(f"Moire tool wrapper error: {e}")
                return {"success": False, "error": str(e)}
        return wrapper

    tools_manager.register_with_observer("moire_scan", create_wrapper(
        lambda timeout=30.0: moire_scan(timeout)
    ))
    print("  - moire_scan")

    tools_manager.register_with_observer("moire_find_element", create_wrapper(
        lambda description, scan_if_needed=True: moire_find_element(description, scan_if_needed)
    ))
    print("  - moire_find_element")

    tools_manager.register_with_observer("moire_get_ui_context", create_wrapper(
        lambda: moire_get_ui_context()
    ))
    print("  - moire_get_ui_context")

    print(f"Moire Server tools registered ({len(MOIRE_TOOLS)} tools)")


# =============================================================================
# TEST
# =============================================================================

async def test_moire_tools():
    """Test Moire Server tools."""
    logger.debug("test_moire_tools called")
    print("Testing Moire Server Tools...")
    print(f"  websockets available: {HAS_WEBSOCKETS}")

    # Test scan
    print("\nTesting moire_scan...")
    result = await moire_scan(timeout=30.0)

    if result["success"]:
        print(f"  Found {result['text_count']} texts, {result['element_count']} elements")
        print(f"  Sample texts: {result['texts'][:5]}")
    else:
        print(f"  Error: {result.get('error')}")

    # Test find element
    print("\nTesting moire_find_element('Start')...")
    result = await moire_find_element("Start")
    print(f"  Result: {result}")

    print("\nMoire tools test completed")


if __name__ == "__main__":
    asyncio.run(test_moire_tools())
