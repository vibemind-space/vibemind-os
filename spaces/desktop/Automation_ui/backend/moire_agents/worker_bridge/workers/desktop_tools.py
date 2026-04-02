"""
Desktop Tools für MoireTracker Tool-Using Agents

Definiert:
1. DESKTOP_TOOLS - Tool-Definitionen für LLM Function-Calling
2. SizeValidator - Validiert LLM Size-Parameter gegen UI-Element-Bounds
3. DesktopToolExecutor - Führt Tools aus mit Size-Validation und Reporting
"""

import asyncio
import base64
import io
import logging
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# PIL für Screenshot-Capture
try:
    from PIL import Image, ImageGrab, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logging.warning("PIL not available. Run: pip install Pillow")

# Import Messages
from worker_bridge.messages import (
    ToolName,
    ExecutionStatus,
    SizeValidationResult,
    SizeValidationReport,
    ToolExecutionResult
)

# Import InteractionAgent
try:
    from agents.interaction import InteractionAgent, get_interaction_agent
    HAS_INTERACTION = True
except ImportError:
    HAS_INTERACTION = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Tool Definitions ====================

DESKTOP_TOOLS = {
    ToolName.CAPTURE_SCREENSHOT_REGION: {
        "name": "capture_screenshot_region",
        "description": "Captures a screenshot of a specific region for context and validation. Use this before and after actions to verify success.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate of top-left corner"},
                "y": {"type": "integer", "description": "Y coordinate of top-left corner"},
                "width": {"type": "integer", "description": "Width of region (minimum 50px)", "minimum": 50},
                "height": {"type": "integer", "description": "Height of region (minimum 50px)", "minimum": 50},
                "target_element": {"type": "string", "description": "Optional: Element ID for size validation"}
            },
            "required": ["x", "y", "width", "height"]
        },
        "returns": "Base64-encoded PNG image of the captured region"
    },
    
    ToolName.CLICK_AT_POSITION: {
        "name": "click_at_position",
        "description": "Clicks at specified screen coordinates. Use for buttons, links, and interactive elements.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate to click"},
                "y": {"type": "integer", "description": "Y coordinate to click"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "default": 1, "minimum": 1, "maximum": 3}
            },
            "required": ["x", "y"]
        },
        "returns": "Action result with success status"
    },
    
    ToolName.DOUBLE_CLICK: {
        "name": "double_click",
        "description": "Double-clicks at specified screen coordinates. Use for opening files or selecting words.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"}
            },
            "required": ["x", "y"]
        },
        "returns": "Action result with success status"
    },
    
    ToolName.RIGHT_CLICK: {
        "name": "right_click",
        "description": "Right-clicks at specified screen coordinates. Use for context menus.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"}
            },
            "required": ["x", "y"]
        },
        "returns": "Action result with success status"
    },
    
    ToolName.TYPE_TEXT: {
        "name": "type_text",
        "description": "Types text at current cursor position. Supports Unicode via clipboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "use_clipboard": {"type": "boolean", "default": True, "description": "Use clipboard for Unicode support"}
            },
            "required": ["text"]
        },
        "returns": "Action result with characters typed"
    },
    
    ToolName.PRESS_KEY: {
        "name": "press_key",
        "description": "Presses a single key. Use for Enter, Tab, Escape, arrow keys, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name (enter, tab, escape, up, down, left, right, space, backspace, delete, home, end, pageup, pagedown, f1-f12, win)"},
                "presses": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10}
            },
            "required": ["key"]
        },
        "returns": "Action result"
    },
    
    ToolName.HOTKEY: {
        "name": "hotkey",
        "description": "Presses a keyboard shortcut. Use for Ctrl+C, Alt+Tab, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keys to press together, e.g., ['ctrl', 'c'] or ['alt', 'tab']"
                }
            },
            "required": ["keys"]
        },
        "returns": "Action result"
    },
    
    ToolName.SCROLL: {
        "name": "scroll",
        "description": "Scrolls in specified direction at current mouse position or given coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "amount": {"type": "integer", "default": 3, "description": "Scroll amount in lines"},
                "x": {"type": "integer", "description": "Optional: X position for scroll"},
                "y": {"type": "integer", "description": "Optional: Y position for scroll"}
            },
            "required": ["direction"]
        },
        "returns": "Action result"
    },
    
    ToolName.DRAG: {
        "name": "drag",
        "description": "Drags from start to end position. Use for moving elements or selecting text.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer", "description": "Start X coordinate"},
                "start_y": {"type": "integer", "description": "Start Y coordinate"},
                "end_x": {"type": "integer", "description": "End X coordinate"},
                "end_y": {"type": "integer", "description": "End Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "duration": {"type": "number", "default": 0.5, "description": "Duration in seconds"}
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        },
        "returns": "Action result"
    },
    
    ToolName.WAIT: {
        "name": "wait",
        "description": "Waits for specified duration. Use after actions to let UI update.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "default": 1.0, "minimum": 0.1, "maximum": 10.0}
            },
            "required": []
        },
        "returns": "Wait completed"
    },
    
    ToolName.WAIT_FOR_ELEMENT: {
        "name": "wait_for_element",
        "description": "Waits until UI element with specified text appears. Use for dynamic loading.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_text": {"type": "string", "description": "Text to find in UI"},
                "timeout_seconds": {"type": "number", "default": 5.0, "minimum": 1.0, "maximum": 30.0}
            },
            "required": ["element_text"]
        },
        "returns": "Element found with coordinates or timeout"
    }
}


def get_tool_functions_schema() -> List[Dict[str, Any]]:
    """
    Gibt Tool-Definitionen im OpenAI Function-Calling Format zurück.
    
    Wird an LLM gesendet für Function-Calling.
    """
    functions = []
    
    for tool_name, tool_def in DESKTOP_TOOLS.items():
        functions.append({
            "name": tool_def["name"],
            "description": tool_def["description"],
            "parameters": tool_def["parameters"]
        })
    
    return functions


# ==================== Size Validator ====================

class SizeValidator:
    """
    Validiert LLM Size-Requests gegen UI-Element-Bounds.
    
    Features:
    - Minimum Size Enforcement (50x50 px)
    - Maximum Margin Capping (100px)
    - Screen Bounds Clipping
    - Detailed Validation Reports
    """
    
    MIN_SIZE = 50  # Minimum 50x50 px
    MAX_MARGIN = 100  # Max 100px extra margin pro Seite
    
    def __init__(self):
        self.validation_history: List[SizeValidationReport] = []
    
    def validate_size_request(
        self,
        llm_request: Dict[str, int],
        element_bounds: Optional[Dict[str, int]] = None,
        screen_bounds: Optional[Dict[str, int]] = None
    ) -> SizeValidationReport:
        """
        Validiert Size-Request und erstellt Report für Function Agent.
        
        Args:
            llm_request: {"x": int, "y": int, "width": int, "height": int}
            element_bounds: {"x": int, "y": int, "width": int, "height": int} oder None
            screen_bounds: {"width": int, "height": int}
            
        Returns:
            SizeValidationReport mit Ergebnis und Adjustments
        """
        screen_bounds = screen_bounds or {"width": 1920, "height": 1080}
        element_bounds = element_bounds or {}
        
        # Original-Werte
        req_x = llm_request.get("x", 0)
        req_y = llm_request.get("y", 0)
        req_w = llm_request.get("width", self.MIN_SIZE)
        req_h = llm_request.get("height", self.MIN_SIZE)
        
        # Element-Werte
        elem_x = element_bounds.get("x", req_x)
        elem_y = element_bounds.get("y", req_y)
        elem_w = element_bounds.get("width", 0)
        elem_h = element_bounds.get("height", 0)
        
        # Applied-Werte (werden angepasst)
        applied_x = req_x
        applied_y = req_y
        applied_w = req_w
        applied_h = req_h
        
        reasons = []
        result = SizeValidationResult.APPROVED
        
        # 1. Minimum Size Check
        if applied_w < self.MIN_SIZE:
            applied_w = self.MIN_SIZE
            reasons.append(f"Width increased to minimum {self.MIN_SIZE}px")
            
        if applied_h < self.MIN_SIZE:
            applied_h = self.MIN_SIZE
            reasons.append(f"Height increased to minimum {self.MIN_SIZE}px")
        
        # 2. Element Bounds Comparison (wenn Element vorhanden)
        if elem_w > 0 and elem_h > 0:
            width_delta = applied_w - elem_w
            height_delta = applied_h - elem_h
            
            # LLM hat weniger angefordert als Element-Größe
            if width_delta < 0:
                applied_w = max(elem_w, self.MIN_SIZE)
                reasons.append(f"Width expanded to element size ({elem_w}px)")
            elif width_delta > self.MAX_MARGIN * 2:  # * 2 weil links+rechts
                applied_w = elem_w + self.MAX_MARGIN * 2
                reasons.append(f"Width margin capped to ±{self.MAX_MARGIN}px")
            
            if height_delta < 0:
                applied_h = max(elem_h, self.MIN_SIZE)
                reasons.append(f"Height expanded to element size ({elem_h}px)")
            elif height_delta > self.MAX_MARGIN * 2:
                applied_h = elem_h + self.MAX_MARGIN * 2
                reasons.append(f"Height margin capped to ±{self.MAX_MARGIN}px")
        
        # 3. Negative Coordinates Check
        if applied_x < 0:
            applied_x = 0
            reasons.append("X coordinate clamped to 0")
            
        if applied_y < 0:
            applied_y = 0
            reasons.append("Y coordinate clamped to 0")
        
        # 4. Screen Bounds Clipping
        max_x = screen_bounds["width"]
        max_y = screen_bounds["height"]
        
        if applied_x + applied_w > max_x:
            if applied_x >= max_x:
                applied_x = max_x - self.MIN_SIZE
                applied_w = self.MIN_SIZE
                reasons.append("X and width adjusted to fit screen")
            else:
                applied_w = max_x - applied_x
                reasons.append(f"Width clipped to screen bounds ({applied_w}px)")
        
        if applied_y + applied_h > max_y:
            if applied_y >= max_y:
                applied_y = max_y - self.MIN_SIZE
                applied_h = self.MIN_SIZE
                reasons.append("Y and height adjusted to fit screen")
            else:
                applied_h = max_y - applied_y
                reasons.append(f"Height clipped to screen bounds ({applied_h}px)")
        
        # Bestimme Ergebnis
        if reasons:
            result = SizeValidationResult.ADJUSTED
        
        # Erstelle Report
        report = SizeValidationReport(
            result=result,
            original_request={
                "x": req_x,
                "y": req_y,
                "width": req_w,
                "height": req_h
            },
            element_bounds=element_bounds if element_bounds else {},
            applied_size={
                "x": applied_x,
                "y": applied_y,
                "width": applied_w,
                "height": applied_h
            },
            adjustments={
                "width_delta": applied_w - elem_w if elem_w > 0 else 0,
                "height_delta": applied_h - elem_h if elem_h > 0 else 0,
                "reasons": reasons
            },
            timestamp=datetime.now()
        )
        
        # Speichere für History
        self.validation_history.append(report)
        if len(self.validation_history) > 100:
            self.validation_history = self.validation_history[-100:]
        
        # Log
        logger.info(f"Size Validation: {result.value}")
        logger.info(f"  Original: {req_w}x{req_h} at ({req_x}, {req_y})")
        logger.info(f"  Applied:  {applied_w}x{applied_h} at ({applied_x}, {applied_y})")
        if reasons:
            logger.info(f"  Adjustments: {reasons}")
        
        return report
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Gibt Validation-Statistiken zurück."""
        if not self.validation_history:
            return {"total": 0, "approved": 0, "adjusted": 0}
        
        approved = sum(1 for r in self.validation_history if r.result == SizeValidationResult.APPROVED)
        adjusted = sum(1 for r in self.validation_history if r.result == SizeValidationResult.ADJUSTED)
        
        return {
            "total": len(self.validation_history),
            "approved": approved,
            "adjusted": adjusted,
            "adjustment_rate": adjusted / len(self.validation_history) if self.validation_history else 0
        }


# ==================== Desktop Tool Executor ====================

class DesktopToolExecutor:
    """
    Führt Desktop-Tools aus mit Size-Validation.
    
    Features:
    - Tool-Dispatching zu InteractionAgent
    - Screenshot-Capture für Validation
    - Size-Validation mit Reporting
    - Execution History
    """
    
    def __init__(
        self,
        interaction_agent: Optional[InteractionAgent] = None,
        screen_bounds: Optional[Dict[str, int]] = None
    ):
        self.interaction_agent = interaction_agent or (
            get_interaction_agent() if HAS_INTERACTION else None
        )
        self.size_validator = SizeValidator()
        self.screen_bounds = screen_bounds or {"width": 1920, "height": 1080}
        self.execution_history: List[Dict[str, Any]] = []
        
        # Detect actual screen size
        if HAS_PIL:
            try:
                screenshot = ImageGrab.grab()
                self.screen_bounds = {
                    "width": screenshot.width,
                    "height": screenshot.height
                }
                logger.info(f"Screen bounds detected: {self.screen_bounds}")
            except Exception as e:
                logger.warning(f"Could not detect screen size: {e}")
    
    async def execute_tool(
        self,
        tool_name: ToolName,
        params: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Führt ein Tool aus.
        
        Args:
            tool_name: Name des Tools
            params: Tool-Parameter
            ui_state: Optional UI-State für Element-Lookup
            
        Returns:
            Tool-Ergebnis
        """
        start_time = datetime.now()
        result = {"success": False, "tool": tool_name.value}
        
        try:
            if tool_name == ToolName.CAPTURE_SCREENSHOT_REGION:
                result = await self._capture_region_with_validation(params, ui_state)
                
            elif tool_name == ToolName.CLICK_AT_POSITION:
                result = await self._execute_click(params)
                
            elif tool_name == ToolName.DOUBLE_CLICK:
                result = await self._execute_double_click(params)
                
            elif tool_name == ToolName.RIGHT_CLICK:
                result = await self._execute_right_click(params)
                
            elif tool_name == ToolName.TYPE_TEXT:
                result = await self._execute_type(params)
                
            elif tool_name == ToolName.PRESS_KEY:
                result = await self._execute_press_key(params)
                
            elif tool_name == ToolName.HOTKEY:
                result = await self._execute_hotkey(params)
                
            elif tool_name == ToolName.SCROLL:
                result = await self._execute_scroll(params)
                
            elif tool_name == ToolName.DRAG:
                result = await self._execute_drag(params)
                
            elif tool_name == ToolName.WAIT:
                result = await self._execute_wait(params)
                
            elif tool_name == ToolName.WAIT_FOR_ELEMENT:
                result = await self._execute_wait_for_element(params, ui_state)
            
            else:
                result = {"success": False, "error": f"Unknown tool: {tool_name}"}
            
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            result = {"success": False, "error": str(e)}
        
        # Execution Time
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        result["duration_ms"] = duration_ms
        
        # Log to history
        self._log_execution(tool_name, params, result)
        
        return result
    
    async def _capture_region_with_validation(
        self,
        params: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Captures screenshot region mit Size-Validation."""
        if not HAS_PIL:
            return {"success": False, "error": "PIL not available"}
        
        # Find target element bounds if specified
        element_bounds = None
        if params.get("target_element") and ui_state:
            element = self._find_element(params["target_element"], ui_state.get("elements", []))
            if element:
                element_bounds = element.get("bounds", {})
        
        # Size Validation
        validation_report = self.size_validator.validate_size_request(
            llm_request={
                "x": params.get("x", 0),
                "y": params.get("y", 0),
                "width": params.get("width", 50),
                "height": params.get("height", 50)
            },
            element_bounds=element_bounds,
            screen_bounds=self.screen_bounds
        )
        
        # Use validated size
        applied = validation_report.applied_size
        
        try:
            # Capture region
            bbox = (
                applied["x"],
                applied["y"],
                applied["x"] + applied["width"],
                applied["y"] + applied["height"]
            )
            screenshot = ImageGrab.grab(bbox=bbox)
            
            # Encode to base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return {
                "success": True,
                "tool": "capture_screenshot_region",
                "image_base64": image_base64,
                "captured_region": applied,
                "size_validation": validation_report.to_dict()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "size_validation": validation_report.to_dict()
            }
    
    async def capture_full_screen(self) -> Optional[str]:
        """Captures full screen screenshot as base64."""
        if not HAS_PIL:
            return None
        
        try:
            screenshot = ImageGrab.grab()
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception as e:
            logger.error(f"Full screen capture failed: {e}")
            return None
    
    async def _execute_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Click aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)
        
        from agents.interaction import MouseButton
        button_enum = MouseButton(button)
        
        return await self.interaction_agent.click((x, y), button=button_enum, clicks=clicks)
    
    async def _execute_double_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Double-Click aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        return await self.interaction_agent.double_click((x, y))
    
    async def _execute_right_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Right-Click aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        x = params.get("x", 0)
        y = params.get("y", 0)
        return await self.interaction_agent.right_click((x, y))
    
    async def _execute_type(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Text-Eingabe aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        text = params.get("text", "")
        use_clipboard = params.get("use_clipboard", True)
        return await self.interaction_agent.type_text(text, use_clipboard=use_clipboard)
    
    async def _execute_press_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Tastendruck aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        key = params.get("key", "")
        presses = params.get("presses", 1)
        return await self.interaction_agent.press_key(key, presses=presses)
    
    async def _execute_hotkey(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Hotkey aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        keys = params.get("keys", [])
        if isinstance(keys, list):
            return await self.interaction_agent.hotkey(*keys)
        return {"success": False, "error": "Keys must be a list"}
    
    async def _execute_scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Scroll aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        direction = params.get("direction", "down")
        amount = params.get("amount", 3)
        target = None
        
        if "x" in params and "y" in params:
            target = (params["x"], params["y"])
        
        return await self.interaction_agent.scroll(direction, amount=amount, target=target)
    
    async def _execute_drag(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Drag aus."""
        if not self.interaction_agent:
            return {"success": False, "error": "InteractionAgent not available"}
        
        start = (params.get("start_x", 0), params.get("start_y", 0))
        end = (params.get("end_x", 0), params.get("end_y", 0))
        duration = params.get("duration", 0.5)
        
        return await self.interaction_agent.drag(start, end, duration=duration)
    
    async def _execute_wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Führt Wait aus."""
        seconds = params.get("seconds", 1.0)
        await asyncio.sleep(seconds)
        return {"success": True, "action": "wait", "seconds": seconds}
    
    async def _execute_wait_for_element(
        self,
        params: Dict[str, Any],
        ui_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Wartet auf Element."""
        element_text = params.get("element_text", "")
        timeout = params.get("timeout_seconds", 5.0)
        
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # Check current UI state
            if ui_state:
                for element in ui_state.get("elements", []):
                    if element_text.lower() in str(element.get("text", "")).lower():
                        return {
                            "success": True,
                            "action": "wait_for_element",
                            "element_found": element,
                            "wait_time_seconds": (datetime.now() - start_time).total_seconds()
                        }
            
            await asyncio.sleep(0.5)
        
        return {
            "success": False,
            "action": "wait_for_element",
            "error": f"Element with text '{element_text}' not found within {timeout}s"
        }
    
    def _find_element(
        self,
        element_id: str,
        elements: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Findet Element in UI-State."""
        for element in elements:
            if element.get("id") == element_id:
                return element
            if element.get("text") == element_id:
                return element
            if element.get("name") == element_id:
                return element
        return None
    
    def _log_execution(
        self,
        tool_name: ToolName,
        params: Dict[str, Any],
        result: Dict[str, Any]
    ):
        """Loggt Execution für History."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name.value,
            "params": params,
            "success": result.get("success", False),
            "duration_ms": result.get("duration_ms", 0)
        }
        
        self.execution_history.append(entry)
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Gibt Execution-Statistiken zurück."""
        if not self.execution_history:
            return {"total": 0, "success_rate": 0}
        
        successful = sum(1 for e in self.execution_history if e.get("success"))
        
        return {
            "total": len(self.execution_history),
            "successful": successful,
            "failed": len(self.execution_history) - successful,
            "success_rate": successful / len(self.execution_history),
            "size_validation_stats": self.size_validator.get_validation_stats()
        }


# ==================== Singleton ====================

_tool_executor_instance: Optional[DesktopToolExecutor] = None


def get_tool_executor() -> DesktopToolExecutor:
    """Gibt Singleton-Instanz des DesktopToolExecutors zurück."""
    global _tool_executor_instance
    if _tool_executor_instance is None:
        _tool_executor_instance = DesktopToolExecutor()
    return _tool_executor_instance


# ==================== Test ====================

async def main():
    """Test der Desktop Tools."""
    executor = DesktopToolExecutor()
    
    print("\n" + "=" * 60)
    print("Desktop Tools Test")
    print("=" * 60)
    
    # Test 1: Size Validation
    print("\n1. Size Validation Test")
    validator = SizeValidator()
    
    # Normal request
    report = validator.validate_size_request(
        llm_request={"x": 100, "y": 200, "width": 80, "height": 60},
        element_bounds={"x": 100, "y": 200, "width": 80, "height": 30}
    )
    print(f"   Result: {report.result.value}")
    print(f"   Applied: {report.applied_size}")
    
    # Small request (under minimum)
    report = validator.validate_size_request(
        llm_request={"x": 100, "y": 200, "width": 30, "height": 30}
    )
    print(f"   Under-minimum Result: {report.result.value}")
    print(f"   Applied: {report.applied_size}")
    
    # Test 2: Screenshot Capture
    print("\n2. Screenshot Capture Test")
    if HAS_PIL:
        result = await executor.execute_tool(
            ToolName.CAPTURE_SCREENSHOT_REGION,
            {"x": 0, "y": 0, "width": 200, "height": 200}
        )
        print(f"   Success: {result.get('success')}")
        print(f"   Captured Region: {result.get('captured_region')}")
        if result.get("image_base64"):
            print(f"   Image Size: {len(result['image_base64'])} chars")
    else:
        print("   PIL not available")
    
    # Test 3: Wait
    print("\n3. Wait Test")
    result = await executor.execute_tool(
        ToolName.WAIT,
        {"seconds": 0.5}
    )
    print(f"   Success: {result.get('success')}")
    print(f"   Duration: {result.get('duration_ms'):.0f}ms")
    
    # Stats
    print("\n4. Execution Stats")
    stats = executor.get_execution_stats()
    print(f"   {stats}")
    
    # Tool Functions Schema
    print("\n5. Tool Functions Schema")
    schema = get_tool_functions_schema()
    print(f"   Available tools: {len(schema)}")
    for func in schema[:3]:
        print(f"   - {func['name']}")
    print(f"   ... and {len(schema) - 3} more")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
