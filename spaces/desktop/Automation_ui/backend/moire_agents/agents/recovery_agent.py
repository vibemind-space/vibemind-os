"""
Recovery Agent - Plan adjustment when actions fail.

This agent analyzes failures and determines recovery strategies:
1. RETRY_SAME: Same action, different timing
2. RETRY_ALTERNATIVE: Different approach (keyboard vs mouse)
3. SKIP_AND_CONTINUE: Non-critical action, move on
4. ABORT_AND_REPORT: Critical failure, stop execution
5. REPLAN: Generate new plan from current state using LLM

Usage:
    from agents.recovery_agent import RecoveryAgent

    agent = RecoveryAgent()
    result = await agent.handle_failure(task, failure_reason)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class RecoveryStrategy(Enum):
    """Strategy for recovering from failures."""
    RETRY_SAME = "retry_same"           # Same action, different timing
    RETRY_ALTERNATIVE = "retry_alt"     # Different approach
    SKIP_AND_CONTINUE = "skip"          # Non-critical, move on
    ABORT_AND_REPORT = "abort"          # Critical failure, stop
    REPLAN = "replan"                   # Generate new plan from current state


@dataclass
class FailureContext:
    """Context about a failed action."""
    action_type: str
    action_params: Dict[str, Any]
    error_message: str
    attempt_count: int
    screen_state: Optional[Any] = None
    goal: str = ""
    remaining_subtasks: List = field(default_factory=list)


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    strategy: RecoveryStrategy
    success: bool
    new_action: Optional[Dict] = None
    new_plan: Optional[List] = None
    message: str = ""
    should_continue: bool = True


class RecoveryAgent:
    """
    Agent that handles failures and determines recovery strategies.

    Analyzes:
    - Action type (keyboard vs mouse vs click)
    - Error message
    - Screen state
    - Goal context

    Then decides:
    - Best recovery strategy
    - Modified action parameters
    - Alternative approach
    """

    # Actions that are critical (abort on failure)
    CRITICAL_ACTIONS = {"app_launch", "window_open"}

    # Actions that can be skipped if non-critical
    SKIPPABLE_ACTIONS = {"sleep", "wait"}

    # Alternative approaches for action types
    ALTERNATIVES = {
        "click": ["hotkey", "press"],  # If click fails, try keyboard
        "hotkey": ["write", "press"],  # If hotkey fails, try typing
        "scroll": ["press"],            # If scroll fails, try arrow keys
    }

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay: float = 0.5,
        use_llm_replan: bool = True
    ):
        """
        Initialize the RecoveryAgent.

        Args:
            max_retries: Maximum retry attempts per action
            retry_delay: Delay between retries
            use_llm_replan: Whether to use LLM for replanning
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.use_llm_replan = use_llm_replan

        # Statistics
        self._stats = {
            "retries": 0,
            "alternatives": 0,
            "skips": 0,
            "aborts": 0,
            "replans": 0
        }

    async def handle_failure(
        self,
        context: FailureContext
    ) -> RecoveryResult:
        """
        Analyze failure and determine recovery strategy.

        Args:
            context: FailureContext with failure details

        Returns:
            RecoveryResult with strategy and modified action
        """
        logger.info(f"Handling failure: {context.error_message}")
        logger.debug(f"Action: {context.action_type}, Attempts: {context.attempt_count}")

        # Determine best strategy
        strategy = self._select_strategy(context)
        logger.info(f"Selected strategy: {strategy.value}")

        # Execute strategy
        if strategy == RecoveryStrategy.RETRY_SAME:
            return await self._retry_same(context)

        elif strategy == RecoveryStrategy.RETRY_ALTERNATIVE:
            return await self._retry_alternative(context)

        elif strategy == RecoveryStrategy.SKIP_AND_CONTINUE:
            return self._skip_action(context)

        elif strategy == RecoveryStrategy.ABORT_AND_REPORT:
            return self._abort_execution(context)

        elif strategy == RecoveryStrategy.REPLAN:
            return await self._replan_from_state(context)

        else:
            return self._abort_execution(context)

    def _select_strategy(self, context: FailureContext) -> RecoveryStrategy:
        """
        Select the best recovery strategy based on context.

        Decision factors:
        1. Attempt count (retry if low)
        2. Action type (critical vs skippable)
        3. Error type (timeout vs not found vs permission)
        4. Screen state (if available)
        """
        # If we haven't retried yet, try same action
        if context.attempt_count < self.max_retries:
            return RecoveryStrategy.RETRY_SAME

        # If action type has alternatives, try them
        if context.action_type in self.ALTERNATIVES:
            return RecoveryStrategy.RETRY_ALTERNATIVE

        # If action is skippable, skip it
        if context.action_type in self.SKIPPABLE_ACTIONS:
            return RecoveryStrategy.SKIP_AND_CONTINUE

        # If action is critical, abort
        if context.action_type in self.CRITICAL_ACTIONS:
            return RecoveryStrategy.ABORT_AND_REPORT

        # If we have screen state and LLM replan is enabled, try replanning
        if self.use_llm_replan and context.screen_state:
            return RecoveryStrategy.REPLAN

        # Default to abort
        return RecoveryStrategy.ABORT_AND_REPORT

    async def _retry_same(self, context: FailureContext) -> RecoveryResult:
        """
        Retry the same action with modified timing.

        Modifications:
        - Increase delay before action
        - Slow down typing interval
        - Extend wait times
        """
        self._stats["retries"] += 1

        # Modify action parameters
        modified_action = context.action_params.copy()

        # Increase wait/delay parameters
        if "interval" in modified_action:
            modified_action["interval"] *= 1.5  # Slower typing

        if "wait_after" in modified_action:
            modified_action["wait_after"] *= 1.5  # Longer wait

        logger.info(f"Retrying with modified params: {modified_action}")

        return RecoveryResult(
            strategy=RecoveryStrategy.RETRY_SAME,
            success=True,  # Indicates strategy was selected, not that action succeeded
            new_action=modified_action,
            message=f"Retrying with adjusted timing (attempt {context.attempt_count + 1})",
            should_continue=True
        )

    async def _retry_alternative(self, context: FailureContext) -> RecoveryResult:
        """
        Try an alternative approach for the action.

        Examples:
        - Click fails -> Try keyboard shortcut
        - Hotkey fails -> Try typing command
        - Scroll fails -> Try arrow keys
        """
        self._stats["alternatives"] += 1

        alternatives = self.ALTERNATIVES.get(context.action_type, [])

        if not alternatives:
            return self._abort_execution(context)

        # For now, just suggest alternative (actual implementation would generate action)
        alt_type = alternatives[0]

        logger.info(f"Suggesting alternative: {context.action_type} -> {alt_type}")

        return RecoveryResult(
            strategy=RecoveryStrategy.RETRY_ALTERNATIVE,
            success=True,
            message=f"Try alternative approach: {alt_type} instead of {context.action_type}",
            should_continue=True
        )

    def _skip_action(self, context: FailureContext) -> RecoveryResult:
        """Skip the failed action and continue."""
        self._stats["skips"] += 1

        logger.info(f"Skipping non-critical action: {context.action_type}")

        return RecoveryResult(
            strategy=RecoveryStrategy.SKIP_AND_CONTINUE,
            success=True,
            message=f"Skipped non-critical action: {context.action_type}",
            should_continue=True
        )

    def _abort_execution(self, context: FailureContext) -> RecoveryResult:
        """Abort execution due to critical failure."""
        self._stats["aborts"] += 1

        logger.error(f"Aborting execution: {context.error_message}")

        return RecoveryResult(
            strategy=RecoveryStrategy.ABORT_AND_REPORT,
            success=False,
            message=f"Critical failure: {context.error_message}",
            should_continue=False
        )

    async def _replan_from_state(self, context: FailureContext) -> RecoveryResult:
        """
        Generate a new plan based on current screen state.

        Uses LLM to:
        1. Analyze current screen via vision
        2. Determine what's already done
        3. Generate new steps to reach goal
        """
        self._stats["replans"] += 1

        if not self.use_llm_replan:
            return self._abort_execution(context)

        logger.info("Attempting to replan from current state...")

        try:
            # This would call the LLM to generate new plan
            # For now, return a placeholder
            new_plan = await self._generate_new_plan(
                context.screen_state,
                context.goal,
                context.remaining_subtasks
            )

            if new_plan:
                return RecoveryResult(
                    strategy=RecoveryStrategy.REPLAN,
                    success=True,
                    new_plan=new_plan,
                    message="Generated new plan from current state",
                    should_continue=True
                )
            else:
                return self._abort_execution(context)

        except Exception as e:
            logger.error(f"Replanning failed: {e}")
            return self._abort_execution(context)

    async def _generate_new_plan(
        self,
        screen_state: Any,
        goal: str,
        remaining_subtasks: List
    ) -> Optional[List]:
        """
        Generate new plan using LLM.

        This is a placeholder - actual implementation would:
        1. Send screenshot to vision LLM
        2. Ask it what has been accomplished
        3. Generate new steps to complete goal
        """
        logger.debug(f"Generating new plan for goal: {goal}")

        # Placeholder - would call TaskDecomposer with screen context
        # For now, return None to trigger abort
        return None

    def get_stats(self) -> Dict[str, int]:
        """Get recovery statistics."""
        return self._stats.copy()

    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            "retries": 0,
            "alternatives": 0,
            "skips": 0,
            "aborts": 0,
            "replans": 0
        }


# Convenience function
async def attempt_recovery(
    action_type: str,
    action_params: Dict,
    error_message: str,
    attempt_count: int = 1,
    goal: str = ""
) -> RecoveryResult:
    """
    Convenience function to attempt recovery.

    Args:
        action_type: Type of failed action
        action_params: Parameters of failed action
        error_message: Error message from failure
        attempt_count: Number of attempts so far
        goal: Original goal

    Returns:
        RecoveryResult with strategy and next steps
    """
    context = FailureContext(
        action_type=action_type,
        action_params=action_params,
        error_message=error_message,
        attempt_count=attempt_count,
        goal=goal
    )

    agent = RecoveryAgent()
    return await agent.handle_failure(context)
