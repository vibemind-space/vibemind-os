"""
OpenClaw Bridge Tool — Connects Coding Engine to OpenClaw browser automation agent.

After code generation, sends debug/test instructions to the OpenClaw agent
running inside Docker. The agent navigates the live preview, tests UI components,
and reports errors back for the fix loop.

Usage:
    bridge = OpenClawBridge()
    result = await bridge.debug_component(
        preview_url="http://host.docker.internal:3100",
        component="LoginForm",
        instructions="Test login with valid and invalid credentials"
    )
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

import os
from src.utils.secrets import get_secret

OPENCLAW_CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "openclaw-openclaw-gateway-1")
OPENCLAW_GATEWAY_TOKEN = get_secret("openclaw_gateway_token", env_fallback="OPENCLAW_GATEWAY_TOKEN")


@dataclass
class DebugResult:
    """Result from an OpenClaw debug session."""
    success: bool
    errors: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    raw_output: str = ""
    agent_id: str = ""


class OpenClawBridge:
    """Bridge between Coding Engine and OpenClaw browser automation agent."""

    def __init__(
        self,
        container: str = OPENCLAW_CONTAINER,
        gateway_token: str = OPENCLAW_GATEWAY_TOKEN,
        timeout: int = 120,
    ):
        self.container = container
        self.gateway_token = gateway_token
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Check if OpenClaw gateway is reachable."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "exec", self.container,
                "openclaw", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception as e:
            logger.warning("OpenClaw not available: %s", e)
            return False

    async def run_agent(
        self,
        message: str,
        agent_id: str = "main",
        session_id: Optional[str] = None,
        thinking: str = "medium",
    ) -> DebugResult:
        """Run an OpenClaw agent turn with a message."""
        cmd = [
            "docker", "exec", self.container,
            "openclaw", "agent",
            "--agent", agent_id,
            "--local",
            "-m", message,
            "--json",
            "--thinking", thinking,
            "--timeout", str(self.timeout),
        ]
        if session_id:
            cmd.extend(["--session-id", session_id])

        logger.info("OpenClaw agent [%s]: %s...", agent_id, message[:100])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout + 30
            )

            raw = stdout.decode("utf-8", errors="replace")
            result = DebugResult(
                success=proc.returncode == 0,
                raw_output=raw,
                agent_id=agent_id,
            )

            # Try to parse JSON output
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    result.errors = data.get("errors", [])
                    result.suggestions = data.get("suggestions", [])
                    result.screenshots = data.get("screenshots", [])
            except json.JSONDecodeError:
                # Non-JSON output — extract errors from text
                for line in raw.split("\n"):
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in ["error", "fail", "broken", "crash", "exception"]):
                        result.errors.append(line.strip())
                    elif any(kw in line_lower for kw in ["suggest", "fix", "should", "try"]):
                        result.suggestions.append(line.strip())

            return result

        except asyncio.TimeoutError:
            logger.error("OpenClaw agent timed out after %ds", self.timeout)
            return DebugResult(
                success=False,
                errors=["Agent timed out after %ds" % self.timeout],
                raw_output="TIMEOUT",
            )
        except Exception as e:
            logger.error("OpenClaw agent error: %s", e)
            return DebugResult(
                success=False,
                errors=[str(e)],
                raw_output=str(e),
            )

    async def debug_component(
        self,
        preview_url: str,
        component: str,
        instructions: str = "",
        requirements: str = "",
    ) -> DebugResult:
        """
        Send a debug task to OpenClaw for a specific UI component.

        Args:
            preview_url: URL of the live preview (e.g. http://host.docker.internal:3100)
            component: Name of the component to test
            instructions: Specific test instructions
            requirements: Original requirements for validation
        """
        parts = [
            "You are a QA browser automation agent. Your task:",
            "",
            "1. Navigate to: %s" % preview_url,
            '2. Find and test the "%s" component' % component,
            "3. Check for:",
            "   - Visual rendering issues (layout, spacing, colors)",
            "   - Console errors in the browser",
            "   - Broken links or missing images",
            "   - Form validation (if applicable)",
            "   - Responsive behavior",
        ]
        if instructions:
            parts.append("4. Specific instructions: %s" % instructions)
        if requirements:
            parts.append("5. Validate against requirements: %s" % requirements)

        parts.extend([
            "",
            "Report your findings as JSON with fields:",
            '  component, status ("pass"/"fail"), errors (list), suggestions (list), screenshots (list)',
        ])

        prompt = "\n".join(parts)
        return await self.run_agent(message=prompt, thinking="high")

    async def debug_full_app(
        self,
        preview_url: str,
        routes: list = None,
    ) -> list:
        """
        Run a full-app debug session, testing all routes.

        Args:
            preview_url: Base URL of the app
            routes: List of routes to test (default: ["/"])
        """
        if not routes:
            routes = ["/"]

        results = []
        for route in routes:
            url = "%s%s" % (preview_url, route)
            prompt = "\n".join([
                "You are a QA browser automation agent. Test this page:",
                "",
                "1. Navigate to: %s" % url,
                "2. Take a screenshot",
                "3. Check for:",
                "   - Console errors",
                "   - Network errors (failed API calls)",
                "   - Visual issues (overlapping elements, broken layouts)",
                "   - Missing content or 404s",
                "   - Accessibility issues (missing alt text, contrast)",
                "4. Click all visible buttons and links — report any that crash",
                "",
                "Report findings as JSON with fields:",
                '  url, status ("pass"/"fail"), errors (list), suggestions (list), screenshots (list)',
            ])
            result = await self.run_agent(message=prompt, thinking="medium")
            results.append(result)

        return results

    async def fix_and_retest(
        self,
        preview_url: str,
        component: str,
        error_description: str,
        max_retries: int = 3,
    ) -> DebugResult:
        """
        After applying a fix, retest the component.
        Used in the Generate -> Test -> Fix -> Re-Test cycle.
        """
        result = None
        for attempt in range(max_retries):
            logger.info("Retest attempt %d/%d for %s", attempt + 1, max_retries, component)

            result = await self.debug_component(
                preview_url=preview_url,
                component=component,
                instructions="Previous error was: %s. A fix was applied. Verify the fix works." % error_description,
            )

            if result.success and not result.errors:
                logger.info("Component %s passed after %d retests", component, attempt + 1)
                return result

            logger.warning("Component %s still has issues: %s", component, result.errors[:3])

        return result

    # ── Phase 2: Skill-Aware Agent Execution ──────────────────────────

    SKILL_MAP = {
        "code-generation": "dev",
        "debugging": "debug",
        "e2e-testing": "qa",
        "ux-review": "design",
        "test-generation": "test",
        "validation": "validator",
    }

    def _load_skill(self, skill_name: str) -> str:
        """Load a skill's SKILL.md content for injection into OpenClaw agent prompt."""
        import pathlib
        # Try multiple skill locations
        for base in [
            pathlib.Path("/app/.claude/skills"),
            pathlib.Path(__file__).parent.parent.parent / ".claude" / "skills",
        ]:
            skill_file = base / skill_name / "SKILL.md"
            if skill_file.exists():
                content = skill_file.read_text(encoding="utf-8", errors="replace")
                # Truncate to ~2000 chars for prompt budget
                if len(content) > 2000:
                    content = content[:2000] + "\n...(truncated)"
                return content
        return ""

    async def run_with_skill(
        self,
        task_description: str,
        skill_name: str,
        context: str = "",
        file_paths: list = None,
    ) -> DebugResult:
        """
        Run OpenClaw agent with a Coding Engine skill injected as system context.

        This exposes our 12 skills to OpenClaw agents, so they can generate code,
        debug errors, run tests, etc. using the same quality standards.
        """
        skill_content = self._load_skill(skill_name)
        agent_id = self.SKILL_MAP.get(skill_name, "main")

        parts = [
            "=== SKILL INSTRUCTIONS ===",
            skill_content if skill_content else "(no skill loaded for %s)" % skill_name,
            "",
            "=== TASK ===",
            task_description,
        ]
        if context:
            parts.extend(["", "=== CONTEXT ===", context])
        if file_paths:
            parts.extend(["", "=== FILES ===", "\n".join(file_paths)])

        prompt = "\n".join(parts)
        logger.info("OpenClaw skill-agent [%s/%s]: %s...", agent_id, skill_name, task_description[:80])
        return await self.run_agent(message=prompt, agent_id=agent_id, thinking="high")

    async def generate_code(self, task: dict, fungus_context: str = "") -> DebugResult:
        """Use OpenClaw + code-generation skill to produce real code."""
        desc = task.get("description", task.get("title", ""))
        files = task.get("files", [])
        return await self.run_with_skill(
            task_description="Generate production-ready code for: %s" % desc,
            skill_name="code-generation",
            context=fungus_context,
            file_paths=files,
        )

    async def debug_error(self, error: str, file_path: str = "", stack: str = "") -> DebugResult:
        """Use OpenClaw + debugging skill to analyze and fix an error."""
        return await self.run_with_skill(
            task_description="Debug this error:\n%s\n\nFile: %s\nStack: %s" % (error, file_path, stack),
            skill_name="debugging",
        )

    async def run_e2e_test(self, preview_url: str, test_spec: str = "") -> DebugResult:
        """Use OpenClaw + e2e-testing skill to run browser tests."""
        return await self.run_with_skill(
            task_description="Run E2E tests on %s\n\nTest spec:\n%s" % (preview_url, test_spec),
            skill_name="e2e-testing",
        )

    async def review_ux(self, preview_url: str, screenshot_path: str = "") -> DebugResult:
        """Use OpenClaw + ux-review skill to analyze UI quality."""
        return await self.run_with_skill(
            task_description="Review UX quality of %s\nScreenshot: %s" % (preview_url, screenshot_path),
            skill_name="ux-review",
        )
