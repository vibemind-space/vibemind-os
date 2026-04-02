"""Execute actions via Windows UI Automation patterns."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class UIAActionExecutor:
    """Execute actions on UI elements via Windows UIA COM patterns."""

    def __init__(self):
        try:
            import comtypes.client
            self._uia = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=comtypes.gen.UIAutomationClient.IUIAutomation,
            )
        except Exception:
            # Lazy fallback: UIA will be initialized on first use
            self._uia = None
            logger.debug("UIA COM init deferred — will initialize on first action")

    def invoke(self, element_handle) -> dict:
        """Click button via InvokePattern.

        Args:
            element_handle: UIA IUIAutomationElement.

        Returns:
            dict with success and message keys.
        """
        try:
            # UIA_InvokePatternId = 10000
            pattern = element_handle.GetCurrentPattern(10000)
            if pattern is None:
                return {"success": False, "message": "Element does not support InvokePattern"}
            pattern.Invoke()
            return {"success": True, "message": "Invoked element"}
        except Exception as e:
            logger.error("InvokePattern failed: %s", e)
            return {"success": False, "message": f"Invoke failed: {e}"}

    def set_value(self, element_handle, text: str) -> dict:
        """Set text via ValuePattern.

        Args:
            element_handle: UIA IUIAutomationElement.
            text: The text to set.

        Returns:
            dict with success and message keys.
        """
        try:
            # UIA_ValuePatternId = 10002
            pattern = element_handle.GetCurrentPattern(10002)
            if pattern is None:
                return {"success": False, "message": "Element does not support ValuePattern"}
            pattern.SetValue(text)
            return {"success": True, "message": f"Set value to '{text[:50]}'"}
        except Exception as e:
            logger.error("ValuePattern.SetValue failed: %s", e)
            return {"success": False, "message": f"SetValue failed: {e}"}

    def get_text(self, element_handle) -> Optional[str]:
        """Read text via TextPattern or ValuePattern.

        Args:
            element_handle: UIA IUIAutomationElement.

        Returns:
            Text content or None if not readable.
        """
        # Try TextPattern first (UIA_TextPatternId = 10014)
        try:
            pattern = element_handle.GetCurrentPattern(10014)
            if pattern is not None:
                doc_range = pattern.DocumentRange
                return doc_range.GetText(-1)
        except Exception:
            pass

        # Fall back to ValuePattern (UIA_ValuePatternId = 10002)
        try:
            pattern = element_handle.GetCurrentPattern(10002)
            if pattern is not None:
                return pattern.CurrentValue
        except Exception:
            pass

        # Try element Name property as last resort
        try:
            return element_handle.CurrentName
        except Exception:
            return None

    def toggle(self, element_handle) -> dict:
        """Toggle checkbox via TogglePattern.

        Args:
            element_handle: UIA IUIAutomationElement.

        Returns:
            dict with success and message keys.
        """
        try:
            # UIA_TogglePatternId = 10015
            pattern = element_handle.GetCurrentPattern(10015)
            if pattern is None:
                return {"success": False, "message": "Element does not support TogglePattern"}
            pattern.Toggle()
            new_state = pattern.CurrentToggleState
            state_names = {0: "off", 1: "on", 2: "indeterminate"}
            state_str = state_names.get(new_state, str(new_state))
            return {"success": True, "message": f"Toggled to {state_str}"}
        except Exception as e:
            logger.error("TogglePattern failed: %s", e)
            return {"success": False, "message": f"Toggle failed: {e}"}

    def select(self, element_handle) -> dict:
        """Select item via SelectionItemPattern.

        Args:
            element_handle: UIA IUIAutomationElement.

        Returns:
            dict with success and message keys.
        """
        try:
            # UIA_SelectionItemPatternId = 10010
            pattern = element_handle.GetCurrentPattern(10010)
            if pattern is None:
                return {"success": False, "message": "Element does not support SelectionItemPattern"}
            pattern.Select()
            return {"success": True, "message": "Selected element"}
        except Exception as e:
            logger.error("SelectionItemPattern failed: %s", e)
            return {"success": False, "message": f"Select failed: {e}"}

    def scroll(self, element_handle, direction: str, amount: float = 1.0) -> dict:
        """Scroll via ScrollPattern.

        Args:
            element_handle: UIA IUIAutomationElement.
            direction: One of "up", "down", "left", "right".
            amount: Scroll amount (number of pages, default 1.0).

        Returns:
            dict with success and message keys.
        """
        try:
            # UIA_ScrollPatternId = 10004
            pattern = element_handle.GetCurrentPattern(10004)
            if pattern is None:
                return {"success": False, "message": "Element does not support ScrollPattern"}

            # ScrollAmount enum: LargeDecrement=0, SmallDecrement=1,
            # NoAmount=2, LargeIncrement=3, SmallIncrement=4
            NO_SCROLL = 2  # NoAmount — don't scroll this axis
            direction_lower = direction.lower()

            if direction_lower in ("down", "runter"):
                pattern.Scroll(NO_SCROLL, 3)  # vertical LargeIncrement
            elif direction_lower in ("up", "hoch"):
                pattern.Scroll(NO_SCROLL, 0)  # vertical LargeDecrement
            elif direction_lower == "right":
                pattern.Scroll(3, NO_SCROLL)  # horizontal LargeIncrement
            elif direction_lower == "left":
                pattern.Scroll(0, NO_SCROLL)  # horizontal LargeDecrement
            else:
                return {"success": False, "message": f"Unknown scroll direction: {direction}"}

            return {"success": True, "message": f"Scrolled {direction}"}
        except Exception as e:
            logger.error("ScrollPattern failed: %s", e)
            return {"success": False, "message": f"Scroll failed: {e}"}

    def focus(self, element_handle) -> dict:
        """Set focus to element via SetFocus().

        Args:
            element_handle: UIA IUIAutomationElement.

        Returns:
            dict with success and message keys.
        """
        try:
            element_handle.SetFocus()
            return {"success": True, "message": "Focused element"}
        except Exception as e:
            logger.error("SetFocus failed: %s", e)
            return {"success": False, "message": f"Focus failed: {e}"}
