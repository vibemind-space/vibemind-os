"""
AutoGen Swarm Mixin - Enables Swarm-style handoffs for event scheduling.

This mixin provides an alternative to RoundRobinGroupChat that uses
AutoGen's Swarm pattern for dynamic task delegation. Agents can hand off
tasks to other agents based on event types and context.

Architecture:
    EventBus Events → SwarmOrchestrator → Agent Handoffs → EventBus

Unlike RoundRobinGroupChat which uses fixed rotation:
    Operator → Validator → Operator → ...

Swarm uses dynamic handoffs based on capabilities:
    DatabaseAgent --[SCHEMA_GENERATED]--> APIAgent --[ROUTES_GENERATED]--> WebSocketAgent

Benefits for Society of Mind:
1. Event dependencies map naturally to handoffs
2. Agents make local decisions about routing
3. Better error recovery with re-routing
4. Context-aware delegation

Usage:
    class DatabaseAgent(AutonomousAgent, AutogenSwarmMixin):
        def get_handoff_targets(self) -> dict[EventType, str]:
            return {
                EventType.DATABASE_SCHEMA_GENERATED: "api_agent",
                EventType.DATABASE_MIGRATION_COMPLETE: "validator_agent",
            }

        async def act(self, events):
            result = await self.execute_with_swarm(events)
            # Automatically hands off to next agent based on result event type
"""

import asyncio
from typing import Any, Optional, TYPE_CHECKING
import structlog

logger = structlog.get_logger(__name__)

# Conditional imports — autogen may not be installed in all environments
try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import Swarm
    from autogen_agentchat.conditions import TextMentionTermination, HandoffTermination
    from autogen_agentchat.messages import HandoffMessage
    from autogen_core.model_context import BufferedChatCompletionContext
    from autogen_core.tools import FunctionTool
    SWARM_AVAILABLE = True
except ImportError:
    SWARM_AVAILABLE = False
    logger.warning("autogen_swarm_not_available",
                   msg="autogen-agentchat Swarm not available")


class AutogenSwarmMixin:
    """
    Mixin for AutonomousAgent subclasses to use AutoGen Swarm pattern.

    Enables dynamic task handoffs between agents based on:
    - Event types (each event type routes to a specific agent)
    - Task context (agents can inspect context before accepting)
    - Capability matching (handoffs based on agent capabilities)

    Requires the host class to provide:
    - self.name: str (agent name)
    - self.working_dir: str (project output directory)
    - self.shared_state: SharedState (from AutonomousAgent)
    - self.event_bus: EventBus (for publishing handoff results)
    """

    _swarm_model_client = None
    _swarm_registry: dict[str, "AssistantAgent"] = {}  # Registry of swarm agents

    # -------------------------------------------------------------------------
    # Swarm Agent Registry
    # -------------------------------------------------------------------------

    @classmethod
    def register_swarm_agent(cls, agent_name: str, swarm_agent: "AssistantAgent"):
        """Register an agent for swarm handoffs."""
        cls._swarm_registry[agent_name] = swarm_agent
        logger.info("swarm_agent_registered", agent=agent_name)

    @classmethod
    def get_swarm_agent(cls, agent_name: str) -> Optional["AssistantAgent"]:
        """Get a registered swarm agent by name."""
        return cls._swarm_registry.get(agent_name)

    @classmethod
    def list_swarm_agents(cls) -> list[str]:
        """List all registered swarm agents."""
        return list(cls._swarm_registry.keys())

    # -------------------------------------------------------------------------
    # Handoff Configuration (Override in subclasses)
    # -------------------------------------------------------------------------

    def get_handoff_targets(self) -> dict[str, str]:
        """
        Define handoff targets for this agent.

        Override in subclasses to specify which agents should receive
        handoffs based on event types or task outcomes.

        Returns:
            Dict mapping event type names to target agent names
            Example: {"DATABASE_SCHEMA_GENERATED": "api_agent"}
        """
        return {}

    def get_agent_capabilities(self) -> list[str]:
        """
        Define this agent's capabilities for swarm routing.

        Override in subclasses to specify what this agent can handle.

        Returns:
            List of capability strings
            Example: ["database", "prisma", "migrations"]
        """
        return []

    # -------------------------------------------------------------------------
    # Swarm Agent Creation
    # -------------------------------------------------------------------------

    def create_swarm_agent(
        self,
        name: str,
        system_message: str,
        tools: list = None,
        handoffs: list[str] = None,
    ) -> "AssistantAgent":
        """
        Create an AssistantAgent configured for swarm participation.

        Args:
            name: Agent name for the swarm
            system_message: System prompt for the agent
            tools: List of FunctionTool objects
            handoffs: List of agent names this agent can hand off to

        Returns:
            AssistantAgent configured for swarm
        """
        if not SWARM_AVAILABLE:
            raise RuntimeError("AutoGen Swarm not available")

        model_client = self._get_swarm_model_client()

        agent = AssistantAgent(
            name=name,
            model_client=model_client,
            tools=tools or [],
            handoffs=handoffs or [],
            system_message=system_message,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Register in swarm registry
        self.register_swarm_agent(name, agent)

        return agent

    def _get_swarm_model_client(self):
        """Get or create the swarm model client."""
        if self._swarm_model_client is None:
            import os
            import sys

            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            shared_path = os.path.join(project_root, "mcp_plugins", "servers", "shared")
            if shared_path not in sys.path:
                sys.path.insert(0, shared_path)

            from model_init import init_model_client
            self._swarm_model_client = init_model_client("swarm-agent", "")

        return self._swarm_model_client

    # -------------------------------------------------------------------------
    # Swarm Execution
    # -------------------------------------------------------------------------

    async def create_swarm(
        self,
        agents: list["AssistantAgent"],
        termination_keyword: str = "SWARM_COMPLETE",
    ) -> "Swarm":
        """
        Create a Swarm team from registered agents.

        Args:
            agents: List of AssistantAgent objects to include in swarm
            termination_keyword: Keyword that signals swarm completion

        Returns:
            Swarm team object
        """
        if not SWARM_AVAILABLE:
            raise RuntimeError("AutoGen Swarm not available")

        termination = TextMentionTermination(termination_keyword)

        return Swarm(
            participants=agents,
            termination_condition=termination,
        )

    async def run_swarm(
        self,
        swarm: "Swarm",
        task: str,
        initial_agent: str = None,
    ) -> dict:
        """
        Execute a swarm and track handoffs.

        Args:
            swarm: Swarm team to execute
            task: Initial task prompt
            initial_agent: Name of agent to start with (optional)

        Returns:
            Dict with execution results and handoff history
        """
        if not SWARM_AVAILABLE:
            return {"success": False, "error": "Swarm not available"}

        logger.info("swarm_starting",
                    agent=self.name,
                    task_length=len(task),
                    initial_agent=initial_agent)

        try:
            result = await swarm.run(task=task)

            # Extract messages and handoff history
            messages = []
            handoffs = []

            if hasattr(result, 'messages') and result.messages:
                for msg in result.messages:
                    content = str(msg.content) if hasattr(msg, 'content') else str(msg)
                    source = getattr(msg, 'source', 'Unknown')
                    messages.append({"source": source, "content": content})

                    # Track handoffs
                    if hasattr(msg, '__class__') and msg.__class__.__name__ == 'HandoffMessage':
                        handoffs.append({
                            "from": source,
                            "to": getattr(msg, 'target', 'unknown'),
                            "reason": content[:200],
                        })

            result_text = messages[-1]["content"] if messages else ""

            logger.info("swarm_completed",
                        agent=self.name,
                        message_count=len(messages),
                        handoff_count=len(handoffs))

            return {
                "success": True,
                "result_text": result_text,
                "messages": messages,
                "handoffs": handoffs,
                "files_mentioned": self._extract_files_from_swarm(messages),
            }

        except Exception as e:
            logger.error("swarm_failed", agent=self.name, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "messages": [],
                "handoffs": [],
            }

    def _extract_files_from_swarm(self, messages: list[dict]) -> list[str]:
        """Extract file paths mentioned in swarm messages."""
        import re
        files = set()
        pattern = re.compile(
            r'(?:^|[\s\'"`])'
            r'((?:src|lib|app|pages|components|prisma|public|config|tests?|e2e)'
            r'/[\w./\-]+\.[a-z]{1,5})',
            re.MULTILINE
        )
        for msg in messages:
            content = msg.get("content", "")
            matches = pattern.findall(content)
            files.update(matches)
        return sorted(files)

    # -------------------------------------------------------------------------
    # Event-Based Handoff Helpers
    # -------------------------------------------------------------------------

    def build_handoff_message(
        self,
        target_agent: str,
        event_type: str,
        context: dict,
    ) -> str:
        """
        Build a handoff message for transitioning to another agent.

        Args:
            target_agent: Name of the agent to hand off to
            event_type: The event type that triggered this handoff
            context: Context data to pass to the target agent

        Returns:
            Formatted handoff message string
        """
        import json
        return f"""HANDOFF to {target_agent}

Event: {event_type}
Context:
{json.dumps(context, indent=2, default=str)[:2000]}

Please continue processing this task."""

    @staticmethod
    def is_swarm_available() -> bool:
        """Check if AutoGen Swarm is installed and available."""
        return SWARM_AVAILABLE


# -------------------------------------------------------------------------
# Swarm Orchestrator for Society of Mind
# -------------------------------------------------------------------------

class SwarmOrchestrator:
    """
    Orchestrates AutoGen Swarms for the Society of Mind event system.

    Maps EventBus events to Swarm handoffs, enabling dynamic routing
    between agents based on event types and context.

    Usage:
        orchestrator = SwarmOrchestrator()

        # Register agents with their capabilities
        orchestrator.register_agent("database_agent", DatabaseAgent(...))
        orchestrator.register_agent("api_agent", APIAgent(...))

        # Define event-to-agent routing
        orchestrator.set_event_routing({
            "CONTRACTS_GENERATED": "database_agent",
            "DATABASE_SCHEMA_GENERATED": "api_agent",
            "API_ROUTES_GENERATED": "websocket_agent",
        })

        # Process event with swarm routing
        result = await orchestrator.process_event(event)
    """

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._event_routing: dict[str, str] = {}
        self._swarm_agents: dict[str, "AssistantAgent"] = {}
        self.logger = logger.bind(component="SwarmOrchestrator")

    def register_agent(self, name: str, agent: Any):
        """Register an AutonomousAgent for swarm participation."""
        self._agents[name] = agent
        self.logger.info("agent_registered_for_swarm", agent=name)

    def set_event_routing(self, routing: dict[str, str]):
        """
        Set event-to-agent routing rules.

        Args:
            routing: Dict mapping event type names to agent names
        """
        self._event_routing = routing
        self.logger.info("event_routing_configured", routes=len(routing))

    def get_target_agent(self, event_type: str) -> Optional[str]:
        """Get the target agent for an event type."""
        return self._event_routing.get(event_type)

    async def create_swarm_for_pipeline(
        self,
        pipeline_events: list[str],
    ) -> Optional["Swarm"]:
        """
        Create a Swarm for a pipeline of events.

        Args:
            pipeline_events: Ordered list of event types in the pipeline
                            e.g., ["CONTRACTS_GENERATED", "DATABASE_SCHEMA_GENERATED", ...]

        Returns:
            Configured Swarm or None if not enough agents
        """
        if not SWARM_AVAILABLE:
            return None

        # Collect agents needed for this pipeline
        agents_needed = []
        for event_type in pipeline_events:
            agent_name = self._event_routing.get(event_type)
            if agent_name and agent_name in self._agents:
                if agent_name not in [a[0] for a in agents_needed]:
                    agents_needed.append((agent_name, self._agents[agent_name]))

        if len(agents_needed) < 2:
            self.logger.warning("insufficient_agents_for_swarm", count=len(agents_needed))
            return None

        # Create swarm agents with appropriate handoffs
        swarm_agents = []
        for i, (name, agent) in enumerate(agents_needed):
            # Determine handoff targets (next agent in pipeline)
            handoff_targets = []
            if i < len(agents_needed) - 1:
                handoff_targets.append(agents_needed[i + 1][0])
            handoff_targets.append("user")  # Always allow handoff to user

            # Create swarm-compatible agent
            if hasattr(agent, 'create_swarm_agent'):
                swarm_agent = agent.create_swarm_agent(
                    name=name,
                    system_message=self._get_agent_system_message(agent),
                    tools=self._get_agent_tools(agent),
                    handoffs=handoff_targets,
                )
                swarm_agents.append(swarm_agent)

        if not swarm_agents:
            return None

        return Swarm(
            participants=swarm_agents,
            termination_condition=TextMentionTermination("PIPELINE_COMPLETE"),
        )

    def _get_agent_system_message(self, agent: Any) -> str:
        """Extract or generate system message for an agent."""
        if hasattr(agent, '_get_operator_system_prompt'):
            return agent._get_operator_system_prompt()
        elif hasattr(agent, 'get_system_prompt'):
            return agent.get_system_prompt()
        return f"You are {agent.name}, an autonomous agent."

    def _get_agent_tools(self, agent: Any) -> list:
        """Extract tools from an agent."""
        if hasattr(agent, '_create_claude_code_tools'):
            return agent._create_claude_code_tools()
        elif hasattr(agent, 'get_autogen_tools'):
            return agent.get_autogen_tools()
        return []


# Default event routing for WhatsApp-like messaging platform
DEFAULT_MESSAGING_PLATFORM_ROUTING = {
    "CONTRACTS_GENERATED": "database_agent",
    "DATABASE_SCHEMA_GENERATED": "api_agent",
    "API_ROUTES_GENERATED": "websocket_agent",
    "WEBSOCKET_HANDLER_GENERATED": "redis_pubsub_agent",
    "REDIS_PUBSUB_CONFIGURED": "auth_agent",
    "AUTH_SETUP_COMPLETE": "infrastructure_agent",
    "GROUP_MANAGEMENT_NEEDED": "group_management_agent",
    "PRESENCE_TRACKING_NEEDED": "presence_agent",
    "ENCRYPTION_REQUIRED": "encryption_agent",
}
