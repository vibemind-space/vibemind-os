"""
Docker Secrets Team Agent - Manages Docker Swarm secrets securely.

Security patterns:
- Secrets via stdin (NEVER CLI args)
- No secrets in logs
- Immediate memory cleanup after use

This agent follows the AutonomousAgent pattern from deployment_team_agent.py.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    swarm_initialized_event,
    swarm_init_failed_event,
    secret_created_event,
    secret_create_failed_event,
    service_deployed_event,
    service_deploy_failed_event,
)
from ..mind.shared_state import SharedState
from ..tools.docker_swarm_tool import DockerSwarmTool, SwarmStatus, SwarmResult

logger = structlog.get_logger(__name__)


@dataclass
class SecretRequest:
    """Request to create a secret."""
    name: str
    # Value loaded from secure source, cleared after use
    source: str  # "env", "file", "prompt", "direct"
    env_var: Optional[str] = None
    file_path: Optional[str] = None


class DockerSecretsTeamAgent(AutonomousAgent):
    """
    Docker Secrets Team Agent - Coordinates secure secret management.

    Follows AutonomousAgent pattern from deployment_team_agent.py.

    Workflow:
    1. Subscribe to SECRET_CREATE_REQUESTED, SERVICE_DEPLOY_REQUESTED
    2. Ensure Swarm is initialized
    3. Create secrets securely via stdin
    4. Deploy services with secrets attached

    Security:
    - Secrets are NEVER passed as CLI arguments
    - Secrets are NEVER logged
    - Values are cleared from memory immediately after use

    Usage:
        # Via events
        await event_bus.publish(Event(
            type=EventType.SECRET_CREATE_REQUESTED,
            source="my_component",
            data={
                "name": "db_password",
                "env_var": "DB_PASSWORD",  # Load from env
            }
        ))

        # Or direct API
        agent = DockerSecretsTeamAgent(...)
        await agent.create_secret("api_key", "secret_value")
    """

    def __init__(
        self,
        name: str = "DockerSecretsTeam",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # Configuration
        auto_init_swarm: bool = True,
        secrets_file: Optional[str] = None,
    ):
        """
        Initialize the Docker Secrets Team Agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Seconds between event checks
            memory_tool: Optional memory tool for patterns
            auto_init_swarm: Automatically initialize swarm if not active
            secrets_file: Path to JSON file containing secrets
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        self.auto_init_swarm = auto_init_swarm
        self.secrets_file = secrets_file
        self._swarm_tool = DockerSwarmTool()
        self._swarm_ready = False
        self._created_secrets: set[str] = set()

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.SECRET_CREATE_REQUESTED,
            EventType.SERVICE_DEPLOY_REQUESTED,
            EventType.SWARM_INIT_REQUESTED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Act on secret/service deployment requests."""
        for event in events:
            if event.type in self.subscribed_events:
                return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Process secret/service deployment requests."""
        for event in events:
            if event.type == EventType.SWARM_INIT_REQUESTED:
                return await self._handle_swarm_init(event)

            if event.type == EventType.SECRET_CREATE_REQUESTED:
                return await self._handle_secret_create(event)

            if event.type == EventType.SERVICE_DEPLOY_REQUESTED:
                return await self._handle_service_deploy(event)

        return None

    async def _ensure_swarm_ready(self) -> bool:
        """Ensure Docker Swarm is initialized."""
        if self._swarm_ready:
            return True

        status = await self._swarm_tool.check_swarm_status()

        if status == SwarmStatus.ACTIVE:
            self._swarm_ready = True
            self.logger.info("swarm_already_active")
            return True

        if self.auto_init_swarm:
            self.logger.info("initializing_swarm")
            result = await self._swarm_tool.init_swarm()
            if result.success:
                self._swarm_ready = True
                await self.event_bus.publish(swarm_initialized_event(source=self.name))
                return True

            self.logger.error("swarm_init_failed", error=result.message)
            await self.event_bus.publish(swarm_init_failed_event(
                source=self.name,
                error_message=result.message,
            ))

        return False

    async def _handle_swarm_init(self, event: Event) -> Event:
        """Handle swarm initialization request."""
        self.logger.info("handling_swarm_init_request")

        if await self._ensure_swarm_ready():
            return swarm_initialized_event(source=self.name)
        return swarm_init_failed_event(
            source=self.name,
            error_message="Failed to initialize swarm",
        )

    async def _handle_secret_create(self, event: Event) -> Event:
        """
        Handle secret creation request.

        Event data:
        - name: Secret name (required)
        - value: Secret value (ONLY if passed securely)
        - env_var: Load value from this environment variable
        - file_path: Load value from this file
        """
        self.logger.info("handling_secret_create_request")

        if not await self._ensure_swarm_ready():
            return secret_create_failed_event(
                source=self.name,
                error_message="Swarm not ready",
            )

        data = event.data or {}
        name = data.get("name")
        if not name:
            return secret_create_failed_event(
                source=self.name,
                error_message="Secret name required",
            )

        # Check if secret already exists
        if await self._swarm_tool.secret_exists(name):
            self.logger.info("secret_already_exists", name=name)
            return secret_created_event(
                source=self.name,
                name=name,
                already_existed=True,
            )

        # Load value from secure source
        value = await self._load_secret_value(data)
        if not value:
            return secret_create_failed_event(
                source=self.name,
                error_message="Could not load secret value",
                name=name,
            )

        # Create secret (value passed via stdin internally)
        result = await self._swarm_tool.create_secret_secure(name, value)

        # Clear value from memory IMMEDIATELY
        value = None  # noqa: F841

        if result.success:
            self._created_secrets.add(name)
            self.logger.info("secret_created_successfully", name=name)
            return secret_created_event(
                source=self.name,
                name=name,
                secret_id=result.data.get("secret_id"),
            )

        return secret_create_failed_event(
            source=self.name,
            error_message=result.message,
            name=name,
        )

    async def _load_secret_value(self, data: dict) -> Optional[str]:
        """
        Load secret value from secure source.

        Sources (in order of precedence):
        1. Direct value in data["value"]
        2. Environment variable specified in data["env_var"]
        3. File path specified in data["file_path"]
        4. Secrets JSON file (if configured)

        Args:
            data: Event data containing source information

        Returns:
            Secret value or None if not found
        """
        import os

        # Direct value (should only come from secure sources)
        if "value" in data:
            return data["value"]

        # From environment variable
        if "env_var" in data:
            value = os.environ.get(data["env_var"])
            if value:
                return value
            self.logger.warning(
                "env_var_not_found",
                env_var=data["env_var"],
            )

        # From file
        if "file_path" in data:
            try:
                with open(data["file_path"], "r") as f:
                    return f.read().strip()
            except Exception as e:
                self.logger.warning(
                    "file_read_failed",
                    file_path=data["file_path"],
                    error=str(e),
                )

        # From secrets.json
        if self.secrets_file and "name" in data:
            try:
                import json
                with open(self.secrets_file, "r") as f:
                    secrets = json.load(f)
                value = secrets.get(data["name"])
                if value:
                    return value
            except Exception as e:
                self.logger.warning(
                    "secrets_file_read_failed",
                    file=self.secrets_file,
                    error=str(e),
                )

        return None

    async def _handle_service_deploy(self, event: Event) -> Event:
        """
        Handle service deployment with secrets.

        Event data:
        - name: Service name (required)
        - image: Docker image (required)
        - secrets: List of secret names to attach
        - replicas: Number of replicas (default 1)
        - ports: Port mappings {host_port: container_port}
        - env: Environment variables
        - networks: Networks to attach
        """
        self.logger.info("handling_service_deploy_request")

        if not await self._ensure_swarm_ready():
            return service_deploy_failed_event(
                source=self.name,
                error_message="Swarm not ready",
            )

        data = event.data or {}
        name = data.get("name")
        image = data.get("image")
        secrets = data.get("secrets", [])

        if not name or not image:
            return service_deploy_failed_event(
                source=self.name,
                error_message="Service name and image required",
            )

        # Verify all secrets exist
        for secret in secrets:
            if not await self._swarm_tool.secret_exists(secret):
                return service_deploy_failed_event(
                    source=self.name,
                    error_message=f"Secret '{secret}' does not exist",
                    name=name,
                    missing_secret=secret,
                )

        result = await self._swarm_tool.create_service_with_secrets(
            name=name,
            image=image,
            secrets=secrets,
            replicas=data.get("replicas", 1),
            ports=data.get("ports"),
            env=data.get("env"),
            networks=data.get("networks"),
        )

        if result.success:
            self.logger.info(
                "service_deployed_successfully",
                name=name,
                secrets=secrets,
            )
            return service_deployed_event(
                source=self.name,
                name=name,
                secrets=secrets,
                service_id=result.data.get("service_id"),
            )

        return service_deploy_failed_event(
            source=self.name,
            error_message=result.message,
            name=name,
        )

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return "Managing Docker Swarm secrets"

    # =====================================================================
    # Convenience methods for direct API usage
    # =====================================================================

    async def create_secret(self, name: str, value: str) -> bool:
        """
        Create a secret directly (convenience method).

        SECURITY: Use this when you already have the value securely.
        The value is passed to Docker via stdin and cleared from memory.

        Args:
            name: Secret name
            value: Secret value

        Returns:
            True if successful
        """
        if not await self._ensure_swarm_ready():
            return False

        result = await self._swarm_tool.create_secret_secure(name, value)

        # Clear value from memory
        value = None  # noqa: F841

        if result.success:
            self._created_secrets.add(name)
        return result.success

    async def create_secret_from_env(self, name: str, env_var: str) -> bool:
        """
        Create a secret from an environment variable.

        Args:
            name: Secret name
            env_var: Environment variable containing the value

        Returns:
            True if successful
        """
        import os

        value = os.environ.get(env_var)
        if not value:
            self.logger.error("env_var_not_found", env_var=env_var)
            return False

        result = await self.create_secret(name, value)
        value = None  # Clear
        return result

    async def create_secret_from_file(self, name: str, file_path: str) -> bool:
        """
        Create a secret from a file.

        Args:
            name: Secret name
            file_path: Path to file containing the value

        Returns:
            True if successful
        """
        try:
            with open(file_path, "r") as f:
                value = f.read().strip()
            result = await self.create_secret(name, value)
            value = None  # Clear
            return result
        except Exception as e:
            self.logger.error("file_read_failed", file_path=file_path, error=str(e))
            return False

    async def deploy_service(
        self,
        name: str,
        image: str,
        secrets: list[str],
        **kwargs,
    ) -> bool:
        """
        Deploy a service with secrets (convenience method).

        Args:
            name: Service name
            image: Docker image
            secrets: List of secret names to attach
            **kwargs: Additional args (replicas, ports, env, networks)

        Returns:
            True if successful
        """
        if not await self._ensure_swarm_ready():
            return False

        result = await self._swarm_tool.create_service_with_secrets(
            name=name,
            image=image,
            secrets=secrets,
            **kwargs,
        )
        return result.success

    async def list_secrets(self) -> list[str]:
        """Get list of all secrets."""
        return await self._swarm_tool.list_secrets()

    async def remove_secret(self, name: str) -> bool:
        """Remove a secret."""
        result = await self._swarm_tool.remove_secret(name)
        if result.success:
            self._created_secrets.discard(name)
        return result.success

    async def remove_service(self, name: str) -> bool:
        """Remove a service."""
        result = await self._swarm_tool.remove_service(name)
        return result.success

    def get_created_secrets(self) -> set[str]:
        """Get set of secrets created by this agent instance."""
        return self._created_secrets.copy()


# =========================================================================
# Helper function for loading secrets from a JSON file
# =========================================================================

def load_secrets_from_file(file_path: str) -> dict[str, str]:
    """
    Load secrets from a JSON file.

    Expected format:
    {
        "secret_name": "secret_value",
        "db_password": "...",
        "api_key": "..."
    }

    Args:
        file_path: Path to JSON secrets file

    Returns:
        Dictionary of secret names to values
    """
    import json

    with open(file_path, "r") as f:
        return json.load(f)
