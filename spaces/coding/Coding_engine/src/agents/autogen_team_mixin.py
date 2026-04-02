"""
Autogen Team Mixin - Bridges AutonomousAgent with autogen-agentchat teams.

This mixin enables AutonomousAgent subclasses to use autogen-agentchat
(AG2 0.4.x) teams inside their act() methods. It provides:

- Model client initialization (reuses mcp_plugins/servers/shared/model_init.py)
- MCPToolRegistry → autogen FunctionTool bridging
- EventBus events → autogen task prompt conversion
- Team execution with result parsing
- Helper methods for creating Operator + QA Validator teams

Architecture:
    EventBus → _run_loop → should_act → act() → build_team → team.run(task) → Event
                                                  ↑              ↑
                                         AutogenTeamMixin   RoundRobinGroupChat

Usage:
    class DatabaseAgent(AutonomousAgent, AutogenTeamMixin):
        async def act(self, events):
            task = self.build_task_prompt(events)
            team = self.create_team(
                operator_name="SchemaOperator",
                operator_prompt="Generate Prisma schema...",
                validator_name="SchemaValidator",
                validator_prompt="Validate the schema...",
                tool_categories=["prisma", "npm", "filesystem"],
            )
            result = await self.run_team(team, task)
            if result["success"]:
                return database_schema_generated_event(...)
"""

import inspect
import json
import sys
import os
from typing import Any, Optional
import structlog

logger = structlog.get_logger(__name__)

# Conditional imports — autogen may not be installed in all environments
try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_agentchat.conditions import TextMentionTermination
    from autogen_core.model_context import BufferedChatCompletionContext
    from autogen_core.tools import FunctionTool
    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False
    logger.warning("autogen_not_available",
                   msg="autogen-agentchat not installed, AutogenTeamMixin disabled")


class AutogenTeamMixin:
    """
    Mixin for AutonomousAgent subclasses to use autogen-agentchat teams.

    Requires the host class to provide:
    - self.name: str (agent name)
    - self.working_dir: str (project output directory)
    - self.tool_registry: MCPToolRegistry (from AutonomousAgent.tool_registry)
    - self.shared_state: SharedState (from AutonomousAgent)
    - self.skill: Optional[Skill] (from AutonomousAgent)
    - self.logger: structlog logger
    """

    _model_client = None
    _qa_model_client = None

    # -------------------------------------------------------------------------
    # Model Client
    # -------------------------------------------------------------------------

    def get_model_client(self, task: str = ""):
        """
        Get or create the autogen model client (cached).

        Uses the shared init_model_client from mcp_plugins which provides
        OpenRouter with intelligent model selection + OpenAI fallback.

        Args:
            task: Task description for intelligent model routing

        Returns:
            OpenAIChatCompletionClient or ResilientModelClient
        """
        if not AUTOGEN_AVAILABLE:
            raise RuntimeError("autogen-agentchat is not installed")

        if self._model_client is None:
            # Add mcp_plugins to path if needed
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            shared_path = os.path.join(project_root, "mcp_plugins", "servers", "shared")
            if shared_path not in sys.path:
                sys.path.insert(0, shared_path)

            from model_init import init_model_client
            agent_id = self.name.lower().replace("agent", "").replace(" ", "-").strip("-")
            self._model_client = init_model_client(agent_id, task)
            self.logger.info("autogen_model_client_initialized",
                             agent=self.name, agent_id=agent_id)

        return self._model_client

    def get_qa_model_client(self, task: str = ""):
        """
        Get a lighter model client for QA validation (cheaper, faster).

        Falls back to the primary model if separate QA client fails.
        """
        if self._qa_model_client is None:
            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                shared_path = os.path.join(project_root, "mcp_plugins", "servers", "shared")
                if shared_path not in sys.path:
                    sys.path.insert(0, shared_path)

                from model_init import init_model_client
                self._qa_model_client = init_model_client("qa-validator", task)
            except Exception:
                # Fall back to primary model
                self._qa_model_client = self.get_model_client(task)

        return self._qa_model_client

    # -------------------------------------------------------------------------
    # Tool Bridging: MCPToolRegistry → autogen FunctionTool
    # -------------------------------------------------------------------------

    def get_autogen_tools(self, categories: list[str] = None) -> list:
        """
        Bridge MCPToolRegistry tools to autogen FunctionTool objects.

        Args:
            categories: Tool categories to include (e.g., ["docker", "npm"]).
                        If None, includes all tools.

        Returns:
            List of FunctionTool objects for use with AssistantAgent
        """
        if not AUTOGEN_AVAILABLE:
            return []

        registry = self.tool_registry
        tools = []

        for tool_info in registry.list_tools():
            if categories and tool_info["category"] not in categories:
                continue

            fn = registry.get_tool(tool_info["name"])
            if fn:
                bridged = self._bridge_tool(
                    tool_info["name"], fn, tool_info["description"]
                )
                if bridged:
                    tools.append(bridged)

        self.logger.debug("autogen_tools_bridged",
                          count=len(tools),
                          categories=categories or "all")
        return tools

    def _bridge_tool(self, tool_name: str, fn, description: str):
        """
        Wrap an MCPToolRegistry callable as an autogen FunctionTool.

        Handles:
        - JSON string result → dict parsing
        - Auto-injection of cwd parameter
        - Error wrapping for tool failures
        """
        working_dir = self.working_dir
        sig = inspect.signature(fn)
        accepts_cwd = 'cwd' in sig.parameters

        def wrapped_tool(**kwargs):
            if accepts_cwd and 'cwd' not in kwargs:
                kwargs['cwd'] = working_dir
            try:
                result_str = fn(**kwargs)
                try:
                    return json.loads(result_str)
                except (json.JSONDecodeError, TypeError):
                    return {"result": result_str}
            except Exception as e:
                return {"error": str(e)}

        # Set function metadata for autogen introspection
        safe_name = tool_name.replace(".", "_")
        wrapped_tool.__name__ = safe_name
        wrapped_tool.__qualname__ = safe_name
        wrapped_tool.__doc__ = description

        # Copy parameter annotations from original function (minus 'cwd')
        params = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'cwd':
                continue  # Auto-injected, hide from autogen
            params[param_name] = param

        from types import FunctionType
        import copy
        new_sig = sig.replace(parameters=list(params.values()))
        wrapped_tool.__signature__ = new_sig

        return FunctionTool(wrapped_tool, description=description)

    # -------------------------------------------------------------------------
    # Event → Task Prompt Conversion
    # -------------------------------------------------------------------------

    def build_task_prompt(self, events: list, extra_context: str = "") -> str:
        """
        Convert EventBus events + skill + SharedState into an autogen task prompt.

        Assembles:
        1. Skill instructions (tier-aware if available)
        2. Current SharedState metrics (build/test/type error status)
        3. Event-specific context (errors, file paths, data)
        4. Extra context from the agent
        5. Completion signal instruction

        Args:
            events: List of Event objects that triggered this action
            extra_context: Additional context from the agent

        Returns:
            Task prompt string for team.run(task=...)
        """
        parts = []

        # 1. Skill instructions
        if hasattr(self, 'skill') and self.skill:
            try:
                instructions = self.skill.get_instructions()
                if instructions:
                    parts.append(f"## Instructions\n{instructions}")
            except Exception:
                pass

        # 2. Working directory context
        parts.append(f"## Working Directory\n{self.working_dir}")

        # 3. SharedState metrics
        if hasattr(self, 'shared_state') and self.shared_state:
            try:
                metrics = self.shared_state.metrics
                status_lines = [
                    f"- Build: {'passing' if metrics.build_success else 'failing' if metrics.build_attempted else 'not attempted'}",
                    f"- Tests: {metrics.tests_passed}/{metrics.total_tests} passed",
                    f"- Type errors: {metrics.type_errors}",
                    f"- Build errors: {metrics.build_errors}",
                ]
                parts.append(f"## Current Project State\n" + "\n".join(status_lines))
            except Exception:
                pass

        # 4. Event context
        if events:
            event_sections = []
            for event in events:
                section = self._format_event_for_prompt(event)
                if section:
                    event_sections.append(section)
            if event_sections:
                parts.append("## Trigger Events\n" + "\n\n".join(event_sections))

        # 5. Extra context from agent
        if extra_context:
            parts.append(f"## Additional Context\n{extra_context}")

        # 6. Completion signal
        parts.append(
            "\n## Completion\n"
            "When you have completed the task successfully, respond with 'TASK_COMPLETE'.\n"
            "If you cannot complete the task, explain why and still end with 'TASK_COMPLETE'."
        )

        return "\n\n".join(parts)

    def _format_event_for_prompt(self, event) -> str:
        """Format a single Event for inclusion in the task prompt."""
        lines = [f"### {event.type.value} (from {event.source})"]

        if not event.success:
            lines.append(f"**Status:** FAILED")

        if event.error_message:
            lines.append(f"**Error:** {event.error_message}")

        if event.file_path:
            lines.append(f"**File:** {event.file_path}")

        # Include typed payload data if available
        if event.typed:
            typed = event.typed
            # TypeErrorPayload
            if hasattr(typed, 'errors_by_file'):
                lines.append(f"**Type Errors:** {getattr(typed, 'error_count', '?')}")
                for file_path, errors in typed.errors_by_file.items():
                    lines.append(f"\n**{file_path}:**")
                    for err in errors[:10]:
                        line_num = err.get('line', '?')
                        msg = err.get('message', str(err))
                        lines.append(f"  Line {line_num}: {msg}")
            # BuildFailurePayload
            elif hasattr(typed, 'build_output'):
                output = typed.build_output[:2000] if typed.build_output else ""
                lines.append(f"**Build Output:**\n```\n{output}\n```")
            # TestFailurePayload
            elif hasattr(typed, 'failed_tests'):
                lines.append(f"**Failed Tests:** {len(typed.failed_tests)}")
                for test in typed.failed_tests[:5]:
                    lines.append(f"  - {test}")

        # Fallback to event.data for untyped events
        elif event.data:
            # Include relevant data keys (limit to avoid huge prompts)
            for key in ['errors', 'error', 'output', 'files', 'message', 'result']:
                if key in event.data:
                    val = event.data[key]
                    if isinstance(val, str):
                        val = val[:1500]  # Truncate long strings
                    elif isinstance(val, list):
                        val = val[:20]  # Truncate long lists
                    lines.append(f"**{key}:** {val}")

        return "\n".join(lines) if len(lines) > 1 else ""

    # -------------------------------------------------------------------------
    # Team Creation Helpers
    # -------------------------------------------------------------------------

    def create_operator(
        self,
        name: str,
        system_message: str,
        tool_categories: list[str] = None,
        tools: list = None,
        buffer_size: int = 20,
        task: str = "",
    ):
        """
        Create an AssistantAgent with tools (the "Operator" role).

        Args:
            name: Agent name (e.g., "SchemaOperator")
            system_message: System prompt for the operator
            tool_categories: MCPToolRegistry categories to include
            tools: Explicit tool list (overrides tool_categories)
            buffer_size: Context buffer size
            task: Task description for model routing

        Returns:
            AssistantAgent configured as an operator
        """
        if not AUTOGEN_AVAILABLE:
            raise RuntimeError("autogen-agentchat is not installed")

        if tools is None:
            tools = self.get_autogen_tools(categories=tool_categories)

        model_client = self.get_model_client(task)

        return AssistantAgent(
            name=name,
            model_client=model_client,
            tools=tools,
            system_message=system_message,
            model_context=BufferedChatCompletionContext(buffer_size=buffer_size),
        )

    def create_qa_validator(
        self,
        name: str,
        system_message: str,
        buffer_size: int = 10,
        task: str = "",
        tools: list = None,
    ):
        """
        Create an AssistantAgent for the "QA Validator" role.

        By default has no tools (review-only). When tools are provided
        (e.g., MCP QA verification tool), the validator can independently
        verify the Operator's work.

        Uses a potentially cheaper/faster model for validation.

        Args:
            name: Agent name (e.g., "SchemaValidator")
            system_message: System prompt for validation
            buffer_size: Context buffer size
            task: Task description for model routing
            tools: Optional list of FunctionTools for QA verification

        Returns:
            AssistantAgent configured as a QA validator
        """
        if not AUTOGEN_AVAILABLE:
            raise RuntimeError("autogen-agentchat is not installed")

        model_client = self.get_qa_model_client(task)

        return AssistantAgent(
            name=name,
            model_client=model_client,
            tools=tools or [],
            system_message=system_message,
            model_context=BufferedChatCompletionContext(buffer_size=buffer_size),
        )

    def create_team(
        self,
        operator_name: str,
        operator_prompt: str,
        validator_name: str,
        validator_prompt: str,
        tool_categories: list[str] = None,
        tools: list = None,
        qa_tools: list = None,
        max_turns: int = 20,
        termination_keyword: str = "TASK_COMPLETE",
        task: str = "",
    ):
        """
        Create a standard Operator + QA Validator team.

        This is the most common team pattern, matching the MCP plugin agents.

        Args:
            operator_name: Name for the operator agent
            operator_prompt: System message for the operator
            validator_name: Name for the QA validator
            validator_prompt: System message for the validator
            tool_categories: MCPToolRegistry categories for operator tools
            tools: Explicit tool list (overrides tool_categories)
            qa_tools: Optional tools for the QA validator (e.g., MCP verification)
            max_turns: Maximum conversation turns
            termination_keyword: Keyword to end the conversation
            task: Task description for model routing

        Returns:
            RoundRobinGroupChat team
        """
        if not AUTOGEN_AVAILABLE:
            raise RuntimeError("autogen-agentchat is not installed")

        operator = self.create_operator(
            name=operator_name,
            system_message=operator_prompt,
            tool_categories=tool_categories,
            tools=tools,
            task=task,
        )

        validator = self.create_qa_validator(
            name=validator_name,
            system_message=validator_prompt,
            task=task,
            tools=qa_tools,
        )

        termination = TextMentionTermination(termination_keyword)

        return RoundRobinGroupChat(
            participants=[operator, validator],
            termination_condition=termination,
            max_turns=max_turns,
        )

    def create_team_with_mcp_qa(self, **kwargs):
        """
        Create a team where the QA Validator can verify via MCP Orchestrator.

        This is a convenience wrapper around create_team() that automatically
        adds the MCP QA verification tool to the QA Validator, allowing it
        to independently check files, run builds, and validate configurations
        using the MCP tool ecosystem.

        Args:
            **kwargs: All arguments forwarded to create_team()
                      (operator_name, operator_prompt, validator_name, etc.)

        Returns:
            RoundRobinGroupChat team with MCP-enabled QA validator
        """
        from src.tools.mcp_qa_tool import create_mcp_qa_tool

        working_dir = getattr(self, "working_dir", ".")
        qa_tool = create_mcp_qa_tool(working_dir=working_dir)

        qa_tools = [qa_tool] if qa_tool else []

        return self.create_team(
            qa_tools=qa_tools,
            **kwargs,
        )

    # -------------------------------------------------------------------------
    # Team Execution
    # -------------------------------------------------------------------------

    async def run_team(self, team, task: str) -> dict:
        """
        Execute an autogen team and parse the result.

        Args:
            team: RoundRobinGroupChat or similar team object
            task: Task prompt string

        Returns:
            Dict with:
            - success (bool): Whether the team completed successfully
            - result_text (str): Final message content
            - messages (list): All messages from the team
            - files_mentioned (list[str]): File paths found in messages
        """
        self.logger.info("autogen_team_starting",
                         agent=self.name, task_length=len(task))

        try:
            result = await team.run(task=task)

            # Extract result text
            result_text = ""
            messages = []
            if hasattr(result, 'messages') and result.messages:
                for msg in result.messages:
                    content = str(msg.content) if hasattr(msg, 'content') else str(msg)
                    source = getattr(msg, 'source', 'Unknown')
                    messages.append({"source": source, "content": content})
                result_text = str(result.messages[-1].content)

            # Detect success — check for error indicators
            success = True
            error_indicators = ["error:", "failed:", "cannot", "unable to"]
            if any(ind in result_text.lower() for ind in error_indicators):
                # Check if it's just reporting errors it fixed vs. actual failure
                if "TASK_COMPLETE" not in result_text:
                    success = False

            # Extract file paths mentioned in messages
            files_mentioned = self._extract_files_from_messages(messages)

            self.logger.info("autogen_team_completed",
                             agent=self.name,
                             success=success,
                             message_count=len(messages),
                             files_mentioned=len(files_mentioned))

            return {
                "success": success,
                "result_text": result_text,
                "messages": messages,
                "files_mentioned": files_mentioned,
            }

        except Exception as e:
            self.logger.error("autogen_team_failed",
                              agent=self.name, error=str(e))
            return {
                "success": False,
                "result_text": f"Team execution failed: {e}",
                "messages": [],
                "files_mentioned": [],
            }

    def _extract_files_from_messages(self, messages: list[dict]) -> list[str]:
        """Extract file paths mentioned in team messages."""
        import re
        files = set()
        # Match common file path patterns
        pattern = re.compile(
            r'(?:^|[\s\'"`])'             # Start or whitespace/quote
            r'((?:src|lib|app|pages|components|prisma|public|config|tests?|e2e)'  # Known dirs
            r'/[\w./\-]+\.[a-z]{1,5})',   # Path with extension
            re.MULTILINE
        )
        for msg in messages:
            content = msg.get("content", "")
            matches = pattern.findall(content)
            files.update(matches)
        return sorted(files)

    # -------------------------------------------------------------------------
    # MCP Tools Integration (New Simplified API)
    # -------------------------------------------------------------------------

    def _create_mcp_tools(self, categories: list[str]) -> list:
        """
        Create MCP tools as AutoGen FunctionTools using MCPToolRegistry.

        This is the simplified API that uses the registry's as_autogen_tools() method.

        Args:
            categories: List of MCP tool categories (e.g., ["docker", "prisma", "npm"])

        Returns:
            List of FunctionTool objects for AutoGen operators

        Example:
            mcp_tools = self._create_mcp_tools(["docker", "prisma"])
            team = self.create_team(tools=mcp_tools)
        """
        if not AUTOGEN_AVAILABLE:
            return []

        from src.mcp.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tools = registry.as_autogen_tools(categories)

        self.logger.debug("mcp_tools_created",
                         categories=categories,
                         tool_count=len(tools))

        return tools

    def _create_combined_tools(
        self,
        mcp_categories: list[str] = None,
        include_claude_code: bool = True,
    ) -> list:
        """
        Create combined tool set: MCP tools + Claude Code tool.

        This is the recommended way to create tools for agents that need both
        code generation (Claude Code) and execution (MCP tools).

        Args:
            mcp_categories: MCP tool categories to include (e.g., ["docker", "npm"])
            include_claude_code: Whether to include Claude Code as a tool

        Returns:
            Combined list of FunctionTool objects

        Example:
            tools = self._create_combined_tools(
                mcp_categories=["prisma", "docker"],
                include_claude_code=True
            )
            team = self.create_team(tools=tools)
        """
        tools = []

        # Add MCP tools
        if mcp_categories:
            mcp_tools = self._create_mcp_tools(mcp_categories)
            tools.extend(mcp_tools)

        # Add Claude Code tool
        if include_claude_code:
            claude_tool = self._create_claude_code_tool()
            if claude_tool:
                tools.append(claude_tool)

        self.logger.debug("combined_tools_created",
                         mcp_count=len(tools) - (1 if include_claude_code else 0),
                         has_claude_code=include_claude_code)

        return tools

    def _create_claude_code_tool(self):
        """
        Create Claude Code as an AutoGen FunctionTool.

        Returns:
            FunctionTool for Claude Code execution or None if not available
        """
        if not AUTOGEN_AVAILABLE:
            return None

        try:
            from src.tools.claude_code_tool import ClaudeCodeTool
        except ImportError:
            self.logger.warning("claude_code_tool_not_available")
            return None

        claude_tool = ClaudeCodeTool(
            working_dir=self.working_dir,
            timeout=300,  # 5 minutes
        )

        async def execute_claude_code(
            prompt: str,
            context: str = "",
            agent_type: str = "backend",
        ) -> dict:
            """
            Execute code generation/fixing using Claude Code CLI.

            Args:
                prompt: Task description (what to generate or fix)
                context: Additional context (error messages, requirements)
                agent_type: Type of task (backend, frontend, devops, testing)

            Returns:
                Dict with success status, generated files, and output
            """
            try:
                result = await claude_tool.execute(
                    prompt=prompt,
                    context=context,
                    agent_type=agent_type,
                )
                return {
                    "success": result.success,
                    "files_created": result.files_created if hasattr(result, "files_created") else [],
                    "files_modified": result.files_modified if hasattr(result, "files_modified") else [],
                    "output": result.output[:2000] if hasattr(result, "output") and result.output else "",
                    "error": result.error if hasattr(result, "error") else None,
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "files_created": [],
                    "files_modified": [],
                }

        return FunctionTool(
            func=execute_claude_code,
            name="claude_code",
            description="Execute code generation or fixing using Claude Code CLI. "
            "Use for: generating new code, fixing errors, refactoring, documentation. "
            "Provide detailed prompts with context for best results.",
        )

    # -------------------------------------------------------------------------
    # Autogen Availability Check
    # -------------------------------------------------------------------------

    @staticmethod
    def is_autogen_available() -> bool:
        """Check if autogen-agentchat is installed and available."""
        return AUTOGEN_AVAILABLE
