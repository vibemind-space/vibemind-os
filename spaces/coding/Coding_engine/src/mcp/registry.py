"""
MCP Agent Registry - Loads and validates MCP agents from servers.json.

This module discovers available MCP agents and checks if their requirements
(environment variables, services) are met for spawning.
"""
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


@dataclass
class MCPAgentInfo:
    """Information about an MCP agent from the registry."""
    name: str
    active: bool
    server_type: str  # stdio, custom, docker
    command: str
    args: List[str]
    env_vars: Dict[str, str]
    description: str
    requires: List[str] = field(default_factory=list)  # Required env vars
    category: str = "core"  # core, network, service, external
    cwd: Optional[str] = None
    read_timeout: int = 120


# Agent category mappings
AGENT_CATEGORIES = {
    # Core - Always available, no external deps
    "core": ["time", "memory", "git", "filesystem", "desktop", "windows-core",
             "taskmanager", "docker"],
    # Network - Requires internet
    "network": ["fetch", "context7", "youtube"],
    # Service - Requires local service running
    "service": ["qdrant", "redis", "postgres"],
    # External - Requires API key
    "external": ["brave-search", "tavily", "github", "supabase", "n8n",
                 "supermemory"],
    # Browser - Requires browser automation
    "browser": ["playwright"],
    # Custom Python agents
    "custom": ["npm", "prisma", "claude-code"],
}


def _categorize_agent(name: str) -> str:
    """Determine agent category by name."""
    for category, agents in AGENT_CATEGORIES.items():
        if name in agents:
            return category
    return "core"  # Default


def _extract_requires(server: dict) -> List[str]:
    """Extract required environment variables from server config."""
    requires = []
    env_vars = server.get("env_vars", {})

    for key, value in env_vars.items():
        # If value references env var (e.g., "env:GITHUB_TOKEN")
        if isinstance(value, str) and value.startswith("env:"):
            env_name = value.split(":", 1)[1]
            requires.append(env_name)
        # Or if the key itself is the requirement
        elif key.endswith("_KEY") or key.endswith("_TOKEN") or key.endswith("_URL"):
            requires.append(key)

    return requires


class MCPRegistry:
    """
    Registry for discovering and validating MCP agents.

    Loads agent configurations from servers.json and provides methods
    to query available agents and check their requirements.

    Usage:
        registry = MCPRegistry()

        # List all active agents
        for agent in registry.list_agents():
            print(f"{agent.name}: {agent.description}")

        # Check if specific agent is available
        if registry.is_available("playwright"):
            info = registry.get_agent("playwright")
    """

    def __init__(self, servers_json_path: str = None):
        """
        Initialize the registry.

        Args:
            servers_json_path: Path to servers.json. If None, uses default location.
        """
        if servers_json_path:
            self.servers_json = Path(servers_json_path)
        else:
            # Find servers.json relative to project root
            project_root = Path(__file__).parent.parent.parent
            self.servers_json = project_root / "mcp_plugins" / "servers" / "servers.json"

        self._agents: Dict[str, MCPAgentInfo] = {}
        self._load_registry()

        logger.info("mcp_registry_loaded",
                   agents_count=len(self._agents),
                   path=str(self.servers_json))

    def _load_registry(self):
        """Load agents from servers.json."""
        if not self.servers_json.exists():
            logger.warning("servers_json_not_found", path=str(self.servers_json))
            return

        try:
            data = json.loads(self.servers_json.read_text(encoding='utf-8'))

            for server in data.get("servers", []):
                if not server.get("active", False):
                    continue

                name = server.get("name", "")
                if not name:
                    continue

                self._agents[name] = MCPAgentInfo(
                    name=name,
                    active=server.get("active", False),
                    server_type=server.get("type", "stdio"),
                    command=server.get("command", ""),
                    args=server.get("args", []),
                    env_vars=server.get("env_vars", {}),
                    description=server.get("description", ""),
                    requires=_extract_requires(server),
                    category=_categorize_agent(name),
                    cwd=server.get("cwd"),
                    read_timeout=server.get("read_timeout_seconds", 120),
                )

        except json.JSONDecodeError as e:
            logger.error("servers_json_parse_error", error=str(e))
        except Exception as e:
            logger.error("registry_load_error", error=str(e))

    def get_agent(self, name: str) -> Optional[MCPAgentInfo]:
        """
        Get agent info by name.

        Args:
            name: Agent name (e.g., "playwright", "supermemory")

        Returns:
            MCPAgentInfo if found, None otherwise
        """
        return self._agents.get(name)

    def list_agents(self, category: str = None) -> List[MCPAgentInfo]:
        """
        List all active agents, optionally filtered by category.

        Args:
            category: Filter by category (core, network, service, external, browser)

        Returns:
            List of MCPAgentInfo objects
        """
        agents = list(self._agents.values())
        if category:
            agents = [a for a in agents if a.category == category]
        return sorted(agents, key=lambda a: a.name)

    def is_available(self, name: str) -> bool:
        """
        Check if agent requirements are met (env vars set).

        Args:
            name: Agent name

        Returns:
            True if agent exists and all requirements are met
        """
        agent = self.get_agent(name)
        if not agent:
            return False

        # Check all required env vars
        for req in agent.requires:
            if not os.getenv(req):
                return False

        return True

    def list_available(self) -> List[str]:
        """
        List names of agents that can be spawned (requirements met).

        Returns:
            List of agent names
        """
        return [
            agent.name for agent in self._agents.values()
            if self.is_available(agent.name)
        ]

    def get_missing_requirements(self, name: str) -> List[str]:
        """
        Get list of missing requirements for an agent.

        Args:
            name: Agent name

        Returns:
            List of missing environment variable names
        """
        agent = self.get_agent(name)
        if not agent:
            return []

        return [req for req in agent.requires if not os.getenv(req)]

    def get_agents_by_event(self, event_type: str) -> List[str]:
        """
        Get agents that should handle a specific event type.

        This is used by MCPProxyAgent to route events to appropriate agents.

        Args:
            event_type: Event type string (e.g., "BUILD_FAILED")

        Returns:
            List of agent names that can handle this event
        """
        # Event to agent mapping
        event_mapping = {
            "BUILD_FAILED": ["npm"],
            "DATABASE_SCHEMA_GENERATED": ["prisma"],
            "E2E_TEST_FAILED": ["playwright"],
            "BROWSER_ERROR": ["playwright"],
            "DEPLOY_SUCCEEDED": ["playwright"],
            "CONTEXT_NEEDED": ["supermemory", "qdrant"],
            "CODE_SEARCH": ["supermemory", "qdrant", "brave-search"],
            "DATABASE_MIGRATION_NEEDED": ["prisma", "postgres"],
            "GIT_COMMIT_NEEDED": ["git", "github"],
        }

        return event_mapping.get(event_type, [])


# Module-level singleton for convenience
_registry_instance: Optional[MCPRegistry] = None


def get_registry() -> MCPRegistry:
    """Get or create the global MCPRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MCPRegistry()
    return _registry_instance


if __name__ == "__main__":
    # Test registry
    print("Testing MCPRegistry...")

    registry = MCPRegistry()

    print(f"\nActive agents: {len(registry.list_agents())}")
    print(f"Available agents: {len(registry.list_available())}")

    print("\nAgents by category:")
    for category in ["core", "network", "service", "external", "browser", "custom"]:
        agents = registry.list_agents(category)
        if agents:
            print(f"  {category}: {', '.join(a.name for a in agents)}")

    print("\nAvailable (requirements met):")
    for name in registry.list_available():
        agent = registry.get_agent(name)
        print(f"  ✓ {name}: {agent.description[:50]}...")

    print("\nUnavailable (missing requirements):")
    for agent in registry.list_agents():
        if not registry.is_available(agent.name):
            missing = registry.get_missing_requirements(agent.name)
            print(f"  ✗ {agent.name}: missing {', '.join(missing)}")
