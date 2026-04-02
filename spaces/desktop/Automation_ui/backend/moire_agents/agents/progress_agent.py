"""
Progress Agent - Async State Monitoring & Incremental Plan Updates

Monitors task execution continuously, analyzes current state vs goal,
and UPDATES the action plan incrementally rather than rebuilding from scratch.

Key Features:
- Runs as background asyncio task
- Maintains rolling state history
- Updates actions in-place (modify/insert/skip/retry)
- Detects blockers and suggests corrections
- Early goal detection
"""

import asyncio
import logging
import time
import base64
from typing import Optional, Dict, Any, List, Literal, Callable
from dataclasses import dataclass, field
from enum import Enum

# Local imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_queue import ActionEvent, ActionStatus

# Optional imports
try:
    from bridge.websocket_client import MoireWebSocketClient
    HAS_MOIRE = True
except ImportError:
    HAS_MOIRE = False
    MoireWebSocketClient = None

try:
    from validation.change_detector import ChangeDetector, ChangeDetectionResult
    HAS_CHANGE_DETECTOR = True
except ImportError:
    HAS_CHANGE_DETECTOR = False
    ChangeDetector = None

try:
    from agents.vision_agent import VisionAnalystAgent, get_vision_agent
    HAS_VISION = True
except ImportError:
    HAS_VISION = False
    VisionAnalystAgent = None

try:
    from core.localization import L
    HAS_LOCALIZATION = True
except ImportError:
    HAS_LOCALIZATION = False
    L = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ScreenState:
    """Captured screen state at a point in time."""
    screenshot: bytes
    ocr_texts: List[str]
    timestamp: float
    elements: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskProgress:
    """Progress tracking for a task."""
    task_id: str
    goal: str
    total_actions: int
    completed_actions: int = 0
    current_action_index: int = 0
    progress_percentage: float = 0.0
    state_history: List[ScreenState] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    last_successful_state: Optional[ScreenState] = None
    goal_achieved: bool = False
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    actions: List[ActionEvent] = field(default_factory=list)
    inserted_actions: Dict[int, List[ActionEvent]] = field(default_factory=dict)


@dataclass
class ActionAdjustment:
    """Suggested adjustment to the action plan."""
    type: Literal["modify", "insert", "skip", "retry"]
    action_index: int
    new_params: Optional[Dict[str, Any]] = None
    new_action: Optional[ActionEvent] = None
    reason: str = ""


@dataclass
class ProgressAnalysis:
    """Result of analyzing progress after an action."""
    action_succeeded: bool
    expected_vs_actual: str
    progress_delta: float  # -1.0 to 1.0 (negative = regression)
    suggested_adjustment: Optional[ActionAdjustment] = None
    goal_achieved: bool = False
    confidence: float = 0.0
    change_regions: List[Dict[str, Any]] = field(default_factory=list)


class ProgressAgent:
    """
    Async agent that monitors task execution and updates plans incrementally.

    Instead of rebuilding the entire plan on issues, this agent:
    - Monitors state changes continuously
    - Analyzes if actions achieved expected outcomes
    - Modifies, inserts, skips, or retries individual actions
    - Tracks progress percentage and blockers
    """

    def __init__(
        self,
        moire_client: Optional[MoireWebSocketClient] = None,
        vision_agent: Optional[VisionAnalystAgent] = None,
        change_detector: Optional[ChangeDetector] = None,
        capture_interval: float = 0.5,
        max_state_history: int = 10
    ):
        self.moire_client = moire_client
        self.vision_agent = vision_agent or (get_vision_agent() if HAS_VISION else None)
        self.change_detector = change_detector or (ChangeDetector() if HAS_CHANGE_DETECTOR else None)

        self.capture_interval = capture_interval
        self.max_state_history = max_state_history

        self.current_progress: Optional[TaskProgress] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._action_just_completed: bool = False
        self._last_completed_index: int = -1

        # Callbacks
        self.on_progress_update: Optional[Callable[[TaskProgress], None]] = None
        self.on_adjustment: Optional[Callable[[ActionAdjustment], None]] = None
        self.on_goal_achieved: Optional[Callable[[TaskProgress], None]] = None

    async def start_monitoring(
        self,
        task_id: str,
        goal: str,
        actions: List[ActionEvent]
    ) -> None:
        """
        Start async monitoring loop for task.

        Args:
            task_id: Unique task identifier
            goal: The goal to achieve
            actions: Initial list of actions to execute
        """
        logger.info(f"Starting progress monitoring for task: {task_id}")

        self.current_progress = TaskProgress(
            task_id=task_id,
            goal=goal,
            total_actions=len(actions),
            actions=actions.copy()
        )

        self._running = True
        self._action_just_completed = False
        self._last_completed_index = -1

        # Start background monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        # Capture initial state
        initial_state = await self._capture_current_state()
        if initial_state:
            self.current_progress.state_history.append(initial_state)
            self.current_progress.last_successful_state = initial_state

    async def stop_monitoring(self) -> TaskProgress:
        """
        Stop monitoring loop and return final progress.

        Returns:
            Final TaskProgress with all stats
        """
        logger.info("Stopping progress monitoring")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self.current_progress:
            self.current_progress.finished_at = time.time()

        return self.current_progress

    async def action_completed(
        self,
        action_index: int,
        result: Dict[str, Any]
    ) -> Optional[ProgressAnalysis]:
        """
        Notify that an action has completed.

        Called by executor after each action. Triggers analysis.

        Args:
            action_index: Index of completed action
            result: Result from action execution

        Returns:
            ProgressAnalysis with suggested adjustments (if any)
        """
        if not self.current_progress:
            return None

        self.current_progress.completed_actions += 1
        self.current_progress.current_action_index = action_index + 1
        self.current_progress.progress_percentage = (
            self.current_progress.completed_actions / self.current_progress.total_actions * 100
        )

        self._action_just_completed = True
        self._last_completed_index = action_index

        # Update action status
        if action_index < len(self.current_progress.actions):
            action = self.current_progress.actions[action_index]
            action.status = ActionStatus.COMPLETED
            action.result = result

        # Trigger progress callback
        if self.on_progress_update:
            self.on_progress_update(self.current_progress)

        # Wait briefly for state to settle, then analyze
        await asyncio.sleep(0.3)
        current_state = await self._capture_current_state()

        if current_state:
            analysis = await self._analyze_progress(current_state, action_index)
            return analysis

        return None

    def get_current_action(self, index: int) -> Optional[ActionEvent]:
        """Get action at index (may have been modified)."""
        if not self.current_progress or index >= len(self.current_progress.actions):
            return None
        return self.current_progress.actions[index]

    def get_inserted_actions(self, after_index: int) -> List[ActionEvent]:
        """Get any actions inserted after the given index."""
        if not self.current_progress:
            return []
        return self.current_progress.inserted_actions.get(after_index, [])

    @property
    def goal_achieved(self) -> bool:
        """Check if goal has been achieved."""
        return self.current_progress.goal_achieved if self.current_progress else False

    async def _monitor_loop(self) -> None:
        """
        Background async loop that runs during task execution.

        Captures state periodically and analyzes progress after actions.
        """
        logger.info("Progress monitor loop started")

        while self._running:
            try:
                # Capture current state
                current_state = await self._capture_current_state()

                if current_state and self.current_progress:
                    # Store in rolling history
                    self.current_progress.state_history.append(current_state)
                    if len(self.current_progress.state_history) > self.max_state_history:
                        self.current_progress.state_history.pop(0)

                    # If action just completed, analysis is handled by action_completed()
                    # This loop is for continuous monitoring between actions

                # Sleep before next capture
                await asyncio.sleep(self.capture_interval)

            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(1.0)

        logger.info("Progress monitor loop ended")

    async def _capture_current_state(self) -> Optional[ScreenState]:
        """Capture current screen state via MoireServer."""
        if not self.moire_client:
            return None

        try:
            result = await self.moire_client.capture_and_wait_for_complete(timeout=5.0)

            if not result or not result.screenshot_base64:
                return None

            # Decode screenshot
            screenshot_b64 = result.screenshot_base64
            if ',' in screenshot_b64:
                screenshot_b64 = screenshot_b64.split(',', 1)[1]

            screenshot_bytes = base64.b64decode(screenshot_b64)

            # Extract OCR texts
            ocr_texts = []
            elements = []
            if hasattr(self.moire_client, 'current_context') and self.moire_client.current_context:
                for elem in self.moire_client.current_context.elements:
                    if hasattr(elem, 'text') and elem.text:
                        ocr_texts.append(elem.text)
                    elements.append({
                        'text': getattr(elem, 'text', ''),
                        'bounds': getattr(elem, 'bounds', {}),
                        'center': getattr(elem, 'center', {})
                    })

            return ScreenState(
                screenshot=screenshot_bytes,
                ocr_texts=ocr_texts,
                timestamp=time.time(),
                elements=elements
            )

        except Exception as e:
            logger.error(f"Failed to capture state: {e}")
            return None

    async def _analyze_progress(
        self,
        current_state: ScreenState,
        action_index: int
    ) -> ProgressAnalysis:
        """
        Analyze progress after an action completed.

        Compares current state to expected state and suggests adjustments.

        Args:
            current_state: Current screen state
            action_index: Index of just-completed action

        Returns:
            ProgressAnalysis with findings and suggestions
        """
        if not self.current_progress:
            return ProgressAnalysis(
                action_succeeded=False,
                expected_vs_actual="No progress context",
                progress_delta=0.0,
                confidence=0.0
            )

        action = self.current_progress.actions[action_index]
        expected_change = action.description

        # 1. Pixel-level change detection
        change_regions = []
        total_change = 0.0

        if self.change_detector and self.current_progress.last_successful_state:
            try:
                detection = self.change_detector.detect_changes(
                    self.current_progress.last_successful_state.screenshot,
                    current_state.screenshot
                )
                total_change = detection.total_change_percentage
                change_regions = [
                    {'bounds': r.bounds, 'intensity': r.intensity.value}
                    for r in detection.regions
                ]
            except Exception as e:
                logger.warning(f"Change detection failed: {e}")

        # 2. OCR text comparison
        new_texts = []
        removed_texts = []

        if self.current_progress.last_successful_state:
            previous_texts = set(self.current_progress.last_successful_state.ocr_texts)
            current_texts = set(current_state.ocr_texts)
            new_texts = list(current_texts - previous_texts)
            removed_texts = list(previous_texts - current_texts)

        # 3. Determine success based on action type
        action_succeeded = self._evaluate_action_success(
            action, total_change, new_texts, removed_texts
        )

        # 4. Check if goal might be achieved
        goal_achieved = await self._check_goal_achieved(current_state)

        # 5. Determine if adjustment needed
        suggested_adjustment = None
        if not action_succeeded and not goal_achieved:
            suggested_adjustment = self._suggest_adjustment(
                action, action_index, current_state, total_change
            )

        # 6. Calculate progress delta
        progress_delta = 0.1 if action_succeeded else -0.05

        # 7. Build analysis
        analysis = ProgressAnalysis(
            action_succeeded=action_succeeded,
            expected_vs_actual=f"Expected: {expected_change}, Change: {total_change:.1f}%, New texts: {len(new_texts)}",
            progress_delta=progress_delta,
            suggested_adjustment=suggested_adjustment,
            goal_achieved=goal_achieved,
            confidence=0.8 if action_succeeded else 0.4,
            change_regions=change_regions
        )

        # Update last successful state if action succeeded
        if action_succeeded:
            self.current_progress.last_successful_state = current_state

        # Handle goal achieved
        if goal_achieved:
            self.current_progress.goal_achieved = True
            self._running = False
            if self.on_goal_achieved:
                self.on_goal_achieved(self.current_progress)

        # Handle adjustment
        if suggested_adjustment:
            self._apply_adjustment(suggested_adjustment)
            if self.on_adjustment:
                self.on_adjustment(suggested_adjustment)

        return analysis

    def _evaluate_action_success(
        self,
        action: ActionEvent,
        change_percentage: float,
        new_texts: List[str],
        removed_texts: List[str]
    ) -> bool:
        """Evaluate if action succeeded based on type and observed changes."""
        action_type = action.action_type

        if action_type == "wait":
            # Wait always succeeds
            return True

        elif action_type == "press_key":
            key = action.params.get("key", "")
            if key in ["win", "alt+tab"]:
                # Major window changes expected
                return change_percentage > 10
            elif key == "enter":
                # Some change expected
                return change_percentage > 2 or len(new_texts) > 0
            else:
                # Any change is good
                return change_percentage > 1

        elif action_type == "type":
            # Text should appear
            typed_text = action.params.get("text", "")
            # Check if any part of typed text appears in new texts
            for new_text in new_texts:
                if typed_text.lower() in new_text.lower() or new_text.lower() in typed_text.lower():
                    return True
            # Fallback: any text change
            return len(new_texts) > 0 or change_percentage > 1

        elif action_type in ["click", "find_and_click"]:
            # Some change expected from click
            return change_percentage > 2

        elif action_type == "hotkey":
            # Hotkeys usually cause significant changes
            return change_percentage > 5

        # Default: accept any notable change
        return change_percentage > 3

    async def _check_goal_achieved(self, current_state: ScreenState) -> bool:
        """Check if the goal has been achieved using vision analysis."""
        if not self.vision_agent or not self.current_progress:
            return False

        # Only check periodically to save API calls
        if self.current_progress.completed_actions < self.current_progress.total_actions * 0.5:
            return False

        try:
            # Use vision agent to check goal
            result = await self.vision_agent.analyze_screen_for_task(
                current_state.screenshot,
                self.current_progress.goal
            )

            return result.get('task_completable', False) and result.get('goal_achieved', False)

        except Exception as e:
            logger.warning(f"Goal check failed: {e}")
            return False

    def _suggest_adjustment(
        self,
        failed_action: ActionEvent,
        action_index: int,
        current_state: ScreenState,
        change_percentage: float
    ) -> Optional[ActionAdjustment]:
        """Suggest an adjustment based on the failed action."""
        action_type = failed_action.action_type

        # Click failed - might need new coordinates
        if action_type in ["click", "find_and_click"]:
            target = failed_action.params.get("target", "")
            if target:
                # Suggest retry with vision search
                return ActionAdjustment(
                    type="retry",
                    action_index=action_index,
                    new_params={"use_vision": True},
                    reason=f"Click on '{target}' failed, retrying with vision"
                )

        # Type failed - might need to click input first
        if action_type == "type" and change_percentage < 1:
            return ActionAdjustment(
                type="insert",
                action_index=action_index,
                new_action=ActionEvent(
                    id=f"inserted_click_{action_index}",
                    task_id=failed_action.task_id,
                    action_type="find_and_click",
                    params={"target": "text input field"},
                    description="Click input field before typing",
                    status=ActionStatus.PENDING
                ),
                reason="Typing failed, inserting click on input field"
            )

        # Hotkey failed - wait and retry
        if action_type == "hotkey" and change_percentage < 5:
            return ActionAdjustment(
                type="retry",
                action_index=action_index,
                new_params={"delay_before": 1.0},
                reason="Hotkey failed, retrying with delay"
            )

        # No specific suggestion
        return None

    def _apply_adjustment(self, adjustment: ActionAdjustment) -> None:
        """Apply an adjustment to the action plan."""
        if not self.current_progress:
            return

        desc_prefix = L.get('progress_adjustment', reason=adjustment.reason) if HAS_LOCALIZATION and L else f"Adjusted: {adjustment.reason}"
        logger.info(desc_prefix)

        if adjustment.type == "modify":
            # Update params of specific action
            if adjustment.action_index < len(self.current_progress.actions):
                action = self.current_progress.actions[adjustment.action_index]
                if adjustment.new_params:
                    action.params.update(adjustment.new_params)
                action.description = f"{action.description} ({adjustment.reason})"

        elif adjustment.type == "insert":
            # Store inserted action for execution
            if adjustment.new_action:
                if adjustment.action_index not in self.current_progress.inserted_actions:
                    self.current_progress.inserted_actions[adjustment.action_index] = []
                self.current_progress.inserted_actions[adjustment.action_index].append(adjustment.new_action)
                self.current_progress.total_actions += 1

        elif adjustment.type == "skip":
            # Mark action as skipped
            if adjustment.action_index < len(self.current_progress.actions):
                self.current_progress.actions[adjustment.action_index].status = ActionStatus.SKIPPED

        elif adjustment.type == "retry":
            # Create retry action
            if adjustment.action_index < len(self.current_progress.actions):
                original = self.current_progress.actions[adjustment.action_index]
                retry_action = ActionEvent(
                    id=f"{original.id}_retry",
                    task_id=original.task_id,
                    action_type=original.action_type,
                    params={**original.params, **(adjustment.new_params or {})},
                    description=f"Retry: {original.description}",
                    status=ActionStatus.PENDING
                )
                if adjustment.action_index not in self.current_progress.inserted_actions:
                    self.current_progress.inserted_actions[adjustment.action_index] = []
                self.current_progress.inserted_actions[adjustment.action_index].append(retry_action)
                self.current_progress.total_actions += 1

        # Add blocker info
        if adjustment.reason and adjustment.reason not in self.current_progress.blockers:
            self.current_progress.blockers.append(adjustment.reason)

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of current progress."""
        if not self.current_progress:
            return {"status": "not_started"}

        return {
            "task_id": self.current_progress.task_id,
            "goal": self.current_progress.goal,
            "progress_percentage": self.current_progress.progress_percentage,
            "completed_actions": self.current_progress.completed_actions,
            "total_actions": self.current_progress.total_actions,
            "goal_achieved": self.current_progress.goal_achieved,
            "blockers": self.current_progress.blockers,
            "duration": time.time() - self.current_progress.started_at
        }


# Singleton instance
_progress_agent_instance: Optional[ProgressAgent] = None


def get_progress_agent(
    moire_client: Optional[MoireWebSocketClient] = None
) -> ProgressAgent:
    """Get or create singleton ProgressAgent instance."""
    global _progress_agent_instance
    if _progress_agent_instance is None:
        _progress_agent_instance = ProgressAgent(moire_client=moire_client)
    return _progress_agent_instance


def reset_progress_agent() -> None:
    """Reset the singleton instance."""
    global _progress_agent_instance
    _progress_agent_instance = None
