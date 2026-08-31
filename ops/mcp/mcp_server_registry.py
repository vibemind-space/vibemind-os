"""
MCP Server Registry - Zentrale Registry für alle MCP Server

Diese Registry verwaltet alle verfügbaren MCP Server und deren Tools.
"""

import os
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class MCPServerType(Enum):
    """MCP Server Typen"""
    DOCKER = "docker"
    REDIS = "redis"
    POSTGRES = "postgres"
    PLAYWRIGHT = "playwright"
    FILESYSTEM = "filesystem"
    GIT = "git"
    GITHUB = "github"
    BRAVE_SEARCH = "brave-search"
    TAVILY = "tavily"
    CONTEXT7 = "context7"
    DESKTOP = "desktop"
    MEMORY = "memory"
    SUPABASE = "supabase"
    QDRANT = "qdrant"
    PRISMA = "prisma"
    NPM = "npm"
    N8N = "n8n"
    FETCH = "fetch"
    TASKMANAGER = "taskmanager"


@dataclass
class MCPServerInfo:
    """Informationen über einen MCP Server"""
    server_type: MCPServerType
    name: str
    description: str
    path: str
    agent_file: str
    tools: List[str]
    dependencies: List[str]
    enabled: bool = True
    priority: int = 0  # Höhere Priorität = wird zuerst geladen


class MCPServerRegistry:
    """
    MCP Server Registry - Verwaltet alle verfügbaren MCP Server.
    
    Diese Registry scannt das mcp_plugins/servers Verzeichnis und
    registriert alle verfügbaren MCP Server mit deren Tools.
    """
    
    def __init__(self, servers_dir: str = None):
        """
        Initialisiert die MCP Server Registry.
        
        Args:
            servers_dir: Pfad zum mcp_plugins/servers Verzeichnis
        """
        if servers_dir is None:
            # Pfad zum mcp_plugins/servers Verzeichnis
            servers_dir = os.path.join(
                os.path.dirname(__file__),
                '..',
                'servers'
            )
        
        self.servers_dir = os.path.abspath(servers_dir)
        self.logger = logger.bind(component="mcp_server_registry", servers_dir=self.servers_dir)
        
        # Registry initialisieren
        self._servers: Dict[MCPServerType, MCPServerInfo] = {}
        
        # Server scannen und registrieren
        self._scan_servers()
    
    def _scan_servers(self):
        """Scannt das servers Verzeichnis und registriert alle verfügbaren Server."""
        self.logger.info("scanning_mcp_servers", servers_dir=self.servers_dir)
        
        # Server-Definitionen
        server_definitions = [
            MCPServerInfo(
                server_type=MCPServerType.DOCKER,
                name="Docker",
                description="Docker Container Management Tools",
                path=os.path.join(self.servers_dir, 'docker'),
                agent_file='agent.py',
                tools=[
                    'list_containers',
                    'get_container_logs',
                    'get_container_status',
                    'get_container_stats',
                    'execute_in_container',
                    'get_container_processes',
                    'get_container_ports',
                ],
                dependencies=['docker'],
                priority=100,
            ),
            MCPServerInfo(
                server_type=MCPServerType.REDIS,
                name="Redis",
                description="Redis Database Tools",
                path=os.path.join(self.servers_dir, 'redis'),
                agent_file='agent.py',
                tools=[
                    'get_keys_pattern',
                    'get_key_info',
                    'get_key_value',
                    'analyze_cache_hit_rate',
                    'get_memory_usage',
                    'get_recent_logs',
                    'get_slow_queries',
                    'delete_key',
                    'flush_cache',
                ],
                dependencies=['redis'],
                priority=90,
            ),
            MCPServerInfo(
                server_type=MCPServerType.POSTGRES,
                name="PostgreSQL",
                description="PostgreSQL Database Tools",
                path=os.path.join(self.servers_dir, 'postgres'),
                agent_file='agent.py',
                tools=[
                    'get_slow_queries',
                    'get_table_sizes',
                    'get_connection_stats',
                    'get_schema_info',
                    'get_index_info',
                    'execute_query',
                ],
                dependencies=['postgresql'],
                priority=90,
            ),
            MCPServerInfo(
                server_type=MCPServerType.PLAYWRIGHT,
                name="Playwright",
                description="Browser Automation and Testing Tools",
                path=os.path.join(self.servers_dir, 'playwright'),
                agent_file='agent.py',
                tools=[
                    'run_e2e_test',
                    'capture_screenshot',
                    'get_page_metrics',
                    'run_visual_regression_test',
                    'get_test_coverage',
                ],
                dependencies=['playwright'],
                priority=80,
            ),
            MCPServerInfo(
                server_type=MCPServerType.FILESYSTEM,
                name="Filesystem",
                description="Filesystem Operations Tools",
                path=os.path.join(self.servers_dir, 'filesystem'),
                agent_file='agent.py',
                tools=[
                    'read_file',
                    'write_file',
                    'list_directory',
                    'create_directory',
                    'delete_file',
                    'move_file',
                    'copy_file',
                ],
                dependencies=[],
                priority=100,
            ),
            MCPServerInfo(
                server_type=MCPServerType.GIT,
                name="Git",
                description="Git Version Control Tools",
                path=os.path.join(self.servers_dir, 'git'),
                agent_file='agent.py',
                tools=[
                    'git_status',
                    'git_add',
                    'git_commit',
                    'git_push',
                    'git_pull',
                    'git_branch',
                    'git_checkout',
                    'git_merge',
                ],
                dependencies=['git'],
                priority=70,
            ),
            MCPServerInfo(
                server_type=MCPServerType.GITHUB,
                name="GitHub",
                description="GitHub API Tools",
                path=os.path.join(self.servers_dir, 'github'),
                agent_file='agent.py',
                tools=[
                    'create_repository',
                    'list_repositories',
                    'create_issue',
                    'list_issues',
                    'create_pull_request',
                    'merge_pull_request',
                ],
                dependencies=[],
                priority=60,
            ),
            MCPServerInfo(
                server_type=MCPServerType.BRAVE_SEARCH,
                name="Brave Search",
                description="Brave Search API Tools",
                path=os.path.join(self.servers_dir, 'brave-search'),
                agent_file='agent.py',
                tools=[
                    'search_web',
                    'search_news',
                ],
                dependencies=[],
                priority=50,
            ),
            MCPServerInfo(
                server_type=MCPServerType.TAVILY,
                name="Tavily",
                description="Tavily Search and Extraction Tools",
                path=os.path.join(self.servers_dir, 'tavily'),
                agent_file='agent.py',
                tools=[
                    'search',
                    'extract',
                    'map',
                    'crawl',
                ],
                dependencies=[],
                priority=50,
            ),
            MCPServerInfo(
                server_type=MCPServerType.CONTEXT7,
                name="Context7",
                description="Context7 Documentation Tools",
                path=os.path.join(self.servers_dir, 'context7'),
                agent_file='agent.py',
                tools=[
                    'query_docs',
                    'resolve_library_id',
                ],
                dependencies=[],
                priority=40,
            ),
            MCPServerInfo(
                server_type=MCPServerType.DESKTOP,
                name="Desktop",
                description="Desktop Automation Tools",
                path=os.path.join(self.servers_dir, 'desktop'),
                agent_file='agent.py',
                tools=[
                    'take_screenshot',
                    'get_clipboard',
                    'set_clipboard',
                    'open_application',
                    'close_application',
                ],
                dependencies=[],
                priority=30,
            ),
            MCPServerInfo(
                server_type=MCPServerType.MEMORY,
                name="Memory",
                description="Memory Storage Tools",
                path=os.path.join(self.servers_dir, 'memory'),
                agent_file='agent.py',
                tools=[
                    'store_memory',
                    'retrieve_memory',
                    'search_memory',
                    'delete_memory',
                ],
                dependencies=[],
                priority=30,
            ),
            MCPServerInfo(
                server_type=MCPServerType.SUPABASE,
                name="Supabase",
                description="Supabase Database Tools",
                path=os.path.join(self.servers_dir, 'supabase'),
                agent_file='agent.py',
                tools=[
                    'query',
                    'insert',
                    'update',
                    'delete',
                    'list_tables',
                ],
                dependencies=[],
                priority=60,
            ),
            MCPServerInfo(
                server_type=MCPServerType.QDRANT,
                name="Qdrant",
                description="Qdrant Vector Database Tools",
                path=os.path.join(self.servers_dir, 'qdrant'),
                agent_file='agent.py',
                tools=[
                    'create_collection',
                    'delete_collection',
                    'insert_points',
                    'search_points',
                    'delete_points',
                ],
                dependencies=[],
                priority=60,
            ),
            MCPServerInfo(
                server_type=MCPServerType.PRISMA,
                name="Prisma",
                description="Prisma ORM Tools",
                path=os.path.join(self.servers_dir, 'prisma'),
                agent_file='agent.py',
                tools=[
                    'generate_client',
                    'migrate',
                    'seed',
                    'studio',
                ],
                dependencies=[],
                priority=50,
            ),
            MCPServerInfo(
                server_type=MCPServerType.NPM,
                name="NPM",
                description="NPM Package Manager Tools",
                path=os.path.join(self.servers_dir, 'npm'),
                agent_file='agent.py',
                tools=[
                    'install',
                    'uninstall',
                    'update',
                    'list',
                    'search',
                ],
                dependencies=['npm'],
                priority=40,
            ),
            MCPServerInfo(
                server_type=MCPServerType.N8N,
                name="n8n",
                description="n8n Workflow Automation Tools",
                path=os.path.join(self.servers_dir, 'n8n'),
                agent_file='agent.py',
                tools=[
                    'create_workflow',
                    'execute_workflow',
                    'list_workflows',
                    'delete_workflow',
                ],
                dependencies=[],
                priority=40,
            ),
            MCPServerInfo(
                server_type=MCPServerType.FETCH,
                name="Fetch",
                description="HTTP Fetch Tools",
                path=os.path.join(self.servers_dir, 'fetch'),
                agent_file='agent.py',
                tools=[
                    'fetch_url',
                    'fetch_json',
                    'fetch_text',
                ],
                dependencies=[],
                priority=30,
            ),
            MCPServerInfo(
                server_type=MCPServerType.TASKMANAGER,
                name="TaskManager",
                description="Task Management Tools",
                path=os.path.join(self.servers_dir, 'taskmanager'),
                agent_file='agent.py',
                tools=[
                    'create_task',
                    'list_tasks',
                    'update_task',
                    'delete_task',
                    'complete_task',
                ],
                dependencies=[],
                priority=30,
            ),
        ]
        
        # Server registrieren
        for server_info in server_definitions:
            self._register_server(server_info)
        
        self.logger.info(
            "mcp_servers_registered",
            count=len(self._servers),
            servers=[s.name for s in self._servers.values()],
        )
    
    def _register_server(self, server_info: MCPServerInfo):
        """
        Registriert einen MCP Server.
        
        Args:
            server_info: Server-Informationen
        """
        # Prüfen, ob Server existiert
        if not os.path.exists(server_info.path):
            self.logger.warning(
                "server_not_found",
                server_type=server_info.server_type.value,
                path=server_info.path,
            )
            server_info.enabled = False
        
        # Prüfen, ob Agent-Datei existiert
        agent_path = os.path.join(server_info.path, server_info.agent_file)
        if not os.path.exists(agent_path):
            self.logger.warning(
                "agent_file_not_found",
                server_type=server_info.server_type.value,
                agent_path=agent_path,
            )
            server_info.enabled = False
        
        # Server registrieren
        self._servers[server_info.server_type] = server_info
        
        self.logger.debug(
            "server_registered",
            server_type=server_info.server_type.value,
            name=server_info.name,
            enabled=server_info.enabled,
            tools_count=len(server_info.tools),
        )
    
    def get_server(self, server_type: MCPServerType) -> Optional[MCPServerInfo]:
        """
        Holt einen MCP Server anhand seines Typs.
        
        Args:
            server_type: Server-Typ
            
        Returns:
            Server-Informationen oder None
        """
        return self._servers.get(server_type)
    
    def get_all_servers(self) -> List[MCPServerInfo]:
        """
        Holt alle registrierten MCP Server.
        
        Returns:
            Liste aller Server-Informationen
        """
        return list(self._servers.values())
    
    def get_enabled_servers(self) -> List[MCPServerInfo]:
        """
        Holt alle aktivierten MCP Server.
        
        Returns:
            Liste aller aktivierten Server-Informationen
        """
        return [s for s in self._servers.values() if s.enabled]
    
    def get_servers_by_priority(self) -> List[MCPServerInfo]:
        """
        Holt alle MCP Server sortiert nach Priorität.
        
        Returns:
            Liste aller Server-Informationen sortiert nach Priorität
        """
        return sorted(self._servers.values(), key=lambda s: s.priority, reverse=True)
    
    def get_tools_for_server(self, server_type: MCPServerType) -> List[str]:
        """
        Holt alle Tools für einen MCP Server.
        
        Args:
            server_type: Server-Typ
            
        Returns:
            Liste aller Tools
        """
        server_info = self.get_server(server_type)
        if server_info:
            return server_info.tools
        return []
    
    def get_all_tools(self) -> Dict[str, List[str]]:
        """
        Holt alle Tools von allen MCP Servern.
        
        Returns:
            Dict mit Server-Typ als Key und Liste von Tools als Value
        """
        return {
            server_type.value: server_info.tools
            for server_type, server_info in self._servers.items()
            if server_info.enabled
        }
    
    def search_tools(self, query: str) -> List[Dict[str, Any]]:
        """
        Sucht nach Tools anhand einer Query.
        
        Args:
            query: Such-Query
            
        Returns:
            Liste von Tool-Informationen
        """
        results = []
        query_lower = query.lower()
        
        for server_type, server_info in self._servers.items():
            if not server_info.enabled:
                continue
            
            for tool in server_info.tools:
                if query_lower in tool.lower():
                    results.append({
                        'server_type': server_type.value,
                        'server_name': server_info.name,
                        'tool': tool,
                        'description': f"{server_info.name} - {tool}",
                    })
        
        self.logger.info(
            "tools_searched",
            query=query,
            results_count=len(results),
        )
        
        return results
    
    def enable_server(self, server_type: MCPServerType):
        """
        Aktiviert einen MCP Server.
        
        Args:
            server_type: Server-Typ
        """
        if server_type in self._servers:
            self._servers[server_type].enabled = True
            self.logger.info(
                "server_enabled",
                server_type=server_type.value,
            )
    
    def disable_server(self, server_type: MCPServerType):
        """
        Deaktiviert einen MCP Server.
        
        Args:
            server_type: Server-Typ
        """
        if server_type in self._servers:
            self._servers[server_type].enabled = False
            self.logger.info(
                "server_disabled",
                server_type=server_type.value,
            )
    
    def get_server_count(self) -> int:
        """
        Holt die Anzahl aller registrierten MCP Server.
        
        Returns:
            Anzahl der Server
        """
        return len(self._servers)
    
    def get_enabled_server_count(self) -> int:
        """
        Holt die Anzahl aller aktivierten MCP Server.
        
        Returns:
            Anzahl der aktivierten Server
        """
        return len([s for s in self._servers.values() if s.enabled])
    
    def print_summary(self):
        """Druckt eine Zusammenfassung aller registrierten MCP Server."""
        print("\n" + "=" * 80)
        print("MCP Server Registry Summary")
        print("=" * 80)
        print(f"Total Servers: {self.get_server_count()}")
        print(f"Enabled Servers: {self.get_enabled_server_count()}")
        print()
        
        for server_info in self.get_servers_by_priority():
            status = "✓" if server_info.enabled else "✗"
            print(f"{status} {server_info.name:20} ({server_info.server_type.value:15}) - {len(server_info.tools)} tools")
            print(f"   Description: {server_info.description}")
            print(f"   Tools: {', '.join(server_info.tools[:3])}{'...' if len(server_info.tools) > 3 else ''}")
            print()
        
        print("=" * 80)


# Singleton-Instanz
_registry_instance: Optional[MCPServerRegistry] = None


def get_registry(servers_dir: str = None) -> MCPServerRegistry:
    """
    Holt die Singleton-Instanz der MCP Server Registry.
    
    Args:
        servers_dir: Optionaler Pfad zum servers Verzeichnis
        
    Returns:
        MCP Server Registry Instanz
    """
    global _registry_instance
    
    if _registry_instance is None:
        _registry_instance = MCPServerRegistry(servers_dir)
    
    return _registry_instance


if __name__ == "__main__":
    # Test: Registry initialisieren und Zusammenfassung drucken
    registry = get_registry()
    registry.print_summary()
    
    # Test: Tools suchen
    print("\nSearching for 'docker' tools:")
    results = registry.search_tools("docker")
    for result in results:
        print(f"  - {result['server_name']}: {result['tool']}")
