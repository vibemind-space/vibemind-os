"""
ValidationTeamAgent - Autonomer Agent für Test-Generierung und Debug Engine.

Triggert auf:
- GENERATION_COMPLETE: Startet Test-Generierung nach Code-Generation
- BUILD_SUCCEEDED: Führt Tests aus nach Build
- CODE_FIXED: Re-runs Tests nach Fixes

Architektur:
- Nutzt ValidationTeam für den Workflow
- Publiziert Events für andere Agents
- Integriert ShellStream für User-Feedback
- Führt NoMock-Validierung vor Build aus (CRITICAL!)

No-Mock Policy:
- Prüft generierten Code auf Mock-Patterns
- Blockiert Build wenn Mocks gefunden werden
- Publiziert MOCK_DETECTED Event für GeneratorAgent
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import structlog

from .autonomous_base import AutonomousAgent
from .autogen_team_mixin import AutogenTeamMixin
from ..mind.event_bus import (
    Event, EventType, EventBus,
    mock_detected_event,
    mock_validation_passed_event,
    tests_running_event,
    tests_passed_event,
    tests_failed_event,
)
from ..mind.shared_state import SharedState
from ..teams.validation_team import (
    ValidationTeam,
    ValidationConfig,
    ValidationResult,
    TestReport,
    ShellStream,
    ShellOutput,
)
from ..validators.no_mock_validator import NoMockValidator

logger = structlog.get_logger(__name__)


class ValidationTeamAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous Agent für Validation mit Test-Generierung und Debug Engine.
    
    Workflow:
    1. Wartet auf GENERATION_COMPLETE oder BUILD_SUCCEEDED
    2. Startet ValidationTeam
    3. Publiziert Test-Events (TESTS_PASSED, TESTS_FAILED)
    4. Triggert Debug Engine bei Failures
    5. Streamt Shell Output für User-Feedback
    
    Events Published:
    - TEST_GENERATION_STARTED
    - TEST_GENERATION_COMPLETE  
    - TESTS_RUNNING
    - TESTS_PASSED
    - TESTS_FAILED
    - DEBUG_STARTED
    - DEBUG_COMPLETE
    - VALIDATION_REPORT_READY
    """
    
    def __init__(
        self,
        name: str = "ValidationTeam",
        event_bus: Optional[EventBus] = None,
        shared_state: Optional[SharedState] = None,
        working_dir: str = ".",
        poll_interval: float = 5.0,
        memory_tool: Optional[Any] = None,
        # Validation Config
        requirements_path: Optional[str] = None,
        test_framework: str = "vitest",
        use_docker: bool = True,
        docker_network: str = "validation-net",
        frontend_port: int = 3100,
        backend_port: int = 8100,
        max_debug_iterations: int = 3,
        timeout_seconds: int = 300,
        # Shell Streaming
        enable_shell_stream: bool = True,
        on_shell_output: Optional[callable] = None,
        # Control
        min_validation_interval: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
            memory_tool=memory_tool,
        )
        
        # Config
        self.requirements_path = requirements_path
        self.test_framework = test_framework
        self.use_docker = use_docker
        self.docker_network = docker_network
        self.frontend_port = frontend_port
        self.backend_port = backend_port
        self.max_debug_iterations = max_debug_iterations
        self.timeout_seconds = timeout_seconds
        self.enable_shell_stream = enable_shell_stream
        self.on_shell_output = on_shell_output
        self.min_validation_interval = min_validation_interval
        self.max_retries = max_retries
        
        # State
        self._last_validation_time: Optional[datetime] = None
        self._validation_count = 0
        self._retry_count = 0
        self._last_result: Optional[ValidationResult] = None
        self._requirements: list[dict] = []
        self._shell_stream: Optional[ShellStream] = None

        # ValidationTeam wird lazy initialisiert
        self._validation_team: Optional[ValidationTeam] = None

        # NoMock Validator - runs before every build
        self._no_mock_validator: Optional[NoMockValidator] = None
        self._enable_no_mock_check: bool = True  # Can be disabled for test files
    
    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent subscribes to."""
        return [
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_FIXED,
            # Phase 11: Completeness-triggered test generation
            EventType.REQUIREMENT_TEST_MISSING,
        ]
    
    async def start(self) -> None:
        """Start the agent."""
        await super().start()
        
        # Load requirements if path provided
        if self.requirements_path:
            self._load_requirements()
        
        # Initialize shell stream
        if self.enable_shell_stream:
            self._shell_stream = ShellStream(on_output=self._handle_shell_output)
            self._shell_stream.start()
        
        self.logger.info(
            "validation_team_agent_started",
            test_framework=self.test_framework,
            use_docker=self.use_docker,
        )
    
    async def stop(self) -> None:
        """Stop the agent."""
        if self._shell_stream:
            self._shell_stream.stop()
        
        await super().stop()
    
    def _load_requirements(self) -> None:
        """Load requirements from JSON file."""
        try:
            req_path = Path(self.requirements_path)
            if req_path.exists():
                with open(req_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Handle different formats
                if isinstance(data, dict) and "requirements" in data:
                    self._requirements = data["requirements"]
                elif isinstance(data, list):
                    self._requirements = data
                
                self.logger.info(
                    "requirements_loaded",
                    count=len(self._requirements),
                )
        except Exception as e:
            self.logger.error("requirements_load_failed", error=str(e))
    
    def _handle_shell_output(self, output: ShellOutput) -> None:
        """Handle shell output - forward to callback."""
        if self.on_shell_output:
            self.on_shell_output(output)
    
    async def should_act(self, events: list[Event]) -> bool:
        """Decide if validation should run."""
        # Check cooldown (but not for REQUIREMENT_TEST_MISSING - always act on those)
        has_test_missing_event = any(
            e.type == EventType.REQUIREMENT_TEST_MISSING for e in events
        )

        if not has_test_missing_event and self._last_validation_time:
            elapsed = (datetime.now() - self._last_validation_time).total_seconds()
            if elapsed < self.min_validation_interval:
                return False

        # Check for trigger events
        for event in events:
            if event.type == EventType.GENERATION_COMPLETE:
                self.logger.info("triggered_by_generation_complete")
                return True

            if event.type == EventType.BUILD_SUCCEEDED:
                self.logger.info("triggered_by_build_succeeded")
                return True

            # Re-run after code fixes if previous validation failed
            if event.type == EventType.CODE_FIXED:
                if self._last_result and not self._last_result.success:
                    if self._retry_count < self.max_retries:
                        self.logger.info("triggered_by_code_fixed")
                        return True

            # Phase 11: Completeness-triggered test generation
            if event.type == EventType.REQUIREMENT_TEST_MISSING:
                self.logger.info(
                    "triggered_by_requirement_test_missing",
                    requirement_id=event.data.get("requirement_id") if event.data else None,
                )
                return True

        return False
    
    async def _run_no_mock_validation(self) -> tuple[bool, Optional[Event]]:
        """
        Run NoMock validation before build.

        Returns:
            Tuple of (passed, event_if_failed)
        """
        if not self._enable_no_mock_check:
            return True, None

        self.logger.info("running_no_mock_validation")

        try:
            # Initialize validator if needed
            if self._no_mock_validator is None:
                self._no_mock_validator = NoMockValidator(
                    self.working_dir,
                    strict_mode=True,
                )

            # Run validation
            result = await self._no_mock_validator.validate()

            if result.passed:
                self.logger.info("no_mock_validation_passed")
                await self.event_bus.publish(mock_validation_passed_event(
                    source=self.name,
                    checks_run=result.checks_run,
                ))
                return True, None

            # Mock patterns detected - block build!
            self.logger.warning(
                "mock_patterns_detected",
                error_count=result.error_count,
                warning_count=result.warning_count,
            )

            # Build violation data for GeneratorAgent
            violations = [
                {
                    "file": f.file_path,
                    "line": f.line_number,
                    "code": f.error_code,
                    "message": f.error_message,
                    "suggested_fix": f.suggested_fix,
                }
                for f in result.failures
            ]

            # Publish MOCK_DETECTED event - GeneratorAgent will fix
            # Use typed factory function for better type safety
            mock_event = mock_detected_event(
                source=self.name,
                violations=violations,
            )
            await self.event_bus.publish(mock_event)

            return False, mock_event

        except Exception as e:
            self.logger.error("no_mock_validation_error", error=str(e))
            # Don't block on validator errors - let the build proceed
            return True, None

    async def _generate_missing_tests(self, event: Event) -> Optional[Event]:
        """
        Generate tests for missing requirement coverage.

        Phase 11: Triggered by FungusCompletenessAgent when it detects
        that a requirement has no corresponding test files.

        Args:
            event: REQUIREMENT_TEST_MISSING event with requirement data

        Returns:
            Event indicating test generation success/failure
        """
        data = event.data or {}
        req_id = data.get("requirement_id", "unknown")
        req_name = data.get("requirement_name", "Untitled Requirement")
        missing_tests = data.get("missing_tests", [])
        existing_tests = data.get("existing_tests", [])

        self.logger.info(
            "generating_missing_tests",
            requirement_id=req_id,
            requirement_name=req_name,
            missing_count=len(missing_tests),
            existing_count=len(existing_tests),
        )

        if not missing_tests:
            self.logger.info("no_missing_tests_to_generate", requirement_id=req_id)
            return None

        try:
            from ..tools.claude_code_tool import ClaudeCodeTool
            from ..tools.sandbox_tool import ProjectType

            # Detect project type
            from ..tools.sandbox_tool import SandboxTool
            sandbox = SandboxTool(self.working_dir)
            project_type = sandbox.detect_project_type()

            # Build targeted test generation prompt
            missing_tests_text = "\n".join(f"- {t}" for t in missing_tests)
            existing_tests_text = "\n".join(f"- {t}" for t in existing_tests) if existing_tests else "None"

            prompt = f"""Generate tests for missing requirement coverage.

## Requirement
- ID: {req_id}
- Name: {req_name}

## Missing Test Coverage
{missing_tests_text}

## Existing Tests (do not duplicate)
{existing_tests_text}

## Instructions
1. Create a test file in tests/{req_id}.test.ts
2. Test each missing scenario listed above
3. Use {self.test_framework} syntax (describe/it pattern)
4. Follow the project's existing test patterns

## CRITICAL RULES - NO MOCKS
- **NO MOCKS** - Use real implementations only
- NO vi.spyOn().mockImplementation()
- NO jest.mock() or vi.mock()
- Test actual behavior with real HTTP calls
- Use real database connections where possible

Generate the test file now."""

            # Use ClaudeCodeTool with test-generation skill
            tool = ClaudeCodeTool(
                working_dir=self.working_dir,
                agent_type="testing",
            )

            result = await tool.execute(
                prompt=prompt,
                agent_type="testing",
            )

            if result.success:
                self.logger.info(
                    "missing_tests_generated",
                    requirement_id=req_id,
                    requirement_name=req_name,
                )

                # Publish success event
                return Event(
                    type=EventType.TEST_SPEC_CREATED,
                    source=self.name,
                    data={
                        "requirement_id": req_id,
                        "requirement_name": req_name,
                        "tests_generated": missing_tests,
                        "triggered_by": "completeness_check",
                    },
                    success=True,
                )
            else:
                self.logger.error(
                    "missing_tests_generation_failed",
                    requirement_id=req_id,
                    error=result.error,
                )

                return tests_failed_event(
                    source=self.name,
                    error_message=f"Failed to generate tests for {req_name}: {result.error}",
                    data={
                        "requirement_id": req_id,
                        "triggered_by": "completeness_check",
                    },
                )

        except Exception as e:
            self.logger.error(
                "missing_tests_generation_error",
                requirement_id=req_id,
                error=str(e),
            )

            return tests_failed_event(
                source=self.name,
                error_message=str(e),
                data={
                    "requirement_id": req_id,
                    "triggered_by": "completeness_check",
                },
            )

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Execute validation workflow. Dispatches to autogen team or legacy."""
        self.logger.info(
            "validation_dispatch",
            mode="autogen" if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true" else "legacy",
        )
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Validation using autogen multi-agent debate: TestGenerator + TestValidator + NoMockEnforcer.

        Preserves NoMock validation, requirement-based test generation, and ValidationTeam delegation.
        """
        self._last_validation_time = datetime.now()
        self._validation_count += 1

        # Handle REQUIREMENT_TEST_MISSING events (same as legacy)
        for event in events:
            if event.type == EventType.REQUIREMENT_TEST_MISSING:
                return await self._generate_missing_tests(event)

        # CRITICAL: Run NoMock validation BEFORE anything else
        mock_check_passed, mock_event = await self._run_no_mock_validation()
        if not mock_check_passed:
            return mock_event

        # Build task prompt for autogen team
        task_prompt = (
            f"Run validation and test generation for the project at {self.working_dir}.\n\n"
            f"Test framework: {self.test_framework}\n"
            f"Validation number: {self._validation_count}\n"
            f"Requirements loaded: {len(self._requirements)}\n\n"
            "## Tasks:\n"
            "1. Generate comprehensive test suites using the project's test framework\n"
            "2. Ensure NO mocks are used — real integrations only\n"
            "3. Run the test suite and report results\n"
            "4. For failures, analyze root cause and suggest fixes\n\n"
            "## CRITICAL RULES — NO MOCKS:\n"
            "- NO vi.spyOn().mockImplementation()\n"
            "- NO jest.mock() or vi.mock()\n"
            "- Test actual behavior with real HTTP calls\n"
            "- Use real database connections where possible\n"
        )

        try:
            # Create combined tools: MCP tools + Claude Code
            # - npm: run tests, install test dependencies
            # - filesystem: read/write test files
            # - playwright: E2E browser testing
            # - claude_code: generate complex test code
            tools = self._create_combined_tools(
                mcp_categories=["npm", "filesystem", "playwright"],
                include_claude_code=True,
            )

            self.logger.info(
                "validation_agent_tools_created",
                tool_count=len(tools),
                tool_names=[getattr(t, 'name', str(t)) for t in tools[:10]],
            )

            team = self.create_team(
                operator_name="TestGenerator",
                operator_prompt=self._get_test_generator_prompt(),
                validator_name="NoMockEnforcer",
                validator_prompt=self._get_nomock_enforcer_prompt(),
                tools=tools,  # Use explicit combined tools
                max_turns=20,
                task=task_prompt,
            )

            result = await self.run_team(team, task_prompt)

            if result["success"]:
                self._retry_count = 0
                return tests_passed_event(
                    source=self.name,
                    validation_number=self._validation_count,
                    tests_passed=0,
                    tests_total=0,
                    pass_rate=0.0,
                    debug_iterations=0,
                    fixes_applied=0,
                    execution_time_ms=0,
                )
            else:
                self._retry_count += 1
                return tests_failed_event(
                    source=self.name,
                    error_message=result.get("result_text", "Autogen validation failed"),
                    validation_number=self._validation_count,
                )

        except Exception as e:
            self.logger.error("autogen_validation_failed", error=str(e))
            self._retry_count += 1
            return tests_failed_event(
                source=self.name,
                error_message=str(e),
                validation_number=self._validation_count,
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """Legacy: Execute validation workflow using ValidationTeam."""
        self._last_validation_time = datetime.now()
        self._validation_count += 1

        self.logger.info(
            "validation_starting",
            validation_number=self._validation_count,
            retry_count=self._retry_count,
        )

        # =====================================================
        # Phase 11: Handle REQUIREMENT_TEST_MISSING events
        # =====================================================
        for event in events:
            if event.type == EventType.REQUIREMENT_TEST_MISSING:
                return await self._generate_missing_tests(event)

        # =====================================================
        # CRITICAL: Run NoMock validation BEFORE build/tests
        # =====================================================
        mock_check_passed, mock_event = await self._run_no_mock_validation()
        if not mock_check_passed:
            self.logger.warning(
                "build_blocked_by_mock_check",
                message="Mock patterns detected - build blocked until fixed",
            )
            # Return early - GeneratorAgent will fix mocks then retrigger
            return mock_event

        # Publish start event
        await self.event_bus.publish(tests_running_event(
            source=self.name,
            validation_number=self._validation_count,
            working_dir=self.working_dir,
            test_framework=self.test_framework,
        ))

        try:
            # Create ValidationTeam config
            config = ValidationConfig(
                project_dir=self.working_dir,
                output_dir=str(Path(self.working_dir) / "validation_output"),
                requirements_path=self.requirements_path or "",
                test_framework=self.test_framework,
                use_docker=self.use_docker,
                docker_network=self.docker_network,
                frontend_port=self.frontend_port,
                backend_port=self.backend_port,
                max_debug_iterations=self.max_debug_iterations,
                timeout_seconds=self.timeout_seconds,
                enable_shell_stream=self.enable_shell_stream,
                on_shell_output=self._handle_shell_output if self.on_shell_output else None,
                on_progress=self._on_validation_progress,
            )
            
            # Initialize ValidationTeam
            self._validation_team = ValidationTeam(config)
            
            # Run validation
            result = await self._validation_team.run(self._requirements)
            self._last_result = result
            
            # Update shared state
            await self._update_metrics(result)
            
            # Store patterns if successful
            if result.success and self.memory_tool:
                await self._store_success_pattern(result)
            
            # Reset/increment retry count
            if result.success:
                self._retry_count = 0
            else:
                self._retry_count += 1
            
            # Publish result event
            return self._create_result_event(result)
            
        except Exception as e:
            self.logger.error("validation_failed", error=str(e))
            self._retry_count += 1

            return tests_failed_event(
                source=self.name,
                error_message=str(e),
                validation_number=self._validation_count,
            )
    
    async def _on_validation_progress(self, phase: str, data: dict) -> None:
        """Handle validation progress updates."""
        # Publish progress events
        if phase == "test_generation":
            if data.get("status") == "starting":
                await self.event_bus.publish(tests_running_event(
                    source=self.name,
                    phase="test_generation",
                    **data,
                ))

        elif phase == "testing":
            await self.event_bus.publish(tests_running_event(
                source=self.name,
                phase="testing",
                **data,
            ))
        
        elif phase == "debugging":
            # Custom event for debug phase
            pass
    
    async def _update_metrics(self, result: ValidationResult) -> None:
        """Update shared state with validation metrics."""
        if result.report:
            await self.shared_state.update_tests(
                passed=result.report.tests_passed,
                failed=result.report.tests_failed,
                total=result.report.tests_total,
            )
    
    def _create_result_event(self, result: ValidationResult) -> Event:
        """Create result event from validation result."""
        if result.success:
            return tests_passed_event(
                source=self.name,
                validation_number=self._validation_count,
                tests_passed=result.report.tests_passed if result.report else 0,
                tests_total=result.report.tests_total if result.report else 0,
                pass_rate=result.final_pass_rate,
                debug_iterations=result.debug_iterations,
                fixes_applied=result.total_fixes_applied,
                execution_time_ms=result.execution_time_ms,
            )
        else:
            return tests_failed_event(
                source=self.name,
                error_message="; ".join(result.errors) if result.errors else None,
                validation_number=self._validation_count,
                tests_passed=result.report.tests_passed if result.report else 0,
                tests_failed=result.report.tests_failed if result.report else 0,
                tests_total=result.report.tests_total if result.report else 0,
                data={
                    "pass_rate": result.final_pass_rate,
                    "debug_iterations": result.debug_iterations,
                    "action_items": len(result.report.action_items) if result.report else 0,
                },
            )
    
    async def _store_success_pattern(self, result: ValidationResult) -> None:
        """Store successful validation pattern in memory."""
        if not self.memory_tool or not getattr(self.memory_tool, 'enabled', False):
            return

        try:
            content = f"""## Validation Success

**Pass Rate:** {result.final_pass_rate:.1f}%
**Tests Passed:** {result.report.tests_passed if result.report else 0}
**Tests Total:** {result.report.tests_total if result.report else 0}
**Debug Iterations:** {result.debug_iterations}
**Fixes Applied:** {result.total_fixes_applied}
**Execution Time:** {result.execution_time_ms}ms

### Test Framework
- Framework: {self.test_framework}
- Docker: {'Yes' if self.use_docker else 'No'}
"""

            if hasattr(self.memory_tool, 'store'):
                await self.memory_tool.store(
                    content=content,
                    description="Successful validation run",
                    category="validation",
                    tags=["tests", "validation", self.test_framework],
                )

        except Exception as e:
            self.logger.warning("failed_to_store_pattern", error=str(e))

    # =========================================================================
    # Phase 8: LLM-Enhanced Test Assertion Validation
    # =========================================================================

    async def validate_test_assertions(
        self,
        test_code: str,
        source_code: str,
        test_file: str = "unknown",
    ) -> dict:
        """
        Use LLM to validate that test assertions are meaningful.

        Tests can pass but still be ineffective if:
        1. Assertions are trivial (expect(true).toBe(true))
        2. Assertions don't match the actual function behavior
        3. Edge cases are missing
        4. Mocks bypass the real logic being tested

        Args:
            test_code: The test file content
            source_code: The source code being tested
            test_file: Path to the test file for context

        Returns:
            Dict with validation results:
            {
                "valid": bool,
                "issues": [str],
                "missing_assertions": [str],
                "trivial_assertions": [str],
                "suggestions": [str],
                "confidence": float
            }
        """
        import re

        try:
            from ..tools.claude_code_tool import ClaudeCodeTool

            prompt = f"""Validate that these test assertions are meaningful and actually test the code behavior:

## TEST CODE:
```
{test_code[:2000]}
```

## SOURCE CODE BEING TESTED:
```
{source_code[:2000]}
```

## VALIDATION CRITERIA:

1. **Trivial Assertions** - Flag these as problems:
   - `expect(true).toBe(true)`
   - `expect(1).toBe(1)`
   - `expect(result).toBeDefined()` without checking the actual value
   - Empty test blocks

2. **Missing Edge Cases** - Tests should cover:
   - Empty input / null / undefined
   - Boundary values (0, -1, max)
   - Error conditions
   - Async edge cases

3. **Behavior Mismatch** - Assertions should match function behavior:
   - If function returns object, test should check properties
   - If function throws, test should check error type
   - If function has side effects, test should verify them

4. **Mock Overuse** - Flag if mocks bypass the logic being tested:
   - Testing a function but mocking everything it calls
   - Assertions only check mock was called, not the result

## RESPONSE FORMAT:

```json
{{
  "valid": true/false,
  "issues": [
    "Line 15: expect(result).toBeDefined() doesn't verify actual value",
    "Line 23: Mock bypasses the validation logic being tested"
  ],
  "missing_assertions": [
    "Should test with empty input",
    "Should test error case when user not found"
  ],
  "trivial_assertions": [
    "Line 10: expect(true).toBe(true) is always true"
  ],
  "suggestions": [
    "Replace toBeDefined() with toEqual(expected) on line 15",
    "Add test for null input handling"
  ],
  "confidence": 0.85,
  "summary": "2 trivial assertions, 3 missing edge cases"
}}
```
"""

            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context=f"Test assertion validation for {test_file}",
                agent_type="test_validator",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))

                self.logger.info(
                    "test_assertions_validated",
                    test_file=test_file,
                    valid=analysis.get("valid", False),
                    issues_count=len(analysis.get("issues", [])),
                    missing_count=len(analysis.get("missing_assertions", [])),
                )

                return analysis

        except Exception as e:
            self.logger.warning("test_assertion_validation_failed", error=str(e))

        # Fallback: basic heuristic check
        return self._fallback_assertion_check(test_code)

    def _fallback_assertion_check(self, test_code: str) -> dict:
        """
        Basic assertion validation without LLM.

        Uses regex to detect common trivial assertion patterns.
        """
        import re

        issues = []
        trivial = []

        # Pattern for trivial assertions
        trivial_patterns = [
            (r'expect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)', "expect(true).toBe(true)"),
            (r'expect\s*\(\s*false\s*\)\s*\.toBe\s*\(\s*false\s*\)', "expect(false).toBe(false)"),
            (r'expect\s*\(\s*1\s*\)\s*\.toBe\s*\(\s*1\s*\)', "expect(1).toBe(1)"),
            (r'expect\s*\(\s*["\'][^"\']*["\']\s*\)\s*\.toBe\s*\(\s*["\'][^"\']*["\']\s*\)',
             "expect('literal').toBe('literal')"),
        ]

        # Pattern for weak assertions
        weak_patterns = [
            (r'expect\s*\([^)]+\)\s*\.toBeDefined\s*\(\s*\)', "toBeDefined() doesn't check actual value"),
            (r'expect\s*\([^)]+\)\s*\.toBeTruthy\s*\(\s*\)', "toBeTruthy() is too permissive"),
            (r'expect\s*\([^)]+\)\s*\.not\.toBeNull\s*\(\s*\)', "not.toBeNull() doesn't verify value"),
        ]

        lines = test_code.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern, desc in trivial_patterns:
                if re.search(pattern, line):
                    trivial.append(f"Line {i}: {desc}")

            for pattern, desc in weak_patterns:
                if re.search(pattern, line):
                    issues.append(f"Line {i}: {desc}")

        # Check for empty test blocks
        empty_test_pattern = r'(?:it|test)\s*\([^)]+,\s*(?:async\s*)?\(\s*\)\s*=>\s*\{\s*\}\s*\)'
        for match in re.finditer(empty_test_pattern, test_code):
            line_num = test_code[:match.start()].count('\n') + 1
            trivial.append(f"Line {line_num}: Empty test block")

        return {
            "valid": len(issues) == 0 and len(trivial) == 0,
            "issues": issues,
            "missing_assertions": [],  # Can't detect without LLM
            "trivial_assertions": trivial,
            "suggestions": [
                "Replace trivial assertions with meaningful checks"
            ] if trivial else [],
            "confidence": 0.5,
            "summary": f"{len(trivial)} trivial, {len(issues)} weak assertions found",
        }

    async def validate_test_quality_batch(
        self,
        test_files: list[Path],
        source_dir: Path,
    ) -> dict:
        """
        Validate test quality for multiple test files.

        Args:
            test_files: List of test file paths
            source_dir: Directory containing source files

        Returns:
            Dict with overall test quality report
        """
        results = []
        total_issues = 0
        total_trivial = 0
        total_missing = 0

        for test_file in test_files[:10]:  # Limit for performance
            try:
                test_content = test_file.read_text(encoding='utf-8', errors='replace')

                # Try to find corresponding source file
                source_content = ""
                test_name = test_file.stem.replace('.test', '').replace('.spec', '')
                for ext in ['.ts', '.tsx', '.js', '.jsx']:
                    source_path = source_dir / f"{test_name}{ext}"
                    if source_path.exists():
                        source_content = source_path.read_text(encoding='utf-8', errors='replace')
                        break

                # Validate this test file
                result = await self.validate_test_assertions(
                    test_content,
                    source_content,
                    str(test_file),
                )

                results.append({
                    "file": str(test_file),
                    **result,
                })

                total_issues += len(result.get("issues", []))
                total_trivial += len(result.get("trivial_assertions", []))
                total_missing += len(result.get("missing_assertions", []))

            except Exception as e:
                self.logger.warning(
                    "test_quality_check_failed",
                    file=str(test_file),
                    error=str(e),
                )

        # Calculate overall score
        total_problems = total_issues + total_trivial + total_missing
        quality_score = max(0, 10 - total_problems)

        return {
            "files_analyzed": len(results),
            "total_issues": total_issues,
            "total_trivial_assertions": total_trivial,
            "total_missing_assertions": total_missing,
            "quality_score": quality_score,
            "results": results,
            "recommendations": self._generate_test_recommendations(results),
        }

    def _generate_test_recommendations(self, results: list[dict]) -> list[str]:
        """Generate recommendations from test validation results."""
        recommendations = []

        # Count problem types
        trivial_count = sum(len(r.get("trivial_assertions", [])) for r in results)
        issue_count = sum(len(r.get("issues", [])) for r in results)
        missing_count = sum(len(r.get("missing_assertions", [])) for r in results)

        if trivial_count > 0:
            recommendations.append(
                f"Remove {trivial_count} trivial assertions that always pass"
            )

        if issue_count > 0:
            recommendations.append(
                f"Strengthen {issue_count} weak assertions (toBeDefined → toEqual)"
            )

        if missing_count > 0:
            recommendations.append(
                f"Add {missing_count} missing edge case tests"
            )

        if not recommendations:
            recommendations.append("Test quality is good - assertions are meaningful")

        return recommendations

    def _get_test_generator_prompt(self) -> str:
        """System prompt for TestGenerator autogen agent."""
        return f"""You are an expert test generator for TypeScript/React/Node projects.

## Available MCP Tools

### NPM Tools
- `npm_run` - Run npm scripts (test, test:coverage)
- `npm_install` - Install test dependencies (vitest, playwright, etc.)
- `npm_list` - List installed packages

### Filesystem Tools
- `filesystem_read_file` - Read source files to understand what to test
- `filesystem_write_file` - Write test files
- `filesystem_list_files` - List files in test directories

### Playwright Tools
- `playwright_navigate` - Navigate browser for E2E tests
- `playwright_click` - Click elements
- `playwright_fill` - Fill form inputs
- `playwright_screenshot` - Capture screenshots
- `playwright_evaluate` - Run JavaScript in browser

### Claude Code Tool
- `claude_code` - For complex test code generation

## Workflow

1. Use `filesystem_list_files` to find existing tests and source files
2. Use `filesystem_read_file` to understand source code behavior
3. Use `claude_code` to generate comprehensive test suites
4. Use `npm_run test` to verify tests pass
5. For E2E tests, use Playwright tools to automate browser testing

## Test Framework: {self.test_framework}

Generate comprehensive test suites using {self.test_framework}.

## CRITICAL RULES - NO MOCKS

- NEVER use vi.mock(), jest.mock(), vi.spyOn().mockImplementation()
- All tests must use real implementations
- Write tests that verify actual behavior:
  - Real HTTP calls to actual endpoints
  - Real database queries
  - Real API responses
- No hardcoded data arrays pretending to be database responses
- No TODO/FIXME placeholders

When tests are generated and passing, say TASK_COMPLETE."""

    def _get_nomock_enforcer_prompt(self) -> str:
        """System prompt for NoMockEnforcer autogen agent."""
        return """You enforce the NO-MOCK policy in generated tests.

## Violations to Detect

1. **Mock Functions**
   - vi.mock(), jest.mock()
   - vi.spyOn().mockImplementation()
   - vi.fn() without real implementation

2. **Fake Data**
   - Hardcoded data arrays pretending to be database responses
   - Inline objects that should come from real sources
   - const mockUsers = [...] patterns

3. **Placeholders**
   - TODO/FIXME comments
   - throw new Error('Not implemented')
   - Empty function bodies

4. **Bypasses**
   - Mocking fetch/axios to return fake data
   - Mocking database client to return hardcoded results
   - Mocking auth to always return success

## What is Allowed

- Test fixtures loaded from files
- Test databases with seeded data
- Real HTTP calls to test servers
- Integration tests with actual services

## Review Process

1. Read each test file
2. Check for mock patterns listed above
3. Verify tests use real integrations
4. If violations found, list them with line numbers
5. Request replacements with real implementations

If all tests are mock-free, say TASK_COMPLETE.
If mock patterns found, list them clearly and request replacements."""

    def _get_action_description(self) -> str:
        """Get description of current action."""
        return f"Running validation #{self._validation_count}"
    
    def set_requirements(self, requirements: list[dict]) -> None:
        """Set requirements for validation."""
        self._requirements = requirements
        self.logger.info("requirements_set", count=len(requirements))
    
    def get_last_result(self) -> Optional[ValidationResult]:
        """Get the last validation result."""
        return self._last_result
    
    def get_shell_buffer(self, count: int = 100) -> list[ShellOutput]:
        """Get recent shell output."""
        if self._shell_stream:
            return self._shell_stream.get_recent(count)
        return []


# Convenience function
async def run_validation(
    project_dir: str,
    requirements: list[dict],
    test_framework: str = "vitest",
    use_docker: bool = True,
    max_iterations: int = 3,
) -> ValidationResult:
    """
    Run validation as standalone (without Orchestrator).
    
    Args:
        project_dir: Path to project
        requirements: List of requirements
        test_framework: Test framework to use
        use_docker: Use Docker for isolation
        max_iterations: Max debug iterations
        
    Returns:
        ValidationResult
    """
    config = ValidationConfig(
        project_dir=project_dir,
        output_dir=str(Path(project_dir) / "validation_output"),
        requirements_path="",
        test_framework=test_framework,
        use_docker=use_docker,
        max_debug_iterations=max_iterations,
    )
    
    team = ValidationTeam(config)
    return await team.run(requirements)