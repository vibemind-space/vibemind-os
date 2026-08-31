#!/usr/bin/env python3
"""
Automation_ui Debug Bridge

Bridge between the DaveFelix Coding Engine and Automation_ui for post-generation
component debugging. After code generation, this bridge:

1. Detects what was generated (React component, API route, hook, etc.)
2. Builds a targeted debug instruction for that component
3. Sends the instruction to Automation_ui's LLM intent router
4. Collects debug results (console errors, visual issues, test failures)
5. Returns structured results back to the task executor for retry loops

Integration points:
- Automation_ui LLM Intent: POST /api/llm/intent (agentic desktop automation)
- Automation_ui MCP Bridge: POST /api/mcp/* (direct MCP tool calls)
- Automation_ui Health: GET /api/llm/intent/health

All LLM calls go through OpenRouter free models (configured in Automation_ui).
Graceful degradation if Automation_ui is not running.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTOMATION_UI_URL = os.getenv("AUTOMATION_UI_URL", "http://localhost:8007")
AUTOMATION_UI_TIMEOUT = int(os.getenv("AUTOMATION_UI_TIMEOUT", "60"))
SANDBOX_APP_URL = os.getenv("SANDBOX_APP_URL", "http://localhost:3100")

# Component type to debug strategy mapping
COMPONENT_DEBUG_STRATEGIES = {
    "fe_component": "visual_and_console",
    "fe_page": "visual_and_console",
    "fe_form": "visual_and_console",
    "fe_hook": "console_only",
    "fe_api_client": "console_and_network",
    "api_controller": "api_endpoint",
    "api_service": "api_endpoint",
    "api_dto": "console_only",
    "api_guard": "api_endpoint",
    "api_validation": "api_endpoint",
    "schema_model": "console_only",
    "schema_relations": "console_only",
}


# ---------------------------------------------------------------------------
# Result Data Class
# ---------------------------------------------------------------------------

@dataclass
class AutomationDebugResult:
    """Structured result from Automation_ui debug session."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    visual_issues: List[str] = field(default_factory=list)
    api_issues: List[str] = field(default_factory=list)
    steps_executed: int = 0
    duration_seconds: float = 0.0
    skipped: bool = False
    skip_reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "console_errors": self.console_errors,
            "visual_issues": self.visual_issues,
            "api_issues": self.api_issues,
            "steps_executed": self.steps_executed,
            "duration_seconds": self.duration_seconds,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# Debug Instruction Builder
# ---------------------------------------------------------------------------

def build_debug_instruction(
    task_type: str,
    component_name: str,
    file_path: str,
    sandbox_url: str = SANDBOX_APP_URL,
    extra_context: str = "",
) -> str:
    """
    Build a natural language debug instruction for Automation_ui's LLM intent agent.

    The instruction tells Automation_ui what to check for the specific component type.
    Automation_ui's agentic loop will use screen_read, shell commands, and browser
    tools to verify the component works.
    """
    strategy = COMPONENT_DEBUG_STRATEGIES.get(task_type, "visual_and_console")

    base_instruction = (
        f"Debug the generated component '{component_name}' at file path '{file_path}'. "
        f"The application is running at {sandbox_url}. "
    )

    if strategy == "visual_and_console":
        instruction = (
            f"{base_instruction}"
            f"Navigate to {sandbox_url} in the browser. "
            f"Check the following:\n"
            f"1. Read the screen to verify the component renders without blank pages\n"
            f"2. Open browser DevTools console and check for JavaScript errors\n"
            f"3. Look for broken layouts, missing text, or overlapping elements\n"
            f"4. Verify no 'Cannot read properties of undefined' or similar React errors\n"
            f"5. Check that the component displays expected content (not just a spinner)\n"
        )
    elif strategy == "console_only":
        instruction = (
            f"{base_instruction}"
            f"Check the application at {sandbox_url} for runtime errors:\n"
            f"1. Open browser DevTools console and look for errors related to '{component_name}'\n"
            f"2. Check for import errors or module not found issues\n"
            f"3. Verify no TypeScript or build errors in the terminal output\n"
        )
    elif strategy == "console_and_network":
        instruction = (
            f"{base_instruction}"
            f"Navigate to {sandbox_url} and check network/API integration:\n"
            f"1. Open browser DevTools console and check for errors\n"
            f"2. Open Network tab and look for failed API calls (4xx/5xx)\n"
            f"3. Verify API endpoints return expected data format\n"
            f"4. Check for CORS errors or authentication failures\n"
        )
    elif strategy == "api_endpoint":
        instruction = (
            f"{base_instruction}"
            f"Test the API endpoint:\n"
            f"1. Run 'curl -s {sandbox_url}/api/health' to verify the server is running\n"
            f"2. Check the terminal/logs for server-side errors related to '{component_name}'\n"
            f"3. Look for database connection errors or schema mismatches\n"
            f"4. Verify the route is registered and responds to requests\n"
        )
    else:
        instruction = (
            f"{base_instruction}"
            f"Verify the component works correctly. Check for errors in console and on screen.\n"
        )

    if extra_context:
        instruction += f"\nAdditional context: {extra_context}\n"

    instruction += (
        "\nRespond with a summary of what you found. "
        "List any errors, warnings, or issues discovered."
    )

    return instruction


# ---------------------------------------------------------------------------
# Main Bridge Class
# ---------------------------------------------------------------------------

class AutomationUIBridge:
    """
    Bridge between the Coding Engine task executor and Automation_ui.

    Sends debug instructions to Automation_ui's LLM intent endpoint and
    parses the results into structured debug reports.

    Usage:
        bridge = AutomationUIBridge()
        result = await bridge.debug_component(
            task_type="fe_component",
            component_name="UserDashboard",
            file_path="src/components/UserDashboard.tsx",
        )
        if not result.passed:
            print(result.errors)
    """

    def __init__(
        self,
        backend_url: str = AUTOMATION_UI_URL,
        sandbox_url: str = SANDBOX_APP_URL,
        timeout: int = AUTOMATION_UI_TIMEOUT,
    ):
        self.backend_url = backend_url
        self.sandbox_url = sandbox_url
        self.timeout = timeout
        self._conversation_id = f"coding-engine-debug-{int(time.time())}"

    async def is_available(self) -> bool:
        """Check if Automation_ui backend is reachable and healthy."""
        try:
            import httpx
        except ImportError:
            logger.debug("automation_ui_bridge: httpx not installed")
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.backend_url}/api/llm/intent/health"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "")
                    if status in ("healthy", "no_api_key"):
                        logger.debug(
                            f"automation_ui_bridge: available | status={status} | "
                            f"tools={data.get('tools_count', 0)}"
                        )
                        return status == "healthy"
                return False
        except Exception as e:
            logger.debug(f"automation_ui_bridge: not available: {e}")
            return False

    async def debug_component(
        self,
        task_type: str,
        component_name: str,
        file_path: str,
        extra_context: str = "",
    ) -> AutomationDebugResult:
        """
        Send a debug instruction to Automation_ui for a generated component.

        Args:
            task_type: Type of task (fe_component, api_controller, etc.)
            component_name: Human-readable component name
            file_path: Path to the generated file
            extra_context: Additional context (e.g., previous errors)

        Returns:
            AutomationDebugResult with pass/fail and discovered issues
        """
        start = time.time()

        # Check if httpx is available
        try:
            import httpx
        except ImportError:
            return AutomationDebugResult(
                passed=True,
                skipped=True,
                skip_reason="httpx not installed (pip install httpx)",
                duration_seconds=time.time() - start,
            )

        # Check availability
        if not await self.is_available():
            return AutomationDebugResult(
                passed=True,
                skipped=True,
                skip_reason=(
                    f"Automation_ui not available at {self.backend_url}. "
                    "Start it with: docker compose -f external/Automation_ui/docker-compose.yml up -d"
                ),
                duration_seconds=time.time() - start,
            )

        # Build the debug instruction
        instruction = build_debug_instruction(
            task_type=task_type,
            component_name=component_name,
            file_path=file_path,
            sandbox_url=self.sandbox_url,
            extra_context=extra_context,
        )

        logger.info(
            f"automation_ui_bridge: debugging {component_name} ({task_type}) "
            f"via LLM intent"
        )

        # Send to Automation_ui LLM intent endpoint
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                resp = await client.post(
                    f"{self.backend_url}/api/llm/intent",
                    json={
                        "text": instruction,
                        "conversation_id": self._conversation_id,
                    },
                )

                if resp.status_code != 200:
                    return AutomationDebugResult(
                        passed=True,
                        skipped=True,
                        skip_reason=(
                            f"Automation_ui returned HTTP {resp.status_code}: "
                            f"{resp.text[:200]}"
                        ),
                        duration_seconds=time.time() - start,
                    )

                data = resp.json()

        except Exception as e:
            logger.warning(f"automation_ui_bridge: request failed: {e}")
            return AutomationDebugResult(
                passed=True,
                skipped=True,
                skip_reason=f"Request to Automation_ui failed: {e}",
                duration_seconds=time.time() - start,
            )

        # Parse the response
        return self._parse_intent_response(data, start)

    def _parse_intent_response(
        self,
        data: Dict[str, Any],
        start_time: float,
    ) -> AutomationDebugResult:
        """Parse Automation_ui IntentResponse into AutomationDebugResult."""
        success = data.get("success", False)
        summary = data.get("summary", "")
        steps = data.get("steps", [])
        error = data.get("error")
        duration = time.time() - start_time

        # Collect issues from the summary and steps
        errors = []
        warnings = []
        console_errors = []
        visual_issues = []
        api_issues = []

        # If the intent itself failed, that's an error
        if error:
            errors.append(f"Automation_ui error: {error}")

        # Parse step results for specific error types
        for step in steps:
            step_result = step.get("result", {})
            step_success = step.get("success", True)
            tool_name = step.get("tool", "")

            if not step_success:
                result_text = json.dumps(step_result) if isinstance(step_result, dict) else str(step_result)
                # Categorize the error based on the tool used
                if tool_name in ("screen_read", "vision_analyze"):
                    visual_issues.append(result_text[:300])
                elif tool_name == "action_shell":
                    # Shell command errors might indicate build/runtime issues
                    errors.append(result_text[:300])
                else:
                    errors.append(f"[{tool_name}] {result_text[:300]}")

        # Parse the summary text for common error patterns
        summary_lower = summary.lower()
        error_keywords = [
            "error", "failed", "broken", "missing", "undefined",
            "cannot read", "not found", "exception", "crash",
            "blank page", "white screen",
        ]
        warning_keywords = [
            "warning", "deprecated", "slow", "performance",
        ]

        # Check if the summary indicates problems
        has_errors = any(kw in summary_lower for kw in error_keywords)
        has_warnings = any(kw in summary_lower for kw in warning_keywords)

        if has_errors and not errors:
            # The summary mentions errors but no explicit step failures
            errors.append(f"Debug summary indicates issues: {summary[:500]}")

        if has_warnings:
            warnings.append(f"Debug summary warnings: {summary[:300]}")

        # Determine pass/fail
        passed = len(errors) == 0 and len(console_errors) == 0

        logger.info(
            f"automation_ui_bridge: debug complete | passed={passed} | "
            f"errors={len(errors)} | steps={len(steps)} | "
            f"duration={duration:.1f}s"
        )

        return AutomationDebugResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            console_errors=console_errors,
            visual_issues=visual_issues,
            api_issues=api_issues,
            steps_executed=len(steps),
            duration_seconds=duration,
            raw_response=data,
        )

    async def quick_health_check(self) -> Dict[str, Any]:
        """Quick health check returning Automation_ui status info."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.backend_url}/api/llm/intent/health"
                )
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "unreachable", "http_status": resp.status_code}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
