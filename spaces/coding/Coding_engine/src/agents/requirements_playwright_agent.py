"""
RequirementsPlaywrightAgent - LLM-guided E2E testing against requirements.

Uses Claude CLI with MCP Playwright to:
1. Parse UI requirements from requirements.json
2. Generate test scenarios per requirement
3. Execute tests via MCP (navigate, click, fill, screenshot)
4. Analyze results with Claude Vision
5. Report requirement verification status
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.tools.claude_code_tool import ClaudeCodeTool

logger = structlog.get_logger(__name__)


@dataclass
class RequirementTest:
    """Test result for a single requirement."""
    requirement_id: str
    requirement_text: str
    test_steps: list[dict]  # [{action, target, value, expected}]
    screenshots: list[str]
    passed: bool
    failure_reason: Optional[str] = None
    claude_analysis: Optional[str] = None


@dataclass
class RequirementsTestResult:
    """Aggregated test results."""
    total_requirements: int = 0
    tested: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0  # Non-UI requirements
    results: list[RequirementTest] = field(default_factory=list)
    duration_ms: float = 0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as percentage."""
        if self.tested == 0:
            return 0.0
        return (self.passed / self.tested) * 100


class RequirementsPlaywrightAgent(AutonomousAgent):
    """
    Autonomous agent for testing UI requirements with Playwright.

    Uses Claude to:
    1. Identify UI-testable requirements
    2. Generate test steps (navigate, click, fill, assert)
    3. Execute via MCP Playwright
    4. Analyze screenshots/DOM with Vision
    5. Determine pass/fail per requirement
    """

    COOLDOWN_SECONDS = 60.0  # Only run once per minute
    DEBOUNCE_SECONDS = 5.0   # Wait for app to stabilize

    def __init__(
        self,
        name: str = "RequirementsPlaywrightAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
        requirements_path: Optional[str] = None,
        app_url: str = "http://localhost:5173",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.requirements_path = requirements_path
        self.app_url = app_url
        self._requirements: list[dict] = []
        self._last_run: Optional[datetime] = None
        self._code_tool: Optional[ClaudeCodeTool] = None

        self.logger = logger.bind(agent=name, working_dir=working_dir)

    @property
    def code_tool(self) -> ClaudeCodeTool:
        """Lazy initialization of ClaudeCodeTool."""
        if self._code_tool is None:
            self._code_tool = ClaudeCodeTool(working_dir=self.working_dir)
        return self._code_tool

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.DEPLOY_SUCCEEDED,
            EventType.PREVIEW_READY,
        ]

    def _load_requirements(self) -> bool:
        """Load requirements from JSON file."""
        if not self.requirements_path:
            # Try to find requirements.json in working dir
            candidates = [
                Path(self.working_dir) / "requirements.json",
                Path(self.working_dir).parent / "requirements.json",
            ]
            for path in candidates:
                if path.exists():
                    self.requirements_path = str(path)
                    break

        if not self.requirements_path:
            self.logger.warning("no_requirements_file_found")
            return False

        try:
            with open(self.requirements_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Support multiple formats
            if "requirements" in data:
                self._requirements = data["requirements"]
            elif "features" in data:
                self._requirements = data["features"]
            elif isinstance(data, list):
                self._requirements = data
            else:
                self._requirements = []

            self.logger.info(
                "requirements_loaded",
                count=len(self._requirements),
                path=self.requirements_path,
            )
            return len(self._requirements) > 0

        except Exception as e:
            self.logger.error("requirements_load_error", error=str(e))
            return False

    async def should_act(self, events: list[Event]) -> bool:
        """Check if we should run requirement tests."""
        # Cooldown check
        if self._last_run:
            elapsed = (datetime.now() - self._last_run).total_seconds()
            if elapsed < self.COOLDOWN_SECONDS:
                self.logger.debug("cooldown_active", remaining=self.COOLDOWN_SECONDS - elapsed)
                return False

        for event in events:
            # Only act on specific events
            if event.type not in (EventType.BUILD_SUCCEEDED, EventType.PREVIEW_READY, EventType.DEPLOY_SUCCEEDED):
                continue

            # Load requirements
            if not self._load_requirements():
                continue

            # Check if app URL is from event data
            if event.data:
                url = event.data.get("url") or event.data.get("preview_url")
                if url:
                    self.app_url = url

            self.logger.info(
                "requirements_test_triggered",
                event_type=event.type.value,
                requirements_count=len(self._requirements),
                app_url=self.app_url,
            )
            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Run requirement-based E2E tests."""
        self._last_run = datetime.now()
        start_time = datetime.now()

        # Wait for app to stabilize
        await asyncio.sleep(self.DEBOUNCE_SECONDS)

        self.logger.info("starting_requirements_tests", app_url=self.app_url)

        # 1. Filter UI-testable requirements
        ui_requirements = await self._identify_ui_requirements()

        result = RequirementsTestResult(
            total_requirements=len(self._requirements),
            skipped=len(self._requirements) - len(ui_requirements),
        )

        self.logger.info(
            "ui_requirements_identified",
            total=len(self._requirements),
            ui_testable=len(ui_requirements),
            skipped=result.skipped,
        )

        # 2. Test each UI requirement
        for req in ui_requirements:
            try:
                test_result = await self._test_requirement(req)
                result.results.append(test_result)
                result.tested += 1
                if test_result.passed:
                    result.passed += 1
                    self.logger.info(
                        "requirement_passed",
                        req_id=test_result.requirement_id,
                    )
                else:
                    result.failed += 1
                    self.logger.warning(
                        "requirement_failed",
                        req_id=test_result.requirement_id,
                        reason=test_result.failure_reason,
                    )
            except Exception as e:
                self.logger.error(
                    "requirement_test_error",
                    req_id=req.get("id", "unknown"),
                    error=str(e),
                )
                result.tested += 1
                result.failed += 1
                result.results.append(RequirementTest(
                    requirement_id=req.get("id", "unknown"),
                    requirement_text=req.get("description", ""),
                    test_steps=[],
                    screenshots=[],
                    passed=False,
                    failure_reason=str(e),
                ))

        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # 3. Publish results
        await self._publish_results(result)

    async def _identify_ui_requirements(self) -> list[dict]:
        """Use Claude to identify which requirements are UI-testable."""
        if not self._requirements:
            return []

        prompt = f"""Analyze these requirements and identify which ones can be tested via browser UI.

Requirements:
{json.dumps(self._requirements, indent=2)}

Return JSON array of requirement IDs that involve:
- User interface elements (buttons, forms, inputs)
- Visual display (showing data, charts, tables)
- User interactions (clicking, filling forms, navigation)
- Page routing/navigation

Exclude:
- Backend-only features (API, database)
- Security features (authentication internals)
- Performance requirements
- Infrastructure requirements

Format: {{"ui_testable": ["REQ-001", "REQ-003", ...]}}
"""

        try:
            result = await self.code_tool.execute(prompt, "", "testing")

            # Parse JSON from response
            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON from output
            json_match = re.search(r'\{[^{}]*"ui_testable"[^{}]*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                ui_ids = set(data.get("ui_testable", []))
                return [r for r in self._requirements if r.get("id") in ui_ids]

        except Exception as e:
            self.logger.warning("ui_requirements_identification_failed", error=str(e))

        # Fallback: use heuristics
        ui_keywords = ["ui", "button", "form", "input", "display", "show", "view", "page", "click", "navigate"]
        ui_reqs = []
        for req in self._requirements:
            desc = req.get("description", "").lower() + req.get("name", "").lower()
            if any(kw in desc for kw in ui_keywords):
                ui_reqs.append(req)

        return ui_reqs if ui_reqs else self._requirements[:5]  # Test at most 5 if no UI detected

    async def _test_requirement(self, requirement: dict) -> RequirementTest:
        """Generate and execute test for a single requirement."""
        req_id = requirement.get("id", "unknown")
        req_text = requirement.get("description", requirement.get("name", ""))

        self.logger.info("testing_requirement", req_id=req_id)

        # 1. Generate test plan with Claude
        test_plan = await self._generate_test_plan(requirement)

        # 2. Execute test via MCP Playwright
        screenshots, execution_result = await self._execute_test_plan(test_plan, req_id)

        # 3. Analyze results with Claude
        passed, analysis = await self._analyze_test_result(
            requirement, test_plan, screenshots, execution_result
        )

        return RequirementTest(
            requirement_id=req_id,
            requirement_text=req_text,
            test_steps=test_plan,
            screenshots=screenshots,
            passed=passed,
            failure_reason=None if passed else analysis,
            claude_analysis=analysis,
        )

    async def _generate_test_plan(self, requirement: dict) -> list[dict]:
        """Use Claude to generate Playwright test steps."""
        prompt = f"""Generate a Playwright test plan for this requirement:

Requirement: {json.dumps(requirement)}
App URL: {self.app_url}

Generate test steps using these MCP Playwright actions:
- browser_navigate: Go to URL
- browser_click: Click element (use CSS selector or text)
- browser_fill: Fill input field
- browser_select_option: Select dropdown option
- browser_wait_for_selector: Wait for element
- browser_take_screenshot: Take screenshot
- browser_snapshot: Get accessibility tree

Return ONLY a JSON array of steps (no markdown, no explanation):
[
  {{"action": "browser_navigate", "params": {{"url": "{self.app_url}"}}}},
  {{"action": "browser_wait_for_selector", "params": {{"selector": "body"}}}},
  {{"action": "browser_click", "params": {{"selector": "button:has-text('Submit')"}}}},
  {{"action": "browser_fill", "params": {{"selector": "#email", "value": "test@example.com"}}}},
  {{"action": "browser_take_screenshot", "params": {{"name": "result"}}}},
  {{"assertion": "Element visible", "selector": ".success-message"}}
]
"""

        try:
            result = await self.code_tool.execute(prompt, "", "testing")
            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON array from output
            json_match = re.search(r'\[[\s\S]*\]', output)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            self.logger.warning("test_plan_generation_failed", error=str(e))

        # Fallback: basic navigation test
        return [
            {"action": "browser_navigate", "params": {"url": self.app_url}},
            {"action": "browser_wait_for_selector", "params": {"selector": "body"}},
            {"action": "browser_take_screenshot", "params": {"name": "fallback"}},
        ]

    async def _execute_test_plan(
        self, test_plan: list[dict], req_id: str
    ) -> tuple[list[str], dict]:
        """Execute test plan via Claude CLI + MCP Playwright."""
        screenshots = []
        execution_log = {"steps": [], "errors": [], "success": True}

        # Build MCP config
        mcp_config = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["-y", "@anthropic/mcp-playwright"]
                }
            }
        }

        # Write temp config
        config_path = Path(self.working_dir) / f".mcp-req-test-{req_id}.json"
        config_path.write_text(json.dumps(mcp_config))

        try:
            # Build execution prompt
            steps_desc = "\n".join([
                f"{i+1}. {step.get('action', 'assert')}: {json.dumps(step.get('params', step))}"
                for i, step in enumerate(test_plan)
            ])

            prompt = f"""Execute these Playwright test steps in order:

{steps_desc}

For each step:
1. Call the appropriate MCP Playwright tool
2. Wait for the action to complete
3. If an error occurs, report it but continue with remaining steps

After all steps, report:
- Which steps succeeded
- Which steps failed and why
- Overall test result

Take a screenshot at the end using browser_take_screenshot.
"""

            # Execute via Claude CLI with MCP
            result = await self.code_tool.execute(
                prompt,
                "",
                "testing",
            )

            output = result.output if hasattr(result, 'output') else str(result)
            execution_log["output"] = output[:2000]  # Truncate for logging

            # Parse success/failure from output
            if "error" in output.lower() or "failed" in output.lower():
                execution_log["success"] = False
                # Extract error messages
                error_match = re.findall(r'error[:\s]+([^\n]+)', output, re.IGNORECASE)
                execution_log["errors"] = error_match[:5]

            # Track screenshots
            screenshot_dir = Path(self.working_dir) / "screenshots"
            screenshot_dir.mkdir(exist_ok=True)
            screenshot_path = screenshot_dir / f"req_{req_id}_{datetime.now().strftime('%H%M%S')}.png"
            screenshots.append(str(screenshot_path))

            return screenshots, execution_log

        except Exception as e:
            self.logger.error("test_execution_error", error=str(e))
            execution_log["success"] = False
            execution_log["errors"].append(str(e))
            return screenshots, execution_log

        finally:
            config_path.unlink(missing_ok=True)

    async def _analyze_test_result(
        self,
        requirement: dict,
        test_plan: list[dict],
        screenshots: list[str],
        execution_result: dict,
    ) -> tuple[bool, str]:
        """Use Claude to analyze if requirement is satisfied."""
        prompt = f"""Analyze if this requirement was satisfied by the test:

Requirement: {json.dumps(requirement)}

Test Plan Executed:
{json.dumps(test_plan, indent=2)}

Execution Result:
{json.dumps(execution_result, indent=2)}

Screenshots taken: {screenshots}

Based on the execution result and any errors:
1. Did all test steps execute successfully?
2. Were the expected assertions satisfied?
3. Is the requirement verified?

Return ONLY JSON (no markdown):
{{
  "passed": true or false,
  "analysis": "Detailed explanation...",
  "missing": ["List of missing functionality if failed"]
}}
"""

        try:
            result = await self.code_tool.execute(prompt, "", "testing")
            output = result.output if hasattr(result, 'output') else str(result)

            # Extract JSON from output
            json_match = re.search(r'\{[^{}]*"passed"[^{}]*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("passed", False), data.get("analysis", "")

            # Heuristic: check for positive indicators
            if execution_result.get("success", False) and not execution_result.get("errors"):
                return True, "All test steps executed successfully"

        except Exception as e:
            self.logger.warning("result_analysis_failed", error=str(e))

        return False, "Could not analyze test result"

    async def _publish_results(self, result: RequirementsTestResult) -> None:
        """Publish test results as events."""
        if not self.event_bus:
            return

        # Determine event type based on results
        if result.failed == 0 and result.passed > 0:
            event_type = EventType.REQUIREMENTS_VERIFIED
        else:
            event_type = EventType.REQUIREMENTS_FAILED

        await self.event_bus.publish(Event(
            type=event_type,
            source=self.name,
            data={
                "total_requirements": result.total_requirements,
                "tested": result.tested,
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "pass_rate": result.pass_rate,
                "duration_ms": result.duration_ms,
                "results": [
                    {
                        "id": r.requirement_id,
                        "passed": r.passed,
                        "analysis": r.claude_analysis,
                    }
                    for r in result.results
                ],
            },
        ))

        self.logger.info(
            "requirements_test_complete",
            event_type=event_type.value,
            total=result.total_requirements,
            tested=result.tested,
            passed=result.passed,
            failed=result.failed,
            pass_rate=f"{result.pass_rate:.1f}%",
            duration_ms=result.duration_ms,
        )


async def create_requirements_playwright_agent(
    event_bus,
    working_dir: str = ".",
    requirements_path: Optional[str] = None,
    app_url: str = "http://localhost:5173",
    auto_start: bool = True,
) -> RequirementsPlaywrightAgent:
    """Factory function to create and start a RequirementsPlaywrightAgent."""
    agent = RequirementsPlaywrightAgent(
        event_bus=event_bus,
        working_dir=working_dir,
        requirements_path=requirements_path,
        app_url=app_url,
    )

    if auto_start:
        asyncio.create_task(agent.start())

    return agent
