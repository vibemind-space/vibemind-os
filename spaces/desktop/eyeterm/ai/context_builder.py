"""Build structured text context from UIElementContext for AI prompts."""

import logging
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..screen.element_context import UIElementContext

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Converts UIElementContext + voice transcript into structured AI context."""

    def build_context(
        self,
        element: "UIElementContext",
        transcript: str,
        recent_actions: Optional[List[str]] = None,
    ) -> str:
        """Build structured text context from UIElementContext + voice transcript.

        Args:
            element: The UI element currently under gaze.
            transcript: Raw voice transcript from STT.
            recent_actions: Optional list of recent action descriptions.

        Returns:
            Multi-line structured context string suitable for AI prompts.
        """
        logger.debug("build_context called: element=%s transcript=%s", element.element_name, transcript[:60])
        patterns_str = ", ".join(element.supported_patterns) if element.supported_patterns else "(none)"
        value_str = element.value if element.value else (
            element.text_content if element.text_content else "(empty)"
        )
        selection_str = element.selection if element.selection else "(none)"
        bbox = element.bounding_box

        lines = [
            "---",
            f"App: {element.app_name}",
            f"Window: {element.window_title}",
            f'Element: {element.control_type} "{element.element_name}" ({patterns_str})',
            f"Value: {value_str}",
            f"Selection: {selection_str}",
            f"Bounding box: ({bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]})",
            f"Available actions: {patterns_str}",
        ]

        if recent_actions:
            last_three = recent_actions[-3:]
            lines.append(f"Recent actions: {'; '.join(last_three)}")
        else:
            lines.append("Recent actions: (none)")

        lines.append("")
        lines.append(f'User said: "{transcript}"')
        lines.append("---")

        return "\n".join(lines)

    def build_orchestrator_context(
        self,
        element: "UIElementContext",
        transcript: str,
    ) -> dict:
        """Build a dict suitable for VibeMind IntentOrchestrator / MinibookHub.

        Returns:
            Dict with gaze_context and user_request fields.
        """
        result = element.to_orchestrator_context()
        result["user_request"] = transcript
        return result

    def build_minimal_context(self, element: "UIElementContext") -> str:
        """One-line context for UI overlay display.

        Args:
            element: The UI element currently under gaze.

        Returns:
            Short one-line summary string.
        """
        app_short = element.app_name.replace(".exe", "") if element.app_name else "?"
        patterns_short = "/".join(element.supported_patterns[:3]) if element.supported_patterns else "-"
        return f"{app_short} | {element.control_type}: {element.element_name} [{patterns_short}]"
