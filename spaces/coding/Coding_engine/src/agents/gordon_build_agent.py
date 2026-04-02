"""
Gordon Build Agent - Iterative Docker image building with AI assistance.

Combines:
- Docker AI (Gordon) for error analysis
- Ollama/Claude CLI for code generation
- DockerSwarmTool for build operations

Workflow:
1. Receive DOCKER_BUILD_REQUESTED event
2. Attempt build with docker_swarm_tool.build_image()
3. On failure: Ask Gordon for analysis
4. Generate fix using Ollama/Claude
5. Apply fix and retry
6. Loop until success or max iterations

Uses AutoGen 0.4 patterns for agent orchestration.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    docker_build_requested_event,
    docker_build_started_event,
    docker_build_succeeded_event,
    docker_build_failed_event,
    docker_build_fix_applied_event,
)
from ..mind.shared_state import SharedState
from ..tools.docker_swarm_tool import DockerSwarmTool

logger = structlog.get_logger(__name__)


class AIBackend(str, Enum):
    """AI backend options for code generation."""
    OLLAMA = "ollama"
    CLAUDE = "claude"


@dataclass
class BuildAttempt:
    """Record of a build attempt."""
    iteration: int
    success: bool
    error: Optional[str] = None
    gordon_analysis: Optional[str] = None
    fix_applied: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class GordonBuildAgent(AutonomousAgent):
    """
    Iterative Docker build agent combining Gordon + LLM.

    Uses:
    - DockerSwarmTool.ask_gordon() for Docker-specific insights
    - DockerSwarmTool.build_image() for building
    - Ollama/Claude for generating fixes

    Event Flow:
        DOCKER_BUILD_REQUESTED
            → GordonBuildAgent attempts build
            → On failure: Ask Gordon for analysis
            → Generate fix with Ollama/Claude
            → Apply fix and retry
            → Publishes DOCKER_BUILD_SUCCEEDED or DOCKER_BUILD_FAILED
    """

    def __init__(
        self,
        name: str = "GordonBuild",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # AI Configuration
        ai_backend: AIBackend = AIBackend.OLLAMA,
        ollama_model: str = "codellama:34b",
        ollama_base_url: str = "http://localhost:11434",
        # Build Configuration
        max_build_iterations: int = 10,
        dockerfile_path: str = "Dockerfile",
    ):
        """
        Initialize Gordon Build Agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Event polling interval
            memory_tool: Memory tool for patterns
            ai_backend: AI backend to use (ollama or claude)
            ollama_model: Ollama model name for code generation
            ollama_base_url: Ollama API base URL
            max_build_iterations: Max attempts before giving up
            dockerfile_path: Default Dockerfile path
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        self.ai_backend = ai_backend
        self.ollama_model = ollama_model
        self.ollama_base_url = ollama_base_url
        self.max_build_iterations = max_build_iterations
        self.dockerfile_path = dockerfile_path

        self._docker_tool = DockerSwarmTool()
        self._build_history: list[BuildAttempt] = []
        self._current_iteration = 0

        self.logger.info(
            "gordon_build_agent_initialized",
            ai_backend=ai_backend.value,
            max_iterations=max_build_iterations,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.DOCKER_BUILD_REQUESTED,
            EventType.DEPLOY_STARTED,  # Can trigger builds
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should act on these events."""
        for event in events:
            if event.type == EventType.DOCKER_BUILD_REQUESTED:
                return True
            # Only act on DEPLOY_STARTED if it has build_first=True
            if event.type == EventType.DEPLOY_STARTED:
                if event.data.get("build_first", False):
                    return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Execute iterative build loop."""
        for event in events:
            if event.type == EventType.DOCKER_BUILD_REQUESTED:
                return await self._handle_build_request(event)
            if event.type == EventType.DEPLOY_STARTED:
                if event.data.get("build_first", False):
                    # Convert deploy event to build request
                    return await self._handle_build_request(event)
        return None

    async def _handle_build_request(self, event: Event) -> Event:
        """
        Main build loop - iteratively build until success or max iterations.

        Args:
            event: The build request event

        Returns:
            DOCKER_BUILD_SUCCEEDED or DOCKER_BUILD_FAILED event
        """
        data = event.data or {}
        tag = data.get("tag", "app:latest")
        context = data.get("context", self.working_dir)
        dockerfile = data.get("dockerfile", self.dockerfile_path)

        self._current_iteration = 0
        self._build_history.clear()

        self.logger.info(
            "build_loop_started",
            tag=tag,
            context=context,
            dockerfile=dockerfile,
            max_iterations=self.max_build_iterations,
        )

        # Publish build started
        await self.event_bus.publish(docker_build_started_event(
            source=self.name,
            tag=tag,
            context=context,
            dockerfile=dockerfile,
        ))

        while self._current_iteration < self.max_build_iterations:
            self._current_iteration += 1
            self.logger.info(
                "build_attempt",
                iteration=self._current_iteration,
                tag=tag,
            )

            # Step 1: Attempt build
            result = await self._docker_tool.build_image(
                tag=tag,
                context=context,
                dockerfile=dockerfile,
            )

            if result.success:
                # SUCCESS!
                self._build_history.append(BuildAttempt(
                    iteration=self._current_iteration,
                    success=True,
                ))

                self.logger.info(
                    "build_succeeded",
                    tag=tag,
                    iterations=self._current_iteration,
                )

                # Update shared state
                if self.shared_state:
                    self.shared_state.set("last_docker_build_success", True)
                    self.shared_state.set("docker_build_iterations", self._current_iteration)

                return docker_build_succeeded_event(
                    source=self.name,
                    tag=tag,
                    iterations=self._current_iteration,
                    history=[self._attempt_to_dict(h) for h in self._build_history],
                )

            # Build failed - analyze and fix
            error_msg = result.message
            self.logger.warning(
                "build_failed",
                iteration=self._current_iteration,
                error=error_msg[:200],
            )

            # Step 2: Ask Gordon for analysis
            gordon_analysis = await self._ask_gordon_for_analysis(
                dockerfile=dockerfile,
                error=error_msg,
                context=context,
            )

            # Step 3: Generate fix using LLM
            fix = await self._generate_fix(
                dockerfile=dockerfile,
                error=error_msg,
                gordon_analysis=gordon_analysis,
                context=context,
            )

            # Step 4: Apply fix
            if fix:
                applied = await self._apply_fix(dockerfile, fix, context)

                if applied:
                    await self.event_bus.publish(docker_build_fix_applied_event(
                        source=self.name,
                        iteration=self._current_iteration,
                        fix_summary=fix[:200],
                    ))

            self._build_history.append(BuildAttempt(
                iteration=self._current_iteration,
                success=False,
                error=error_msg[:500] if error_msg else None,
                gordon_analysis=gordon_analysis[:500] if gordon_analysis else None,
                fix_applied=fix[:200] if fix else None,
            ))

        # Max iterations reached - build failed
        self.logger.error(
            "build_max_iterations_reached",
            tag=tag,
            iterations=self._current_iteration,
        )

        # Update shared state
        if self.shared_state:
            self.shared_state.set("last_docker_build_success", False)
            self.shared_state.set("docker_build_iterations", self._current_iteration)

        last_error = self._build_history[-1].error if self._build_history else "Unknown error"
        return docker_build_failed_event(
            source=self.name,
            tag=tag,
            error=f"Build failed after {self.max_build_iterations} iterations: {last_error}",
            iterations=self._current_iteration,
            history=[self._attempt_to_dict(h) for h in self._build_history],
        )

    async def _ask_gordon_for_analysis(
        self,
        dockerfile: str,
        error: str,
        context: str,
    ) -> Optional[str]:
        """
        Ask Gordon (Docker AI) to analyze the build failure.

        Args:
            dockerfile: Path to Dockerfile
            error: Build error message
            context: Build context directory

        Returns:
            Gordon's analysis or None if unavailable
        """
        # Read the Dockerfile
        dockerfile_path = os.path.join(context, dockerfile)
        dockerfile_content = ""
        try:
            with open(dockerfile_path, 'r') as f:
                dockerfile_content = f.read()
        except Exception as e:
            self.logger.warning("dockerfile_read_failed", error=str(e))

        question = f"""Analyze this Docker build failure and suggest specific fixes:

DOCKERFILE ({dockerfile}):
```dockerfile
{dockerfile_content[:2000]}
```

BUILD ERROR:
```
{error[:2000]}
```

What is causing this error and how should I fix it? Be specific about:
1. The exact line(s) causing the issue
2. What needs to be changed
3. Any missing dependencies or configurations"""

        self.logger.debug("asking_gordon", question_length=len(question))

        result = await self._docker_tool.ask_gordon(question)
        if result.success:
            response = result.data.get("response", "")
            self.logger.info(
                "gordon_analysis_received",
                response_length=len(response),
            )
            return response

        self.logger.warning(
            "gordon_unavailable",
            error=result.message,
        )
        return None

    async def _generate_fix(
        self,
        dockerfile: str,
        error: str,
        gordon_analysis: Optional[str],
        context: str,
    ) -> Optional[str]:
        """
        Use Ollama/Claude to generate fix for the Dockerfile.

        Args:
            dockerfile: Path to Dockerfile
            error: Build error message
            gordon_analysis: Gordon's analysis (if available)
            context: Build context directory

        Returns:
            Fixed Dockerfile content or None
        """
        # Read current Dockerfile
        dockerfile_path = os.path.join(context, dockerfile)
        try:
            with open(dockerfile_path, 'r') as f:
                current_content = f.read()
        except Exception as e:
            self.logger.error("dockerfile_read_failed", error=str(e))
            return None

        prompt = f"""Fix this Dockerfile based on the build error and analysis.

CURRENT DOCKERFILE:
```dockerfile
{current_content}
```

BUILD ERROR:
```
{error[:1500]}
```

DOCKER AI ANALYSIS:
{gordon_analysis or 'N/A'}

INSTRUCTIONS:
1. Fix the issue identified in the error
2. Keep all other functionality intact
3. Output ONLY the complete fixed Dockerfile content
4. Do not include any explanations or markdown formatting
5. Start directly with the FROM instruction"""

        self.logger.debug("generating_fix", ai_backend=self.ai_backend.value)

        if self.ai_backend == AIBackend.OLLAMA:
            return await self._call_ollama(prompt)
        else:
            return await self._call_claude(prompt)

    async def _call_ollama(self, prompt: str) -> Optional[str]:
        """
        Call Ollama API for code generation.

        Args:
            prompt: The prompt to send

        Returns:
            Generated response or None
        """
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ollama_base_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=120.0,
                )
                if response.status_code == 200:
                    result = response.json().get("response", "")
                    self.logger.info(
                        "ollama_response_received",
                        response_length=len(result),
                    )
                    return self._extract_dockerfile(result)
                else:
                    self.logger.error(
                        "ollama_request_failed",
                        status=response.status_code,
                    )
        except Exception as e:
            self.logger.error("ollama_call_failed", error=str(e))
        return None

    async def _call_claude(self, prompt: str) -> Optional[str]:
        """
        Call Claude CLI for code generation.

        Args:
            prompt: The prompt to send

        Returns:
            Generated response or None
        """
        try:
            from ..tools.claude_code_tool import ClaudeCodeTool
            tool = ClaudeCodeTool(working_dir=self.working_dir)
            result = await tool.generate_code(prompt)
            if result:
                self.logger.info(
                    "claude_response_received",
                    response_length=len(result),
                )
                return self._extract_dockerfile(result)
        except ImportError:
            self.logger.error("claude_code_tool_not_available")
        except Exception as e:
            self.logger.error("claude_call_failed", error=str(e))
        return None

    def _extract_dockerfile(self, response: str) -> str:
        """
        Extract Dockerfile content from LLM response.

        Handles responses that may include markdown code blocks.

        Args:
            response: Raw LLM response

        Returns:
            Cleaned Dockerfile content
        """
        # Remove markdown code blocks if present
        content = response.strip()

        # Handle ```dockerfile or ``` blocks
        if "```" in content:
            # Find content between ``` markers
            lines = content.split("\n")
            in_block = False
            dockerfile_lines = []

            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    dockerfile_lines.append(line)

            if dockerfile_lines:
                content = "\n".join(dockerfile_lines)

        # Ensure it starts with a valid Dockerfile instruction
        valid_starts = ["FROM", "ARG", "#"]
        lines = content.strip().split("\n")

        # Find first valid line
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if any(stripped.upper().startswith(s) for s in valid_starts):
                start_idx = i
                break

        return "\n".join(lines[start_idx:]).strip()

    async def _apply_fix(
        self,
        dockerfile: str,
        fix_content: str,
        context: str,
    ) -> bool:
        """
        Apply the generated fix to the Dockerfile.

        Args:
            dockerfile: Path to Dockerfile (relative to context)
            fix_content: New Dockerfile content
            context: Build context directory

        Returns:
            True if fix was applied successfully
        """
        dockerfile_path = os.path.join(context, dockerfile)

        # Validate the fix looks like a Dockerfile
        if not fix_content.strip():
            self.logger.warning("empty_fix_content")
            return False

        if not any(fix_content.upper().startswith(s) for s in ["FROM", "ARG", "#"]):
            self.logger.warning(
                "invalid_dockerfile_fix",
                first_line=fix_content.split("\n")[0][:50],
            )
            return False

        try:
            # Backup original
            backup_path = f"{dockerfile_path}.bak"
            if os.path.exists(dockerfile_path):
                with open(dockerfile_path, 'r') as f:
                    original = f.read()
                with open(backup_path, 'w') as f:
                    f.write(original)

            # Write fix
            with open(dockerfile_path, 'w') as f:
                f.write(fix_content)

            self.logger.info(
                "fix_applied",
                dockerfile=dockerfile,
                backup=backup_path,
            )
            return True

        except Exception as e:
            self.logger.error("fix_apply_failed", error=str(e))
            return False

    def _attempt_to_dict(self, attempt: BuildAttempt) -> dict:
        """Convert BuildAttempt to dict for serialization."""
        return {
            "iteration": attempt.iteration,
            "success": attempt.success,
            "error": attempt.error,
            "gordon_analysis": attempt.gordon_analysis,
            "fix_applied": attempt.fix_applied,
            "timestamp": attempt.timestamp.isoformat(),
        }

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Building Docker image (iteration {self._current_iteration}/{self.max_build_iterations})"

    # =========================================================================
    # Convenience methods for direct usage
    # =========================================================================

    async def build_image(
        self,
        tag: str,
        context: str = ".",
        dockerfile: str = "Dockerfile",
    ) -> bool:
        """
        Convenience method to trigger a build directly.

        Args:
            tag: Image tag
            context: Build context directory
            dockerfile: Dockerfile path

        Returns:
            True if build succeeded
        """
        event = docker_build_requested_event(
            source="direct_call",
            tag=tag,
            context=context,
            dockerfile=dockerfile,
        )

        result = await self._handle_build_request(event)
        return result.success if result else False

    def get_build_history(self) -> list[dict]:
        """Get build history as list of dicts."""
        return [self._attempt_to_dict(h) for h in self._build_history]

    def reset(self) -> None:
        """Reset agent state for new build."""
        self._build_history.clear()
        self._current_iteration = 0


# =========================================================================
# Factory functions
# =========================================================================

def create_gordon_build_agent(
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    working_dir: str = ".",
    use_ollama: bool = True,
    ollama_model: str = "codellama:34b",
    **kwargs,
) -> GordonBuildAgent:
    """
    Create a GordonBuildAgent with common defaults.

    Args:
        event_bus: Event bus for communication
        shared_state: Shared state for metrics
        working_dir: Project directory
        use_ollama: Use Ollama (True) or Claude (False)
        ollama_model: Ollama model to use
        **kwargs: Additional arguments for GordonBuildAgent

    Returns:
        Configured GordonBuildAgent
    """
    return GordonBuildAgent(
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
        ai_backend=AIBackend.OLLAMA if use_ollama else AIBackend.CLAUDE,
        ollama_model=ollama_model,
        **kwargs,
    )
