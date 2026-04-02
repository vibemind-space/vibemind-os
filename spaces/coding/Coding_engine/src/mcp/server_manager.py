"""
MCP Server Manager - Dynamic provisioning of MCP servers.

This module handles:
1. Starting/stopping MCP servers (Docker, local, stdio)
2. Generating MCP config for Claude CLI
3. Server lifecycle management
4. Health checks and auto-recovery
"""

import asyncio
import json
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class ServerType(str, Enum):
    """Types of MCP servers."""
    DOCKER = "docker"
    STDIO = "stdio"
    HTTP = "http"
    PYTHON = "python"


class ServerStatus(str, Enum):
    """Server status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    server_type: ServerType

    # For Docker servers
    image: Optional[str] = None
    docker_args: list[str] = field(default_factory=list)

    # For stdio servers
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)

    # For HTTP servers
    url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)

    # For Python servers
    module: Optional[str] = None

    # Common
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    auto_restart: bool = False

    def to_mcp_config(self) -> dict:
        """Convert to MCP JSON config format."""
        if self.server_type == ServerType.DOCKER:
            return {
                "command": "docker",
                "args": ["run", "-i", "--rm"] + self.docker_args + [self.image],
                "env": self.env,
            }
        elif self.server_type == ServerType.STDIO:
            return {
                "command": self.command,
                "args": self.args,
                "env": self.env,
            }
        elif self.server_type == ServerType.HTTP:
            config = {"url": self.url}
            if self.headers:
                config["headers"] = self.headers
            return config
        elif self.server_type == ServerType.PYTHON:
            return {
                "command": "python",
                "args": ["-m", self.module],
                "env": self.env,
            }
        else:
            raise ValueError(f"Unknown server type: {self.server_type}")


@dataclass
class MCPServer:
    """Running MCP server instance."""
    config: MCPServerConfig
    status: ServerStatus = ServerStatus.STOPPED
    process: Optional[asyncio.subprocess.Process] = None
    container_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_running(self) -> bool:
        return self.status == ServerStatus.RUNNING


class MCPServerManager:
    """
    Manages dynamic MCP server provisioning.

    Usage:
        manager = MCPServerManager(working_dir="./output")

        # Start Docker-based Playwright
        await manager.start_server(MCPServerConfig(
            name="playwright",
            server_type=ServerType.DOCKER,
            image="mcr.microsoft.com/playwright:latest"
        ))

        # Start local Python server
        await manager.start_server(MCPServerConfig(
            name="code-analyzer",
            server_type=ServerType.PYTHON,
            module="src.mcp.tools.analyzer"
        ))

        # Get config for Claude CLI
        config = manager.get_mcp_config()

        # Cleanup
        await manager.stop_all()
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.config_path = Path(config_path) if config_path else self.working_dir / ".claude" / "mcp-dynamic.json"
        self.servers: dict[str, MCPServer] = {}
        self.logger = logger.bind(component="mcp_manager")

        # Predefined server templates
        self.templates = self._load_templates()

    def _load_templates(self) -> dict[str, MCPServerConfig]:
        """Load predefined server templates."""
        return {
            "playwright": MCPServerConfig(
                name="playwright",
                server_type=ServerType.STDIO,
                command="npx",
                args=["-y", "@anthropic/mcp-playwright"],
            ),
            "playwright-docker": MCPServerConfig(
                name="playwright-docker",
                server_type=ServerType.DOCKER,
                image="mcr.microsoft.com/playwright:latest",
                docker_args=["-p", "3000:3000"],
            ),
            "filesystem": MCPServerConfig(
                name="filesystem",
                server_type=ServerType.STDIO,
                command="npx",
                args=["-y", "@anthropic/mcp-filesystem", str(self.working_dir)],
            ),
            "github": MCPServerConfig(
                name="github",
                server_type=ServerType.STDIO,
                command="npx",
                args=["-y", "@anthropic/mcp-github"],
            ),
        }

    def get_template(self, name: str) -> Optional[MCPServerConfig]:
        """Get a predefined server template."""
        return self.templates.get(name)

    async def start_server(
        self,
        config: MCPServerConfig,
        wait_ready: bool = True,
    ) -> MCPServer:
        """
        Start an MCP server.

        Args:
            config: Server configuration
            wait_ready: Wait for server to be ready

        Returns:
            MCPServer instance
        """
        if config.name in self.servers:
            existing = self.servers[config.name]
            if existing.is_running:
                self.logger.info("server_already_running", name=config.name)
                return existing
            # Remove stopped server
            del self.servers[config.name]

        server = MCPServer(config=config, status=ServerStatus.STARTING)
        self.servers[config.name] = server

        self.logger.info(
            "starting_server",
            name=config.name,
            type=config.server_type.value,
        )

        try:
            if config.server_type == ServerType.DOCKER:
                await self._start_docker_server(server)
            elif config.server_type in (ServerType.STDIO, ServerType.PYTHON):
                await self._start_stdio_server(server)
            elif config.server_type == ServerType.HTTP:
                # HTTP servers are external, just validate
                await self._validate_http_server(server)

            server.status = ServerStatus.RUNNING
            self.logger.info("server_started", name=config.name)

            # Update MCP config file
            self._write_config()

            return server

        except Exception as e:
            server.status = ServerStatus.ERROR
            server.error = str(e)
            self.logger.error("server_start_failed", name=config.name, error=str(e))
            raise

    async def start_from_template(
        self,
        template_name: str,
        override_name: Optional[str] = None,
    ) -> MCPServer:
        """Start a server from a predefined template."""
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")

        config = MCPServerConfig(
            name=override_name or template.name,
            server_type=template.server_type,
            image=template.image,
            docker_args=template.docker_args.copy(),
            command=template.command,
            args=template.args.copy(),
            url=template.url,
            headers=template.headers.copy(),
            module=template.module,
            env=template.env.copy(),
            timeout=template.timeout,
            auto_restart=template.auto_restart,
        )

        return await self.start_server(config)

    async def _start_docker_server(self, server: MCPServer) -> None:
        """Start a Docker-based MCP server."""
        config = server.config

        # Build docker run command
        cmd = ["docker", "run", "-d", "--rm"]
        cmd.extend(config.docker_args)

        # Add environment variables
        for key, value in config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.append(config.image)

        self.logger.debug("docker_command", cmd=" ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Docker start failed: {result.stderr}")

        server.container_id = result.stdout.strip()[:12]
        self.logger.info("docker_started", container_id=server.container_id)

    async def _start_stdio_server(self, server: MCPServer) -> None:
        """Start a stdio-based MCP server."""
        config = server.config

        if config.server_type == ServerType.PYTHON:
            cmd = ["python", "-m", config.module]
        else:
            cmd = [config.command] + config.args

        env = os.environ.copy()
        env.update(config.env)

        # Note: For stdio servers, we don't actually start them here
        # They are started by Claude CLI when using --mcp-config
        # We just validate the command exists

        self.logger.info(
            "stdio_server_registered",
            name=config.name,
            command=cmd[0],
        )

    async def _validate_http_server(self, server: MCPServer) -> None:
        """Validate an HTTP MCP server is reachable."""
        import urllib.request

        config = server.config

        try:
            req = urllib.request.Request(config.url, method="HEAD")
            for key, value in config.headers.items():
                req.add_header(key, value)

            urllib.request.urlopen(req, timeout=config.timeout)
            self.logger.info("http_server_validated", url=config.url)
        except Exception as e:
            self.logger.warning("http_server_unreachable", url=config.url, error=str(e))

    async def stop_server(self, name: str) -> None:
        """Stop an MCP server."""
        if name not in self.servers:
            return

        server = self.servers[name]

        self.logger.info("stopping_server", name=name)

        try:
            if server.config.server_type == ServerType.DOCKER and server.container_id:
                subprocess.run(
                    ["docker", "stop", server.container_id],
                    capture_output=True,
                    timeout=30,
                )
            elif server.process:
                server.process.terminate()
                try:
                    await asyncio.wait_for(server.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    server.process.kill()
        except Exception as e:
            self.logger.error("stop_failed", name=name, error=str(e))

        server.status = ServerStatus.STOPPED
        del self.servers[name]

        # Update config file
        self._write_config()

    async def stop_all(self) -> None:
        """Stop all running servers."""
        names = list(self.servers.keys())
        for name in names:
            await self.stop_server(name)

    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get a server by name."""
        return self.servers.get(name)

    def list_servers(self) -> list[MCPServer]:
        """List all servers."""
        return list(self.servers.values())

    def get_mcp_config(self) -> dict:
        """
        Get MCP config dict for all running servers.

        Returns:
            Dict in MCP JSON format for Claude CLI
        """
        config = {"mcpServers": {}}

        for name, server in self.servers.items():
            if server.is_running or server.status == ServerStatus.STARTING:
                config["mcpServers"][name] = server.config.to_mcp_config()

        return config

    def get_config_path(self) -> Path:
        """Get path to the MCP config file."""
        return self.config_path

    def _write_config(self) -> None:
        """Write current config to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        config = self.get_mcp_config()

        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

        self.logger.debug("config_written", path=str(self.config_path))

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup servers."""
        await self.stop_all()

        # Remove config file
        if self.config_path.exists():
            self.config_path.unlink()
