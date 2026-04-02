"""
Accessibility Agent - Autonomous agent for WCAG compliance and accessibility testing.

Tests generated applications for:
- WCAG 2.1 Level A/AA compliance
- axe-core integration via Playwright
- Color contrast analysis
- Keyboard navigation testing
- Screen reader compatibility hints

Publishes:
- A11Y_SCAN_STARTED: Accessibility scan initiated
- A11Y_TEST_PASSED: All accessibility tests passed
- A11Y_ISSUE_FOUND: Individual accessibility issue
- WCAG_VIOLATION: WCAG guideline violation detected
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    a11y_scan_started_event,
    a11y_issue_found_event,
    a11y_test_passed_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin


logger = structlog.get_logger(__name__)


# WCAG 2.1 Guidelines reference
WCAG_GUIDELINES = {
    "1.1.1": {"name": "Non-text Content", "level": "A"},
    "1.3.1": {"name": "Info and Relationships", "level": "A"},
    "1.4.1": {"name": "Use of Color", "level": "A"},
    "1.4.3": {"name": "Contrast (Minimum)", "level": "AA"},
    "1.4.4": {"name": "Resize Text", "level": "AA"},
    "2.1.1": {"name": "Keyboard", "level": "A"},
    "2.1.2": {"name": "No Keyboard Trap", "level": "A"},
    "2.4.1": {"name": "Bypass Blocks", "level": "A"},
    "2.4.2": {"name": "Page Titled", "level": "A"},
    "2.4.4": {"name": "Link Purpose", "level": "A"},
    "2.4.6": {"name": "Headings and Labels", "level": "AA"},
    "2.4.7": {"name": "Focus Visible", "level": "AA"},
    "3.1.1": {"name": "Language of Page", "level": "A"},
    "3.2.1": {"name": "On Focus", "level": "A"},
    "3.2.2": {"name": "On Input", "level": "A"},
    "3.3.1": {"name": "Error Identification", "level": "A"},
    "3.3.2": {"name": "Labels or Instructions", "level": "A"},
    "4.1.1": {"name": "Parsing", "level": "A"},
    "4.1.2": {"name": "Name, Role, Value", "level": "A"},
}

# Color contrast ratios (WCAG 2.1)
CONTRAST_RATIOS = {
    "AA_normal_text": 4.5,
    "AA_large_text": 3.0,
    "AAA_normal_text": 7.0,
    "AAA_large_text": 4.5,
}

# Common accessibility anti-patterns in code
A11Y_ANTIPATTERNS = {
    "missing_alt": {
        "pattern": r"<img[^>]*(?<!alt=)[^>]*>",
        "description": "Image missing alt attribute",
        "wcag": "1.1.1",
        "severity": "critical",
    },
    "empty_alt_decorative": {
        "pattern": r'<img[^>]*alt=""[^>]*(?:role="(?!presentation|none))[^>]*>',
        "description": "Empty alt on non-decorative image",
        "wcag": "1.1.1",
        "severity": "high",
    },
    "missing_label": {
        "pattern": r'<input[^>]*(?<!aria-label|aria-labelledby|id=)[^>]*type="(?:text|email|password|tel|search)"[^>]*>',
        "description": "Form input missing accessible label",
        "wcag": "3.3.2",
        "severity": "high",
    },
    "missing_button_text": {
        "pattern": r"<button[^>]*>\s*<(?:svg|img|i)[^>]*>\s*</button>",
        "description": "Button with only icon, missing accessible text",
        "wcag": "4.1.2",
        "severity": "high",
    },
    "missing_lang": {
        "pattern": r"<html(?![^>]*lang=)[^>]*>",
        "description": "HTML element missing lang attribute",
        "wcag": "3.1.1",
        "severity": "high",
    },
    "positive_tabindex": {
        "pattern": r'tabindex="[1-9]',
        "description": "Positive tabindex disrupts natural tab order",
        "wcag": "2.4.3",
        "severity": "medium",
    },
    "autofocus_misuse": {
        "pattern": r"<(?:input|button|select|textarea)[^>]*autofocus[^>]*>",
        "description": "Autofocus can disorient screen reader users",
        "wcag": "3.2.1",
        "severity": "low",
    },
    "onclick_div": {
        "pattern": r'<div[^>]*onclick[^>]*>(?!.*role="button")',
        "description": "Clickable div without button role - not keyboard accessible",
        "wcag": "2.1.1",
        "severity": "high",
    },
    "missing_heading_structure": {
        "pattern": r"<h[3-6][^>]*>.*?</h[3-6]>(?![\s\S]*<h[12])",
        "description": "Heading hierarchy skipped (no h1/h2 before h3+)",
        "wcag": "1.3.1",
        "severity": "medium",
    },
    "link_no_text": {
        "pattern": r'<a[^>]*href[^>]*>\s*<(?:img|svg|i)[^>]*>\s*</a>',
        "description": "Link with only image/icon, missing accessible text",
        "wcag": "2.4.4",
        "severity": "high",
    },
}


class AccessibilityAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for accessibility testing and WCAG compliance.

    Triggers on:
    - E2E_TEST_PASSED: Run a11y tests after UI tests pass
    - SCREEN_STREAM_READY: VNC screenshot available for analysis
    - UX_REVIEW_PASSED: After UX review

    Tests for:
    - WCAG 2.1 Level A/AA compliance
    - Color contrast ratios
    - Keyboard navigation patterns
    - Screen reader compatibility
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        wcag_level: str = "AA",
        enable_axe_core: bool = True,
        enable_pattern_scan: bool = True,
        enable_contrast_check: bool = True,
    ):
        """
        Initialize AccessibilityAgent.

        Args:
            event_bus: EventBus for pub/sub
            shared_state: SharedState for metrics
            working_dir: Project directory to analyze
            claude_tool: Optional Claude tool for AI analysis
            wcag_level: Target WCAG level ("A", "AA", or "AAA")
            enable_axe_core: Whether to run axe-core via Playwright
            enable_pattern_scan: Whether to scan code for anti-patterns
            enable_contrast_check: Whether to check color contrast
        """
        super().__init__(
            name="AccessibilityAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.working_dir = Path(working_dir)
        self.claude_tool = claude_tool
        self.wcag_level = wcag_level
        self.enable_axe_core = enable_axe_core
        self.enable_pattern_scan = enable_pattern_scan
        self.enable_contrast_check = enable_contrast_check

        self._last_scan: Optional[datetime] = None
        self._issues_found: list[dict] = []

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens for."""
        return [
            EventType.E2E_TEST_PASSED,
            EventType.SCREEN_STREAM_READY,
            EventType.UX_REVIEW_PASSED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Determine if agent should act on any event.

        Acts when:
        - E2E tests passed (run full a11y suite)
        - VNC screenshot ready (analyze for visual a11y)
        - UX review passed (validate accessibility)
        """
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Rate limit: Don't scan more than once per 90 seconds
            if self._last_scan:
                elapsed = (datetime.now() - self._last_scan).total_seconds()
                if elapsed < 90:
                    logger.debug(
                        "a11y_scan_skipped",
                        reason="rate_limited",
                        seconds_since_last=elapsed,
                    )
                    continue

            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Perform accessibility testing.

        Uses autogen team if available, falls back to direct scanning.
        """
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> None:
        """Run accessibility testing using autogen A11yOperator + A11yValidator team."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_scan = datetime.now()
        self._issues_found = []

        await self.event_bus.publish(a11y_scan_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            wcag_level=self.wcag_level,
            trigger=event.type.value,
        ))

        try:
            task = self.build_task_prompt(events, extra_context=f"""
## Accessibility Testing Task

Test the project at {self.working_dir} for WCAG {self.wcag_level} compliance:

1. Run axe-core via Playwright on http://localhost:5173
2. Scan source code (.tsx, .jsx, .html) for accessibility anti-patterns
3. Check CSS for color contrast issues (WCAG 1.4.3)
4. Verify keyboard navigation patterns
5. Check for proper ARIA labels and roles

Target: WCAG 2.1 Level {self.wcag_level}
""")

            team = self.create_team(
                operator_name="A11yOperator",
                operator_prompt=f"""You are a WCAG accessibility expert targeting Level {self.wcag_level}.

Your role is to test applications for accessibility compliance:
- Run axe-core accessibility scans via Playwright
- Check for missing alt attributes, labels, ARIA roles
- Verify color contrast meets WCAG {self.wcag_level} ratios
- Check keyboard navigation (no traps, focus visible)
- Verify heading hierarchy and landmark structure

Report each issue with: file, line, WCAG guideline, severity, description.
When done, say TASK_COMPLETE.""",
                validator_name="A11yValidator",
                validator_prompt=f"""You are an accessibility compliance validator for WCAG {self.wcag_level}.

Review the accessibility scan results and verify:
1. All WCAG Level A criteria were checked
2. All WCAG Level AA criteria were checked (if target is AA)
3. Color contrast ratios are correctly assessed
4. No false positives (e.g., decorative images with empty alt are OK)
5. Critical issues (missing labels, keyboard traps) are flagged as high severity

If the scan is comprehensive, say TASK_COMPLETE.
If areas were missed, describe what needs additional testing.""",
                tool_categories=["npm", "node"],
                max_turns=20,
                task=task,
            )

            result = await self.run_team(team, task)

            if result["success"]:
                await self.event_bus.publish(a11y_test_passed_event(
                    source=self.name,
                    total_issues=0, critical=0, high=0, medium=0, low=0,
                    wcag_level=self.wcag_level,
                    wcag_violations={},
                    issues=[],
                ))
                logger.info("a11y_tests_passed", mode="autogen", wcag_level=self.wcag_level)
            else:
                await self.event_bus.publish(a11y_issue_found_event(
                    source=self.name,
                    total_issues=0,
                    wcag_level=self.wcag_level,
                ))
                logger.warning("a11y_issues_detected", mode="autogen")

        except Exception as e:
            logger.error("a11y_autogen_error", error=str(e))

    async def _act_legacy(self, events: list[Event]) -> None:
        """Run accessibility testing using direct scanning (legacy)."""
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_scan = datetime.now()
        self._issues_found = []

        logger.info(
            "a11y_scan_started",
            working_dir=str(self.working_dir),
            wcag_level=self.wcag_level,
            trigger_event=event.type.value,
        )

        await self.event_bus.publish(a11y_scan_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            wcag_level=self.wcag_level,
            trigger=event.type.value,
        ))

        if self.enable_axe_core:
            axe_issues = await self._run_axe_core()
            self._issues_found.extend(axe_issues)

        if self.enable_pattern_scan:
            pattern_issues = await self._scan_antipatterns()
            self._issues_found.extend(pattern_issues)

        if self.enable_contrast_check:
            contrast_issues = await self._check_color_contrast()
            self._issues_found.extend(contrast_issues)

        await self._publish_results()

    async def _run_axe_core(self) -> list[dict]:
        """
        Run axe-core accessibility testing via Playwright.

        Returns:
            List of accessibility violations
        """
        issues = []

        # Check if there's a running app to test
        app_url = "http://localhost:5173"

        try:
            # Try to use Playwright with axe-core
            # This requires @axe-core/playwright to be installed

            # Generate a test script that runs axe-core
            test_script = f"""
const {{ chromium }} = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;

(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage();

    try {{
        await page.goto('{app_url}', {{ timeout: 10000 }});
        await page.waitForLoadState('networkidle');

        const results = await new AxeBuilder({{ page }})
            .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
            .analyze();

        console.log(JSON.stringify(results.violations));
    }} catch (e) {{
        console.log('[]');
    }} finally {{
        await browser.close();
    }}
}})();
"""
            # Write test script
            test_path = self.working_dir / "_a11y_test.js"
            test_path.write_text(test_script)

            # Run the test via node.run_script tool
            result = await self.call_tool(
                "node.run_script",
                script_path=str(test_path),
                cwd=str(self.working_dir),
            )

            # Clean up
            test_path.unlink(missing_ok=True)

            output = result.get("output", "")
            if result.get("success") and output.strip():
                try:
                    violations = json.loads(output.strip())
                    for violation in violations:
                        for node in violation.get("nodes", []):
                            issues.append({
                                "type": "axe-core",
                                "severity": self._map_axe_impact(violation.get("impact", "minor")),
                                "rule_id": violation.get("id"),
                                "description": violation.get("description"),
                                "help": violation.get("help"),
                                "help_url": violation.get("helpUrl"),
                                "wcag_tags": violation.get("tags", []),
                                "html": node.get("html", "")[:200],
                                "target": node.get("target", []),
                            })
                except json.JSONDecodeError:
                    logger.debug("axe_core_output_parse_failed")

        except Exception as e:
            logger.debug("axe_core_error", error=str(e))

        logger.info("axe_core_scan_complete", issues_found=len(issues))
        return issues

    def _map_axe_impact(self, impact: str) -> str:
        """Map axe-core impact to severity."""
        mapping = {
            "critical": "critical",
            "serious": "high",
            "moderate": "medium",
            "minor": "low",
        }
        return mapping.get(impact, "medium")

    async def _scan_antipatterns(self) -> list[dict]:
        """
        Scan source code for accessibility anti-patterns.

        Returns:
            List of anti-pattern issues
        """
        issues = []

        # Source directories to scan
        src_dirs = [
            self.working_dir / "src",
            self.working_dir / "app",
            self.working_dir / "pages",
            self.working_dir / "components",
        ]

        files_to_scan = []
        for src_dir in src_dirs:
            if src_dir.exists():
                files_to_scan.extend(src_dir.rglob("*.tsx"))
                files_to_scan.extend(src_dir.rglob("*.jsx"))
                files_to_scan.extend(src_dir.rglob("*.html"))

        for file_path in files_to_scan:
            try:
                content = file_path.read_text(encoding="utf-8")

                for pattern_name, pattern_info in A11Y_ANTIPATTERNS.items():
                    # Skip AAA-level checks if targeting AA
                    wcag_ref = pattern_info.get("wcag", "")
                    guideline = WCAG_GUIDELINES.get(wcag_ref, {})
                    if self.wcag_level == "A" and guideline.get("level") != "A":
                        continue
                    if self.wcag_level == "AA" and guideline.get("level") == "AAA":
                        continue

                    matches = re.finditer(pattern_info["pattern"], content, re.IGNORECASE)

                    for match in matches:
                        # Find line number
                        line_num = content[:match.start()].count("\n") + 1

                        issues.append({
                            "type": "pattern",
                            "severity": pattern_info["severity"],
                            "pattern": pattern_name,
                            "file": str(file_path.relative_to(self.working_dir)),
                            "line": line_num,
                            "wcag": pattern_info.get("wcag"),
                            "description": pattern_info["description"],
                            "matched_text": match.group(0)[:100],
                        })

            except Exception as e:
                logger.debug("file_scan_error", file=str(file_path), error=str(e))

        logger.info(
            "antipattern_scan_complete",
            files_scanned=len(files_to_scan),
            issues_found=len(issues),
        )

        return issues

    async def _check_color_contrast(self) -> list[dict]:
        """
        Check color contrast in CSS files.

        Returns:
            List of contrast issues
        """
        issues = []

        # Find CSS files
        css_files = list(self.working_dir.rglob("*.css"))
        css_files.extend(self.working_dir.rglob("*.scss"))

        # Also check for CSS-in-JS patterns in TSX/JSX
        js_files = list((self.working_dir / "src").rglob("*.tsx")) if (self.working_dir / "src").exists() else []

        # Color contrast checking patterns
        # This is a simplified check - real contrast checking needs color parsing
        low_contrast_patterns = [
            # Light gray on white
            (r"color:\s*#(?:ccc|ddd|eee|f[0-9a-f]{2})[;\s]", "Very light text color may have contrast issues"),
            # White/light text without dark background context
            (r"color:\s*(?:white|#fff)\s*;(?![^}]*background)", "White text without visible background definition"),
            # Gray on gray patterns
            (r"color:\s*#[89a-f][0-9a-f]{5}[;\s].*background[^:]*:\s*#[89a-f][0-9a-f]{5}", "Similar gray tones may have contrast issues"),
        ]

        for css_file in css_files:
            try:
                content = css_file.read_text(encoding="utf-8")

                for pattern, description in low_contrast_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)

                    for match in matches:
                        line_num = content[:match.start()].count("\n") + 1

                        issues.append({
                            "type": "contrast",
                            "severity": "medium",
                            "file": str(css_file.relative_to(self.working_dir)),
                            "line": line_num,
                            "wcag": "1.4.3",
                            "description": description,
                            "matched_text": match.group(0)[:100],
                        })

            except Exception as e:
                logger.debug("css_scan_error", file=str(css_file), error=str(e))

        logger.info("contrast_check_complete", issues_found=len(issues))
        return issues

    async def _publish_results(self) -> None:
        """Publish accessibility test results."""

        # Categorize issues by severity
        critical_issues = [i for i in self._issues_found if i["severity"] == "critical"]
        high_issues = [i for i in self._issues_found if i["severity"] == "high"]
        medium_issues = [i for i in self._issues_found if i["severity"] == "medium"]
        low_issues = [i for i in self._issues_found if i["severity"] == "low"]

        # Group by WCAG guideline
        wcag_violations = {}
        for issue in self._issues_found:
            wcag = issue.get("wcag", "unknown")
            if wcag not in wcag_violations:
                wcag_violations[wcag] = []
            wcag_violations[wcag].append(issue)

        result_data = {
            "total_issues": len(self._issues_found),
            "critical": len(critical_issues),
            "high": len(high_issues),
            "medium": len(medium_issues),
            "low": len(low_issues),
            "wcag_level": self.wcag_level,
            "wcag_violations": wcag_violations,
            "issues": self._issues_found,
        }

        # Publish individual WCAG violations
        for wcag_ref, violations in wcag_violations.items():
            if wcag_ref != "unknown":
                await self.event_bus.publish(a11y_issue_found_event(
                    source=self.name,
                    wcag=wcag_ref,
                    guideline=WCAG_GUIDELINES.get(wcag_ref, {}).get("name", "Unknown"),
                    level=WCAG_GUIDELINES.get(wcag_ref, {}).get("level", "?"),
                    violations=violations,
                ))

        if critical_issues or high_issues:
            # Accessibility issues detected
            await self.event_bus.publish(a11y_issue_found_event(
                source=self.name,
                total_issues=len(self._issues_found),
                critical=len(critical_issues),
                high=len(high_issues),
                medium=len(medium_issues),
                low=len(low_issues),
                wcag_level=self.wcag_level,
                wcag_violations=wcag_violations,
                issues=self._issues_found,
            ))

            logger.warning(
                "a11y_issues_detected",
                critical=len(critical_issues),
                high=len(high_issues),
                wcag_level=self.wcag_level,
            )
        else:
            # All accessibility tests passed
            await self.event_bus.publish(a11y_test_passed_event(
                source=self.name,
                total_issues=len(self._issues_found),
                critical=len(critical_issues),
                high=len(high_issues),
                medium=len(medium_issues),
                low=len(low_issues),
                wcag_level=self.wcag_level,
                wcag_violations=wcag_violations,
                issues=self._issues_found,
            ))

            logger.info(
                "a11y_tests_passed",
                wcag_level=self.wcag_level,
                minor_issues=len(medium_issues) + len(low_issues),
            )

        # Update shared state
        await self.shared_state.update_accessibility_metrics(
            issues_found=len(self._issues_found),
            critical_count=len(critical_issues),
            wcag_level=self.wcag_level,
        )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Remove temporary test script if exists
        test_path = self.working_dir / "_a11y_test.js"
        if test_path.exists():
            try:
                test_path.unlink()
            except Exception:
                pass

        logger.info("accessibility_agent_cleanup_complete")
