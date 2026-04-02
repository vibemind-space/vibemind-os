"""
MCP Workbench - Lädt alle MCP Server für AutoGen Integration

Dieser Modul erstellt eine zentrale Workbench, die alle konfigurierten
MCP Server aus servers.json lädt und für AutoGen Agents verfügbar macht.
"""
import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# OpenAI has a limit of 128 tools maximum
MAX_TOOLS = 128

# Priority order for servers (most important first)
# Tools from these servers are loaded first before hitting the limit
PRIORITY_SERVERS = [
    "filesystem",   # Core file operations
    "docker",       # Container management
    "playwright",   # Browser automation & testing
    "redis",        # Cache/queue operations
    "context7",     # Documentation lookup
    "memory",       # Knowledge graph
    "time",         # Time operations
    "taskmanager",  # Task management
    "fetch",        # HTTP requests
    "tavily",       # Web search
]

# AutoGen MCP imports (mit Fallback für fehlende Dependencies)
try:
    from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams, mcp_server_tools
    AUTOGEN_MCP_AVAILABLE = True
except ImportError:
    logger.warning("autogen_ext.tools.mcp nicht verfügbar. Installiere mit: pip install autogen-ext[mcp]")
    AUTOGEN_MCP_AVAILABLE = False
    McpWorkbench = None
    StdioServerParams = None
    mcp_server_tools = None

class MCPServerConfig:
    """Konfiguration für einen einzelnen MCP Server"""

    def __init__(self, config: Dict[str, Any]):
        self.name = config.get("name", "unknown")
        self.active = config.get("active", False)
        self.server_type = config.get("type", "stdio")
        self.command = config.get("command", "")
        self.args = config.get("args", [])
        self.env_vars = config.get("env_vars", {})
        self.description = config.get("description", "")
        self.read_timeout = config.get("read_timeout_seconds", 120)
        self.cwd = config.get("cwd", None)

    def resolve_env_vars(self) -> Dict[str, str]:
        """Löst Umgebungsvariablen auf (env:VAR_NAME -> actual value)"""
        resolved = {}
        for key, value in self.env_vars.items():
            if isinstance(value, str) and value.startswith("env:"):
                env_var_name = value[4:]  # Remove "env:" prefix
                resolved[key] = os.environ.get(env_var_name, "")
            else:
                resolved[key] = str(value)
        return resolved

    def is_stdio(self) -> bool:
        """Prüft ob Server vom Typ stdio ist"""
        return self.server_type == "stdio"

    def is_custom(self) -> bool:
        """Prüft ob Server ein Custom Agent ist"""
        return self.server_type == "custom"


class MCPWorkbenchManager:
    """
    Manager für MCP Server Workbench

    Lädt Server-Konfigurationen aus servers.json und erstellt
    eine AutoGen-kompatible McpWorkbench.
    """

    def __init__(self, servers_json_path: Optional[str] = None):
        """
        Initialisiert den WorkbenchManager

        Args:
            servers_json_path: Pfad zur servers.json (optional, Default: ../servers.json)
        """
        if servers_json_path:
            self.servers_json_path = Path(servers_json_path)
        else:
            # Default: servers.json im parent directory
            self.servers_json_path = Path(__file__).parent.parent / "servers.json"

        self.servers: List[MCPServerConfig] = []
        self.workbench: Optional[McpWorkbench] = None
        self._tools_cache: List[Any] = []

        # Konfiguration laden
        self._load_config()

    def _load_config(self):
        """Lädt die Server-Konfiguration aus servers.json"""
        if not self.servers_json_path.exists():
            logger.error(f"servers.json nicht gefunden: {self.servers_json_path}")
            return

        try:
            with open(self.servers_json_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            servers_list = config.get("servers", [])

            for server_config in servers_list:
                server = MCPServerConfig(server_config)
                self.servers.append(server)

            active_count = sum(1 for s in self.servers if s.active)
            logger.info(f"Loaded {len(self.servers)} servers ({active_count} active)")

        except json.JSONDecodeError as e:
            logger.error(f"Fehler beim Parsen von servers.json: {e}")
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")

    def get_active_servers(self) -> List[MCPServerConfig]:
        """Gibt alle aktiven Server zurück"""
        return [s for s in self.servers if s.active]

    def get_stdio_servers(self) -> List[MCPServerConfig]:
        """Gibt alle aktiven stdio Server zurück, sortiert nach Priorität"""
        active_servers = [s for s in self.servers if s.active and s.is_stdio()]

        # Sort by priority - servers in PRIORITY_SERVERS list come first
        def get_priority(server):
            try:
                return PRIORITY_SERVERS.index(server.name)
            except ValueError:
                return len(PRIORITY_SERVERS) + 1  # Non-priority servers come last

        return sorted(active_servers, key=get_priority)

    def get_custom_servers(self) -> List[MCPServerConfig]:
        """Gibt alle aktiven custom Server zurück"""
        return [s for s in self.servers if s.active and s.is_custom()]

    def create_workbench(self) -> Optional[McpWorkbench]:
        """
        Erstellt eine AutoGen McpWorkbench mit allen aktiven stdio Servern

        Returns:
            McpWorkbench oder None wenn nicht verfügbar
        """
        if not AUTOGEN_MCP_AVAILABLE:
            logger.error("AutoGen MCP nicht verfügbar")
            return None

        if self.workbench is not None:
            return self.workbench

        try:
            # Erst alle Server-Params sammeln
            server_params = {}

            for server in self.get_stdio_servers():
                try:
                    # Umgebungsvariablen auflösen
                    env = server.resolve_env_vars()

                    # StdioServerParams erstellen
                    params = StdioServerParams(
                        command=server.command,
                        args=server.args,
                        env=env if env else None
                    )

                    server_params[server.name] = params
                    logger.info(f"Server '{server.name}' konfiguriert")

                except Exception as e:
                    logger.warning(f"Konnte Server '{server.name}' nicht konfigurieren: {e}")

            if not server_params:
                logger.warning("Keine stdio Server konfiguriert")
                return None

            # Workbench mit allen Params auf einmal erstellen
            self.workbench = McpWorkbench(server_params=server_params)
            logger.info(f"McpWorkbench erstellt mit {len(server_params)} Servern")

            return self.workbench

        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Workbench: {e}")
            return None

    async def get_all_tools(self, max_tools: int = MAX_TOOLS) -> List[Any]:
        """
        Holt alle verfügbaren Tools von allen aktiven MCP Servern

        Args:
            max_tools: Maximum number of tools to load (OpenAI limit is 128)

        Returns:
            Liste aller Tools (original tools, duplicates skipped, limited to max_tools)
        """
        if self._tools_cache:
            return self._tools_cache[:max_tools]

        if not AUTOGEN_MCP_AVAILABLE:
            logger.error("AutoGen MCP nicht verfügbar")
            return []

        all_tools = []
        seen_names = set()
        skipped_tools = []
        skipped_servers = []
        failed_servers = []

        # Retry configuration
        MAX_RETRIES = 3
        TIMEOUT_SECONDS = 90.0  # Longer timeout for npx first-time downloads
        RETRY_DELAY = 2.0

        for server in self.get_stdio_servers():
            # Check if we've hit the limit
            if len(all_tools) >= max_tools:
                skipped_servers.append(server.name)
                continue

            # Umgebungsvariablen auflösen
            env = server.resolve_env_vars()

            # StdioServerParams erstellen
            params = StdioServerParams(
                command=server.command,
                args=server.args,
                env=env if env else None
            )

            # Retry loop for transient failures
            tools = None
            last_error = None
            for attempt in range(MAX_RETRIES):
                try:
                    # Tools für diesen Server laden mit Timeout
                    logger.info(f"Lade Tools von Server '{server.name}' (Versuch {attempt + 1}/{MAX_RETRIES})...")
                    tools = await asyncio.wait_for(
                        mcp_server_tools(params),
                        timeout=TIMEOUT_SECONDS
                    )
                    # Success - break retry loop
                    break
                except asyncio.TimeoutError:
                    last_error = f"Timeout nach {TIMEOUT_SECONDS}s"
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(f"Server '{server.name}' timeout, retry in {RETRY_DELAY}s...")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.error(f"Server '{server.name}' failed after {MAX_RETRIES} attempts: {last_error}")
                        failed_servers.append(f"{server.name} ({last_error})")
                except Exception as e:
                    last_error = str(e)
                    # For non-timeout errors, check if retryable
                    error_str = str(e).lower()
                    is_retryable = any(x in error_str for x in ['taskgroup', 'connection', 'timeout', 'network'])

                    if is_retryable and attempt < MAX_RETRIES - 1:
                        logger.warning(f"Server '{server.name}' error (retryable), retry in {RETRY_DELAY}s: {e}")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        logger.warning(f"Server '{server.name}' failed: {e}")
                        failed_servers.append(f"{server.name} ({last_error[:50]})")
                        break

            if tools is None:
                continue

            # Filter duplicate tool names - keep first occurrence
            unique_tools = []
            for tool in tools:
                # Check if we've hit the limit
                if len(all_tools) + len(unique_tools) >= max_tools:
                    break

                if hasattr(tool, 'name'):
                    tool_name = tool.name

                    # Check for duplicates
                    if tool_name in seen_names:
                        skipped_tools.append(f"{server.name}:{tool_name}")
                        continue

                    seen_names.add(tool_name)
                    unique_tools.append(tool)
                else:
                    # Tool without name - add as-is
                    unique_tools.append(tool)

            logger.info(f"  -> {len(unique_tools)} Tools von '{server.name}'")
            all_tools.extend(unique_tools)

        if skipped_tools:
            logger.info(f"Skipped {len(skipped_tools)} duplicate tools: {skipped_tools[:5]}{'...' if len(skipped_tools) > 5 else ''}")

        if skipped_servers:
            logger.info(f"Skipped {len(skipped_servers)} servers due to tool limit ({max_tools}): {skipped_servers}")

        if failed_servers:
            logger.warning(f"Failed to load {len(failed_servers)} servers: {failed_servers}")

        self._tools_cache = all_tools
        logger.info(f"Loaded {len(self._tools_cache)} unique tools from MCP servers (limit: {max_tools})")
        return self._tools_cache

    def get_server_info(self) -> Dict[str, Any]:
        """Gibt Informationen über alle Server zurück"""
        return {
            "total_servers": len(self.servers),
            "active_servers": len(self.get_active_servers()),
            "stdio_servers": len(self.get_stdio_servers()),
            "custom_servers": len(self.get_custom_servers()),
            "servers": [
                {
                    "name": s.name,
                    "active": s.active,
                    "type": s.server_type,
                    "description": s.description
                }
                for s in self.servers
            ]
        }

    async def shutdown(self):
        """Fährt die Workbench herunter und gibt Ressourcen frei"""
        logger.info("Shutting down MCP Workbench...")

        if self.workbench is not None:
            try:
                # Stop all MCP servers
                if hasattr(self.workbench, 'stop'):
                    await self.workbench.stop()
                elif hasattr(self.workbench, 'close'):
                    await self.workbench.close()
                elif hasattr(self.workbench, 'shutdown'):
                    await self.workbench.shutdown()
            except Exception as e:
                logger.warning(f"Error during workbench cleanup: {e}")
            finally:
                self.workbench = None

        # Cache leeren
        self._tools_cache = []
        logger.info("MCP Workbench shutdown complete")


# Singleton Instance
_workbench_manager: Optional[MCPWorkbenchManager] = None


def get_workbench_manager() -> MCPWorkbenchManager:
    """
    Gibt die globale WorkbenchManager Instanz zurück (Singleton)

    Returns:
        MCPWorkbenchManager Instanz
    """
    global _workbench_manager
    if _workbench_manager is None:
        _workbench_manager = MCPWorkbenchManager()
    return _workbench_manager


def get_workbench() -> Optional[McpWorkbench]:
    """
    Gibt die globale McpWorkbench Instanz zurück

    Returns:
        McpWorkbench oder None
    """
    manager = get_workbench_manager()
    return manager.create_workbench()


async def get_all_mcp_tools() -> List[Any]:
    """
    Holt alle MCP Tools (async)

    Returns:
        Liste aller verfügbaren Tools
    """
    manager = get_workbench_manager()
    return await manager.get_all_tools()


# Für Kompatibilität mit dem Plan - DEPRECATED
# Verwende stattdessen get_all_mcp_tools() direkt
async def get_tools_from_workbench(workbench: McpWorkbench) -> List[Any]:
    """
    DEPRECATED: Factory function für AutoGen - holt alle Tools von einer Workbench

    Verwende stattdessen get_all_mcp_tools() oder mcp_server_tools() direkt.

    Args:
        workbench: McpWorkbench Instanz

    Returns:
        Liste aller Tools
    """
    try:
        await workbench.start()
        return await workbench.list_tools()
    except Exception as e:
        logger.error(f"Fehler beim Laden der Tools: {e}")
        return []


# Test-Funktion
async def test_workbench():
    """Test-Funktion für die Workbench"""
    print("=== MCP Workbench Test ===\n")

    manager = get_workbench_manager()
    info = manager.get_server_info()

    print(f"Total Servers: {info['total_servers']}")
    print(f"Active Servers: {info['active_servers']}")
    print(f"Stdio Servers: {info['stdio_servers']}")
    print(f"Custom Servers: {info['custom_servers']}")

    print("\n=== Active Servers ===")
    for server in info['servers']:
        if server['active']:
            print(f"  - {server['name']} ({server['type']}): {server['description'][:50]}...")

    if AUTOGEN_MCP_AVAILABLE:
        print("\n=== Creating Workbench ===")
        workbench = get_workbench()
        if workbench:
            print("Workbench created successfully!")

            print("\n=== Loading Tools ===")
            tools = await get_all_mcp_tools()
            print(f"Loaded {len(tools)} tools")

            if tools:
                print("\nFirst 5 tools:")
                for tool in tools[:5]:
                    print(f"  - {getattr(tool, 'name', str(tool))}")
    else:
        print("\n[!] AutoGen MCP not available - install with: pip install autogen-ext[mcp]")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(test_workbench())
