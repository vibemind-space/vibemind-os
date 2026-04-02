"""
Generator Agent - Autonomous agent for code generation and fixes.

Subscribes to CODE_FIX_NEEDED events and uses ClaudeCodeTool to generate
or fix code. Publishes CODE_GENERATED and FILE_CREATED events.
"""

import asyncio
from typing import Optional
import os
import structlog
from typing import TYPE_CHECKING

from ..mind.event_bus import (
    EventBus, Event, EventType,
    mock_replaced_event,
    file_modified_event,
    implementation_plan_created_event,
    code_fixed_event,
    recovery_failed_event,
    pattern_learned_event,
)
from ..mind.event_payloads import PatternRetrievedPayload
from ..mind.shared_state import SharedState
from ..mind.prompt_hints import PromptHints, merge_hints_from_events, build_hints_from_event
from ..mind.event_payloads import (
    DebugReportCreatedPayload,
    QualityReportCreatedPayload,
    TestFailurePayload,
    TypeErrorPayload,
    MockViolationPayload,
    BuildFailurePayload,
)
from ..tools.claude_code_tool import ClaudeCodeTool, CodeGenerationResult
from ..tools.memory_tool import MemoryTool
from ..registry.document_registry import DocumentRegistry
from ..registry.documents import (
    DebugReport,
    ImplementationPlan,
    PlannedFix,
    FileChange,
    QualityReport,
)
from ..registry.document_types import DocumentType
from .autonomous_base import AutonomousAgent, AgentStatus
from .autogen_team_mixin import AutogenTeamMixin

if TYPE_CHECKING:
    from ..engine.tech_stack import TechStack


logger = structlog.get_logger(__name__)


class GeneratorAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Autonomous agent that handles code generation and fixes.

    Subscribes to:
    - CODE_FIX_NEEDED: When code needs to be fixed based on errors
    - RECOVERY_ATTEMPTED: After a recovery attempt to check if more is needed

    Publishes:
    - CODE_GENERATED: When code is generated
    - CODE_FIXED: When code is fixed
    - FILE_CREATED/FILE_MODIFIED: When files are created or modified
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        timeout: int = 300,
        memory_tool: Optional[MemoryTool] = None,
        document_registry: Optional[DocumentRegistry] = None,
        tech_stack: Optional["TechStack"] = None,  # FIX-27: Add tech_stack parameter
    ):
        super().__init__(name, event_bus, shared_state, working_dir)

        # Load code-generation skill from .claude/skills/
        skill = None
        try:
            from ..skills.loader import SkillLoader
            engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            loader = SkillLoader(engine_root)
            skill = loader.load_skill("code-generation")
            if skill:
                logger.info("skill_loaded", agent=name, skill_name=skill.name, tokens=skill.instruction_tokens)
        except Exception as e:
            logger.debug("skill_load_failed", agent=name, error=str(e))

        self.tool = ClaudeCodeTool(working_dir=working_dir, timeout=timeout, skill=skill)
        self.memory_tool = memory_tool
        self.document_registry = document_registry
        self.tech_stack = tech_stack
        self._fix_queue: list[Event] = []
        self._last_fix_time: Optional[float] = None
        self._cooldown_seconds = 5.0  # Prevent rapid fire fixes
        self._pending_debug_reports: list[DebugReport] = []
        self._pending_quality_reports: list[QualityReport] = []

        if tech_stack:
            self.logger.info(
                "generator_tech_stack_configured",
                frontend=getattr(tech_stack, 'frontend_framework', None),
                backend=getattr(tech_stack, 'backend_framework', None),
            )

    def _get_task_type(self) -> str:
        """Return task type for AgentContextBridge."""
        return "frontend"

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens to."""
        return [
            EventType.CODE_FIX_NEEDED,
            EventType.TEST_FAILED,
            EventType.BUILD_FAILED,
            EventType.VALIDATION_ERROR,
            EventType.TYPE_ERROR,
            EventType.DEBUG_REPORT_CREATED,  # From PlaywrightE2EAgent
            EventType.QUALITY_REPORT_CREATED,  # From CodeQualityAgent
            EventType.MOCK_DETECTED,  # From ValidationTeamAgent - CRITICAL!
            EventType.UX_ISSUE_FOUND,  # From UXDesignAgent - UI/UX problems
            # Backend agent failures (Task 11) - retry/fix on backend generation failures
            EventType.DATABASE_SCHEMA_FAILED,  # From DatabaseAgent
            EventType.API_GENERATION_FAILED,  # From APIAgent
            EventType.AUTH_SETUP_FAILED,  # From AuthAgent
            EventType.ENV_CONFIG_FAILED,  # Task 19: From InfrastructureAgent
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide if we should generate/fix code.

        Acts when:
        - There are CODE_FIX_NEEDED events
        - There are failure events that haven't been addressed
        - There are pending DEBUG_REPORTs to process
        - There are pending QUALITY_REPORTs to process
        - Not in cooldown period
        """
        if not events:
            # Check for pending documents in document registry
            if self.document_registry:
                pending = await self.document_registry.get_pending_for_agent("Generator")
                if pending:
                    self._pending_debug_reports = [
                        d for d in pending if isinstance(d, DebugReport)
                    ]
                    self._pending_quality_reports = [
                        d for d in pending if isinstance(d, QualityReport)
                    ]
                    if self._pending_debug_reports or self._pending_quality_reports:
                        return True
            return False

        # Check cooldown
        import time
        if self._last_fix_time:
            elapsed = time.time() - self._last_fix_time
            if elapsed < self._cooldown_seconds:
                return False

        # Check for actionable events
        fix_events = [
            e for e in events
            if e.type in (
                EventType.CODE_FIX_NEEDED,
                EventType.TEST_FAILED,
                EventType.BUILD_FAILED,
                EventType.VALIDATION_ERROR,
                EventType.TYPE_ERROR,
                EventType.MOCK_DETECTED,  # CRITICAL: Handle mock violations immediately
                EventType.UX_ISSUE_FOUND,  # UI/UX problems from UXDesignAgent
                # Backend agent failures (Task 11) - retry/fix on backend generation failures
                EventType.DATABASE_SCHEMA_FAILED,
                EventType.API_GENERATION_FAILED,
                EventType.AUTH_SETUP_FAILED,
                EventType.ENV_CONFIG_FAILED,  # Task 20: Infrastructure failures
            )
            and not e.success
            # Phase 28: Skip events managed by TaskExecutor retry (SoMBridge tags these)
            and not e.data.get("som_managed")
            # Phase 28: Skip differential analysis gaps (DifferentialFixAgent handles these)
            and not e.data.get("source_analysis", "").startswith("differential")
            # Phase 31: Skip user vibe-coding fixes (user manages these files)
            and not e.data.get("source") == "user_vibe"
        ]

        # Check for DEBUG_REPORT_CREATED events
        debug_events = [e for e in events if e.type == EventType.DEBUG_REPORT_CREATED]
        if debug_events and self.document_registry:
            for event in debug_events:
                # Use typed payload if available, fallback to data.get()
                if event.typed and isinstance(event.typed, DebugReportCreatedPayload):
                    doc_id = event.typed.doc_id
                else:
                    doc_id = event.data.get("doc_id")
                if doc_id:
                    doc = await self.document_registry.read_document(doc_id)
                    if doc and isinstance(doc, DebugReport):
                        self._pending_debug_reports.append(doc)

        # Check for QUALITY_REPORT_CREATED events
        quality_events = [e for e in events if e.type == EventType.QUALITY_REPORT_CREATED]
        if quality_events and self.document_registry:
            for event in quality_events:
                # Use typed payload if available, fallback to data.get()
                if event.typed and isinstance(event.typed, QualityReportCreatedPayload):
                    doc_id = event.typed.doc_id
                    requires_action = event.typed.requires_action
                else:
                    doc_id = event.data.get("doc_id")
                    requires_action = event.data.get("requires_action")
                if doc_id and requires_action:
                    doc = await self.document_registry.read_document(doc_id)
                    if doc and isinstance(doc, QualityReport):
                        self._pending_quality_reports.append(doc)

        return (
            len(fix_events) > 0 or
            len(self._pending_debug_reports) > 0 or
            len(self._pending_quality_reports) > 0
        )

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Generate or fix code based on events. Dispatches to autogen team or legacy.
        """
        self.logger.info(
            "generator_act_starting",
            event_count=len(events),
            mode="autogen" if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true" else "legacy",
        )
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Code generation/fix using autogen team: CodeOperator + ArchitectReviewer + QAValidator.

        Preserves memory tool integration, document registry, and prompt hints.
        """
        import time
        self._last_fix_time = time.time()
        await self.shared_state.set_generator_pending(True)

        # ===== NEW: Get rich context via AgentContextBridge =====
        # This combines static context (RichContextProvider) with dynamic RAG search
        context = await self.get_task_context(
            query="React components TypeScript UI design system frontend patterns",
            epic_id=events[0].data.get("epic_id") if events and events[0].data else None,
        )

        # Store design context for use in prompt building
        self._design_context = None
        if context:
            self._design_context = {
                "design_tokens": context.design_tokens,
                "rag_results": context.rag_results[:3] if context.rag_results else [],
            }
            self.logger.info(
                "context_bridge_loaded",
                has_design_tokens=bool(context.design_tokens),
                rag_results_count=len(context.rag_results) if context.rag_results else 0,
            )

        try:
            # --- Collect errors (same logic as legacy) ---
            errors_to_fix = self._collect_errors_from_events(events)

            # Collect from debug/quality reports
            debug_report_ids = []
            for report in self._pending_debug_reports:
                debug_report_ids.append(report.id)
                for issue in report.visual_issues:
                    errors_to_fix.append({
                        "type": "visual_issue",
                        "message": issue.description,
                        "file": issue.element,
                        "severity": issue.severity,
                        "data": {"expected": issue.expected, "actual": issue.actual},
                    })
                for fix in report.suggested_fixes:
                    errors_to_fix.append({
                        "type": "debug_report_fix",
                        "message": fix.description,
                        "file": fix.file,
                        "action": fix.action,
                        "data": {"priority": fix.priority},
                    })
                if report.root_cause_hypothesis:
                    errors_to_fix.append({
                        "type": "root_cause",
                        "message": report.root_cause_hypothesis,
                        "file": None,
                        "data": {"affected_files": report.affected_files},
                    })
            self._pending_debug_reports = []

            quality_report_ids = []
            quality_tasks = []
            for report in self._pending_quality_reports:
                quality_report_ids.append(report.id)
                for task in report.documentation_tasks:
                    quality_tasks.append({
                        "type": "documentation_task",
                        "task_type": task.task_type,
                        "message": task.description,
                        "file": task.target_path,
                    })
                for task in report.cleanup_tasks:
                    if task.confidence >= 0.9:
                        quality_tasks.append({
                            "type": "cleanup_task",
                            "message": f"Remove unused file: {task.file_path}",
                            "file": task.file_path,
                        })
                for task in report.refactor_tasks:
                    quality_tasks.append({
                        "type": "refactor_task",
                        "message": task.description,
                        "file": task.file_path,
                    })
            self._pending_quality_reports = []

            if quality_tasks and not errors_to_fix:
                result = await self._handle_quality_tasks(quality_tasks, quality_report_ids)
                return result

            errors_to_fix.extend(quality_tasks)

            if not errors_to_fix:
                return None

            # Memory search (preserved)
            similar_fixes = []
            if self.memory_tool and self.memory_tool.enabled:
                for error in errors_to_fix[:3]:
                    try:
                        patterns = await self.memory_tool.search_similar_errors(
                            error_type=error["type"],
                            error_message=error["message"][:200],
                            project_type=self._detect_project_type(),
                            limit=5,
                            rerank=True,
                        )
                        if patterns:
                            similar_fixes.extend(patterns)
                    except Exception:
                        pass

            # Build prompt with hints
            prompt = self._build_fix_prompt(errors_to_fix, similar_fixes, events=events)

            # --- Autogen team execution ---
            team = self.create_team(
                operator_name="CodeOperator",
                operator_prompt=(
                    "You are an expert full-stack code generator for TypeScript/React/Node projects. "
                    "You fix build errors, type errors, test failures, runtime errors, and mock violations. "
                    "You generate production-ready code — never use mocks, placeholders, or TODOs. "
                    "Apply fixes by editing files directly. Follow the project's coding style. "
                    "After applying all fixes, say TASK_COMPLETE."
                ),
                validator_name="ArchitectReviewer",
                validator_prompt=(
                    "You review code fixes for architectural quality. Check:\n"
                    "1. Root cause is addressed, not just symptoms\n"
                    "2. No mocks, placeholders, or TODOs introduced\n"
                    "3. TypeScript types are correct and complete\n"
                    "4. Imports are valid and files exist\n"
                    "5. Code follows project patterns\n"
                    "6. No regressions introduced\n"
                    "If the fix is correct, say TASK_COMPLETE.\n"
                    "If issues remain, describe what needs to change."
                ),
                tool_categories=["filesystem", "npm", "git"],
                max_turns=25,
                task=prompt,
            )

            result = await self.run_team(team, prompt)

            if result["success"]:
                await self.shared_state.record_fix(0)
                await self.shared_state.clear_stuck_state()

                # Store in memory
                if self.memory_tool and self.memory_tool.enabled:
                    try:
                        iteration = getattr(self.shared_state, 'iteration', 0)
                        for error in errors_to_fix[:3]:
                            await self.memory_tool.store_error_fix(
                                error_type=error["type"],
                                error_message=error["message"][:300],
                                fix_description="Autogen team fix applied",
                                files_modified=[],
                                project_type=self._detect_project_type(),
                                project_name=os.path.basename(self.working_dir),
                                iteration=iteration,
                                success=True,
                            )
                    except Exception:
                        pass

                # Mark debug reports consumed
                if self.document_registry and debug_report_ids:
                    for doc_id in debug_report_ids:
                        await self.document_registry.mark_consumed(doc_id, "Generator")

                self._pending_events.clear()

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    attempted=len(errors_to_fix),
                    files_modified=0,
                )
            else:
                return recovery_failed_event(
                    source=self.name,
                    error=result.get("result_text", "Autogen team generation failed"),
                    attempted=len(errors_to_fix),
                )

        except Exception as e:
            self.logger.error("autogen_generation_failed", error=str(e))
            return recovery_failed_event(
                source=self.name,
                error=str(e),
            )
        finally:
            await self.shared_state.set_generator_pending(False)

    def _collect_errors_from_events(self, events: list[Event]) -> list[dict]:
        """Extract error dicts from events (shared by both paths)."""
        errors_to_fix = []
        for event in events:
            # Phase 28: Skip events managed by other handlers
            if event.data.get("som_managed"):
                continue
            if event.data.get("source_analysis", "").startswith("differential"):
                continue
            # Phase 31: Skip user vibe-coding fixes
            if event.data.get("source") == "user_vibe":
                continue

            if event.type == EventType.CODE_FIX_NEEDED:
                errors_to_fix.append({
                    "type": "fix_request",
                    "message": event.error_message or event.data.get("message", ""),
                    "file": event.file_path,
                    "data": event.data,
                })
            elif event.type == EventType.TEST_FAILED:
                if event.typed and isinstance(event.typed, TestFailurePayload):
                    payload = event.typed
                    errors_to_fix.append({
                        "type": "test_failure",
                        "message": payload.error_message or event.error_message or "Test failed",
                        "file": payload.test_file or event.file_path,
                        "test_name": payload.test_name,
                        "expected": payload.expected,
                        "actual": payload.actual,
                        "data": event.data,
                    })
                else:
                    errors_to_fix.append({
                        "type": "test_failure",
                        "message": event.error_message or "Test failed",
                        "file": event.file_path,
                        "test_name": event.data.get("test_name", "unknown"),
                        "data": event.data,
                    })
            elif event.type == EventType.BUILD_FAILED:
                if event.typed and isinstance(event.typed, BuildFailurePayload):
                    payload = event.typed
                    errors_to_fix.append({
                        "type": "build_failure",
                        "message": event.error_message or "Build failed",
                        "file": event.file_path,
                        "error_count": payload.error_count,
                        "is_type_error": payload.is_type_error,
                        "is_import_error": payload.is_import_error,
                        "affected_files": payload.affected_files,
                        "likely_causes": payload.likely_causes,
                        "data": event.data,
                    })
                else:
                    errors_to_fix.append({
                        "type": "build_failure",
                        "message": event.error_message or "Build failed",
                        "file": event.file_path,
                        "data": event.data,
                    })
            elif event.type == EventType.VALIDATION_ERROR:
                errors_to_fix.append({
                    "type": "validation_error",
                    "message": event.error_message or "Validation error",
                    "file": event.file_path,
                    "data": event.data,
                })
            elif event.type == EventType.TYPE_ERROR:
                if event.typed and isinstance(event.typed, TypeErrorPayload):
                    payload = event.typed
                    errors_to_fix.append({
                        "type": "type_error",
                        "message": event.error_message or "Type error",
                        "file": event.file_path,
                        "error_count": payload.error_count,
                        "errors_by_file": payload.errors_by_file,
                        "missing_types": payload.missing_types,
                        "type_mismatches": payload.type_mismatches,
                        "data": event.data,
                    })
                else:
                    errors_to_fix.append({
                        "type": "type_error",
                        "message": event.error_message or "Type error",
                        "file": event.file_path,
                        "line": event.data.get("line"),
                        "data": event.data,
                    })
            elif event.type == EventType.MOCK_DETECTED:
                if event.typed and isinstance(event.typed, MockViolationPayload):
                    violations = event.typed.violations
                else:
                    violations = event.data.get("violations", [])
                for violation in violations:
                    errors_to_fix.append({
                        "type": "mock_violation",
                        "message": f"MOCK DETECTED: {violation.get('message', 'Unknown mock pattern')}",
                        "file": violation.get("file"),
                        "line": violation.get("line"),
                        "suggested_fix": violation.get("suggested_fix", "Replace mock with real implementation"),
                        "data": {"code": violation.get("code"), "is_mock_violation": True, "priority": "critical"},
                    })
            elif event.type == EventType.DATABASE_SCHEMA_FAILED:
                errors_to_fix.append({
                    "type": "database_schema_failure",
                    "message": event.error_message or "Database schema generation failed",
                    "file": event.file_path,
                    "data": {"db_type": event.data.get("db_type", "prisma"), "is_backend_failure": True, "priority": "high"},
                })
            elif event.type == EventType.API_GENERATION_FAILED:
                errors_to_fix.append({
                    "type": "api_generation_failure",
                    "message": event.error_message or "API route generation failed",
                    "file": event.file_path,
                    "data": {"api_framework": event.data.get("api_framework", "nextjs"), "is_backend_failure": True, "priority": "high"},
                })
            elif event.type == EventType.AUTH_SETUP_FAILED:
                errors_to_fix.append({
                    "type": "auth_setup_failure",
                    "message": event.error_message or "Authentication setup failed",
                    "file": event.file_path,
                    "data": {"auth_type": event.data.get("auth_type", "jwt"), "is_backend_failure": True, "priority": "high"},
                })
            elif event.type == EventType.ENV_CONFIG_FAILED:
                errors_to_fix.append({
                    "type": "env_config_failure",
                    "message": event.error_message or "Environment/infrastructure configuration failed",
                    "file": event.file_path,
                    "data": {"is_backend_failure": True, "priority": "high"},
                })
        return errors_to_fix

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy: Generate or fix code based on events using ClaudeCodeTool.

        Collects all error information and creates a comprehensive fix prompt.
        """
        import time
        self._last_fix_time = time.time()

        # Mark generator as pending so orchestrator can wait
        await self.shared_state.set_generator_pending(True)

        try:
            # Collect all errors to fix
            errors_to_fix = self._collect_errors_from_events(events)

            # Also include errors from debug reports
            debug_report_ids = []
            for report in self._pending_debug_reports:
                debug_report_ids.append(report.id)
                # Add visual issues as errors
                for issue in report.visual_issues:
                    errors_to_fix.append({
                        "type": "visual_issue",
                        "message": issue.description,
                        "file": issue.element,
                        "severity": issue.severity,
                        "data": {"expected": issue.expected, "actual": issue.actual},
                    })
                # Add suggested fixes
                for fix in report.suggested_fixes:
                    errors_to_fix.append({
                        "type": "debug_report_fix",
                        "message": fix.description,
                        "file": fix.file,
                        "action": fix.action,
                        "data": {"priority": fix.priority},
                    })
                # Add root cause if available
                if report.root_cause_hypothesis:
                    errors_to_fix.append({
                        "type": "root_cause",
                        "message": report.root_cause_hypothesis,
                        "file": None,
                        "data": {"affected_files": report.affected_files},
                    })

            # Clear pending debug reports
            self._pending_debug_reports = []

            # Also include tasks from quality reports
            quality_report_ids = []
            quality_tasks = []
            for report in self._pending_quality_reports:
                quality_report_ids.append(report.id)

                # Add documentation tasks
                for task in report.documentation_tasks:
                    quality_tasks.append({
                        "type": "documentation_task",
                        "task_type": task.task_type,
                        "message": task.description,
                        "file": task.target_path,
                        "scope": task.scope,
                        "priority": task.priority,
                    })

                # Add cleanup tasks (only high confidence)
                for task in report.cleanup_tasks:
                    if task.confidence >= 0.9:
                        quality_tasks.append({
                            "type": "cleanup_task",
                            "message": f"Remove unused file: {task.file_path}",
                            "file": task.file_path,
                            "reason": task.reason,
                            "confidence": task.confidence,
                        })

                # Add refactor tasks
                for task in report.refactor_tasks:
                    quality_tasks.append({
                        "type": "refactor_task",
                        "message": task.description,
                        "file": task.file_path,
                        "current_lines": task.current_lines,
                        "suggested_splits": task.suggested_splits,
                    })

            # Clear pending quality reports
            self._pending_quality_reports = []

            # If we only have quality tasks, handle them separately
            if quality_tasks and not errors_to_fix:
                result = await self._handle_quality_tasks(quality_tasks, quality_report_ids)
                return result

            # Add quality tasks to errors if we have both
            errors_to_fix.extend(quality_tasks)

            if not errors_to_fix:
                return None

            # Search memory for similar error fixes with intelligent reranking
            similar_fixes = []
            if self.memory_tool and self.memory_tool.enabled:
                for error in errors_to_fix[:3]:  # Search for first 3 errors
                    try:
                        patterns = await self.memory_tool.search_similar_errors(
                            error_type=error["type"],
                            error_message=error["message"][:200],
                            project_type=self._detect_project_type(),
                            limit=5,  # Increased from 2 to 5 for better scoring
                            rerank=True  # Enable reranking for deeper semantic understanding
                        )
                        if patterns:
                            similar_fixes.extend(patterns)
                            self.logger.info(
                                "found_similar_fixes_in_memory",
                                error_type=error["type"],
                                matches=len(patterns),
                                top_confidence=patterns[0].confidence if patterns else 0
                            )
                            # Emit PATTERN_RETRIEVED event
                            await self.event_bus.publish(Event(
                                type=EventType.PATTERN_RETRIEVED,
                                source=self.name,
                                data=PatternRetrievedPayload(
                                    query=error["message"][:200],
                                    matches_found=len(patterns),
                                    top_match_confidence=patterns[0].confidence if patterns else 0.0,
                                    pattern_type="error_fix",
                                    used_by_agent=self.name,
                                ).to_dict(),
                            ))
                    except Exception as e:
                        self.logger.warning("memory_search_failed", error=str(e))

            # Build fix prompt with PromptHints from events
            prompt = self._build_fix_prompt(errors_to_fix, similar_fixes, events=events)

            self.logger.info(
                "generating_fix",
                error_count=len(errors_to_fix),
                error_types=[e["type"] for e in errors_to_fix],
                memory_hints=len(similar_fixes),
                has_prompt_hints=any(e.prompt_hints for e in events),
            )

            # Execute code generation
            result = await self.tool.execute(
                prompt=prompt,
                context=self._get_error_context(errors_to_fix),
                agent_type="general",
            )

            if result.success:
                # Update shared state
                await self.shared_state.record_fix(len(result.files))

                # Clear stuck state since we made progress
                await self.shared_state.clear_stuck_state()

                # Check if we fixed mock violations - publish MOCK_REPLACED event
                mock_violations_fixed = [
                    e for e in errors_to_fix
                    if e.get("data", {}).get("is_mock_violation")
                ]
                if mock_violations_fixed:
                    self.logger.info(
                        "mock_violations_replaced",
                        count=len(mock_violations_fixed),
                    )
                    await self.event_bus.publish(mock_replaced_event(
                        source=self.name,
                        violations_fixed=len(mock_violations_fixed),
                        files_modified=[f.path for f in result.files],
                    ))

                # Store successful fix in memory
                if self.memory_tool and self.memory_tool.enabled:
                    try:
                        # Get iteration from shared state
                        iteration = getattr(self.shared_state, 'iteration', 0)

                        # Store each error fix
                        for error in errors_to_fix[:3]:  # Store first 3 fixes
                            await self.memory_tool.store_error_fix(
                                error_type=error["type"],
                                error_message=error["message"][:300],
                                fix_description=result.output[:500] if result.output else "Fix applied successfully",
                                files_modified=[f.path for f in result.files],
                                project_type=self._detect_project_type(),
                                project_name=os.path.basename(self.working_dir),
                                iteration=iteration,
                                success=True
                            )
                        self.logger.info("stored_fix_in_memory", fixes=len(errors_to_fix[:3]))

                        # Emit PATTERN_LEARNED event for each stored fix
                        for error in errors_to_fix[:3]:
                            await self.event_bus.publish(pattern_learned_event(
                                source=self.name,
                                pattern_type="error_fix",
                                pattern_key=f"{error['type']}:{error['message'][:80]}",
                                confidence=0.8,
                                metadata={
                                    "error_type": error["type"],
                                    "files_modified": [f.path for f in result.files],
                                    "project_type": self._detect_project_type(),
                                    "iteration": iteration,
                                },
                            ))
                    except Exception as e:
                        self.logger.warning("memory_store_failed", error=str(e))

                # Publish file events for each generated file
                for gen_file in result.files:
                    await self.event_bus.publish(file_modified_event(
                        source=self.name,
                        file_path=gen_file.path,
                        language=gen_file.language,
                    ))

                # Write IMPLEMENTATION_PLAN and mark debug reports as consumed
                impl_plan_id = None
                if self.document_registry and debug_report_ids:
                    impl_plan_id = await self._write_implementation_plan(
                        debug_report_ids=debug_report_ids,
                        errors_fixed=errors_to_fix,
                        files_modified=[f.path for f in result.files],
                        output=result.output,
                    )

                    # Mark debug reports as consumed
                    for doc_id in debug_report_ids:
                        await self.document_registry.mark_consumed(doc_id, "Generator")

                # Clear processed events
                self._pending_events.clear()

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    attempted=len(errors_to_fix),
                    files_modified=len(result.files),
                )
            else:
                self.logger.error("fix_generation_failed", error=result.error)
                return recovery_failed_event(
                    source=self.name,
                    error=result.error,
                    attempted=len(errors_to_fix),
                )

        except Exception as e:
            self.logger.error("fix_execution_error", error=str(e))
            return recovery_failed_event(
                source=self.name,
                error=str(e),
            )
        finally:
            # Always clear pending state when done
            await self.shared_state.set_generator_pending(False)

    def _build_fix_prompt(
        self,
        errors: list[dict],
        similar_fixes: list = None,
        events: list[Event] = None,
    ) -> str:
        """
        Build a comprehensive fix prompt from errors.

        Args:
            errors: List of error dictionaries to fix
            similar_fixes: Optional similar fixes from memory
            events: Optional list of source events for PromptHints

        Returns:
            Formatted prompt string with hints prepended
        """
        lines = []

        # Phase 11: Prepend PromptHints from events
        if events:
            merged_hints = merge_hints_from_events(events)
            if merged_hints and not merged_hints.is_empty():
                lines.append(merged_hints.to_prompt_section())
                lines.append("---\n")

        lines.append("Fix the following issues in the codebase:\n")

        for i, error in enumerate(errors, 1):
            error_type = error["type"].replace("_", " ").title()
            lines.append(f"\n{i}. {error_type}:")
            lines.append(f"   Message: {error['message']}")
            if error.get("file"):
                lines.append(f"   File: {error['file']}")
            if error.get("line"):
                lines.append(f"   Line: {error['line']}")
            if error.get("test_name"):
                lines.append(f"   Test: {error['test_name']}")

        # Add similar fixes from memory as hints with confidence scores
        if similar_fixes:
            lines.append("\n\nContext from similar past fixes:")
            # Sort by confidence and take top 3
            sorted_fixes = sorted(similar_fixes, key=lambda x: x.confidence, reverse=True)
            for i, fix in enumerate(sorted_fixes[:3], 1):  # Top 3 fixes
                lines.append(f"{i}. {fix.error_type}: {fix.fix_description}")
                if fix.files_modified:
                    lines.append(f"   Files modified: {', '.join(fix.files_modified[:2])}")
                lines.append(f"   Confidence: {fix.confidence:.2f}")

        # FIX-27: Add technology-specific instructions based on tech_stack
        if self.tech_stack:
            lines.append("\n\n## Technology Stack Requirements:")
            
            if hasattr(self.tech_stack, 'frontend_framework') and self.tech_stack.frontend_framework:
                frontend = self.tech_stack.frontend_framework.lower()
                lines.append(f"\n### Frontend: {self.tech_stack.frontend_framework}")
                
                if 'react' in frontend:
                    lines.append("- Use React functional components with hooks")
                    lines.append("- Use TypeScript (.tsx files) for type safety")
                    lines.append("- Place components in src/components/")
                    lines.append("- Use React.FC<Props> for component typing")
                elif 'vue' in frontend:
                    lines.append("- Use Vue 3 Composition API with <script setup>")
                    lines.append("- Use TypeScript for type safety")
                    lines.append("- Place components in src/components/")
                elif 'angular' in frontend:
                    lines.append("- Use Angular standalone components")
                    lines.append("- Use TypeScript with strict mode")
                    lines.append("- Follow Angular style guide")
                elif 'svelte' in frontend:
                    lines.append("- Use Svelte components (.svelte files)")
                    lines.append("- Use TypeScript in <script lang='ts'>")
            
            if hasattr(self.tech_stack, 'backend_framework') and self.tech_stack.backend_framework:
                backend = self.tech_stack.backend_framework.lower()
                lines.append(f"\n### Backend: {self.tech_stack.backend_framework}")
                
                if 'fastapi' in backend:
                    lines.append("- Use FastAPI with Pydantic models")
                    lines.append("- Place routes in src/api/routes/")
                    lines.append("- Use async/await for endpoints")
                    lines.append("- Add proper type hints")
                elif 'flask' in backend:
                    lines.append("- Use Flask blueprints for routes")
                    lines.append("- Use Flask-SQLAlchemy for database")
                elif 'django' in backend:
                    lines.append("- Use Django REST framework for APIs")
                    lines.append("- Follow Django project structure")
                elif 'express' in backend or 'node' in backend:
                    lines.append("- Use Express.js with TypeScript")
                    lines.append("- Use async/await for routes")
            
            if hasattr(self.tech_stack, 'styling_framework') and self.tech_stack.styling_framework:
                styling = self.tech_stack.styling_framework.lower()
                lines.append(f"\n### Styling: {self.tech_stack.styling_framework}")
                
                if 'tailwind' in styling:
                    lines.append("- Use Tailwind CSS utility classes")
                    lines.append("- Avoid custom CSS where Tailwind suffices")
                elif 'bootstrap' in styling:
                    lines.append("- Use Bootstrap classes and components")
                elif 'mui' in styling or 'material' in styling:
                    lines.append("- Use MUI components and sx prop for styling")
            
            if hasattr(self.tech_stack, 'database_name') and self.tech_stack.database_name:
                lines.append(f"\n### Database: {self.tech_stack.database_name}")
                
            if hasattr(self.tech_stack, 'platform') and self.tech_stack.platform:
                platform = self.tech_stack.platform.lower()
                if 'electron' in platform:
                    lines.append("\n### Platform: Electron")
                    lines.append("- Separate main and renderer processes")
                    lines.append("- Use IPC for process communication")
                    lines.append("- Follow electron security best practices")

        # Rich Context: Design Tokens from RichContextProvider for frontend consistency
        if hasattr(self.shared_state, 'context_provider') and self.shared_state.context_provider:
            try:
                if hasattr(self.shared_state.context_provider, 'for_frontend_agent'):
                    fe_context = self.shared_state.context_provider.for_frontend_agent()

                    # Include design tokens for UI consistency
                    if fe_context.design_tokens:
                        tokens = fe_context.design_tokens
                        lines.append("\n\n## Design System")
                        lines.append("Use these design tokens for consistent UI styling:\n")

                        # Colors
                        if tokens.get("colors"):
                            colors = tokens["colors"]
                            lines.append("### Colors")
                            if colors.get("primary"):
                                lines.append(f"- Primary: `{colors['primary']}`")
                            if colors.get("secondary"):
                                lines.append(f"- Secondary: `{colors['secondary']}`")
                            if colors.get("background"):
                                lines.append(f"- Background: `{colors['background']}`")
                            if colors.get("text"):
                                lines.append(f"- Text: `{colors['text']}`")
                            if colors.get("success"):
                                lines.append(f"- Success: `{colors['success']}`")
                            if colors.get("error"):
                                lines.append(f"- Error: `{colors['error']}`")

                        # Typography
                        if tokens.get("typography"):
                            typo = tokens["typography"]
                            lines.append("\n### Typography")
                            if typo.get("font_family"):
                                lines.append(f"- Font Family: `{typo['font_family']}`")
                            if typo.get("heading_sizes"):
                                lines.append(f"- Headings: {typo['heading_sizes']}")

                        # Spacing
                        if tokens.get("spacing"):
                            spacing = tokens["spacing"]
                            lines.append("\n### Spacing")
                            for key, value in list(spacing.items())[:5]:
                                lines.append(f"- {key}: `{value}`")

                        # Breakpoints
                        if tokens.get("breakpoints"):
                            bp = tokens["breakpoints"]
                            lines.append("\n### Breakpoints (Responsive)")
                            for key, value in list(bp.items())[:4]:
                                lines.append(f"- {key}: `{value}`")

                        lines.append("")
                        self.logger.debug("design_tokens_injected", has_colors=bool(tokens.get("colors")))
            except Exception as e:
                self.logger.debug("design_tokens_extraction_failed", error=str(e))

        # NEW: Inject RAG context from AgentContextBridge for code patterns
        if hasattr(self, '_design_context') and self._design_context:
            rag_results = self._design_context.get("rag_results", [])
            if rag_results:
                lines.append("\n\n## Relevant Code Examples (from RAG)")
                lines.append("Use these as reference for patterns and conventions:\n")
                for result in rag_results[:3]:  # Top 3 RAG results
                    file_path = result.get("relative_path", result.get("file_path", "unknown"))
                    content = result.get("content", "")[:600]  # Truncate long content
                    score = result.get("score", 0)
                    lines.append(f"### {file_path} (relevance: {score:.2f})")
                    lines.append(f"```\n{content}\n```")
                self.logger.debug("rag_context_injected", rag_results_count=len(rag_results))

        # Check for mock violations - add critical instructions
        mock_violations = [e for e in errors if e.get("data", {}).get("is_mock_violation")]
        if mock_violations:
            lines.append("\n\n## ⚠️ CRITICAL: MOCK VIOLATIONS DETECTED")
            lines.append("The following mock patterns MUST be replaced with REAL implementations:")
            for violation in mock_violations:
                lines.append(f"\n- File: {violation.get('file')}")
                lines.append(f"  Issue: {violation.get('message')}")
                if violation.get("suggested_fix"):
                    lines.append(f"  Fix: {violation['suggested_fix']}")

            lines.append("\n### NO-MOCK POLICY:")
            lines.append("You MUST NOT generate:")
            lines.append("- Hardcoded data arrays (const users = [{...}])")
            lines.append("- TODO/FIXME placeholders")
            lines.append("- Mock success returns (return { success: true })")
            lines.append("- Fake tokens or credentials")
            lines.append("- In-memory Maps/Objects as database substitutes")
            lines.append("\nYou MUST generate:")
            lines.append("- Real Prisma/database queries")
            lines.append("- Real API calls with fetch/axios")
            lines.append("- Real JWT token generation (jwt.sign)")
            lines.append("- Environment variables for secrets")

        lines.append("\n\nPlease analyze these errors and fix all of them.")
        lines.append("Make sure to:")
        lines.append("1. Address the root cause, not just the symptoms")
        lines.append("2. Maintain existing functionality")
        lines.append("3. Follow the project's coding style")
        if self.tech_stack:
            lines.append("4. Adhere to the technology stack requirements above")
        if mock_violations:
            lines.append("5. CRITICAL: Replace ALL mock patterns with real implementations")

        return "\n".join(lines)

    def _detect_project_type(self) -> str:
        """Detect project type from working directory."""
        # Simple detection based on file existence
        if os.path.exists(os.path.join(self.working_dir, "package.json")):
            if os.path.exists(os.path.join(self.working_dir, "electron.vite.config.ts")):
                return "electron-vite"
            elif os.path.exists(os.path.join(self.working_dir, "electron-builder.yml")):
                return "electron"
            return "node"
        elif os.path.exists(os.path.join(self.working_dir, "requirements.txt")):
            return "python"
        elif os.path.exists(os.path.join(self.working_dir, "Cargo.toml")):
            return "rust"
        return "unknown"

    def _get_error_context(self, errors: list[dict]) -> str:
        """Build context string from errors."""
        files_mentioned = set()
        for error in errors:
            if error.get("file"):
                files_mentioned.add(error["file"])

        if files_mentioned:
            return f"Files involved: {', '.join(sorted(files_mentioned))}"
        return ""

    async def _write_implementation_plan(
        self,
        debug_report_ids: list[str],
        errors_fixed: list[dict],
        files_modified: list[str],
        output: Optional[str],
    ) -> Optional[str]:
        """
        Write an IMPLEMENTATION_PLAN document to the registry.

        Args:
            debug_report_ids: IDs of debug reports being addressed
            errors_fixed: List of errors that were fixed
            files_modified: List of files that were modified
            output: Output from the fix generation

        Returns:
            Document ID if written successfully
        """
        if not self.document_registry:
            return None

        try:
            from uuid import uuid4
            from datetime import datetime

            timestamp = datetime.now()
            doc_id = f"impl_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

            # Create planned fixes from errors
            fixes_planned = []
            for i, error in enumerate(errors_fixed):
                fixes_planned.append(PlannedFix(
                    id=f"pfix_{i+1:03d}",
                    description=error.get("message", "Fix applied"),
                    responding_to_fix_id=error.get("data", {}).get("fix_id"),
                    approach=error.get("type"),
                    estimated_complexity="medium",
                ))

            # Create file change manifest
            file_manifest = {}
            for file_path in files_modified:
                file_manifest[file_path] = FileChange(
                    action="modified",
                    summary="Changes applied",
                )

            # Determine test focus areas from errors
            test_focus_areas = []
            for error in errors_fixed:
                if error.get("file"):
                    test_focus_areas.append(f"Verify {error.get('file')}")
                if error.get("type") == "visual_issue":
                    test_focus_areas.append("Visual regression tests")
                if error.get("type") == "test_failure":
                    test_focus_areas.append(f"Re-run test: {error.get('test_name', 'all')}")

            # Create the implementation plan
            impl_plan = ImplementationPlan(
                id=doc_id,
                timestamp=timestamp,
                source_agent=self.name,
                responding_to=debug_report_ids[0] if debug_report_ids else None,
                fixes_planned=fixes_planned,
                file_manifest=file_manifest,
                test_focus_areas=list(set(test_focus_areas))[:10],  # Dedupe and limit
                expected_outcomes=[
                    "Build passes",
                    "Visual issues resolved",
                    "No new errors introduced",
                ],
                verification_steps=[
                    "Run build",
                    "Run visual E2E tests",
                    "Verify affected components",
                ],
                summary=output[:500] if output else "Fixes applied successfully",
                total_files_changed=len(files_modified),
            )

            # Write to registry
            await self.document_registry.write_document(impl_plan, priority=5)

            # Publish event
            await self.event_bus.publish(implementation_plan_created_event(
                source=self.name,
                doc_id=doc_id,
                files_changed=len(files_modified),
                fixes_planned=len(fixes_planned),
                responding_to=debug_report_ids,
            ))

            self.logger.info(
                "implementation_plan_written",
                doc_id=doc_id,
                files_changed=len(files_modified),
                fixes_planned=len(fixes_planned),
            )

            return doc_id

        except Exception as e:
            self.logger.error("implementation_plan_write_failed", error=str(e))
            return None

    async def _handle_quality_tasks(
        self,
        quality_tasks: list[dict],
        quality_report_ids: list[str],
    ) -> Optional[Event]:
        """
        Handle quality improvement tasks (documentation, cleanup, refactoring).

        This is called when we only have quality tasks and no error fixes.

        Args:
            quality_tasks: List of quality improvement tasks
            quality_report_ids: IDs of quality reports being addressed

        Returns:
            Event describing the result
        """
        self.logger.info(
            "handling_quality_tasks",
            task_count=len(quality_tasks),
            quality_report_ids=quality_report_ids,
        )

        # Build a quality-focused prompt
        prompt = self._build_quality_prompt(quality_tasks)

        try:
            result = await self.tool.execute(
                prompt=prompt,
                context=self._get_quality_context(quality_tasks),
                agent_type="general",
            )

            if result.success:
                # Update shared state
                await self.shared_state.record_fix(len(result.files))

                # Publish file events
                for gen_file in result.files:
                    await self.event_bus.publish(file_modified_event(
                        source=self.name,
                        file_path=gen_file.path,
                        language=gen_file.language,
                        quality_task=True,
                    ))

                # Mark quality reports as consumed
                if self.document_registry:
                    for doc_id in quality_report_ids:
                        await self.document_registry.mark_consumed(doc_id, "Generator")

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    attempted=len(quality_tasks),
                    files_modified=len(result.files),
                )
            else:
                self.logger.error("quality_task_failed", error=result.error)
                return code_fixed_event(
                    source=self.name,
                    success=False,
                    attempted=len(quality_tasks),
                    error=result.error,
                )

        except Exception as e:
            self.logger.error("quality_task_error", error=str(e))
            return recovery_failed_event(
                source=self.name,
                error=str(e),
            )

    def _build_quality_prompt(self, tasks: list[dict]) -> str:
        """Build a prompt for quality improvement tasks."""
        lines = ["Perform the following code quality improvements:\n"]

        # Group tasks by type
        doc_tasks = [t for t in tasks if t["type"] == "documentation_task"]
        cleanup_tasks = [t for t in tasks if t["type"] == "cleanup_task"]
        refactor_tasks = [t for t in tasks if t["type"] == "refactor_task"]

        if doc_tasks:
            lines.append("\n## Documentation Tasks")
            for i, task in enumerate(doc_tasks, 1):
                lines.append(f"\n{i}. {task['message']}")
                lines.append(f"   Target: {task['file']}")
                if task.get("task_type"):
                    lines.append(f"   Type: {task['task_type']}")
                if task.get("scope"):
                    lines.append(f"   Scope: {', '.join(task['scope'][:5])}")

        if cleanup_tasks:
            lines.append("\n## Cleanup Tasks (CAUTION - verify before deleting)")
            for i, task in enumerate(cleanup_tasks, 1):
                lines.append(f"\n{i}. {task['message']}")
                lines.append(f"   Reason: {task['reason']}")
                lines.append(f"   Confidence: {task['confidence']:.0%}")

        if refactor_tasks:
            lines.append("\n## Refactoring Tasks")
            for i, task in enumerate(refactor_tasks, 1):
                lines.append(f"\n{i}. {task['message']}")
                lines.append(f"   File: {task['file']}")
                lines.append(f"   Current lines: {task['current_lines']}")
                if task.get("suggested_splits"):
                    lines.append(f"   Suggested splits: {', '.join(task['suggested_splits'][:3])}")

        lines.append("\n\nPlease:")
        lines.append("1. For documentation tasks: Create comprehensive, well-structured documentation")
        lines.append("2. For cleanup tasks: VERIFY the file is truly unused before removing")
        lines.append("3. For refactoring: Split large files logically, maintaining all functionality")

        return "\n".join(lines)

    def _get_quality_context(self, tasks: list[dict]) -> str:
        """Build context string from quality tasks."""
        files_mentioned = set()
        for task in tasks:
            if task.get("file"):
                files_mentioned.add(task["file"])
            if task.get("scope"):
                files_mentioned.update(task["scope"][:5])

        if files_mentioned:
            return f"Files involved: {', '.join(sorted(files_mentioned)[:10])}"
        return ""


async def create_generator_agent(
    event_bus: EventBus,
    shared_state: SharedState,
    working_dir: str,
) -> GeneratorAgent:
    """Create and start a GeneratorAgent."""
    agent = GeneratorAgent(
        name="Generator",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
    )
    await agent.start()
    return agent
