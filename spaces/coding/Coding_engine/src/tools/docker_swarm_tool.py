"""
Docker Swarm Tool - Secure Docker Swarm Operations.

Security-first approach:
- Secrets passed via stdin (NEVER as CLI args)
- No secrets logged
- subprocess with capture_output=True
"""

import asyncio
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class SwarmStatus(str, Enum):
    """Docker Swarm status states."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class SwarmResult:
    """Result of a Docker Swarm operation."""
    success: bool
    message: str
    data: Optional[dict] = field(default_factory=dict)


class DockerSwarmTool:
    """
    Secure Docker Swarm operations tool.

    SECURITY PATTERNS:
    - Secrets are ALWAYS passed via stdin (never as CLI arguments)
    - Secret values are NEVER logged
    - Memory is cleared immediately after use
    """

    def __init__(self):
        self.logger = logger.bind(component="DockerSwarmTool")

    async def check_swarm_status(self) -> SwarmStatus:
        """Check if Docker Swarm is initialized."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
                capture_output=True,
                text=True,
            )
            state = result.stdout.strip()
            if state == "active":
                return SwarmStatus.ACTIVE
            return SwarmStatus.INACTIVE
        except Exception as e:
            self.logger.error("swarm_status_check_failed", error=str(e))
            return SwarmStatus.ERROR

    async def init_swarm(self, advertise_addr: Optional[str] = None) -> SwarmResult:
        """
        Initialize Docker Swarm.

        Args:
            advertise_addr: Optional address to advertise to other nodes

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "swarm", "init"]
        if advertise_addr:
            cmd.extend(["--advertise-addr", advertise_addr])

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("swarm_initialized")
                return SwarmResult(success=True, message="Swarm initialized")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def leave_swarm(self, force: bool = False) -> SwarmResult:
        """
        Leave Docker Swarm.

        Args:
            force: Force leave even if this is the last manager

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "swarm", "leave"]
        if force:
            cmd.append("--force")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("swarm_left")
                return SwarmResult(success=True, message="Left swarm")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def create_secret_secure(self, name: str, value: str) -> SwarmResult:
        """
        Create Docker secret securely via stdin.

        SECURITY: value is passed via stdin, NOT as CLI arg!
        This prevents the secret from appearing in:
        - Process listings (ps aux)
        - Shell history
        - Logs

        Args:
            name: Secret name
            value: Secret value (will be cleared from memory after use)

        Returns:
            SwarmResult with success status and secret_id
        """
        try:
            # Use Popen to pass value via stdin
            process = await asyncio.to_thread(
                subprocess.Popen,
                ["docker", "secret", "create", name, "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(input=value.encode())

            # Clear value from memory immediately
            # Note: Python string interning may keep copies, but this is best effort
            value = None  # noqa: F841

            if process.returncode == 0:
                secret_id = stdout.decode().strip()
                self.logger.info("secret_created", name=name)  # NEVER log value!
                return SwarmResult(
                    success=True,
                    message=f"Secret '{name}' created",
                    data={"secret_id": secret_id}
                )
            return SwarmResult(success=False, message=stderr.decode())
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_secrets(self) -> list[str]:
        """
        List all Docker secrets (names only).

        Returns:
            List of secret names
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "secret", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                names = result.stdout.strip()
                return names.split("\n") if names else []
            return []
        except Exception:
            return []

    async def secret_exists(self, name: str) -> bool:
        """
        Check if a secret exists.

        Args:
            name: Secret name to check

        Returns:
            True if secret exists
        """
        secrets = await self.list_secrets()
        return name in secrets

    async def inspect_secret(self, name: str) -> Optional[dict]:
        """
        Inspect a secret (metadata only, not the value).

        Args:
            name: Secret name

        Returns:
            Secret metadata or None if not found
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "secret", "inspect", name, "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return None
        except Exception:
            return None

    async def remove_secret(self, name: str) -> SwarmResult:
        """
        Remove a Docker secret.

        Args:
            name: Secret name to remove

        Returns:
            SwarmResult with success status
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "secret", "rm", name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.logger.info("secret_removed", name=name)
                return SwarmResult(success=True, message=f"Secret '{name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def create_service_with_secrets(
        self,
        name: str,
        image: str,
        secrets: list[str],
        replicas: int = 1,
        ports: Optional[dict[int, int]] = None,
        env: Optional[dict[str, str]] = None,
        networks: Optional[list[str]] = None,
        mounts: Optional[list[str]] = None,
        constraints: Optional[list[str]] = None,
        labels: Optional[dict[str, str]] = None,
    ) -> SwarmResult:
        """
        Create Docker service with secrets attached.

        Secrets are mounted at /run/secrets/<secret_name> in the container.

        Args:
            name: Service name
            image: Docker image
            secrets: List of secret names to attach
            replicas: Number of replicas (default 1)
            ports: Port mappings {host_port: container_port}
            env: Environment variables
            networks: Networks to attach
            mounts: Volume mounts
            constraints: Placement constraints
            labels: Service labels

        Returns:
            SwarmResult with success status and service_id
        """
        cmd = ["docker", "service", "create", "--name", name]

        # Add secrets
        for secret in secrets:
            cmd.extend(["--secret", secret])

        # Add port mappings
        if ports:
            for host_port, container_port in ports.items():
                cmd.extend(["--publish", f"{host_port}:{container_port}"])

        # Add environment variables
        if env:
            for key, val in env.items():
                cmd.extend(["--env", f"{key}={val}"])

        # Add networks
        if networks:
            for network in networks:
                cmd.extend(["--network", network])

        # Add mounts
        if mounts:
            for mount in mounts:
                cmd.extend(["--mount", mount])

        # Add constraints
        if constraints:
            for constraint in constraints:
                cmd.extend(["--constraint", constraint])

        # Add labels
        if labels:
            for key, val in labels.items():
                cmd.extend(["--label", f"{key}={val}"])

        # Add replicas
        cmd.extend(["--replicas", str(replicas)])

        # Add image
        cmd.append(image)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                service_id = result.stdout.strip()
                self.logger.info(
                    "service_created",
                    name=name,
                    secrets=secrets,
                    replicas=replicas,
                )
                return SwarmResult(
                    success=True,
                    message=f"Service '{name}' created",
                    data={"service_id": service_id}
                )
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def update_service(
        self,
        name: str,
        image: Optional[str] = None,
        replicas: Optional[int] = None,
        add_secrets: Optional[list[str]] = None,
        remove_secrets: Optional[list[str]] = None,
        env_add: Optional[dict[str, str]] = None,
        env_remove: Optional[list[str]] = None,
    ) -> SwarmResult:
        """
        Update a Docker service.

        Args:
            name: Service name
            image: New image (optional)
            replicas: New replica count (optional)
            add_secrets: Secrets to add
            remove_secrets: Secrets to remove
            env_add: Environment variables to add
            env_remove: Environment variable names to remove

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "service", "update"]

        if image:
            cmd.extend(["--image", image])

        if replicas is not None:
            cmd.extend(["--replicas", str(replicas)])

        if add_secrets:
            for secret in add_secrets:
                cmd.extend(["--secret-add", secret])

        if remove_secrets:
            for secret in remove_secrets:
                cmd.extend(["--secret-rm", secret])

        if env_add:
            for key, val in env_add.items():
                cmd.extend(["--env-add", f"{key}={val}"])

        if env_remove:
            for key in env_remove:
                cmd.extend(["--env-rm", key])

        cmd.append(name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("service_updated", name=name)
                return SwarmResult(success=True, message=f"Service '{name}' updated")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def remove_service(self, name: str) -> SwarmResult:
        """
        Remove a Docker service.

        Args:
            name: Service name to remove

        Returns:
            SwarmResult with success status
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "service", "rm", name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.logger.info("service_removed", name=name)
                return SwarmResult(success=True, message=f"Service '{name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_services(self) -> list[dict]:
        """
        List all Docker services.

        Returns:
            List of service info dicts
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "service", "ls", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                services = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        services.append(json.loads(line))
                return services
            return []
        except Exception:
            return []

    async def get_service_logs(
        self,
        name: str,
        tail: int = 100,
        since: Optional[str] = None,
    ) -> str:
        """
        Get logs from a Docker service.

        Args:
            name: Service name
            tail: Number of lines to return
            since: Only return logs since this time (e.g., "10m", "2h")

        Returns:
            Log output as string
        """
        cmd = ["docker", "service", "logs", "--tail", str(tail)]

        if since:
            cmd.extend(["--since", since])

        cmd.append(name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error getting logs: {e}"

    # =========================================================================
    # DOCKER AI (Gordon) - Ask AI for Docker help
    # =========================================================================

    async def ask_gordon(self, question: str) -> SwarmResult:
        """
        Ask Docker AI (Gordon) a question.

        Gordon is Docker's AI assistant that can help with:
        - Writing Dockerfiles
        - Debugging container issues
        - Best practices
        - Docker Compose configurations

        Args:
            question: Question to ask Gordon

        Returns:
            SwarmResult with Gordon's response
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "ai", question],
                capture_output=True,
                text=True,
                timeout=120,  # AI responses can take time
            )
            if result.returncode == 0:
                return SwarmResult(
                    success=True,
                    message="Gordon responded",
                    data={"response": result.stdout}
                )
            return SwarmResult(success=False, message=result.stderr or "Gordon unavailable")
        except subprocess.TimeoutExpired:
            return SwarmResult(success=False, message="Gordon response timed out")
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # DOCKER COMPOSE / STACKS
    # =========================================================================

    async def compose_up(
        self,
        compose_file: Optional[str] = None,
        project_name: Optional[str] = None,
        detach: bool = True,
        build: bool = False,
        services: Optional[list[str]] = None,
    ) -> SwarmResult:
        """
        Start services with Docker Compose.

        Args:
            compose_file: Path to compose file (default: docker-compose.yml)
            project_name: Project name
            detach: Run in background
            build: Build images before starting
            services: Specific services to start (default: all)

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "compose"]

        if compose_file:
            cmd.extend(["-f", compose_file])
        if project_name:
            cmd.extend(["-p", project_name])

        cmd.append("up")

        if detach:
            cmd.append("-d")
        if build:
            cmd.append("--build")

        if services:
            cmd.extend(services)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                self.logger.info("compose_up", project=project_name)
                return SwarmResult(success=True, message="Compose services started")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def compose_down(
        self,
        compose_file: Optional[str] = None,
        project_name: Optional[str] = None,
        volumes: bool = False,
        remove_orphans: bool = False,
    ) -> SwarmResult:
        """
        Stop and remove Docker Compose services.

        Args:
            compose_file: Path to compose file
            project_name: Project name
            volumes: Remove volumes
            remove_orphans: Remove orphan containers

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "compose"]

        if compose_file:
            cmd.extend(["-f", compose_file])
        if project_name:
            cmd.extend(["-p", project_name])

        cmd.append("down")

        if volumes:
            cmd.append("-v")
        if remove_orphans:
            cmd.append("--remove-orphans")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message="Compose services stopped")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def stack_deploy(
        self,
        stack_name: str,
        compose_file: str,
        prune: bool = False,
    ) -> SwarmResult:
        """
        Deploy a stack to Docker Swarm.

        Args:
            stack_name: Name of the stack
            compose_file: Path to compose file
            prune: Prune services that are no longer referenced

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "stack", "deploy", "-c", compose_file]

        if prune:
            cmd.append("--prune")

        cmd.append(stack_name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("stack_deployed", name=stack_name)
                return SwarmResult(success=True, message=f"Stack '{stack_name}' deployed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def stack_remove(self, stack_name: str) -> SwarmResult:
        """Remove a Docker stack."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "stack", "rm", stack_name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Stack '{stack_name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_stacks(self) -> list[dict]:
        """List all Docker stacks."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "stack", "ls", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            return []
        except Exception:
            return []

    # =========================================================================
    # NETWORKS
    # =========================================================================

    async def create_network(
        self,
        name: str,
        driver: str = "overlay",
        attachable: bool = True,
        internal: bool = False,
        subnet: Optional[str] = None,
        labels: Optional[dict[str, str]] = None,
    ) -> SwarmResult:
        """
        Create a Docker network.

        Args:
            name: Network name
            driver: Network driver (bridge, overlay, macvlan)
            attachable: Allow manual container attachment (overlay only)
            internal: Restrict external access
            subnet: Subnet in CIDR format (e.g., "10.0.0.0/24")
            labels: Network labels

        Returns:
            SwarmResult with network_id
        """
        cmd = ["docker", "network", "create", "--driver", driver]

        if attachable and driver == "overlay":
            cmd.append("--attachable")
        if internal:
            cmd.append("--internal")
        if subnet:
            cmd.extend(["--subnet", subnet])
        if labels:
            for key, val in labels.items():
                cmd.extend(["--label", f"{key}={val}"])

        cmd.append(name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("network_created", name=name, driver=driver)
                return SwarmResult(
                    success=True,
                    message=f"Network '{name}' created",
                    data={"network_id": result.stdout.strip()}
                )
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def remove_network(self, name: str) -> SwarmResult:
        """Remove a Docker network."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "network", "rm", name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Network '{name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_networks(self) -> list[dict]:
        """List all Docker networks."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "network", "ls", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            return []
        except Exception:
            return []

    async def connect_network(self, network: str, container: str) -> SwarmResult:
        """Connect a container to a network."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "network", "connect", network, container],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Connected {container} to {network}")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # VOLUMES
    # =========================================================================

    async def create_volume(
        self,
        name: str,
        driver: str = "local",
        labels: Optional[dict[str, str]] = None,
        driver_opts: Optional[dict[str, str]] = None,
    ) -> SwarmResult:
        """
        Create a Docker volume.

        Args:
            name: Volume name
            driver: Volume driver
            labels: Volume labels
            driver_opts: Driver-specific options

        Returns:
            SwarmResult with volume name
        """
        cmd = ["docker", "volume", "create", "--driver", driver]

        if labels:
            for key, val in labels.items():
                cmd.extend(["--label", f"{key}={val}"])
        if driver_opts:
            for key, val in driver_opts.items():
                cmd.extend(["--opt", f"{key}={val}"])

        cmd.append(name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                self.logger.info("volume_created", name=name)
                return SwarmResult(success=True, message=f"Volume '{name}' created")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def remove_volume(self, name: str, force: bool = False) -> SwarmResult:
        """Remove a Docker volume."""
        cmd = ["docker", "volume", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(name)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Volume '{name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_volumes(self) -> list[dict]:
        """List all Docker volumes."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "volume", "ls", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            return []
        except Exception:
            return []

    async def prune_volumes(self, force: bool = True) -> SwarmResult:
        """Remove all unused volumes."""
        cmd = ["docker", "volume", "prune"]
        if force:
            cmd.append("-f")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message="Unused volumes pruned")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # CONFIGS (similar to secrets but for non-sensitive data)
    # =========================================================================

    async def create_config(self, name: str, file_path: str) -> SwarmResult:
        """
        Create a Docker config from a file.

        Configs are like secrets but for non-sensitive configuration data.

        Args:
            name: Config name
            file_path: Path to config file

        Returns:
            SwarmResult with config_id
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "config", "create", name, file_path],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.logger.info("config_created", name=name)
                return SwarmResult(
                    success=True,
                    message=f"Config '{name}' created",
                    data={"config_id": result.stdout.strip()}
                )
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def create_config_from_string(self, name: str, content: str) -> SwarmResult:
        """Create a Docker config from string content via stdin."""
        try:
            process = await asyncio.to_thread(
                subprocess.Popen,
                ["docker", "config", "create", name, "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(input=content.encode())

            if process.returncode == 0:
                self.logger.info("config_created", name=name)
                return SwarmResult(
                    success=True,
                    message=f"Config '{name}' created",
                    data={"config_id": stdout.decode().strip()}
                )
            return SwarmResult(success=False, message=stderr.decode())
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def remove_config(self, name: str) -> SwarmResult:
        """Remove a Docker config."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "config", "rm", name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Config '{name}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_configs(self) -> list[str]:
        """List all Docker configs."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "config", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n") if result.stdout.strip() else []
            return []
        except Exception:
            return []

    # =========================================================================
    # BUILDER / BUILDX
    # =========================================================================

    async def build_image(
        self,
        tag: str,
        context: str = ".",
        dockerfile: Optional[str] = None,
        build_args: Optional[dict[str, str]] = None,
        no_cache: bool = False,
        platform: Optional[str] = None,
    ) -> SwarmResult:
        """
        Build a Docker image using buildx.

        Args:
            tag: Image tag (e.g., "myapp:latest")
            context: Build context path
            dockerfile: Dockerfile path
            build_args: Build arguments
            no_cache: Don't use cache
            platform: Target platform (e.g., "linux/amd64,linux/arm64")

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "buildx", "build", "-t", tag]

        if dockerfile:
            cmd.extend(["-f", dockerfile])
        if build_args:
            for key, val in build_args.items():
                cmd.extend(["--build-arg", f"{key}={val}"])
        if no_cache:
            cmd.append("--no-cache")
        if platform:
            cmd.extend(["--platform", platform])

        cmd.append(context)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                self.logger.info("image_built", tag=tag)
                return SwarmResult(success=True, message=f"Image '{tag}' built")
            return SwarmResult(success=False, message=result.stderr)
        except subprocess.TimeoutExpired:
            return SwarmResult(success=False, message="Build timed out")
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def push_image(self, tag: str) -> SwarmResult:
        """Push an image to a registry."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "push", tag],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Image '{tag}' pushed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def pull_image(self, tag: str) -> SwarmResult:
        """Pull an image from a registry."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "pull", tag],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Image '{tag}' pulled")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_images(self) -> list[dict]:
        """List all Docker images."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "image", "ls", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            return []
        except Exception:
            return []

    async def remove_image(self, tag: str, force: bool = False) -> SwarmResult:
        """Remove a Docker image."""
        cmd = ["docker", "image", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(tag)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Image '{tag}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # CONTAINER MANAGEMENT
    # =========================================================================

    async def run_container(
        self,
        image: str,
        name: Optional[str] = None,
        detach: bool = True,
        ports: Optional[dict[int, int]] = None,
        env: Optional[dict[str, str]] = None,
        volumes: Optional[list[str]] = None,
        network: Optional[str] = None,
        command: Optional[str] = None,
        remove: bool = False,
    ) -> SwarmResult:
        """
        Run a Docker container.

        Args:
            image: Image to run
            name: Container name
            detach: Run in background
            ports: Port mappings
            env: Environment variables
            volumes: Volume mounts
            network: Network to connect
            command: Command to run
            remove: Auto-remove when stopped

        Returns:
            SwarmResult with container_id
        """
        cmd = ["docker", "container", "run"]

        if name:
            cmd.extend(["--name", name])
        if detach:
            cmd.append("-d")
        if remove:
            cmd.append("--rm")
        if ports:
            for host, container in ports.items():
                cmd.extend(["-p", f"{host}:{container}"])
        if env:
            for key, val in env.items():
                cmd.extend(["-e", f"{key}={val}"])
        if volumes:
            for vol in volumes:
                cmd.extend(["-v", vol])
        if network:
            cmd.extend(["--network", network])

        cmd.append(image)

        if command:
            cmd.extend(command.split())

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                container_id = result.stdout.strip()
                self.logger.info("container_started", name=name or container_id[:12])
                return SwarmResult(
                    success=True,
                    message="Container started",
                    data={"container_id": container_id}
                )
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def stop_container(self, name_or_id: str, timeout: int = 10) -> SwarmResult:
        """Stop a running container."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "container", "stop", "-t", str(timeout), name_or_id],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Container '{name_or_id}' stopped")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def remove_container(self, name_or_id: str, force: bool = False) -> SwarmResult:
        """Remove a container."""
        cmd = ["docker", "container", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(name_or_id)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message=f"Container '{name_or_id}' removed")
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def list_containers(self, all: bool = False) -> list[dict]:
        """List Docker containers."""
        cmd = ["docker", "container", "ls", "--format", "{{json .}}"]
        if all:
            cmd.append("-a")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            return []
        except Exception:
            return []

    async def exec_in_container(
        self,
        container: str,
        command: list[str],
        interactive: bool = False,
    ) -> SwarmResult:
        """Execute a command in a running container."""
        cmd = ["docker", "container", "exec"]
        if interactive:
            cmd.append("-it")
        cmd.append(container)
        cmd.extend(command)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            return SwarmResult(
                success=result.returncode == 0,
                message=result.stdout or result.stderr,
                data={"exit_code": result.returncode}
            )
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def get_container_logs(
        self,
        name_or_id: str,
        tail: int = 100,
        follow: bool = False,
    ) -> str:
        """Get logs from a container."""
        cmd = ["docker", "container", "logs", "--tail", str(tail)]
        if follow:
            cmd.append("-f")
        cmd.append(name_or_id)

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error: {e}"

    # =========================================================================
    # SYSTEM MANAGEMENT
    # =========================================================================

    async def system_info(self) -> dict:
        """Get Docker system information."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "system", "info", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return {}
        except Exception:
            return {}

    async def system_df(self) -> dict:
        """Get Docker disk usage."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "system", "df", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                import json
                return {"items": [json.loads(line) for line in result.stdout.strip().split("\n") if line]}
            return {}
        except Exception:
            return {}

    async def system_prune(
        self,
        all: bool = False,
        volumes: bool = False,
        force: bool = True,
    ) -> SwarmResult:
        """
        Remove unused Docker data.

        Args:
            all: Remove all unused images (not just dangling)
            volumes: Also prune volumes
            force: Don't prompt for confirmation

        Returns:
            SwarmResult with success status
        """
        cmd = ["docker", "system", "prune"]
        if all:
            cmd.append("-a")
        if volumes:
            cmd.append("--volumes")
        if force:
            cmd.append("-f")

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                return SwarmResult(success=True, message="System pruned", data={"output": result.stdout})
            return SwarmResult(success=False, message=result.stderr)
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # DOCKER DEBUG (get shell into any image or container)
    # =========================================================================

    async def debug_container(self, target: str) -> SwarmResult:
        """
        Get debug shell into a container or image.

        Uses 'docker debug' to get a shell with debugging tools.

        Args:
            target: Container ID/name or image name

        Returns:
            SwarmResult (note: interactive shell not supported, use for diagnostics)
        """
        try:
            # Run a diagnostic command instead of interactive shell
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "debug", target, "--", "sh", "-c", "uname -a && cat /etc/os-release 2>/dev/null || true"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return SwarmResult(
                success=result.returncode == 0,
                message=result.stdout or result.stderr,
                data={"exit_code": result.returncode}
            )
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    # =========================================================================
    # DOCKER SCOUT (security scanning)
    # =========================================================================

    async def scout_quickview(self, image: str) -> SwarmResult:
        """
        Get quick security overview of an image.

        Args:
            image: Image to scan

        Returns:
            SwarmResult with vulnerability summary
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "scout", "quickview", image],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return SwarmResult(
                success=result.returncode == 0,
                message="Scout scan complete",
                data={"report": result.stdout}
            )
        except Exception as e:
            return SwarmResult(success=False, message=str(e))

    async def scout_cves(self, image: str) -> SwarmResult:
        """
        Get CVE details for an image.

        Args:
            image: Image to scan

        Returns:
            SwarmResult with CVE details
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "scout", "cves", image],
                capture_output=True,
                text=True,
                timeout=180,
            )
            return SwarmResult(
                success=result.returncode == 0,
                message="CVE scan complete",
                data={"report": result.stdout}
            )
        except Exception as e:
            return SwarmResult(success=False, message=str(e))
