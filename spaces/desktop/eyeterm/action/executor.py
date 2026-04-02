"""Priority-based action dispatch: UIA > keyboard > OCR fallback."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .keyboard_actions import KeyboardActions
from .uia_actions import UIAActionExecutor

if TYPE_CHECKING:
    from ..audio.command_parser import ParsedCommand
    from ..screen.element_context import UIElementContext

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of an action execution."""
    success: bool
    message: str
    data: dict = field(default_factory=dict)


class ActionExecutor:
    """Priority-based action dispatch: UIA > keyboard > OCR fallback."""

    def __init__(self):
        self._uia = UIAActionExecutor()
        self._keyboard = KeyboardActions()

    def execute(
        self,
        command: "ParsedCommand",
        element: "UIElementContext",
        element_handle=None,
    ) -> ActionResult:
        """Execute command on element using best available method.

        Priority:
        1. UIA pattern (if element supports it and handle is available)
        2. Keyboard/mouse (focus element, then type/click)
        3. OCR-based coordinate click (last resort via bounding box center)

        Args:
            command: Parsed voice command.
            element: UI element context (metadata).
            element_handle: Optional raw UIA IUIAutomationElement for pattern access.

        Returns:
            ActionResult with success status, message, and optional data.
        """
        action = command.action
        patterns = element.supported_patterns if element else []

        dispatch = {
            "click": self._execute_click,
            "type": self._execute_type,
            "read": self._execute_read,
            "select": self._execute_select,
            "toggle": self._execute_toggle,
            "scroll": self._execute_scroll,
        }

        handler = dispatch.get(action)
        if handler:
            return handler(command, element, element_handle, patterns)

        # Focus is a common utility action
        if action == "focus" and element_handle:
            result = self._uia.focus(element_handle)
            return ActionResult(**result)

        logger.debug("No specific handler for action '%s', passing through", action)
        return ActionResult(
            success=False,
            message=f"No executor for action '{action}'",
        )

    def _execute_click(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Click: InvokePattern > click_at(bbox center)."""
        # Try UIA InvokePattern
        if element_handle and "Invoke" in patterns:
            result = self._uia.invoke(element_handle)
            if result["success"]:
                return ActionResult(**result)

        # Fallback: click at bounding box center
        bbox = element.bounding_box if element else None
        if bbox and (bbox[2] > 0 and bbox[3] > 0):
            center_x = bbox[0] + bbox[2] // 2
            center_y = bbox[1] + bbox[3] // 2
            result = self._keyboard.click_at(center_x, center_y)
            return ActionResult(**result, data={"method": "keyboard_click", "coords": (center_x, center_y)})

        return ActionResult(success=False, message="No click method available (no InvokePattern, no bounding box)")

    def _execute_type(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Type: ValuePattern > focus + type_text."""
        text = command.prompt or command.instruction or ""
        if not text:
            return ActionResult(success=False, message="No text to type")

        # Try UIA ValuePattern
        if element_handle and "Value" in patterns:
            result = self._uia.set_value(element_handle, text)
            if result["success"]:
                return ActionResult(**result, data={"method": "value_pattern"})

        # Fallback: focus element then type via keyboard
        if element_handle:
            self._uia.focus(element_handle)
        elif element and element.bounding_box:
            bbox = element.bounding_box
            if bbox[2] > 0 and bbox[3] > 0:
                self._keyboard.click_at(bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2)

        result = self._keyboard.type_text(text)
        return ActionResult(**result, data={"method": "keyboard_type"})

    def _execute_read(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Read: TextPattern/ValuePattern > element metadata."""
        # Try UIA text extraction
        if element_handle:
            text = self._uia.get_text(element_handle)
            if text:
                return ActionResult(
                    success=True,
                    message=f"Read: {text[:200]}",
                    data={"text": text, "method": "uia_pattern"},
                )

        # Fallback: use element context data
        if element:
            text = element.value or element.text_content
            if text:
                return ActionResult(
                    success=True,
                    message=f"Read: {text[:200]}",
                    data={"text": text, "method": "element_context"},
                )

        return ActionResult(success=False, message="Could not read element content")

    def _execute_select(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Select: SelectionItemPattern > focus element."""
        if element_handle and "SelectionItem" in patterns:
            result = self._uia.select(element_handle)
            if result["success"]:
                return ActionResult(**result, data={"method": "selection_pattern"})

        # Fallback: just focus the element
        if element_handle:
            result = self._uia.focus(element_handle)
            return ActionResult(**result, data={"method": "focus_fallback"})

        return ActionResult(success=False, message="No select method available")

    def _execute_toggle(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Toggle: TogglePattern > click."""
        if element_handle and "Toggle" in patterns:
            result = self._uia.toggle(element_handle)
            if result["success"]:
                return ActionResult(**result, data={"method": "toggle_pattern"})

        # Fallback: click the element
        return self._execute_click(command, element, element_handle, patterns)

    def _execute_scroll(
        self, command, element, element_handle, patterns
    ) -> ActionResult:
        """Scroll: ScrollPattern > keyboard arrows."""
        direction = command.target or "down"

        # Try UIA ScrollPattern
        if element_handle and "Scroll" in patterns:
            result = self._uia.scroll(element_handle, direction)
            if result["success"]:
                return ActionResult(**result, data={"method": "scroll_pattern"})

        # Fallback: keyboard arrow keys
        key_map = {
            "up": "pageup",
            "hoch": "pageup",
            "down": "pagedown",
            "runter": "pagedown",
            "left": "left",
            "right": "right",
        }
        key = key_map.get(direction.lower(), "pagedown")
        result = self._keyboard.press_key(key)
        return ActionResult(**result, data={"method": "keyboard_scroll", "key": key})
