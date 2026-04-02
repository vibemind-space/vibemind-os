"""
Project MCP Config - Per-project dynamic configuration for MCP servers.

Each project gets a `.mcp-config.json` that overrides global servers.json
with project-specific paths, database URLs, container names, etc.

The config is generated when a generation starts and can be updated
at runtime (e.g., when a database container spins up).

File location: {project_path}/.mcp-config.json
"""
import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any
import structlog

logger = structlog.get_logger()


@dataclass
class MCPServerOverride:
    """Override config for a single MCP server."""
    enabled: bool = True
    env_vars: Dict[str, str] = field(default_factory=dict)
    args_override: list = field(default_factory=list)
    notes: str = ""


@dataclass
class ProjectMCPConfig:
    """
    Per-project MCP configuration.

    Generated at generation start, persisted as .mcp-config.json.
    MCPAgentPool merges this with global servers.json at spawn time.
    """
    project_id: str
    project_path: str
    output_dir: str
    sandbox_container: str = ""
    vnc_port: int = 6090
    app_port: int = 3100

    # Per-server overrides
    servers: Dict[str, MCPServerOverride] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        result = {
            "project_id": self.project_id,
            "project_path": self.project_path,
            "output_dir": self.output_dir,
            "sandbox_container": self.sandbox_container,
            "vnc_port": self.vnc_port,
            "app_port": self.app_port,
            "servers": {},
        }
        for name, override in self.servers.items():
            result["servers"][name] = asdict(override)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectMCPConfig":
        """Deserialize from dict."""
        servers = {}
        for name, srv_data in data.get("servers", {}).items():
            servers[name] = MCPServerOverride(**srv_data)
        return cls(
            project_id=data.get("project_id", ""),
            project_path=data.get("project_path", ""),
            output_dir=data.get("output_dir", ""),
            sandbox_container=data.get("sandbox_container", ""),
            vnc_port=data.get("vnc_port", 6090),
            app_port=data.get("app_port", 3100),
            servers=servers,
        )


def generate_project_mcp_config(
    project_id: str,
    project_path: str,
    output_dir: str,
    sandbox_container: str = "",
    vnc_port: int = 6090,
    app_port: int = 3100,
) -> ProjectMCPConfig:
    """
    Generate a project-specific MCP config by scanning the project.

    Detects which services the project uses (DB, Redis, etc.)
    and configures MCP servers accordingly.

    Args:
        project_id: Unique project identifier
        project_path: Root path of the project data (requirements, docs)
        output_dir: Where generated code goes
        sandbox_container: Docker sandbox container name
        vnc_port: VNC port for the sandbox
        app_port: App preview port

    Returns:
        ProjectMCPConfig ready to persist
    """
    config = ProjectMCPConfig(
        project_id=project_id,
        project_path=project_path,
        output_dir=output_dir,
        sandbox_container=sandbox_container or f"sandbox-{project_id}",
        vnc_port=vnc_port,
        app_port=app_port,
    )

    output = Path(output_dir)

    # --- Filesystem: scope to project output dir ---
    config.servers["filesystem"] = MCPServerOverride(
        enabled=True,
        args_override=[output_dir],
        env_vars={},
        notes=f"Scoped to project output: {output_dir}",
    )

    # --- Docker: target sandbox container ---
    config.servers["docker"] = MCPServerOverride(
        enabled=True,
        env_vars={
            "SANDBOX_CONTAINER": config.sandbox_container,
            "VNC_PORT": str(vnc_port),
            "APP_PORT": str(app_port),
        },
        notes=f"Sandbox: {config.sandbox_container}",
    )

    # --- Detect Prisma (look for schema.prisma in output or data) ---
    prisma_paths = list(output.rglob("schema.prisma")) if output.exists() else []
    data_prisma = list(Path(project_path).rglob("schema.prisma")) if Path(project_path).exists() else []
    if prisma_paths or data_prisma:
        schema_path = str(prisma_paths[0] if prisma_paths else data_prisma[0])
        config.servers["prisma"] = MCPServerOverride(
            enabled=True,
            env_vars={"PRISMA_SCHEMA_PATH": schema_path},
            notes=f"Schema: {schema_path}",
        )

    # --- Detect Database URL from .env files ---
    db_url = _find_env_var(output, "DATABASE_URL") or _find_env_var(Path(project_path), "DATABASE_URL")
    if db_url:
        config.servers["postgres"] = MCPServerOverride(
            enabled=True,
            env_vars={"DATABASE_URL": db_url},
            notes="From project .env",
        )

    # --- Detect Redis from .env or docker-compose ---
    redis_url = _find_env_var(output, "REDIS_URL") or _find_env_var(Path(project_path), "REDIS_URL")
    if redis_url:
        config.servers["redis"] = MCPServerOverride(
            enabled=True,
            env_vars={"REDIS_URL": redis_url},
            notes="From project .env",
        )
    elif _has_docker_service(output, "redis") or _has_docker_service(Path(project_path), "redis"):
        # Redis in docker-compose but no explicit URL — construct from container
        config.servers["redis"] = MCPServerOverride(
            enabled=True,
            env_vars={"REDIS_URL": f"redis://{config.sandbox_container}-redis:6379"},
            notes="Auto-detected from docker-compose",
        )

    # --- Git: scope to output dir ---
    if (output / ".git").exists():
        config.servers["git"] = MCPServerOverride(
            enabled=True,
            args_override=[str(output)],
            notes=f"Git repo: {output}",
        )

    # --- Playwright: target sandbox app ---
    config.servers["playwright"] = MCPServerOverride(
        enabled=True,
        env_vars={
            "PLAYWRIGHT_BASE_URL": f"http://localhost:{app_port}",
        },
        notes=f"App at port {app_port}",
    )

    # --- NPM: scope to output dir ---
    if (output / "package.json").exists() or True:  # Always enable for generated projects
        config.servers["npm"] = MCPServerOverride(
            enabled=True,
            env_vars={"NPM_PROJECT_DIR": str(output)},
            notes=f"Project: {output}",
        )

    logger.info(
        "project_mcp_config_generated",
        project_id=project_id,
        servers_configured=list(config.servers.keys()),
        output_dir=output_dir,
    )

    return config


def save_project_mcp_config(config: ProjectMCPConfig) -> Path:
    """
    Save config to {project_path}/.mcp-config.json.

    Returns:
        Path to the saved config file
    """
    config_path = Path(config.project_path) / ".mcp-config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info("project_mcp_config_saved", path=str(config_path))
    return config_path


def load_project_mcp_config(project_path: str) -> Optional[ProjectMCPConfig]:
    """
    Load config from {project_path}/.mcp-config.json.

    Returns:
        ProjectMCPConfig or None if not found
    """
    config_path = Path(project_path) / ".mcp-config.json"
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = ProjectMCPConfig.from_dict(data)
        logger.info("project_mcp_config_loaded", path=str(config_path))
        return config
    except Exception as e:
        logger.warning("project_mcp_config_load_failed", path=str(config_path), error=str(e))
        return None


def update_project_mcp_config(
    project_path: str,
    updates: Dict[str, Any],
) -> Optional[ProjectMCPConfig]:
    """
    Partial update of an existing config.

    Args:
        project_path: Project root path
        updates: Dict with fields to update. Supports nested:
            {"servers": {"postgres": {"env_vars": {"DATABASE_URL": "..."}}}}

    Returns:
        Updated config or None if no config exists
    """
    config = load_project_mcp_config(project_path)
    if not config:
        return None

    # Apply top-level updates
    for key in ("project_id", "output_dir", "sandbox_container", "vnc_port", "app_port"):
        if key in updates:
            setattr(config, key, updates[key])

    # Apply server overrides
    if "servers" in updates:
        for server_name, srv_updates in updates["servers"].items():
            if server_name not in config.servers:
                config.servers[server_name] = MCPServerOverride()
            srv = config.servers[server_name]
            if "enabled" in srv_updates:
                srv.enabled = srv_updates["enabled"]
            if "env_vars" in srv_updates:
                srv.env_vars.update(srv_updates["env_vars"])
            if "args_override" in srv_updates:
                srv.args_override = srv_updates["args_override"]
            if "notes" in srv_updates:
                srv.notes = srv_updates["notes"]

    save_project_mcp_config(config)
    return config


# ─── Helpers ──────────────────────────────────────────────────────────


def _find_env_var(search_dir: Path, var_name: str) -> Optional[str]:
    """Search for an env var in .env files within a directory."""
    if not search_dir.exists():
        return None

    for env_file in [".env", ".env.local", ".env.development"]:
        env_path = search_dir / env_file
        if env_path.exists():
            try:
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{var_name}="):
                            value = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if value:
                                return value
            except Exception:
                pass
    return None


def _has_docker_service(search_dir: Path, service_name: str) -> bool:
    """Check if a docker-compose file references a service."""
    if not search_dir.exists():
        return False

    for compose_file in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]:
        compose_path = search_dir / compose_file
        if compose_path.exists():
            try:
                content = compose_path.read_text()
                # Simple check: service name appears in services section
                if f"{service_name}:" in content:
                    return True
            except Exception:
                pass
    return False


# ─── CLI MCP Config Generator ──────────────────────────────────────


def generate_cli_mcp_config(
    working_dir: str,
    output_path: Optional[str] = None,
) -> Path:
    """
    Generate a Claude-CLI-compatible MCP config from servers.json.

    Reads all active stdio servers from servers.json and writes a
    .claude/mcp.json file that Claude CLI understands.

    Format: {"mcpServers": {"name": {"command": "...", "args": [...], "env": {...}}}}

    Args:
        working_dir: Directory where .claude/mcp.json will be written
        output_path: Override output path (default: {working_dir}/.claude/mcp.json)

    Returns:
        Path to the generated config file
    """
    servers_json_path = Path(__file__).parent.parent.parent / "mcp_plugins" / "servers" / "servers.json"
    if not servers_json_path.exists():
        # Try Docker path
        servers_json_path = Path("/app/mcp_plugins/servers/servers.json")

    mcp_servers: Dict[str, dict] = {}

    if servers_json_path.exists():
        try:
            with open(servers_json_path, "r") as f:
                data = json.load(f)

            for server in data.get("servers", []):
                if not server.get("active", False):
                    continue

                name = server["name"]
                server_type = server.get("type", "stdio")

                # Only stdio servers can be passed to Claude CLI
                if server_type != "stdio":
                    continue

                entry: dict = {
                    "command": server.get("command", "npx"),
                    "args": server.get("args", []),
                }

                # Resolve env vars (replace "env:VAR" with actual values)
                env_vars = server.get("env_vars", {})
                if env_vars:
                    resolved_env: Dict[str, str] = {}
                    for key, val in env_vars.items():
                        if isinstance(val, str) and val.startswith("env:"):
                            resolved = os.environ.get(val[4:], "")
                            if resolved:
                                resolved_env[key] = resolved
                        elif isinstance(val, str):
                            resolved_env[key] = val
                    if resolved_env:
                        entry["env"] = resolved_env

                mcp_servers[name] = entry
        except Exception as e:
            logger.warning("cli_mcp_config_parse_failed", error=str(e))

    config = {"mcpServers": mcp_servers}

    # Write config
    if output_path:
        config_path = Path(output_path)
    else:
        config_path = Path(working_dir) / ".claude" / "mcp.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    logger.info(
        "cli_mcp_config_generated",
        path=str(config_path),
        servers=list(mcp_servers.keys()),
        count=len(mcp_servers),
    )
    return config_path
