"""
Group Management Agent - Generates group chat CRUD and member operations.

This agent is responsible for:
- Generating group CRUD endpoints (create, read, update, delete)
- Implementing member add/remove/role assignment
- Creating admin controls and permissions
- Setting up group notification system

Architecture:
- Uses AutogenTeamMixin for AG2 0.4.x team-based execution
- GroupOperator agent has Claude Code as tool for code generation
- GroupValidator reviews generated code without tool access

Trigger Events:
- API_ROUTES_GENERATED: After REST APIs are ready
- GROUP_MANAGEMENT_NEEDED: Explicit request for group features
- DATABASE_SCHEMA_GENERATED: After group entities are defined

Publishes:
- GROUP_CREATED: When group management code is generated
- GROUP_MANAGEMENT_FAILED: When generation fails
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


class GroupManagementAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent for group chat management code generation.

    Generates:
    - Group CRUD controllers and services
    - Member management (add, remove, promote, demote)
    - Admin controls (mute, ban, settings)
    - Group notification dispatchers
    - Permission middleware

    Supports:
    - NestJS controllers and services
    - Prisma for database operations
    - Socket.io for real-time group updates

    CRITICAL: Group operations must enforce proper authorization:
    - Only admins can modify group settings
    - Only admins can add/remove members
    - Permission checks at service layer
    """

    # Keywords indicating group management features needed
    GROUP_KEYWORDS = [
        "group", "channel", "room", "team",
        "member", "admin", "moderator", "owner",
        "invite", "join", "leave", "kick", "ban",
    ]

    def __init__(
        self,
        name: str,
        event_bus: "EventBus",
        shared_state: "SharedState",
        working_dir: str,
        skill_registry: Optional["SkillRegistry"] = None,
        skill_generator: Optional["DynamicSkillGenerator"] = None,
        **kwargs,
    ):
        """
        Initialize the GroupManagementAgent.

        Args:
            name: Agent name (typically "GroupManagementAgent")
            event_bus: EventBus for communication
            shared_state: Shared state for metrics
            working_dir: Project output directory
            skill_registry: Registry to get skill instructions
            skill_generator: Dynamic skill generator for on-demand skills
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
        self._api_routes_data: Optional[dict] = None
        self._entities_data: Optional[dict] = None
        self._generated_files: list[str] = []

        self.logger = logger.bind(agent=name)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.API_ROUTES_GENERATED,
            EventType.DATABASE_SCHEMA_GENERATED,
            EventType.CONTRACTS_GENERATED,
            # Custom events
            # EventType.GROUP_MANAGEMENT_NEEDED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to generate group management code.

        Acts when:
        - API routes are generated AND contain group-related endpoints
        - Database schema has group entities
        - Explicit group management request received
        """
        for event in events:
            # Primary trigger: API routes with group features
            if event.type == EventType.API_ROUTES_GENERATED:
                self._api_routes_data = event.data
                if self._has_group_features(event.data):
                    self.logger.info(
                        "group_features_detected",
                        routes=event.data.get("routes", [])[:5] if event.data else [],
                    )
                    return True

            # Store entity data for context
            if event.type == EventType.DATABASE_SCHEMA_GENERATED:
                self._entities_data = event.data
                if self._has_group_entities(event.data):
                    self.logger.info(
                        "group_entities_detected",
                        entities=event.data.get("entities", [])[:5] if event.data else [],
                    )
                    return True

            # Check contracts for group interfaces
            if event.type == EventType.CONTRACTS_GENERATED:
                if self._has_group_contracts(event.data):
                    self.logger.info("group_contracts_detected")
                    return True

        return False

    def _has_group_features(self, data: Optional[dict]) -> bool:
        """Check if API routes contain group features."""
        if not data:
            return False

        routes = data.get("routes", [])
        for route in routes:
            path = str(route.get("path", "")).lower()
            for keyword in self.GROUP_KEYWORDS:
                if keyword in path:
                    return True
        return False

    def _has_group_entities(self, data: Optional[dict]) -> bool:
        """Check if database schema contains group entities."""
        if not data:
            return False

        entities = data.get("entities", [])
        for entity in entities:
            name = str(entity).lower() if isinstance(entity, str) else str(entity.get("name", "")).lower()
            if any(kw in name for kw in ["group", "member", "channel"]):
                return True
        return False

    def _has_group_contracts(self, data: Optional[dict]) -> bool:
        """Check if contracts contain group-related interfaces."""
        if not data:
            return False

        interfaces = data.get("interfaces", {})
        for name in interfaces.keys():
            name_lower = name.lower()
            if any(kw in name_lower for kw in self.GROUP_KEYWORDS):
                return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate group management code.

        Uses AutoGen team pattern when available:
        - GroupOperator: Has Claude Code tool for code generation
        - GroupValidator: Reviews code without tool access

        Fallback: Direct Claude Code tool execution.
        """
        self.logger.info("generating_group_management_code")

        # Use AutoGen team pattern if available
        if self.is_autogen_available():
            return await self._act_with_autogen_team(events)

        # Fallback to legacy execution
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Execute group management code generation using AutoGen team pattern.

        The team consists of:
        - GroupOperator: Has Claude Code tool, generates NestJS group management code
        - GroupValidator: Reviews generated code for security and patterns
        """
        try:
            # Get skill instructions for context
            skill_instructions = await self._get_skill_instructions()

            # Build extra context for the task prompt
            extra_context = self._build_generation_prompt(skill_instructions)

            # Build task prompt using mixin helper
            task = self.build_task_prompt(events, extra_context=extra_context)

            # Create Claude Code tool for the operator
            claude_code_tools = self._create_claude_code_tools()

            # Create the Operator + Validator team
            team = self.create_team(
                operator_name="GroupOperator",
                operator_prompt=self._get_operator_system_prompt(),
                validator_name="GroupValidator",
                validator_prompt=self._get_validator_system_prompt(),
                tools=claude_code_tools,
                max_turns=15,
                task="Generate NestJS group management endpoints",
            )

            # Execute the team
            result = await self.run_team(team, task)

            if result["success"]:
                files_mentioned = result.get("files_mentioned", [])

                self.logger.info(
                    "group_management_generated_via_autogen",
                    files=files_mentioned,
                    message_count=len(result.get("messages", [])),
                )

                return Event(
                    type=EventType.GROUP_CREATED,
                    source=self.name,
                    data={
                        "files": files_mentioned,
                        "features": ["crud", "members", "admin_controls", "notifications"],
                        "autogen_result": result.get("result_text", "")[:500],
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "group_management_failed_via_autogen",
                    error=result.get("result_text", "Unknown error")[:200],
                )

                return Event(
                    type=EventType.GROUP_MANAGEMENT_FAILED,
                    source=self.name,
                    data={"error": result.get("result_text", "AutoGen team failed")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("group_autogen_error")
            self.logger.info("falling_back_to_legacy_execution")
            return await self._act_legacy(events)

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy execution path using direct Claude Code tool.
        """
        try:
            skill_instructions = await self._get_skill_instructions()
            prompt = self._build_generation_prompt(skill_instructions)
            result = await self._generate_group_code(prompt)

            if result.get("success"):
                self._generated_files = result.get("files", [])

                self.logger.info(
                    "group_management_generated",
                    files=self._generated_files,
                )

                return Event(
                    type=EventType.GROUP_CREATED,
                    source=self.name,
                    data={
                        "files": self._generated_files,
                        "features": ["crud", "members", "admin_controls", "notifications"],
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "group_management_failed",
                    error=result.get("error", "Unknown error"),
                )

                return Event(
                    type=EventType.GROUP_MANAGEMENT_FAILED,
                    source=self.name,
                    data={"error": result.get("error")},
                    success=False,
                )

        except Exception as e:
            self.logger.exception("group_agent_error")
            return system_error_event(
                source=self.name,
                error=str(e),
                context="Group management generation",
            )

    def _create_claude_code_tools(self) -> list:
        """Create Claude Code as a FunctionTool for AutoGen operators."""
        try:
            from autogen_core.tools import FunctionTool
        except ImportError:
            self.logger.warning("autogen_tools_not_available")
            return []

        from ..tools.claude_code_tool import ClaudeCodeTool

        claude_tool = ClaudeCodeTool(
            working_dir=self.working_dir,
            timeout=300,
        )

        async def generate_group_code(
            prompt: str,
            context: str = "",
        ) -> dict:
            """
            Generate group management code using Claude Code CLI.

            Args:
                prompt: Description of what group management code to generate
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

        tool = FunctionTool(
            generate_group_code,
            description=(
                "Generate NestJS group management code using Claude Code. "
                "Provide a detailed prompt describing the group CRUD operations, "
                "member management, admin controls, and permission requirements."
            ),
        )

        return [tool]

    def _get_operator_system_prompt(self) -> str:
        """Get system prompt for GroupOperator agent."""
        return f"""You are GroupOperator, an expert in generating NestJS group management features.

Your role:
1. Use the generate_group_code tool to create group management code
2. Generate complete, production-ready NestJS code
3. Follow best practices for authorization and permissions

Working Directory: {self.working_dir}

CRITICAL REQUIREMENTS:
- Generate GroupController with full CRUD endpoints
- Create GroupService with business logic
- Implement member management (add, remove, promote, demote)
- Add admin controls (mute, ban, settings modification)
- Create permission guards for authorization
- Generate DTOs with class-validator decorators
- NO MOCKS - Connect to real Prisma database
- Handle errors gracefully with proper HTTP status codes

Code Structure:
- src/groups/groups.controller.ts - REST endpoints
- src/groups/groups.service.ts - Business logic
- src/groups/dto/ - CreateGroupDto, UpdateGroupDto, AddMemberDto, etc.
- src/groups/guards/ - GroupAdminGuard, GroupMemberGuard
- src/groups/groups.module.ts - Module registration

API Endpoints to Generate:
- POST /groups - Create new group
- GET /groups - List user's groups
- GET /groups/:id - Get group details
- PATCH /groups/:id - Update group (admin only)
- DELETE /groups/:id - Delete group (owner only)
- POST /groups/:id/members - Add member (admin only)
- DELETE /groups/:id/members/:userId - Remove member (admin only)
- PATCH /groups/:id/members/:userId/role - Change member role

Permission Levels:
- Owner: Full control, can delete group
- Admin: Can manage members and settings
- Member: Can read and participate
- Banned: No access

After completing all code generation, say TASK_COMPLETE."""

    def _get_validator_system_prompt(self) -> str:
        """Get system prompt for GroupValidator agent."""
        return """You are GroupValidator, a code reviewer specializing in secure group management systems.

Your role:
1. Review the code generated by GroupOperator
2. Verify proper authorization at every endpoint
3. Check for security vulnerabilities
4. Ensure database operations are correct

Review Checklist:
- [ ] All endpoints have proper guards (GroupAdminGuard, etc.)
- [ ] Permission checks happen at service layer, not just controller
- [ ] DTOs validate all input properly
- [ ] Prisma queries are safe from injection
- [ ] Error messages don't leak sensitive information
- [ ] Member operations check authorization before execution
- [ ] Role changes follow hierarchy (can't promote above own role)
- [ ] Owner cannot be removed or demoted

Security Requirements:
- [ ] No direct object reference vulnerabilities
- [ ] Rate limiting considerations documented
- [ ] Input validation on all user-provided data
- [ ] Proper TypeScript types throughout

If you find issues:
1. Clearly describe the security risk
2. Explain the attack vector
3. Suggest the fix
4. Ask the Operator to regenerate if needed

If the code meets all requirements, confirm approval and say TASK_COMPLETE."""

    async def _get_skill_instructions(self) -> str:
        """Get skill instructions for group management generation."""
        if self.skill_generator:
            try:
                tech_stack = {}
                if hasattr(self.shared_state, "tech_stack"):
                    tech_stack = self.shared_state.tech_stack or {}

                skill = await self.skill_generator.generate(
                    task_type="nestjs_controller",
                    tech_stack=tech_stack,
                    requirements=[],
                )
                return skill.instructions

            except Exception as e:
                self.logger.warning(
                    "dynamic_skill_generation_failed",
                    error=str(e),
                )

        if self.skill_registry:
            skill = self.skill_registry.get_skill("api-generation")
            if skill:
                return skill.instructions

        return self._default_group_instructions()

    def _default_group_instructions(self) -> str:
        """Default instructions for group management generation."""
        return """
## Group Management Generation Instructions

Generate NestJS group management following these patterns:

1. **Group Controller**:
   ```typescript
   @Controller('groups')
   @UseGuards(JwtAuthGuard)
   export class GroupsController {
     @Post()
     create(@Body() dto: CreateGroupDto, @CurrentUser() user: User) { ... }

     @Get(':id')
     @UseGuards(GroupMemberGuard)
     findOne(@Param('id') id: string) { ... }

     @Patch(':id')
     @UseGuards(GroupAdminGuard)
     update(@Param('id') id: string, @Body() dto: UpdateGroupDto) { ... }
   }
   ```

2. **Group Service**:
   ```typescript
   @Injectable()
   export class GroupsService {
     constructor(private prisma: PrismaService) {}

     async addMember(groupId: string, userId: string, role: GroupRole) {
       // Check if requester has permission
       // Add member with role
       // Notify via WebSocket
     }
   }
   ```

3. **Permission Guards**:
   ```typescript
   @Injectable()
   export class GroupAdminGuard implements CanActivate {
     async canActivate(context: ExecutionContext) {
       const user = context.switchToHttp().getRequest().user;
       const groupId = context.switchToHttp().getRequest().params.id;
       const membership = await this.getMembership(groupId, user.id);
       return membership?.role in ['OWNER', 'ADMIN'];
     }
   }
   ```

CRITICAL:
- NO MOCKS - Connect to real Prisma database
- Validate all incoming data with class-validator
- Check permissions at service layer, not just guards
- Handle edge cases (last admin, owner transfer)
"""

    def _build_generation_prompt(self, skill_instructions: str) -> str:
        """Build the complete generation prompt."""
        entities_context = ""
        if self._entities_data:
            entities = self._entities_data.get("entities", [])
            entities_context = f"\n\nAvailable Entities:\n" + "\n".join(
                f"- {e}" for e in entities[:10]
            )

        routes_context = ""
        if self._api_routes_data:
            routes = self._api_routes_data.get("routes", [])
            group_routes = [r for r in routes if any(kw in str(r.get("path", "")).lower() for kw in self.GROUP_KEYWORDS)]
            if group_routes:
                routes_context = f"\n\nExisting Group Routes:\n" + "\n".join(
                    f"- {r.get('method', 'GET')} {r.get('path', '/unknown')}"
                    for r in group_routes[:10]
                )

        return f"""
{skill_instructions}

## Context
{entities_context}
{routes_context}

## Task
Generate complete group management code for a WhatsApp-like messaging platform:

1. **Group CRUD Operations**
   - Create group with name, description, avatar
   - Update group settings (name, description, privacy)
   - Delete group (owner only)
   - List user's groups with pagination

2. **Member Management**
   - Add members (admin only)
   - Remove members (admin only, can't remove owner)
   - Promote/demote members (owner only)
   - Leave group voluntarily

3. **Admin Controls**
   - Mute members for duration
   - Ban members from rejoining
   - Set group privacy (public/private/invite-only)
   - Pin important messages

4. **Notifications**
   - Emit WebSocket events for group updates
   - Member added/removed notifications
   - Role change notifications

Generate the complete implementation with:
- Controllers with proper guards
- Services with business logic
- DTOs with validation
- Guards for permission checks
- Module registration
"""

    async def _generate_group_code(self, prompt: str) -> dict:
        """Execute the code generation using Claude Code tool."""
        from ..tools.claude_code_tool import ClaudeCodeTool

        try:
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                timeout=300,
            )

            result = await tool.execute(
                prompt=prompt,
                context="Group management generation",
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
