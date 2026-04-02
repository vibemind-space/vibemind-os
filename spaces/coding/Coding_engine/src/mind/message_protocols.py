"""
Message Protocols for Handoffs Pattern.

Defines the data structures used for communication between the Event Interpreter
(Triage Agent) and specialist agents using the AutoGen Handoffs pattern.

References:
- https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/design-patterns/handoffs.html
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum


class TopicType(str, Enum):
    """Topic types for agent communication (Handoffs routing)."""

    # Triage Agent (Event Interpreter)
    EVENT_INTERPRETER = "EventInterpreter"

    # Specialist Agents
    GENERATOR = "GeneratorAgent"
    TESTER = "TesterTeamAgent"
    VALIDATOR = "ValidationTeamAgent"
    DEPLOYER = "DeploymentTeamAgent"
    DEBUGGER = "ContinuousDebugAgent"
    UX_REVIEWER = "UXDesignAgent"

    # Backend Specialist Agents
    DATABASE = "DatabaseAgent"
    API = "APIAgent"
    AUTH = "AuthAgent"
    INFRASTRUCTURE = "InfrastructureAgent"

    # Special agents
    HUMAN = "HumanAgent"


@dataclass
class EventTask:
    """
    Task containing an event and conversation context.

    Passed from Event Interpreter to specialist agents.
    Contains full context for intelligent handling.
    """
    # The original event from EventBus
    event_type: str
    event_source: str
    event_data: dict
    event_timestamp: datetime = field(default_factory=datetime.now)

    # Conversation context (LLM message history)
    context: list = field(default_factory=list)

    # Current system state
    shared_state: dict = field(default_factory=dict)

    # Handoff metadata
    handoff_from: Optional[str] = None
    handoff_reason: Optional[str] = None
    priority: int = 5  # 1 = highest, 10 = lowest

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "event_source": self.event_source,
            "event_data": self.event_data,
            "event_timestamp": self.event_timestamp.isoformat() if self.event_timestamp else None,
            "context": self.context,
            "shared_state": self.shared_state,
            "handoff_from": self.handoff_from,
            "handoff_reason": self.handoff_reason,
            "priority": self.priority,
        }

    @classmethod
    def from_event(cls, event: Any, context: list = None, shared_state: dict = None) -> "EventTask":
        """Create an EventTask from an Event object."""
        return cls(
            event_type=event.type.value if hasattr(event.type, 'value') else str(event.type),
            event_source=event.source,
            event_data=event.data if hasattr(event, 'data') else {},
            event_timestamp=event.timestamp if hasattr(event, 'timestamp') else datetime.now(),
            context=context or [],
            shared_state=shared_state or {},
        )


@dataclass
class AgentResponse:
    """
    Response from a specialist agent back to Event Interpreter.

    Contains results and updated context for next routing decision.
    """
    # Which agent is responding
    reply_from_topic: str

    # Updated conversation context
    context: list = field(default_factory=list)

    # Result of the agent's work
    result: dict = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None

    # Follow-up indicators
    needs_followup: bool = False
    followup_event_type: Optional[str] = None
    followup_data: dict = field(default_factory=dict)

    # Which agent should handle next (if known)
    suggested_next_agent: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "reply_from_topic": self.reply_from_topic,
            "context": self.context,
            "result": self.result,
            "success": self.success,
            "error_message": self.error_message,
            "needs_followup": self.needs_followup,
            "followup_event_type": self.followup_event_type,
            "followup_data": self.followup_data,
            "suggested_next_agent": self.suggested_next_agent,
        }


@dataclass
class HandoffRequest:
    """
    Request to hand off control from one agent to another.

    Used by Event Interpreter to delegate tasks.
    """
    target_topic: str
    task: EventTask
    reason: str
    urgent: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "target_topic": self.target_topic,
            "task": self.task.to_dict(),
            "reason": self.reason,
            "urgent": self.urgent,
        }


@dataclass
class RoutingDecision:
    """
    Decision made by Event Interpreter about routing.

    Contains reasoning and target agent selection.
    """
    event_type: str
    target_agent: str
    confidence: float  # 0.0 to 1.0
    reasoning: str
    priority: int  # 1 = highest priority
    alternatives: list = field(default_factory=list)  # Other possible agents

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "target_agent": self.target_agent,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "priority": self.priority,
            "alternatives": self.alternatives,
        }


# Mapping of event types to suggested specialist agents
DEFAULT_ROUTING_MAP = {
    # Build/Code errors -> Generator
    "build_failed": TopicType.GENERATOR,
    "code_fix_needed": TopicType.GENERATOR,
    "type_error": TopicType.GENERATOR,
    "validation_error": TopicType.GENERATOR,

    # Mock violations -> Generator (for auto-fix)
    "mock_detected": TopicType.GENERATOR,
    "mock_replacement_needed": TopicType.GENERATOR,

    # E2E/UX issues -> Generator (with visual context)
    "e2e_test_failed": TopicType.GENERATOR,
    "ux_issue_found": TopicType.GENERATOR,
    "playwright_e2e_failed": TopicType.GENERATOR,

    # Build success -> Deploy then Test
    "build_succeeded": TopicType.DEPLOYER,
    "code_fixed": TopicType.DEPLOYER,

    # Test events -> Tester
    "test_failed": TopicType.TESTER,
    "app_launched": TopicType.TESTER,

    # Generation complete -> Validator
    "generation_complete": TopicType.VALIDATOR,

    # Sandbox issues -> Debugger
    "sandbox_test_failed": TopicType.DEBUGGER,
    "runtime_test_failed": TopicType.DEBUGGER,
    "app_crashed": TopicType.DEBUGGER,

    # UX review -> UX Reviewer
    "e2e_screenshot_taken": TopicType.UX_REVIEWER,

    # Backend: Contracts -> Database Agent
    "contracts_generated": TopicType.DATABASE,
    "schema_update_needed": TopicType.DATABASE,
    "database_migration_needed": TopicType.DATABASE,

    # Backend: Database Schema -> API Agent
    "database_schema_generated": TopicType.API,
    "api_update_needed": TopicType.API,
    "api_endpoint_failed": TopicType.API,

    # Backend: API Routes -> Auth Agent
    "api_routes_generated": TopicType.AUTH,
    "auth_required": TopicType.AUTH,
    "role_definition_needed": TopicType.AUTH,
    "auth_config_updated": TopicType.AUTH,

    # Backend: Infrastructure events
    "auth_setup_complete": TopicType.INFRASTRUCTURE,
    "env_config_needed": TopicType.INFRASTRUCTURE,
    "docker_setup_needed": TopicType.INFRASTRUCTURE,
}


def get_default_routing(event_type: str) -> Optional[TopicType]:
    """
    Get the default agent for a given event type.

    This is used as a fallback when LLM doesn't make a decision.
    """
    # Normalize event type
    event_type_lower = event_type.lower()

    return DEFAULT_ROUTING_MAP.get(event_type_lower)


# Priority levels for different event types
EVENT_PRIORITY = {
    # Critical (Priority 1-2)
    "build_failed": 1,
    "app_crashed": 1,
    "system_error": 1,
    "mock_detected": 2,  # Mocks block build

    # High (Priority 3-4)
    "type_error": 3,
    "test_failed": 3,
    "sandbox_test_failed": 3,
    "e2e_test_failed": 4,
    "api_endpoint_failed": 3,
    "database_schema_failed": 3,
    "auth_setup_failed": 3,

    # Medium (Priority 5-6)
    "code_fix_needed": 5,
    "validation_error": 5,
    "build_succeeded": 5,
    "generation_complete": 5,
    "contracts_generated": 5,  # Triggers backend chain
    "database_schema_generated": 5,
    "api_routes_generated": 5,
    "auth_setup_complete": 5,

    # Low (Priority 7-8)
    "ux_issue_found": 7,
    "code_fixed": 7,
    "test_passed": 8,
    "mock_replaced": 7,
    "env_config_generated": 7,
    "docker_compose_ready": 7,

    # Informational (Priority 9-10)
    "agent_started": 9,
    "convergence_update": 10,
}


def get_event_priority(event_type: str) -> int:
    """Get the priority level for an event type (1 = highest)."""
    event_type_lower = event_type.lower()
    return EVENT_PRIORITY.get(event_type_lower, 5)  # Default to medium priority
