"""
Handoff-based Multi-Agent System

Implements AutoGen's handoff pattern for agent coordination.
Agents delegate tasks to specialized colleagues using dedicated tool calls.

Based on: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/design-patterns/handoffs.html
"""

from .messages import (
    UserTask,
    AgentResponse,
    HandoffRequest,
    ProgressUpdate,
    RecoveryRequest
)
from .base_agent import BaseHandoffAgent, AgentConfig, Tool
from .runtime import AgentRuntime, Session
from .tools import (
    DelegateTool,
    ActionTool,
    create_delegate_tool,
    create_action_tool,
    ToolRegistry,
    get_tool_registry,
    transfer_to_execution,
    transfer_to_vision,
    transfer_to_recovery,
    transfer_to_orchestrator
)
from .execution_agent import ExecutionAgent
from .vision_handoff_agent import VisionHandoffAgent
from .orchestrator_agent import OrchestratorAgent, RecoveryAgent
from .claude_desktop_bridge import (
    ClaudeDesktopBridge,
    ClaudeDesktopReport,
    ReportType,
    ReportParser,
    EventStream,
    get_project_instructions
)

# Society of Mind - Team Agents
from .team_agent import (
    TeamAgent,
    TeamConfig,
    SubAgentResult,
    SynthesisStrategy
)
from .planning_team import (
    PlanningTeam,
    PlannerAgent,
    CriticAgent
)
from .validation_team import (
    ValidationTeam,
    ElementFinderAgent,
    ScreenStateValidator,
    ChangeDetector
)

__all__ = [
    # Messages
    'UserTask',
    'AgentResponse',
    'HandoffRequest',
    'ProgressUpdate',
    'RecoveryRequest',

    # Base classes
    'BaseHandoffAgent',
    'AgentConfig',
    'Tool',

    # Runtime
    'AgentRuntime',
    'Session',

    # Tools
    'DelegateTool',
    'ActionTool',
    'create_delegate_tool',
    'create_action_tool',
    'ToolRegistry',
    'get_tool_registry',
    'transfer_to_execution',
    'transfer_to_vision',
    'transfer_to_recovery',
    'transfer_to_orchestrator',

    # Concrete Agents
    'ExecutionAgent',
    'VisionHandoffAgent',
    'OrchestratorAgent',
    'RecoveryAgent',

    # Claude Desktop Bridge
    'ClaudeDesktopBridge',
    'ClaudeDesktopReport',
    'ReportType',
    'ReportParser',
    'EventStream',
    'get_project_instructions',

    # Society of Mind - Team Agents
    'TeamAgent',
    'TeamConfig',
    'SubAgentResult',
    'SynthesisStrategy',
    'PlanningTeam',
    'PlannerAgent',
    'CriticAgent',
    'ValidationTeam',
    'ElementFinderAgent',
    'ScreenStateValidator',
    'ChangeDetector',
]
