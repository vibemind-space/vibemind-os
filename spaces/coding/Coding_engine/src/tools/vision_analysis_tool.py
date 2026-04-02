"""
Vision Analysis Tool - Screenshot analysis using Claude Vision API.

Uses Claude's multimodal capabilities to:
- Analyze UI screenshots
- Detect interactive elements
- Identify layout issues
- Generate interaction plans for E2E testing
"""

import asyncio
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import structlog

from ..config import get_settings
from src.llm_config import get_model

logger = structlog.get_logger(__name__)


@dataclass
class VisualElement:
    """An element identified in a screenshot."""
    element_type: str  # "button", "input", "text", "link", "image", "container"
    label: str
    state: str = "enabled"  # "enabled", "disabled", "focused", "hidden"
    selector_hint: Optional[str] = None
    bounding_box: Optional[dict] = None  # {"x": int, "y": int, "width": int, "height": int}
    accessibility_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "element_type": self.element_type,
            "label": self.label,
            "state": self.state,
            "selector_hint": self.selector_hint,
            "bounding_box": self.bounding_box,
            "accessibility_issues": self.accessibility_issues,
        }


@dataclass
class InteractionStep:
    """A step in an interaction plan."""
    action: str  # "click", "type", "scroll", "wait", "hover", "navigate"
    target: str  # Element description or selector
    value: Optional[str] = None  # For "type" action
    expected_result: str = ""
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "target": self.target,
            "value": self.value,
            "expected_result": self.expected_result,
            "rationale": self.rationale,
        }


@dataclass
class VisualAnalysisResult:
    """Result of visual analysis of a screenshot."""
    success: bool
    screenshot_path: str
    elements: list[VisualElement] = field(default_factory=list)
    layout_issues: list[str] = field(default_factory=list)
    accessibility_score: float = 0.0  # 0-100
    usability_observations: list[str] = field(default_factory=list)
    interaction_plan: list[InteractionStep] = field(default_factory=list)
    debugging_hints: list[str] = field(default_factory=list)
    raw_response: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "screenshot_path": self.screenshot_path,
            "elements": [e.to_dict() for e in self.elements],
            "layout_issues": self.layout_issues,
            "accessibility_score": self.accessibility_score,
            "usability_observations": self.usability_observations,
            "interaction_plan": [s.to_dict() for s in self.interaction_plan],
            "debugging_hints": self.debugging_hints,
            "error": self.error,
        }


@dataclass
class DebuggingPlan:
    """A plan for debugging based on visual analysis."""
    root_cause_hypothesis: str
    visual_symptoms: list[str] = field(default_factory=list)
    suggested_checks: list[str] = field(default_factory=list)
    interaction_steps: list[InteractionStep] = field(default_factory=list)
    files_to_investigate: list[str] = field(default_factory=list)
    fix_priority: str = "medium"  # "critical", "high", "medium", "low"

    def to_dict(self) -> dict:
        return {
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "visual_symptoms": self.visual_symptoms,
            "suggested_checks": self.suggested_checks,
            "interaction_steps": [s.to_dict() for s in self.interaction_steps],
            "files_to_investigate": self.files_to_investigate,
            "fix_priority": self.fix_priority,
        }


class VisionAnalysisTool:
    """
    Tool for analyzing screenshots using Claude's vision capabilities.

    Provides:
    - Screenshot encoding (PNG/JPEG to base64)
    - Vision-based UI analysis
    - Element detection and state identification
    - Interaction plan generation
    - Debugging hints from visual inspection
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
        max_tokens: int = 4096,
    ):
        """
        Initialize the vision analysis tool.

        Args:
            api_key: Anthropic API key (defaults to settings)
            model: Model to use for vision analysis
            max_tokens: Maximum tokens for response
        """
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or get_model("primary")
        self.max_tokens = max_tokens
        self.client = None
        self.logger = logger.bind(tool="vision_analysis")

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self.logger.info("vision_tool_initialized", model=model)
            except ImportError:
                self.logger.warning("anthropic_sdk_not_installed")
        else:
            self.logger.warning("no_api_key_configured")

    @property
    def enabled(self) -> bool:
        """Check if vision analysis is available."""
        return self.client is not None

    def _encode_image(self, path: str) -> tuple[str, str]:
        """
        Encode image to base64 and detect media type.

        Args:
            path: Path to image file

        Returns:
            Tuple of (base64_data, media_type)
        """
        path_obj = Path(path)
        suffix = path_obj.suffix.lower()

        media_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }

        media_type = media_type_map.get(suffix, "image/png")

        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        return image_data, media_type

    def _build_analysis_prompt(
        self,
        analysis_type: str = "full_analysis",
        requirements: Optional[list[str]] = None,
        context: Optional[str] = None,
    ) -> str:
        """Build structured analysis prompt."""
        prompts = {
            "full_analysis": f"""Analyze this screenshot of a web application UI.

{f"Requirements being tested:{chr(10)}{chr(10).join(f'- {r}' for r in requirements[:10])}" if requirements else ""}

Identify and report:

1. **Interactive Elements**: All clickable/interactive elements (buttons, links, inputs, dropdowns)
2. **Navigation**: Menu items, tabs, breadcrumbs
3. **Layout Issues**: Alignment problems, overlapping elements, broken layouts
4. **Accessibility**: Contrast issues, missing labels, small touch targets
5. **Usability**: Unclear labels, confusing navigation, missing feedback
6. **Suggested Tests**: Steps to verify functionality

Respond in JSON format:
{{
    "elements": [
        {{"element_type": "button", "label": "Submit", "state": "enabled", "selector_hint": "button.submit"}},
        ...
    ],
    "layout_issues": ["Issue 1", "Issue 2"],
    "accessibility_score": 75,
    "usability_observations": ["Observation 1"],
    "interaction_plan": [
        {{"action": "click", "target": "Submit button", "expected_result": "Form submits"}}
    ],
    "debugging_hints": ["Check event handler on button"]
}}""",

            "interaction_plan": f"""Based on this screenshot, create an interaction plan to test the UI.

Goal: {context or "Explore and test all interactive elements"}

Create a step-by-step test plan that:
1. Identifies all interactive elements
2. Tests each element's functionality
3. Verifies expected behaviors

Respond in JSON format:
{{
    "steps": [
        {{"action": "click|type|scroll|wait", "target": "element description", "value": "optional", "expected_result": "what should happen", "rationale": "why this test"}},
        ...
    ]
}}""",

            "debugging": f"""Analyze this screenshot to help debug an issue.

Error Context: {context or "Unknown error"}

Based on the visual state:
1. What symptoms are visible?
2. What might be causing the issue?
3. What should be checked?
4. What files might need investigation?

Respond in JSON format:
{{
    "root_cause_hypothesis": "Likely cause",
    "visual_symptoms": ["Symptom 1", "Symptom 2"],
    "suggested_checks": ["Check 1", "Check 2"],
    "files_to_investigate": ["src/component.tsx"],
    "fix_priority": "critical|high|medium|low"
}}""",
        }

        return prompts.get(analysis_type, prompts["full_analysis"])

    async def analyze_screenshot(
        self,
        screenshot_path: str,
        requirements: Optional[list[str]] = None,
    ) -> VisualAnalysisResult:
        """
        Analyze a single screenshot.

        Args:
            screenshot_path: Path to screenshot file
            requirements: Optional list of requirements to check against

        Returns:
            VisualAnalysisResult with detected elements and issues
        """
        if not self.enabled:
            return VisualAnalysisResult(
                success=False,
                screenshot_path=screenshot_path,
                error="Vision analysis not available (no API key)",
            )

        try:
            # Encode image
            image_data, media_type = self._encode_image(screenshot_path)

            # Build prompt
            prompt = self._build_analysis_prompt("full_analysis", requirements)

            # Call Claude Vision API
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            }
                        ],
                    }
                ],
            )

            # Parse response
            raw_response = response.content[0].text
            result = self._parse_analysis_response(raw_response, screenshot_path)

            self.logger.info(
                "screenshot_analyzed",
                path=screenshot_path,
                elements=len(result.elements),
                issues=len(result.layout_issues),
            )

            return result

        except Exception as e:
            self.logger.error("analysis_failed", path=screenshot_path, error=str(e))
            return VisualAnalysisResult(
                success=False,
                screenshot_path=screenshot_path,
                error=str(e),
            )

    def _parse_analysis_response(
        self,
        response: str,
        screenshot_path: str,
    ) -> VisualAnalysisResult:
        """Parse Claude's analysis response into structured result."""
        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                # Try to parse entire response as JSON
                data = json.loads(response)

            # Build elements
            elements = []
            for e in data.get("elements", []):
                elements.append(VisualElement(
                    element_type=e.get("element_type", "unknown"),
                    label=e.get("label", ""),
                    state=e.get("state", "enabled"),
                    selector_hint=e.get("selector_hint"),
                    bounding_box=e.get("bounding_box"),
                    accessibility_issues=e.get("accessibility_issues", []),
                ))

            # Build interaction plan
            interaction_plan = []
            for step in data.get("interaction_plan", []):
                interaction_plan.append(InteractionStep(
                    action=step.get("action", "click"),
                    target=step.get("target", ""),
                    value=step.get("value"),
                    expected_result=step.get("expected_result", ""),
                    rationale=step.get("rationale", ""),
                ))

            return VisualAnalysisResult(
                success=True,
                screenshot_path=screenshot_path,
                elements=elements,
                layout_issues=data.get("layout_issues", []),
                accessibility_score=float(data.get("accessibility_score", 0)),
                usability_observations=data.get("usability_observations", []),
                interaction_plan=interaction_plan,
                debugging_hints=data.get("debugging_hints", []),
                raw_response=response,
            )

        except json.JSONDecodeError as e:
            self.logger.warning("json_parse_failed", error=str(e))
            return VisualAnalysisResult(
                success=True,
                screenshot_path=screenshot_path,
                raw_response=response,
                debugging_hints=[response[:500]],  # Include raw response as hint
            )

    async def create_interaction_plan(
        self,
        screenshot_path: str,
        goal: str,
    ) -> list[InteractionStep]:
        """
        Generate an interaction plan from current UI state.

        Args:
            screenshot_path: Path to screenshot file
            goal: What the interaction plan should accomplish

        Returns:
            List of interaction steps
        """
        if not self.enabled:
            return []

        try:
            image_data, media_type = self._encode_image(screenshot_path)
            prompt = self._build_analysis_prompt("interaction_plan", context=goal)

            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            raw = response.content[0].text
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0:
                data = json.loads(raw[json_start:json_end])
                steps = []
                for s in data.get("steps", []):
                    steps.append(InteractionStep(
                        action=s.get("action", "click"),
                        target=s.get("target", ""),
                        value=s.get("value"),
                        expected_result=s.get("expected_result", ""),
                        rationale=s.get("rationale", ""),
                    ))
                return steps

            return []

        except Exception as e:
            self.logger.error("interaction_plan_failed", error=str(e))
            return []

    async def create_debugging_plan(
        self,
        screenshot_path: str,
        error_context: Optional[str] = None,
    ) -> DebuggingPlan:
        """
        Generate a debugging plan based on visual state.

        Args:
            screenshot_path: Path to screenshot file
            error_context: Optional error message or context

        Returns:
            DebuggingPlan with investigation steps
        """
        if not self.enabled:
            return DebuggingPlan(
                root_cause_hypothesis="Vision analysis not available",
            )

        try:
            image_data, media_type = self._encode_image(screenshot_path)
            prompt = self._build_analysis_prompt("debugging", context=error_context)

            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            raw = response.content[0].text
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0:
                data = json.loads(raw[json_start:json_end])
                return DebuggingPlan(
                    root_cause_hypothesis=data.get("root_cause_hypothesis", "Unknown"),
                    visual_symptoms=data.get("visual_symptoms", []),
                    suggested_checks=data.get("suggested_checks", []),
                    files_to_investigate=data.get("files_to_investigate", []),
                    fix_priority=data.get("fix_priority", "medium"),
                )

            return DebuggingPlan(root_cause_hypothesis="Could not parse response")

        except Exception as e:
            self.logger.error("debugging_plan_failed", error=str(e))
            return DebuggingPlan(root_cause_hypothesis=f"Error: {str(e)}")

    async def compare_screenshots(
        self,
        before_path: str,
        after_path: str,
        action_performed: str,
    ) -> dict:
        """
        Compare before/after screenshots to verify an action.

        Args:
            before_path: Path to screenshot before action
            after_path: Path to screenshot after action
            action_performed: Description of action that was taken

        Returns:
            Comparison result dict
        """
        if not self.enabled:
            return {"success": False, "error": "Vision analysis not available"}

        try:
            before_data, before_type = self._encode_image(before_path)
            after_data, after_type = self._encode_image(after_path)

            prompt = f"""Compare these BEFORE and AFTER screenshots.

Action performed: {action_performed}

Analyze:
1. Did the action succeed? (visible changes indicate success)
2. What changed between before/after?
3. Are there any unexpected changes or issues?

Respond in JSON format:
{{
    "action_succeeded": true/false,
    "changes_observed": ["Change 1", "Change 2"],
    "unexpected_issues": ["Issue 1"],
    "next_recommended_action": "What to do next"
}}"""

            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "BEFORE screenshot:"},
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": before_type, "data": before_data},
                            },
                            {"type": "text", "text": "AFTER screenshot:"},
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": after_type, "data": after_data},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            raw = response.content[0].text
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0:
                return json.loads(raw[json_start:json_end])

            return {"success": True, "raw_response": raw}

        except Exception as e:
            self.logger.error("comparison_failed", error=str(e))
            return {"success": False, "error": str(e)}
