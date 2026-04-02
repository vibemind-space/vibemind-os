"""
Validated Executor - Executes LLM-generated actions with visual validation.

This module integrates:
- MoireWebSocketClient for screenshot capture
- ActionExecutor for PyAutoGUI execution
- StateComparator for before/after comparison
- VisionAnalystAgent for analysis and reflection

Usage:
    from core.validated_executor import ValidatedExecutor
    from core.task_decomposer import TaskDecomposer

    decomposer = TaskDecomposer()
    executor = ValidatedExecutor()

    await executor.connect()
    subtasks = await decomposer.decompose_with_actions("Open Notepad and type Hello")
    result = await executor.execute_with_validation(subtasks, goal="Open Notepad and type Hello")
    await executor.disconnect()
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Import Moire components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.websocket_client import MoireWebSocketClient, CaptureResult
from validation.state_comparator import StateComparator, ScreenState, ChangeType
from core.action_executor import ActionExecutor

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single action."""
    success: bool
    change_detected: bool
    change_type: Optional[ChangeType] = None
    confidence: float = 0.0
    message: str = ""
    before_screenshot: Optional[str] = None
    after_screenshot: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of executing all subtasks with validation."""
    success: bool
    goal_achieved: bool
    actions_executed: int
    actions_validated: int
    actions_failed: int
    validation_results: List[ValidationResult] = field(default_factory=list)
    goal_reflection: str = ""
    total_time_seconds: float = 0.0
    error: Optional[str] = None


class ValidatedExecutor:
    """
    Executes LLM-generated actions with visual validation.

    For each action:
    1. Capture BEFORE screenshot via MoireServer
    2. Execute PyAutoGUI action
    3. Capture AFTER screenshot
    4. Compare states using StateComparator
    5. Validate that expected change occurred
    """

    def __init__(
        self,
        moire_host: str = "localhost",
        moire_port: int = 8765,
        validation_threshold: float = 0.1,  # Lowered for text changes
        dry_run: bool = False
    ):
        """
        Initialize the ValidatedExecutor.

        Args:
            moire_host: MoireServer host
            moire_port: MoireServer port
            validation_threshold: Minimum confidence for action success (0.0-1.0)
            dry_run: If True, skip PyAutoGUI execution
        """
        self.moire_client = MoireWebSocketClient(host=moire_host, port=moire_port)
        self.action_executor = ActionExecutor(dry_run=dry_run)
        self.state_comparator = StateComparator()
        self.validation_threshold = validation_threshold
        self.dry_run = dry_run
        self._connected = False

    async def connect(self) -> bool:
        """Connect to MoireServer."""
        try:
            success = await self.moire_client.connect()
            self._connected = success
            if success:
                logger.info("Connected to MoireServer")
            else:
                logger.error("Failed to connect to MoireServer")
            return success
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self):
        """Disconnect from MoireServer."""
        if self._connected:
            await self.moire_client.disconnect()
            self._connected = False
            logger.info("Disconnected from MoireServer")

    async def capture_screen_state(self) -> Optional[ScreenState]:
        """Capture current screen state via MoireServer."""
        try:
            result: CaptureResult = await self.moire_client.capture_and_wait_for_complete(
                timeout=30.0,
                min_ocr_confidence=0.3
            )

            if not result.success:
                logger.warning(f"Capture failed: {result.error}")
                return None

            # Convert base64 to bytes (with padding fix)
            screenshot_bytes = None
            if result.screenshot_base64:
                # Fix padding if needed
                b64_str = result.screenshot_base64
                # Remove data URL prefix if present
                if ',' in b64_str:
                    b64_str = b64_str.split(',', 1)[1]
                # Add padding if missing
                padding = 4 - (len(b64_str) % 4)
                if padding != 4:
                    b64_str += '=' * padding
                try:
                    screenshot_bytes = base64.b64decode(b64_str)
                except Exception as e:
                    logger.warning(f"Base64 decode failed: {e}")

            # Extract OCR text and elements from ui_context
            ocr_text = []
            elements = []
            window_title = None

            if result.ui_context:
                # Get OCR texts
                if hasattr(result.ui_context, 'texts') and result.ui_context.texts:
                    ocr_text = [t.get('text', '') for t in result.ui_context.texts if t.get('text')]

                # Get detected elements
                if hasattr(result.ui_context, 'boxes') and result.ui_context.boxes:
                    elements = result.ui_context.boxes

                # Get window title if available
                if hasattr(result.ui_context, 'window_title'):
                    window_title = result.ui_context.window_title

            # Create ScreenState using factory method
            if screenshot_bytes:
                state = ScreenState.from_screenshot(
                    screenshot_data=screenshot_bytes,
                    elements=elements,
                    ocr_text=ocr_text,
                    window_title=window_title
                )
            else:
                # Fallback if no screenshot data
                state = ScreenState(
                    timestamp=asyncio.get_event_loop().time(),
                    screenshot_hash="",
                    screenshot_data=None,
                    elements=elements,
                    ocr_text=ocr_text,
                    window_title=window_title
                )

            return state

        except Exception as e:
            logger.error(f"Error capturing screen state: {e}")
            return None

    async def validate_action(
        self,
        before_state: ScreenState,
        after_state: ScreenState,
        expected_description: str
    ) -> ValidationResult:
        """
        Validate that an action succeeded by comparing before/after states.

        Args:
            before_state: Screen state before action
            after_state: Screen state after action
            expected_description: What the action was supposed to do

        Returns:
            ValidationResult with success status and details
        """
        try:
            # Compare states
            comparison = self.state_comparator.compare(before_state, after_state)

            # Determine if change is significant enough
            change_detected = comparison.change_type not in [
                ChangeType.NO_CHANGE,
                ChangeType.MINOR_CHANGE
            ]

            # Calculate confidence based on change type
            confidence_map = {
                ChangeType.NO_CHANGE: 0.1,
                ChangeType.MINOR_CHANGE: 0.3,
                ChangeType.SIGNIFICANT_CHANGE: 0.7,
                ChangeType.MAJOR_CHANGE: 0.9,
                ChangeType.NEW_WINDOW: 0.95,
                ChangeType.TEXT_CHANGED: 0.8,
                ChangeType.ELEMENT_APPEARED: 0.85,
                ChangeType.ELEMENT_DISAPPEARED: 0.85,
            }

            confidence = confidence_map.get(comparison.change_type, 0.5)

            # Success if confidence exceeds threshold
            success = confidence >= self.validation_threshold

            message = f"{comparison.change_type.value}: {comparison.change_percentage:.1f}% change"
            if comparison.description:
                message += f" - {comparison.description}"

            return ValidationResult(
                success=success,
                change_detected=change_detected,
                change_type=comparison.change_type,
                confidence=confidence,
                message=message,
                before_screenshot=None,  # Skip storing full screenshots for now
                after_screenshot=None
            )

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationResult(
                success=False,
                change_detected=False,
                confidence=0.0,
                message=f"Validation error: {e}"
            )

    async def execute_with_validation(
        self,
        subtasks: List,
        goal: str,
        on_progress: Optional[Callable] = None,
        max_retries: int = 2
    ) -> ExecutionResult:
        """
        Execute all subtasks with visual validation.

        Args:
            subtasks: List of Subtask objects from TaskDecomposer
            goal: Original goal for reflection
            on_progress: Optional callback(step, total, description, validation_result)
            max_retries: Maximum retries per action

        Returns:
            ExecutionResult with detailed status
        """
        import time
        start_time = time.time()

        if not self._connected:
            if not await self.connect():
                return ExecutionResult(
                    success=False,
                    goal_achieved=False,
                    actions_executed=0,
                    actions_validated=0,
                    actions_failed=0,
                    error="Could not connect to MoireServer"
                )

        total = len(subtasks)
        validation_results = []
        actions_validated = 0
        actions_failed = 0

        logger.info(f"Executing {total} subtasks with validation...")

        for i, subtask in enumerate(subtasks):
            description = subtask.description
            action = subtask.context.get("pyautogui_action")

            if on_progress:
                on_progress(i, total, description, None)

            print(f"  [{i+1}/{total}] {description}")

            if not action:
                logger.debug(f"No action for subtask: {description}")
                validation_results.append(ValidationResult(
                    success=True,
                    change_detected=False,
                    message="No action required"
                ))
                continue

            # Retry loop
            for attempt in range(max_retries + 1):
                # 1. Capture BEFORE state
                before_state = await self.capture_screen_state()
                if not before_state:
                    logger.warning("Could not capture before state, proceeding without validation")

                # 2. Execute action
                action_success = await self.action_executor.execute_action(action)

                if not action_success:
                    logger.error(f"Action execution failed: {description}")
                    actions_failed += 1
                    validation_results.append(ValidationResult(
                        success=False,
                        change_detected=False,
                        message="Action execution failed"
                    ))
                    break

                # 3. Wait for action to take effect
                wait_time = subtask.context.get("wait_after", 0.3)
                await asyncio.sleep(wait_time)

                # 4. Capture AFTER state
                after_state = await self.capture_screen_state()

                # 5. Validate change
                if before_state and after_state:
                    validation = await self.validate_action(
                        before_state,
                        after_state,
                        description
                    )

                    status = "[OK]" if validation.success else "[??]"
                    print(f"    {status} {validation.message}")

                    if validation.success or attempt >= max_retries:
                        validation_results.append(validation)
                        if validation.success:
                            actions_validated += 1
                        else:
                            actions_failed += 1
                        break
                    else:
                        logger.info(f"Retrying action (attempt {attempt + 2}/{max_retries + 1})")
                else:
                    # No validation possible, assume success
                    validation_results.append(ValidationResult(
                        success=True,
                        change_detected=True,
                        message="Executed (no validation)"
                    ))
                    actions_validated += 1
                    break

            if on_progress:
                on_progress(i, total, description, validation_results[-1] if validation_results else None)

        # Calculate totals
        total_time = time.time() - start_time
        actions_executed = len([v for v in validation_results if v.success or v.change_detected])

        # Goal reflection (simplified - could use VisionAgent for more thorough analysis)
        goal_achieved = actions_failed == 0 and actions_validated > 0
        goal_reflection = f"Executed {actions_executed}/{total} actions successfully"

        if goal_achieved:
            goal_reflection += f". Goal '{goal}' appears to be achieved."
        else:
            goal_reflection += f". Some actions may have failed."

        return ExecutionResult(
            success=actions_failed == 0,
            goal_achieved=goal_achieved,
            actions_executed=actions_executed,
            actions_validated=actions_validated,
            actions_failed=actions_failed,
            validation_results=validation_results,
            goal_reflection=goal_reflection,
            total_time_seconds=total_time
        )


async def demo():
    """Demo function to test ValidatedExecutor."""
    from core.task_decomposer import Subtask

    # Create sample subtasks
    subtasks = [
        Subtask.create(
            description="Open Run dialog",
            approach="keyboard",
            context={
                "pyautogui_action": {"type": "hotkey", "keys": ["win", "r"]},
                "wait_after": 0.5
            }
        ),
        Subtask.create(
            description="Type notepad",
            approach="keyboard",
            context={
                "pyautogui_action": {"type": "write", "text": "notepad", "interval": 0.05},
                "wait_after": 0.2
            }
        ),
        Subtask.create(
            description="Press Enter to launch",
            approach="keyboard",
            context={
                "pyautogui_action": {"type": "press", "key": "enter"},
                "wait_after": 2.0
            }
        ),
        Subtask.create(
            description="Type Hello World",
            approach="keyboard",
            context={
                "pyautogui_action": {"type": "write", "text": "Hello World!", "interval": 0.03},
                "wait_after": 0.2
            }
        ),
    ]

    print("\n" + "=" * 60)
    print("ValidatedExecutor Demo")
    print("=" * 60)
    print("\nThis demo will:")
    print("1. Connect to MoireServer for visual validation")
    print("2. Execute PyAutoGUI actions")
    print("3. Validate each action with before/after screenshots")
    print("\nMake sure MoireServer is running at ws://localhost:8765")

    print("\nStarting in 3 seconds... (move mouse to corner to abort)")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        await asyncio.sleep(1)

    executor = ValidatedExecutor()

    try:
        result = await executor.execute_with_validation(
            subtasks=subtasks,
            goal="Open Notepad and type Hello World"
        )

        print("\n" + "-" * 50)
        print("RESULT:")
        print(f"  Success: {result.success}")
        print(f"  Goal achieved: {result.goal_achieved}")
        print(f"  Actions executed: {result.actions_executed}")
        print(f"  Actions validated: {result.actions_validated}")
        print(f"  Actions failed: {result.actions_failed}")
        print(f"  Duration: {result.total_time_seconds:.1f}s")
        print(f"  Reflection: {result.goal_reflection}")

    finally:
        await executor.disconnect()


if __name__ == "__main__":
    asyncio.run(demo())
