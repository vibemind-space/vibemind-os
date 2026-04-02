"""
Orchestrator Agent - Root coordinator for handoff workflows

Main entry point agent that receives tasks, plans actions,
and delegates to specialized agents.
Part of the handoff pattern multi-agent system.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseHandoffAgent, AgentConfig
from .messages import UserTask, HandoffRequest, AgentResponse
from .tools import (
    transfer_to_execution,
    transfer_to_vision,
    transfer_to_recovery
)

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseHandoffAgent):
    """
    Root coordinator agent that manages workflow execution.

    Responsibilities:
    - Receives initial tasks from users
    - Plans action sequences
    - Delegates to specialized agents
    - Tracks overall progress
    - Returns final results
    """

    def __init__(self):
        config = AgentConfig(
            name="orchestrator",
            description="Coordinates workflow execution and delegates to specialists",
            topic_type="orchestrator",
            timeout=120.0
        )
        super().__init__(config)

        # Track workflow state
        self._current_step = 0
        self._total_steps = 0

    def _register_default_tools(self):
        """Register delegate tools."""
        self.register_delegate_tool(
            name="delegate_to_execution",
            target_agent="execution",
            description="Delegate keyboard/mouse action to execution agent"
        )

        self.register_delegate_tool(
            name="delegate_to_vision",
            target_agent="vision",
            description="Delegate element finding to vision agent"
        )

        self.register_delegate_tool(
            name="delegate_to_recovery",
            target_agent="recovery",
            description="Delegate error recovery"
        )

    async def _process_task(self, task: UserTask) -> Any:
        """
        Process a task - either plan and start, or continue workflow.

        The orchestrator handles multiple scenarios:
        1. New task: Plan actions and start execution
        2. Return from execution: Check result and continue
        3. Return from vision: Use coordinates and continue
        4. Return from recovery: Retry or fail
        """
        # Check if this is a return from another agent
        if task.context.get("returning_from"):
            return await self._handle_return(task)

        # New task - plan and execute
        return await self._start_workflow(task)

    async def _start_workflow(self, task: UserTask) -> Any:
        """Start a new workflow."""
        goal = task.goal

        await self.report_progress(task, 0.0, f"Planning: {goal[:50]}...")

        # Check if workflow is predefined
        workflow_type = task.context.get("workflow")

        if workflow_type == "claude_desktop":
            actions = self._plan_claude_desktop_workflow(task)
        else:
            # Generic workflow planning
            actions = self._plan_generic_workflow(task)

        if not actions:
            return {
                "success": False,
                "error": "Could not plan workflow"
            }

        # Store actions in task
        task.pending_actions = actions
        task.total_steps = len(actions)
        task.current_step = 0

        self._total_steps = len(actions)
        self._current_step = 0

        await self.report_progress(
            task, 5.0,
            f"Planned {len(actions)} actions"
        )

        # Execute first action
        return await self._execute_next_action(task)

    async def _handle_return(self, task: UserTask) -> Any:
        """Handle return from another agent."""
        returning_from = task.context.get("returning_from", "")
        task.context.pop("returning_from", None)

        logger.info(f"Orchestrator: Return from {returning_from}")

        # Check execution result
        if returning_from == "execution":
            exec_result = task.context.get("execution_result", {})
            if not exec_result.get("success", True):
                # Execution failed - escalate to recovery
                task.context["error"] = exec_result.get("error", "Execution failed")
                return await self.hand_off_to(
                    "recovery",
                    task,
                    reason="Execution failed"
                )

        # Check vision result
        elif returning_from == "vision":
            vision_result = task.context.get("vision_result", {})
            if not vision_result.get("found", False):
                # Element not found - try fallback or fail
                if task.context.get("vision_fallback"):
                    # Use fallback position
                    task.context["action"] = {
                        "type": "click",
                        "x": vision_result.get("x", 960),
                        "y": vision_result.get("y", 540)
                    }
                else:
                    logger.warning(f"Vision failed, no fallback")

        # Check recovery result
        elif returning_from == "recovery":
            recovery_result = task.context.get("recovery_result", {})
            if not recovery_result.get("recovered", False):
                return {
                    "success": False,
                    "error": "Recovery failed",
                    "details": recovery_result
                }

        # Continue with next action
        return await self._execute_next_action(task)

    async def _execute_next_action(self, task: UserTask) -> Any:
        """Execute the next pending action."""
        if not task.pending_actions:
            # Workflow complete!
            await self.report_progress(task, 100.0, "Workflow complete")
            return {
                "success": True,
                "completed_actions": task.completed_actions,
                "total_steps": task.total_steps
            }

        # Get next action
        action = task.pending_actions[0]
        task.pending_actions = task.pending_actions[1:]
        task.current_step += 1
        self._current_step = task.current_step

        # Calculate progress
        progress = (task.current_step / task.total_steps) * 100
        await self.report_progress(
            task, progress,
            f"Step {task.current_step}/{task.total_steps}: {action.get('description', action.get('type', 'unknown'))}"
        )

        # Determine agent based on action type
        action_type = action.get("type", "")

        if action_type == "find_and_click":
            # Vision agent finds element, then execution clicks
            task.context["find_target"] = action.get("target", "")
            task.context["return_mode"] = "execute_click"
            task.context["returning_from"] = None  # Clear for fresh handoff

            return await self.hand_off_to(
                "vision",
                task,
                reason=f"Find element: {action.get('target', '')}"
            )

        elif action_type in ("hotkey", "write", "press", "click", "scroll", "sleep", "moveTo"):
            # Direct execution
            task.context["action"] = action
            task.context["returning_from"] = None

            return await self.hand_off_to(
                "execution",
                task,
                reason=f"Execute: {action_type}"
            )

        else:
            logger.warning(f"Unknown action type: {action_type}")
            # Skip and continue
            return await self._execute_next_action(task)

    def _plan_claude_desktop_workflow(self, task: UserTask) -> List[Dict]:
        """
        Plan actions for Claude Desktop workflow.

        Simple approach: hotkey opens Claude Desktop with input already focused,
        so we just open, wait briefly, type, and send.
        """
        message = task.context.get("message", task.goal)

        # Check if user wants the complex flow with vision detection
        use_vision = task.context.get("use_vision_detection", False)

        if use_vision:
            # Complex flow with vision-based click
            return [
                {
                    "type": "hotkey",
                    "keys": ["ctrl", "alt", "space"],
                    "description": "Open Claude Desktop"
                },
                {
                    "type": "sleep",
                    "seconds": 2.0,
                    "description": "Wait for Claude Desktop"
                },
                {
                    "type": "find_and_click",
                    "target": "chat input field",
                    "description": "Click chat input"
                },
                {
                    "type": "sleep",
                    "seconds": 0.5,
                    "description": "Wait for focus"
                },
                {
                    "type": "write",
                    "text": message,
                    "description": "Type message"
                },
                {
                    "type": "press",
                    "key": "enter",
                    "description": "Send message"
                }
            ]

        # Simple flow - input is already focused when Claude Desktop opens
        return [
            {
                "type": "hotkey",
                "keys": ["ctrl", "alt", "space"],
                "description": "Open Claude Desktop"
            },
            {
                "type": "sleep",
                "seconds": 1.5,
                "description": "Wait for Claude Desktop"
            },
            {
                "type": "write",
                "text": message,
                "description": "Type message"
            },
            {
                "type": "press",
                "key": "enter",
                "description": "Send message"
            }
        ]

    def _plan_generic_workflow(self, task: UserTask) -> List[Dict]:
        """Plan actions for a generic task."""
        # For now, just extract actions from context
        actions = task.context.get("actions", [])

        if not actions:
            # Try to create basic actions from goal
            goal = task.goal.lower()

            if "open" in goal and "claude" in goal:
                return self._plan_claude_desktop_workflow(task)

            # Default: just report we don't know what to do
            logger.warning(f"No actions defined for goal: {task.goal}")

        return actions


class RecoveryAgent(BaseHandoffAgent):
    """
    Agent that handles error recovery.

    Attempts to recover from failures using strategies:
    - Retry: Same action again
    - Alternative: Different approach
    - Skip: Move to next action
    - Abort: Stop workflow
    """

    def __init__(self, max_retries: int = 2):
        config = AgentConfig(
            name="recovery",
            description="Handles error recovery and retries",
            topic_type="recovery"
        )
        super().__init__(config)
        self.max_retries = max_retries

    def _register_default_tools(self):
        """Register delegate tools."""
        self.register_delegate_tool(
            name="retry_with_execution",
            target_agent="execution",
            description="Retry action with execution agent"
        )

        self.register_delegate_tool(
            name="return_to_orchestrator",
            target_agent="orchestrator",
            description="Return to orchestrator"
        )

    async def _process_task(self, task: UserTask) -> Any:
        """Handle recovery."""
        error = task.context.get("error", "Unknown error")
        failed_action = task.context.get("failed_action", {})
        retry_count = task.context.get("retry_count", 0)

        await self.report_progress(
            task, 50.0,
            f"Recovery: {error[:30]}..."
        )

        # Check retry count
        if retry_count >= self.max_retries:
            # Max retries exceeded
            task.context["recovery_result"] = {
                "recovered": False,
                "reason": f"Max retries ({self.max_retries}) exceeded"
            }
            task.context["returning_from"] = "recovery"

            return await self.hand_off_to(
                "orchestrator",
                task,
                reason="Recovery failed - max retries"
            )

        # Attempt recovery
        task.context["retry_count"] = retry_count + 1

        # Strategy: Wait and retry
        await asyncio.sleep(1.0)

        task.context["action"] = failed_action
        task.context["recovery_result"] = {
            "recovered": True,
            "retry_count": retry_count + 1
        }
        task.context["returning_from"] = "recovery"

        return await self.hand_off_to(
            "execution",
            task,
            reason=f"Retry attempt {retry_count + 1}"
        )
