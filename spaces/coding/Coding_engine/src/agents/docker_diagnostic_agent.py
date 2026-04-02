"""
DockerDiagnosticAgent - LLM-Powered Infrastructure Error Analysis.

Uses Claude to:
1. Analyze Docker daemon and container errors
2. Diagnose port conflicts, network issues, and permission problems
3. Understand docker-compose configuration issues
4. Suggest specific fixes with actionable commands
5. Assess risk and potential side effects

This agent provides intelligent diagnosis that goes beyond pattern matching,
using LLM understanding of Docker concepts and infrastructure.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType
from src.tools.claude_code_tool import ClaudeCodeTool


logger = structlog.get_logger(__name__)


@dataclass
class DockerDiagnosis:
    """Result of LLM Docker error analysis."""
    root_cause: str
    error_type: str = "unknown"  # port_conflict, name_conflict, network, permission, etc.
    immediate_fix: str = ""  # Command to run
    prevention: str = ""  # How to avoid in future
    risk_level: str = "low"  # low, medium, high
    affected_containers: list[str] = field(default_factory=list)
    affected_ports: list[int] = field(default_factory=list)
    compose_issue: Optional[str] = None


class DockerDiagnosticAgent(AutonomousAgent):
    """
    LLM-powered autonomous agent for diagnosing Docker and infrastructure errors.

    Uses Claude to:
    1. Parse and understand Docker daemon error messages
    2. Analyze docker-compose configurations
    3. Identify root cause of container/network issues
    4. Suggest specific fixes with executable commands
    5. Warn about potential side effects

    Publishes DOCUMENT_CREATED event with diagnosis for DeploymentTeamAgent.
    """

    COOLDOWN_SECONDS = 10.0  # Allow rapid diagnosis

    # Docker error patterns that trigger diagnosis
    DOCKER_ERROR_PATTERNS = [
        (r"port is already allocated", "port_conflict"),
        (r"address already in use", "port_conflict"),
        (r"bind: address already in use", "port_conflict"),
        (r"container name .* already in use", "name_conflict"),
        (r"Conflict\. The container name", "name_conflict"),
        (r"no space left on device", "disk_space"),
        (r"network .* not found", "network_error"),
        (r"could not find network", "network_error"),
        (r"permission denied", "permission_error"),
        (r"cannot connect to Docker daemon", "daemon_error"),
        (r"Is the docker daemon running", "daemon_error"),
        (r"error during connect", "daemon_error"),
        (r"image .* not found", "image_error"),
        (r"pull access denied", "image_error"),
        (r"unauthorized", "auth_error"),
        (r"no matching manifest", "platform_error"),
        (r"OCI runtime create failed", "runtime_error"),
        (r"Error response from daemon", "daemon_error"),
        (r"failed to create endpoint", "network_error"),
    ]

    def __init__(
        self,
        name: str = "DockerDiagnosticAgent",
        event_bus=None,
        shared_state=None,
        working_dir: str = ".",
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.claude_tool = ClaudeCodeTool(working_dir=working_dir)
        self._diagnosed_errors: set[str] = set()  # Track already diagnosed errors
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "docker_diagnostic_agent_initialized",
            working_dir=working_dir,
            subscribed_events=[e.value for e in self.subscribed_events],
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.DEPLOY_FAILED,
            EventType.SANDBOX_TEST_FAILED,
            EventType.BUILD_FAILED,  # Sometimes Docker errors appear in build
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Determine if any event contains a Docker error worth diagnosing."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Get error content from various possible fields
            error_content = ""
            if event.data:
                for field in ["error", "build_output", "deploy_output", "stderr", "message"]:
                    if field in event.data:
                        error_content += str(event.data.get(field, "")) + "\n"

            if not error_content:
                continue

            # Check for Docker error patterns
            for pattern, error_type in self.DOCKER_ERROR_PATTERNS:
                if re.search(pattern, error_content, re.IGNORECASE):
                    # Create hash to avoid re-diagnosing same error
                    error_hash = hash(error_content[:500])
                    if error_hash in self._diagnosed_errors:
                        self.logger.debug("docker_error_already_diagnosed", hash=error_hash)
                        continue
                    self._diagnosed_errors.add(error_hash)
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Diagnose Docker error using LLM."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self.logger.info(
            "diagnosing_docker_error",
            event_type=event.type.value,
            project_id=event.data.get("project_id") if event.data else None,
        )

        try:
            # Extract error information
            error_output = ""
            if event.data:
                for field in ["error", "build_output", "deploy_output", "stderr", "message"]:
                    if field in event.data:
                        error_output += str(event.data.get(field, "")) + "\n"

            # Load docker-compose if available
            compose_content = await self._load_compose_files()

            # Perform LLM diagnosis
            diagnosis = await self._analyze_docker_error(error_output, compose_content)

            if diagnosis:
                self.logger.info(
                    "docker_diagnosis_complete",
                    root_cause=diagnosis.root_cause,
                    error_type=diagnosis.error_type,
                    risk_level=diagnosis.risk_level,
                )

                # Publish diagnosis
                await self.event_bus.publish(Event(
                    type=EventType.DOCUMENT_CREATED,
                    source=self.name,
                    data={
                        "document_type": "docker_diagnosis",
                        "project_id": event.data.get("project_id"),
                        "diagnosis": {
                            "root_cause": diagnosis.root_cause,
                            "error_type": diagnosis.error_type,
                            "immediate_fix": diagnosis.immediate_fix,
                            "prevention": diagnosis.prevention,
                            "risk_level": diagnosis.risk_level,
                            "affected_containers": diagnosis.affected_containers,
                            "affected_ports": diagnosis.affected_ports,
                            "compose_issue": diagnosis.compose_issue,
                        },
                        "original_error": error_output[:1000],
                    }
                ))

                # Update shared state with diagnosis
                if self.shared_state:
                    self.shared_state.set(
                        f"docker_diagnosis_{event.data.get('project_id', 'default')}",
                        diagnosis.__dict__
                    )

        except Exception as e:
            self.logger.error("docker_diagnosis_failed", error=str(e))

    async def _load_compose_files(self) -> str:
        """Load docker-compose configuration files."""
        compose_content = ""
        working_path = Path(self.working_dir)

        # Common docker-compose file names
        compose_files = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "docker-compose.dev.yml",
            "docker-compose.override.yml",
            "compose.yml",
            "compose.yaml",
        ]

        # Also check infra/docker directory
        search_dirs = [working_path, working_path / "infra" / "docker"]

        for search_dir in search_dirs:
            for compose_file in compose_files:
                compose_path = search_dir / compose_file
                if compose_path.exists():
                    try:
                        content = compose_path.read_text()
                        rel_path = compose_path.relative_to(working_path) if compose_path.is_relative_to(working_path) else compose_path
                        compose_content += f"\n=== {rel_path} ===\n{content}\n"
                    except Exception:
                        pass

        # Also try to get Dockerfile if present
        dockerfiles = list(working_path.glob("**/Dockerfile*"))[:3]  # Limit to 3
        for dockerfile in dockerfiles:
            try:
                content = dockerfile.read_text()
                if len(content) < 2000:  # Only include small Dockerfiles
                    rel_path = dockerfile.relative_to(working_path)
                    compose_content += f"\n=== {rel_path} ===\n{content}\n"
            except Exception:
                pass

        return compose_content

    async def _analyze_docker_error(
        self, error_output: str, compose_content: str
    ) -> Optional[DockerDiagnosis]:
        """Use LLM to analyze Docker error and suggest fix."""

        # Detect error type for context
        error_type = "unknown"
        for pattern, etype in self.DOCKER_ERROR_PATTERNS:
            if re.search(pattern, error_output, re.IGNORECASE):
                error_type = etype
                break

        prompt = f"""Diagnose this Docker/container error and provide a specific fix.

## ERROR OUTPUT:
```
{error_output[:3000]}
```

## DETECTED ERROR TYPE: {error_type}

## DOCKER CONFIGURATION:
```
{compose_content[:3000] if compose_content else "No docker-compose files found"}
```

## ANALYSIS REQUIRED:

1. **Root Cause**: What is the exact cause of this error?
2. **Error Type**: Classify as: port_conflict, name_conflict, disk_space, network_error, permission_error, daemon_error, image_error, runtime_error, or unknown
3. **Immediate Fix**: What COMMAND should be run to fix this? (e.g., `docker rm -f container_name`, `docker network prune`)
4. **Prevention**: How to avoid this in the future?
5. **Risk Level**: low/medium/high
6. **Affected Containers**: Which container names are affected?
7. **Affected Ports**: Which ports have conflicts?
8. **Compose Issue**: Any issue in docker-compose config?

## COMMON FIXES BY ERROR TYPE:
- **port_conflict**: `docker ps --filter publish=PORT -q | xargs docker rm -f`
- **name_conflict**: `docker rm -f CONTAINER_NAME`
- **disk_space**: `docker system prune -af`
- **network_error**: `docker network prune` or `docker network create NETWORK`
- **daemon_error**: Check Docker Desktop is running
- **permission_error**: Add user to docker group or use sudo

Respond in this exact JSON format:
```json
{{
    "root_cause": "Clear explanation of what went wrong",
    "error_type": "port_conflict|name_conflict|disk_space|network_error|permission_error|daemon_error|image_error|runtime_error|unknown",
    "immediate_fix": "docker command to run",
    "prevention": "How to prevent this in future",
    "risk_level": "low|medium|high",
    "affected_containers": ["container1", "container2"],
    "affected_ports": [3000, 5432],
    "compose_issue": "Issue in compose file or null"
}}
```
"""

        try:
            result = await self.claude_tool.execute(
                prompt=prompt,
                skill="docker-sandbox",
                skill_tier="standard",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                diagnosis_data = json.loads(json_match.group(1))
                return DockerDiagnosis(
                    root_cause=diagnosis_data.get("root_cause", "Unknown"),
                    error_type=diagnosis_data.get("error_type", error_type),
                    immediate_fix=diagnosis_data.get("immediate_fix", ""),
                    prevention=diagnosis_data.get("prevention", ""),
                    risk_level=diagnosis_data.get("risk_level", "medium"),
                    affected_containers=diagnosis_data.get("affected_containers", []),
                    affected_ports=diagnosis_data.get("affected_ports", []),
                    compose_issue=diagnosis_data.get("compose_issue"),
                )
            else:
                # Fallback: try to extract useful info
                self.logger.warning("docker_json_parse_failed_using_fallback")
                return DockerDiagnosis(
                    root_cause=f"LLM analysis: {result[:500]}",
                    error_type=error_type,
                    immediate_fix="docker system prune -f",
                    prevention="Review Docker logs and configuration",
                    risk_level="medium",
                )

        except Exception as e:
            self.logger.error("llm_docker_analysis_failed", error=str(e))
            return None

    async def _execute_fix(self, diagnosis: DockerDiagnosis, auto_fix: bool = False) -> bool:
        """Optionally execute the suggested fix command."""
        if not auto_fix or not diagnosis.immediate_fix:
            return False

        # Only execute low-risk fixes automatically
        if diagnosis.risk_level != "low":
            self.logger.warning(
                "skipping_risky_auto_fix",
                risk_level=diagnosis.risk_level,
                fix=diagnosis.immediate_fix,
            )
            return False

        # TODO: Execute the fix command via sandbox or subprocess
        # For now, just log it
        self.logger.info(
            "suggested_fix_available",
            fix=diagnosis.immediate_fix,
            risk_level=diagnosis.risk_level,
        )
        return False
