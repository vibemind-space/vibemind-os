"""
WebSocket Agent - Generates WebSocket handlers for real-time features.

This agent is responsible for:
- Generating NestJS WebSocket Gateways with Socket.io
- Creating real-time messaging handlers
- Implementing presence and typing indicators
- Setting up room/channel management

Architecture:
- Uses AutogenTeamMixin for AG2 0.4.x team-based execution
- Operator agent has Claude Code as tool for code generation
- QA Validator reviews generated code without tool access

Trigger Events:
- API_ROUTES_GENERATED: After REST APIs are ready
- WEBSOCKET_HANDLER_NEEDED: When WebSocket features are needed
- REALTIME_FEATURE_REQUESTED: When real-time features are requested

Publishes:
- WEBSOCKET_HANDLER_GENERATED: When WebSocket handlers are complete
- WEBSOCKET_GENERATION_FAILED: When generation fails
"""

import asyncio
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType,
    system_error_event,
)

if TYPE_CHECKING:
    from ..mind.event_bus import EventBus
    from ..mind.shared_state import SharedState
    from ..skills.registry import SkillRegistry
    from ..skills.dynamic_skill_generator import DynamicSkillGenerator

logger = structlog.get_logger(__name__)


class WebSocketAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for WebSocket/real-time feature generation.

    Uses dynamic skill generation to:
    - Generate NestJS WebSocket Gateways
    - Create Socket.io event handlers
    - Implement presence tracking
    - Set up room/channel management

    Supports:
    - NestJS with @nestjs/websockets
    - Socket.io integration
    - Redis adapter for scaling

    CRITICAL: All WebSocket handlers must integrate with Redis Pub/Sub
    for horizontal scaling across multiple server instances.
    """

    # Event types for real-time features
    REALTIME_KEYWORDS = [
        "message", "chat", "notification", "presence",
        "typing", "status", "call", "video", "voice",
        "live", "realtime", "real-time", "echtzeit",
    ]

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        skill_generator: Optional["DynamicSkillGenerator"] = None,
        websocket_framework: str = "nestjs",  # nestjs, express-ws, socket.io
        **kwargs,
    ):
        """
        Initialize the WebSocketAgent.

        Args:
            name: Agent name (typically "WebSocketAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            skill_generator: Dynamic skill generator for on-demand skills
            websocket_framework: Target WebSocket framework
            **kwargs: Additional args for AutonomousAgent
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.skill_registry = skill_registry
        self.skill_generator = skill_generator
        self.websocket_framework = websocket_framework
        self._api_routes_data: Optional[dict] = None
        self._entities_data: Optional[dict] = None
        self._generated_handlers: list[str] = []

        self.logger = logger.bind(agent=name, framework=websocket_framework)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.API_ROUTES_GENERATED,
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.CONTRACTS_GENERATED,
            # Custom events for real-time features
            # EventType.WEBSOCKET_HANDLER_NEEDED,
            # EventType.REALTIME_FEATURE_REQUESTED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to generate WebSocket handlers.

        Acts when:
        - API routes are generated AND have real-time features
        - Explicit WebSocket handler request received
        - Contracts contain messaging/real-time requirements
        """
        for event in events:
            # Primary trigger: API routes generated
            if event.type == EventType.API_ROUTES_GENERATED:
                self._api_routes_data = event.data

                # Check if real-time features are needed
                if self._has_realtime_features(event.data):
                    self.logger.info(
                        "realtime_features_detected",
                        routes=event.data.get("routes", [])[:5] if event.data else [],
                    )
                    return True

            # Store entity data for context
            if event.type == EventType.DATABASE_SCHEMA_GENERATED:
                self._entities_data = event.data

            # Check contracts for messaging requirements
            if event.type == EventType.CONTRACTS_GENERATED:
                if self._has_messaging_contracts(event.data):
                    self.logger.info(
                        "messaging_contracts_detected",
                        interfaces=list(event.data.get("interfaces", {}).keys())[:5] if event.data else [],
                    )
                    return True

        return False

    def _has_realtime_features(self, data: Optional[dict]) -> bool:
        """Check if API routes data contains real-time features."""
        if not data:
            return False

        # Check route paths for real-time keywords
        routes = data.get("routes", [])
        for route in routes:
            path = str(route.get("path", "")).lower()
            for keyword in self.REALTIME_KEYWORDS:
                if keyword in path:
                    return True

        # Check entities for messaging types
        entities = data.get("entities", [])
        for entity in entities:
            name = str(entity).lower()
            if any(kw in name for kw in ["message", "chat", "notification"]):
                return True

        return False

    def _has_messaging_contracts(self, data: Optional[dict]) -> bool:
        """Check if contracts contain messaging interfaces."""
        if not data:
            return False

        interfaces = data.get("interfaces", {})
        for name in interfaces.keys():
            name_lower = name.lower()
            if any(kw in name_lower for kw in self.REALTIME_KEYWORDS):
                return True

        return False

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "websocket"

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate WebSocket handlers for real-time features.

        Uses AutoGen team pattern when available:
        - WebSocketOperator: Has Claude Code tool for code generation
        - WebSocketValidator: Reviews code without tool access

        Fallback: Direct Claude Code tool execution.
        """
        self.logger.info("generating_websocket_handlers")

        # Use AutoGen team pattern if available
        if self.is_autogen_available():
            return await self._act_with_autogen_team(events)

        # Fallback to legacy execution
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Execute WebSocket generation using AutoGen team pattern.

        The team consists of:
        - WebSocketOperator: Has Claude Code tool, generates NestJS WebSocket code
        - WebSocketValidator: Reviews generated code for quality and patterns
        """
        try:
            # Get skill instructions for context
            skill_instructions = await self._get_skill_instructions()

            # Get RAG context for WebSocket patterns
            context = await self.get_task_context(
                query="websocket socket.io gateway event handlers rooms presence NestJS",
                epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
            )

            # Build extra context for the task prompt
            extra_context = self._build_generation_prompt(skill_instructions)

            # Inject RAG results into prompt
            if context and context.rag_results:
                extra_context += "\n\n## Relevant Code Examples (from RAG)"
                for result in context.rag_results[:3]:
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:500]
                    score = result.get("score", 0)
                    extra_context += f"\n### {file_path} (score: {score:.2f})\n```\n{content}\n```"

                self.logger.info(
                    "rag_context_injected",
                    rag_results_count=len(context.rag_results),
                )

            # Build task prompt using mixin helper
            task = self.build_task_prompt(events, extra_context=extra_context)

            # Create Claude Code tool for the operator
            claude_code_tools = self._create_claude_code_tools()

            # Create the Operator + Validator team
            team = self.create_team(
                operator_name="WebSocketOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="WebSocketValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=claude_code_tools,  # Claude Code as primary tool
                max_turns=15,
                task="Generate NestJS WebSocket handlers with Socket.io",
            )

            # Execute the team
            result = await self.run_team(team, task)

            if result["success"]:
                # Extract generated files from result
                files_mentioned = result.get("files_mentioned", [])

                self.logger.info(
                    "websocket_handlers_generated_via_autogen",
                    files=files_mentioned,
                    message_count=len(result.get("messages", [])),
                )

                return Event(
                    type=EventType.WEBSOCKET_HANDLER_GENERATED,
                    source=self.name,
                    data={
                        "handlers": files_mentioned,
                        "framework": self.websocket_framework,
                        "features": ["messaging", "presence", "rooms"],
                        "autogen_result": result.get("result_text", "")[:500],
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "websocket_generation_failed_via_autogen",
                    error=result.get("result_text", "Unknown error")[:200],
                )

                return Event(
                    type=EventType.WEBSOCKET_GENERATION_FAILED,
                    source=self.name,
                    data={"error": result.get("result_text", "AutoGen team failed")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("websocket_autogen_error")
            # Fall back to legacy execution on error
            self.logger.info("falling_back_to_legacy_execution")
            return await self._act_legacy(events)

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy execution path using direct Claude Code tool.

        Used when AutoGen is not available or as fallback on error.
        """
        try:
            # Step 1: Generate dynamic skill if available
            skill_instructions = await self._get_skill_instructions()

            # Step 2: Build generation prompt
            prompt = self._build_generation_prompt(skill_instructions)

            # Step 3: Execute code generation
            result = await self._generate_websocket_code(prompt)

            if result.get("success"):
                self._generated_handlers = result.get("files", [])

                self.logger.info(
                    "websocket_handlers_generated",
                    files=self._generated_handlers,
                )

                # Publish success event
                return Event(
                    type=EventType.WEBSOCKET_HANDLER_GENERATED,
                    source=self.name,
                    data={
                        "handlers": self._generated_handlers,
                        "framework": self.websocket_framework,
                        "features": ["messaging", "presence", "rooms"],
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "websocket_generation_failed",
                    error=result.get("error", "Unknown error"),
                )

                return Event(
                    type=EventType.WEBSOCKET_GENERATION_FAILED,
                    source=self.name,
                    data={"error": result.get("error")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("websocket_agent_error")
            return system_error_event(
                source=self.name,
                error=str(e),
                context="WebSocket generation",
            )

    def _create_claude_code_tools(self) -> list:
        """
        Create Claude Code as a FunctionTool for AutoGen operators.

        Returns:
            List containing the Claude Code FunctionTool
        """
        try:
            from autogen_core.tools import FunctionTool
        except ImportError:
            self.logger.warning("autogen_tools_not_available")
            return []

        from ..tools.claude_code_tool import ClaudeCodeTool

        # Create the Claude Code tool instance
        claude_tool = ClaudeCodeTool(
            working_dir=self.working_dir,
            timeout=300,  # 5 minutes for complex generation
        )

        async def generate_websocket_code(
            prompt: str,
            context: str = "",
        ) -> dict:
            """
            Generate WebSocket code using Claude Code CLI.

            Args:
                prompt: Description of what WebSocket code to generate
                context: Additional context (entities, routes, requirements)

            Returns:
                Dict with success status, generated files, and any errors
            """
            try:
                result = await claude_tool.execute(
                    prompt=prompt,
                    context=context,
                    agent_type="backend",
                )
                return {
                    "success": result.success,
                    "files": [f.path for f in result.files] if result.files else [],
                    "output": result.output[:1000] if result.output else "",
                    "error": result.error,
                }
            except Exception as e:
                return {
                    "success": False,
                    "files": [],
                    "output": "",
                    "error": str(e),
                }

        # Wrap as FunctionTool
        tool = FunctionTool(
            generate_websocket_code,
            description=(
                "Generate NestJS WebSocket Gateway code using Claude Code. "
                "Provide a detailed prompt describing the WebSocket handlers to create, "
                "including event names, DTOs, and room management logic."
            ),
        )

        return [tool]

    def _get_operator_system_prompt(self) -> str:
        """Get system prompt for WebSocketOperator agent."""
        return f"""You are WebSocketOperator, an expert in generating NestJS WebSocket Gateways with Socket.io.

Your role:
1. Use the generate_websocket_code tool to create WebSocket handlers
2. Generate complete, production-ready NestJS code
3. Follow best practices for real-time communication

Framework: {self.websocket_framework}
Working Directory: {self.working_dir}

CRITICAL REQUIREMENTS:
- Generate @WebSocketGateway classes with proper decorators
- Use @SubscribeMessage for event handlers
- Implement OnGatewayConnection and OnGatewayDisconnect interfaces
- Create DTOs with class-validator decorators
- Configure Redis adapter for horizontal scaling
- NO MOCKS - Connect to real database services
- Handle errors gracefully with proper error events

Code Structure:
- src/websocket/gateways/ - Gateway classes
- src/websocket/dto/ - Data transfer objects
- src/websocket/adapters/ - Redis adapter configuration
- src/websocket/websocket.module.ts - Module registration

When calling the tool, provide detailed prompts including:
- Specific event names (sendMessage, joinRoom, etc.)
- DTO structure with validation rules
- Room management logic
- Presence tracking requirements

After completing all code generation, say TASK_COMPLETE."""

    def _get_validator_system_prompt(self) -> str:
        """Get system prompt for WebSocketValidator agent."""
        return """You are WebSocketValidator, a code reviewer specializing in NestJS WebSocket implementations.

Your role:
1. Review the code generated by WebSocketOperator
2. Verify it follows NestJS and Socket.io best practices
3. Check for security issues and proper validation
4. Ensure Redis adapter is properly configured

Review Checklist:
- [ ] Gateway classes use proper decorators (@WebSocketGateway, @SubscribeMessage)
- [ ] DTOs have class-validator decorators for input validation
- [ ] Connection/disconnection handlers are implemented
- [ ] Room management follows Socket.io patterns
- [ ] Error handling emits proper error events
- [ ] Redis adapter is configured for scaling
- [ ] No mock implementations - real database connections
- [ ] Proper TypeScript types throughout

If you find issues:
1. Clearly describe the problem
2. Suggest the fix
3. Ask the Operator to regenerate if needed

If the code meets all requirements, confirm approval and say TASK_COMPLETE."""

    async def _get_skill_instructions(self) -> str:
        """Get skill instructions, using dynamic generation if available."""
        if self.skill_generator:
            try:
                # Get tech stack from shared state
                tech_stack = {}
                if hasattr(self.shared_state, "tech_stack"):
                    tech_stack = self.shared_state.tech_stack or {}

                # Generate dynamic skill
                skill = await self.skill_generator.generate(
                    task_type="nestjs_websocket",
                    tech_stack=tech_stack,
                    requirements=[],  # Could be enriched from context
                )
                return skill.instructions

            except Exception as e:
                self.logger.warning(
                    "dynamic_skill_generation_failed",
                    error=str(e),
                    fallback="static",
                )

        # Fallback to static skill if available
        if self.skill_registry:
            skill = self.skill_registry.get_skill("api-generation")
            if skill:
                return skill.instructions

        # Return minimal instructions
        return self._default_websocket_instructions()

    def _default_websocket_instructions(self) -> str:
        """Default instructions when no skill is available."""
        return """
## WebSocket Generation Instructions

Generate NestJS WebSocket handlers following these patterns:

1. Create a WebSocket Gateway:
   ```typescript
   @WebSocketGateway({ cors: true })
   export class ChatGateway implements OnGatewayConnection, OnGatewayDisconnect {
     @WebSocketServer()
     server: Server;

     handleConnection(client: Socket) { ... }
     handleDisconnect(client: Socket) { ... }
   }
   ```

2. Implement message handlers:
   ```typescript
   @SubscribeMessage('sendMessage')
   async handleMessage(
     @MessageBody() data: SendMessageDto,
     @ConnectedSocket() client: Socket,
   ) { ... }
   ```

3. Use Redis adapter for scaling:
   ```typescript
   const redisIoAdapter = new RedisIoAdapter(app);
   await redisIoAdapter.connectToRedis();
   app.useWebSocketAdapter(redisIoAdapter);
   ```

CRITICAL:
- NO MOCKS - Connect to real database
- Validate all incoming messages with class-validator
- Use rooms for targeted messaging
- Implement proper error handling
"""

    def _build_generation_prompt(self, skill_instructions: str) -> str:
        """Build the complete generation prompt."""
        # Extract entity info
        entities_context = ""
        if self._entities_data:
            entities = self._entities_data.get("entities", [])
            entities_context = f"\n\nAvailable Entities:\n" + "\n".join(
                f"- {e}" for e in entities[:10]
            )

        # Extract API routes info
        routes_context = ""
        if self._api_routes_data:
            routes = self._api_routes_data.get("routes", [])
            routes_context = f"\n\nExisting API Routes:\n" + "\n".join(
                f"- {r.get('method', 'GET')} {r.get('path', '/unknown')}"
                for r in routes[:10]
            )

        return f"""
{skill_instructions}

## Context
{entities_context}
{routes_context}

## Task
Generate WebSocket handlers for the following real-time features:

1. **Chat Gateway** - Real-time messaging
   - Send/receive messages
   - Message reactions
   - Typing indicators
   - Read receipts

2. **Presence Gateway** - Online/offline status
   - User presence tracking
   - Last seen updates
   - Activity status

3. **Notification Gateway** - Push notifications
   - Real-time notifications
   - Notification acknowledgment

Framework: {self.websocket_framework}
Use Redis Pub/Sub for horizontal scaling.

Generate the complete implementation with:
- Gateway classes
- DTO classes for message validation
- Redis adapter configuration
- Module registration
"""

    async def _generate_websocket_code(self, prompt: str) -> dict:
        """Execute the code generation using Claude Code tool."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        try:
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=300,  # 5 minutes for complex generation
            )

            result = await tool.execute(
                prompt=prompt,
                context="WebSocket handler generation",
                agent_type="backend",
            )

            return {
                "success": result.success,
                "files": result.files or [],
                "error": result.error if not result.success else None,
            }

        except Exception as e:
            return {
                "success": False,
                "files": [],
                "error": str(e),
            }
