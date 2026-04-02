"""
Docker MCP Server - Manages Docker-based MCP servers.

Provides utilities for:
1. Building custom MCP server images
2. Running MCP servers in containers
3. Container lifecycle management
4. Volume mounting for workspace access
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class DockerMCPConfig:
    """Configuration for a Docker MCP server."""
    name: str
    image: str

    # Container settings
    ports: dict[int, int] = field(default_factory=dict)  # host:container
    volumes: dict[str, str] = field(default_factory=dict)  # host:container
    env: dict[str, str] = field(default_factory=dict)
    network: Optional[str] = None

    # MCP settings
    interactive: bool = True  # -i flag for stdio transport
    remove_on_exit: bool = True  # --rm flag

    # Resource limits
    memory: Optional[str] = None  # e.g. "512m"
    cpus: Optional[float] = None  # e.g. 1.0


class DockerMCPServer:
    """
    Docker-based MCP server manager.

    Provides higher-level Docker operations for MCP servers:
    - Building images from Dockerfile
    - Running containers with proper MCP configuration
    - Health checks and logs
    - Cleanup and resource management

    Usage:
        server = DockerMCPServer(
            config=DockerMCPConfig(
                name="my-mcp",
                image="my-mcp-image:latest",
                ports={3000: 3000},
                volumes={"/workspace": "/app/workspace"}
            )
        )

        container_id = await server.start()
        logs = await server.logs()
        await server.stop()
    """

    def __init__(self, config: DockerMCPConfig):
        self.config = config
        self.container_id: Optional[str] = None
        self.logger = logger.bind(
            component="docker_mcp",
            server=config.name,
        )

    @staticmethod
    async def build_image(
        dockerfile_path: str,
        image_name: str,
        context_path: Optional[str] = None,
        build_args: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Build a Docker image for an MCP server.

        Args:
            dockerfile_path: Path to Dockerfile
            image_name: Name:tag for the image
            context_path: Build context directory
            build_args: Build arguments

        Returns:
            True if build succeeded
        """
        dockerfile = Path(dockerfile_path)
        context = Path(context_path) if context_path else dockerfile.parent

        cmd = ["docker", "build", "-t", image_name, "-f", str(dockerfile)]

        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

        cmd.append(str(context))

        logger.info("building_image", image=image_name, dockerfile=str(dockerfile))

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error("build_failed", stderr=result.stderr)
            return False

        logger.info("image_built", image=image_name)
        return True

    def _build_run_command(self) -> list[str]:
        """Build the docker run command."""
        cmd = ["docker", "run"]

        # Interactive mode for stdio transport
        if self.config.interactive:
            cmd.append("-i")

        # Remove container on exit
        if self.config.remove_on_exit:
            cmd.append("--rm")

        # Detach mode for background operation
        cmd.append("-d")

        # Container name
        cmd.extend(["--name", self.config.name])

        # Port mappings
        for host_port, container_port in self.config.ports.items():
            cmd.extend(["-p", f"{host_port}:{container_port}"])

        # Volume mounts
        for host_path, container_path in self.config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])

        # Environment variables
        for key, value in self.config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Network
        if self.config.network:
            cmd.extend(["--network", self.config.network])

        # Resource limits
        if self.config.memory:
            cmd.extend(["--memory", self.config.memory])
        if self.config.cpus:
            cmd.extend(["--cpus", str(self.config.cpus)])

        # Image
        cmd.append(self.config.image)

        return cmd

    async def start(self) -> str:
        """
        Start the Docker container.

        Returns:
            Container ID
        """
        # Check if already running
        if self.container_id:
            if await self.is_running():
                return self.container_id

        # Remove any existing container with same name
        await self._remove_existing()

        cmd = self._build_run_command()
        self.logger.debug("docker_run", cmd=" ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr}")

        self.container_id = result.stdout.strip()[:12]
        self.logger.info("container_started", container_id=self.container_id)

        return self.container_id

    async def stop(self, timeout: int = 10) -> None:
        """Stop the container."""
        if not self.container_id:
            return

        self.logger.info("stopping_container", container_id=self.container_id)

        subprocess.run(
            ["docker", "stop", "-t", str(timeout), self.container_id],
            capture_output=True,
            timeout=timeout + 5,
        )

        self.container_id = None

    async def _remove_existing(self) -> None:
        """Remove existing container with same name."""
        subprocess.run(
            ["docker", "rm", "-f", self.config.name],
            capture_output=True,
            stderr=subprocess.DEVNULL,
        )

    async def is_running(self) -> bool:
        """Check if container is running."""
        if not self.container_id:
            return False

        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", self.container_id],
            capture_output=True,
            text=True,
        )

        return result.stdout.strip() == "true"

    async def logs(self, tail: int = 100) -> str:
        """Get container logs."""
        if not self.container_id:
            return ""

        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), self.container_id],
            capture_output=True,
            text=True,
        )

        return result.stdout + result.stderr

    async def exec(self, command: list[str]) -> tuple[str, str]:
        """Execute command in container."""
        if not self.container_id:
            raise RuntimeError("Container not running")

        result = subprocess.run(
            ["docker", "exec", self.container_id] + command,
            capture_output=True,
            text=True,
        )

        return result.stdout, result.stderr

    async def health_check(self) -> bool:
        """Check container health."""
        if not await self.is_running():
            return False

        # Try to get health status if defined
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", self.container_id],
            capture_output=True,
            text=True,
        )

        status = result.stdout.strip()

        # If no healthcheck defined, just check if running
        if not status or status == "<no value>":
            return True

        return status == "healthy"

    def to_mcp_config(self) -> dict:
        """
        Convert to MCP JSON config format.

        For stdio transport, the container runs interactively.
        """
        return {
            "command": "docker",
            "args": self._build_run_command()[1:],  # Skip 'docker' prefix
        }

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()


# Predefined Docker MCP server configurations
DOCKER_MCP_TEMPLATES = {
    "playwright": DockerMCPConfig(
        name="mcp-playwright",
        image="mcr.microsoft.com/playwright:latest",
        ports={3000: 3000},
        memory="1g",
    ),
    "puppeteer": DockerMCPConfig(
        name="mcp-puppeteer",
        image="ghcr.io/anthropics/mcp-puppeteer:latest",
        ports={3000: 3000},
    ),
    "postgres": DockerMCPConfig(
        name="mcp-postgres",
        image="ghcr.io/anthropics/mcp-postgres:latest",
        env={"DATABASE_URL": "postgresql://localhost:5432/db"},
    ),
}


def get_docker_template(name: str) -> Optional[DockerMCPConfig]:
    """Get a predefined Docker MCP configuration."""
    return DOCKER_MCP_TEMPLATES.get(name)
