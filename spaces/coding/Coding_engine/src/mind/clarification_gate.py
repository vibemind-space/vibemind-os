"""
ClarificationGate - Pause Generation for User Clarification.

Handles the workflow of:
1. Detecting that clarification is needed
2. Pausing generation (blocking mode) OR collecting in queue (queue mode)
3. Presenting options to the user
4. Collecting responses
5. Resuming generation with clarified requirements

Modes:
- Blocking Mode (queue_mode=False): Pauses generation until user responds
- Queue Mode (queue_mode=True): Collects clarifications non-blocking, generation continues

Queue mode is recommended for better UX - questions accumulate in a notification
queue while generation proceeds, and users can answer at their convenience.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

import structlog

from src.engine.ambiguity_detector import DetectedAmbiguity
from src.engine.interpretation_generator import Interpretation, InterpretationSet
from src.mind.event_bus import Event, EventType

if TYPE_CHECKING:
    from src.mind.event_bus import EventBus
    from src.mind.shared_state import SharedState
    from src.mind.clarification_queue import ClarificationQueue, ClarificationPriority

logger = structlog.get_logger(__name__)


class ClarificationStatus(Enum):
    """Status of a clarification request."""

    PENDING = "pending"  # Waiting for user response
    PARTIAL = "partial"  # Some questions answered
    COMPLETE = "complete"  # All questions answered
    EXPIRED = "expired"  # Timeout reached
    CANCELLED = "cancelled"  # User cancelled


@dataclass
class ClarificationRequest:
    """A request for user clarification."""

    id: str
    interpretation_sets: list[InterpretationSet]
    status: ClarificationStatus = ClarificationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    responses: dict[str, str] = field(default_factory=dict)  # ambiguity_id -> interpretation_id
    selected_interpretations: dict[str, Interpretation] = field(default_factory=dict)

    @property
    def total_questions(self) -> int:
        return len(self.interpretation_sets)

    @property
    def answered_questions(self) -> int:
        return len(self.responses)

    @property
    def is_complete(self) -> bool:
        return self.answered_questions >= self.total_questions

    @property
    def unanswered_ambiguity_ids(self) -> list[str]:
        all_ids = {iset.ambiguity.id for iset in self.interpretation_sets}
        answered_ids = set(self.responses.keys())
        return list(all_ids - answered_ids)


class ClarificationGate:
    """
    Manages the clarification workflow.

    When ambiguities are detected:
    1. Creates a ClarificationRequest
    2. Pauses generation via SharedState (blocking mode)
       OR adds to queue (queue mode)
    3. Publishes CLARIFICATION_NEEDED event
    4. Waits for user responses (blocking) OR continues (queue)
    5. Applies selections and resumes

    Modes:
    - queue_mode=False (default): Blocking - pauses generation until resolved
    - queue_mode=True: Non-blocking - adds to queue, generation continues
    """

    DEFAULT_TIMEOUT_SECONDS = 3600  # 1 hour default

    def __init__(
        self,
        shared_state: Optional["SharedState"] = None,
        event_bus: Optional["EventBus"] = None,
        queue_mode: bool = False,
        auto_resolve_timeout: int = 300,
    ) -> None:
        self.shared_state = shared_state
        self.event_bus = event_bus
        self.queue_mode = queue_mode
        self.auto_resolve_timeout = auto_resolve_timeout
        self._pending_requests: dict[str, ClarificationRequest] = {}
        self._request_counter = 0
        self._wait_event: Optional[asyncio.Event] = None
        self._queue: Optional["ClarificationQueue"] = None
        self.logger = logger.bind(component="ClarificationGate")

        # Initialize queue if in queue mode
        if queue_mode:
            self._init_queue()

    def _init_queue(self) -> None:
        """Initialize the clarification queue."""
        try:
            from src.mind.clarification_queue import ClarificationQueue
            self._queue = ClarificationQueue(
                auto_resolve_timeout=self.auto_resolve_timeout,
                use_defaults_on_timeout=True,
                event_bus=self.event_bus,
            )
            self.logger.info("clarification_queue_initialized")
        except ImportError:
            self.logger.warning("clarification_queue_import_failed")
            self._queue = None

    @property
    def queue(self) -> Optional["ClarificationQueue"]:
        """Get the clarification queue (None if not in queue mode)."""
        return self._queue

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self._request_counter += 1
        return f"CLAR-{self._request_counter:04d}"

    async def request_clarification(
        self,
        interpretation_sets: list[InterpretationSet],
        timeout_seconds: Optional[int] = None,
    ) -> ClarificationRequest:
        """
        Create a clarification request.

        In queue mode: Adds to queue non-blocking and returns immediately.
        In blocking mode: Pauses generation until user responds.

        Args:
            interpretation_sets: Sets of interpretations to choose from
            timeout_seconds: How long to wait for response

        Returns:
            The ClarificationRequest (check status for completion)
        """
        request_id = self._generate_request_id()
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

        request = ClarificationRequest(
            id=request_id,
            interpretation_sets=interpretation_sets,
            expires_at=datetime.fromtimestamp(
                datetime.now().timestamp() + timeout
            ),
        )

        self._pending_requests[request_id] = request

        self.logger.info(
            "clarification_requested",
            request_id=request_id,
            questions=request.total_questions,
            timeout_seconds=timeout,
            queue_mode=self.queue_mode,
        )

        # QUEUE MODE: Add to queue and return immediately (non-blocking)
        if self.queue_mode and self._queue:
            from src.mind.clarification_queue import ClarificationPriority

            for iset in interpretation_sets:
                # Determine priority based on ambiguity severity
                priority = ClarificationPriority.MEDIUM
                if iset.ambiguity.severity == "high":
                    priority = ClarificationPriority.HIGH
                elif iset.ambiguity.severity == "low":
                    priority = ClarificationPriority.LOW

                await self._queue.enqueue(
                    ambiguity=iset.ambiguity,
                    interpretations=iset.interpretations,
                    priority=priority,
                    timeout_seconds=timeout,
                )

            # Return immediately without blocking
            self.logger.info(
                "clarifications_queued",
                request_id=request_id,
                count=len(interpretation_sets),
                queue_size=self._queue.pending_count(),
            )
            return request

        # BLOCKING MODE: Pause generation and wait
        # Pause generation via SharedState
        if self.shared_state:
            await self.shared_state.pause_for_review()

        # Publish event for dashboard/API
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    type=EventType.REVIEW_PAUSE_REQUESTED,
                    source="ClarificationGate",
                    data={
                        "request_id": request_id,
                        "action": "clarification_needed",
                        "mode": "blocking",
                        "questions": [
                            {
                                "ambiguity_id": iset.ambiguity.id,
                                "description": iset.ambiguity.description,
                                "options": [
                                    {
                                        "id": interp.id,
                                        "label": interp.label,
                                        "description": interp.description,
                                        "is_recommended": interp.is_recommended,
                                    }
                                    for interp in iset.interpretations
                                ],
                            }
                            for iset in interpretation_sets
                        ],
                        "timeout_seconds": timeout,
                    },
                )
            )

        return request

    async def submit_choice(
        self,
        request_id: str,
        ambiguity_id: str,
        interpretation_id: str,
    ) -> bool:
        """
        Submit a user's choice for an ambiguity.

        Args:
            request_id: The clarification request ID
            ambiguity_id: Which ambiguity is being answered
            interpretation_id: The chosen interpretation

        Returns:
            True if submission was accepted
        """
        request = self._pending_requests.get(request_id)
        if not request:
            self.logger.warning("submit_unknown_request", request_id=request_id)
            return False

        if request.status in (ClarificationStatus.EXPIRED, ClarificationStatus.CANCELLED):
            self.logger.warning(
                "submit_to_closed_request",
                request_id=request_id,
                status=request.status.value,
            )
            return False

        # Find and validate the interpretation
        interpretation = None
        for iset in request.interpretation_sets:
            if iset.ambiguity.id == ambiguity_id:
                for interp in iset.interpretations:
                    if interp.id == interpretation_id:
                        interpretation = interp
                        break
                break

        if not interpretation:
            self.logger.warning(
                "invalid_interpretation",
                request_id=request_id,
                ambiguity_id=ambiguity_id,
                interpretation_id=interpretation_id,
            )
            return False

        # Record the choice
        request.responses[ambiguity_id] = interpretation_id
        request.selected_interpretations[ambiguity_id] = interpretation

        # Update status
        if request.is_complete:
            request.status = ClarificationStatus.COMPLETE
        else:
            request.status = ClarificationStatus.PARTIAL

        self.logger.info(
            "choice_submitted",
            request_id=request_id,
            ambiguity_id=ambiguity_id,
            interpretation_id=interpretation_id,
            remaining=request.total_questions - request.answered_questions,
        )

        # Publish event
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    type=EventType.REVIEW_FEEDBACK_SUBMITTED,
                    source="ClarificationGate",
                    data={
                        "request_id": request_id,
                        "ambiguity_id": ambiguity_id,
                        "interpretation_id": interpretation_id,
                        "interpretation_label": interpretation.label,
                        "is_complete": request.is_complete,
                        "remaining": request.total_questions - request.answered_questions,
                    },
                )
            )

        # If complete, signal to resume
        if request.is_complete:
            await self._complete_request(request)

        return True

    async def submit_all_choices(
        self,
        request_id: str,
        selections: dict[str, str],  # ambiguity_id -> interpretation_id
    ) -> bool:
        """
        Submit all choices at once.

        Args:
            request_id: The clarification request ID
            selections: Map of ambiguity_id to interpretation_id

        Returns:
            True if all submissions were accepted
        """
        success = True
        for ambiguity_id, interpretation_id in selections.items():
            result = await self.submit_choice(request_id, ambiguity_id, interpretation_id)
            if not result:
                success = False

        return success

    async def use_defaults(self, request_id: str) -> bool:
        """
        Use recommended defaults for all unanswered questions.

        Args:
            request_id: The clarification request ID

        Returns:
            True if defaults were applied
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False

        for iset in request.interpretation_sets:
            if iset.ambiguity.id not in request.responses:
                # Use recommended or first interpretation
                default_id = iset.recommended_id
                if not default_id and iset.interpretations:
                    default_id = iset.interpretations[0].id

                if default_id:
                    await self.submit_choice(request_id, iset.ambiguity.id, default_id)

        return True

    async def _complete_request(self, request: ClarificationRequest) -> None:
        """Handle completion of a clarification request."""
        self.logger.info(
            "clarification_complete",
            request_id=request.id,
            selections=len(request.selected_interpretations),
        )

        # Resume generation via SharedState
        if self.shared_state:
            # Build feedback context from selections
            feedback = self._build_feedback_context(request)
            await self.shared_state.resume_from_review(feedback)

        # Publish completion event
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    type=EventType.REVIEW_RESUMED,
                    source="ClarificationGate",
                    data={
                        "request_id": request.id,
                        "action": "clarification_resolved",
                        "selections": {
                            amb_id: {
                                "interpretation_id": interp.id,
                                "label": interp.label,
                                "technical_approach": interp.technical_approach,
                            }
                            for amb_id, interp in request.selected_interpretations.items()
                        },
                    },
                )
            )

        # Signal any waiting coroutines
        if self._wait_event:
            self._wait_event.set()

    def _build_feedback_context(self, request: ClarificationRequest) -> str:
        """Build feedback context string from selections."""
        lines = ["## Clarification Decisions\n"]

        for amb_id, interp in request.selected_interpretations.items():
            # Find the original ambiguity
            ambiguity = None
            for iset in request.interpretation_sets:
                if iset.ambiguity.id == amb_id:
                    ambiguity = iset.ambiguity
                    break

            if ambiguity:
                lines.append(f"### {ambiguity.detected_term}")
                lines.append(f"- Decision: {interp.label}")
                lines.append(f"- Approach: {interp.technical_approach}")
                lines.append("")

        return "\n".join(lines)

    async def wait_for_completion(
        self,
        request_id: str,
        timeout_seconds: Optional[int] = None,
    ) -> ClarificationRequest:
        """
        Wait for a clarification request to complete.

        Args:
            request_id: The request to wait for
            timeout_seconds: How long to wait

        Returns:
            The completed ClarificationRequest
        """
        request = self._pending_requests.get(request_id)
        if not request:
            raise ValueError(f"Unknown request ID: {request_id}")

        if request.is_complete:
            return request

        self._wait_event = asyncio.Event()
        timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

        try:
            await asyncio.wait_for(self._wait_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            request.status = ClarificationStatus.EXPIRED
            self.logger.warning("clarification_timeout", request_id=request_id)

        return request

    def cancel_request(self, request_id: str) -> bool:
        """Cancel a pending clarification request."""
        request = self._pending_requests.get(request_id)
        if not request:
            return False

        request.status = ClarificationStatus.CANCELLED

        self.logger.info("clarification_cancelled", request_id=request_id)

        # Signal waiting coroutines
        if self._wait_event:
            self._wait_event.set()

        return True

    def get_request(self, request_id: str) -> Optional[ClarificationRequest]:
        """Get a clarification request by ID."""
        return self._pending_requests.get(request_id)

    def get_pending_requests(self) -> list[ClarificationRequest]:
        """Get all pending clarification requests."""
        return [
            r
            for r in self._pending_requests.values()
            if r.status in (ClarificationStatus.PENDING, ClarificationStatus.PARTIAL)
        ]

    def get_selected_interpretations(
        self,
        request_id: str,
    ) -> dict[str, Interpretation]:
        """Get the selected interpretations for a completed request."""
        request = self._pending_requests.get(request_id)
        if request:
            return request.selected_interpretations
        return {}

    def get_statistics(self) -> dict:
        """Get clarification gate statistics."""
        total = len(self._pending_requests)
        by_status = {}
        for request in self._pending_requests.values():
            status = request.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_requests": total,
            "by_status": by_status,
            "pending_count": len(self.get_pending_requests()),
        }

    def reset(self) -> None:
        """Reset clarification gate state."""
        count = len(self._pending_requests)
        self._pending_requests.clear()
        self._request_counter = 0

        # Also reset queue if in queue mode
        if self._queue:
            self._queue.clear()

        self.logger.info("clarification_gate_reset", cleared_requests=count)

    # =========================================================================
    # Queue Mode Methods
    # =========================================================================

    def get_pending_from_queue(self) -> list[dict]:
        """
        Get all pending clarifications from the queue.

        Returns:
            List of clarification dicts for API/dashboard
        """
        if not self._queue:
            return []
        return [c.to_dict() for c in self._queue.get_pending()]

    def get_queue_statistics(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Statistics dict with counts and breakdowns
        """
        if not self._queue:
            return {
                "queue_mode": False,
                "total": 0,
                "pending": 0,
            }

        stats = self._queue.get_statistics()
        stats["queue_mode"] = True
        return stats

    async def resolve_from_queue(
        self,
        clarification_id: str,
        interpretation_id: str,
    ) -> bool:
        """
        Resolve a clarification in the queue.

        Args:
            clarification_id: The CLARQ-XXXX ID
            interpretation_id: The chosen interpretation

        Returns:
            True if resolved successfully
        """
        if not self._queue:
            return False
        return await self._queue.resolve(clarification_id, interpretation_id)

    async def resolve_all_defaults_from_queue(self) -> int:
        """
        Resolve all pending queue items with defaults.

        Returns:
            Number of items resolved
        """
        if not self._queue:
            return 0
        return await self._queue.resolve_all_with_defaults()

    def get_queue_resolution(self, ambiguity_id: str) -> Optional[Interpretation]:
        """
        Get the resolved interpretation for an ambiguity from queue.

        Args:
            ambiguity_id: The ambiguity to check

        Returns:
            Resolved Interpretation or None
        """
        if not self._queue:
            return None
        return self._queue.get_resolved_interpretation(ambiguity_id)

    def is_queue_resolved(self, ambiguity_id: str) -> bool:
        """Check if an ambiguity has been resolved in the queue."""
        if not self._queue:
            return False
        return self._queue.is_resolved(ambiguity_id)

    async def stop_queue(self) -> None:
        """Stop the queue and cleanup background tasks."""
        if self._queue:
            await self._queue.stop()
