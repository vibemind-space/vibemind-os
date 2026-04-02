"""
Message Types for Handoff Pattern

Core message types that enable agent communication:
- UserTask: Contains context and task; published when agents hand off
- AgentResponse: Sent by agents with results
- HandoffRequest: Explicit handoff to another agent
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


@dataclass
class Message:
    """Base message class."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""
    source_agent: str = ""


@dataclass
class UserTask(Message):
    """
    Task message containing context and instructions.
    Published when agents hand off tasks to each other.
    """
    goal: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    total_steps: int = 0

    # Screen state for vision-related tasks
    screenshot_base64: Optional[str] = None
    ocr_results: Optional[List[Dict]] = None
    detected_elements: Optional[List[Dict]] = None

    # Action context
    pending_actions: List[Dict] = field(default_factory=list)
    completed_actions: List[Dict] = field(default_factory=list)

    def add_to_history(self, agent: str, action: str, result: Any):
        """Add an entry to the conversation history."""
        self.history.append({
            "agent": agent,
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })


@dataclass
class AgentResponse(Message):
    """
    Response from an agent with execution results.
    """
    success: bool = False
    result: Any = None
    error: Optional[str] = None
    next_agent: Optional[str] = None  # For handoff
    updated_context: Dict[str, Any] = field(default_factory=dict)

    # Metrics
    execution_time_ms: float = 0.0
    confidence: float = 1.0


@dataclass
class HandoffRequest(Message):
    """
    Explicit request to transfer control to another agent.
    """
    target_agent: str = ""
    reason: str = ""
    task: Optional[UserTask] = None
    priority: int = 0  # Higher = more urgent

    # Handoff metadata
    handoff_count: int = 0  # How many times this task has been handed off
    max_handoffs: int = 5  # Prevent infinite loops


@dataclass
class ProgressUpdate(Message):
    """
    Progress update from an agent.
    """
    agent_name: str = ""
    progress_percentage: float = 0.0
    current_action: str = ""
    blockers: List[str] = field(default_factory=list)
    suggestions: List[Dict] = field(default_factory=list)


@dataclass
class RecoveryRequest(Message):
    """
    Request for recovery agent to handle a failure.
    """
    failed_action: Dict = field(default_factory=dict)
    error_message: str = ""
    retry_count: int = 0
    screen_state: Optional[Dict] = None
    suggested_recovery: Optional[str] = None
