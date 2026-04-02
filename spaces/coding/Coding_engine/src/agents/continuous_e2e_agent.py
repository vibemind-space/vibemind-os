"""
ContinuousE2EAgent - Continuous E2E testing during code generation.

Periodically tests the live preview by:
1. Navigating to the app
2. Clicking on sidebar items/buttons
3. Filling forms with test data
4. Taking screenshots
5. Capturing console errors
6. Reporting issues for BugFixerAgent

Events:
- Subscribes to: PREVIEW_READY, BUILD_SUCCEEDED, GENERATION_COMPLETE
- Publishes: E2E_TEST_PASSED, E2E_TEST_FAILED, E2E_SCREENSHOT_TAKEN
"""

import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType

logger = structlog.get_logger(__name__)


@dataclass
class E2ETestResult:
    """Result of a single E2E test run."""
    timestamp: datetime
    duration_ms: float
    pages_visited: int
    clicks_performed: int
    forms_filled: int
    screenshots: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    passed: bool = True


class ContinuousE2EAgent(AutonomousAgent):
    """
    Autonomous agent for continuous E2E testing during generation.

    Uses MCP Playwright to periodically test the live preview,
    clicking through the UI and reporting any errors found.
    """

    COOLDOWN_SECONDS = 60.0  # Run every 60 seconds
    TEST_TIMEOUT_MS = 30000  # 30 second timeout per test run

    def __init__(
        self,
        name: str = "ContinuousE2EAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
        app_url: str = "http://localhost:5173",
        screenshots_dir: str = "e2e_screenshots",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.app_url = app_url
        self.screenshots_dir = Path(working_dir) / screenshots_dir
        self.screenshots_dir.mkdir(exist_ok=True)
        self._test_count = 0
        self._last_test_time: Optional[datetime] = None
        self._is_running = False
        self._periodic_task: Optional[asyncio.Task] = None
        self.logger = logger.bind(agent=name)

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.PREVIEW_READY,
            EventType.BUILD_SUCCEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Start periodic testing when preview is ready."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue
            if event.type == EventType.PREVIEW_READY:
                return True
            if event.type == EventType.BUILD_SUCCEEDED:
                # Also trigger on successful builds
                return True
        return False

    async def act(self, events: list[Event]) -> None:
        """Start or continue periodic E2E testing."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        # Start periodic testing if not already running
        if not self._is_running:
            self._is_running = True
            self._periodic_task = asyncio.create_task(self._run_periodic_tests())
            self.logger.info("continuous_e2e_started", url=self.app_url)

    async def _run_periodic_tests(self) -> None:
        """Run E2E tests periodically."""
        while self._is_running:
            try:
                result = await self._run_single_test()
                await self._publish_result(result)

                if result.errors or result.console_errors:
                    self.logger.warning(
                        "e2e_issues_found",
                        errors=len(result.errors),
                        console_errors=len(result.console_errors),
                    )
                else:
                    self.logger.info(
                        "e2e_test_passed",
                        pages=result.pages_visited,
                        clicks=result.clicks_performed,
                    )

            except Exception as e:
                self.logger.error("e2e_test_exception", error=str(e))

            # Wait before next test
            await asyncio.sleep(self.COOLDOWN_SECONDS)

    async def _run_single_test(self) -> E2ETestResult:
        """Execute a single E2E test run."""
        start_time = datetime.now()
        self._test_count += 1

        result = E2ETestResult(
            timestamp=start_time,
            duration_ms=0,
            pages_visited=0,
            clicks_performed=0,
            forms_filled=0,
        )

        try:
            # Import autogen MCP workbench
            from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams

            params = StdioServerParams(
                command='npx',
                args=['--yes', '@playwright/mcp@latest', '--browser', 'chrome', '--headless']
            )

            async with McpWorkbench(server_params=params) as workbench:
                # 1. Navigate to app
                self.logger.debug("e2e_navigating", url=self.app_url)
                await workbench.call_tool('browser_navigate', {'url': self.app_url})
                await asyncio.sleep(2)  # Wait for page load
                result.pages_visited += 1

                # 2. Get page snapshot to find clickable elements
                snapshot_result = await workbench.call_tool('browser_snapshot', {})
                snapshot_text = self._extract_content(snapshot_result)

                # 3. Get console messages for errors
                console_result = await workbench.call_tool('browser_console_messages', {})
                console_text = self._extract_content(console_result)
                result.console_errors = self._parse_console_errors(console_text)

                # 4. Take initial screenshot
                screenshot_path = self._get_screenshot_path("initial")
                await workbench.call_tool('browser_screenshot', {'path': screenshot_path})
                result.screenshots.append(screenshot_path)

                # 5. Find and click on sidebar items
                clickable_items = self._find_clickable_elements(snapshot_text)
                self.logger.debug("e2e_found_elements", count=len(clickable_items))

                # 6. Click on random sidebar items (max 5)
                items_to_click = random.sample(
                    clickable_items,
                    min(5, len(clickable_items))
                ) if clickable_items else []

                for i, item in enumerate(items_to_click):
                    try:
                        self.logger.debug("e2e_clicking", element=item)
                        await workbench.call_tool('browser_click', {'element': item})
                        await asyncio.sleep(1)  # Wait for navigation
                        result.clicks_performed += 1
                        result.pages_visited += 1

                        # Take screenshot after click
                        screenshot_path = self._get_screenshot_path(f"click_{i}")
                        await workbench.call_tool('browser_screenshot', {'path': screenshot_path})
                        result.screenshots.append(screenshot_path)

                        # Check for new console errors
                        console_result = await workbench.call_tool('browser_console_messages', {})
                        new_errors = self._parse_console_errors(self._extract_content(console_result))
                        for err in new_errors:
                            if err not in result.console_errors:
                                result.console_errors.append(err)

                    except Exception as click_err:
                        result.errors.append({
                            "type": "click_failed",
                            "element": item,
                            "error": str(click_err),
                        })

                # 7. Find and fill forms
                form_inputs = self._find_form_inputs(snapshot_text)
                for inp in form_inputs[:3]:  # Max 3 form fields
                    try:
                        test_value = self._get_test_value(inp)
                        await workbench.call_tool('browser_fill', {
                            'element': inp,
                            'value': test_value,
                        })
                        result.forms_filled += 1
                    except Exception as fill_err:
                        result.errors.append({
                            "type": "fill_failed",
                            "element": inp,
                            "error": str(fill_err),
                        })

                # 8. Final screenshot
                screenshot_path = self._get_screenshot_path("final")
                await workbench.call_tool('browser_screenshot', {'path': screenshot_path})
                result.screenshots.append(screenshot_path)

                # Close browser
                await workbench.call_tool('browser_close', {})

        except Exception as e:
            result.errors.append({
                "type": "test_exception",
                "error": str(e),
            })
            result.passed = False

        # Calculate duration
        result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        result.passed = len(result.errors) == 0 and len(result.console_errors) == 0
        self._last_test_time = datetime.now()

        return result

    def _extract_content(self, result) -> str:
        """Extract text content from MCP result."""
        if hasattr(result, 'result') and result.result:
            for item in result.result:
                if hasattr(item, 'content'):
                    return item.content
        return ""

    def _parse_console_errors(self, console_text: str) -> list[str]:
        """Parse console output for errors."""
        errors = []
        for line in console_text.split('\n'):
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['error', 'exception', 'failed', 'uncaught']):
                errors.append(line.strip())
        return errors

    def _find_clickable_elements(self, snapshot_text: str) -> list[str]:
        """Find clickable elements from accessibility snapshot."""
        clickable = []

        # Look for buttons and links in the snapshot
        for line in snapshot_text.split('\n'):
            line_stripped = line.strip()
            # Button patterns
            if 'button' in line.lower():
                # Extract button text
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        clickable.append(f'button:has-text("{parts[1]}")')
            # Link patterns
            elif 'link' in line.lower():
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        clickable.append(f'a:has-text("{parts[1]}")')
            # Navigation items (sidebar)
            elif any(kw in line.lower() for kw in ['navigation', 'nav', 'menu', 'sidebar']):
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        clickable.append(f'text="{parts[1]}"')

        return clickable[:20]  # Limit to 20 elements

    def _find_form_inputs(self, snapshot_text: str) -> list[str]:
        """Find form input elements from accessibility snapshot."""
        inputs = []

        for line in snapshot_text.split('\n'):
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['textbox', 'input', 'textarea', 'combobox']):
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 2:
                        label = parts[1]
                        inputs.append(f'[placeholder*="{label}"], [aria-label*="{label}"]')
                elif 'id=' in line:
                    # Extract ID
                    idx = line.find('id=')
                    if idx >= 0:
                        id_part = line[idx+3:].split()[0].strip('"\'')
                        inputs.append(f'#{id_part}')

        return inputs[:10]  # Limit to 10 inputs

    def _get_test_value(self, input_selector: str) -> str:
        """Generate appropriate test value based on input type."""
        selector_lower = input_selector.lower()

        if 'email' in selector_lower:
            return "test@example.com"
        elif 'phone' in selector_lower or 'tel' in selector_lower:
            return "+49 123 4567890"
        elif 'date' in selector_lower:
            return "2024-01-15"
        elif 'number' in selector_lower or 'amount' in selector_lower:
            return "100"
        elif 'password' in selector_lower:
            return "TestPassword123!"
        else:
            return "Test Value"

    def _get_screenshot_path(self, suffix: str) -> str:
        """Generate screenshot file path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"e2e_{self._test_count}_{timestamp}_{suffix}.png"
        return str(self.screenshots_dir / filename)

    async def _publish_result(self, result: E2ETestResult) -> None:
        """Publish E2E test result as event."""
        if not self.event_bus:
            return

        event_type = EventType.E2E_TEST_PASSED if result.passed else EventType.E2E_TEST_FAILED

        await self.event_bus.publish(Event(
            type=event_type,
            source=self.name,
            data={
                "timestamp": result.timestamp.isoformat(),
                "duration_ms": result.duration_ms,
                "pages_visited": result.pages_visited,
                "clicks_performed": result.clicks_performed,
                "forms_filled": result.forms_filled,
                "screenshots": result.screenshots,
                "errors": result.errors,
                "console_errors": result.console_errors,
            },
        ))

        # Publish individual errors for BugFixerAgent
        for error in result.errors:
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_ERROR,
                source=self.name,
                data={
                    "error_type": "e2e_error",
                    "error": error,
                    "url": self.app_url,
                },
            ))

        # Publish console errors
        for console_error in result.console_errors:
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_ERROR,
                source=self.name,
                data={
                    "error_type": "console_error",
                    "error_message": console_error,
                    "url": self.app_url,
                },
            ))

        # Publish screenshots
        for screenshot in result.screenshots:
            await self.event_bus.publish(Event(
                type=EventType.E2E_SCREENSHOT_TAKEN,
                source=self.name,
                data={
                    "screenshot_path": screenshot,
                    "test_count": self._test_count,
                },
            ))

    async def stop(self) -> None:
        """Stop periodic testing."""
        self._is_running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
        self.logger.info("continuous_e2e_stopped", tests_run=self._test_count)
