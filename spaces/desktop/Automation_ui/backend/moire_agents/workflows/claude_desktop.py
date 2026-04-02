"""
Claude Desktop Workflow - Automation for Claude Desktop interactions.

Provides:
- Open Claude Desktop via hotkey (Ctrl+Alt+Space)
- Send tasks to Claude chat
- Wait for response completion
- Extract response content
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .base_workflow import BaseWorkflow, WorkflowStep, WorkflowResult

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional imports
try:
    from agents.progress_agent import ProgressAgent
    HAS_PROGRESS_AGENT = True
except ImportError:
    HAS_PROGRESS_AGENT = False
    ProgressAgent = None

try:
    from core.localization import L
    HAS_LOCALIZATION = True
except ImportError:
    HAS_LOCALIZATION = False
    L = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ClaudeResponse:
    """Response from Claude Desktop."""
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    response_time: float = 0.0


class ClaudeDesktopWorkflow(BaseWorkflow):
    """
    Workflow for interacting with Claude Desktop application.

    Features:
    - Open via Ctrl+Alt+Space hotkey
    - Send tasks to chat
    - Wait for and detect response completion
    - Integration with Progress Agent for monitoring
    """

    # Hotkey to open Claude Desktop
    OPEN_HOTKEY = ["ctrl", "alt", "space"]

    # Common task templates
    TASK_TEMPLATES = {
        "docker_debug": (
            "Generate a comprehensive debug report about Docker containers. "
            "Include: container status, running containers, recent logs, "
            "resource usage (CPU/memory), and any errors or warnings. "
            "Format the report as a Word document (.docx)."
        ),
        "system_status": (
            "Generate a system status report including: "
            "CPU usage, memory usage, disk space, running processes, "
            "and network connections. Save as a Word document."
        ),
        "git_summary": (
            "Analyze the current git repository and create a summary report: "
            "recent commits, branch status, uncommitted changes, "
            "and any merge conflicts. Output as Word document."
        )
    }

    def __init__(
        self,
        steering_agent=None,
        progress_agent: Optional[ProgressAgent] = None,
        response_timeout: float = 120.0
    ):
        super().__init__(
            steering_agent=steering_agent,
            progress_agent=progress_agent,
            name="ClaudeDesktop"
        )
        self.response_timeout = response_timeout

    def define_steps(
        self,
        task: str = "",
        template: Optional[str] = None,
        wait_for_response: bool = True,
        **kwargs
    ) -> List[WorkflowStep]:
        """
        Define steps for Claude Desktop interaction.

        Args:
            task: The task text to send to Claude
            template: Optional template name from TASK_TEMPLATES
            wait_for_response: Whether to wait for Claude's response
            **kwargs: Additional parameters

        Returns:
            List of WorkflowStep objects
        """
        # Use template if provided
        if template and template in self.TASK_TEMPLATES:
            task = self.TASK_TEMPLATES[template]

        if not task:
            raise ValueError("Task text or template required")

        # Localized descriptions
        if HAS_LOCALIZATION and L:
            desc_open = L.get('workflow_claude_open') if hasattr(L, 'get') else "Open Claude Desktop"
            desc_wait_open = L.get('wait_for_app', app='Claude Desktop') if hasattr(L, 'get') else "Wait for Claude Desktop"
            desc_click_input = L.get('click_on', target='chat input') if hasattr(L, 'get') else "Click chat input"
            desc_type_task = L.get('workflow_claude_send') if hasattr(L, 'get') else "Send task to Claude"
            desc_send = L.get('press_enter') if hasattr(L, 'get') else "Press Enter to send"
            desc_wait_response = "Wait for Claude response"
        else:
            desc_open = "Open Claude Desktop"
            desc_wait_open = "Wait for Claude Desktop to open"
            desc_click_input = "Click on chat input field"
            desc_type_task = "Type task for Claude"
            desc_send = "Press Enter to send message"
            desc_wait_response = "Wait for Claude's response"

        steps = [
            # Step 1: Open Claude Desktop with hotkey
            WorkflowStep(
                id="open_claude",
                action_type="hotkey",
                params={"keys": self.OPEN_HOTKEY},
                description=desc_open,
                timeout=5.0
            ),

            # Step 2: Wait for window to appear
            WorkflowStep(
                id="wait_open",
                action_type="sleep",
                params={"seconds": 2.0},
                description=desc_wait_open,
                timeout=10.0
            ),

            # Step 3: Click on chat input field
            WorkflowStep(
                id="click_input",
                action_type="find_and_click",
                params={"target": "chat input field", "fallback_click": True},
                description=desc_click_input,
                timeout=10.0
            ),

            # Step 4: Small wait for focus
            WorkflowStep(
                id="wait_focus",
                action_type="sleep",
                params={"seconds": 0.5},
                description="Wait for input focus",
                timeout=2.0
            ),

            # Step 5: Type the task
            WorkflowStep(
                id="type_task",
                action_type="write",
                params={"text": task, "interval": 0.01},
                description=desc_type_task,
                timeout=30.0
            ),

            # Step 6: Press Enter to send
            WorkflowStep(
                id="send_message",
                action_type="press",
                params={"key": "enter"},
                description=desc_send,
                timeout=5.0
            ),
        ]

        # Step 7: Wait for response (optional)
        if wait_for_response:
            steps.append(
                WorkflowStep(
                    id="wait_response",
                    action_type="wait_for_element",
                    params={
                        "target": "response complete indicator",
                        "timeout": self.response_timeout,
                        "poll_interval": 2.0
                    },
                    description=desc_wait_response,
                    timeout=self.response_timeout + 10
                )
            )

        return steps

    async def send_task(
        self,
        task: str,
        template: Optional[str] = None,
        wait_for_response: bool = True
    ) -> WorkflowResult:
        """
        Send a task to Claude Desktop.

        Convenience method that wraps execute().

        Args:
            task: Task text to send
            template: Optional template name
            wait_for_response: Whether to wait for response

        Returns:
            WorkflowResult with execution details
        """
        return await self.execute(
            task=task,
            template=template,
            wait_for_response=wait_for_response
        )

    async def open_and_send(self, task: str) -> WorkflowResult:
        """
        Quick method to open Claude Desktop and send a task.

        Args:
            task: Task to send

        Returns:
            WorkflowResult
        """
        return await self.send_task(task, wait_for_response=False)

    async def docker_debug_report(self) -> WorkflowResult:
        """
        Send Docker debug report task to Claude.

        Returns:
            WorkflowResult
        """
        return await self.send_task(template="docker_debug", wait_for_response=True)

    async def system_status_report(self) -> WorkflowResult:
        """
        Send system status report task to Claude.

        Returns:
            WorkflowResult
        """
        return await self.send_task(template="system_status", wait_for_response=True)

    async def _execute_step(self, step: WorkflowStep) -> Dict[str, Any]:
        """Override to handle Claude-specific step types."""

        # Handle wait_for_element specially
        if step.action_type == "wait_for_element":
            return await self._wait_for_response(step)

        # Handle find_and_click with fallback
        if step.action_type == "find_and_click":
            return await self._find_and_click_with_fallback(step)

        # Default handling
        return await super()._execute_step(step)

    async def _find_and_click_with_fallback(self, step: WorkflowStep) -> Dict[str, Any]:
        """
        Try to find and click element, with fallback to center click.
        """
        import pyautogui

        target = step.params.get("target", "")
        fallback = step.params.get("fallback_click", False)

        step.started_at = time.time()

        try:
            # Try via steering agent first
            if self.steering_agent:
                result = await super()._execute_via_steering(step)
                if result.get("success"):
                    step.status = "completed"
                    step.finished_at = time.time()
                    return result

            # Fallback: click in center-bottom area (typical chat input location)
            if fallback:
                screen_width, screen_height = pyautogui.size()
                # Chat input is usually at bottom-center
                x = screen_width // 2
                y = int(screen_height * 0.85)  # 85% down the screen

                logger.info(f"Fallback click at ({x}, {y})")
                pyautogui.click(x, y)

                step.status = "completed"
                step.finished_at = time.time()
                return {"success": True, "action": "fallback_click", "x": x, "y": y}

            return {"success": False, "error": "Could not find element"}

        except Exception as e:
            step.status = "failed"
            step.error = str(e)
            step.finished_at = time.time()
            return {"success": False, "error": str(e)}

    async def _wait_for_response(self, step: WorkflowStep) -> Dict[str, Any]:
        """
        Wait for Claude to complete its response.

        Monitors screen for indicators that response is complete:
        - Stop button disappears
        - Response text stops growing
        - Specific completion indicators
        """
        timeout = step.params.get("timeout", self.response_timeout)
        poll_interval = step.params.get("poll_interval", 2.0)

        step.started_at = time.time()
        start_time = time.time()

        logger.info(f"Waiting for Claude response (timeout: {timeout}s)")

        last_screen_hash = None
        stable_count = 0
        required_stable = 3  # Need 3 stable readings to confirm done

        try:
            while time.time() - start_time < timeout:
                # Check if workflow was cancelled
                if self._cancelled:
                    return {"success": False, "error": "Cancelled"}

                # Capture current screen state
                if self.progress_agent:
                    current_state = await self.progress_agent._capture_current_state()

                    if current_state:
                        # Simple hash of OCR texts to detect changes
                        current_hash = hash(tuple(sorted(current_state.ocr_texts)))

                        if current_hash == last_screen_hash:
                            stable_count += 1
                            logger.debug(f"Screen stable ({stable_count}/{required_stable})")

                            if stable_count >= required_stable:
                                # Response appears complete
                                step.status = "completed"
                                step.finished_at = time.time()
                                return {
                                    "success": True,
                                    "action": "wait_for_response",
                                    "duration": time.time() - start_time,
                                    "stable_readings": stable_count
                                }
                        else:
                            stable_count = 0  # Reset counter
                            last_screen_hash = current_hash

                await asyncio.sleep(poll_interval)

            # Timeout reached
            step.status = "failed"
            step.error = "Timeout waiting for response"
            step.finished_at = time.time()
            return {
                "success": False,
                "error": "Timeout waiting for Claude response",
                "duration": time.time() - start_time
            }

        except Exception as e:
            step.status = "failed"
            step.error = str(e)
            step.finished_at = time.time()
            return {"success": False, "error": str(e)}

    @classmethod
    def quick_task(cls, task: str) -> 'ClaudeDesktopWorkflow':
        """
        Create a workflow configured for a quick task.

        Args:
            task: Task text

        Returns:
            Configured workflow instance
        """
        workflow = cls()
        workflow._quick_task = task
        return workflow

    async def execute_quick(self) -> WorkflowResult:
        """Execute the quick task if configured."""
        if hasattr(self, '_quick_task'):
            return await self.send_task(self._quick_task, wait_for_response=False)
        raise ValueError("No quick task configured")


# Convenience functions
async def send_to_claude(task: str, wait: bool = False) -> WorkflowResult:
    """
    Quick function to send a task to Claude Desktop.

    Args:
        task: Task text to send
        wait: Whether to wait for response

    Returns:
        WorkflowResult
    """
    workflow = ClaudeDesktopWorkflow()
    return await workflow.send_task(task, wait_for_response=wait)


async def claude_docker_debug() -> WorkflowResult:
    """Send Docker debug report task to Claude Desktop."""
    workflow = ClaudeDesktopWorkflow()
    return await workflow.docker_debug_report()
