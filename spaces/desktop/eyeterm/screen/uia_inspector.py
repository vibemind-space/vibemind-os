"""
UIAInspector — Windows UI Automation element inspector via comtypes COM.

Provides hit-testing at screen coordinates and focused-element queries,
returning fully populated UIElementContext instances.
"""

import ctypes
import ctypes.wintypes
import logging
from typing import List, Optional

try:
    import comtypes
    import comtypes.client
    HAS_COMTYPES = True
except ImportError:
    HAS_COMTYPES = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .element_context import UIElementContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UIA COM GUIDs
# ---------------------------------------------------------------------------
CLSID_CUIAutomation = comtypes.GUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}") if HAS_COMTYPES else None
IID_IUIAutomation = comtypes.GUID("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}") if HAS_COMTYPES else None

# ---------------------------------------------------------------------------
# UIA Control Type IDs  (subset — extend as needed)
# ---------------------------------------------------------------------------
_CONTROL_TYPE_NAMES = {
    50000: "Button",
    50001: "Calendar",
    50002: "CheckBox",
    50003: "ComboBox",
    50004: "Edit",
    50005: "Hyperlink",
    50006: "Image",
    50007: "ListItem",
    50008: "List",
    50009: "Menu",
    50010: "MenuBar",
    50011: "MenuItem",
    50012: "ProgressBar",
    50013: "RadioButton",
    50014: "ScrollBar",
    50015: "Slider",
    50016: "Spinner",
    50017: "StatusBar",
    50018: "Tab",
    50019: "TabItem",
    50020: "Text",
    50021: "ToolBar",
    50022: "ToolTip",
    50023: "Tree",
    50024: "TreeItem",
    50025: "Custom",
    50026: "Group",
    50027: "Thumb",
    50028: "DataGrid",
    50029: "DataItem",
    50030: "Document",
    50031: "SplitButton",
    50032: "Window",
    50033: "Pane",
    50034: "Header",
    50035: "HeaderItem",
    50036: "Table",
    50037: "TitleBar",
    50038: "Separator",
}

# ---------------------------------------------------------------------------
# UIA Pattern IDs  (subset — extend as needed)
# ---------------------------------------------------------------------------
_PATTERN_IDS = {
    10000: "Invoke",
    10001: "Selection",
    10002: "Value",
    10003: "RangeValue",
    10004: "Scroll",
    10005: "ExpandCollapse",
    10006: "Grid",
    10007: "GridItem",
    10008: "MultipleView",
    10009: "Window",
    10010: "SelectionItem",
    10011: "Dock",
    10012: "Table",
    10013: "TableItem",
    10014: "Text",
    10015: "Toggle",
    10016: "Transform",
    10017: "ScrollItem",
    10018: "ItemContainer",
}

# Specific pattern IDs we try to read values from
_UIA_VALUE_PATTERN_ID = 10002
_UIA_TEXT_PATTERN_ID = 10014

# Maximum chars to keep from text content
_MAX_TEXT_LENGTH = 500


class UIAInspector:
    """
    Inspect Windows UI elements using the native UI Automation COM API.

    Usage::

        inspector = UIAInspector()
        ctx = inspector.element_at_point(500, 300)
        if ctx:
            print(ctx.summary())
    """

    def __init__(self):
        if not HAS_COMTYPES:
            raise RuntimeError(
                "comtypes is required for UIAInspector. Install with: pip install comtypes"
            )

        try:
            self._uia = comtypes.CoCreateInstance(
                CLSID_CUIAutomation,
                interface=comtypes.gen.UIAutomationClient.IUIAutomation,
            )
        except Exception:
            # Fallback: generate the type library on-the-fly then retry.
            try:
                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen.UIAutomationClient import IUIAutomation  # noqa: F811

                self._uia = comtypes.CoCreateInstance(
                    CLSID_CUIAutomation,
                    interface=IUIAutomation,
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to initialise IUIAutomation COM interface: {exc}") from exc

        # TreeWalker for parent navigation
        try:
            self._walker = self._uia.RawViewWalker
        except Exception:
            self._walker = None

        logger.info("UIAInspector initialised successfully")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def element_at_point(self, x: int, y: int) -> Optional[UIElementContext]:
        """Hit-test the UI tree at screen coordinates *(x, y)*.

        Returns a fully populated :class:`UIElementContext` or ``None``
        if no element could be resolved.
        """
        try:
            pt = ctypes.wintypes.POINT(x, y)
            element = self._uia.ElementFromPoint(pt)
            if element is None:
                return None
            return self._build_context(element)
        except Exception:
            logger.debug("element_at_point(%s, %s) failed", x, y, exc_info=True)
            return None

    def get_focused_element(self) -> Optional[UIElementContext]:
        """Return the currently keyboard-focused element."""
        try:
            element = self._uia.GetFocusedElement()
            if element is None:
                return None
            return self._build_context(element)
        except Exception:
            logger.debug("get_focused_element() failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, element) -> UIElementContext:
        """Extract all available properties from an IUIAutomationElement."""

        # --- Identity ---
        element_name = self._safe_prop(element, "CurrentName") or ""
        automation_id = self._safe_prop(element, "CurrentAutomationId") or ""
        control_type_id = self._safe_prop(element, "CurrentControlType") or 0
        control_type = _CONTROL_TYPE_NAMES.get(control_type_id, f"Unknown({control_type_id})")

        # Process / window info
        pid = self._safe_prop(element, "CurrentProcessId") or 0
        app_name = self._process_name_from_pid(pid)

        # Walk up to find the top-level window title
        window_title = self._find_window_title(element)

        # --- Geometry ---
        bounding_box = self._get_bounding_box(element)

        # --- Capabilities ---
        is_enabled = bool(self._safe_prop(element, "CurrentIsEnabled"))
        is_focusable = bool(self._safe_prop(element, "CurrentIsKeyboardFocusable"))
        supported_patterns = self._get_supported_patterns(element)

        # --- Content ---
        value = self._try_get_value(element)
        text_content = self._try_get_text(element)
        selection = self._try_get_selection(element)

        # --- Navigation ---
        parent_chain = self._get_parent_chain(element)

        return UIElementContext(
            app_name=app_name,
            window_title=window_title,
            control_type=control_type,
            element_name=element_name,
            automation_id=automation_id,
            value=value,
            text_content=text_content,
            selection=selection,
            bounding_box=bounding_box,
            supported_patterns=supported_patterns,
            is_enabled=is_enabled,
            is_keyboard_focusable=is_focusable,
            parent_chain=parent_chain,
            source="uia",
        )

    # -- Property helpers ------------------------------------------------

    @staticmethod
    def _safe_prop(element, prop_name):
        """Read a COM property, returning None on any error."""
        try:
            return getattr(element, prop_name)
        except Exception:
            return None

    def _get_bounding_box(self, element):
        """Return (x, y, w, h) from CurrentBoundingRectangle."""
        try:
            rect = element.CurrentBoundingRectangle
            # rect is a RECT-like struct with left, top, right, bottom
            x = rect.left
            y = rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            return (x, y, w, h)
        except Exception:
            return (0, 0, 0, 0)

    # -- Pattern helpers -------------------------------------------------

    def _get_supported_patterns(self, element) -> List[str]:
        """Check which UIA patterns the element supports."""
        patterns: List[str] = []
        for pattern_id, pattern_name in _PATTERN_IDS.items():
            try:
                pat = element.GetCurrentPattern(pattern_id)
                if pat is not None:
                    patterns.append(pattern_name)
            except Exception:
                continue
        return patterns

    def _try_get_value(self, element) -> Optional[str]:
        """Attempt to read the element's value via ValuePattern."""
        try:
            pat = element.GetCurrentPattern(_UIA_VALUE_PATTERN_ID)
            if pat is not None:
                val = pat.CurrentValue
                if val:
                    return str(val)[:_MAX_TEXT_LENGTH]
        except Exception:
            pass
        return None

    def _try_get_text(self, element) -> Optional[str]:
        """Attempt to read full text via TextPattern.DocumentRange."""
        try:
            pat = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
            if pat is not None:
                doc_range = pat.DocumentRange
                if doc_range is not None:
                    text = doc_range.GetText(-1)
                    if text:
                        return str(text)[:_MAX_TEXT_LENGTH]
        except Exception:
            pass
        return None

    def _try_get_selection(self, element) -> Optional[str]:
        """Attempt to read selected text via TextPattern.GetSelection."""
        try:
            pat = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
            if pat is not None:
                selection_array = pat.GetSelection()
                if selection_array is not None and selection_array.Length > 0:
                    first_range = selection_array.GetElement(0)
                    text = first_range.GetText(-1)
                    if text:
                        return str(text)[:_MAX_TEXT_LENGTH]
        except Exception:
            pass
        return None

    # -- Tree navigation -------------------------------------------------

    def _get_parent_chain(self, element, max_depth: int = 5) -> List[str]:
        """Walk up the UI tree via TreeWalker, returning labels."""
        if self._walker is None:
            return []
        chain: List[str] = []
        current = element
        for _ in range(max_depth):
            try:
                parent = self._walker.GetParentElement(current)
                if parent is None:
                    break
                name = self._safe_prop(parent, "CurrentName") or ""
                ct_id = self._safe_prop(parent, "CurrentControlType") or 0
                ct_name = _CONTROL_TYPE_NAMES.get(ct_id, "Unknown")
                chain.append(f"{ct_name}:{name}" if name else ct_name)
                current = parent
            except Exception:
                break
        return chain

    def _find_window_title(self, element) -> str:
        """Walk up to the nearest Window control and return its name."""
        if self._walker is None:
            return self._safe_prop(element, "CurrentName") or ""
        current = element
        for _ in range(20):
            try:
                ct_id = self._safe_prop(current, "CurrentControlType") or 0
                if ct_id == 50032:  # Window
                    return self._safe_prop(current, "CurrentName") or ""
                parent = self._walker.GetParentElement(current)
                if parent is None:
                    break
                current = parent
            except Exception:
                break
        return ""

    # -- Process helpers -------------------------------------------------

    @staticmethod
    def _process_name_from_pid(pid: int) -> str:
        """Resolve a PID to its executable name."""
        if pid <= 0:
            return ""
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(pid)
                return proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return ""
        # Fallback: use ctypes OpenProcess + QueryFullProcessImageName
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(260)
                size = ctypes.wintypes.DWORD(260)
                ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
                if ok:
                    # Return just the filename
                    full_path = buf.value
                    return full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass
        return ""
