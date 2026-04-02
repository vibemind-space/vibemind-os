"""
Event Interpreter Agent - Triage agent for intelligent event routing.

Implements the AutoGen Handoffs pattern for Phase 3 of Society of Mind.
Acts as a central hub that receives ALL events and delegates to specialists.

Reference: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/design-patterns/handoffs.html

Key responsibilities:
- Receive all events from EventBus
- Use LLM to make intelligent routing decisions
- Delegate to specialist agents with full context
- Handle responses from specialists
- Prevent conflicts and prioritize critical events
- Skill-aware routing (considers skills that match event types)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable, TYPE_CHECKING
import structlog
import json

if TYPE_CHECKING:
    from ..skills.registry import SkillRegistry

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..mind.message_protocols import (
    TopicType,
    EventTask,
    AgentResponse,
    HandoffRequest,
    RoutingDecision,
    get_default_routing,
    get_event_priority,
)

logger = structlog.get_logger(__name__)


# Delegate tool functions - return target topic for handoff
def transfer_to_generator() -> str:
    """Delegate to GeneratorAgent for code fixes and generation."""
    return TopicType.GENERATOR.value


def transfer_to_tester() -> str:
    """Delegate to TesterTeamAgent for test execution."""
    return TopicType.TESTER.value


def transfer_to_validator() -> str:
    """Delegate to ValidationTeamAgent for test generation."""
    return TopicType.VALIDATOR.value


def transfer_to_deployer() -> str:
    """Delegate to DeploymentTeamAgent for sandbox deployment."""
    return TopicType.DEPLOYER.value


def transfer_to_debugger() -> str:
    """Delegate to ContinuousDebugAgent for error analysis."""
    return TopicType.DEBUGGER.value


def transfer_to_ux_reviewer() -> str:
    """Delegate to UXDesignAgent for UI/UX review."""
    return TopicType.UX_REVIEWER.value


def escalate_to_human() -> str:
    """Escalate to human when conflict cannot be resolved."""
    return TopicType.HUMAN.value


@dataclass
class DelegateTool:
    """Definition of a delegate tool for handoffs."""
    name: str
    function: Callable[[], str]
    description: str
    event_types: list[str]  # Which event types this tool handles


# Define all delegate tools
DELEGATE_TOOLS = [
    DelegateTool(
        name="transfer_to_generator",
        function=transfer_to_generator,
        description="Use for code fixes, generation, refactoring. Handles: BUILD_FAILED, CODE_FIX_NEEDED, TYPE_ERROR, E2E_TEST_FAILED, UX_ISSUE_FOUND, VERIFICATION_FAILED",
        event_types=["build_failed", "code_fix_needed", "type_error", "e2e_test_failed", "ux_issue_found", "verification_failed"],
    ),
    DelegateTool(
        name="transfer_to_tester",
        function=transfer_to_tester,
        description="Use for test execution, E2E tests. Handles: BUILD_SUCCEEDED (after deploy), APP_LAUNCHED, E2E_TEST_STARTED",
        event_types=["app_launched", "e2e_test_started", "tests_running"],
    ),
    DelegateTool(
        name="transfer_to_validator",
        function=transfer_to_validator,
        description="Use for test generation, validation loops. Handles: GENERATION_COMPLETE, BUILD_SUCCEEDED (for type checking)",
        event_types=["generation_complete", "code_generated"],
    ),
    DelegateTool(
        name="transfer_to_deployer",
        function=transfer_to_deployer,
        description="Use for sandbox deployment, VNC streaming. Handles: BUILD_SUCCEEDED, CODE_FIXED",
        event_types=["build_succeeded", "code_fixed"],
    ),
    DelegateTool(
        name="transfer_to_debugger",
        function=transfer_to_debugger,
        description="Use for error analysis, file sync, container debugging. Handles: SANDBOX_TEST_FAILED, BUILD_FAILED (complex), APP_CRASHED",
        event_types=["sandbox_test_failed", "app_crashed", "runtime_test_failed"],
    ),
    DelegateTool(
        name="transfer_to_ux_reviewer",
        function=transfer_to_ux_reviewer,
        description="Use for UI/UX review from screenshots. Handles: E2E_SCREENSHOT_TAKEN, SCREEN_STREAM_READY",
        event_types=["e2e_screenshot_taken", "screen_stream_ready"],
    ),
    DelegateTool(
        name="escalate_to_human",
        function=escalate_to_human,
        description="Only use when multiple agents conflict, error is unresolvable, or explicit human intervention is needed",
        event_types=[],
    ),
]


# Build tool lookup map
TOOL_BY_NAME = {tool.name: tool for tool in DELEGATE_TOOLS}


class EventInterpreterAgent:
    """
    Triage Agent that interprets events and delegates to specialists.

    Uses LLM-based routing when available, with fallback to rule-based routing.
    Implements the AutoGen Handoffs pattern for intelligent task delegation.

    Key features:
    - Receives ALL events from EventBus (wildcard subscription)
    - Makes intelligent routing decisions based on event type, data, and system state
    - Preserves conversation context across handoffs
    - Prioritizes critical events (BUILD_FAILED > TEST_FAILED > UX_ISSUE)
    - Prevents conflicts by serializing delegate tasks
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        use_llm_routing: bool = True,
        llm_client: Optional[Any] = None,
        skill_registry: Optional["SkillRegistry"] = None,
    ):
        """
        Initialize the Event Interpreter.

        Args:
            event_bus: EventBus for receiving events and publishing handoffs
            shared_state: SharedState for system metrics
            working_dir: Working directory for file operations
            use_llm_routing: Whether to use LLM for routing decisions (default: True)
            llm_client: Optional LLM client for intelligent routing
            skill_registry: Optional SkillRegistry for skill-aware routing
        """
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.working_dir = working_dir
        self.use_llm_routing = use_llm_routing
        self.llm_client = llm_client
        self.skill_registry = skill_registry

        # Context tracking for handoffs
        self._context: list[dict] = []
        self._max_context_size = 50  # Keep last 50 messages

        # Active handoffs tracking
        self._active_handoffs: dict[str, EventTask] = {}
        self._handoff_lock = asyncio.Lock()

        # Specialist agent callbacks
        self._specialist_handlers: dict[str, Callable] = {}

        # Event queue for prioritization
        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

        # Running state
        self._should_stop = False
        self._task: Optional[asyncio.Task] = None

        self.logger = logger.bind(agent="EventInterpreter")

        # Subscribe to all events
        self.event_bus.subscribe_all(self._on_event)

    def register_specialist(self, topic: str, handler: Callable[[EventTask], Any]) -> None:
        """
        Register a specialist agent's handler for receiving delegated tasks.

        Args:
            topic: The topic type (e.g., TopicType.GENERATOR.value)
            handler: Async function that accepts EventTask and returns AgentResponse
        """
        self._specialist_handlers[topic] = handler
        self.logger.info("specialist_registered", topic=topic)

    def _on_event(self, event: Event) -> None:
        """
        Handle incoming events from EventBus.

        Called for every event (wildcard subscription).
        Adds events to priority queue for processing.
        """
        # Don't process our own events
        if event.source == "EventInterpreter":
            return

        # Get event priority
        priority = get_event_priority(event.type.value)

        # Add to priority queue (lower number = higher priority)
        try:
            self._event_queue.put_nowait((priority, datetime.now().timestamp(), event))
        except asyncio.QueueFull:
            self.logger.warning("event_queue_full", event_type=event.type.value)

    async def _process_events(self) -> None:
        """Main loop for processing events from priority queue."""
        self.logger.info("event_processor_started")

        while not self._should_stop:
            try:
                # Wait for next event (with timeout to check stop flag)
                try:
                    priority, timestamp, event = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Process the event
                await self._handle_event(event)

            except Exception as e:
                self.logger.error("event_processing_error", error=str(e))

        self.logger.info("event_processor_stopped")

    async def _handle_event(self, event: Event) -> None:
        """
        Process a single event and route to appropriate specialist.

        Args:
            event: The event to process
        """
        self.logger.debug(
            "handling_event",
            event_type=event.type.value,
            source=event.source,
        )

        # Make routing decision
        if self.use_llm_routing and self.llm_client:
            decision = await self._llm_route(event)
        else:
            decision = self._rule_based_route(event)

        if not decision:
            self.logger.debug("no_routing_decision", event_type=event.type.value)
            return

        # Log decision
        self.logger.info(
            "routing_decision",
            event_type=event.type.value,
            target=decision.target_agent,
            confidence=decision.confidence,
            priority=decision.priority,
        )

        # Add to context
        self._add_to_context({
            "role": "event",
            "event_type": event.type.value,
            "source": event.source,
            "data": event.data,
            "routing": decision.target_agent,
        })

        # Create EventTask with full context
        task = EventTask.from_event(
            event=event,
            context=self._context.copy(),
            shared_state=self.shared_state.to_dict() if hasattr(self.shared_state, 'to_dict') else {},
        )
        task.handoff_from = "EventInterpreter"
        task.handoff_reason = decision.reasoning
        task.priority = decision.priority

        # SKILL INTEGRATION: Enhance task with relevant skill context
        task = self.enhance_task_with_skill(task, event)

        # Log skill info if available
        skills = self.get_skills_for_event(event)
        if skills:
            self.logger.debug(
                "skills_matched_for_event",
                event_type=event.type.value,
                skills=[s.name for s in skills],
            )

        # Delegate to specialist
        await self._delegate_task(decision.target_agent, task)

    def _rule_based_route(self, event: Event) -> Optional[RoutingDecision]:
        """
        Make routing decision using rule-based logic (fallback).

        Args:
            event: The event to route

        Returns:
            RoutingDecision or None if event should not be routed
        """
        event_type = event.type.value.lower()

        # Check default routing map
        default_target = get_default_routing(event_type)

        if default_target:
            return RoutingDecision(
                event_type=event_type,
                target_agent=default_target.value,
                confidence=0.9,
                reasoning=f"Rule-based routing for {event_type}",
                priority=get_event_priority(event_type),
            )

        # Custom routing rules
        if event_type in ["build_failed", "type_error", "validation_error"]:
            return RoutingDecision(
                event_type=event_type,
                target_agent=TopicType.GENERATOR.value,
                confidence=0.95,
                reasoning="Error event routed to Generator for fixing",
                priority=get_event_priority(event_type),
            )

        if event_type == "build_succeeded":
            return RoutingDecision(
                event_type=event_type,
                target_agent=TopicType.DEPLOYER.value,
                confidence=0.9,
                reasoning="Build success routed to Deployer for sandbox testing",
                priority=get_event_priority(event_type),
            )

        if event_type in ["e2e_test_failed", "ux_issue_found"]:
            return RoutingDecision(
                event_type=event_type,
                target_agent=TopicType.GENERATOR.value,
                confidence=0.9,
                reasoning="E2E/UX issue routed to Generator for fixing",
                priority=get_event_priority(event_type),
            )

        if event_type == "generation_complete":
            return RoutingDecision(
                event_type=event_type,
                target_agent=TopicType.VALIDATOR.value,
                confidence=0.9,
                reasoning="Generation complete routed to Validator",
                priority=get_event_priority(event_type),
            )

        # Events that don't need routing
        skip_events = [
            "agent_started", "agent_completed", "agent_acting",
            "convergence_update", "system_ready", "cli_stats_updated",
            "file_created", "file_modified",  # These trigger Builder directly
        ]
        if event_type in skip_events:
            return None

        # Unknown event - log but don't route
        self.logger.debug("unknown_event_type", event_type=event_type)
        return None

    async def _llm_route(self, event: Event) -> Optional[RoutingDecision]:
        """
        Make routing decision using LLM (intelligent routing).

        Args:
            event: The event to route

        Returns:
            RoutingDecision or None
        """
        if not self.llm_client:
            return self._rule_based_route(event)

        # Build prompt for LLM
        prompt = self._build_routing_prompt(event)

        try:
            # Call LLM for routing decision
            response = await self.llm_client.create(
                messages=[
                    {"role": "system", "content": self._get_system_message()},
                    {"role": "user", "content": prompt},
                ],
                tools=self._get_tool_definitions(),
            )

            # Parse LLM response
            if hasattr(response, 'content') and response.content:
                # Look for tool call in response
                for item in response.content if isinstance(response.content, list) else [response.content]:
                    if hasattr(item, 'name') and item.name in TOOL_BY_NAME:
                        tool = TOOL_BY_NAME[item.name]
                        target = tool.function()
                        return RoutingDecision(
                            event_type=event.type.value,
                            target_agent=target,
                            confidence=0.95,
                            reasoning=f"LLM selected {item.name}",
                            priority=get_event_priority(event.type.value),
                        )

            # Fallback to rule-based if LLM didn't make a decision
            return self._rule_based_route(event)

        except Exception as e:
            self.logger.error("llm_routing_error", error=str(e))
            return self._rule_based_route(event)

    def _get_system_message(self) -> str:
        """Get the system message for LLM routing."""
        return """Du bist der Event Interpreter für das Society of Mind Code-Generierungssystem.

Deine Aufgabe:
1. Analysiere eingehende Events aus dem Event-Stream
2. Entscheide welcher Spezialist das Event bearbeiten soll
3. Priorisiere kritische Fehler (BUILD_FAILED > TEST_FAILED > UX_ISSUE)
4. Vermeide parallele Aktionen auf denselben Dateien
5. Behalte den Kontext über mehrere Events hinweg

Routing-Regeln:
- BUILD_FAILED, CODE_FIX_NEEDED, TYPE_ERROR → transfer_to_generator()
- E2E_TEST_FAILED, UX_ISSUE_FOUND → transfer_to_generator() (mit Screenshot-Context)
- BUILD_SUCCEEDED → transfer_to_deployer()
- SANDBOX_TEST_FAILED → transfer_to_debugger()
- GENERATION_COMPLETE → transfer_to_validator()
- E2E_SCREENSHOT_TAKEN → transfer_to_ux_reviewer()

Bei Konflikten:
- Wenn Generator bereits aktiv ist, warte bis fertig
- Wenn kritischer Fehler während anderer Aktion, unterbreche nicht-kritische
- Bei unlösbaren Konflikten: escalate_to_human()

Wähle GENAU EIN Tool aus um das Event zu routen."""

    def _build_routing_prompt(self, event: Event) -> str:
        """Build prompt for LLM routing decision."""
        # Get current system state
        metrics = {}
        if hasattr(self.shared_state, 'metrics'):
            m = self.shared_state.metrics
            metrics = {
                "build_success": getattr(m, 'build_success', False),
                "type_errors": getattr(m, 'type_error_count', 0),
                "test_pass_rate": getattr(m, 'test_pass_rate', 0),
            }

        # Get skill context for this event
        skill_context = self.get_skill_context_for_event(event)

        prompt = f"""Neues Event empfangen:
- Typ: {event.type.value}
- Source: {event.source}
- Daten: {json.dumps(event.data, default=str)}
- Erfolg: {event.success}
- Fehlermeldung: {event.error_message or 'None'}

Aktueller System-Status:
{json.dumps(metrics, default=str)}

Aktive Handoffs: {len(self._active_handoffs)}
"""

        # Add skill context if available
        if skill_context:
            prompt += f"""
{skill_context}
"""

        prompt += """
Entscheide: Welcher Spezialist soll dieses Event bearbeiten? Wähle ein Tool."""

        return prompt

    def _get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": {}, "required": []},
                }
            }
            for tool in DELEGATE_TOOLS
        ]

    async def _delegate_task(self, target: str, task: EventTask) -> None:
        """
        Delegate a task to a specialist agent.

        Args:
            target: Target topic/agent
            task: The EventTask to delegate
        """
        async with self._handoff_lock:
            # Check if there's already an active handoff to this target
            if target in self._active_handoffs:
                self.logger.debug(
                    "queuing_handoff",
                    target=target,
                    event_type=task.event_type,
                )
                # Queue will be processed when current handoff completes
                return

            # Mark as active
            self._active_handoffs[target] = task

        # Get specialist handler
        handler = self._specialist_handlers.get(target)

        if handler:
            try:
                # Call specialist handler
                response = await handler(task)

                # Process response
                if response:
                    await self._handle_specialist_response(response)

            except Exception as e:
                self.logger.error(
                    "specialist_error",
                    target=target,
                    error=str(e),
                )
            finally:
                # Clear active handoff
                async with self._handoff_lock:
                    self._active_handoffs.pop(target, None)
        else:
            self.logger.warning(
                "no_specialist_handler",
                target=target,
                event_type=task.event_type,
            )
            # Clear active handoff since we can't process it
            async with self._handoff_lock:
                self._active_handoffs.pop(target, None)

    async def _handle_specialist_response(self, response: AgentResponse) -> None:
        """
        Handle response from a specialist agent.

        Args:
            response: The AgentResponse from the specialist
        """
        # Add to context
        self._add_to_context({
            "role": "specialist_response",
            "from": response.reply_from_topic,
            "success": response.success,
            "result": response.result,
        })

        self.logger.info(
            "specialist_completed",
            from_topic=response.reply_from_topic,
            success=response.success,
        )

        # Check if follow-up needed
        if response.needs_followup and response.followup_event_type:
            # Create follow-up event
            followup_event = Event(
                type=EventType(response.followup_event_type) if response.followup_event_type in [e.value for e in EventType] else EventType.SYSTEM_READY,
                source=response.reply_from_topic,
                data=response.followup_data,
            )
            # Re-route the follow-up
            await self._handle_event(followup_event)

        # If specialist suggested next agent, route there
        if response.suggested_next_agent:
            # Create continuation task
            task = EventTask(
                event_type="continuation",
                event_source=response.reply_from_topic,
                event_data=response.result,
                context=response.context,
                shared_state=self.shared_state.to_dict() if hasattr(self.shared_state, 'to_dict') else {},
            )
            await self._delegate_task(response.suggested_next_agent, task)

    def _add_to_context(self, message: dict) -> None:
        """Add a message to conversation context."""
        message["timestamp"] = datetime.now().isoformat()
        self._context.append(message)

        # Trim context if too large
        if len(self._context) > self._max_context_size:
            self._context = self._context[-self._max_context_size:]

    async def start(self) -> None:
        """Start the Event Interpreter."""
        if self._task and not self._task.done():
            self.logger.warning("already_running")
            return

        self._should_stop = False
        self._task = asyncio.create_task(self._process_events())
        self.logger.info("started")

    async def stop(self) -> None:
        """Stop the Event Interpreter."""
        self._should_stop = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self.logger.info("stopped")

    def get_status(self) -> dict:
        """Get current status of the Event Interpreter."""
        return {
            "running": self._task is not None and not self._task.done(),
            "active_handoffs": list(self._active_handoffs.keys()),
            "queue_size": self._event_queue.qsize(),
            "context_size": len(self._context),
            "use_llm_routing": self.use_llm_routing,
            "has_skill_registry": self.skill_registry is not None,
        }

    # =========================================================================
    # SKILL INTEGRATION - Event-to-Skill Mapping
    # =========================================================================

    def get_skills_for_event(self, event: Event) -> list:
        """
        Get all skills that should trigger for this event type.

        Uses the SkillRegistry to find skills whose trigger_events
        match the incoming event type.

        Args:
            event: The event to find matching skills for

        Returns:
            List of Skill objects that match this event
        """
        if not self.skill_registry:
            return []

        try:
            return self.skill_registry.get_skills_for_event(event.type)
        except Exception as e:
            self.logger.debug("skill_lookup_failed", error=str(e))
            return []

    def get_skill_context_for_event(self, event: Event) -> str:
        """
        Get skill metadata for inclusion in routing context.

        Returns a brief summary of relevant skills for this event,
        using minimal tokens (metadata only, not full instructions).

        Args:
            event: The event to get skill context for

        Returns:
            Formatted skill metadata string
        """
        skills = self.get_skills_for_event(event)
        if not skills:
            return ""

        parts = ["## Relevant Skills for this Event"]
        for skill in skills:
            parts.append(skill.get_metadata_prompt())

        return "\n".join(parts)

    def enhance_task_with_skill(self, task: EventTask, event: Event) -> EventTask:
        """
        Enhance an EventTask with skill information.

        Adds skill metadata to the task's context for the specialist
        agent to use when processing.

        Args:
            task: The EventTask to enhance
            event: The original event

        Returns:
            Enhanced EventTask with skill context
        """
        skill_context = self.get_skill_context_for_event(event)
        if skill_context:
            task.skill_context = skill_context
            # Also add to the task's context list
            self._add_to_context({
                "role": "skill_context",
                "event_type": event.type.value,
                "skills": [s.name for s in self.get_skills_for_event(event)],
            })

        return task
