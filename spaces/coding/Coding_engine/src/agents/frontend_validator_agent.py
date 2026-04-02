"""
Frontend Validator Agent - Validates UI against requirements using Playwright.

This agent:
1. Captures screenshots of the running app via MCP Playwright
2. Analyzes UI elements and layout
3. Compares against requirements
4. Reports mismatches and suggests fixes

Works in the Society of Mind as a quality gate before deployment.
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime

import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    ux_review_complete_event,
    code_fix_needed_event,
    ux_issue_found_event,
)
from ..mind.shared_state import SharedState
from ..autogen.cli_wrapper import ClaudeCLI
from ..mcp import MCPServerManager

logger = structlog.get_logger(__name__)


@dataclass
class UIValidationResult:
    """Result of UI validation against requirements."""
    passed: bool
    score: float  # 0.0 to 1.0
    requirements_matched: list[str] = field(default_factory=list)
    requirements_missing: list[str] = field(default_factory=list)
    ui_issues: list[dict] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "requirements_matched": self.requirements_matched,
            "requirements_missing": self.requirements_missing,
            "ui_issues": self.ui_issues,
            "screenshots": self.screenshots,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp,
        }


class FrontendValidatorAgent(AutonomousAgent):
    """
    Autonomous agent that validates frontend UI against requirements.

    Uses Playwright via MCP to:
    - Navigate to the running app
    - Take screenshots
    - Analyze DOM structure
    - Compare UI elements with requirements
    - Report discrepancies

    Triggers on:
    - BUILD_SUCCEEDED: After successful build
    - PREVIEW_READY: When dev server is running

    Publishes:
    - UX_REVIEW_COMPLETE: With validation results
    - CODE_FIX_NEEDED: If UI doesn't match requirements
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        preview_url: str = "http://localhost:5173",
        requirements_path: Optional[str] = None,
        validation_threshold: float = 0.8,
        **kwargs,
    ):
        super().__init__(
            name="FrontendValidator",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.preview_url = preview_url
        self.requirements_path = requirements_path
        self.validation_threshold = validation_threshold
        self.mcp_manager: Optional[MCPServerManager] = None
        self._last_validation: Optional[UIValidationResult] = None

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.PREVIEW_READY,
            EventType.CODE_FIXED,  # Re-validate after fixes
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide whether to validate UI."""
        # Act if we received relevant events
        for event in events:
            if event.type in [EventType.BUILD_SUCCEEDED, EventType.PREVIEW_READY]:
                return True
            # Re-validate after code was fixed (if it was a UI fix)
            if event.type == EventType.CODE_FIXED:
                if event.data.get("fix_type") == "ui":
                    return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Validate the frontend UI against requirements."""
        self.logger.info("starting_ui_validation", preview_url=self.preview_url)

        try:
            # Initialize MCP manager with Playwright
            if not self.mcp_manager:
                self.mcp_manager = MCPServerManager(working_dir=self.working_dir)
                await self.mcp_manager.start_from_template("playwright")

            # Load requirements
            requirements = await self._load_requirements()

            # Run validation via Claude CLI with Playwright
            result = await self._validate_ui(requirements)

            # Store result
            self._last_validation = result

            # Update shared state
            self.shared_state.set(
                "ui_validation",
                result.to_dict(),
            )
            self.shared_state.set("ui_validation_score", result.score)

            # Determine what event to publish
            if result.passed:
                self.logger.info(
                    "ui_validation_passed",
                    score=result.score,
                    matched=len(result.requirements_matched),
                )
                return ux_review_complete_event(
                    source=self.name,
                    success=True,
                    overall_score=result.score,
                    review_data={
                        "passed": True,
                        "result": result.to_dict(),
                    },
                )
            else:
                self.logger.warning(
                    "ui_validation_failed",
                    score=result.score,
                    missing=len(result.requirements_missing),
                    issues=len(result.ui_issues),
                )
                return code_fix_needed_event(
                    source=self.name,
                    fix_type="ui",
                    error_message="UI does not match requirements",
                    data={
                        "missing_requirements": result.requirements_missing,
                        "ui_issues": result.ui_issues,
                        "recommendations": result.recommendations,
                        "validation_result": result.to_dict(),
                    },
                )

        except Exception as e:
            self.logger.error("ui_validation_error", error=str(e))
            return ux_issue_found_event(
                source=self.name,
                issues=[{"error": str(e), "url": self.preview_url}],
            )

    async def _load_requirements(self) -> dict:
        """Load requirements from file."""
        if self.requirements_path:
            req_path = Path(self.requirements_path)
        else:
            # Try to find requirements in working dir
            for name in ["requirements.json", "requirements.yaml", "package.json"]:
                req_path = Path(self.working_dir) / name
                if req_path.exists():
                    break
            else:
                return {}

        if not req_path.exists():
            return {}

        try:
            with open(req_path, "r", encoding="utf-8") as f:
                if req_path.suffix == ".json":
                    return json.load(f)
                elif req_path.suffix in [".yaml", ".yml"]:
                    import yaml
                    return yaml.safe_load(f)
        except Exception as e:
            self.logger.warning("requirements_load_failed", error=str(e))
            return {}

        return {}

    async def _validate_ui(self, requirements: dict) -> UIValidationResult:
        """
        Validate UI against requirements using Claude CLI with Playwright.

        This method:
        1. Uses MCP Playwright to navigate and screenshot
        2. Asks Claude to analyze the UI
        3. Compares with requirements
        """
        # Build validation prompt
        features = requirements.get("features", [])
        feature_list = "\n".join([
            f"- {f.get('name', f.get('id', 'unnamed'))}: {f.get('description', '')}"
            for f in features
        ]) if features else "No specific features defined"

        prompt = f"""You have access to Playwright MCP tools for browser automation.

## Task: Validate Frontend UI

Navigate to: {self.preview_url}

## Requirements to Validate:
{feature_list}

## Instructions:

1. Use browser_navigate to go to the app URL
2. Use browser_snapshot to get the accessibility tree
3. Take a screenshot using browser_take_screenshot
4. Analyze the UI and check if it matches the requirements

## Respond with JSON:
```json
{{
    "score": 0.85,
    "requirements_matched": ["feature_1", "feature_2"],
    "requirements_missing": ["feature_3"],
    "ui_issues": [
        {{"element": "button", "issue": "Missing submit button"}}
    ],
    "recommendations": [
        "Add a submit button to the form"
    ],
    "observations": "The app loads correctly..."
}}
```

Be thorough but fair in your assessment."""

        # Execute via Claude CLI with MCP
        cli = ClaudeCLI(
            working_dir=self.working_dir,
            mcp_manager=self.mcp_manager,
            enable_playwright=True,
        )

        response = await cli.execute(prompt, output_format="text", use_mcp=True)

        if not response.success:
            return UIValidationResult(
                passed=False,
                score=0.0,
                ui_issues=[{"error": response.error}],
            )

        # Parse response
        return self._parse_validation_response(response.output, requirements)

    def _parse_validation_response(
        self,
        output: str,
        requirements: dict,
    ) -> UIValidationResult:
        """Parse Claude's validation response."""
        import re

        # Try to extract JSON from response
        json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)

        if json_match:
            try:
                data = json.loads(json_match.group(1))
                score = data.get("score", 0.5)
                return UIValidationResult(
                    passed=score >= self.validation_threshold,
                    score=score,
                    requirements_matched=data.get("requirements_matched", []),
                    requirements_missing=data.get("requirements_missing", []),
                    ui_issues=data.get("ui_issues", []),
                    recommendations=data.get("recommendations", []),
                )
            except json.JSONDecodeError:
                pass

        # Fallback: Basic text analysis
        lower_output = output.lower()

        # Simple heuristics
        has_errors = "error" in lower_output or "failed" in lower_output
        has_success = "success" in lower_output or "passed" in lower_output or "looks good" in lower_output

        if has_errors and not has_success:
            score = 0.3
        elif has_success and not has_errors:
            score = 0.9
        else:
            score = 0.6

        return UIValidationResult(
            passed=score >= self.validation_threshold,
            score=score,
            ui_issues=[{"observation": output[:500]}] if not has_success else [],
            recommendations=["Review UI manually"] if not has_success else [],
        )

    def _get_action_description(self) -> str:
        """Description of current action for status updates."""
        return f"Validating UI at {self.preview_url}"

    async def cleanup(self) -> None:
        """Clean up MCP resources."""
        if self.mcp_manager:
            await self.mcp_manager.stop_all()
            self.mcp_manager = None

    @property
    def last_validation(self) -> Optional[UIValidationResult]:
        """Get the last validation result."""
        return self._last_validation
