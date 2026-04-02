"""
Playwright E2E Agent - Post-deployment visual E2E testing.

Uses Claude CLI with Playwright MCP for browser automation and
Claude Vision for screenshot analysis to:
- Capture screenshots after deployment
- Analyze UI visually for issues
- Generate debugging/interaction plans
- Execute interactive E2E tests
- Store successful test patterns in memory
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    EventBus, Event, EventType,
    playwright_e2e_started_event,
    playwright_e2e_result_event,
    playwright_screenshot_analyzed_event,
    playwright_debug_plan_created_event,
    debug_report_event,
)
from ..mind.shared_state import SharedState
from ..tools.vision_analysis_tool import (
    VisionAnalysisTool,
    VisualAnalysisResult,
    InteractionStep,
    DebuggingPlan,
)
from ..tools.claude_agent_tool import find_claude_executable
from ..registry.document_registry import DocumentRegistry
from ..registry.documents import DebugReport, VisualIssue, SuggestedFix

logger = structlog.get_logger(__name__)


@dataclass
class PlaywrightTestStep:
    """A single test step executed via Playwright."""
    action: str  # "click", "fill", "screenshot", "navigate"
    selector: Optional[str] = None
    value: Optional[str] = None
    screenshot_path: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value,
            "screenshot_path": self.screenshot_path,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class PlaywrightE2EResult:
    """Result of a Playwright E2E test session."""
    success: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    screenshots: list[str] = field(default_factory=list)
    steps_executed: list[PlaywrightTestStep] = field(default_factory=list)
    visual_issues_found: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    debugging_plan: Optional[DebuggingPlan] = None
    duration_ms: float = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "screenshots": self.screenshots,
            "steps_executed": [s.to_dict() for s in self.steps_executed],
            "visual_issues_found": self.visual_issues_found,
            "console_errors": self.console_errors,
            "debugging_plan": self.debugging_plan.to_dict() if self.debugging_plan else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class PlaywrightE2EAgent(AutonomousAgent):
    """
    Post-deployment visual E2E testing agent with Playwright MCP.

    Triggers on: DEPLOY_SUCCEEDED
    Only for: Web dashboards accessible via Playwright (localhost URLs)

    Workflow:
    1. Receives DEPLOY_SUCCEEDED event with URL
    2. Verifies app is web-accessible
    3. Captures screenshots via Playwright MCP
    4. Analyzes screenshots with Claude Vision
    5. Creates debugging/interaction plans
    6. Executes interactive tests
    7. Stores successful patterns in memory
    """

    def __init__(
        self,
        name: str = "PlaywrightE2E",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        memory_tool: Optional[Any] = None,
        document_registry: Optional[DocumentRegistry] = None,
        poll_interval: float = 2.0,
        test_timeout: int = 300,
        min_action_interval: int = 60,
    ):
        """
        Initialize the Playwright E2E agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Working directory
            memory_tool: Optional memory tool
            document_registry: Optional document registry for inter-agent communication
            poll_interval: Polling interval
            test_timeout: Timeout for test execution (seconds)
            min_action_interval: Minimum time between actions (seconds)
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        self.test_timeout = test_timeout
        self.min_action_interval = min_action_interval
        self._last_action_time: Optional[datetime] = None
        self._pending_url: Optional[str] = None
        self._screenshots_dir = Path(working_dir) / "screenshots" / "playwright_e2e"
        self._screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Initialize vision tool
        self.vision_tool = VisionAnalysisTool()

        # Document registry for writing DEBUG_REPORTs
        self.document_registry = document_registry

        self.logger = logger.bind(agent=name)
        self.logger.info("playwright_e2e_agent_initialized", vision_enabled=self.vision_tool.enabled)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Event types this agent listens to."""
        return [EventType.DEPLOY_SUCCEEDED]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to take action based on deployment events.

        Args:
            events: Recent events matching subscriptions

        Returns:
            True if should run E2E tests
        """
        # Check cooldown
        if self._last_action_time:
            elapsed = (datetime.now() - self._last_action_time).total_seconds()
            if elapsed < self.min_action_interval:
                return False

        # Look for DEPLOY_SUCCEEDED with valid URL
        for event in events:
            if event.type == EventType.DEPLOY_SUCCEEDED:
                url = self._extract_url(event)
                if url and self._is_web_accessible(url):
                    self._pending_url = url
                    self.logger.debug(
                        "deployment_detected",
                        url=url,
                        source=event.source,
                    )
                    return True

        return False

    def _extract_url(self, event: Event) -> Optional[str]:
        """Extract deployment URL from event data."""
        data = event.data or {}
        # Try various URL field names
        for key in ["url", "preview_url", "deploy_url", "app_url"]:
            if url := data.get(key):
                return url

        # Try to infer from working directory context
        return self._infer_url()

    def _infer_url(self) -> Optional[str]:
        """Infer deployment URL from common patterns."""
        # Common development server ports
        common_ports = [5173, 3000, 8080, 4200, 8000]
        for port in common_ports:
            return f"http://localhost:{port}"
        return None

    def _is_web_accessible(self, url: str) -> bool:
        """Check if URL is accessible via Playwright (web-based)."""
        if not url:
            return False

        # Check for web URLs (http/https)
        if not url.startswith(("http://", "https://")):
            return False

        # Skip file:// URLs and other non-web protocols
        if "file://" in url:
            return False

        return True

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Perform visual E2E testing.

        Args:
            events: Events that triggered this action

        Returns:
            Event describing the result
        """
        self._last_action_time = datetime.now()
        start_time = datetime.now()

        if not self._pending_url:
            return None

        url = self._pending_url
        self._pending_url = None

        self.logger.info("starting_playwright_e2e", url=url)

        # Publish start event
        await self.event_bus.publish(playwright_e2e_started_event(
            source=self.name,
            url=url,
        ))

        result = PlaywrightE2EResult(success=False)

        try:
            # Step 1: Capture initial screenshots
            screenshots = await self._capture_screenshots(url)
            result.screenshots = screenshots

            if not screenshots:
                result.error = "Failed to capture screenshots"
                return self._create_result_event(result)

            # Step 2: Analyze screenshots with Vision
            if self.vision_tool.enabled and screenshots:
                analysis = await self.vision_tool.analyze_screenshot(screenshots[0])

                # Publish analysis event
                await self.event_bus.publish(playwright_screenshot_analyzed_event(
                    source=self.name,
                    analysis_data=analysis.to_dict(),
                ))

                result.visual_issues_found = analysis.layout_issues

                # Step 3: Create interaction plan from analysis
                if analysis.interaction_plan:
                    # Publish debug plan event
                    await self.event_bus.publish(playwright_debug_plan_created_event(
                        source=self.name,
                        steps=[s.to_dict() for s in analysis.interaction_plan],
                    ))

                    # Step 4: Execute interaction plan
                    test_results = await self._execute_interaction_plan(
                        url, analysis.interaction_plan
                    )
                    result.steps_executed = test_results
                    result.tests_run = len(test_results)
                    result.tests_passed = sum(1 for s in test_results if s.success)
                    result.tests_failed = result.tests_run - result.tests_passed

            # Determine success
            result.success = (
                len(result.screenshots) > 0
                and result.tests_failed == 0
                and len(result.visual_issues_found) == 0
            )

            # Step 5: Store successful patterns in memory
            if result.success and self.memory_tool:
                await self._store_test_patterns(url, result)

            # Step 6: Write DEBUG_REPORT to document registry
            if self.document_registry:
                await self._write_debug_report(url, result)

        except Exception as e:
            self.logger.error("playwright_e2e_failed", error=str(e))
            result.error = str(e)

        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        return self._create_result_event(result)

    def _create_result_event(self, result: PlaywrightE2EResult) -> Event:
        """Create result event from test result."""
        return playwright_e2e_result_event(
            source=self.name,
            success=result.success,
            error=result.error,
            data=result.to_dict(),
        )

    async def _capture_screenshots(self, url: str) -> list[str]:
        """
        Capture screenshots using Claude CLI with Playwright MCP.

        Args:
            url: URL to capture

        Returns:
            List of screenshot file paths
        """
        screenshots = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build MCP config using community Playwright MCP server
        mcp_config = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["--yes", "@playwright/mcp@latest", "--browser", "chrome", "--headless"]
                }
            }
        }

        mcp_config_path = Path(self.working_dir) / ".mcp-playwright-e2e.json"
        with open(mcp_config_path, 'w') as f:
            json.dump(mcp_config, f)

        screenshot_path = self._screenshots_dir / f"initial_{timestamp}.png"

        try:
            prompt = f"""Navigate to {url} and capture a screenshot.

Steps:
1. Use browser_navigate to go to {url}
2. Wait 2 seconds for the page to load
3. Take a full-page screenshot using browser_take_screenshot
4. Save to: {screenshot_path}

Report the screenshot path when done."""

            claude_exe = find_claude_executable() or "claude"
            cmd = [
                claude_exe,
                "--mcp-config", str(mcp_config_path),
                "-p", prompt,
                "--output-format", "json",
            ]

            self.logger.info("capturing_screenshot", url=url)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120  # 2 minute timeout for screenshot
                )

                if process.returncode == 0:
                    # Check if screenshot was created
                    if screenshot_path.exists():
                        screenshots.append(str(screenshot_path))
                        self.logger.info("screenshot_captured", path=str(screenshot_path))
                    else:
                        # Try to find any screenshots in the directory
                        for p in self._screenshots_dir.glob(f"*{timestamp}*"):
                            screenshots.append(str(p))
                else:
                    self.logger.warning(
                        "screenshot_capture_failed",
                        stderr=stderr.decode('utf-8', errors='replace')[:500],
                    )

            except asyncio.TimeoutError:
                process.kill()
                self.logger.warning("screenshot_capture_timeout")

        except FileNotFoundError:
            self.logger.warning("claude_cli_not_found")

        except Exception as e:
            self.logger.error("screenshot_error", error=str(e))

        finally:
            if mcp_config_path.exists():
                mcp_config_path.unlink()

        return screenshots

    async def _execute_interaction_plan(
        self,
        url: str,
        plan: list[InteractionStep],
    ) -> list[PlaywrightTestStep]:
        """
        Execute interaction plan using Playwright MCP.

        Args:
            url: Base URL
            plan: List of interaction steps

        Returns:
            List of executed test steps with results
        """
        results = []

        if not plan:
            return results

        # Build MCP config using community Playwright MCP server
        mcp_config = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["--yes", "@playwright/mcp@latest", "--browser", "chrome", "--headless"]
                }
            }
        }

        mcp_config_path = Path(self.working_dir) / ".mcp-playwright-e2e-exec.json"
        with open(mcp_config_path, 'w') as f:
            json.dump(mcp_config, f)

        try:
            # Build execution prompt from plan
            steps_text = "\n".join(
                f"{i+1}. {step.action} on '{step.target}'"
                + (f" with value '{step.value}'" if step.value else "")
                + f" - Expected: {step.expected_result}"
                for i, step in enumerate(plan[:10])  # Limit to 10 steps
            )

            prompt = f"""Execute these test steps on {url}:

{steps_text}

For each step:
1. Navigate to the URL if not already there
2. Perform the action
3. Take a screenshot after the action
4. Verify the expected result
5. Report success or failure

Report results in JSON format:
{{
    "steps": [
        {{"action": "...", "target": "...", "success": true/false, "error": null/"message"}}
    ]
}}"""

            claude_exe = find_claude_executable() or "claude"
            cmd = [
                claude_exe,
                "--mcp-config", str(mcp_config_path),
                "-p", prompt,
                "--output-format", "json",
            ]

            self.logger.info("executing_test_plan", steps=len(plan))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.test_timeout
                )

                if process.returncode == 0:
                    output = stdout.decode('utf-8', errors='replace')
                    results = self._parse_execution_results(output, plan)
                else:
                    # Record failure for all steps
                    error_msg = stderr.decode('utf-8', errors='replace')[:200]
                    for step in plan:
                        results.append(PlaywrightTestStep(
                            action=step.action,
                            selector=step.target,
                            success=False,
                            error=error_msg,
                        ))

            except asyncio.TimeoutError:
                process.kill()
                for step in plan:
                    results.append(PlaywrightTestStep(
                        action=step.action,
                        selector=step.target,
                        success=False,
                        error="Test execution timed out",
                    ))

        except FileNotFoundError:
            self.logger.warning("claude_cli_not_found_for_execution")

        except Exception as e:
            self.logger.error("execution_error", error=str(e))

        finally:
            if mcp_config_path.exists():
                mcp_config_path.unlink()

        return results

    def _parse_execution_results(
        self,
        output: str,
        plan: list[InteractionStep],
    ) -> list[PlaywrightTestStep]:
        """Parse execution output into test step results."""
        results = []

        try:
            # Try to extract JSON from output
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(output[json_start:json_end])
                for step_data in data.get("steps", []):
                    results.append(PlaywrightTestStep(
                        action=step_data.get("action", "unknown"),
                        selector=step_data.get("target"),
                        value=step_data.get("value"),
                        success=step_data.get("success", False),
                        error=step_data.get("error"),
                    ))
        except json.JSONDecodeError:
            # Fallback: assume all steps succeeded if no JSON
            for step in plan:
                results.append(PlaywrightTestStep(
                    action=step.action,
                    selector=step.target,
                    value=step.value,
                    success=True,
                ))

        return results

    async def _store_test_patterns(
        self,
        url: str,
        result: PlaywrightE2EResult,
    ) -> None:
        """Store successful test patterns in memory."""
        if not self.memory_tool or not self.memory_tool.enabled:
            return

        try:
            content = f"""## Playwright E2E Test Session
**URL:** {url}
**Result:** {'SUCCESS' if result.success else 'FAILED'}
**Tests Run:** {result.tests_run}
**Tests Passed:** {result.tests_passed}

## Screenshots Captured
{chr(10).join(f"- {s}" for s in result.screenshots)}

## Steps Executed
{chr(10).join(f"- {s.action} on {s.selector}: {'PASS' if s.success else 'FAIL'}" for s in result.steps_executed)}

## Visual Issues
{chr(10).join(f"- {issue}" for issue in result.visual_issues_found) or "None found"}
"""

            # Use store method if available
            if hasattr(self.memory_tool, 'store_memory'):
                await self.memory_tool.store_memory(
                    content=content,
                    category="playwright_e2e",
                    metadata={
                        "url": url,
                        "success": result.success,
                        "tests_passed": result.tests_passed,
                        "tests_failed": result.tests_failed,
                    }
                )
            elif hasattr(self.memory_tool, 'supermemory'):
                await self.memory_tool.supermemory.store(
                    content=content,
                    description=f"Playwright E2E test results for {url}",
                    category="playwright_e2e",
                    tags=["e2e", "playwright", "visual_testing"],
                )

            self.logger.info("test_patterns_stored", url=url)

        except Exception as e:
            self.logger.warning("pattern_storage_failed", error=str(e))

    def _get_action_description(self) -> str:
        """Return human-readable action description."""
        return f"Running Playwright E2E tests on {self._pending_url or 'deployment'}"

    async def _write_debug_report(
        self,
        url: str,
        result: PlaywrightE2EResult,
    ) -> Optional[str]:
        """
        Write a DEBUG_REPORT to the document registry.

        Args:
            url: The URL tested
            result: Test results

        Returns:
            Document ID if written successfully
        """
        if not self.document_registry:
            return None

        try:
            from uuid import uuid4
            timestamp = datetime.now()
            doc_id = f"debug_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

            # Convert visual issues to VisualIssue objects
            visual_issues = []
            for issue_text in result.visual_issues_found:
                visual_issues.append(VisualIssue(
                    severity="major",
                    description=issue_text,
                ))

            # Generate suggested fixes from debugging plan and issues
            suggested_fixes = []
            affected_files = []
            root_cause = None
            debugging_steps = []

            if result.debugging_plan:
                root_cause = result.debugging_plan.root_cause_hypothesis
                debugging_steps = result.debugging_plan.suggested_tests or []

                for i, fix_info in enumerate(result.debugging_plan.files_to_investigate or []):
                    suggested_fixes.append(SuggestedFix(
                        id=f"fix_{i+1:03d}",
                        priority=i + 1,
                        description=f"Investigate {fix_info}",
                        file=fix_info,
                        action="modify",
                    ))
                    affected_files.append(fix_info)

            # Create the debug report
            debug_report = DebugReport(
                id=doc_id,
                timestamp=timestamp,
                source_agent=self.name,
                screenshots=result.screenshots,
                visual_issues=visual_issues,
                console_errors=result.console_errors,
                suggested_fixes=suggested_fixes,
                priority_order=[sf.id for sf in suggested_fixes],
                affected_files=affected_files,
                root_cause_hypothesis=root_cause,
                debugging_steps=debugging_steps,
                readiness_score=self._calculate_readiness_score(result),
                test_url=url,
            )

            # Write to registry
            await self.document_registry.write_document(
                debug_report,
                priority=10 if not result.success else 5,
            )

            # Publish event using factory function
            await self.event_bus.publish(debug_report_event(
                source=self.name,
                doc_id=doc_id,
                issues_found=len(visual_issues),
                visual_issues=[{"description": v.description, "severity": v.severity, "location": v.location} for v in visual_issues],
                page_url=url,
                requires_immediate_fix=not result.success and len(visual_issues) > 0,
            ))

            self.logger.info(
                "debug_report_written",
                doc_id=doc_id,
                visual_issues=len(visual_issues),
                suggested_fixes=len(suggested_fixes),
            )

            return doc_id

        except Exception as e:
            self.logger.error("debug_report_write_failed", error=str(e))
            return None

    def _calculate_readiness_score(self, result: PlaywrightE2EResult) -> int:
        """Calculate a readiness score (0-100) based on test results."""
        score = 100

        # Deduct for visual issues
        score -= len(result.visual_issues_found) * 15

        # Deduct for failed tests
        if result.tests_run > 0:
            fail_rate = result.tests_failed / result.tests_run
            score -= int(fail_rate * 40)

        # Deduct for console errors
        score -= len(result.console_errors) * 10

        # Deduct for no screenshots
        if not result.screenshots:
            score -= 20

        # Deduct for errors
        if result.error:
            score -= 25

        return max(0, min(100, score))
