"""
Runtime Debug Agent - Autonomous agent for runtime debugging with Claude CLI.

This agent:
1. Triggers after BUILD_SUCCEEDED to test app startup
2. Runs the project and captures any errors
3. Uses Claude CLI to analyze errors and generate fixes
4. Applies fixes and re-tests
5. Works with any project type (Electron, Node, Python, etc.)
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import os
import structlog
import uuid

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import (
    Event, EventType,
    agent_event,
    file_modified_event,
    code_fixed_event,
    validation_passed_event,
    validation_error_event,
)
from ..mind.shared_state import SharedState
from ..validators.general_runtime_validator import (
    GeneralRuntimeValidator,
    ProjectType,
    RuntimeResult,
    DebugAnalysis,
)
from ..registry.document_registry import DocumentRegistry
from ..registry.documents import DebugReport, SuggestedFix, VisualIssue

logger = structlog.get_logger(__name__)


class RuntimeDebugAgent(AutonomousAgent):
    """
    Agent that performs runtime debugging after successful builds.

    Uses Claude CLI to intelligently analyze and fix runtime errors
    for any project type. Writes debug reports to reports/debug/.

    Workflow:
    1. Subscribe to BUILD_SUCCEEDED, APP_CRASHED, CODE_FIXED events
    2. When triggered, run the project and capture output
    3. If errors, send to Claude CLI for analysis
    4. Apply Claude's suggested fixes
    5. Re-run and verify
    6. Write debug report to DocumentRegistry
    """

    def __init__(
        self,
        name: str,
        event_bus,
        shared_state: SharedState,
        working_dir: str,
        max_fix_attempts: int = 3,
        startup_timeout: float = 30.0,
        startup_wait: float = 5.0,
        poll_interval: float = 2.0,
        memory_tool: Optional[Any] = None,
    ):
        """
        Initialize the runtime debug agent.

        Args:
            name: Agent name
            event_bus: Event bus for communication
            shared_state: Shared state for metrics
            working_dir: Project working directory
            max_fix_attempts: Maximum automatic fix attempts
            startup_timeout: Timeout for runtime tests
            startup_wait: Time to wait for startup errors
            poll_interval: Polling interval
            memory_tool: Optional memory tool for searching/storing patterns
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            poll_interval=poll_interval,
        )
        self.max_fix_attempts = max_fix_attempts
        self.startup_timeout = startup_timeout
        self.startup_wait = startup_wait
        self.memory_tool = memory_tool
        self._fix_attempts = 0
        self._last_test_time: Optional[datetime] = None
        self._applied_fixes: list[str] = []
        self._detected_project_type: Optional[ProjectType] = None
        
        # Initialize DocumentRegistry for writing debug reports
        self._doc_registry = DocumentRegistry(working_dir)

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.BUILD_SUCCEEDED,
            EventType.APP_CRASHED,
            EventType.CODE_FIXED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to run runtime tests.

        Acts when:
        - Build succeeded (new build to test)
        - App crashed (need to diagnose)
        - Code was fixed (re-test after fix)
        """
        for event in events:
            # Check for initial trigger
            if event.data and event.data.get("trigger") == "initial":
                # Only test initially if build has already succeeded
                if self.shared_state.metrics.build_success:
                    return True
                continue

            # Test after successful build
            if event.type == EventType.BUILD_SUCCEEDED:
                self.logger.info("build_succeeded_triggering_runtime_test")
                return True

            # Diagnose after crash
            if event.type == EventType.APP_CRASHED:
                self.logger.info("app_crashed_triggering_diagnosis")
                return True

            # Re-test after code fix (but not our own fixes)
            if event.type == EventType.CODE_FIXED:
                if event.source != self.name:
                    self.logger.info("code_fixed_triggering_retest")
                    return True

        return False

    async def _should_act_on_state(self) -> bool:
        """
        Check if we should test based on state.

        Run test if:
        - Build succeeded but runtime not yet tested
        - We haven't exceeded fix attempts
        """
        metrics = self.shared_state.metrics
        if metrics.build_success and not getattr(metrics, 'runtime_tested', False):
            if self._fix_attempts < self.max_fix_attempts:
                return True
        return False

    async def _write_debug_report(
        self,
        runtime_result: RuntimeResult,
        analysis: Optional[DebugAnalysis],
    ) -> None:
        """
        Write a debug report to the DocumentRegistry.
        
        Args:
            runtime_result: Result from runtime testing
            analysis: Optional debug analysis from Claude
        """
        try:
            # Collect console errors
            console_errors = []
            if runtime_result.stderr:
                console_errors.append(runtime_result.stderr[:1000])
            if runtime_result.error_summary:
                console_errors.append(runtime_result.error_summary)
            
            # Convert analysis fix suggestions to SuggestedFix objects
            suggested_fixes = []
            if analysis and analysis.fix_suggestions:
                for i, suggestion in enumerate(analysis.fix_suggestions):
                    suggested_fixes.append(SuggestedFix(
                        id=f"fix_{i+1}",
                        priority=i + 1,
                        description=suggestion.explanation[:200] if suggestion.explanation else "Fix suggestion",
                        file=suggestion.file_path,
                        action="modify",
                        code_hint=suggestion.fixed_content[:500] if suggestion.fixed_content else None,
                    ))
            
            # Create debug report
            report = DebugReport(
                id=f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                timestamp=datetime.now(),
                source_agent=self.name,
                screenshots=[],  # Would need browser integration for screenshots
                visual_issues=[],
                console_errors=console_errors,
                suggested_fixes=suggested_fixes,
                priority_order=[f.id for f in suggested_fixes],
                affected_files=self._applied_fixes[-10:] if self._applied_fixes else [],
                root_cause_hypothesis=analysis.root_cause if analysis else None,
                debugging_steps=analysis.debugging_steps if analysis else [],
                readiness_score=100 if not runtime_result.has_errors else 50,
                test_url=None,
            )
            
            # Write to registry
            await self._doc_registry.write_document(report, priority=2)
            
            self.logger.info(
                "debug_report_written",
                report_id=report.id,
                console_errors=len(console_errors),
                suggested_fixes=len(suggested_fixes),
            )
            
        except Exception as e:
            self.logger.warning("failed_to_write_debug_report", error=str(e))

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Run runtime tests and attempt fixes using Claude CLI.

        Returns:
            Event describing test results
        """
        self.logger.info("running_runtime_debug")
        self._last_test_time = datetime.now()

        # Create validator
        validator = GeneralRuntimeValidator(
            project_dir=self.working_dir,
            timeout=self.startup_timeout,
            startup_wait=self.startup_wait,
            clean_env=True,
        )

        # Check if applicable
        if not validator.is_applicable():
            self.logger.info("runtime_validator_not_applicable")
            return agent_event(
                self.name,
                EventType.VALIDATION_PASSED,
                action="runtime_test_skipped",
                reason="Unknown project type",
            )

        # Store detected project type
        self._detected_project_type = validator.detect_project_type()
        self.logger.info(
            "project_type_detected",
            project_type=self._detected_project_type.value,
        )

        # Search for similar runtime errors in memory with intelligent scoring
        if self.memory_tool and self.memory_tool.enabled:
            try:
                # Search with reranking for better relevance
                from ..tools.memory_tool import ErrorFixPattern

                patterns = await self.memory_tool.search_similar_errors(
                    error_type="runtime_error",
                    error_message=f"{self._detected_project_type.value} startup",
                    project_type=self._detected_project_type.value,
                    limit=5,
                    rerank=True
                )

                if patterns:
                    self.logger.info(
                        "found_similar_runtime_patterns",
                        count=len(patterns),
                        top_confidence=patterns[0].confidence if patterns else 0
                    )

                    scored_patterns = []
                    now = datetime.now()

                    for pattern in patterns:
                        base_confidence = pattern.confidence
                        temporal_factor = 1.0
                        final_score = base_confidence

                        scored_patterns.append({
                            "pattern": pattern,
                            "score": final_score
                        })

                    scored_patterns.sort(key=lambda x: x["score"], reverse=True)

                    learned_fixes = []
                    for item in scored_patterns:
                        pattern = item["pattern"]
                        if pattern.confidence > 0.6:
                            learned_fixes.append({
                                "fix": pattern.fix_description,
                                "files": pattern.files_modified,
                                "confidence": pattern.confidence,
                                "score": item["score"]
                            })
                            self.logger.info(
                                "applying_learned_fix_pattern",
                                fix=pattern.fix_description[:100],
                                confidence=pattern.confidence,
                                score=item["score"],
                                files=len(pattern.files_modified)
                            )

                    if learned_fixes:
                        self._applied_fixes.extend([f["fix"] for f in learned_fixes])
                        self.logger.info(
                            "runtime_patterns_selected",
                            count=len(learned_fixes),
                            avg_confidence=sum(f["confidence"] for f in learned_fixes) / len(learned_fixes)
                        )
            except Exception as e:
                self.logger.warning("memory_search_failed", error=str(e))

        # Run and debug with Claude CLI
        runtime_result, analysis = await validator.run_and_debug()

        # Write debug report to DocumentRegistry
        await self._write_debug_report(runtime_result, analysis)

        # Update shared state
        await self._update_runtime_metrics(
            not runtime_result.has_errors,
            1 if runtime_result.has_errors else 0,
        )

        if not runtime_result.has_errors:
            self.logger.info(
                "runtime_test_passed",
                project_type=self._detected_project_type.value,
            )
            return validation_passed_event(
                source=self.name,
                check_type="runtime",
                project_type=self._detected_project_type.value,
                message=f"{self._detected_project_type.value} app starts correctly",
            )

        # Test failed - attempt fixes
        self.logger.warning(
            "runtime_test_failed",
            project_type=self._detected_project_type.value,
            fix_attempts=self._fix_attempts,
            error=runtime_result.error_summary[:200] if runtime_result.error_summary else "Unknown",
        )

        # Try to apply Claude's fixes if we haven't exceeded attempts
        if self._fix_attempts < self.max_fix_attempts and analysis:
            fix_applied = await self._apply_claude_fixes(analysis)
            self._fix_attempts += 1

            if fix_applied:
                return code_fixed_event(
                    source=self.name,
                    success=True,
                    fix_type="claude_runtime_fix",
                    extra_data={
                        "project_type": self._detected_project_type.value,
                        "fixes_applied": self._applied_fixes[-5:],
                    },
                )

        # Store runtime debugging session in memory
        if self.memory_tool and runtime_result.has_errors:
            try:
                project_name = os.path.basename(self.working_dir)

                errors = []
                if runtime_result.error_summary:
                    errors.append({
                        "error_type": "runtime_error",
                        "message": runtime_result.error_summary[:300]
                    })

                fix_suggestions = []
                if analysis and analysis.fix_suggestions:
                    fix_suggestions = [s.explanation[:100] for s in analysis.fix_suggestions[:3]]

                await self.memory_tool.store_runtime_debug(
                    project_name=project_name,
                    project_type=self._detected_project_type.value if self._detected_project_type else "unknown",
                    runtime_success=not runtime_result.has_errors,
                    crashed=runtime_result.crashed,
                    errors=errors,
                    fix_suggestions=fix_suggestions if fix_suggestions else None
                )
                self.logger.debug("runtime_debug_stored", project_name=project_name)
            except Exception as e:
                self.logger.warning("runtime_debug_store_failed", error=str(e))

        # Return failure event
        return validation_error_event(
            source=self.name,
            error_message=runtime_result.error_summary[:500] if runtime_result.error_summary else "Runtime error",
            check_type="runtime",
            project_type=self._detected_project_type.value if self._detected_project_type else "unknown",
            fix_attempts=self._fix_attempts,
            data={
                "stdout": runtime_result.stdout[:500],
                "stderr": runtime_result.stderr[:500],
                "analysis": analysis.root_cause if analysis else None,
            },
        )

    async def _update_runtime_metrics(self, success: bool, error_count: int) -> None:
        """Update shared state with runtime metrics."""
        try:
            if hasattr(self.shared_state, 'update_runtime'):
                await self.shared_state.update_runtime(
                    tested=True,
                    success=success,
                    errors=error_count,
                )
            else:
                # Fallback: update validation metrics
                if not success:
                    await self.shared_state.update_validation(
                        errors=self.shared_state.metrics.validation_errors + error_count,
                    )
        except Exception as e:
            self.logger.error("failed_to_update_metrics", error=str(e))

    async def _apply_claude_fixes(self, analysis: DebugAnalysis) -> bool:
        """
        Apply fixes suggested by Claude CLI.

        Args:
            analysis: Debug analysis from Claude

        Returns:
            True if any fix was applied
        """
        if not analysis.fix_suggestions:
            self.logger.info("no_fix_suggestions_from_claude")
            return False

        self.logger.info(
            "applying_claude_fixes",
            num_fixes=len(analysis.fix_suggestions),
        )

        fix_applied = False
        project_dir = Path(self.working_dir)

        for suggestion in analysis.fix_suggestions:
            try:
                file_path = project_dir / suggestion.file_path

                # Create parent directories if needed
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write the fixed content
                file_path.write_text(suggestion.fixed_content, encoding='utf-8')

                self.logger.info(
                    "fix_applied",
                    file=suggestion.file_path,
                    explanation=suggestion.explanation[:100],
                )

                self._applied_fixes.append(suggestion.file_path)
                fix_applied = True

                # Publish file event
                await self.event_bus.publish(file_modified_event(
                    source=self.name,
                    file_path=str(file_path),
                ))

            except Exception as e:
                self.logger.error(
                    "fix_apply_failed",
                    file=suggestion.file_path,
                    error=str(e),
                )

        return fix_applied

    def _get_action_description(self) -> str:
        return f"Runtime debugging ({self._detected_project_type.value if self._detected_project_type else 'detecting'})"

    def get_status_details(self) -> dict:
        """Get detailed status for debugging."""
        return {
            "fix_attempts": self._fix_attempts,
            "max_fix_attempts": self.max_fix_attempts,
            "applied_fixes": self._applied_fixes[-10:],  # Last 10
            "detected_project_type": self._detected_project_type.value if self._detected_project_type else None,
            "last_test_time": self._last_test_time.isoformat() if self._last_test_time else None,
        }
