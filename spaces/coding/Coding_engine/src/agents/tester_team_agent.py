"""
Tester Team Agent - E2E Testing with MCP Playwright.

Uses Claude CLI with MCP Playwright server to:
- Launch and interact with Electron apps
- Take screenshots of UI states
- Click elements, fill forms, navigate
- Capture console errors and network issues
- Verify visual output matches requirements
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    app_launched_event,
    test_spec_created_event,
    e2e_test_passed_event,
    e2e_test_failed_event,
)
from ..mind.shared_state import SharedState
from ..tools.memory_tool import MemoryTool
from ..tools.claude_agent_tool import find_claude_executable
from ..registry.document_registry import DocumentRegistry
from ..registry.documents import ImplementationPlan, TestSpec, TestCase, TestResults
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


@dataclass
class E2ETestResult:
    """Result of an E2E test run."""
    success: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    screenshots: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    app_launched: bool = False
    app_crashed: bool = False
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "screenshots": self.screenshots,
            "errors": self.errors,
            "console_errors": self.console_errors,
            "app_launched": self.app_launched,
            "app_crashed": self.app_crashed,
            "duration_ms": self.duration_ms,
        }


class TesterTeamAgent(AutonomousAgent):
    """
    Agent that performs E2E testing using Claude CLI with MCP Playwright.

    Triggers on:
    - Build succeeded
    - App launched
    - Code fixed (after fixes, verify UI still works)
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        requirements: Optional[list[str]] = None,
        poll_interval: float = 2.0,
        memory_tool: Optional[MemoryTool] = None,
        document_registry: Optional[DocumentRegistry] = None,
    ):
        super().__init__(name, event_bus, shared_state, working_dir, poll_interval)
        self.requirements = requirements or []
        self.memory_tool = memory_tool
        self.document_registry = document_registry
        self._screenshots_dir = Path(working_dir) / "screenshots"
        self._screenshots_dir.mkdir(exist_ok=True)
        self._last_test_time: Optional[datetime] = None
        self._test_cooldown = 60  # Seconds between test runs
        self._pending_impl_plans: list[ImplementationPlan] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.APP_LAUNCHED,
            EventType.CODE_FIXED,
            EventType.E2E_TEST_FAILED,  # Retry on failure after fixes
            EventType.IMPLEMENTATION_PLAN_CREATED,  # From GeneratorAgent
        ]

    async def should_act(self, events: list[Event]) -> bool:
        # Check cooldown
        if self._last_test_time:
            elapsed = (datetime.now() - self._last_test_time).seconds
            if elapsed < self._test_cooldown:
                return False

        # Check for pending implementation plans in document registry
        if self.document_registry:
            pending = await self.document_registry.get_pending_for_agent("TesterTeam")
            if pending:
                self._pending_impl_plans = [
                    d for d in pending if isinstance(d, ImplementationPlan)
                ]
                if self._pending_impl_plans:
                    return True

        for event in events:
            # Check for initial trigger
            if event.data and event.data.get("trigger") == "initial":
                return True
            # Act after successful build
            if event.type == EventType.BUILD_SUCCEEDED:
                return True
            # Act when app is launched
            if event.type == EventType.APP_LAUNCHED:
                return True
            # Act after code fixes to verify
            if event.type == EventType.CODE_FIXED and event.success:
                return True
            # Act on implementation plan created
            if event.type == EventType.IMPLEMENTATION_PLAN_CREATED and self.document_registry:
                doc_id = event.data.get("doc_id")
                if doc_id:
                    doc = await self.document_registry.read_document(doc_id)
                    if doc and isinstance(doc, ImplementationPlan):
                        self._pending_impl_plans.append(doc)
                        return True

        return False

    async def _should_act_on_state(self) -> bool:
        """Run E2E tests if build succeeded but no E2E tests run yet."""
        metrics = self.shared_state.metrics
        return (
            metrics.build_success and
            metrics.iteration >= 2 and
            not getattr(metrics, 'e2e_tests_run', False)
        )

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Run E2E tests using Claude CLI with MCP Playwright."""
        self.logger.info("starting_e2e_tests")
        self._last_test_time = datetime.now()

        # Search for learned test patterns and common issues
        learned_patterns = []
        if self.memory_tool and self.memory_tool.enabled:
            try:
                project_type = self._detect_project_type()
                test_query = f"E2E testing {project_type} electron UI testing patterns"

                result_data = await self.memory_tool.search_test_patterns(
                    query=test_query,
                    project_type=project_type,
                    limit=5,  # Get 5 candidates for scoring
                    rerank=True  # Enable reranking
                )

                if result_data.found and result_data.results:
                    # Extract and format learned patterns
                    learned_patterns = result_data.results[:3]  # Top 3 patterns
                    self.logger.info(
                        "found_test_patterns_in_memory",
                        patterns_count=len(learned_patterns),
                        top_score=learned_patterns[0].get("score", 0) if learned_patterns else 0
                    )
            except Exception as e:
                self.logger.warning("memory_search_failed", error=str(e))

        try:
            # First, try to launch the app
            app_process = await self._launch_app()
            if not app_process:
                return e2e_test_failed_event(
                    source=self.name,
                    error_message="Failed to launch application",
                )

            # Give app time to start
            await asyncio.sleep(3)

            # Run E2E tests with Claude + MCP Playwright
            result = await self._run_playwright_tests(learned_patterns)

            # Cleanup
            await self._stop_app(app_process)

            # Update shared state
            if hasattr(self.shared_state, 'update_e2e_tests'):
                await self.shared_state.update_e2e_tests(
                    run=True,
                    passed=result.tests_passed,
                    failed=result.tests_failed,
                )

            # Store test results in memory
            if self.memory_tool and self.memory_tool.enabled:
                try:
                    # Store test run results (both success and failure for learning)
                    test_summary = f"E2E test run: {result.tests_passed}/{result.tests_run} passed"
                    if result.console_errors:
                        test_summary += f". Console errors: {'; '.join(result.console_errors[:2])}"
                    if result.errors:
                        test_summary += f". Issues: {'; '.join(result.errors[:2])}"

                    await self.memory_tool.store_memory(
                        content=test_summary,
                        category="test_run",
                        metadata={
                            "project_type": self._detect_project_type(),
                            "project_name": os.path.basename(self.working_dir),
                            "success": result.success,
                            "tests_run": result.tests_run,
                            "tests_passed": result.tests_passed,
                            "tests_failed": result.tests_failed,
                            "app_launched": result.app_launched,
                            "console_errors_count": len(result.console_errors),
                        }
                    )
                    self.logger.info("stored_test_results_in_memory", success=result.success)
                except Exception as e:
                    self.logger.warning("memory_store_failed", error=str(e))

            # Write TEST_SPEC and mark implementation plans as consumed
            if self.document_registry and self._pending_impl_plans:
                await self._write_test_spec(result)

                # Mark implementation plans as consumed
                for plan in self._pending_impl_plans:
                    await self.document_registry.mark_consumed(plan.id, "TesterTeam")

                # Clear pending plans
                self._pending_impl_plans = []

            if result.success:
                return e2e_test_passed_event(
                    source=self.name,
                    data=result.to_dict(),
                )
            else:
                return e2e_test_failed_event(
                    source=self.name,
                    error_message="; ".join(result.errors[:3]),
                    data=result.to_dict(),
                )

        except Exception as e:
            self.logger.error("e2e_test_error", error=str(e))
            return e2e_test_failed_event(
                source=self.name,
                error_message=str(e),
            )

    async def _launch_app(self) -> Optional[subprocess.Popen]:
        """Launch the Electron app for testing."""
        self.logger.info("launching_app")

        try:
            # Check if package.json exists
            package_json = Path(self.working_dir) / "package.json"
            if not package_json.exists():
                self.logger.error("package_json_not_found")
                return None

            # Try npm run dev first, then npm start
            for cmd in ["npm run dev", "npm start", "npx electron ."]:
                try:
                    process = subprocess.Popen(
                        cmd,
                        shell=True,
                        cwd=self.working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    # Give it a moment to fail fast if it's going to
                    await asyncio.sleep(2)
                    if process.poll() is None:  # Still running
                        self.logger.info("app_launched", command=cmd)
                        await self.event_bus.publish(app_launched_event(
                            source=self.name,
                            command=cmd,
                            pid=process.pid,
                        ))
                        return process
                except Exception as e:
                    self.logger.warning("app_launch_attempt_failed", command=cmd, error=str(e))
                    continue

            return None

        except Exception as e:
            self.logger.error("app_launch_failed", error=str(e))
            return None

    async def _stop_app(self, process: subprocess.Popen) -> None:
        """Stop the running app process."""
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            self.logger.info("app_stopped")
        except Exception as e:
            self.logger.warning("app_stop_failed", error=str(e))

    async def _run_playwright_tests(self, learned_patterns: list = None) -> E2ETestResult:
        """Run E2E tests using Claude CLI with MCP Playwright server."""
        start_time = datetime.now()
        result = E2ETestResult(success=False, app_launched=True)

        # Build the test prompt with learned patterns
        test_prompt = self._build_test_prompt(learned_patterns)

        # Prepare Claude CLI command with MCP Playwright (official server)
        # Uses @playwright/mcp@latest for better compatibility and features
        mcp_config = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["--yes", "@playwright/mcp@latest", "--browser", "chrome", "--headless"]
                }
            }
        }

        # Write temporary MCP config
        mcp_config_path = Path(self.working_dir) / ".mcp-test-config.json"
        with open(mcp_config_path, 'w') as f:
            json.dump(mcp_config, f)

        try:
            # Run Claude CLI with MCP Playwright
            claude_exe = find_claude_executable() or "claude"
            cmd = [
                claude_exe,
                "--mcp-config", str(mcp_config_path),
                "-p", test_prompt,
                "--output-format", "json",
            ]

            self.logger.info("running_claude_playwright", prompt_length=len(test_prompt))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300  # 5 minute timeout
                )

                if process.returncode == 0:
                    # Parse output for test results
                    output = stdout.decode('utf-8', errors='replace')
                    result = self._parse_test_output(output, result)
                else:
                    result.errors.append(f"Claude CLI failed: {stderr.decode('utf-8', errors='replace')}")

            except asyncio.TimeoutError:
                process.kill()
                result.errors.append("Test execution timed out after 5 minutes")

        except FileNotFoundError:
            # Claude CLI not available, fallback to basic checks
            self.logger.warning("claude_cli_not_found_using_fallback")
            result = await self._fallback_basic_tests(result)

        except Exception as e:
            result.errors.append(f"Test execution error: {str(e)}")

        finally:
            # Cleanup config
            if mcp_config_path.exists():
                mcp_config_path.unlink()

        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        result.success = len(result.errors) == 0 and result.tests_failed == 0

        return result

    def _build_test_prompt(self, learned_patterns: list = None) -> str:
        """Build the test prompt for Claude with MCP Playwright, including learned patterns."""
        req_text = "\n".join(f"- {r}" for r in self.requirements[:10]) if self.requirements else "- Basic UI rendering\n- App launches without crashes"

        prompt_parts = [
            "You are an E2E tester for an Electron application. Use the MCP Playwright tools to test the app.",
            "",
            f"The app should be running on localhost. Test the following requirements:",
            req_text,
            "",
        ]

        # Add learned test patterns from memory
        if learned_patterns:
            prompt_parts.extend([
                "## Learned Test Patterns and Common Issues",
                "Based on previous test runs, pay attention to these patterns:",
                "",
            ])
            for i, pattern in enumerate(learned_patterns, 1):
                content = pattern.get("content", "")
                score = pattern.get("score", 0)
                if content:
                    prompt_parts.append(f"{i}. {content[:200]} (confidence: {score:.2f})")
            prompt_parts.append("")

        prompt_parts.extend([
            "Perform these tests:",
            "1. Navigate to the app (try http://localhost:5173 for Vite dev server or http://localhost:3000)",
            "2. Take a screenshot of the initial state",
            "3. Check for any console errors",
            "4. Verify the main UI elements are visible",
            "5. Test basic interactions if applicable",
            "6. Take a screenshot after interactions",
            "",
            "Report your findings in JSON format:",
            "{",
            '    "tests_run": <number>,',
            '    "tests_passed": <number>,',
            '    "tests_failed": <number>,',
            '    "screenshots": ["<path1>", "<path2>"],',
            '    "console_errors": ["<error1>", "<error2>"],',
            '    "issues_found": ["<issue1>", "<issue2>"],',
            '    "recommendations": ["<rec1>", "<rec2>"]',
            "}",
            "",
            "Focus on functionality and user-visible issues. Be thorough but efficient.",
        ])

        return "\n".join(prompt_parts)

    def _parse_test_output(self, output: str, result: E2ETestResult) -> E2ETestResult:
        """Parse Claude's test output."""
        try:
            # Try to find JSON in output
            import re
            json_match = re.search(r'\{[^{}]*"tests_run"[^{}]*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                result.tests_run = data.get('tests_run', 0)
                result.tests_passed = data.get('tests_passed', 0)
                result.tests_failed = data.get('tests_failed', 0)
                result.screenshots = data.get('screenshots', [])
                result.console_errors = data.get('console_errors', [])
                result.errors.extend(data.get('issues_found', []))

        except json.JSONDecodeError:
            self.logger.warning("could_not_parse_test_output")
            # Assume some basic success if we got output
            result.tests_run = 1
            result.tests_passed = 1 if "passed" in output.lower() or "success" in output.lower() else 0
            result.tests_failed = 0 if result.tests_passed else 1

        return result

    async def _fallback_basic_tests(self, result: E2ETestResult) -> E2ETestResult:
        """Fallback tests when Claude CLI is not available."""
        self.logger.info("running_fallback_tests")

        # Check if dist/out folder exists (app was built)
        dist_path = Path(self.working_dir) / "dist"
        out_path = Path(self.working_dir) / "out"

        if dist_path.exists() or out_path.exists():
            result.tests_run = 1
            result.tests_passed = 1
            self.logger.info("build_output_exists")
        else:
            result.tests_run = 1
            result.tests_failed = 1
            result.errors.append("No build output found (dist/ or out/ directory)")

        # Check for main entry point
        package_json = Path(self.working_dir) / "package.json"
        if package_json.exists():
            with open(package_json) as f:
                pkg = json.load(f)
                main = pkg.get("main", "")
                main_path = Path(self.working_dir) / main
                if main_path.exists():
                    result.tests_run += 1
                    result.tests_passed += 1
                else:
                    result.tests_run += 1
                    result.tests_failed += 1
                    result.errors.append(f"Main entry point not found: {main}")

        result.success = result.tests_failed == 0
        return result

    def _detect_project_type(self) -> str:
        """Detect project type from working directory."""
        # Simple detection based on file existence
        if os.path.exists(os.path.join(self.working_dir, "package.json")):
            if os.path.exists(os.path.join(self.working_dir, "electron.vite.config.ts")):
                return "electron-vite"
            elif os.path.exists(os.path.join(self.working_dir, "electron-builder.yml")):
                return "electron"
            return "node"
        elif os.path.exists(os.path.join(self.working_dir, "requirements.txt")):
            return "python"
        elif os.path.exists(os.path.join(self.working_dir, "Cargo.toml")):
            return "rust"
        return "unknown"

    async def _write_test_spec(self, result: E2ETestResult) -> Optional[str]:
        """
        Write a TEST_SPEC document to the registry.

        Args:
            result: E2E test results

        Returns:
            Document ID if written successfully
        """
        if not self.document_registry:
            return None

        try:
            from uuid import uuid4

            timestamp = datetime.now()
            doc_id = f"test_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

            # Get the implementation plan we're responding to
            responding_to = None
            coverage_targets = []
            if self._pending_impl_plans:
                responding_to = self._pending_impl_plans[0].id
                coverage_targets = self._pending_impl_plans[0].test_focus_areas

            # Create test cases from what was actually run
            test_cases = []
            for i in range(result.tests_run):
                passed = i < result.tests_passed
                test_cases.append(TestCase(
                    id=f"tc_{i+1:03d}",
                    name=f"E2E Test {i+1}",
                    description=f"Automated E2E test case {i+1}",
                    test_type="e2e",
                    priority=1,
                    expected_result="Test passes without errors",
                ))

            # Create test results
            test_results = TestResults(
                total=result.tests_run,
                passed=result.tests_passed,
                failed=result.tests_failed,
                skipped=0,
                duration_seconds=result.duration_ms / 1000,
                failures=[{"error": e} for e in result.errors[:5]],
            )

            # Create the test spec
            test_spec = TestSpec(
                id=doc_id,
                timestamp=timestamp,
                source_agent=self.name,
                responding_to=responding_to,
                test_cases=test_cases,
                coverage_targets=coverage_targets,
                results=test_results,
                executed_at=timestamp,
            )

            # Write to registry
            await self.document_registry.write_document(test_spec, priority=3)

            # Publish event using factory function
            await self.event_bus.publish(test_spec_created_event(
                source=self.name,
                doc_id=doc_id,
                tests_run=result.tests_run,
                tests_passed=result.tests_passed,
                tests_failed=result.tests_failed,
                responding_to=responding_to,
            ))

            self.logger.info(
                "test_spec_written",
                doc_id=doc_id,
                tests_run=result.tests_run,
                tests_passed=result.tests_passed,
            )

            return doc_id

        except Exception as e:
            self.logger.error("test_spec_write_failed", error=str(e))
            return None

    def _get_action_description(self) -> str:
        return "Running E2E tests with Playwright"
