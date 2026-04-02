"""
PresenceAgent - Tracks online/offline status, typing indicators, and read receipts.

This agent handles real-time presence features for messaging platforms:
- Online/offline status tracking with heartbeat
- Typing indicators with TTL (auto-expire)
- Read receipts (sent, delivered, read)
- Last seen timestamps
- Presence broadcasting to relevant users

Architecture:
    WebSocketAgent (WEBSOCKET_HANDLER_GENERATED)
        ↓
    PresenceAgent → Redis-backed presence store
        ↓
    PRESENCE_UPDATED (broadcast to subscribers)

Uses AutoGen Team pattern:
    PresenceOperator (has Claude Code tool) + PresenceValidator (review only)
"""

import asyncio
from pathlib import Path
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from src.mind.event_bus import Event, EventType

logger = structlog.get_logger(__name__)


class PresenceAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for presence tracking in real-time messaging.

    Generates:
    - Presence service with Redis-backed state
    - Typing indicator handlers with TTL
    - Read receipt tracking (sent → delivered → read)
    - Online/offline status with heartbeat
    - Last seen timestamp management
    - Presence WebSocket events

    Uses AutoGen RoundRobinGroupChat:
        PresenceOperator: Generates presence code using Claude Code tool
        PresenceValidator: Reviews for race conditions, TTL correctness, broadcast efficiency
    """

    def __init__(
        self,
        name: str = "presence_agent",
        working_dir: str = "./output",
        event_bus=None,
        shared_state=None,
        skill_loader=None,  # Kept for backwards compatibility, not used
        **kwargs,
    ):
        super().__init__(
            name=name,
            working_dir=working_dir,
            event_bus=event_bus,
            shared_state=shared_state,
            **kwargs,
        )
        self.skill_loader = skill_loader  # Store locally if needed
        self.logger = logger.bind(agent=self.name)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent responds to."""
        return [
            EventType.WEBSOCKET_HANDLER_GENERATED,
            EventType.REDIS_PUBSUB_CONFIGURED,
            # Custom event for explicit presence requests
            # EventType.PRESENCE_TRACKING_NEEDED,  # Add when defined in event_bus.py
        ]

    def should_act(self, events: list[Event]) -> bool:
        """Determine if agent should act based on events."""
        if not events:
            return False

        for event in events:
            # Act when WebSocket handlers are ready (presence depends on WS)
            if event.type == EventType.WEBSOCKET_HANDLER_GENERATED:
                return True
            # Act when Redis pub/sub is configured (presence uses Redis)
            if event.type == EventType.REDIS_PUBSUB_CONFIGURED:
                return True

        return False

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "websocket"  # Uses WebSocket context for presence features

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate presence tracking infrastructure.

        Uses AutoGen team if available, otherwise falls back to legacy mode.
        """
        self.logger.info(
            "presence_agent_acting",
            event_count=len(events),
            event_types=[e.event_type.value for e in events],
        )

        # Use AutoGen team pattern if available
        if self.is_autogen_available():
            return await self._act_with_autogen_team(events)

        # Fallback to legacy implementation
        return await self._act_legacy(events)

    # -------------------------------------------------------------------------
    # AutoGen Team Implementation
    # -------------------------------------------------------------------------

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """Execute presence generation using AutoGen RoundRobinGroupChat."""
        self.logger.info("presence_autogen_team_starting")

        try:
            # Get RAG context for presence patterns
            context = await self.get_task_context(
                query="presence tracking online offline typing indicators heartbeat read receipts Redis NestJS",
                epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
            )

            # Build task prompt with context
            presence_prompt = self._build_presence_prompt(events)

            # Inject RAG results into prompt
            if context and context.rag_results:
                presence_prompt += "\n\n## Relevant Code Examples (from RAG)"
                for result in context.rag_results[:3]:
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:500]
                    score = result.get("score", 0)
                    presence_prompt += f"\n### {file_path} (score: {score:.2f})\n```\n{content}\n```"

                self.logger.info(
                    "rag_context_injected",
                    rag_results_count=len(context.rag_results),
                )

            task = self.build_task_prompt(events, extra_context=presence_prompt)

            # Create Claude Code tools for the Operator
            claude_code_tools = self._create_claude_code_tools()

            # Create Operator + Validator team
            team = self.create_team(
                operator_name="PresenceOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="PresenceValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=claude_code_tools,
                max_turns=12,
            )

            # Execute team
            result = await self.run_team(team, task)

            if result["success"]:
                self.logger.info(
                    "presence_generation_complete",
                    files_created=result.get("files_mentioned", []),
                )

                return Event(
                    event_type=EventType.GENERATION_COMPLETE,  # Or PRESENCE_UPDATED when defined
                    source=self.name,
                    data={
                        "agent": self.name,
                        "task": "presence_tracking",
                        "files": result.get("files_mentioned", []),
                        "result_summary": result.get("result_text", "")[:500],
                        "features": [
                            "online_offline_status",
                            "typing_indicators",
                            "read_receipts",
                            "last_seen",
                            "presence_broadcast",
                        ],
                    },
                )
            else:
                self.logger.error(
                    "presence_generation_failed",
                    error=result.get("error", "Unknown error"),
                )
                return Event(
                    event_type=EventType.BUILD_FAILED,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "error": result.get("error", "Presence generation failed"),
                    },
                )

        except Exception as e:
            self.logger.exception("presence_autogen_team_error", error=str(e))
            return Event(
                event_type=EventType.BUILD_FAILED,
                source=self.name,
                data={"agent": self.name, "error": str(e)},
            )

    def _build_presence_prompt(self, events: list[Event]) -> str:
        """Build detailed prompt for presence generation."""
        # Extract context from events
        websocket_context = ""
        redis_context = ""

        for event in events:
            if event.type == EventType.WEBSOCKET_HANDLER_GENERATED:
                websocket_context = event.data.get("result_summary", "")
            elif event.type == EventType.REDIS_PUBSUB_CONFIGURED:
                redis_context = event.data.get("result_summary", "")

        return f"""
## Presence Tracking System Generation

### Context
WebSocket handlers have been generated. Now implement presence tracking features.

{f"WebSocket Context: {websocket_context}" if websocket_context else ""}
{f"Redis Context: {redis_context}" if redis_context else ""}

### Required Components

#### 1. Presence Service (`src/presence/presence.service.ts`)
- Redis-backed user presence state
- Methods: setOnline, setOffline, getStatus, getOnlineUsers
- Heartbeat support with configurable TTL (default: 60s)
- Batch status queries for contact lists

#### 2. Typing Indicator Handler (`src/presence/typing.service.ts`)
- Start/stop typing events per conversation
- Auto-expire typing after 5 seconds (TTL)
- Support for group conversations (multiple typers)
- Debounce rapid typing events

#### 3. Read Receipt Service (`src/presence/receipts.service.ts`)
- Message states: SENT → DELIVERED → READ
- Batch delivery receipts (when app comes to foreground)
- Read receipt with timestamp
- Privacy option to disable read receipts

#### 4. Presence Gateway (`src/presence/presence.gateway.ts`)
- WebSocket events: user:online, user:offline, user:typing, user:stopped_typing
- Subscribe to presence updates for contacts
- Efficient broadcasting (only to relevant users)

#### 5. Last Seen Service (`src/presence/last-seen.service.ts`)
- Update on disconnect or explicit offline
- Privacy setting: show to everyone / contacts only / nobody
- Format: "online", "last seen today at 10:30", "last seen yesterday"

### Technical Requirements
- Use Redis SETEX for TTL-based expiry
- Use Redis Pub/Sub for real-time presence broadcasts
- Implement connection cleanup on WebSocket disconnect
- Handle reconnection gracefully (restore presence state)
- Rate limit presence updates (max 1 per second per user)

### Output Directory
{self.working_dir}
"""

    def _get_operator_system_prompt(self) -> str:
        """System prompt for PresenceOperator agent."""
        return """You are PresenceOperator, an expert in real-time presence systems.

Your role is to generate production-ready presence tracking code for a messaging platform.

## Expertise
- Redis-based presence state management
- WebSocket event handling for real-time updates
- TTL-based auto-expiry for typing indicators
- Efficient presence broadcasting patterns
- Race condition prevention in distributed systems

## Code Standards
1. Use NestJS with @nestjs/websockets and Socket.io
2. Redis client: ioredis with connection pooling
3. TypeScript with strict types
4. Handle edge cases: reconnection, tab switching, network loss
5. Implement proper cleanup on disconnect

## Key Patterns
- Presence heartbeat with sliding window TTL
- Typing indicator debouncing
- Batched read receipt updates
- Contact-filtered presence broadcasts

When you receive a task:
1. Analyze the requirements carefully
2. Use the generate_presence_code tool to create each component
3. Ensure all services integrate with the existing WebSocket gateway
4. Handle error cases and edge conditions

After completing all components, say "TERMINATE" to signal completion."""

    def _get_validator_system_prompt(self) -> str:
        """System prompt for PresenceValidator agent."""
        return """You are PresenceValidator, a code reviewer specialized in real-time systems.

Your role is to review presence tracking code for correctness and reliability.

## Review Checklist
1. **Race Conditions**: Check for concurrent update issues
2. **TTL Correctness**: Verify expiry times are appropriate
3. **Memory Leaks**: Ensure subscriptions are cleaned up
4. **Broadcast Efficiency**: Only send to relevant recipients
5. **Error Handling**: Graceful degradation on Redis failures
6. **Privacy**: Respect user privacy settings

## Common Issues to Catch
- Missing cleanup on WebSocket disconnect
- Typing indicator not expiring
- Read receipts sent to wrong users
- Presence updates without rate limiting
- Last seen not updating on disconnect

## Review Process
1. Check each generated file for correctness
2. Verify integration between services
3. Look for missing error handling
4. Ensure Redis operations are atomic where needed

If code passes review, respond with "APPROVED - [summary]"
If issues found, respond with "NEEDS_FIX - [specific issues]"

When all code is approved, say "TERMINATE" to signal completion."""

    def _create_claude_code_tools(self) -> list:
        """Create Claude Code as FunctionTool for AutoGen."""
        try:
            from autogen_core.tools import FunctionTool
        except ImportError:
            self.logger.warning("autogen_tools_not_available")
            return []

        from src.tools.claude_code_tool import ClaudeCodeTool

        claude_tool = ClaudeCodeTool(
            working_dir=self.working_dir,
            skill_loader=self.skill_loader,
        )

        async def generate_presence_code(
            prompt: str,
            context: str = "",
            file_type: str = "service",
        ) -> dict:
            """
            Generate presence tracking code using Claude Code.

            Args:
                prompt: What to generate (e.g., "Create typing indicator service")
                context: Additional context (existing code, requirements)
                file_type: Type of file (service, gateway, dto)

            Returns:
                Dictionary with success status and generated file info
            """
            full_prompt = f"""
## Task
{prompt}

## File Type
{file_type}

## Context
{context}

## Requirements
- NestJS with TypeScript
- ioredis for Redis operations
- Socket.io for WebSocket events
- Proper error handling
- Clean disconnect handling
"""

            try:
                result = await claude_tool.execute(
                    prompt=full_prompt,
                    context=context,
                    agent_type="backend",
                )

                return {
                    "success": result.success,
                    "files_created": result.files_created if hasattr(result, "files_created") else [],
                    "files_modified": result.files_modified if hasattr(result, "files_modified") else [],
                    "summary": result.summary if hasattr(result, "summary") else "",
                    "error": result.error if hasattr(result, "error") else None,
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "files_created": [],
                    "files_modified": [],
                }

        return [
            FunctionTool(
                func=generate_presence_code,
                name="generate_presence_code",
                description="Generate presence tracking code (services, gateways, DTOs) using Claude Code. "
                "Use for: presence service, typing indicators, read receipts, last seen.",
            )
        ]

    # -------------------------------------------------------------------------
    # Legacy Implementation (Fallback)
    # -------------------------------------------------------------------------

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Legacy implementation without AutoGen."""
        self.logger.info("presence_legacy_mode")

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool

            claude_tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                skill_loader=self.skill_loader,
            )

            prompt = self._build_presence_prompt(events)

            result = await claude_tool.execute(
                prompt=prompt,
                context="Generate complete presence tracking system",
                agent_type="backend",
            )

            if result.success:
                return Event(
                    event_type=EventType.GENERATION_COMPLETE,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "task": "presence_tracking",
                        "files": result.files_created if hasattr(result, "files_created") else [],
                    },
                )
            else:
                return Event(
                    event_type=EventType.BUILD_FAILED,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "error": result.error if hasattr(result, "error") else "Unknown error",
                    },
                )

        except Exception as e:
            self.logger.exception("presence_legacy_error", error=str(e))
            return Event(
                event_type=EventType.BUILD_FAILED,
                source=self.name,
                data={"agent": self.name, "error": str(e)},
            )

    # -------------------------------------------------------------------------
    # Swarm Handoff Configuration (for AutogenSwarmMixin)
    # -------------------------------------------------------------------------

    def get_handoff_targets(self) -> dict[str, str]:
        """Define handoff targets for Swarm pattern."""
        return {
            "PRESENCE_UPDATED": "encryption_agent",  # After presence, setup E2EE
            "PRESENCE_TRACKING_COMPLETE": "validation_team_agent",  # Validate presence
        }

    def get_agent_capabilities(self) -> list[str]:
        """Define capabilities for Swarm routing."""
        return [
            "presence",
            "typing_indicators",
            "read_receipts",
            "online_status",
            "last_seen",
            "redis",
            "websocket",
        ]
