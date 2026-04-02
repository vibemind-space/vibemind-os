"""
Agent Factory - Creates specialized agents dynamically based on project profile.

Instead of using fixed agent classes, this factory composes agents with:
1. Project-appropriate system prompts
2. Technology-specific tools
3. Correct file ownership patterns
"""

from dataclasses import dataclass
from typing import Optional, Callable
import structlog

from ..engine.project_analyzer import ProjectProfile, ProjectType, Technology, Domain
from ..prompts.prompt_composer import PromptComposer
from ..tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


@dataclass
class DynamicAgentConfig:
    """Configuration for a dynamically created agent."""
    agent_role: str
    system_prompt: str
    prompt_prefix: str
    file_patterns: list[str]  # Patterns this agent is responsible for
    tools: list[str]  # Tool names this agent can use
    priority: int = 0  # Higher = run first


class AgentFactory:
    """
    Factory for creating specialized agents based on project profile.

    Usage:
        factory = AgentFactory(profile)
        configs = factory.create_agent_configs()

        for config in configs:
            # Use config.system_prompt when invoking Claude
            result = claude_tool.execute(
                prompt=config.prompt_prefix + task_prompt,
                ...
            )
    """

    def __init__(self, profile: ProjectProfile, working_dir: str):
        """
        Initialize factory with project profile.

        Args:
            profile: ProjectProfile from analyzer
            working_dir: Working directory for generated files
        """
        self.profile = profile
        self.working_dir = working_dir
        self.composer = PromptComposer(profile)
        self.logger = logger.bind(component="agent_factory")

    def create_agent_configs(self) -> list[DynamicAgentConfig]:
        """
        Create agent configurations based on project profile.

        Returns:
            List of DynamicAgentConfig for all needed agents
        """
        configs = []

        # Get agent roles from profile
        agent_roles = self.profile.get_agent_types()

        self.logger.info(
            "creating_agent_configs",
            project_type=self.profile.project_type.value,
            roles=agent_roles,
        )

        for role in agent_roles:
            config = self._create_config_for_role(role)
            if config:
                configs.append(config)

        # Sort by priority
        configs.sort(key=lambda c: c.priority, reverse=True)

        return configs

    def _create_config_for_role(self, role: str) -> Optional[DynamicAgentConfig]:
        """Create configuration for a specific agent role."""

        # Get composed system prompt
        system_prompt = self.composer.compose(role)
        prompt_prefix = self.composer.get_agent_prefix(role)

        # Get file patterns and tools for role
        file_patterns = self._get_file_patterns(role)
        tools = self._get_tools(role)
        priority = self._get_priority(role)

        return DynamicAgentConfig(
            agent_role=role,
            system_prompt=system_prompt,
            prompt_prefix=prompt_prefix,
            file_patterns=file_patterns,
            tools=tools,
            priority=priority,
        )

    def _get_file_patterns(self, role: str) -> list[str]:
        """Get file patterns this agent is responsible for."""

        # Base patterns by role
        role_patterns = {
            "electron-main": ["src/main/**", "electron.vite.config.ts"],
            "electron-renderer": ["src/renderer/**", "index.html"],
            "electron-preload": ["src/preload/**"],
            "frontend": ["src/components/**", "src/pages/**", "src/styles/**", "src/hooks/**"],
            "backend": ["src/api/**", "src/routes/**", "src/services/**", "src/models/**"],
            "database": ["src/db/**", "src/models/**", "migrations/**"],
            "testing": ["tests/**", "**/*.test.ts", "**/*.spec.ts"],
            "devops": [".github/**", "Dockerfile*", "docker-compose.*", "*.yml"],
            "security": ["src/auth/**", "src/security/**"],
            "general": ["**/*"],
        }

        return role_patterns.get(role, ["**/*"])

    def _get_tools(self, role: str) -> list[str]:
        """Get tool names available to this agent role."""

        base_tools = ["write_file", "read_file", "list_directory"]

        role_tools = {
            "electron-main": ["create_ipc_handler", "create_window", "create_menu"],
            "electron-preload": ["create_context_bridge"],
            "frontend": ["create_component", "create_hook", "generate_styles"],
            "backend": ["create_endpoint", "create_model", "create_migration"],
            "database": ["create_migration", "create_model", "run_query"],
            "testing": ["create_test", "run_tests", "create_fixture"],
            "devops": ["create_dockerfile", "create_pipeline", "create_k8s_manifest"],
        }

        return base_tools + role_tools.get(role, [])

    def _get_priority(self, role: str) -> int:
        """
        Get execution priority for role.
        Higher priority runs first.
        """
        priorities = {
            # Infrastructure first
            "devops": 100,
            "database": 90,

            # Core application
            "electron-main": 80,
            "electron-preload": 75,
            "backend": 70,

            # UI
            "electron-renderer": 60,
            "frontend": 60,

            # Support
            "security": 50,
            "testing": 40,

            # Fallback
            "general": 0,
        }

        return priorities.get(role, 0)

    def get_agent_for_task(self, task_description: str) -> DynamicAgentConfig:
        """
        Select the best agent for a specific task.

        Args:
            task_description: Description of the task

        Returns:
            Best matching DynamicAgentConfig
        """
        task_lower = task_description.lower()
        configs = self.create_agent_configs()

        # Try to match task to role
        role_keywords = {
            "electron-main": ["main process", "ipcmain", "browserwindow", "app.when", "native menu"],
            "electron-preload": ["preload", "contextbridge", "exposeInMainWorld"],
            "electron-renderer": ["ui", "component", "render", "display", "button", "panel"],
            "frontend": ["ui", "component", "page", "style", "css", "layout"],
            "backend": ["api", "endpoint", "route", "server", "request", "response"],
            "database": ["database", "migration", "model", "query", "table"],
            "testing": ["test", "spec", "assert", "expect", "mock"],
            "devops": ["docker", "deploy", "ci", "cd", "pipeline", "kubernetes"],
            "security": ["auth", "login", "permission", "encrypt", "token"],
        }

        for config in configs:
            keywords = role_keywords.get(config.agent_role, [])
            if any(kw in task_lower for kw in keywords):
                return config

        # Return general agent as fallback
        return configs[-1] if configs else self._create_config_for_role("general")

    def create_claude_tool(
        self,
        config: DynamicAgentConfig,
    ) -> ClaudeCodeTool:
        """
        Create a ClaudeCodeTool configured for this agent.

        Args:
            config: Agent configuration

        Returns:
            Configured ClaudeCodeTool
        """
        return ClaudeCodeTool(
            working_dir=self.working_dir,
            agent_type=config.agent_role,
            system_prompt=config.system_prompt,
        )


def create_agents_for_project(
    profile: ProjectProfile,
    working_dir: str,
) -> list[DynamicAgentConfig]:
    """
    Convenience function to create all agent configs for a project.

    Args:
        profile: ProjectProfile from analyzer
        working_dir: Working directory

    Returns:
        List of agent configurations
    """
    factory = AgentFactory(profile, working_dir)
    return factory.create_agent_configs()
