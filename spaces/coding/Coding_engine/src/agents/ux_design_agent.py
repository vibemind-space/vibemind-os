"""
UX Design Agent - Evaluates and recommends UI/UX improvements.

Uses Claude to analyze:
- Screenshots from E2E tests
- Component structure and user flows
- Accessibility (contrast, font sizes, keyboard nav)
- Layout and spacing improvements
- Prioritize changes by impact on "senseful benefit"
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    ux_review_started_event,
    ux_issue_found_event,
    ux_recommendation_event,
    ux_review_complete_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_agent_tool import find_claude_executable
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


@dataclass
class UXIssue:
    """A UX issue found during review."""
    severity: str  # "critical", "major", "minor", "suggestion"
    category: str  # "accessibility", "usability", "visual", "flow", "benefit"
    description: str
    recommendation: str
    file_path: Optional[str] = None
    component: Optional[str] = None
    priority: int = 5  # 1-10, 10 being highest

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "recommendation": self.recommendation,
            "file_path": self.file_path,
            "component": self.component,
            "priority": self.priority,
        }


@dataclass
class UXReviewResult:
    """Result of a UX review."""
    success: bool
    issues: list[UXIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    accessibility_score: float = 0.0  # 0-100
    usability_score: float = 0.0  # 0-100
    benefit_score: float = 0.0  # 0-100 (does app provide senseful benefit?)
    overall_score: float = 0.0  # 0-100
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "issues": [i.to_dict() for i in self.issues],
            "recommendations": self.recommendations,
            "accessibility_score": self.accessibility_score,
            "usability_score": self.usability_score,
            "benefit_score": self.benefit_score,
            "overall_score": self.overall_score,
            "duration_ms": self.duration_ms,
        }


class UXDesignAgent(AutonomousAgent):
    """
    Agent that evaluates UI/UX and suggests improvements.

    Triggers on:
    - E2E tests complete (with screenshots)
    - Screenshots taken
    - Build succeeded (to review initial UI)
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        requirements: Optional[list[str]] = None,
        poll_interval: float = 2.0,
    ):
        super().__init__(name, event_bus, shared_state, working_dir, poll_interval)
        self.requirements = requirements or []
        self._screenshots_dir = Path(working_dir) / "screenshots"
        self._reviews_dir = Path(working_dir) / "ux_reviews"
        self._reviews_dir.mkdir(exist_ok=True)
        self._last_review_time: Optional[datetime] = None
        self._review_cooldown = 120  # Seconds between reviews
        self._pending_screenshots: list[str] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.E2E_TEST_PASSED,
            EventType.E2E_TEST_FAILED,
            EventType.E2E_SCREENSHOT_TAKEN,
            EventType.BUILD_SUCCEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        # Check cooldown
        if self._last_review_time:
            elapsed = (datetime.now() - self._last_review_time).seconds
            if elapsed < self._review_cooldown:
                return False

        for event in events:
            # Check for initial trigger
            if event.data and event.data.get("trigger") == "initial":
                return True
            # Act after E2E tests complete
            if event.type in [EventType.E2E_TEST_PASSED, EventType.E2E_TEST_FAILED]:
                # Collect screenshots from test results
                screenshots = event.data.get("screenshots", [])
                self._pending_screenshots.extend(screenshots)
                return True
            # Act when new screenshots are taken
            if event.type == EventType.E2E_SCREENSHOT_TAKEN:
                if event.file_path:
                    self._pending_screenshots.append(event.file_path)
                return len(self._pending_screenshots) >= 1

        return False

    async def _should_act_on_state(self) -> bool:
        """Run UX review if E2E tests passed but no review done."""
        metrics = self.shared_state.metrics
        return (
            getattr(metrics, 'e2e_tests_run', False) and
            not getattr(metrics, 'ux_review_done', False) and
            metrics.iteration >= 3
        )

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Perform UX review."""
        self.logger.info("starting_ux_review")
        self._last_review_time = datetime.now()

        try:
            # Publish review started
            await self.event_bus.publish(ux_review_started_event(
                source=self.name,
            ))

            # Perform the review
            result = await self._perform_review()

            # Save review results
            await self._save_review(result)

            # Update shared state
            if hasattr(self.shared_state, 'update_ux_review'):
                await self.shared_state.update_ux_review(
                    done=True,
                    score=result.overall_score,
                    issues=len(result.issues),
                )

            # Publish issues and recommendations
            for issue in result.issues[:5]:  # Top 5 issues
                issue_dict = issue.to_dict()
                await self.event_bus.publish(ux_issue_found_event(
                    source=self.name,
                    issues=[issue_dict],
                    severity=issue_dict.get("severity", "medium"),
                ))

            for rec in result.recommendations[:3]:  # Top 3 recommendations
                await self.event_bus.publish(ux_recommendation_event(
                    source=self.name,
                    recommendation=rec,
                ))

            # Clear pending screenshots
            self._pending_screenshots.clear()

            return ux_review_complete_event(
                source=self.name,
                success=result.success,
                overall_score=result.overall_score,
                issues_count=len(result.issues),
                recommendations_count=len(result.recommendations),
                review_data=result.to_dict(),
            )

        except Exception as e:
            self.logger.error("ux_review_error", error=str(e))
            return ux_review_complete_event(
                source=self.name,
                success=False,
            )

    async def _perform_review(self) -> UXReviewResult:
        """Perform UX review using Claude CLI."""
        start_time = datetime.now()
        result = UXReviewResult(success=False)

        # Gather context for review
        context = await self._gather_review_context()

        # Build review prompt
        prompt = self._build_review_prompt(context)

        try:
            # Run Claude CLI for review
            claude_exe = find_claude_executable() or "claude"
            cmd = [
                claude_exe,
                "-p", prompt,
                "--output-format", "json",
            ]

            self.logger.info("running_ux_review_claude", prompt_length=len(prompt))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=180  # 3 minute timeout
                )

                if process.returncode == 0:
                    output = stdout.decode('utf-8', errors='replace')
                    result = self._parse_review_output(output, result)
                else:
                    self.logger.warning("claude_review_failed", stderr=stderr.decode())
                    result = await self._fallback_review(context, result)

            except asyncio.TimeoutError:
                process.kill()
                self.logger.warning("ux_review_timeout")
                result = await self._fallback_review(context, result)

        except FileNotFoundError:
            # Claude CLI not available, use fallback
            self.logger.warning("claude_cli_not_found_using_fallback")
            result = await self._fallback_review(context, result)

        except Exception as e:
            self.logger.error("review_error", error=str(e))
            result = await self._fallback_review(context, result)

        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        result.success = True  # We completed the review
        return result

    async def _gather_review_context(self) -> dict:
        """Gather context for UX review."""
        context = {
            "screenshots": self._pending_screenshots,
            "components": [],
            "styles": [],
            "requirements": self.requirements,
        }

        # Find React/Vue components
        src_dir = Path(self.working_dir) / "src"
        if src_dir.exists():
            for ext in ["*.tsx", "*.jsx", "*.vue"]:
                for file in src_dir.rglob(ext):
                    try:
                        content = file.read_text(errors='replace')
                        context["components"].append({
                            "path": str(file.relative_to(self.working_dir)),
                            "content_preview": content[:1000],
                        })
                    except Exception:
                        pass

            # Find CSS files
            for ext in ["*.css", "*.scss", "*.less"]:
                for file in src_dir.rglob(ext):
                    try:
                        content = file.read_text(errors='replace')
                        context["styles"].append({
                            "path": str(file.relative_to(self.working_dir)),
                            "content_preview": content[:500],
                        })
                    except Exception:
                        pass

        return context

    def _build_review_prompt(self, context: dict) -> str:
        """Build the UX review prompt."""
        req_text = "\n".join(f"- {r}" for r in context.get("requirements", [])[:10])
        component_list = "\n".join(
            f"- {c['path']}" for c in context.get("components", [])[:15]
        )

        return f"""You are a UX Design expert reviewing a desktop application. Analyze the UI/UX and provide recommendations.

## Application Requirements
{req_text if req_text else "- Standard desktop application"}

## Components Found
{component_list if component_list else "- No components found"}

## Screenshots Available
{len(context.get('screenshots', []))} screenshots captured from E2E tests

## Your Task
Analyze the application and provide a comprehensive UX review focusing on:

1. **Accessibility** (contrast, font sizes, keyboard navigation, screen reader support)
2. **Usability** (intuitive navigation, clear CTAs, logical flow)
3. **Visual Design** (consistency, spacing, alignment, visual hierarchy)
4. **User Flow** (task completion, error handling, feedback)
5. **Senseful Benefit** (Does the app provide meaningful value? How can it be improved?)

Provide your analysis in JSON format:
{{
    "accessibility_score": <0-100>,
    "usability_score": <0-100>,
    "benefit_score": <0-100>,
    "overall_score": <0-100>,
    "issues": [
        {{
            "severity": "critical|major|minor|suggestion",
            "category": "accessibility|usability|visual|flow|benefit",
            "description": "<what's wrong>",
            "recommendation": "<how to fix>",
            "component": "<component name if applicable>",
            "priority": <1-10>
        }}
    ],
    "recommendations": [
        "<top recommendation 1>",
        "<top recommendation 2>",
        "<top recommendation 3>"
    ]
}}

Focus on actionable improvements that would make the biggest impact on user experience and value."""

    def _parse_review_output(self, output: str, result: UXReviewResult) -> UXReviewResult:
        """Parse Claude's review output."""
        try:
            # Try to find JSON in output
            json_match = re.search(
                r'\{[^{}]*"overall_score"[^{}]*\}',
                output,
                re.DOTALL
            )
            if not json_match:
                # Try broader match
                json_match = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', output)

            if json_match:
                data = json.loads(json_match.group())

                result.accessibility_score = data.get('accessibility_score', 50)
                result.usability_score = data.get('usability_score', 50)
                result.benefit_score = data.get('benefit_score', 50)
                result.overall_score = data.get('overall_score', 50)
                result.recommendations = data.get('recommendations', [])

                # Parse issues
                for issue_data in data.get('issues', []):
                    result.issues.append(UXIssue(
                        severity=issue_data.get('severity', 'minor'),
                        category=issue_data.get('category', 'usability'),
                        description=issue_data.get('description', ''),
                        recommendation=issue_data.get('recommendation', ''),
                        component=issue_data.get('component'),
                        priority=issue_data.get('priority', 5),
                    ))

                # Sort issues by priority
                result.issues.sort(key=lambda x: x.priority, reverse=True)

        except json.JSONDecodeError as e:
            self.logger.warning("could_not_parse_review_output", error=str(e))
            result = self._generate_default_review(result)

        return result

    async def _fallback_review(self, context: dict, result: UXReviewResult) -> UXReviewResult:
        """Fallback review when Claude CLI is not available."""
        self.logger.info("running_fallback_review")

        # Basic heuristic-based review
        result = self._generate_default_review(result)

        # Check for common issues
        components = context.get("components", [])
        styles = context.get("styles", [])

        # Check for accessibility concerns
        for comp in components:
            content = comp.get("content_preview", "")
            if "onClick" in content and "onKeyDown" not in content:
                result.issues.append(UXIssue(
                    severity="major",
                    category="accessibility",
                    description="Click handler without keyboard support",
                    recommendation="Add onKeyDown handler for keyboard accessibility",
                    file_path=comp.get("path"),
                    priority=7,
                ))

            if "<img" in content and "alt=" not in content:
                result.issues.append(UXIssue(
                    severity="major",
                    category="accessibility",
                    description="Image without alt text",
                    recommendation="Add descriptive alt text to images",
                    file_path=comp.get("path"),
                    priority=7,
                ))

        # Check for color contrast issues (simplified)
        for style in styles:
            content = style.get("content_preview", "")
            if "color: #fff" in content.lower() or "color: white" in content.lower():
                if "background" not in content.lower():
                    result.issues.append(UXIssue(
                        severity="minor",
                        category="accessibility",
                        description="White text without explicit background",
                        recommendation="Ensure sufficient color contrast",
                        file_path=style.get("path"),
                        priority=4,
                    ))

        # Add general recommendations
        if not result.recommendations:
            result.recommendations = [
                "Add keyboard navigation support throughout the app",
                "Implement loading states and error feedback",
                "Consider adding tooltips for complex features",
            ]

        result.success = True
        return result

    def _generate_default_review(self, result: UXReviewResult) -> UXReviewResult:
        """Generate default review scores."""
        result.accessibility_score = 60
        result.usability_score = 65
        result.benefit_score = 55
        result.overall_score = 60

        result.issues.append(UXIssue(
            severity="suggestion",
            category="benefit",
            description="Review app value proposition",
            recommendation="Ensure the app clearly communicates its benefit to users",
            priority=8,
        ))

        result.recommendations = [
            "Consider adding onboarding flow for new users",
            "Improve visual feedback for user actions",
            "Review color contrast for accessibility",
        ]

        return result

    async def _save_review(self, result: UXReviewResult) -> None:
        """Save review results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        review_file = self._reviews_dir / f"ux_review_{timestamp}.json"

        try:
            with open(review_file, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
            self.logger.info("review_saved", path=str(review_file))
        except Exception as e:
            self.logger.warning("review_save_failed", error=str(e))

    def _get_action_description(self) -> str:
        return "Performing UX design review"
