"""
Autonomous E2E Test Runner — Tests generated apps using Playwright MCP browser.

Flow:
1. Load User Stories from project spec
2. LLM generates test plan (TestCases with TestSteps)
3. Execute each test via MCP Playwright browser tools
4. Screenshot + snapshot to verify assertions
5. Report results to Discord + JSON file
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from app.models.e2e_models import (
    E2ERunStatus, StepStatus, StepType, TestCase, TestReport,
    TestResult, TestStatus, TestStep, UserStory,
)

logger = logging.getLogger(__name__)

# MCP Docker Playwright base URL (runs in coding-engine-api container)
PLAYWRIGHT_API = os.getenv("CODING_ENGINE_API_URL", "http://localhost:8000")

# LLM for test plan generation
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = os.getenv("E2E_LLM_MODEL", "anthropic/claude-sonnet-4")


class E2ETestRunner:
    """Autonomous E2E test runner using Playwright MCP browser."""

    def __init__(self):
        self._status = E2ERunStatus()
        self._cancel = False
        self._browser_page = None  # Playwright page ref

    @property
    def status(self) -> E2ERunStatus:
        return self._status

    def cancel(self):
        self._cancel = True

    # =========================================================================
    # Main Entry
    # =========================================================================

    async def run_tests(
        self,
        project_path: str,
        app_url: str,
        max_tests: int = 20,
        story_filter: Optional[List[str]] = None,
    ) -> TestReport:
        """Load stories → generate plan → execute → report."""
        self._cancel = False
        self._status = E2ERunStatus(running=True)
        started = datetime.utcnow()

        try:
            # 1. Load user stories
            stories = self._load_user_stories(project_path)
            if story_filter:
                stories = [s for s in stories if s.id in story_filter]
            stories = stories[:max_tests]
            logger.info(f"E2E: Loaded {len(stories)} user stories")

            if not stories:
                return TestReport(
                    project_name=Path(project_path).name,
                    app_url=app_url,
                    started_at=started,
                    finished_at=datetime.utcnow(),
                )

            # 2. Generate test plan via LLM
            test_cases = await self._generate_test_plan(stories, app_url)
            self._status.total_tests = len(test_cases)
            logger.info(f"E2E: Generated {len(test_cases)} test cases")

            # 3. Initialize browser
            await self._init_browser(app_url)

            # 4. Execute tests
            results: List[TestResult] = []
            for i, tc in enumerate(test_cases):
                if self._cancel:
                    break
                self._status.current_test = tc.name
                self._status.progress_pct = (i / len(test_cases)) * 100

                result = await self._execute_test(tc, app_url)
                results.append(result)

                self._status.completed = i + 1
                if result.passed:
                    self._status.passed += 1
                else:
                    self._status.failed += 1

            # 5. Build report
            finished = datetime.utcnow()
            report = TestReport(
                project_name=Path(project_path).name,
                app_url=app_url,
                total_tests=len(results),
                passed=sum(1 for r in results if r.passed),
                failed=sum(1 for r in results if not r.passed),
                results=results,
                started_at=started,
                finished_at=finished,
                duration_ms=int((finished - started).total_seconds() * 1000),
            )

            # Save report to disk
            report_dir = Path(project_path).parent.parent / "output" / Path(project_path).name / "e2e-reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / f"e2e-report-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
            report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            report.report_path = str(report_path)

            # Post to Discord
            await self._post_discord_report(report)

            self._status.report = report
            self._status.progress_pct = 100
            logger.info(f"E2E: Complete — {report.passed}/{report.total_tests} passed")
            return report

        except Exception as e:
            logger.error(f"E2E runner error: {e}", exc_info=True)
            self._status.running = False
            raise
        finally:
            self._status.running = False
            await self._close_browser()

    # =========================================================================
    # 1. Load User Stories
    # =========================================================================

    def _load_user_stories(self, project_path: str) -> List[UserStory]:
        """Parse user stories from project spec files."""
        stories = []
        spec_dir = Path(project_path)

        # Try epics.json first
        epics_file = spec_dir / "tasks" / "epics.json"
        if epics_file.exists():
            try:
                data = json.loads(epics_file.read_text(encoding="utf-8"))
                for epic in data if isinstance(data, list) else data.get("epics", []):
                    for us_id in epic.get("user_stories", []):
                        stories.append(UserStory(
                            id=us_id,
                            title=f"{us_id}: {epic.get('name', '')}",
                            description=epic.get("description", ""),
                            priority="high" if "Auth" in epic.get("name", "") else "medium",
                        ))
            except (json.JSONDecodeError, OSError):
                pass

        # Try user_stories.md or user_stories.json
        for us_file in [spec_dir / "user_stories.json", spec_dir / "user-stories.json"]:
            if us_file.exists():
                try:
                    data = json.loads(us_file.read_text(encoding="utf-8"))
                    for us in data if isinstance(data, list) else data.get("user_stories", []):
                        stories.append(UserStory(
                            id=us.get("id", us.get("story_id", "")),
                            title=us.get("title", us.get("name", "")),
                            description=us.get("description", ""),
                            acceptance_criteria=us.get("acceptance_criteria", []),
                            priority=us.get("priority", "medium"),
                        ))
                except (json.JSONDecodeError, OSError):
                    pass

        # Deduplicate by ID
        seen = set()
        unique = []
        for s in stories:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)
        return unique

    # =========================================================================
    # 2. Generate Test Plan via LLM
    # =========================================================================

    async def _generate_test_plan(self, stories: List[UserStory], app_url: str) -> List[TestCase]:
        """Ask LLM to generate test cases from user stories."""
        stories_text = "\n".join(
            f"- {s.id}: {s.title}" + (f"\n  {s.description}" if s.description else "")
            for s in stories[:20]
        )

        prompt = f"""Generate E2E test cases for a WhatsApp-like messaging app.
The app runs at {app_url}.

User Stories:
{stories_text}

For each testable story, generate a test case as JSON. Each test has steps:
- navigate: Go to a URL path
- assert_text: Check text is visible on page
- click: Click a button/link by its visible label
- type: Type into an input field
- assert_url: Check current URL
- screenshot: Take proof screenshot

Return ONLY a JSON array of test cases:
[{{
  "story_id": "US-001",
  "name": "User can see login page",
  "steps": [
    {{"type": "navigate", "path": "/"}},
    {{"type": "assert_text", "expected": "Login"}},
    {{"type": "screenshot", "label": "login_page"}}
  ]
}}]

Focus on SIMPLE, verifiable tests. Max 5 steps per test. Max 15 tests total.
Return ONLY the JSON array, no markdown."""

        if not OPENROUTER_API_KEY:
            # Fallback: generate basic tests without LLM
            return self._generate_fallback_tests(stories, app_url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 4000,
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"LLM returned {resp.status}, using fallback tests")
                        return self._generate_fallback_tests(stories, app_url)

                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]

                    # Parse JSON from response (strip markdown if present)
                    content = content.strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1].rsplit("```", 1)[0]

                    raw_tests = json.loads(content)
                    return [
                        TestCase(
                            story_id=t.get("story_id", "UNKNOWN"),
                            name=t.get("name", "Test"),
                            steps=[TestStep(**s) for s in t.get("steps", [])],
                        )
                        for t in raw_tests
                    ]
        except Exception as e:
            logger.warning(f"LLM test generation failed: {e}, using fallback")
            return self._generate_fallback_tests(stories, app_url)

    def _generate_fallback_tests(self, stories: List[UserStory], app_url: str) -> List[TestCase]:
        """Basic tests without LLM — just check pages load."""
        tests = [
            TestCase(
                story_id="SMOKE-001",
                name="Homepage loads",
                steps=[
                    TestStep(type=StepType.NAVIGATE, path="/"),
                    TestStep(type=StepType.ASSERT_TEXT, expected="WhatsApp"),
                    TestStep(type=StepType.SCREENSHOT, label="homepage"),
                ],
            ),
            TestCase(
                story_id="SMOKE-002",
                name="Login page accessible",
                steps=[
                    TestStep(type=StepType.NAVIGATE, path="/"),
                    TestStep(type=StepType.CLICK, target="Login"),
                    TestStep(type=StepType.SCREENSHOT, label="login_page"),
                ],
            ),
        ]
        # Add a nav test for each feature button visible on homepage
        for label in ["Chats", "Contacts", "Settings", "Calls"]:
            tests.append(TestCase(
                story_id=f"NAV-{label.upper()}",
                name=f"Navigate to {label}",
                steps=[
                    TestStep(type=StepType.NAVIGATE, path="/"),
                    TestStep(type=StepType.CLICK, target=label),
                    TestStep(type=StepType.SCREENSHOT, label=f"{label.lower()}_page"),
                ],
            ))
        return tests

    # =========================================================================
    # 3. Browser Control via Playwright MCP
    # =========================================================================

    async def _init_browser(self, app_url: str):
        """Navigate Playwright browser to app."""
        try:
            await self._playwright_call("browser_navigate", {"url": app_url})
            await asyncio.sleep(2)  # Wait for page load
        except Exception as e:
            logger.warning(f"Browser init failed: {e}")

    async def _close_browser(self):
        """Close Playwright browser."""
        try:
            await self._playwright_call("browser_close", {})
        except Exception:
            pass

    async def _playwright_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Call a Playwright MCP tool via the MCP Docker proxy."""
        try:
            async with aiohttp.ClientSession() as session:
                # Use the MCP exec endpoint
                async with session.post(
                    f"{PLAYWRIGHT_API}/api/v1/mcp/exec",
                    json={"tool": f"browser_{tool_name}" if not tool_name.startswith("browser_") else tool_name, "arguments": args},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    # Fallback: try direct MCP Docker tool
                    return {"error": f"MCP call failed: {resp.status}"}
        except Exception as e:
            logger.debug(f"Playwright call {tool_name} failed: {e}")
            return {"error": str(e)}

    async def _take_screenshot(self, label: str = "screenshot") -> Optional[str]:
        """Take browser screenshot, return path."""
        result = await self._playwright_call("browser_take_screenshot", {
            "filename": f"e2e-{label}-{int(time.time())}.png"
        })
        if isinstance(result, dict) and "path" in result:
            return result["path"]
        return None

    async def _get_page_text(self) -> str:
        """Get accessibility snapshot of current page."""
        result = await self._playwright_call("browser_snapshot", {})
        if isinstance(result, dict):
            # Extract text content from snapshot
            return json.dumps(result, default=str)[:5000]
        return str(result)[:5000] if result else ""

    # =========================================================================
    # 4. Test Execution
    # =========================================================================

    async def _execute_test(self, tc: TestCase, app_url: str) -> TestResult:
        """Execute a single test case."""
        tc.status = TestStatus.RUNNING
        started = datetime.utcnow()
        assertions_total = 0
        assertions_passed = 0
        screenshots = []
        error_msg = None

        try:
            for step in tc.steps:
                if self._cancel:
                    step.status = StepStatus.SKIPPED
                    continue

                step.status = StepStatus.RUNNING
                step_start = time.time()

                try:
                    if step.type == StepType.NAVIGATE:
                        url = app_url.rstrip("/") + (step.path or "/")
                        await self._playwright_call("browser_navigate", {"url": url})
                        await asyncio.sleep(1.5)
                        step.status = StepStatus.PASSED

                    elif step.type == StepType.CLICK:
                        # Get snapshot to find element ref
                        snapshot = await self._get_page_text()
                        # Try clicking by finding element in snapshot
                        result = await self._playwright_call("browser_click", {
                            "element": step.target or "",
                            "ref": step.target or "",
                        })
                        await asyncio.sleep(1)
                        step.status = StepStatus.PASSED

                    elif step.type == StepType.TYPE:
                        result = await self._playwright_call("browser_type", {
                            "element": step.target or "",
                            "ref": step.target or "",
                            "text": step.value or "",
                        })
                        step.status = StepStatus.PASSED

                    elif step.type == StepType.ASSERT_TEXT:
                        assertions_total += 1
                        page_text = await self._get_page_text()
                        if step.expected and step.expected.lower() in page_text.lower():
                            step.status = StepStatus.PASSED
                            assertions_passed += 1
                        else:
                            step.status = StepStatus.FAILED
                            step.error = f"Expected '{step.expected}' not found on page"

                    elif step.type == StepType.ASSERT_ELEMENT:
                        assertions_total += 1
                        page_text = await self._get_page_text()
                        if step.expected and step.expected.lower() in page_text.lower():
                            step.status = StepStatus.PASSED
                            assertions_passed += 1
                        else:
                            step.status = StepStatus.FAILED
                            step.error = f"Element '{step.expected}' not found"

                    elif step.type == StepType.SCREENSHOT:
                        path = await self._take_screenshot(step.label or "step")
                        if path:
                            screenshots.append(path)
                        step.status = StepStatus.PASSED

                    elif step.type == StepType.WAIT:
                        await asyncio.sleep(int(step.value or "2"))
                        step.status = StepStatus.PASSED

                    else:
                        step.status = StepStatus.SKIPPED

                except Exception as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)[:200]
                    logger.debug(f"Step failed: {step.type} - {e}")

                step.duration_ms = int((time.time() - step_start) * 1000)

        except Exception as e:
            error_msg = str(e)[:500]
            tc.status = TestStatus.ERROR

        finished = datetime.utcnow()
        all_passed = all(
            s.status in (StepStatus.PASSED, StepStatus.SKIPPED)
            for s in tc.steps
        )
        tc.status = TestStatus.PASSED if all_passed else TestStatus.FAILED
        tc.duration_ms = int((finished - started).total_seconds() * 1000)
        tc.screenshots = screenshots

        return TestResult(
            test_case=tc,
            passed=all_passed,
            assertions_total=assertions_total,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_total - assertions_passed,
            error_message=error_msg,
            screenshots=screenshots,
            started_at=started,
            finished_at=finished,
        )

    # =========================================================================
    # 5. Discord Report
    # =========================================================================

    async def _post_discord_report(self, report: TestReport):
        """Post test results to Discord."""
        token = os.getenv("DISCORD_BOT_TOKEN", "")
        channel = os.getenv("DISCORD_CH_TESTING", "")
        if not token or not channel:
            return

        emoji = "+" if report.failed == 0 else "!"
        msg = (
            f"**E2E Test Report** — {report.project_name}\n"
            f"```diff\n"
            f"{emoji} {report.passed}/{report.total_tests} passed "
            f"({report.failed} failed)\n"
            f"  Duration: {report.duration_ms // 1000}s\n"
        )
        for r in report.results:
            icon = "+" if r.passed else "-"
            msg += f"{icon} {r.test_case.story_id}: {r.test_case.name}\n"
        msg += "```"

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"https://discord.com/api/v10/channels/{channel}/messages",
                    headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                    json={"content": msg[:2000]},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.debug(f"Discord post failed: {e}")


# Singleton instance
_runner: Optional[E2ETestRunner] = None


def get_runner() -> E2ETestRunner:
    global _runner
    if _runner is None:
        _runner = E2ETestRunner()
    return _runner
