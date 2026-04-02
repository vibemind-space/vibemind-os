"""
Steering Agent - Central coordinator with handoff pattern.

Inspired by AutoGen's handoff pattern, this agent:
1. Monitors ALL action executions
2. Categorizes actions (safe vs visual-dependent)
3. Routes to appropriate specialist agents
4. Handles failures with recovery handoffs

Usage:
    from agents.steering_agent import SteeringAgent

    agent = SteeringAgent()
    await agent.connect()
    result = await agent.execute_with_steering(subtasks, goal="Open Notepad")
    await agent.disconnect()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.action_executor import ActionExecutor
from validation.change_detector import ChangeDetector, ChangeRegion, ChangeDetectionResult
from bridge.websocket_client import MoireWebSocketClient

logger = logging.getLogger(__name__)


class ActionCategory(Enum):
    """Category of action for routing."""
    SAFE = "safe"                    # Keyboard actions - no visual validation needed
    VISUAL_DEPENDENT = "visual"      # Click/scroll - requires visual validation
    FIND_DEPENDENT = "find"          # Find element then click - requires OCR/vision search
    WAIT = "wait"                    # Sleep/wait - just timing
    UNKNOWN = "unknown"


class RecoveryStrategy(Enum):
    """Strategy for recovering from failures."""
    RETRY_SAME = "retry_same"           # Same action, different timing
    RETRY_ALTERNATIVE = "retry_alt"     # Different approach
    SKIP_AND_CONTINUE = "skip"          # Non-critical, move on
    ABORT_AND_REPORT = "abort"          # Critical failure, stop
    REPLAN = "replan"                   # Generate new plan from current state


@dataclass
class TaskMessage:
    """Message passed between agents via handoff."""
    task_id: str
    conversation_history: List[Dict] = field(default_factory=list)
    current_action: Optional[Dict] = None
    screen_state: Optional[Any] = None
    goal: str = ""
    attempt: int = 1
    subtask_index: int = 0
    total_subtasks: int = 0


@dataclass
class HandoffResult:
    """Result returned after agent completes task."""
    success: bool
    next_agent: Optional[str] = None  # Handoff target or None if done
    updated_plan: Optional[List] = None  # If plan was modified
    change_regions: List[ChangeRegion] = field(default_factory=list)
    annotated_screenshot: Optional[bytes] = None
    message: str = ""
    confidence: float = 0.0


@dataclass
class SteeringResult:
    """Final result from steering agent execution."""
    success: bool
    goal_achieved: bool
    actions_executed: int
    actions_validated: int
    actions_failed: int
    change_regions: List[Dict] = field(default_factory=list)  # All detected changes
    recovery_attempts: int = 0
    total_time_seconds: float = 0.0
    summary: str = ""


class SteeringAgent:
    """
    Central coordinator that monitors execution and handles handoffs.

    Routes actions to:
    - ExecutionAgent: For safe keyboard actions
    - ValidationAgent: For visual-dependent actions
    - RecoveryAgent: When actions fail
    """

    # Action type categorization
    SAFE_ACTIONS = {"hotkey", "press", "write", "sleep"}
    VISUAL_ACTIONS = {"click", "scroll", "drag", "moveTo"}
    FIND_ACTIONS = {"find_and_click", "find_element"}
    WAIT_ACTIONS = {"sleep"}

    def __init__(
        self,
        moire_host: str = "localhost",
        moire_port: int = 8765,
        validation_threshold: float = 0.3,
        max_retries: int = 2
    ):
        """
        Initialize the SteeringAgent.

        Args:
            moire_host: MoireServer host
            moire_port: MoireServer port
            validation_threshold: Confidence threshold for action success
            max_retries: Maximum retry attempts per action
        """
        self.moire_client = MoireWebSocketClient(host=moire_host, port=moire_port)
        self.action_executor = ActionExecutor()
        self.change_detector = ChangeDetector()
        self.validation_threshold = validation_threshold
        self.max_retries = max_retries
        self._connected = False

        # Statistics
        self._stats = {
            "safe_actions": 0,
            "visual_actions": 0,
            "recoveries": 0,
            "total_regions": 0
        }

    async def connect(self) -> bool:
        """Connect to MoireServer for visual validation."""
        try:
            success = await self.moire_client.connect()
            self._connected = success
            if success:
                logger.info("SteeringAgent connected to MoireServer")
            return success
        except Exception as e:
            logger.error(f"SteeringAgent connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from MoireServer."""
        if self._connected:
            await self.moire_client.disconnect()
            self._connected = False
            logger.info("SteeringAgent disconnected")

    def classify_action(self, action: Dict) -> ActionCategory:
        """
        Categorize action for routing.

        Args:
            action: PyAutoGUI action dictionary

        Returns:
            ActionCategory indicating how to handle this action
        """
        if not action:
            return ActionCategory.UNKNOWN

        action_type = action.get("type", "")

        if action_type in self.WAIT_ACTIONS:
            return ActionCategory.WAIT
        elif action_type in self.SAFE_ACTIONS:
            return ActionCategory.SAFE
        elif action_type in self.FIND_ACTIONS:
            return ActionCategory.FIND_DEPENDENT
        elif action_type in self.VISUAL_ACTIONS:
            return ActionCategory.VISUAL_DEPENDENT
        else:
            return ActionCategory.UNKNOWN

    async def execute_with_steering(
        self,
        subtasks: List,
        goal: str,
        on_progress: Optional[Callable] = None
    ) -> SteeringResult:
        """
        Main execution loop with steering and handoffs.

        For each action:
        1. Classify action (safe vs visual-dependent)
        2. Route to appropriate handler
        3. If visual: capture before, execute, capture after, validate
        4. If failed: attempt recovery
        5. Track all change regions for feedback

        Args:
            subtasks: List of Subtask objects from TaskDecomposer
            goal: Original goal for context
            on_progress: Optional callback(step, total, message, regions)

        Returns:
            SteeringResult with execution summary and visual feedback
        """
        import time
        start_time = time.time()

        total = len(subtasks)
        executed = 0
        validated = 0
        failed = 0
        all_regions = []
        recovery_count = 0

        logger.info(f"SteeringAgent executing {total} subtasks for goal: {goal}")

        for i, subtask in enumerate(subtasks):
            description = subtask.description
            action = subtask.context.get("pyautogui_action")

            # Create task message for handoffs
            task = TaskMessage(
                task_id=f"task_{i}",
                current_action=action,
                goal=goal,
                subtask_index=i,
                total_subtasks=total
            )

            # Progress callback
            if on_progress:
                on_progress(i, total, f"Step {i+1}/{total}: {description}", [])

            print(f"\n  [{i+1}/{total}] {description}")

            if not action:
                print(f"    [SKIP] No action defined")
                continue

            # Classify and route
            category = self.classify_action(action)
            category_str = category.value.upper()
            print(f"    [CATEGORY] {category_str}")

            # Handle based on category
            result = await self._route_action(task, category, subtask)

            if result.success:
                executed += 1
                if result.change_regions:
                    validated += 1
                    all_regions.extend([r.to_dict() for r in result.change_regions])
                    self._stats["total_regions"] += len(result.change_regions)

                status = "[OK]"
                if result.change_regions:
                    regions_str = f" ({len(result.change_regions)} change regions)"
                else:
                    regions_str = ""
                print(f"    {status} {result.message}{regions_str}")

                # Show change regions
                for region in result.change_regions:
                    print(f"      Region {region.id}: {region.bounds} - {region.intensity.value}")

            else:
                # Attempt recovery
                recovery_result = await self._handle_failure(task, result)
                recovery_count += 1

                if recovery_result.success:
                    executed += 1
                    print(f"    [RECOVERED] {recovery_result.message}")
                else:
                    failed += 1
                    print(f"    [FAILED] {result.message}")

            # Wait after action
            wait_time = subtask.context.get("wait_after", 0.2)
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        # Calculate result
        total_time = time.time() - start_time
        success = failed == 0
        goal_achieved = executed > 0 and failed == 0

        summary = f"Executed {executed}/{total} actions"
        if validated > 0:
            summary += f", validated {validated} with visual feedback"
        if recovery_count > 0:
            summary += f", {recovery_count} recovery attempts"

        return SteeringResult(
            success=success,
            goal_achieved=goal_achieved,
            actions_executed=executed,
            actions_validated=validated,
            actions_failed=failed,
            change_regions=all_regions,
            recovery_attempts=recovery_count,
            total_time_seconds=total_time,
            summary=summary
        )

    async def _route_action(
        self,
        task: TaskMessage,
        category: ActionCategory,
        subtask
    ) -> HandoffResult:
        """
        Route action to appropriate handler based on category.

        Args:
            task: TaskMessage with context
            category: ActionCategory for routing
            subtask: Original subtask object

        Returns:
            HandoffResult from the handler
        """
        action = task.current_action

        if category == ActionCategory.SAFE:
            # Safe actions - execute directly, no validation needed
            self._stats["safe_actions"] += 1
            return await self._execute_safe(action)

        elif category == ActionCategory.FIND_DEPENDENT:
            # Find actions - search for element then click
            self._stats["visual_actions"] += 1
            return await self._execute_find_and_click(action)

        elif category == ActionCategory.VISUAL_DEPENDENT:
            # Visual actions - capture before/after, validate with change detection
            self._stats["visual_actions"] += 1
            return await self._execute_with_validation(action)

        elif category == ActionCategory.WAIT:
            # Wait actions - just execute
            return await self._execute_safe(action)

        else:
            # Unknown - try as safe action
            logger.warning(f"Unknown action type, treating as safe: {action}")
            return await self._execute_safe(action)

    async def _execute_safe(self, action: Dict) -> HandoffResult:
        """
        Execute a safe action (keyboard) without visual validation.

        Args:
            action: PyAutoGUI action dictionary

        Returns:
            HandoffResult with success status
        """
        try:
            success = await self.action_executor.execute_action(action)
            return HandoffResult(
                success=success,
                message="Action executed" if success else "Execution failed",
                confidence=1.0 if success else 0.0
            )
        except Exception as e:
            logger.error(f"Safe action failed: {e}")
            return HandoffResult(
                success=False,
                message=f"Error: {e}",
                confidence=0.0
            )

    async def _execute_with_validation(self, action: Dict) -> HandoffResult:
        """
        Execute a visual-dependent action with before/after validation.

        1. Capture BEFORE screenshot
        2. Execute action
        3. Capture AFTER screenshot
        4. Detect change regions
        5. Validate based on detected changes

        Args:
            action: PyAutoGUI action dictionary

        Returns:
            HandoffResult with change regions and validation status
        """
        before_screenshot = None
        after_screenshot = None

        try:
            # 1. Capture BEFORE
            if self._connected:
                before_result = await self.moire_client.capture_and_wait_for_complete(timeout=10.0)
                if before_result.success and before_result.screenshot_base64:
                    import base64
                    before_screenshot = base64.b64decode(before_result.screenshot_base64)

            # 2. Execute action
            success = await self.action_executor.execute_action(action)

            if not success:
                return HandoffResult(
                    success=False,
                    message="Action execution failed",
                    confidence=0.0
                )

            # 3. Wait for UI to update
            await asyncio.sleep(0.3)

            # 4. Capture AFTER
            if self._connected:
                after_result = await self.moire_client.capture_and_wait_for_complete(timeout=10.0)
                if after_result.success and after_result.screenshot_base64:
                    import base64
                    after_screenshot = base64.b64decode(after_result.screenshot_base64)

            # 5. Detect changes
            if before_screenshot and after_screenshot:
                detection = self.change_detector.detect_changes(
                    before_screenshot,
                    after_screenshot,
                    return_diff_image=False
                )

                # Validate based on changes
                if detection.changed and detection.regions:
                    # Generate annotated screenshot
                    annotated = self.change_detector.annotate_screenshot(
                        after_screenshot,
                        detection.regions,
                        style="boxes"
                    )

                    # Calculate confidence based on change intensity
                    high_count = sum(1 for r in detection.regions if r.intensity.value == "high")
                    confidence = min(1.0, 0.5 + (high_count * 0.2) + (len(detection.regions) * 0.1))

                    return HandoffResult(
                        success=True,
                        change_regions=detection.regions,
                        annotated_screenshot=annotated,
                        message=f"Validated with {len(detection.regions)} change regions ({detection.total_change_percentage:.1f}% total)",
                        confidence=confidence
                    )
                else:
                    # No change detected - action may have failed
                    return HandoffResult(
                        success=False,
                        message="No visual change detected",
                        confidence=0.2
                    )
            else:
                # No screenshots - fall back to execution-only success
                return HandoffResult(
                    success=True,
                    message="Executed (no visual validation)",
                    confidence=0.5
                )

        except Exception as e:
            logger.error(f"Visual validation failed: {e}")
            return HandoffResult(
                success=False,
                message=f"Validation error: {e}",
                confidence=0.0
            )

    async def _execute_find_and_click(self, action: Dict) -> HandoffResult:
        """
        Find element by text/description, then click on it.

        1. Capture screen with OCR via MoireServer
        2. Try OCR-based text search first
        3. If OCR fails, fall back to vision-based search
        4. Execute click at found coordinates
        5. Validate with change detection

        Args:
            action: Action dictionary with 'target' field

        Returns:
            HandoffResult with success status and change regions
        """
        import base64
        import pyautogui

        target = action.get("target", "")
        if not target:
            return HandoffResult(
                success=False,
                message="No target specified for find_and_click",
                confidence=0.0
            )

        logger.info(f"Finding element: '{target}'")

        try:
            # 1. Capture screen with OCR
            if not self._connected:
                return HandoffResult(
                    success=False,
                    message="Not connected to MoireServer for visual search",
                    confidence=0.0
                )

            result = await self.moire_client.capture_and_wait_for_complete(timeout=15.0)

            if not result.success:
                return HandoffResult(
                    success=False,
                    message=f"Screen capture failed: {result.message}",
                    confidence=0.0
                )

            # 2. Try OCR-based text search first
            element = self.moire_client.find_element_by_text(target, exact=False)

            if element:
                x = element.center.get("x", 0)
                y = element.center.get("y", 0)
                logger.info(f"Found '{target}' via OCR at ({x}, {y})")
            else:
                # 3. Fall back to vision-based search
                logger.info(f"OCR failed, trying vision-based search for '{target}'")

                # Try to import vision agent
                try:
                    from agents.vision_agent import VisionAnalystAgent

                    # Helper to decode base64 with data URI handling
                    def decode_b64_vision(data):
                        if not data:
                            return None
                        if ',' in data:
                            data = data.split(',', 1)[1]
                        missing = len(data) % 4
                        if missing:
                            data += '=' * (4 - missing)
                        return base64.b64decode(data)

                    vision_agent = VisionAnalystAgent()
                    if result.screenshot_base64:
                        screenshot_bytes = decode_b64_vision(result.screenshot_base64)
                        location = await vision_agent.find_element_from_screenshot(
                            screenshot_bytes,
                            target
                        )

                        if location.found:
                            x = location.x
                            y = location.y
                            logger.info(f"Found '{target}' via Vision at ({x}, {y})")
                        else:
                            return HandoffResult(
                                success=False,
                                message=f"Could not find element: {target}",
                                confidence=0.0
                            )
                    else:
                        return HandoffResult(
                            success=False,
                            message="No screenshot available for vision search",
                            confidence=0.0
                        )
                except ImportError:
                    return HandoffResult(
                        success=False,
                        message=f"Could not find '{target}' (vision agent not available)",
                        confidence=0.0
                    )

            # Helper to decode base64 with data URI handling
            def decode_b64(data):
                if not data:
                    return None
                if ',' in data:
                    data = data.split(',', 1)[1]
                missing = len(data) % 4
                if missing:
                    data += '=' * (4 - missing)
                return base64.b64decode(data)

            # Capture BEFORE screenshot for validation
            before_screenshot = decode_b64(result.screenshot_base64)

            # 4. Execute click at found coordinates
            logger.info(f"Clicking at ({x}, {y})")
            pyautogui.click(x, y)

            # Wait for UI update
            await asyncio.sleep(0.3)

            # 5. Capture AFTER and validate with change detection
            after_result = await self.moire_client.capture_and_wait_for_complete(timeout=10.0)
            after_screenshot = None
            if after_result.success and after_result.screenshot_base64:
                after_screenshot = decode_b64(after_result.screenshot_base64)

            if before_screenshot and after_screenshot:
                detection = self.change_detector.detect_changes(
                    before_screenshot,
                    after_screenshot,
                    return_diff_image=False
                )

                if detection.changed and detection.regions:
                    annotated = self.change_detector.annotate_screenshot(
                        after_screenshot,
                        detection.regions,
                        style="boxes"
                    )

                    return HandoffResult(
                        success=True,
                        change_regions=detection.regions,
                        annotated_screenshot=annotated,
                        message=f"Found and clicked '{target}' - {len(detection.regions)} regions changed",
                        confidence=0.9
                    )
                else:
                    # Click executed but no change detected - might still be successful
                    return HandoffResult(
                        success=True,
                        message=f"Clicked '{target}' but no visual change detected",
                        confidence=0.6
                    )
            else:
                return HandoffResult(
                    success=True,
                    message=f"Clicked '{target}' (no visual validation)",
                    confidence=0.5
                )

        except Exception as e:
            logger.error(f"Find and click failed: {e}")
            return HandoffResult(
                success=False,
                message=f"Error: {e}",
                confidence=0.0
            )

    async def _handle_failure(
        self,
        task: TaskMessage,
        failed_result: HandoffResult
    ) -> HandoffResult:
        """
        Handle action failure with recovery strategies.

        Strategies:
        1. RETRY_SAME: Same action, different timing
        2. RETRY_ALTERNATIVE: Different approach
        3. SKIP_AND_CONTINUE: Non-critical action
        4. ABORT_AND_REPORT: Critical failure

        Args:
            task: TaskMessage with context
            failed_result: The failed HandoffResult

        Returns:
            HandoffResult after recovery attempt
        """
        self._stats["recoveries"] += 1
        action = task.current_action
        attempt = task.attempt

        logger.info(f"Recovery attempt {attempt} for action: {action}")

        # Simple retry strategy for now
        if attempt < self.max_retries:
            task.attempt += 1

            # Wait a bit before retry
            await asyncio.sleep(0.5)

            # Retry the action
            category = self.classify_action(action)

            if category == ActionCategory.FIND_DEPENDENT:
                return await self._execute_find_and_click(action)
            elif category == ActionCategory.VISUAL_DEPENDENT:
                return await self._execute_with_validation(action)
            else:
                return await self._execute_safe(action)

        else:
            # Max retries exceeded
            return HandoffResult(
                success=False,
                message=f"Failed after {attempt} attempts: {failed_result.message}",
                confidence=0.0
            )

    def get_stats(self) -> Dict[str, int]:
        """Get execution statistics."""
        return self._stats.copy()


async def demo():
    """Demo the SteeringAgent with a simple task."""
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
                "pyautogui_action": {"type": "write", "text": "Hello from SteeringAgent!", "interval": 0.03},
                "wait_after": 0.2
            }
        ),
    ]

    print("\n" + "=" * 60)
    print("SteeringAgent Demo")
    print("=" * 60)
    print("\nThis demo will execute actions with visual validation.")
    print("Make sure MoireServer is running at ws://localhost:8765")

    print("\nStarting in 3 seconds... (move mouse to corner to abort)")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        await asyncio.sleep(1)

    agent = SteeringAgent()

    try:
        # Connect to MoireServer
        connected = await agent.connect()
        if not connected:
            print("\n[WARNING] Could not connect to MoireServer - running without validation")

        # Execute with steering
        result = await agent.execute_with_steering(
            subtasks=subtasks,
            goal="Open Notepad and type Hello World"
        )

        # Show results
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"  Success: {result.success}")
        print(f"  Goal achieved: {result.goal_achieved}")
        print(f"  Actions executed: {result.actions_executed}")
        print(f"  Actions validated: {result.actions_validated}")
        print(f"  Actions failed: {result.actions_failed}")
        print(f"  Recovery attempts: {result.recovery_attempts}")
        print(f"  Total change regions: {len(result.change_regions)}")
        print(f"  Duration: {result.total_time_seconds:.1f}s")
        print(f"\n  Summary: {result.summary}")

        # Show stats
        stats = agent.get_stats()
        print(f"\n  Stats: {stats}")

    finally:
        await agent.disconnect()


if __name__ == "__main__":
    asyncio.run(demo())
