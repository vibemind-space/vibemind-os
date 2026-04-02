"""
UIElementContext — Structured representation of a UI element on screen.

Captures identity, content, geometry, capabilities, and navigation context
for any element discovered via UIA inspection or OCR fallback.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class UIElementContext:
    """Full context snapshot of a single UI element."""

    # Identity
    app_name: str               # "chrome.exe", "Code.exe", "WINWORD.EXE"
    window_title: str           # "README.md - Visual Studio Code"
    control_type: str           # "Edit", "Button", "Document", "Text", "List", "Pane", etc.
    element_name: str           # "Search", "OK", "editor"
    automation_id: str          # Internal ID for precise targeting

    # Content
    value: Optional[str] = None        # Current value (text fields, combos)
    text_content: Optional[str] = None # Full text (documents, editors) — truncated to 500 chars
    selection: Optional[str] = None    # Selected text if any

    # Geometry
    bounding_box: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (x, y, w, h)

    # Capabilities
    supported_patterns: List[str] = field(default_factory=list)  # ["Invoke", "Value", "Text", "Toggle"]
    is_enabled: bool = True
    is_keyboard_focusable: bool = False

    # Navigation
    parent_chain: List[str] = field(default_factory=list)  # ["Window:VSCode", "Pane:Editor"]

    # Source
    source: str = "uia"  # "uia" or "ocr_fallback"

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "control_type": self.control_type,
            "element_name": self.element_name,
            "automation_id": self.automation_id,
            "value": self.value,
            "text_content": self.text_content,
            "selection": self.selection,
            "bounding_box": list(self.bounding_box),
            "supported_patterns": self.supported_patterns,
            "is_enabled": self.is_enabled,
            "is_keyboard_focusable": self.is_keyboard_focusable,
            "parent_chain": self.parent_chain,
            "source": self.source,
        }

    def summary(self) -> str:
        """One-line summary like '[Button: OK | Chrome | InvokePattern]'."""
        patterns_str = ", ".join(self.supported_patterns) if self.supported_patterns else "none"
        app_short = self.app_name.replace(".exe", "") if self.app_name else "?"
        return f"[{self.control_type}: {self.element_name} | {app_short} | {patterns_str}]"

    def to_orchestrator_context(self) -> dict:
        """Compact dict for VibeMind IntentOrchestrator/MinibookHub payloads."""
        return {
            "gaze_app": self.app_name,
            "gaze_window": self.window_title,
            "gaze_element": f"{self.control_type}: {self.element_name}",
            "gaze_patterns": self.supported_patterns,
            "gaze_value": (self.value or self.text_content or "")[:200],
            "gaze_selection": (self.selection or "")[:200],
            "gaze_bbox": list(self.bounding_box),
        }

    def to_ai_context(self) -> str:
        """Multi-line structured context suitable for inclusion in AI prompts."""
        logger.debug("to_ai_context called for element %s", self.element_name)
        lines = [
            f"Element: {self.element_name}",
            f"  Type: {self.control_type}",
            f"  App: {self.app_name}",
            f"  Window: {self.window_title}",
            f"  AutomationId: {self.automation_id}",
            f"  Enabled: {self.is_enabled} | Focusable: {self.is_keyboard_focusable}",
            f"  Patterns: {', '.join(self.supported_patterns) if self.supported_patterns else 'none'}",
            f"  BoundingBox: x={self.bounding_box[0]}, y={self.bounding_box[1]}, w={self.bounding_box[2]}, h={self.bounding_box[3]}",
        ]
        if self.value is not None:
            lines.append(f"  Value: {self.value[:200]}")
        if self.text_content is not None:
            lines.append(f"  Text: {self.text_content[:200]}...")
        if self.selection is not None:
            lines.append(f"  Selection: {self.selection[:200]}")
        if self.parent_chain:
            lines.append(f"  ParentChain: {' > '.join(self.parent_chain)}")
        lines.append(f"  Source: {self.source}")
        return "\n".join(lines)
