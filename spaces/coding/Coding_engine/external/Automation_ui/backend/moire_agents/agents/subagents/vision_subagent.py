"""
Vision Subagent - Analyzes screen regions in parallel.

Each VisionSubagent instance analyzes ONE screen region:
- TASKBAR: Windows taskbar (pinned apps, system tray)
- MAIN_CONTENT: Primary content area of active window
- TITLE_BAR: Window title, controls (minimize/maximize/close)
- SIDEBAR: Navigation panels, file trees
- MENU: Open menus, dropdowns
- DIALOG: Popup dialogs, modals
- SYSTEM_TRAY: System notification area

Multiple instances run in parallel analyzing different regions.
Results are merged by the orchestrator for complete screen understanding.

Example:
    Screenshot is divided into regions, each analyzed in parallel:
    - TASKBAR worker finds: Chrome icon (pinned), notification badge
    - MAIN_CONTENT worker finds: text editor, buttons, input fields
    - TITLE_BAR worker finds: "Untitled - Notepad", close button
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import base64

from .base_subagent import BaseSubagent, SubagentContext, SubagentOutput

logger = logging.getLogger(__name__)


class ScreenRegion(Enum):
    """Screen regions for analysis."""
    TASKBAR = "taskbar"          # Windows taskbar
    MAIN_CONTENT = "main_content"  # Primary window content
    TITLE_BAR = "title_bar"      # Window title and controls
    SIDEBAR = "sidebar"          # Side panels, navigation
    MENU = "menu"                # Open menus, dropdowns
    DIALOG = "dialog"            # Popup dialogs, modals
    SYSTEM_TRAY = "system_tray"  # System notification area
    FULL_SCREEN = "full_screen"  # Entire screen analysis


@dataclass
class RegionBounds:
    """Bounding box for a screen region."""
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Dict) -> "RegionBounds":
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 0),
            height=data.get("height", 0)
        )


@dataclass
class DetectedElement:
    """A UI element detected in a region."""
    element_type: str       # button, text, icon, input, link, image, etc.
    label: str              # Text or description
    bounds: RegionBounds    # Position within region
    confidence: float = 1.0
    clickable: bool = False
    editable: bool = False
    state: str = "normal"   # normal, focused, disabled, selected
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_type": self.element_type,
            "label": self.label,
            "bounds": self.bounds.to_dict(),
            "confidence": self.confidence,
            "clickable": self.clickable,
            "editable": self.editable,
            "state": self.state,
            "metadata": self.metadata
        }


# Region-specific analysis prompts for LLM vision
REGION_PROMPTS = {
    ScreenRegion.TASKBAR: """Analyze this Windows taskbar region.

IDENTIFY:
1. Pinned application icons (Chrome, Word, Explorer, etc.)
2. Running application indicators (underlined icons)
3. Start button position
4. Search icon/box
5. System tray icons (network, sound, battery, clock)
6. Notification badges or alerts

OUTPUT FORMAT (JSON):
{
    "elements": [
        {"type": "icon", "label": "Chrome", "position": "pinned", "state": "running"},
        {"type": "button", "label": "Start", "position": "left"},
        {"type": "icon", "label": "Network", "position": "system_tray"}
    ],
    "active_app": "Chrome",
    "notifications": 2,
    "confidence": 0.9
}""",

    ScreenRegion.MAIN_CONTENT: """Analyze the main content area of this window.

IDENTIFY:
1. Primary interactive elements (buttons, inputs, links)
2. Text content and headings
3. Images or icons
4. Lists, tables, or grids
5. Form fields
6. Scrollable areas

OUTPUT FORMAT (JSON):
{
    "elements": [
        {"type": "button", "label": "Save", "clickable": true},
        {"type": "input", "label": "Search field", "editable": true},
        {"type": "text", "label": "Document content..."}
    ],
    "scroll_position": "top",
    "focus_element": "Search field",
    "confidence": 0.85
}""",

    ScreenRegion.TITLE_BAR: """Analyze this window title bar.

IDENTIFY:
1. Window title text
2. Application icon
3. Minimize button
4. Maximize/restore button
5. Close button
6. Any toolbar buttons (back, forward, menu)

OUTPUT FORMAT (JSON):
{
    "title": "Document1 - Microsoft Word",
    "app_name": "Microsoft Word",
    "elements": [
        {"type": "button", "label": "minimize", "position": "right"},
        {"type": "button", "label": "maximize", "position": "right"},
        {"type": "button", "label": "close", "position": "right"}
    ],
    "is_maximized": false,
    "confidence": 0.95
}""",

    ScreenRegion.DIALOG: """Analyze this dialog or modal window.

IDENTIFY:
1. Dialog title
2. Message or content text
3. Action buttons (OK, Cancel, Yes, No, etc.)
4. Input fields if present
5. Checkboxes or options
6. Close button

OUTPUT FORMAT (JSON):
{
    "title": "Save Changes?",
    "message": "Do you want to save changes before closing?",
    "buttons": [
        {"label": "Save", "type": "primary"},
        {"label": "Don't Save", "type": "secondary"},
        {"label": "Cancel", "type": "cancel"}
    ],
    "is_blocking": true,
    "confidence": 0.9
}""",

    ScreenRegion.MENU: """Analyze this menu or dropdown.

IDENTIFY:
1. Menu items with labels
2. Keyboard shortcuts shown
3. Submenus (indicated by arrows)
4. Separators between groups
5. Disabled items (grayed out)
6. Checkmarks or selection indicators

OUTPUT FORMAT (JSON):
{
    "menu_type": "context_menu",
    "items": [
        {"label": "Cut", "shortcut": "Ctrl+X", "enabled": true},
        {"label": "Copy", "shortcut": "Ctrl+C", "enabled": true},
        {"label": "Paste", "shortcut": "Ctrl+V", "enabled": false}
    ],
    "has_submenu": false,
    "confidence": 0.9
}"""
}


# Default region bounds (for 1920x1080 resolution)
DEFAULT_REGION_BOUNDS = {
    ScreenRegion.TASKBAR: RegionBounds(x=0, y=1030, width=1920, height=50),
    ScreenRegion.TITLE_BAR: RegionBounds(x=0, y=0, width=1920, height=40),
    ScreenRegion.SYSTEM_TRAY: RegionBounds(x=1600, y=1030, width=320, height=50),
    ScreenRegion.MAIN_CONTENT: RegionBounds(x=0, y=40, width=1920, height=990),
    ScreenRegion.SIDEBAR: RegionBounds(x=0, y=40, width=250, height=990),
    ScreenRegion.FULL_SCREEN: RegionBounds(x=0, y=0, width=1920, height=1080),
}


class VisionSubagent(BaseSubagent):
    """
    Subagent that analyzes a specific screen region.

    Each instance is configured with ONE region type.
    Multiple instances run in parallel, each analyzing their region.
    """

    def __init__(
        self,
        subagent_id: str,
        region: ScreenRegion,
        openrouter_client: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the vision subagent.

        Args:
            subagent_id: Unique identifier
            region: The screen region to analyze
            openrouter_client: LLM client for vision analysis
            config: Additional configuration
        """
        super().__init__(subagent_id, openrouter_client, config)
        self.region = region
        self.system_prompt = REGION_PROMPTS.get(region, "")

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities of this vision subagent."""
        return {
            "type": "vision",
            "region": self.region.value,
            "can_handle": ["element_detection", "text_extraction", "state_analysis"],
            "requires_screenshot": True
        }

    async def execute(self, context: SubagentContext) -> SubagentOutput:
        """
        Analyze the screen region in the provided screenshot.

        Args:
            context: SubagentContext with screenshot and region bounds

        Returns:
            SubagentOutput with detected elements
        """
        logger.info(f"Analyzing [{self.region.value}] region")

        # Get region bounds from params or use defaults
        bounds = self._get_region_bounds(context.params)

        # Get screenshot data
        screenshot_bytes = context.screenshot_bytes
        if not screenshot_bytes and context.screenshot_ref:
            # TODO: Fetch from Redis by reference
            pass

        if not screenshot_bytes:
            return SubagentOutput(
                success=False,
                result=None,
                error="No screenshot provided",
                confidence=0.0
            )

        # Crop region if not full screen
        cropped_image = await self._crop_region(screenshot_bytes, bounds)

        # Analyze with LLM vision if available
        if self.client:
            return await self._analyze_with_llm(cropped_image, context)

        # Fallback: basic analysis without LLM
        return self._basic_analysis(context)

    def _get_region_bounds(self, params: Dict[str, Any]) -> RegionBounds:
        """Get bounds for this region from params or defaults."""
        if "bounds" in params:
            return RegionBounds.from_dict(params["bounds"])

        # Get screen resolution from params or use default
        screen_width = params.get("screen_width", 1920)
        screen_height = params.get("screen_height", 1080)

        # Scale default bounds to screen resolution
        default = DEFAULT_REGION_BOUNDS.get(self.region, DEFAULT_REGION_BOUNDS[ScreenRegion.FULL_SCREEN])

        scale_x = screen_width / 1920
        scale_y = screen_height / 1080

        return RegionBounds(
            x=int(default.x * scale_x),
            y=int(default.y * scale_y),
            width=int(default.width * scale_x),
            height=int(default.height * scale_y)
        )

    async def _crop_region(self, screenshot_bytes: bytes, bounds: RegionBounds) -> bytes:
        """Crop the screenshot to the region bounds."""
        try:
            from PIL import Image
            import io

            # Load image
            image = Image.open(io.BytesIO(screenshot_bytes))

            # Crop to bounds
            cropped = image.crop((
                bounds.x,
                bounds.y,
                bounds.x + bounds.width,
                bounds.y + bounds.height
            ))

            # Convert back to bytes
            output = io.BytesIO()
            cropped.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.warning(f"Failed to crop region: {e}, using full image")
            return screenshot_bytes

    async def _analyze_with_llm(self, image_bytes: bytes, context: SubagentContext) -> SubagentOutput:
        """Use LLM vision to analyze the region."""
        try:
            import json
            import re

            # Encode image as base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')

            # Build prompt
            user_prompt = f"""Analyze this {self.region.value} region screenshot.

{self.system_prompt}

Additional context:
- Active app: {context.active_app or 'Unknown'}
- Looking for: {context.params.get('look_for', 'all elements')}

Return ONLY valid JSON with the analysis."""

            # Call LLM with vision
            response = await self.client.chat_completion(
                model="openai/gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a UI analysis expert. Analyze screenshots and identify UI elements precisely."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=1000
            )

            # Parse response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                analysis_data = json.loads(json_match.group())

                # Convert to DetectedElement objects
                elements = []
                for elem_data in analysis_data.get("elements", []):
                    elements.append(DetectedElement(
                        element_type=elem_data.get("type", "unknown"),
                        label=elem_data.get("label", ""),
                        bounds=RegionBounds(0, 0, 0, 0),  # Position from LLM if available
                        confidence=elem_data.get("confidence", 0.8),
                        clickable=elem_data.get("clickable", False),
                        editable=elem_data.get("editable", False),
                        state=elem_data.get("state", "normal"),
                        metadata=elem_data
                    ))

                return SubagentOutput(
                    success=True,
                    result={
                        "region": self.region.value,
                        "elements": [e.to_dict() for e in elements],
                        "analysis": analysis_data,
                        "element_count": len(elements)
                    },
                    confidence=analysis_data.get("confidence", 0.8),
                    reasoning=f"LLM analysis of {self.region.value}"
                )
            else:
                raise ValueError("No JSON found in LLM response")

        except Exception as e:
            logger.error(f"LLM vision analysis failed: {e}")
            return self._basic_analysis(context)

    def _basic_analysis(self, context: SubagentContext) -> SubagentOutput:
        """
        Basic analysis without LLM.

        Returns placeholder results based on region type.
        """
        # Region-specific basic analysis
        if self.region == ScreenRegion.TASKBAR:
            elements = [
                DetectedElement("button", "Start", RegionBounds(0, 0, 50, 50), clickable=True),
                DetectedElement("icon", "Search", RegionBounds(50, 0, 50, 50), clickable=True),
            ]
        elif self.region == ScreenRegion.TITLE_BAR:
            elements = [
                DetectedElement("button", "minimize", RegionBounds(1800, 0, 40, 40), clickable=True),
                DetectedElement("button", "maximize", RegionBounds(1840, 0, 40, 40), clickable=True),
                DetectedElement("button", "close", RegionBounds(1880, 0, 40, 40), clickable=True),
            ]
        elif self.region == ScreenRegion.SYSTEM_TRAY:
            elements = [
                DetectedElement("icon", "Network", RegionBounds(0, 0, 30, 30)),
                DetectedElement("icon", "Sound", RegionBounds(30, 0, 30, 30)),
                DetectedElement("text", "Clock", RegionBounds(60, 0, 80, 30)),
            ]
        else:
            elements = []

        return SubagentOutput(
            success=True,
            result={
                "region": self.region.value,
                "elements": [e.to_dict() for e in elements],
                "element_count": len(elements),
                "analysis_type": "basic"
            },
            confidence=0.5,
            reasoning="Basic analysis without LLM"
        )


# Runner for the vision subagent
from core.subagent_runner import SubagentRunner, SubagentType, SubagentTask, SubagentResult


class VisionSubagentRunner(SubagentRunner):
    """
    Runner that wraps VisionSubagent for Redis stream processing.

    Listens to moire:vision stream and processes tasks.
    """

    def __init__(
        self,
        redis_client,
        region: ScreenRegion,
        worker_id: Optional[str] = None,
        openrouter_client: Optional[Any] = None
    ):
        super().__init__(
            redis_client=redis_client,
            agent_type=SubagentType.VISION,
            worker_id=worker_id or f"vision_{region.value}"
        )
        self.region = region
        self.subagent = VisionSubagent(
            subagent_id=self.worker_id,
            region=region,
            openrouter_client=openrouter_client
        )

    async def execute(self, task: SubagentTask) -> SubagentResult:
        """Process a vision analysis task."""
        # Build context from task params
        context = SubagentContext(
            task_id=task.task_id,
            goal=f"Analyze {self.region.value} region",
            params=task.params,
            screenshot_bytes=task.params.get("screenshot_bytes"),
            screenshot_ref=task.params.get("screenshot_ref"),
            active_app=task.params.get("active_app"),
            timeout=task.timeout
        )

        # Execute vision analysis
        output = await self.subagent.process(context)

        return SubagentResult(
            success=output.success,
            result=output.result,
            confidence=output.confidence,
            error=output.error
        )


# Convenience function to start vision workers
async def start_vision_workers(
    redis_client,
    openrouter_client=None,
    regions: List[ScreenRegion] = None
) -> List[VisionSubagentRunner]:
    """
    Start vision subagent workers for specified regions.

    Args:
        redis_client: Connected RedisStreamClient
        openrouter_client: Optional LLM client for vision analysis
        regions: List of regions to analyze (default: common regions)

    Returns:
        List of running VisionSubagentRunner instances
    """
    import asyncio

    # Default to common regions
    if regions is None:
        regions = [
            ScreenRegion.TASKBAR,
            ScreenRegion.MAIN_CONTENT,
            ScreenRegion.TITLE_BAR,
            ScreenRegion.SYSTEM_TRAY
        ]

    runners = []

    for region in regions:
        runner = VisionSubagentRunner(
            redis_client=redis_client,
            region=region,
            openrouter_client=openrouter_client
        )
        runners.append(runner)
        asyncio.create_task(runner.run_forever())
        logger.info(f"Started vision worker: {region.value}")

    return runners
