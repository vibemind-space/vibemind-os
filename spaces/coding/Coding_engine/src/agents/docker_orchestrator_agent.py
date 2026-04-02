"""
Docker Orchestrator Agent - Intelligent Docker management using local or cloud LLM.

This agent uses Claude CLI or Ollama (local) to:
- Analyze Docker configurations and issues
- Generate Dockerfiles and compose files
- Debug container problems
- Plan and execute deployments
- Consult Gordon (Docker AI) for best practices

Supports two AI backends:
- "ollama": Local Ollama model (default, no API costs)
- "claude": Claude CLI (requires API key)
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    code_fixed_event,
    system_error_event,
    swarm_initialized_event,
    secret_created_event,
    code_generated_event,
)
from ..mind.shared_state import SharedState
from ..tools.docker_swarm_tool import DockerSwarmTool, SwarmResult, SwarmStatus


class AIBackend(str, Enum):
    """AI backend options for the orchestrator."""
    OLLAMA = "ollama"
    CLAUDE = "claude"


# Lazy imports to avoid startup errors if one backend is not installed
def _get_claude_tool():
    """Lazy import ClaudeCodeTool."""
    try:
        from ..tools.claude_code_tool import ClaudeCodeTool
        return ClaudeCodeTool
    except ImportError:
        return None


def _get_ollama_tool():
    """Lazy import OllamaTool."""
    try:
        from ..tools.ollama_tool import OllamaTool
        return OllamaTool
    except ImportError:
        return None

logger = structlog.get_logger(__name__)


@dataclass
class DockerTask:
    """A Docker-related task for the orchestrator."""
    task_type: str  # "deploy", "debug", "optimize", "create", "scale"
    description: str
    context: dict
    priority: int = 1
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class DockerOrchestratorAgent(AutonomousAgent):
    """
    Docker Orchestrator Agent - Uses local Ollama or Claude CLI for intelligent Docker management.

    This agent combines:
    - Local LLM (Ollama) or Claude CLI for AI-powered analysis
    - DockerSwarmTool for Docker operations
    - Gordon (Docker AI) for Docker-specific advice

    AI Backend Options:
    - AIBackend.OLLAMA (default): Local Ollama model (free, fast, offline)
    - AIBackend.CLAUDE: Claude CLI (requires API key)

    Capabilities:
    1. Analyze and fix Docker issues
    2. Generate Dockerfiles and compose files
    3. Plan deployments with proper secret handling
    4. Debug container failures
    5. Optimize Docker configurations
    6. Scale services intelligently

    Triggers on:
    - DEPLOY_STARTED - Assist with deployments
    - BUILD_FAILED - Debug Docker build issues
    - SANDBOX_TEST_FAILED - Debug container runtime issues
    - SERVICE_DEPLOY_FAILED - Fix service deployment problems
    """

    def __init__(
        self,
        name: str = "DockerOrchestrator",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # AI Backend Configuration
        ai_backend: Union[str, AIBackend] = AIBackend.OLLAMA,  # Default to local Ollama
        ollama_model: str = "codellama:34b",  # Model for Ollama
        ollama_base_url: str = "http://localhost:11434",  # Ollama API URL
        llm_timeout: int = 300,  # Timeout for LLM calls (longer for local)
        # Docker Configuration
        use_gordon: bool = True,
        auto_fix: bool = True,
        max_retries: int = 3,
    ):
        """
        Initialize Docker Orchestrator Agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Event polling interval
            memory_tool: Memory tool for patterns
            ai_backend: AI backend to use ("ollama" or "claude")
            ollama_model: Ollama model name (e.g., "codellama:34b", "deepseek-coder:33b")
            ollama_base_url: Ollama API base URL
            llm_timeout: Timeout for LLM calls in seconds
            use_gordon: Consult Docker AI (Gordon) for advice
            auto_fix: Automatically attempt fixes
            max_retries: Max retry attempts for operations
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        # AI Backend configuration
        self.ai_backend = AIBackend(ai_backend) if isinstance(ai_backend, str) else ai_backend
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.llm_timeout = llm_timeout

        # Docker configuration
        self.use_gordon = use_gordon
        self.auto_fix = auto_fix
        self.max_retries = max_retries

        # Tools
        self._docker_tool = DockerSwarmTool()
        self._llm_tool: Optional[Any] = None  # Lazy initialized
        self._pending_tasks: list[DockerTask] = []
        self._retry_counts: dict[str, int] = {}

        self.logger.info(
            "docker_orchestrator_initialized",
            ai_backend=self.ai_backend.value,
            model=self.ollama_model if self.ai_backend == AIBackend.OLLAMA else "claude",
        )

    def _get_llm_tool(self) -> Any:
        """
        Lazy initialization of LLM tool based on backend.

        Returns either OllamaTool or ClaudeCodeTool.
        """
        if self._llm_tool is None:
            if self.ai_backend == AIBackend.OLLAMA:
                OllamaTool = _get_ollama_tool()
                if OllamaTool is None:
                    raise ImportError(
                        "OllamaTool not available. Install with: pip install aiohttp"
                    )
                self._llm_tool = OllamaTool(
                    model=self.ollama_model,
                    base_url=self.ollama_base_url,
                    working_dir=self.working_dir,
                    timeout=self.llm_timeout,
                )
                self.logger.info(
                    "ollama_tool_initialized",
                    model=self.ollama_model,
                    base_url=self.ollama_base_url,
                )
            else:  # CLAUDE
                ClaudeCodeTool = _get_claude_tool()
                if ClaudeCodeTool is None:
                    raise ImportError(
                        "ClaudeCodeTool not available. Check src/tools/claude_code_tool.py"
                    )
                self._llm_tool = ClaudeCodeTool(
                    working_dir=self.working_dir,
                    timeout=self.llm_timeout,
                )
                self.logger.info("claude_tool_initialized")

        return self._llm_tool

    async def _execute_llm(
        self,
        prompt: str,
        context: Optional[str] = None,
        agent_type: str = "general",
    ) -> Any:
        """
        Execute LLM call with the configured backend.

        Args:
            prompt: The prompt to send
            context: Additional context
            agent_type: Agent type for specialized prompts

        Returns:
            Result from either Ollama or Claude tool
        """
        llm = self._get_llm_tool()
        return await llm.execute(
            prompt=prompt,
            context=context,
            agent_type=agent_type,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.DEPLOY_STARTED,
            EventType.BUILD_FAILED,
            EventType.SANDBOX_TEST_FAILED,
            EventType.SERVICE_DEPLOY_FAILED,
            EventType.SWARM_INIT_FAILED,
            EventType.SECRET_CREATE_FAILED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should act on events."""
        for event in events:
            if event.type in self.subscribed_events:
                # Check retry count
                error_key = f"{event.type.value}:{event.error_message or 'unknown'}"
                if self._retry_counts.get(error_key, 0) < self.max_retries:
                    return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Process Docker-related events using Claude CLI."""
        for event in events:
            error_key = f"{event.type.value}:{event.error_message or 'unknown'}"
            self._retry_counts[error_key] = self._retry_counts.get(error_key, 0) + 1

            if event.type == EventType.BUILD_FAILED:
                return await self._handle_build_failure(event)

            if event.type == EventType.SANDBOX_TEST_FAILED:
                return await self._handle_sandbox_failure(event)

            if event.type == EventType.SERVICE_DEPLOY_FAILED:
                return await self._handle_service_failure(event)

            if event.type == EventType.SWARM_INIT_FAILED:
                return await self._handle_swarm_failure(event)

            if event.type == EventType.SECRET_CREATE_FAILED:
                return await self._handle_secret_failure(event)

            if event.type == EventType.DEPLOY_STARTED:
                return await self._assist_deployment(event)

        return None

    async def _handle_build_failure(self, event: Event) -> Optional[Event]:
        """Use Claude CLI to analyze and fix Docker build failures."""
        self.logger.info("analyzing_build_failure", error=event.error_message)

        # Get Gordon's advice if enabled
        gordon_advice = ""
        if self.use_gordon:
            gordon_result = await self._docker_tool.ask_gordon(
                f"Docker build failed with error: {event.error_message}. How do I fix this?"
            )
            if gordon_result.success:
                gordon_advice = gordon_result.data.get("response", "")

        # Use Claude CLI to analyze and fix
        prompt = f"""Analyze and fix this Docker build failure:

Error: {event.error_message}

Build context: {json.dumps(event.data, indent=2)}

{f"Docker AI (Gordon) suggests: {gordon_advice}" if gordon_advice else ""}

Tasks:
1. Identify the root cause of the build failure
2. Fix the Dockerfile or build configuration
3. Ensure the fix follows Docker best practices

Focus on:
- Missing dependencies
- Incorrect base images
- Permission issues
- Multi-stage build problems
- Cache optimization
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Docker build failure analysis and fix",
            agent_type="docker_fixer",
        )

        if result.success and (result.files or getattr(result, 'response', '')):
            self.logger.info("build_fix_applied", files=result.files)
            return code_fixed_event(
                source=self.name,
                success=True,
                fix_type="docker_build",
                files_modified=result.files,
                extra_data={"used_gordon": bool(gordon_advice)},
            )

        return system_error_event(
            source=self.name,
            error_message=f"Failed to fix build: {result.error}",
        )

    async def _handle_sandbox_failure(self, event: Event) -> Optional[Event]:
        """Debug container runtime failures using Claude CLI."""
        self.logger.info("analyzing_sandbox_failure", data=event.data)

        # Get container logs if available
        container_id = event.data.get("container_id")
        logs = ""
        if container_id:
            logs = await self._docker_tool.get_container_logs(container_id, tail=200)

        # Get system info
        system_info = await self._docker_tool.system_info()

        prompt = f"""Debug this Docker container/sandbox failure:

Error: {event.error_message}

Event data:
{json.dumps(event.data, indent=2)}

Container logs:
{logs[:3000] if logs else "No logs available"}

System info:
- Docker version: {system_info.get('ServerVersion', 'unknown')}
- OS: {system_info.get('OperatingSystem', 'unknown')}
- Swarm active: {system_info.get('Swarm', {}).get('LocalNodeState', 'unknown')}

Tasks:
1. Identify why the container/app failed to start or respond
2. Check for:
   - Missing environment variables
   - Port conflicts
   - Resource limits
   - Network issues
   - Missing files/volumes
3. Fix the application or Docker configuration
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Container runtime debugging",
            agent_type="docker_debugger",
        )

        if result.success:
            return code_fixed_event(
                source=self.name,
                success=True,
                fix_type="sandbox_runtime",
                files_modified=result.files or [],
            )

        return None

    async def _handle_service_failure(self, event: Event) -> Optional[Event]:
        """Fix Docker service deployment failures."""
        self.logger.info("analyzing_service_failure", error=event.error_message)

        service_name = event.data.get("name", "unknown")

        # List current services for context
        services = await self._docker_tool.list_services()
        secrets = await self._docker_tool.list_secrets()
        networks = await self._docker_tool.list_networks()

        # Get Gordon's advice
        gordon_advice = ""
        if self.use_gordon:
            gordon_result = await self._docker_tool.ask_gordon(
                f"Docker service '{service_name}' deployment failed: {event.error_message}. How to fix?"
            )
            if gordon_result.success:
                gordon_advice = gordon_result.data.get("response", "")

        prompt = f"""Fix this Docker service deployment failure:

Service: {service_name}
Error: {event.error_message}

Event data:
{json.dumps(event.data, indent=2)}

Current environment:
- Services: {[s.get('Name') for s in services]}
- Secrets: {secrets}
- Networks: {[n.get('Name') for n in networks]}

{f"Gordon suggests: {gordon_advice}" if gordon_advice else ""}

Tasks:
1. Identify why service deployment failed
2. Check for:
   - Missing secrets (must be created before service)
   - Missing networks (overlay networks need swarm mode)
   - Image availability
   - Resource constraints
   - Port conflicts
3. Create any missing resources
4. Fix the deployment configuration
"""

        result = await self._execute_llm(
            prompt=prompt,
            context=f"Service deployment fix: {service_name}",
            agent_type="docker_fixer",
        )

        if result.success:
            return code_fixed_event(
                source=self.name,
                success=True,
                fix_type="service_deployment",
                extra_data={"service": service_name},
            )

        return None

    async def _handle_swarm_failure(self, event: Event) -> Optional[Event]:
        """Handle Docker Swarm initialization failures."""
        self.logger.info("handling_swarm_failure", error=event.error_message)

        # Check current swarm status
        status = await self._docker_tool.check_swarm_status()

        prompt = f"""Fix Docker Swarm initialization failure:

Error: {event.error_message}
Current status: {status.value}

Common issues:
1. Already part of a swarm - need to leave first
2. Network/firewall blocking ports (2377, 7946, 4789)
3. IP address conflicts
4. Docker daemon not running

Provide commands or code to fix this issue.
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Swarm initialization fix",
            agent_type="docker_fixer",
        )

        # If swarm is already active, report success
        if status == SwarmStatus.ACTIVE:
            return swarm_initialized_event(source=self.name)

        if result.success:
            return code_fixed_event(
                source=self.name,
                success=True,
                fix_type="swarm_init",
            )

        return None

    async def _handle_secret_failure(self, event: Event) -> Optional[Event]:
        """Handle Docker secret creation failures."""
        secret_name = event.data.get("name", "unknown")
        self.logger.info("handling_secret_failure", secret=secret_name, error=event.error_message)

        # Check if secret already exists
        secrets = await self._docker_tool.list_secrets()
        if secret_name in secrets:
            return secret_created_event(
                source=self.name,
                name=secret_name,
                already_existed=True,
            )

        # Check swarm status
        status = await self._docker_tool.check_swarm_status()
        if status != SwarmStatus.ACTIVE:
            # Try to initialize swarm
            init_result = await self._docker_tool.init_swarm()
            if init_result.success:
                return swarm_initialized_event(source=self.name)

        return system_error_event(
            source=self.name,
            error_message=f"Cannot create secret '{secret_name}': {event.error_message}",
        )

    async def _assist_deployment(self, event: Event) -> Optional[Event]:
        """Assist with deployment planning using Claude CLI."""
        self.logger.info("assisting_deployment", data=event.data)

        project_type = event.data.get("project_type", "unknown")

        # Get Gordon's deployment advice
        gordon_advice = ""
        if self.use_gordon:
            gordon_result = await self._docker_tool.ask_gordon(
                f"Best practices for deploying a {project_type} application with Docker Swarm and secrets?"
            )
            if gordon_result.success:
                gordon_advice = gordon_result.data.get("response", "")

        prompt = f"""Plan Docker deployment for this project:

Project type: {project_type}
Working directory: {self.working_dir}

Event data:
{json.dumps(event.data, indent=2)}

{f"Gordon recommends: {gordon_advice}" if gordon_advice else ""}

Create a deployment plan that includes:
1. Required Docker resources (networks, volumes, secrets)
2. Service configuration with health checks
3. Proper secret handling (never hardcode!)
4. Resource limits and scaling policies
5. Logging configuration
6. Update strategy (rolling updates)

Generate:
- docker-compose.yml for local development
- docker-compose.prod.yml for production with secrets
- Any required Dockerfiles
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Deployment planning",
            agent_type="docker_architect",
        )

        if result.success and result.files:
            return code_generated_event(
                source=self.name,
                task="deployment_plan",
                files_created=result.files,
            )

        return None

    # =========================================================================
    # Convenience methods for direct usage
    # =========================================================================

    async def generate_dockerfile(
        self,
        project_type: str,
        requirements: Optional[list[str]] = None,
    ) -> Optional[str]:
        """
        Generate a Dockerfile using Claude CLI.

        Args:
            project_type: Type of project (python, node, react, etc.)
            requirements: List of requirements/features

        Returns:
            Generated Dockerfile content or None
        """
        prompt = f"""Generate an optimized Dockerfile for a {project_type} project.

Requirements:
{json.dumps(requirements or [], indent=2)}

Best practices to follow:
- Multi-stage build for smaller images
- Non-root user for security
- Proper layer caching
- Health checks
- .dockerignore recommendations
"""

        # Get Gordon's advice
        if self.use_gordon:
            gordon = await self._docker_tool.ask_gordon(
                f"Best Dockerfile practices for {project_type}?"
            )
            if gordon.success:
                prompt += f"\n\nGordon suggests:\n{gordon.data.get('response', '')}"

        result = await self._execute_llm(
            prompt=prompt,
            context="Dockerfile generation",
            agent_type="docker_generator",
        )

        if result.success and result.files:
            # Read the generated Dockerfile
            for f in result.files:
                if "Dockerfile" in f:
                    try:
                        with open(f, "r") as file:
                            return file.read()
                    except Exception:
                        pass

        return None

    async def generate_compose_file(
        self,
        services: list[dict],
        include_secrets: bool = True,
    ) -> Optional[str]:
        """
        Generate a docker-compose.yml using Claude CLI.

        Args:
            services: List of service definitions
            include_secrets: Include secret management

        Returns:
            Generated compose file content or None
        """
        prompt = f"""Generate a docker-compose.yml file for these services:

Services:
{json.dumps(services, indent=2)}

Include:
- Proper networking (overlay for swarm)
- Health checks for all services
- Resource limits
- Logging configuration
- {"Secret management with Docker secrets" if include_secrets else "Environment variables for configuration"}
- Volume mounts for persistent data
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Compose file generation",
            agent_type="docker_generator",
        )

        if result.success and result.files:
            for f in result.files:
                if "compose" in f.lower() and f.endswith((".yml", ".yaml")):
                    try:
                        with open(f, "r") as file:
                            return file.read()
                    except Exception:
                        pass

        return None

    async def debug_container(
        self,
        container_id: str,
        issue_description: str,
    ) -> dict:
        """
        Debug a container issue using Claude CLI and Docker tools.

        Args:
            container_id: Container ID or name
            issue_description: Description of the issue

        Returns:
            Debug report with findings and recommendations
        """
        # Gather diagnostics
        logs = await self._docker_tool.get_container_logs(container_id, tail=500)
        debug_info = await self._docker_tool.debug_container(container_id)

        # Get Gordon's advice
        gordon_advice = ""
        if self.use_gordon:
            gordon = await self._docker_tool.ask_gordon(
                f"Container issue: {issue_description}. Error logs: {logs[:1000]}"
            )
            if gordon.success:
                gordon_advice = gordon.data.get("response", "")

        prompt = f"""Debug this container issue:

Issue: {issue_description}

Container: {container_id}

Logs (last 500 lines):
{logs[:5000]}

Debug info:
{debug_info.message}

{f"Gordon says: {gordon_advice}" if gordon_advice else ""}

Provide:
1. Root cause analysis
2. Specific fixes to apply
3. Commands to run
4. Prevention recommendations
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Container debugging",
            agent_type="docker_debugger",
        )

        return {
            "container": container_id,
            "issue": issue_description,
            "analysis": result.response if result.success else "Analysis failed",
            "files_modified": result.files or [],
            "gordon_advice": gordon_advice,
        }

    async def optimize_images(self) -> dict:
        """
        Analyze and suggest optimizations for Docker images.

        Returns:
            Optimization report
        """
        images = await self._docker_tool.list_images()

        # Get disk usage
        df = await self._docker_tool.system_df()

        prompt = f"""Analyze these Docker images and suggest optimizations:

Images:
{json.dumps(images[:20], indent=2)}

Disk usage:
{json.dumps(df, indent=2)}

Analyze:
1. Which images are oversized?
2. Which images have too many layers?
3. Which images could benefit from multi-stage builds?
4. Are there dangling images to clean up?
5. Are there unused images?

Provide specific recommendations with commands.
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Image optimization analysis",
            agent_type="docker_optimizer",
        )

        return {
            "images_analyzed": len(images),
            "recommendations": result.response if result.success else "Analysis failed",
            "disk_usage": df,
        }

    async def security_scan(self, image: str) -> dict:
        """
        Run security scan on a Docker image.

        Args:
            image: Image to scan

        Returns:
            Security report
        """
        # Use Docker Scout
        quickview = await self._docker_tool.scout_quickview(image)
        cves = await self._docker_tool.scout_cves(image)

        # Analyze with Claude
        prompt = f"""Analyze this Docker image security scan:

Image: {image}

Scout Quickview:
{quickview.data.get('report', 'No report')}

CVE Details:
{cves.data.get('report', 'No CVEs found')[:5000]}

Provide:
1. Summary of vulnerabilities
2. Critical issues to fix immediately
3. Recommended base image alternatives
4. Specific fixes for each vulnerability type
"""

        result = await self._execute_llm(
            prompt=prompt,
            context="Security analysis",
            agent_type="security_analyzer",
        )

        return {
            "image": image,
            "scout_report": quickview.data.get("report"),
            "cve_count": len(cves.data.get("report", "").split("\n")),
            "analysis": result.response if result.success else "Analysis failed",
        }

    def _get_action_description(self) -> str:
        """Get description of current action."""
        backend = "Ollama" if self.ai_backend == AIBackend.OLLAMA else "Claude"
        return f"Orchestrating Docker operations with {backend}"

    async def check_llm_available(self) -> bool:
        """
        Check if the configured LLM backend is available.

        Returns:
            True if backend is ready
        """
        if self.ai_backend == AIBackend.OLLAMA:
            OllamaTool = _get_ollama_tool()
            if OllamaTool:
                tool = OllamaTool(
                    model=self.ollama_model,
                    base_url=self.ollama_base_url,
                )
                return await tool.check_available()
            return False
        else:
            # Claude CLI assumed available if tool loads
            return _get_claude_tool() is not None

    async def pull_ollama_model(self) -> bool:
        """
        Pull the Ollama model if using Ollama backend.

        Returns:
            True if model is now available
        """
        if self.ai_backend != AIBackend.OLLAMA:
            self.logger.warning("pull_only_for_ollama")
            return False

        OllamaTool = _get_ollama_tool()
        if OllamaTool:
            tool = OllamaTool(
                model=self.ollama_model,
                base_url=self.ollama_base_url,
            )
            return await tool.pull_model()
        return False

    def reset_retry_counts(self) -> None:
        """Reset retry counts for all errors."""
        self._retry_counts.clear()
