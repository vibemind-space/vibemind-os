"""
Deployment Team Agent - Coordinates deployment verification pipeline.

This agent:
1. Triggers on BUILD_SUCCEEDED to verify deployment
2. Runs Docker sandbox tests for isolated verification
3. Optionally triggers cloud tests (GitHub Actions)
4. Reports deployment success/failure
5. NEW: Continuous testing mode - runs 30-second cycles from the start
"""

import asyncio
from datetime import datetime
from typing import Any, Optional
import structlog

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType, EventBus,
    sandbox_test_event,
    sandbox_test_started_event,
    sandbox_test_passed_event,
    sandbox_test_failed_event,
    screen_stream_ready_event,
    persistent_deploy_started_event,
    persistent_deploy_ready_event,
    persistent_deploy_failed_event,
    deploy_succeeded_event,
)
from ..mind.shared_state import SharedState
from ..tools.sandbox_tool import SandboxTool, SandboxResult, ContinuousSandboxCycle

logger = structlog.get_logger(__name__)


class DeploymentTeamAgent(AutonomousAgent):
    """
    Deployment Team Agent - Verifies apps work in isolated environments.

    Workflow:
    1. Subscribe to BUILD_SUCCEEDED
    2. Run Docker sandbox test (install → build → start → health check)
    3. Report results and update shared state
    4. Optionally trigger cloud tests

    Continuous Mode (NEW):
    When enable_continuous=True, starts a background loop that:
    - Creates container once at start
    - Every 30 seconds: starts app → health check → kills app
    - Reports status via SANDBOX_CYCLE_COMPLETE events
    - Continues until convergence or stopped

    Triggers on:
    - BUILD_SUCCEEDED - Primary trigger after successful build
    - CODE_FIXED - Re-run after code fixes
    """

    def __init__(
        self,
        name: str = "DeploymentTeam",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # Configuration
        enable_sandbox: bool = True,
        enable_cloud_tests: bool = False,
        enable_vnc: bool = False,
        vnc_port: int = 6080,
        min_deploy_interval: int = 120,
        max_retries: int = 3,
        sandbox_timeout: int = 300,
        # Continuous testing mode
        enable_continuous: bool = False,
        cycle_interval: int = 30,
        start_continuous_immediately: bool = True,
        # Persistent deployment mode (VNC persists after convergence)
        enable_persistent_final_deploy: bool = False,
        persistent_vnc_port: int = 6080,
        inject_collected_secrets: bool = True,
    ):
        """
        Initialize deployment team agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project directory
            poll_interval: Seconds between event checks
            memory_tool: Optional memory tool for patterns
            enable_sandbox: Enable Docker sandbox testing
            enable_cloud_tests: Enable GitHub Actions testing
            enable_vnc: Enable VNC streaming for Electron apps in sandbox
            vnc_port: noVNC web port (default 6080, access at http://localhost:6080/vnc.html)
            min_deploy_interval: Minimum seconds between deploy attempts
            max_retries: Maximum retry attempts for failed deployments
            sandbox_timeout: Timeout for sandbox tests in seconds
            enable_continuous: Enable continuous 30-second test cycle mode
            cycle_interval: Seconds between test cycles (default 30)
            start_continuous_immediately: Start continuous loop on agent start (default True)
            enable_persistent_final_deploy: Deploy to persistent VNC container on convergence
            persistent_vnc_port: Port for persistent VNC (default 6080)
            inject_collected_secrets: Inject secrets from os.environ into container
        """
        # IMPORTANT: Set attributes BEFORE super().__init__() because the base class
        # calls self.subscribed_events which depends on these attributes
        self.enable_persistent_final_deploy = enable_persistent_final_deploy

        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )

        self.enable_sandbox = enable_sandbox
        self.enable_cloud_tests = enable_cloud_tests
        self.enable_vnc = enable_vnc
        self.vnc_port = vnc_port
        self.min_deploy_interval = min_deploy_interval
        self.max_retries = max_retries
        self.sandbox_timeout = sandbox_timeout

        # Continuous testing mode
        self.enable_continuous = enable_continuous
        self.cycle_interval = cycle_interval
        self.start_continuous_immediately = start_continuous_immediately

        # Persistent deployment mode (already set above, but document here)
        self.persistent_vnc_port = persistent_vnc_port
        self.inject_collected_secrets = inject_collected_secrets
        self._persistent_deployed = False
        self._persistent_container_id: Optional[str] = None

        # State tracking
        self._last_deploy_time: Optional[datetime] = None
        self._deploy_count = 0
        self._retry_count = 0
        self._last_result: Optional[SandboxResult] = None
        
        # Continuous mode state
        self._continuous_task: Optional[asyncio.Task] = None
        self._continuous_running = False
        self._cycle_count = 0
        self._last_cycle: Optional[ContinuousSandboxCycle] = None
        self._sandbox_tool: Optional[SandboxTool] = None

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        events = [
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_FIXED,
        ]
        # Add CONVERGENCE_ACHIEVED for persistent deployment
        if self.enable_persistent_final_deploy:
            events.append(EventType.CONVERGENCE_ACHIEVED)
        return events

    async def start(self) -> None:
        """
        Start the agent.
        
        If continuous mode is enabled and start_continuous_immediately is True,
        this will start the continuous testing loop immediately.
        """
        await super().start()
        
        if self.enable_continuous and self.start_continuous_immediately:
            self.logger.info(
                "starting_continuous_sandbox_loop",
                cycle_interval=self.cycle_interval,
                vnc_enabled=self.enable_vnc,
            )
            await self.start_continuous_loop()
    
    async def stop(self) -> None:
        """Stop the agent and any running continuous loop."""
        if self._continuous_running:
            await self.stop_continuous_loop()
        await super().stop()

    async def start_continuous_loop(self) -> None:
        """
        Start the continuous sandbox testing loop.
        
        This creates a background task that:
        1. Sets up the Docker container once
        2. Every cycle_interval seconds: starts app → health check → kills app
        3. Publishes events for each cycle result
        """
        if self._continuous_running:
            self.logger.warning("continuous_loop_already_running")
            return
        
        self._continuous_running = True
        self._continuous_task = asyncio.create_task(self._continuous_loop())
        
        self.logger.info(
            "continuous_loop_started",
            cycle_interval=self.cycle_interval,
            working_dir=self.working_dir,
        )
        
        # Publish event
        await self.event_bus.publish(sandbox_test_started_event(
            source=self.name,
            working_dir=self.working_dir,
            mode="continuous",
            cycle_interval=self.cycle_interval,
            vnc_enabled=self.enable_vnc,
            vnc_port=self.vnc_port if self.enable_vnc else None,
        ))

    async def stop_continuous_loop(self) -> None:
        """Stop the continuous sandbox testing loop."""
        if not self._continuous_running:
            return
        
        self._continuous_running = False
        
        if self._sandbox_tool:
            self._sandbox_tool.stop_continuous_tests()
        
        if self._continuous_task:
            self._continuous_task.cancel()
            try:
                await self._continuous_task
            except asyncio.CancelledError:
                pass
            self._continuous_task = None
        
        self.logger.info(
            "continuous_loop_stopped",
            total_cycles=self._cycle_count,
        )

    async def _continuous_loop(self) -> None:
        """
        Internal continuous testing loop.
        
        Runs until stopped or convergence criteria met.
        """
        try:
            # Create sandbox tool for continuous testing
            self._sandbox_tool = SandboxTool(
                project_dir=self.working_dir,
                timeout=self.sandbox_timeout,
                cleanup=not self.enable_vnc,  # Keep container for VNC
                enable_vnc=self.enable_vnc,
                vnc_port=self.vnc_port,
                cycle_interval=self.cycle_interval,
            )
            
            # Run continuous tests
            async for cycle in self._sandbox_tool.run_continuous_tests():
                if not self._continuous_running:
                    break
                
                self._cycle_count = cycle.cycle_number
                self._last_cycle = cycle
                
                # Update shared state
                await self._update_cycle_metrics(cycle)
                
                # Publish cycle result event
                await self._publish_cycle_result(cycle)
                
                # Check if we should stop (e.g., on convergence)
                if await self._should_stop_continuous(cycle):
                    self.logger.info(
                        "continuous_loop_convergence_reached",
                        cycle=cycle.cycle_number,
                    )
                    break
                    
        except asyncio.CancelledError:
            self.logger.info("continuous_loop_cancelled")
        except Exception as e:
            self.logger.error("continuous_loop_error", error=str(e))
            await self.event_bus.publish(sandbox_test_event(
                source=self.name,
                passed=False,
                error_message=str(e),
            ))
        finally:
            self._continuous_running = False

    async def _update_cycle_metrics(self, cycle: ContinuousSandboxCycle) -> None:
        """Update shared state with cycle metrics."""
        await self.shared_state.update_sandbox(
            tested=True,
            success=cycle.success,
            errors=0 if cycle.success else 1,
            duration_ms=cycle.duration_ms,
        )

    async def _publish_cycle_result(self, cycle: ContinuousSandboxCycle) -> None:
        """Publish event for cycle result."""
        # Use typed factory function for sandbox test events
        await self.event_bus.publish(sandbox_test_event(
            source=self.name,
            passed=cycle.success,
            container_id=getattr(self, '_container_id', None),
            app_url=f"http://localhost:{self._sandbox_tool.app_port}" if cycle.app_started else None,
            vnc_url=f"http://localhost:{self.vnc_port}/vnc.html" if self.enable_vnc else None,
            error_message=cycle.error_message,
        ))
        
        # If VNC is enabled and first successful start, publish stream URL
        if self.enable_vnc and cycle.app_started and cycle.cycle_number == 1:
            await self.event_bus.publish(screen_stream_ready_event(
                source=self.name,
                vnc_url=f"http://localhost:{self.vnc_port}/vnc.html",
                vnc_port=self.vnc_port,
                mode="continuous",
            ))

    async def _should_stop_continuous(self, cycle: ContinuousSandboxCycle) -> bool:
        """
        Check if continuous loop should stop.
        
        Override this to implement custom convergence criteria.
        Default: never stop automatically (run until external stop).
        """
        # Could check shared_state.convergence_met or other criteria
        # For now, run indefinitely until stopped
        return False

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if deployment verification should run.
        
        In continuous mode, always return False since the loop handles everything.

        Conditions (non-continuous mode):
        1. Recent BUILD_SUCCEEDED event
        2. Cooldown period elapsed
        3. Haven't exceeded max retries for current iteration
        """
        # In continuous mode, the loop handles everything
        if self.enable_continuous and self._continuous_running:
            return False
        
        # Check cooldown
        if self._last_deploy_time:
            elapsed = (datetime.now() - self._last_deploy_time).total_seconds()
            if elapsed < self.min_deploy_interval:
                return False

        # Check for relevant events
        for event in events:
            if event.type == EventType.BUILD_SUCCEEDED:
                self.logger.info("build_succeeded_triggering_deployment")
                return True

            # Re-run after code fixes if previous deploy failed
            if event.type == EventType.CODE_FIXED:
                if self._last_result and not self._last_result.success:
                    if self._retry_count < self.max_retries:
                        self.logger.info("code_fixed_retrying_deployment")
                        return True

            # Handle persistent deployment on convergence
            if event.type == EventType.CONVERGENCE_ACHIEVED:
                if self.enable_persistent_final_deploy and not self._persistent_deployed:
                    self.logger.info("convergence_achieved_triggering_persistent_deploy")
                    return True

        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Execute deployment verification pipeline.

        Steps:
        1. Check for CONVERGENCE_ACHIEVED -> persistent deploy
        2. Run Docker sandbox tests
        3. Update shared state metrics
        4. Store successful patterns in memory
        5. Return result event
        """
        # Check if this is a CONVERGENCE_ACHIEVED event for persistent deployment
        for event in events:
            if event.type == EventType.CONVERGENCE_ACHIEVED:
                if self.enable_persistent_final_deploy and not self._persistent_deployed:
                    return await self._deploy_persistent()

        self._last_deploy_time = datetime.now()
        self._deploy_count += 1

        self.logger.info(
            "deployment_verification_starting",
            deploy_number=self._deploy_count,
            retry_count=self._retry_count,
        )

        # Publish start event
        await self.event_bus.publish(sandbox_test_started_event(
            source=self.name,
            working_dir=self.working_dir,
            mode="single",
            deploy_number=self._deploy_count,
        ))

        result: Optional[SandboxResult] = None

        try:
            # Run sandbox tests if enabled
            if self.enable_sandbox:
                result = await self._run_sandbox_tests()
                self._last_result = result

                # Update shared state
                await self._update_metrics(result)

                # Store pattern if successful
                if result.success and self.memory_tool:
                    await self._store_success_pattern(result)

                # Reset retry count on success, increment on failure
                if result.success:
                    self._retry_count = 0
                else:
                    self._retry_count += 1

                # Return result event
                return self._create_result_event(result)

            else:
                # Sandbox disabled, just report success
                return sandbox_test_passed_event(
                    source=self.name,
                    message="Sandbox testing disabled",
                )

        except Exception as e:
            self.logger.error("deployment_verification_error", error=str(e))
            self._retry_count += 1

            return sandbox_test_failed_event(
                source=self.name,
                error_message=str(e),
                deploy_number=self._deploy_count,
            )

    async def _run_sandbox_tests(self) -> SandboxResult:
        """Run Docker sandbox tests."""
        self.logger.info(
            "running_sandbox_tests",
            vnc_enabled=self.enable_vnc,
            vnc_port=self.vnc_port if self.enable_vnc else None,
        )

        tool = SandboxTool(
            project_dir=self.working_dir,
            timeout=self.sandbox_timeout,
            cleanup=not self.enable_vnc,  # Keep container alive for VNC viewing
            enable_vnc=self.enable_vnc,
            vnc_port=self.vnc_port,
        )

        result = await tool.run_sandbox_tests()

        # Publish VNC stream event if VNC is enabled and container started
        if self.enable_vnc and result.vnc_enabled and result.vnc_url:
            await self.event_bus.publish(screen_stream_ready_event(
                source=self.name,
                vnc_url=result.vnc_url,
                vnc_port=result.vnc_port,
                container_id=result.container_id,
                project_type=result.project_type.value,
                mode="single",
            ))

        return result

    async def _update_metrics(self, result: SandboxResult) -> None:
        """Update shared state with sandbox metrics."""
        await self.shared_state.update_sandbox(
            tested=True,
            success=result.success,
            errors=0 if result.success else 1,
            duration_ms=result.total_duration_ms,
        )

    def _create_result_event(self, result: SandboxResult) -> Event:
        """Create result event from sandbox result."""
        if result.success:
            return sandbox_test_passed_event(
                source=self.name,
                data=result.to_dict(),
            )
        else:
            return sandbox_test_failed_event(
                source=self.name,
                error_message=result.error_message,
                data=result.to_dict(),
            )

    async def _store_success_pattern(self, result: SandboxResult) -> None:
        """Store successful deployment pattern in memory."""
        if not self.memory_tool or not getattr(self.memory_tool, 'enabled', False):
            return

        try:
            content = f"""## Deployment Verification Success

**Project Type:** {result.project_type.value}
**Duration:** {result.total_duration_ms}ms
**App Started:** {result.app_started}
**App Responsive:** {result.app_responsive}

### Steps Completed
{chr(10).join(f"- {s.name}: {'PASS' if s.success else 'FAIL'} ({s.duration_ms}ms)" for s in result.steps)}

### Key Information
- Container ID: {result.container_id}
- Total Steps: {len(result.steps)}
- All Steps Passed: {all(s.success for s in result.steps)}
"""

            if hasattr(self.memory_tool, 'store'):
                await self.memory_tool.store(
                    content=content,
                    description="Successful deployment verification",
                    category="deployment",
                    tags=["sandbox", "deployment", result.project_type.value],
                )

        except Exception as e:
            self.logger.warning("failed_to_store_pattern", error=str(e))

    async def _deploy_persistent(self) -> Event:
        """
        Deploy to a persistent VNC-enabled container after convergence.

        This creates a container that:
        - Runs the app continuously
        - Has VNC enabled for viewing
        - Stays running until manually stopped
        - Injects collected secrets from environment

        Returns:
            PERSISTENT_DEPLOY_READY or PERSISTENT_DEPLOY_FAILED event
        """
        import os

        self.logger.info(
            "persistent_deployment_starting",
            vnc_port=self.persistent_vnc_port,
            inject_secrets=self.inject_collected_secrets,
        )

        # Publish start event
        await self.event_bus.publish(persistent_deploy_started_event(
            source=self.name,
            vnc_port=self.persistent_vnc_port,
            working_dir=self.working_dir,
        ))

        try:
            # Collect secrets from environment (set by EnvironmentReportAgent)
            secrets = {}
            if self.inject_collected_secrets:
                secret_keys = [
                    "ANTHROPIC_API_KEY",
                    "OPENAI_API_KEY",
                    "DATABASE_URL",
                    "API_KEY",
                    "SECRET_KEY",
                    "GITHUB_TOKEN",
                ]
                for key in secret_keys:
                    value = os.environ.get(key)
                    if value:
                        secrets[key] = value
                        self.logger.debug("secret_collected_for_deploy", name=key)

            # Create persistent sandbox tool
            tool = SandboxTool(
                project_dir=self.working_dir,
                timeout=0,  # No timeout for persistent
                cleanup=False,  # Never cleanup
                enable_vnc=True,
                vnc_port=self.persistent_vnc_port,
            )

            # Run in persistent mode (keeps container running)
            result = await tool.run_sandbox_tests(
                env_vars=secrets,
                persistent=True,  # New flag for persistent mode
            )

            self._persistent_deployed = True
            self._persistent_container_id = result.container_id

            vnc_url = f"http://localhost:{self.persistent_vnc_port}/vnc.html"

            self.logger.info(
                "persistent_deployment_ready",
                vnc_url=vnc_url,
                container_id=result.container_id,
            )

            # Publish ready event
            return persistent_deploy_ready_event(
                source=self.name,
                vnc_url=vnc_url,
                vnc_port=self.persistent_vnc_port,
                container_id=result.container_id,
                secrets_injected=list(secrets.keys()),
            )

        except Exception as e:
            self.logger.error("persistent_deployment_failed", error=str(e))
            return persistent_deploy_failed_event(
                source=self.name,
                error_message=str(e),
                vnc_port=self.persistent_vnc_port,
            )

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Running deployment verification #{self._deploy_count}"

    # =========================================================================
    # Phase 9: LLM-Enhanced Environment Variable Detection
    # =========================================================================

    async def detect_env_vars_with_llm(
        self,
        code_files: dict[str, str],
    ) -> list[dict]:
        """
        Use LLM to analyze code and find all environment variable references.

        This method understands different patterns for accessing env vars:
        - process.env.* (Node.js)
        - import.meta.env.* (Vite)
        - os.environ.get() (Python)
        - Config file references

        Args:
            code_files: Dict of {path: content} for code files to analyze

        Returns:
            List of env var dicts with name, required, type, example, and usage
        """
        import json
        import re

        try:
            from ..tools.claude_code_tool import ClaudeCodeTool

            # Format code files for LLM (limit size)
            files_text = ""
            for path, content in list(code_files.items())[:15]:
                files_text += f"\n### {path}\n```\n{content[:1500]}\n```\n"

            prompt = f"""Analyze this codebase and find ALL environment variables used:

## CODE FILES:
{files_text}

## DETECTION PATTERNS:

**JavaScript/TypeScript:**
- `process.env.VARIABLE_NAME`
- `process.env['VARIABLE_NAME']`
- `import.meta.env.VARIABLE_NAME` (Vite)
- `Deno.env.get('VARIABLE_NAME')` (Deno)

**Python:**
- `os.environ.get('VARIABLE_NAME')`
- `os.getenv('VARIABLE_NAME')`
- `os.environ['VARIABLE_NAME']`

**Config Files:**
- `.env` file references
- `config.get('variable')` patterns
- YAML/JSON config references

## FOR EACH VARIABLE:

1. **name**: The env var name (e.g., DATABASE_URL)
2. **required**: Is it required for the app to run? (true/false)
3. **default**: Default value if any (null if none)
4. **type**: string | number | boolean | url | secret
5. **example**: A realistic example value for .env.example
6. **usage**: How it's used (one line)
7. **files**: Which files reference it

## RESPONSE FORMAT:

```json
{{
  "env_vars": [
    {{
      "name": "DATABASE_URL",
      "required": true,
      "default": null,
      "type": "url",
      "example": "postgresql://user:pass@localhost:5432/mydb",
      "usage": "Prisma database connection string",
      "files": ["src/db/client.ts", "prisma/schema.prisma"]
    }},
    {{
      "name": "PORT",
      "required": false,
      "default": "3000",
      "type": "number",
      "example": "3000",
      "usage": "HTTP server port",
      "files": ["src/server.ts"]
    }}
  ],
  "env_example": "# Example .env file\\nDATABASE_URL=postgresql://...\\nPORT=3000"
}}
```

## IMPORTANT:
- Include ALL env vars, not just obvious ones
- Mark secrets (API keys, passwords) as type="secret"
- For secrets, use placeholder examples like "your-api-key-here"
- Check for vars used in Docker, CI, and config files too
"""

            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context="Environment variable detection for deployment",
                agent_type="env_detector",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                env_vars = analysis.get("env_vars", [])

                self.logger.info(
                    "env_vars_detected",
                    count=len(env_vars),
                    required=sum(1 for v in env_vars if v.get("required")),
                    secrets=sum(1 for v in env_vars if v.get("type") == "secret"),
                )

                return env_vars

        except Exception as e:
            self.logger.warning("llm_env_detection_failed", error=str(e))

        # Fallback: regex-based detection
        return self._fallback_env_detection(code_files)

    def _fallback_env_detection(
        self,
        code_files: dict[str, str],
    ) -> list[dict]:
        """
        Basic env var detection without LLM using regex.
        """
        import re

        env_vars = {}  # name -> info dict

        patterns = [
            # Node.js patterns
            (r'process\.env\.([A-Z_][A-Z0-9_]*)', 'js'),
            (r'process\.env\[[\'"]([A-Z_][A-Z0-9_]*)[\'\"]\]', 'js'),
            # Vite patterns
            (r'import\.meta\.env\.([A-Z_][A-Z0-9_]*)', 'vite'),
            (r'import\.meta\.env\[[\'"]([A-Z_][A-Z0-9_]*)[\'\"]\]', 'vite'),
            # Python patterns
            (r'os\.environ\.get\([\'"]([A-Z_][A-Z0-9_]*)[\'"]', 'py'),
            (r'os\.getenv\([\'"]([A-Z_][A-Z0-9_]*)[\'"]', 'py'),
            (r'os\.environ\[[\'"]([A-Z_][A-Z0-9_]*)[\'\"]\]', 'py'),
        ]

        for file_path, content in code_files.items():
            for pattern, source_type in patterns:
                for match in re.finditer(pattern, content):
                    var_name = match.group(1)

                    if var_name not in env_vars:
                        env_vars[var_name] = {
                            "name": var_name,
                            "required": True,  # Assume required by default
                            "default": None,
                            "type": self._guess_env_type(var_name),
                            "example": self._guess_env_example(var_name),
                            "usage": f"Found in {file_path}",
                            "files": [file_path],
                        }
                    else:
                        if file_path not in env_vars[var_name]["files"]:
                            env_vars[var_name]["files"].append(file_path)

        return list(env_vars.values())

    def _guess_env_type(self, var_name: str) -> str:
        """Guess the type of an env var from its name."""
        name_lower = var_name.lower()

        if any(kw in name_lower for kw in ['key', 'secret', 'password', 'token', 'auth']):
            return 'secret'
        if any(kw in name_lower for kw in ['url', 'uri', 'endpoint']):
            return 'url'
        if any(kw in name_lower for kw in ['port', 'timeout', 'limit', 'size', 'count']):
            return 'number'
        if any(kw in name_lower for kw in ['enable', 'disable', 'debug', 'verbose']):
            return 'boolean'

        return 'string'

    def _guess_env_example(self, var_name: str) -> str:
        """Generate an example value for an env var."""
        name_lower = var_name.lower()

        # Common patterns with example values
        examples = {
            'database_url': 'postgresql://user:password@localhost:5432/dbname',
            'mongodb_url': 'mongodb://localhost:27017/dbname',
            'redis_url': 'redis://localhost:6379',
            'api_key': 'your-api-key-here',
            'secret_key': 'your-secret-key-here',
            'jwt_secret': 'your-jwt-secret-here',
            'port': '3000',
            'host': 'localhost',
            'node_env': 'development',
            'debug': 'true',
        }

        for pattern, example in examples.items():
            if pattern in name_lower:
                return example

        # Generic examples by type
        if self._guess_env_type(var_name) == 'secret':
            return 'your-secret-here'
        if self._guess_env_type(var_name) == 'url':
            return 'https://api.example.com'
        if self._guess_env_type(var_name) == 'number':
            return '3000'
        if self._guess_env_type(var_name) == 'boolean':
            return 'true'

        return 'value'

    async def generate_env_files(
        self,
        code_files: dict[str, str],
        output_dir: str,
    ) -> dict:
        """
        Generate .env and .env.example files from detected env vars.

        Args:
            code_files: Dict of {path: content} for code files
            output_dir: Directory to write env files to

        Returns:
            Dict with generated file paths and content
        """
        from pathlib import Path

        # Detect env vars
        env_vars = await self.detect_env_vars_with_llm(code_files)

        # Build .env.example content
        example_lines = ["# Environment Variables"]
        example_lines.append("# Copy this file to .env and fill in the values")
        example_lines.append("")

        # Group by type
        secrets = [v for v in env_vars if v.get("type") == "secret"]
        required = [v for v in env_vars if v.get("required") and v.get("type") != "secret"]
        optional = [v for v in env_vars if not v.get("required") and v.get("type") != "secret"]

        if secrets:
            example_lines.append("# Secrets (required)")
            for var in secrets:
                example_lines.append(f"{var['name']}={var.get('example', 'your-secret-here')}")
            example_lines.append("")

        if required:
            example_lines.append("# Required")
            for var in required:
                example_lines.append(f"{var['name']}={var.get('example', '')}")
            example_lines.append("")

        if optional:
            example_lines.append("# Optional")
            for var in optional:
                default = var.get("default", "")
                example_lines.append(f"# {var['name']}={default or var.get('example', '')}")
            example_lines.append("")

        example_content = "\n".join(example_lines)

        # Write files
        output_path = Path(output_dir)
        example_path = output_path / ".env.example"

        example_path.write_text(example_content)

        self.logger.info(
            "env_files_generated",
            env_vars_count=len(env_vars),
            example_path=str(example_path),
        )

        return {
            "env_vars": env_vars,
            "env_example_path": str(example_path),
            "env_example_content": example_content,
        }

    def get_continuous_status(self) -> dict:
        """Get current status of continuous testing."""
        return {
            "enabled": self.enable_continuous,
            "running": self._continuous_running,
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle.to_dict() if self._last_cycle else None,
            "cycle_interval": self.cycle_interval,
            "vnc_enabled": self.enable_vnc,
            "vnc_url": f"http://localhost:{self.vnc_port}/vnc.html" if self.enable_vnc else None,
        }


# Convenience function for running deployment verification
async def verify_deployment(project_dir: str, enable_sandbox: bool = True) -> SandboxResult:
    """
    Run deployment verification on a project.

    Args:
        project_dir: Path to project directory
        enable_sandbox: Whether to run Docker sandbox tests

    Returns:
        SandboxResult with verification results
    """
    tool = SandboxTool(project_dir)
    return await tool.run_sandbox_tests()
