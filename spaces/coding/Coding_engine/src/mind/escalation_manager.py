"""
EscalationManager - Progressive Fix Strategy Management.

Manages escalation through increasingly sophisticated fix approaches:
1. PATTERN_FIX: Simple regex/pattern-based fixes
2. LLM_TARGETED: Current approach with error context
3. LLM_BROAD: LLM with expanded file context
4. SCOPE_REDUCTION: Simplify/stub problematic code
5. HUMAN_REVIEW: Trigger review gate for human intervention
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

import structlog

from src.mind.event_bus import Event, EventType

if TYPE_CHECKING:
    from src.mind.event_bus import EventBus
    from src.mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


class EscalationLevel(IntEnum):
    """Progressive escalation levels for fix attempts."""

    PATTERN_FIX = 1  # Simple regex/pattern-based fix
    LLM_TARGETED = 2  # Current approach - LLM with error context
    LLM_BROAD = 3  # LLM with expanded context from related files
    SCOPE_REDUCTION = 4  # Simplify or stub problematic code
    HUMAN_REVIEW = 5  # Request human intervention via review gate


@dataclass
class EscalationStrategy:
    """Configuration for an escalation level."""

    level: EscalationLevel
    name: str
    description: str
    max_attempts: int = 2
    timeout_seconds: int = 180
    confidence_threshold: float = 0.3  # Minimum confidence to try this level
    requires_context_files: int = 0  # How many related files to include


@dataclass
class EscalationAttempt:
    """Record of a single escalation attempt."""

    level: EscalationLevel
    error_hash: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    files_modified: list[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class EscalationState:
    """Tracks escalation state for an error."""

    error_hash: str
    error_type: str
    current_level: EscalationLevel = EscalationLevel.PATTERN_FIX
    attempts: list[EscalationAttempt] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_attempts(self) -> int:
        return len(self.attempts)

    @property
    def level_attempts(self) -> int:
        """Count attempts at current level."""
        return len([a for a in self.attempts if a.level == self.current_level])

    @property
    def should_escalate(self) -> bool:
        """Check if we should move to next level."""
        strategy = ESCALATION_STRATEGIES.get(self.current_level)
        if not strategy:
            return False
        return self.level_attempts >= strategy.max_attempts

    @property
    def is_at_max_level(self) -> bool:
        """Check if already at maximum escalation level."""
        return self.current_level >= EscalationLevel.HUMAN_REVIEW


# Strategy configurations for each level
ESCALATION_STRATEGIES: dict[EscalationLevel, EscalationStrategy] = {
    EscalationLevel.PATTERN_FIX: EscalationStrategy(
        level=EscalationLevel.PATTERN_FIX,
        name="Pattern Fix",
        description="Simple pattern-based fixes (missing imports, typos)",
        max_attempts=1,
        timeout_seconds=30,
        confidence_threshold=0.7,
        requires_context_files=0,
    ),
    EscalationLevel.LLM_TARGETED: EscalationStrategy(
        level=EscalationLevel.LLM_TARGETED,
        name="LLM Targeted Fix",
        description="LLM analyzes error and applies targeted fix",
        max_attempts=2,
        timeout_seconds=180,
        confidence_threshold=0.4,
        requires_context_files=0,
    ),
    EscalationLevel.LLM_BROAD: EscalationStrategy(
        level=EscalationLevel.LLM_BROAD,
        name="LLM Broad Context",
        description="LLM with expanded context from related files",
        max_attempts=2,
        timeout_seconds=300,
        confidence_threshold=0.25,
        requires_context_files=5,
    ),
    EscalationLevel.SCOPE_REDUCTION: EscalationStrategy(
        level=EscalationLevel.SCOPE_REDUCTION,
        name="Scope Reduction",
        description="Simplify or stub problematic functionality",
        max_attempts=1,
        timeout_seconds=120,
        confidence_threshold=0.1,
        requires_context_files=0,
    ),
    EscalationLevel.HUMAN_REVIEW: EscalationStrategy(
        level=EscalationLevel.HUMAN_REVIEW,
        name="Human Review",
        description="Request human intervention via review gate",
        max_attempts=1,
        timeout_seconds=0,  # No timeout - waits for human
        confidence_threshold=0.0,
        requires_context_files=0,
    ),
}


class EscalationManager:
    """
    Manages escalation through fix strategies.

    Instead of giving up after 2-3 retries, progressively escalates
    through more sophisticated approaches:
    1. Try simple pattern-based fixes
    2. Use LLM with focused context
    3. Use LLM with broader file context
    4. Simplify/stub the problematic code
    5. Ask for human help

    Each level has configurable max attempts and confidence thresholds.
    """

    def __init__(
        self,
        shared_state: Optional["SharedState"] = None,
        event_bus: Optional["EventBus"] = None,
    ):
        self.shared_state = shared_state
        self.event_bus = event_bus
        self._error_states: dict[str, EscalationState] = {}
        self._history: list[EscalationAttempt] = []
        self.logger = logger.bind(component="EscalationManager")

    def get_or_create_state(
        self,
        error_hash: str,
        error_type: str,
    ) -> EscalationState:
        """Get or create escalation state for an error."""
        if error_hash not in self._error_states:
            self._error_states[error_hash] = EscalationState(
                error_hash=error_hash,
                error_type=error_type,
            )
            self.logger.info(
                "escalation_state_created",
                error_hash=error_hash[:16],
                error_type=error_type,
            )
        return self._error_states[error_hash]

    def get_state(self, error_hash: str) -> Optional[EscalationState]:
        """Get escalation state for an error if it exists."""
        return self._error_states.get(error_hash)

    def get_current_strategy(
        self,
        error_hash: str,
    ) -> Optional[EscalationStrategy]:
        """Get the current escalation strategy for an error."""
        state = self._error_states.get(error_hash)
        if not state:
            # Return first level strategy for new errors
            return ESCALATION_STRATEGIES[EscalationLevel.PATTERN_FIX]
        return ESCALATION_STRATEGIES.get(state.current_level)

    async def escalate(self, error_hash: str) -> Optional[EscalationLevel]:
        """
        Move to next escalation level.

        Returns:
            New escalation level, or None if already at max level.
        """
        state = self._error_states.get(error_hash)
        if not state:
            self.logger.warning(
                "escalate_no_state",
                error_hash=error_hash[:16],
            )
            return None

        current = state.current_level
        if current >= EscalationLevel.HUMAN_REVIEW:
            self.logger.info(
                "escalation_at_max_level",
                error_hash=error_hash[:16],
            )
            return None

        next_level = EscalationLevel(current + 1)
        state.current_level = next_level

        self.logger.info(
            "escalation_level_increased",
            error_hash=error_hash[:16],
            from_level=current.name,
            to_level=next_level.name,
            total_attempts=state.total_attempts,
        )

        # Publish escalation event
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    type=EventType.AGENT_ACTING,
                    source="EscalationManager",
                    data={
                        "action": "escalation_level_changed",
                        "error_hash": error_hash,
                        "from_level": current.name,
                        "to_level": next_level.name,
                        "attempts": state.total_attempts,
                    },
                )
            )

        # If escalating to HUMAN_REVIEW, trigger the review gate
        if next_level == EscalationLevel.HUMAN_REVIEW:
            await self._trigger_human_review(error_hash, state)

        return next_level

    async def _trigger_human_review(
        self,
        error_hash: str,
        state: EscalationState,
    ) -> None:
        """Trigger the review gate for human intervention."""
        self.logger.warning(
            "escalating_to_human_review",
            error_hash=error_hash[:16],
            error_type=state.error_type,
            total_attempts=state.total_attempts,
        )

        # Build summary of what was tried
        attempt_summary = []
        for level in EscalationLevel:
            level_attempts = [a for a in state.attempts if a.level == level]
            if level_attempts:
                attempt_summary.append(
                    {
                        "level": level.name,
                        "attempts": len(level_attempts),
                        "last_error": level_attempts[-1].error_message,
                    }
                )

        # Publish ESCALATE_TO_HUMAN event if it exists
        if self.event_bus:
            # Use REVIEW_PAUSE_REQUESTED since ESCALATE_TO_HUMAN may not exist
            await self.event_bus.publish(
                Event(
                    type=EventType.REVIEW_PAUSE_REQUESTED,
                    source="EscalationManager",
                    data={
                        "error_hash": error_hash,
                        "error_type": state.error_type,
                        "attempts": state.total_attempts,
                        "reason": "All automated fix strategies exhausted",
                        "attempt_summary": attempt_summary,
                    },
                )
            )

        # Trigger review gate pause if shared_state available
        if self.shared_state:
            await self.shared_state.pause_for_review()

    def record_attempt(
        self,
        error_hash: str,
        level: EscalationLevel,
        success: bool,
        confidence_before: float = 0.0,
        confidence_after: float = 0.0,
        files_modified: Optional[list[str]] = None,
        error_message: Optional[str] = None,
    ) -> EscalationAttempt:
        """Record an escalation attempt."""
        attempt = EscalationAttempt(
            level=level,
            error_hash=error_hash,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=success,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            files_modified=files_modified or [],
            error_message=error_message,
        )

        state = self._error_states.get(error_hash)
        if state:
            state.attempts.append(attempt)

        self._history.append(attempt)

        self.logger.info(
            "escalation_attempt_recorded",
            error_hash=error_hash[:16],
            level=level.name,
            success=success,
            confidence_before=f"{confidence_before:.2f}",
            confidence_after=f"{confidence_after:.2f}",
        )

        return attempt

    def get_success_rate(
        self,
        level: EscalationLevel,
        error_type: Optional[str] = None,
    ) -> float:
        """Get historical success rate for an escalation level."""
        relevant = [a for a in self._history if a.level == level]

        if error_type:
            # Filter by error type if state exists
            relevant = [
                a
                for a in relevant
                if self._error_states.get(a.error_hash, EscalationState("", "")).error_type
                == error_type
            ]

        if not relevant:
            return 0.5  # Default if no history

        return sum(1 for a in relevant if a.success) / len(relevant)

    def clear_error_state(self, error_hash: str) -> None:
        """Clear escalation state for a resolved error."""
        if error_hash in self._error_states:
            state = self._error_states[error_hash]
            self.logger.info(
                "escalation_state_cleared",
                error_hash=error_hash[:16],
                final_level=state.current_level.name,
                total_attempts=state.total_attempts,
            )
            del self._error_states[error_hash]

    def should_escalate_for_confidence(
        self,
        error_hash: str,
        confidence: float,
    ) -> bool:
        """
        Check if we should escalate based on low confidence.

        If confidence is below the threshold for the current level,
        we should escalate to a more powerful approach.
        """
        strategy = self.get_current_strategy(error_hash)
        if not strategy:
            return False

        return confidence < strategy.confidence_threshold

    def get_statistics(self) -> dict:
        """Get escalation manager statistics."""
        stats = {
            "active_error_states": len(self._error_states),
            "total_attempts": len(self._history),
            "by_level": {},
        }

        for level in EscalationLevel:
            level_attempts = [a for a in self._history if a.level == level]
            if level_attempts:
                successes = sum(1 for a in level_attempts if a.success)
                stats["by_level"][level.name] = {
                    "attempts": len(level_attempts),
                    "successes": successes,
                    "success_rate": successes / len(level_attempts),
                }

        return stats

    def reset(self) -> None:
        """Reset all escalation states (for new generation session)."""
        self.logger.info(
            "escalation_manager_reset",
            cleared_states=len(self._error_states),
        )
        self._error_states.clear()
        # Keep history for learning across sessions
