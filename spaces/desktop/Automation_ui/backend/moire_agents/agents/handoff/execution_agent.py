"""
Execution Agent - Handles keyboard and mouse actions

Concrete agent that executes pyautogui actions without visual validation.
Part of the handoff pattern multi-agent system.
"""

import asyncio
import logging
import pyautogui
import pyperclip
from typing import Any, Dict, Optional

from .base_agent import BaseHandoffAgent, AgentConfig, Tool
from .messages import UserTask, HandoffRequest
from .tools import transfer_to_orchestrator, transfer_to_recovery

logger = logging.getLogger(__name__)

# PyAutoGUI safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


class ExecutionAgent(BaseHandoffAgent):
    """
    Agent that executes keyboard and mouse actions.

    Handles action types:
    - hotkey: Keyboard combinations (ctrl+c, alt+tab, etc.)
    - write: Type text
    - press: Single key press
    - click: Mouse click at coordinates
    - scroll: Mouse scroll
    - sleep: Wait for duration

    Returns control to orchestrator after execution.
    """

    def __init__(self, use_clipboard_for_text: bool = True):
        """
        Initialize the execution agent.

        Args:
            use_clipboard_for_text: Use clipboard paste instead of typing
                                   (more reliable for some apps)
        """
        config = AgentConfig(
            name="execution",
            description="Executes keyboard and mouse actions via pyautogui",
            topic_type="execution"
        )
        super().__init__(config)

        self.use_clipboard_for_text = use_clipboard_for_text

    def _register_default_tools(self):
        """Register delegate tools for this agent."""
        # Return to orchestrator after execution
        self.register_delegate_tool(
            name="return_to_orchestrator",
            target_agent="orchestrator",
            description="Return control to orchestrator after action completion"
        )

        # Escalate to recovery on failure
        self.register_delegate_tool(
            name="escalate_to_recovery",
            target_agent="recovery",
            description="Escalate to recovery agent on failure"
        )

    async def _process_task(self, task: UserTask) -> Any:
        """
        Process an execution task.

        Expected context:
        - action: Dict with 'type' and action-specific params
        - return_to_orchestrator: bool - whether to return after (default True)

        NOTE: This agent executes ONE action and returns to orchestrator.
        The orchestrator manages the workflow and decides what to do next.
        """
        action = task.context.get("action", {})
        if not action:
            return {"success": False, "error": "No action specified in context"}

        action_type = action.get("type", "")

        await self.report_progress(
            task, 50.0,
            f"Executing: {action_type}"
        )

        try:
            result = await self._execute_action(action)

            # Add to completed actions
            task.completed_actions.append({
                **action,
                "result": result
            })

            await self.report_progress(task, 100.0, "Execution complete")

            # Always return to orchestrator - let it decide what's next
            task.context["execution_result"] = result
            task.context["returning_from"] = "execution"
            return await self.hand_off_to(
                "orchestrator",
                task,
                reason="Execution complete"
            )

        except Exception as e:
            logger.error(f"Execution error: {e}")

            # Escalate to recovery
            task.context["error"] = str(e)
            task.context["failed_action"] = action
            task.context["returning_from"] = "execution"
            return await self.hand_off_to(
                "recovery",
                task,
                reason=f"Execution failed: {e}"
            )

    async def _execute_action(self, action: Dict) -> Dict[str, Any]:
        """Execute a single pyautogui action."""
        action_type = action.get("type", "")

        if action_type == "hotkey":
            return await self._execute_hotkey(action)
        elif action_type == "write":
            return await self._execute_write(action)
        elif action_type == "press":
            return await self._execute_press(action)
        elif action_type == "click":
            return await self._execute_click(action)
        elif action_type == "scroll":
            return await self._execute_scroll(action)
        elif action_type == "sleep":
            return await self._execute_sleep(action)
        elif action_type == "moveTo":
            return await self._execute_move_to(action)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def _execute_hotkey(self, action: Dict) -> Dict[str, Any]:
        """Execute a hotkey combination."""
        keys = action.get("keys", [])
        if not keys:
            raise ValueError("Hotkey requires 'keys' list")

        logger.info(f"Hotkey: {'+'.join(keys)}")
        pyautogui.hotkey(*keys)

        return {"action": "hotkey", "keys": keys, "success": True}

    async def _execute_write(self, action: Dict) -> Dict[str, Any]:
        """Type text."""
        text = action.get("text", "")
        if not text:
            raise ValueError("Write requires 'text'")

        interval = action.get("interval", 0.02)

        logger.info(f"Writing: {text[:30]}{'...' if len(text) > 30 else ''}")

        if self.use_clipboard_for_text:
            # Use clipboard for more reliable text entry
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            await asyncio.sleep(0.1)
        else:
            pyautogui.write(text, interval=interval)

        return {"action": "write", "chars": len(text), "success": True}

    async def _execute_press(self, action: Dict) -> Dict[str, Any]:
        """Press a single key."""
        key = action.get("key", "")
        if not key:
            raise ValueError("Press requires 'key'")

        presses = action.get("presses", 1)

        logger.info(f"Pressing: {key} x{presses}")
        pyautogui.press(key, presses=presses)

        return {"action": "press", "key": key, "presses": presses, "success": True}

    async def _execute_click(self, action: Dict) -> Dict[str, Any]:
        """Click at coordinates."""
        x = action.get("x")
        y = action.get("y")
        button = action.get("button", "left")
        clicks = action.get("clicks", 1)

        if x is not None and y is not None:
            logger.info(f"Clicking: ({x}, {y}) {button} x{clicks}")
            pyautogui.click(x, y, clicks=clicks, button=button)
        else:
            logger.info(f"Clicking: current position {button} x{clicks}")
            pyautogui.click(clicks=clicks, button=button)

        return {"action": "click", "x": x, "y": y, "success": True}

    async def _execute_scroll(self, action: Dict) -> Dict[str, Any]:
        """Scroll the mouse."""
        clicks = action.get("clicks", 3)
        x = action.get("x")
        y = action.get("y")

        logger.info(f"Scrolling: {clicks} clicks")
        pyautogui.scroll(clicks, x, y)

        return {"action": "scroll", "clicks": clicks, "success": True}

    async def _execute_sleep(self, action: Dict) -> Dict[str, Any]:
        """Wait for a duration."""
        seconds = action.get("seconds", 1.0)

        logger.info(f"Sleeping: {seconds}s")
        await asyncio.sleep(seconds)

        return {"action": "sleep", "seconds": seconds, "success": True}

    async def _execute_move_to(self, action: Dict) -> Dict[str, Any]:
        """Move mouse to position."""
        x = action.get("x")
        y = action.get("y")
        duration = action.get("duration", 0.25)

        if x is None or y is None:
            raise ValueError("moveTo requires 'x' and 'y'")

        logger.info(f"Moving to: ({x}, {y})")
        pyautogui.moveTo(x, y, duration=duration)

        return {"action": "moveTo", "x": x, "y": y, "success": True}
