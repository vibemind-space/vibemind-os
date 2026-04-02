"""
ClarificationQueue - Non-Blocking Clarification Collection.

Collects clarifications without blocking generation.
Clarifications are queued and can be:
- Answered by user via API/dashboard
- Auto-resolved with defaults after timeout
- Batched and presented at phase boundaries

This enables generation to continue while questions accumulate,
improving throughput and user experience.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

import structlog

from src.engine.ambiguity_detector import DetectedAmbiguity
from src.engine.interpretation_generator import Interpretation

if TYPE_CHECKING:
    from src.mind.event_bus import EventBus

logger = structlog.get_logger(__name__)


class ClarificationPriority(Enum):
    """Priority levels for clarifications."""

    HIGH = 1  # Blocks critical path, needs immediate attention
    MEDIUM = 2  # Important but can wait
    LOW = 3  # Nice to have, can use defaults


class ClarificationSeverity(Enum):
    """Severity of the ambiguity."""

    HIGH = "high"  # Wrong interpretation could cause significant issues
    MEDIUM = "medium"  # Could affect functionality
    LOW = "low"  # Mostly cosmetic or minor


@dataclass
class QueuedClarification:
    """A clarification item in the queue."""

    id: str
    ambiguity: DetectedAmbiguity
    interpretations: list[Interpretation]
    priority: ClarificationPriority = ClarificationPriority.MEDIUM
    severity: ClarificationSeverity = ClarificationSeverity.MEDIUM
    queued_at: datetime = field(default_factory=datetime.now)
    timeout_at: Optional[datetime] = None
    answered: bool = False
    selected_interpretation_id: Optional[str] = None
    selected_interpretation: Optional[Interpretation] = None
    auto_resolved: bool = False  # True if resolved by timeout with default

    @property
    def description(self) -> str:
        """Get human-readable description."""
        return self.ambiguity.description

    @property
    def requirement_text(self) -> str:
        """Get the requirement text that triggered this."""
        return self.ambiguity.requirement_text

    @property
    def recommended_interpretation(self) -> Optional[Interpretation]:
        """Get the recommended interpretation if any."""
        for interp in self.interpretations:
            if interp.is_recommended:
                return interp
        return self.interpretations[0] if self.interpretations else None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "ambiguity_id": self.ambiguity.id,
            "requirement_id": self.ambiguity.requirement_id,
            "description": self.description,
            "requirement_text": self.requirement_text[:200],
            "detected_term": self.ambiguity.detected_term,
            "priority": self.priority.value,
            "severity": self.severity.value,
            "queued_at": self.queued_at.isoformat(),
            "timeout_at": self.timeout_at.isoformat() if self.timeout_at else None,
            "answered": self.answered,
            "selected_interpretation_id": self.selected_interpretation_id,
            "auto_resolved": self.auto_resolved,
            "interpretations": [
                {
                    "id": interp.id,
                    "label": interp.label,
                    "description": interp.description,
                    "technical_approach": interp.technical_approach,
                    "complexity": interp.complexity,
                    "is_recommended": interp.is_recommended,
                    "trade_offs": interp.trade_offs,
                }
                for interp in self.interpretations
            ],
        }


class ClarificationQueue:
    """
    Non-blocking clarification queue.

    Collects clarifications without blocking generation.
    Supports:
    - Async enqueueing of new clarifications
    - User resolution via API
    - Auto-resolution with defaults after timeout
    - Priority-based ordering
    - Event publishing for real-time updates
    """

    DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        auto_resolve_timeout: int = 300,
        use_defaults_on_timeout: bool = True,
        event_bus: Optional["EventBus"] = None,
    ):
        self._queue: list[QueuedClarification] = []
        self._resolved: dict[str, str] = {}  # ambiguity_id -> interpretation_id
        self._resolved_interpretations: dict[str, Interpretation] = {}
        self._counter = 0
        self.auto_resolve_timeout = auto_resolve_timeout
        self.use_defaults_on_timeout = use_defaults_on_timeout
        self.event_bus = event_bus
        self._timeout_task: Optional[asyncio.Task] = None
        self.logger = logger.bind(component="ClarificationQueue")

    def _generate_id(self) -> str:
        """Generate unique clarification ID."""
        self._counter += 1
        return f"CLARQ-{self._counter:04d}"

    async def enqueue(
        self,
        ambiguity: DetectedAmbiguity,
        interpretations: list[Interpretation],
        priority: ClarificationPriority = ClarificationPriority.MEDIUM,
        timeout_seconds: Optional[int] = None,
    ) -> QueuedClarification:
        """
        Add a clarification to the queue (non-blocking).

        Args:
            ambiguity: The detected ambiguity
            interpretations: Possible interpretations
            priority: Priority level
            timeout_seconds: Custom timeout (or use default)

        Returns:
            The queued clarification item
        """
        timeout = timeout_seconds or self.auto_resolve_timeout
        timeout_at = datetime.fromtimestamp(
            datetime.now().timestamp() + timeout
        )

        # Determine severity from ambiguity type
        severity = ClarificationSeverity.MEDIUM
        if ambiguity.ambiguity_type.value in ("conflict", "unclear_scope"):
            severity = ClarificationSeverity.HIGH
        elif ambiguity.ambiguity_type.value == "technology_choice":
            severity = ClarificationSeverity.LOW

        item = QueuedClarification(
            id=self._generate_id(),
            ambiguity=ambiguity,
            interpretations=interpretations,
            priority=priority,
            severity=severity,
            timeout_at=timeout_at,
        )

        # Insert in priority order
        inserted = False
        for i, existing in enumerate(self._queue):
            if priority.value < existing.priority.value:
                self._queue.insert(i, item)
                inserted = True
                break

        if not inserted:
            self._queue.append(item)

        self.logger.info(
            "clarification_enqueued",
            id=item.id,
            ambiguity_id=ambiguity.id,
            term=ambiguity.detected_term,
            priority=priority.value,
            queue_size=len(self._queue),
        )

        # Publish event for real-time dashboard updates
        if self.event_bus:
            from src.mind.event_bus import Event, EventType
            await self.event_bus.publish(
                Event(
                    type=EventType.CLARIFICATION_REQUESTED,
                    source="ClarificationQueue",
                    data={
                        "action": "enqueued",
                        "clarification": item.to_dict(),
                        "queue_size": len(self._queue),
                    },
                )
            )

        # Start timeout checker if not running
        if not self._timeout_task or self._timeout_task.done():
            self._timeout_task = asyncio.create_task(self._timeout_checker())

        return item

    async def enqueue_batch(
        self,
        items: list[tuple[DetectedAmbiguity, list[Interpretation]]],
        priority: ClarificationPriority = ClarificationPriority.MEDIUM,
    ) -> list[QueuedClarification]:
        """
        Enqueue multiple clarifications at once.

        Args:
            items: List of (ambiguity, interpretations) tuples
            priority: Priority for all items

        Returns:
            List of queued clarifications
        """
        queued = []
        for ambiguity, interpretations in items:
            item = await self.enqueue(ambiguity, interpretations, priority)
            queued.append(item)
        return queued

    def get_pending(self) -> list[QueuedClarification]:
        """Get all pending (unanswered) clarifications."""
        return [c for c in self._queue if not c.answered]

    def get_all(self) -> list[QueuedClarification]:
        """Get all clarifications (including answered)."""
        return list(self._queue)

    def get_by_id(self, clarification_id: str) -> Optional[QueuedClarification]:
        """Get a specific clarification by ID."""
        for item in self._queue:
            if item.id == clarification_id:
                return item
        return None

    def get_by_ambiguity_id(self, ambiguity_id: str) -> Optional[QueuedClarification]:
        """Get clarification by ambiguity ID."""
        for item in self._queue:
            if item.ambiguity.id == ambiguity_id:
                return item
        return None

    async def resolve(
        self,
        clarification_id: str,
        interpretation_id: str,
    ) -> bool:
        """
        Mark a clarification as resolved.

        Args:
            clarification_id: The queue item ID (CLARQ-XXXX)
            interpretation_id: The chosen interpretation ID

        Returns:
            True if resolved successfully
        """
        item = self.get_by_id(clarification_id)
        if not item:
            self.logger.warning("resolve_unknown_clarification", id=clarification_id)
            return False

        if item.answered:
            self.logger.debug("clarification_already_answered", id=clarification_id)
            return True

        # Find the interpretation
        selected = None
        for interp in item.interpretations:
            if interp.id == interpretation_id:
                selected = interp
                break

        if not selected:
            self.logger.warning(
                "invalid_interpretation",
                clarification_id=clarification_id,
                interpretation_id=interpretation_id,
            )
            return False

        # Mark as resolved
        item.answered = True
        item.selected_interpretation_id = interpretation_id
        item.selected_interpretation = selected

        # Store in resolved map for easy lookup
        self._resolved[item.ambiguity.id] = interpretation_id
        self._resolved_interpretations[item.ambiguity.id] = selected

        self.logger.info(
            "clarification_resolved",
            id=clarification_id,
            ambiguity_id=item.ambiguity.id,
            interpretation_id=interpretation_id,
            label=selected.label,
        )

        # Publish event
        if self.event_bus:
            from src.mind.event_bus import Event, EventType
            await self.event_bus.publish(
                Event(
                    type=EventType.CLARIFICATION_CHOICE_SUBMITTED,
                    source="ClarificationQueue",
                    data={
                        "action": "resolved",
                        "clarification_id": clarification_id,
                        "ambiguity_id": item.ambiguity.id,
                        "interpretation_id": interpretation_id,
                        "interpretation_label": selected.label,
                        "pending_count": len(self.get_pending()),
                    },
                )
            )

        return True

    async def resolve_all_with_defaults(self) -> int:
        """
        Auto-resolve all pending clarifications with recommended defaults.

        Returns:
            Number of clarifications resolved
        """
        count = 0
        for item in self.get_pending():
            recommended = item.recommended_interpretation
            if recommended:
                item.answered = True
                item.auto_resolved = True
                item.selected_interpretation_id = recommended.id
                item.selected_interpretation = recommended
                self._resolved[item.ambiguity.id] = recommended.id
                self._resolved_interpretations[item.ambiguity.id] = recommended
                count += 1

                self.logger.info(
                    "clarification_auto_resolved",
                    id=item.id,
                    ambiguity_id=item.ambiguity.id,
                    interpretation=recommended.label,
                )

        if count > 0 and self.event_bus:
            from src.mind.event_bus import Event, EventType
            await self.event_bus.publish(
                Event(
                    type=EventType.CLARIFICATION_RESOLVED,
                    source="ClarificationQueue",
                    data={
                        "action": "all_defaults",
                        "count": count,
                        "pending_count": len(self.get_pending()),
                    },
                )
            )

        return count

    async def _timeout_checker(self) -> None:
        """
        Background task that checks for timed-out clarifications.

        Auto-resolves with defaults if use_defaults_on_timeout is True.
        """
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds

            now = datetime.now()
            timed_out = []

            for item in self.get_pending():
                if item.timeout_at and now > item.timeout_at:
                    timed_out.append(item)

            if not timed_out:
                # Check if we should stop
                if not self.get_pending():
                    break
                continue

            for item in timed_out:
                if self.use_defaults_on_timeout:
                    recommended = item.recommended_interpretation
                    if recommended:
                        item.answered = True
                        item.auto_resolved = True
                        item.selected_interpretation_id = recommended.id
                        item.selected_interpretation = recommended
                        self._resolved[item.ambiguity.id] = recommended.id
                        self._resolved_interpretations[item.ambiguity.id] = recommended

                        self.logger.info(
                            "clarification_timeout_auto_resolved",
                            id=item.id,
                            ambiguity_id=item.ambiguity.id,
                            interpretation=recommended.label,
                        )

                        # Publish timeout event
                        if self.event_bus:
                            from src.mind.event_bus import Event, EventType
                            await self.event_bus.publish(
                                Event(
                                    type=EventType.CLARIFICATION_TIMEOUT,
                                    source="ClarificationQueue",
                                    data={
                                        "action": "timeout_auto_resolved",
                                        "clarification_id": item.id,
                                        "ambiguity_id": item.ambiguity.id,
                                        "interpretation": recommended.label,
                                    },
                                )
                            )

            # Stop if no more pending
            if not self.get_pending():
                break

    def check_timeouts(self) -> list[str]:
        """
        Synchronously check for timed-out clarifications.

        Returns:
            List of IDs that timed out
        """
        now = datetime.now()
        timed_out = []

        for item in self.get_pending():
            if item.timeout_at and now > item.timeout_at:
                timed_out.append(item.id)

        return timed_out

    def get_resolution(self, ambiguity_id: str) -> Optional[str]:
        """
        Get the resolved interpretation ID for an ambiguity.

        Args:
            ambiguity_id: The ambiguity to check

        Returns:
            Interpretation ID if resolved, None otherwise
        """
        return self._resolved.get(ambiguity_id)

    def get_resolved_interpretation(self, ambiguity_id: str) -> Optional[Interpretation]:
        """
        Get the resolved Interpretation object for an ambiguity.

        Args:
            ambiguity_id: The ambiguity to check

        Returns:
            Interpretation if resolved, None otherwise
        """
        return self._resolved_interpretations.get(ambiguity_id)

    def get_all_resolutions(self) -> dict[str, Interpretation]:
        """Get all resolved interpretations."""
        return dict(self._resolved_interpretations)

    def is_resolved(self, ambiguity_id: str) -> bool:
        """Check if an ambiguity has been resolved."""
        return ambiguity_id in self._resolved

    def pending_count(self) -> int:
        """Get count of pending clarifications."""
        return len(self.get_pending())

    def total_count(self) -> int:
        """Get total count of clarifications."""
        return len(self._queue)

    def get_statistics(self) -> dict:
        """Get queue statistics."""
        pending = self.get_pending()

        by_priority = {
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        by_severity = {
            "high": 0,
            "medium": 0,
            "low": 0,
        }

        for item in pending:
            priority_name = {1: "high", 2: "medium", 3: "low"}.get(item.priority.value, "medium")
            by_priority[priority_name] += 1
            by_severity[item.severity.value] += 1

        auto_resolved_count = sum(1 for item in self._queue if item.auto_resolved)

        return {
            "total": len(self._queue),
            "pending": len(pending),
            "resolved": len(self._queue) - len(pending),
            "auto_resolved": auto_resolved_count,
            "by_priority": by_priority,
            "by_severity": by_severity,
        }

    def clear(self) -> int:
        """
        Clear all clarifications from the queue.

        Returns:
            Number of items cleared
        """
        count = len(self._queue)
        self._queue.clear()
        self._resolved.clear()
        self._resolved_interpretations.clear()
        self._counter = 0

        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        self.logger.info("clarification_queue_cleared", count=count)
        return count

    async def stop(self) -> None:
        """Stop the queue and cancel background tasks."""
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

        self.logger.info("clarification_queue_stopped")
