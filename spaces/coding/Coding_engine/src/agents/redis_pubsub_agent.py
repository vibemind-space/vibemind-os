"""
Redis Pub/Sub Agent - Configures Redis for real-time messaging.

This agent is responsible for:
- Setting up Redis Pub/Sub for WebSocket scaling
- Generating Redis adapter configuration
- Creating message queue handlers
- Implementing caching layer

Architecture:
- Uses AutogenTeamMixin for AG2 0.4.x team-based execution
- RedisOperator agent has Claude Code as tool for code generation
- RedisValidator reviews generated code without tool access

Trigger Events:
- WEBSOCKET_HANDLER_GENERATED: After WebSocket handlers are ready
- INFRASTRUCTURE_NEEDED: When infrastructure setup is needed
- REDIS_SETUP_NEEDED: Explicit Redis setup request

Publishes:
- REDIS_PUBSUB_CONFIGURED: When Redis is configured
- REDIS_SETUP_FAILED: When setup fails
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


class RedisPubSubAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for Redis Pub/Sub configuration.

    Generates:
    - Redis adapter for Socket.io/WebSocket scaling
    - Pub/Sub message handlers
    - Cache service implementation
    - Docker Compose Redis configuration

    Supports:
    - NestJS with @nestjs/microservices
    - ioredis client
    - Bull queues for background jobs

    CRITICAL: Redis configuration must be production-ready:
    - Connection pooling
    - Reconnection logic
    - Error handling
    - Health checks
    """

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        skill_generator: Optional["DynamicSkillGenerator"] = None,
        redis_mode: str = "pubsub",  # pubsub, cache, queue, all
        enable_caching: bool = False,
        enable_session_store: bool = False,
        enable_queue: bool = False,
        **kwargs,
    ):
        """
        Initialize the RedisPubSubAgent.

        Args:
            name: Agent name (typically "RedisPubSubAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            skill_generator: Dynamic skill generator
            redis_mode: Redis operation mode
            enable_caching: Enable Redis caching layer generation
            enable_session_store: Enable Redis session store generation
            enable_queue: Enable Redis queue (Bull) generation
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
        self.redis_mode = redis_mode
        self.enable_caching = enable_caching
        self.enable_session_store = enable_session_store
        self.enable_queue = enable_queue
        self._websocket_data: Optional[dict] = None
        self._generated_files: list[str] = []

        self.logger = logger.bind(agent=name, mode=redis_mode)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.WEBSOCKET_HANDLER_GENERATED,
            EventType.AUTH_SETUP_COMPLETE,
            EventType.CONTRACTS_GENERATED,
            # Custom events
            # EventType.REDIS_SETUP_NEEDED,
            # EventType.INFRASTRUCTURE_NEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to configure Redis.

        Acts when:
        - WebSocket handlers are generated (need Redis adapter)
        - Auth setup complete (need session cache)
        - Explicit Redis setup request
        """
        for event in events:
            # Primary trigger: WebSocket handlers ready
            if event.type == EventType.WEBSOCKET_HANDLER_GENERATED:
                self._websocket_data = event.data
                self.logger.info(
                    "websocket_handlers_detected",
                    handlers=event.data.get("handlers", []) if event.data else [],
                )
                return True

            # Secondary trigger: Auth needs session cache
            if event.type == EventType.AUTH_SETUP_COMPLETE:
                if event.data and event.data.get("needs_session_cache"):
                    self.logger.info("session_cache_needed")
                    return True

            # Check contracts for real-time features
            if event.type == EventType.CONTRACTS_GENERATED:
                if self._needs_redis(event.data):
                    self.logger.info("redis_needed_from_contracts")
                    return True

        return False

    def _needs_redis(self, data: Optional[dict]) -> bool:
        """Check if contracts indicate need for Redis."""
        if not data:
            return False

        redis_keywords = ["cache", "session", "realtime", "queue", "job", "pubsub"]
        interfaces = data.get("interfaces", {})

        for name in interfaces.keys():
            name_lower = name.lower()
            if any(kw in name_lower for kw in redis_keywords):
                return True

        return False

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "infra"

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Configure Redis for the project.

        Uses AutoGen team pattern when available:
        - RedisOperator: Has Claude Code tool for code generation
        - RedisValidator: Reviews code without tool access

        Fallback: Direct Claude Code tool execution.
        """
        self.logger.info("configuring_redis")

        # Use AutoGen team pattern if available
        if self.is_autogen_available():
            return await self._act_with_autogen_team(events)

        # Fallback to legacy execution
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Execute Redis configuration using AutoGen team pattern.

        The team consists of:
        - RedisOperator: Has Claude Code tool, generates Redis configuration
        - RedisValidator: Reviews generated code for production readiness
        """
        try:
            # Get skill instructions for context
            skill_instructions = await self._get_skill_instructions()

            # Get RAG context for Redis patterns
            context = await self.get_task_context(
                query="redis ioredis pubsub cache adapter socket.io NestJS docker-compose",
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
                operator_name="RedisOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="RedisValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=claude_code_tools,  # Claude Code as primary tool
                max_turns=15,
                task="Configure Redis Pub/Sub for WebSocket scaling",
            )

            # Execute the team
            result = await self.run_team(team, task)

            if result["success"]:
                # Extract generated files from result
                files_mentioned = result.get("files_mentioned", [])

                self.logger.info(
                    "redis_configured_via_autogen",
                    files=files_mentioned,
                    mode=self.redis_mode,
                    message_count=len(result.get("messages", [])),
                )

                return Event(
                    type=EventType.REDIS_PUBSUB_CONFIGURED,
                    source=self.name,
                    data={
                        "files": files_mentioned,
                        "mode": self.redis_mode,
                        "features": self._get_configured_features(),
                        "autogen_result": result.get("result_text", "")[:500],
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "redis_configuration_failed_via_autogen",
                    error=result.get("result_text", "Unknown error")[:200],
                )

                return Event(
                    type=EventType.REDIS_SETUP_FAILED,
                    source=self.name,
                    data={"error": result.get("result_text", "AutoGen team failed")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("redis_autogen_error")
            # Fall back to legacy execution on error
            self.logger.info("falling_back_to_legacy_execution")
            return await self._act_legacy(events)

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy execution path using direct Claude Code tool.

        Used when AutoGen is not available or as fallback on error.
        """
        try:
            # Get skill instructions
            skill_instructions = await self._get_skill_instructions()

            # Build generation prompt
            prompt = self._build_generation_prompt(skill_instructions)

            # Execute code generation
            result = await self._generate_redis_code(prompt)

            if result.get("success"):
                self._generated_files = result.get("files", [])

                self.logger.info(
                    "redis_configured",
                    files=self._generated_files,
                    mode=self.redis_mode,
                )

                # Publish success event
                return Event(
                    type=EventType.REDIS_PUBSUB_CONFIGURED,
                    source=self.name,
                    data={
                        "files": self._generated_files,
                        "mode": self.redis_mode,
                        "features": self._get_configured_features(),
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "redis_configuration_failed",
                    error=result.get("error", "Unknown error"),
                )

                return Event(
                    type=EventType.REDIS_SETUP_FAILED,
                    source=self.name,
                    data={"error": result.get("error")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("redis_agent_error")
            return system_error_event(
                source=self.name,
                error=str(e),
                context="Redis configuration",
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
            timeout=240,  # 4 minutes
        )

        async def generate_redis_code(
            prompt: str,
            context: str = "",
        ) -> dict:
            """
            Generate Redis configuration code using Claude Code CLI.

            Args:
                prompt: Description of what Redis code to generate
                context: Additional context (WebSocket handlers, requirements)

            Returns:
                Dict with success status, generated files, and any errors
            """
            try:
                result = await claude_tool.execute(
                    prompt=prompt,
                    context=context,
                    agent_type="devops",
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
            generate_redis_code,
            description=(
                "Generate Redis configuration code using Claude Code. "
                "Provide a detailed prompt describing the Redis setup needed, "
                "including Pub/Sub, caching, Docker config, and health checks."
            ),
        )

        return [tool]

    def _get_operator_system_prompt(self) -> str:
        """Get system prompt for RedisOperator agent."""
        return f"""You are RedisOperator, an expert in Redis configuration for production NestJS applications.

Your role:
1. Use the generate_redis_code tool to create Redis configurations
2. Generate complete, production-ready Redis setup code
3. Follow best practices for high availability and performance

Redis Mode: {self.redis_mode}
Working Directory: {self.working_dir}

CRITICAL REQUIREMENTS:
- Configure ioredis client with connection pooling
- Implement exponential backoff reconnection logic
- Create Redis adapter for Socket.io scaling
- Generate Docker Compose with health checks
- Add environment variable templates
- NO MOCKS - Connect to real Redis instance
- Handle connection errors gracefully

Code Structure:
- src/redis/redis.module.ts - Redis module configuration
- src/redis/redis-io.adapter.ts - Socket.io Redis adapter
- src/redis/cache.service.ts - Cache service with TTL
- src/redis/presence.service.ts - User presence tracking
- docker-compose.yml - Redis service entry
- .env.example - Redis environment variables

When calling the tool, provide detailed prompts including:
- Specific Redis features needed (Pub/Sub, cache, sessions)
- Connection configuration (cluster, sentinel, standalone)
- Error handling requirements
- Health check integration

After completing all code generation, say TASK_COMPLETE."""

    def _get_validator_system_prompt(self) -> str:
        """Get system prompt for RedisValidator agent."""
        return """You are RedisValidator, a code reviewer specializing in Redis production deployments.

Your role:
1. Review the code generated by RedisOperator
2. Verify it follows Redis best practices for production
3. Check for security issues and proper error handling
4. Ensure high availability configuration

Review Checklist:
- [ ] Connection pooling is configured
- [ ] Reconnection logic with exponential backoff
- [ ] Error handling for connection failures
- [ ] Health check endpoint included
- [ ] Docker Compose has proper Redis configuration
- [ ] Environment variables are externalized
- [ ] No hardcoded credentials
- [ ] TTL is set for cached data
- [ ] Proper TypeScript types throughout

Production Readiness:
- [ ] Redis persistence (AOF/RDB) configured
- [ ] Memory limits set
- [ ] Cluster/Sentinel support if needed
- [ ] Graceful shutdown handling

If you find issues:
1. Clearly describe the problem
2. Explain the production risk
3. Suggest the fix
4. Ask the Operator to regenerate if needed

If the code meets all requirements, confirm approval and say TASK_COMPLETE."""

    def _get_configured_features(self) -> list[str]:
        """Get list of configured Redis features."""
        features = []

        if self.redis_mode in ["pubsub", "all"]:
            features.extend(["pubsub", "websocket_adapter"])

        if self.redis_mode in ["cache", "all"]:
            features.extend(["cache", "session_store"])

        if self.redis_mode in ["queue", "all"]:
            features.extend(["job_queue", "background_tasks"])

        return features

    async def _get_skill_instructions(self) -> str:
        """Get skill instructions for Redis configuration."""
        if self.skill_generator:
            try:
                tech_stack = {}
                if hasattr(self.shared_state, "tech_stack"):
                    tech_stack = self.shared_state.tech_stack or {}

                skill = await self.skill_generator.generate(
                    task_type="redis_pubsub",
                    tech_stack=tech_stack,
                    requirements=[],
                )
                return skill.instructions

            except Exception as e:
                self.logger.warning(
                    "dynamic_skill_generation_failed",
                    error=str(e),
                )

        return self._default_redis_instructions()

    def _default_redis_instructions(self) -> str:
        """Default instructions for Redis configuration."""
        return """
## Redis Configuration Instructions

Configure Redis for NestJS application with the following components:

1. **Redis Module Setup**:
   ```typescript
   @Module({
     imports: [
       RedisModule.forRootAsync({
         useFactory: (configService: ConfigService) => ({
           config: {
             host: configService.get('REDIS_HOST', 'localhost'),
             port: configService.get('REDIS_PORT', 6379),
           },
         }),
         inject: [ConfigService],
       }),
     ],
   })
   export class AppModule {}
   ```

2. **Redis Adapter for WebSockets**:
   ```typescript
   export class RedisIoAdapter extends IoAdapter {
     private adapterConstructor: ReturnType<typeof createAdapter>;

     async connectToRedis(): Promise<void> {
       const pubClient = createClient({ url: process.env.REDIS_URL });
       const subClient = pubClient.duplicate();
       await Promise.all([pubClient.connect(), subClient.connect()]);
       this.adapterConstructor = createAdapter(pubClient, subClient);
     }

     createIOServer(port: number, options?: ServerOptions): any {
       const server = super.createIOServer(port, options);
       server.adapter(this.adapterConstructor);
       return server;
     }
   }
   ```

3. **Cache Service**:
   ```typescript
   @Injectable()
   export class CacheService {
     constructor(@InjectRedis() private readonly redis: Redis) {}

     async get<T>(key: string): Promise<T | null> {
       const value = await this.redis.get(key);
       return value ? JSON.parse(value) : null;
     }

     async set(key: string, value: any, ttlSeconds?: number): Promise<void> {
       const serialized = JSON.stringify(value);
       if (ttlSeconds) {
         await this.redis.setex(key, ttlSeconds, serialized);
       } else {
         await this.redis.set(key, serialized);
       }
     }
   }
   ```

4. **Docker Compose Entry**:
   ```yaml
   redis:
     image: redis:7-alpine
     ports:
       - "6379:6379"
     volumes:
       - redis-data:/data
     command: redis-server --appendonly yes
     healthcheck:
       test: ["CMD", "redis-cli", "ping"]
       interval: 5s
       timeout: 3s
       retries: 5
   ```

CRITICAL:
- Use connection pooling for production
- Implement reconnection logic with exponential backoff
- Add health checks
- Configure Redis persistence (AOF/RDB) for durability
"""

    def _build_generation_prompt(self, skill_instructions: str) -> str:
        """Build the complete generation prompt."""
        websocket_context = ""
        if self._websocket_data:
            handlers = self._websocket_data.get("handlers", [])
            websocket_context = f"\n\nExisting WebSocket Handlers:\n" + "\n".join(
                f"- {h}" for h in handlers
            )

        return f"""
{skill_instructions}

## Context
{websocket_context}

## Task
Configure Redis for the following purposes:

1. **Pub/Sub for WebSocket Scaling**
   - Redis adapter for Socket.io
   - Cross-instance message broadcasting
   - Room management synchronization

2. **Session Cache**
   - User session storage
   - JWT token blacklist
   - Rate limiting counters

3. **Presence Tracking**
   - Online user set
   - Last seen timestamps
   - Typing indicators with TTL

Mode: {self.redis_mode}

Generate the complete implementation with:
- Redis module configuration
- Redis adapter for NestJS
- Cache service with TTL support
- Docker Compose configuration
- Environment variables template
- Health check integration
"""

    async def _generate_redis_code(self, prompt: str) -> dict:
        """Execute the code generation using Claude Code tool."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        try:
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=240,  # 4 minutes
            )

            result = await tool.execute(
                prompt=prompt,
                context="Redis Pub/Sub configuration",
                agent_type="devops",
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
