"""
Environment Report Agent - Collects and validates required API keys/secrets.

This agent:
1. Reads environment requirements from config or requirements.json
2. Validates which env vars are already set
3. Seeds SECRET_CREATE_REQUESTED events for Docker secrets
4. Reports missing/configured status to the event bus

Usage:
    # Define requirements in code
    agent = EnvironmentReportAgent(
        env_requirements=[
            EnvRequirement("ANTHROPIC_API_KEY", "Claude API key"),
            EnvRequirement("GITHUB_TOKEN", "GitHub token", required=False),
        ]
    )

    # Or load from requirements.json "environment" section
    agent = EnvironmentReportAgent(requirements_path="requirements.json")
"""

import asyncio
import getpass
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Union
import structlog

# Type alias for secret input callback (supports both sync and async)
# AutoGen 0.4 compatible: works with Console.input() or custom callbacks
SecretInputCallback = Callable[[str, str], Union[str, Awaitable[str]]]

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    env_missing_required_event,
    env_report_complete_event,
    secret_create_requested_event,
)
from ..mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


@dataclass
class EnvRequirement:
    """Definition of a required environment variable."""
    name: str                      # Secret/env var name (e.g., "ANTHROPIC_API_KEY")
    description: str               # Human-readable description
    required: bool = True          # Is this mandatory?
    source: str = "env"            # Where to load from: "env", "file", "prompt"
    docker_secret: bool = True     # Create as Docker secret?
    default: Optional[str] = None  # Default value if not provided


# Pre-defined common requirements for the Coding Engine
COMMON_ENV_REQUIREMENTS = [
    EnvRequirement(
        "ANTHROPIC_API_KEY",
        "Claude API key for AI operations",
        required=True,
        docker_secret=True,
    ),
    EnvRequirement(
        "GITHUB_TOKEN",
        "GitHub token for cloud tests and releases",
        required=False,
        docker_secret=True,
    ),
    EnvRequirement(
        "SUPERMEMORY_API_KEY",
        "Supermemory API for pattern storage",
        required=False,
        docker_secret=True,
    ),
    EnvRequirement(
        "OLLAMA_BASE_URL",
        "Ollama API URL for local LLM (default: http://localhost:11434)",
        required=False,
        docker_secret=False,
        default="http://localhost:11434",
    ),
]


class EnvironmentReportAgent(AutonomousAgent):
    """
    Environment Report Agent - Seeds environment setup events.

    This agent validates that required environment variables/API keys
    are configured and seeds SECRET_CREATE_REQUESTED events for the
    DockerSecretsTeamAgent to create Docker secrets.

    Workflow:
    1. On SYSTEM_READY or ENV_REPORT_REQUESTED, check required env vars
    2. Report which are configured vs missing
    3. Seed SECRET_CREATE_REQUESTED events for configured secrets
    4. Publish ENV_REPORT_COMPLETE with status

    Event Flow:
        SYSTEM_READY
            → EnvironmentReportAgent checks os.environ
            → Publishes SECRET_CREATE_REQUESTED for each configured secret
            → DockerSecretsTeamAgent creates Docker secrets
            → Publishes ENV_REPORT_COMPLETE with full status

    Configuration:
        env_requirements: List of EnvRequirement defining what's needed
        requirements_path: JSON file with "environment" section
        auto_seed_secrets: Automatically seed SECRET_CREATE_REQUESTED events
        fail_on_missing: Raise error if required env var is missing
    """

    def __init__(
        self,
        name: str = "EnvironmentReport",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # Environment configuration
        env_requirements: Optional[list[EnvRequirement]] = None,
        requirements_path: Optional[str] = None,
        auto_seed_secrets: bool = True,
        fail_on_missing: bool = False,
        use_common_requirements: bool = True,
        # User input configuration (AutoGen 0.4 compatible)
        prompt_for_missing: bool = False,
        input_callback: Optional[SecretInputCallback] = None,
    ):
        """
        Initialize Environment Report Agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Event polling interval
            memory_tool: Memory tool for patterns
            env_requirements: List of EnvRequirement to check
            requirements_path: Path to JSON with "environment" section
            auto_seed_secrets: Auto-publish SECRET_CREATE_REQUESTED events
            fail_on_missing: Fail if required env var is missing
            use_common_requirements: Include COMMON_ENV_REQUIREMENTS
            prompt_for_missing: Prompt user for missing required secrets
            input_callback: Custom input callback (AutoGen 0.4 Console compatible)
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        # Build requirements list
        self.env_requirements: list[EnvRequirement] = []

        if use_common_requirements:
            self.env_requirements.extend(COMMON_ENV_REQUIREMENTS)

        if env_requirements:
            self.env_requirements.extend(env_requirements)

        self.requirements_path = requirements_path
        self.auto_seed_secrets = auto_seed_secrets
        self.fail_on_missing = fail_on_missing
        self.prompt_for_missing = prompt_for_missing
        self.input_callback = input_callback

        self._report_generated = False
        self._configured: dict[str, bool] = {}
        self._secrets_seeded: set[str] = set()

        # Load from JSON if path provided
        if requirements_path:
            self._load_requirements_from_file()

        self.logger.info(
            "environment_report_agent_initialized",
            total_requirements=len(self.env_requirements),
            auto_seed=auto_seed_secrets,
            prompt_for_missing=prompt_for_missing,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.SYSTEM_READY,
            EventType.ENV_REPORT_REQUESTED,
            EventType.DEPLOY_STARTED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should generate environment report."""
        # Only generate report once per session unless reset
        if self._report_generated:
            # But respond to explicit requests
            for event in events:
                if event.type == EventType.ENV_REPORT_REQUESTED:
                    self._report_generated = False  # Reset for re-check
                    return True
            return False

        for event in events:
            if event.type in self.subscribed_events:
                return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Generate environment report and seed secrets."""
        self.logger.info("generating_environment_report")

        # Generate the initial report
        report = await self._generate_report()

        # Log summary
        self.logger.info(
            "environment_report_generated",
            configured=report["configured_count"],
            missing=len(report["missing"]),
            missing_required=report["missing_required"],
        )

        # Prompt for missing required secrets if enabled
        if report["has_missing_required"] and self.prompt_for_missing:
            self.logger.info(
                "prompting_for_missing_secrets",
                count=len(report["missing_required"]),
            )
            await self._prompt_for_missing_secrets(report)
            # Regenerate report after user input
            report = await self._generate_report()
            self.logger.info(
                "report_regenerated_after_prompts",
                configured=report["configured_count"],
                missing_required=report["missing_required"],
            )

        # Check for missing required (after potential prompting)
        if report["has_missing_required"]:
            self.logger.warning(
                "missing_required_env_vars",
                missing=report["missing_required"],
            )

            if self.fail_on_missing:
                await self.event_bus.publish(env_missing_required_event(
                    source=self.name,
                    missing_vars=report["missing_required"],
                    report=report,
                ))
                return env_report_complete_event(
                    source=self.name,
                    success=False,
                    report=report,
                    error_message="Missing required environment variables",
                )

        # Seed secrets for configured env vars
        if self.auto_seed_secrets:
            await self._seed_secret_events(report)

        self._report_generated = True

        # Update shared state with env status
        if self.shared_state:
            self.shared_state.set("env_configured", report["configured_count"])
            self.shared_state.set("env_missing", len(report["missing"]))
            self.shared_state.set("env_ready", not report["has_missing_required"])

        # Publish report
        return env_report_complete_event(
            source=self.name,
            success=not report["has_missing_required"],
            report=report,
        )

    async def _generate_report(self) -> dict:
        """
        Check all env requirements and generate report.

        Returns:
            Dict with configured, missing, and summary fields
        """
        configured = []
        missing = []
        missing_required = []

        for req in self.env_requirements:
            value = os.environ.get(req.name)

            # Check for default value
            if not value and req.default:
                value = req.default
                # Set it in environment for downstream use
                os.environ[req.name] = value
                self.logger.debug(
                    "using_default_value",
                    name=req.name,
                )

            if value:
                configured.append({
                    "name": req.name,
                    "description": req.description,
                    "docker_secret": req.docker_secret,
                    "source": req.source,
                    "has_value": True,
                })
                self._configured[req.name] = True
            else:
                missing.append({
                    "name": req.name,
                    "description": req.description,
                    "required": req.required,
                    "docker_secret": req.docker_secret,
                })
                self._configured[req.name] = False

                if req.required:
                    missing_required.append(req.name)

        return {
            "configured": configured,
            "missing": missing,
            "missing_required": missing_required,
            "has_missing_required": len(missing_required) > 0,
            "total": len(self.env_requirements),
            "configured_count": len(configured),
        }

    async def _seed_secret_events(self, report: dict) -> None:
        """
        Seed SECRET_CREATE_REQUESTED events for configured env vars.

        Only seeds events for env vars that:
        - Are configured (have a value)
        - Have docker_secret=True
        - Haven't been seeded yet this session
        """
        for item in report["configured"]:
            name = item["name"]

            # Skip if not a Docker secret or already seeded
            if not item["docker_secret"]:
                continue
            if name in self._secrets_seeded:
                continue

            self.logger.info("seeding_secret_create_event", name=name)

            await self.event_bus.publish(secret_create_requested_event(
                source=self.name,
                name=name,
                env_var=name,  # Load value from this env var
                description=item["description"],
            ))

            self._secrets_seeded.add(name)

        self.logger.info(
            "secrets_seeded",
            count=len(self._secrets_seeded),
        )

    async def _prompt_for_secret(self, name: str, description: str) -> Optional[str]:
        """
        Prompt user for a secret value securely.

        AutoGen 0.4 compatible - supports:
        - Custom callback (for AutoGen Console/UI integration)
        - Default getpass for CLI (hides input)

        Args:
            name: Secret name (e.g., "ANTHROPIC_API_KEY")
            description: Human-readable description

        Returns:
            Secret value or None if cancelled/empty
        """
        if self.input_callback:
            # Use custom callback (AutoGen 0.4 Console or custom UI)
            try:
                result = self.input_callback(name, description)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    return await result
                return result if result else None
            except Exception as e:
                self.logger.warning(
                    "input_callback_failed",
                    name=name,
                    error=str(e),
                )
                return None

        # Default: CLI prompt with getpass (hides input)
        print(f"\n[EnvironmentReport] Required secret missing: {name}")
        print(f"   Description: {description}")

        try:
            value = await asyncio.to_thread(
                getpass.getpass,
                f"   Enter value for {name}: "
            )
            return value if value.strip() else None
        except (KeyboardInterrupt, EOFError):
            self.logger.warning("secret_input_cancelled", name=name)
            return None

    async def _prompt_for_missing_secrets(self, report: dict) -> None:
        """
        Prompt user for each missing required secret.

        Iterates through missing required secrets and prompts user for each.
        Values are stored in os.environ for downstream use.

        Args:
            report: Environment report with "missing" list
        """
        for item in report["missing"]:
            if not item["required"]:
                continue

            name = item["name"]
            description = item["description"]

            self.logger.info("prompting_for_secret", name=name)

            value = await self._prompt_for_secret(name, description)

            if value:
                # Store in environment for downstream use
                os.environ[name] = value
                # SECURITY: Clear local reference immediately
                value = None  # noqa: F841
                self.logger.info("secret_collected", name=name)
            else:
                self.logger.warning("secret_skipped", name=name)

    def _load_requirements_from_file(self) -> None:
        """
        Load environment requirements from JSON file.

        Expected format:
        {
            "environment": [
                {
                    "name": "API_KEY",
                    "description": "API key for service",
                    "required": true,
                    "docker_secret": true
                }
            ]
        }
        """
        import json

        try:
            with open(self.requirements_path, 'r') as f:
                data = json.load(f)

            # Look for "environment" or "env" section
            env_section = data.get("environment", data.get("env", []))

            if not env_section:
                self.logger.debug(
                    "no_environment_section_in_json",
                    path=self.requirements_path,
                )
                return

            for item in env_section:
                if not isinstance(item, dict) or "name" not in item:
                    continue

                self.env_requirements.append(EnvRequirement(
                    name=item["name"],
                    description=item.get("description", ""),
                    required=item.get("required", True),
                    docker_secret=item.get("docker_secret", True),
                    source=item.get("source", "env"),
                    default=item.get("default"),
                ))

            self.logger.info(
                "loaded_env_requirements_from_json",
                path=self.requirements_path,
                count=len(env_section),
            )

        except FileNotFoundError:
            self.logger.debug(
                "requirements_file_not_found",
                path=self.requirements_path,
            )
        except json.JSONDecodeError as e:
            self.logger.warning(
                "requirements_json_parse_error",
                path=self.requirements_path,
                error=str(e),
            )
        except Exception as e:
            self.logger.warning(
                "env_requirements_load_failed",
                path=self.requirements_path,
                error=str(e),
            )

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return "Validating environment variables and API keys"

    # =========================================================================
    # Convenience methods for direct usage
    # =========================================================================

    def add_requirement(self, requirement: EnvRequirement) -> None:
        """Add a requirement dynamically."""
        self.env_requirements.append(requirement)

    def add_requirements(self, requirements: list[EnvRequirement]) -> None:
        """Add multiple requirements dynamically."""
        self.env_requirements.extend(requirements)

    def is_configured(self, name: str) -> bool:
        """Check if a specific env var is configured."""
        return self._configured.get(name, False)

    def get_missing_required(self) -> list[str]:
        """Get list of missing required env vars."""
        missing = []
        for req in self.env_requirements:
            if req.required and not os.environ.get(req.name):
                missing.append(req.name)
        return missing

    async def check_and_report(self) -> dict:
        """
        Manually trigger environment check and return report.

        This can be called directly without waiting for events.

        Returns:
            Environment report dict
        """
        return await self._generate_report()

    def reset(self) -> None:
        """Reset agent state to allow re-checking."""
        self._report_generated = False
        self._configured.clear()
        self._secrets_seeded.clear()


# =========================================================================
# Factory functions for common configurations
# =========================================================================

def create_coding_engine_env_agent(
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    **kwargs,
) -> EnvironmentReportAgent:
    """
    Create an EnvironmentReportAgent pre-configured for Coding Engine.

    Includes common requirements:
    - ANTHROPIC_API_KEY (required)
    - GITHUB_TOKEN (optional)
    - SUPERMEMORY_API_KEY (optional)
    - OLLAMA_BASE_URL (optional, has default)
    """
    return EnvironmentReportAgent(
        event_bus=event_bus,
        shared_state=shared_state,
        use_common_requirements=True,
        **kwargs,
    )


def create_minimal_env_agent(
    requirements: list[EnvRequirement],
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    **kwargs,
) -> EnvironmentReportAgent:
    """
    Create an EnvironmentReportAgent with only specified requirements.

    Does NOT include common requirements.
    """
    return EnvironmentReportAgent(
        event_bus=event_bus,
        shared_state=shared_state,
        env_requirements=requirements,
        use_common_requirements=False,
        **kwargs,
    )
