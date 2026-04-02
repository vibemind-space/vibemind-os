# -*- coding: utf-8 -*-
"""
Fungus Validation Agent - Phase 17

Autonomous agent that runs MCMP simulation for continuous code validation
during epic generation. Subscribes to epic lifecycle events, indexes the
codebase as it grows, and uses a validation-oriented Judge LLM to produce
structured findings. High-confidence findings are bridged to standard
CODE_FIX_NEEDED events so existing agents (GeneratorAgent, BugFixerAgent)
can react.

Event lifecycle:
    EPIC_EXECUTION_STARTED  -> Start service, index codebase
    EPIC_TASK_COMPLETED     -> Re-index new files, run validation if threshold met
    EPIC_TASK_FAILED        -> Deep validation focused on error context
    BUILD_FAILED / TYPE_ERROR -> Repair-mode validation
    EPIC_EXECUTION_COMPLETED -> Stop service, publish final report

Publishes:
    FUNGUS_VALIDATION_STARTED  -> Service initialized
    FUNGUS_VALIDATION_ISSUE    -> Per-finding (finding_type, severity, file, confidence)
    FUNGUS_VALIDATION_PASSED   -> File/component validated OK
    FUNGUS_VALIDATION_REPORT   -> Aggregated round summary
    FUNGUS_VALIDATION_STOPPED  -> Service stopped, final stats
    CODE_FIX_NEEDED            -> For high-confidence error findings (bridge to existing agents)
"""
import asyncio
from typing import Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class FungusValidationAgent(AutonomousAgent):
    """
    Autonomous validation agent using MCMP (Mycelial Collective Pheromone Search).

    Runs Fungus simulation continuously during epic generation, re-indexing
    the codebase as files are generated and validating code patterns via
    a Judge LLM.
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        validation_interval: int = 10,
        min_files_for_validation: int = 5,
        auto_fix_threshold: float = 0.8,
        seed_patterns: Optional[dict] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self._validation_interval = validation_interval
        self._min_files = min_files_for_validation
        self._auto_fix_threshold = auto_fix_threshold
        self._seed_patterns = seed_patterns or {}

        # Runtime state
        self._validation_service = None
        self._epic_active = False
        self._files_since_last_validation = 0
        self._current_epic_id: Optional[str] = None

    # ------------------------------------------------------------------
    # AutonomousAgent interface
    # ------------------------------------------------------------------

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.EPIC_EXECUTION_STARTED,
            EventType.EPIC_TASK_COMPLETED,
            EventType.EPIC_TASK_FAILED,
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.CODE_GENERATED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
        ]

    async def should_act(self, events: list) -> bool:
        """Act on any subscribed event."""
        return any(e.type in self.subscribed_events for e in events)

    async def act(self, events: list) -> Optional[Event]:
        """Process events and drive validation."""
        for event in events:
            if event.source == self.name:
                continue  # Skip own events

            try:
                if event.type == EventType.EPIC_EXECUTION_STARTED:
                    await self._handle_epic_start(event)
                elif event.type == EventType.EPIC_TASK_COMPLETED:
                    await self._handle_task_completed(event)
                elif event.type == EventType.EPIC_TASK_FAILED:
                    await self._handle_task_failed(event)
                elif event.type in (EventType.FILE_CREATED, EventType.FILE_MODIFIED):
                    await self._handle_file_change(event)
                elif event.type == EventType.CODE_GENERATED:
                    await self._handle_code_generated(event)
                elif event.type in (EventType.BUILD_FAILED, EventType.TYPE_ERROR):
                    await self._handle_error_event(event)
                elif event.type == EventType.EPIC_EXECUTION_COMPLETED:
                    await self._handle_epic_end(event)
            except Exception as e:
                self.logger.warning(
                    "event_handling_error",
                    event_type=event.type.value if hasattr(event.type, "value") else str(event.type),
                    error=str(e),
                )

        return None  # We publish events directly, not via return

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    async def _handle_epic_start(self, event: Event) -> None:
        """Start validation service when an epic begins."""
        if self._epic_active:
            self.logger.warning("epic_already_active", current=self._current_epic_id)
            return

        # Lazy import to avoid circular dependencies
        from ..services.fungus_validation_service import FungusValidationService

        epic_id = event.data.get("epic_id", "unknown")
        self._current_epic_id = epic_id

        self._validation_service = FungusValidationService(
            working_dir=self.working_dir,
            event_bus=self.event_bus,
            job_id=f"validation_{epic_id}",
        )

        started = await self._validation_service.start(
            seed_patterns=self._seed_patterns,
        )

        if started:
            self._epic_active = True
            self._files_since_last_validation = 0

            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_VALIDATION_STARTED,
                source=self.name,
                data={
                    "epic_id": epic_id,
                    "files_indexed": self._validation_service.indexed_count,
                },
            ))

            self.logger.info(
                "validation_started",
                epic_id=epic_id,
                files_indexed=self._validation_service.indexed_count,
            )
        else:
            self.logger.warning("validation_start_failed", epic_id=epic_id)
            self._validation_service = None

    async def _handle_task_completed(self, event: Event) -> None:
        """On task completion, re-index and optionally validate."""
        if not self._validation_service or not self._epic_active:
            return

        task_data = event.data or {}

        # Track completed task for seed patterns
        self._validation_service.add_completed_task(task_data)

        # Re-index files from this task
        files_created = task_data.get("files_created", [])
        files_modified = task_data.get("files_modified", [])
        output_files = task_data.get("output_files", [])

        changed_count = 0
        for f in files_created + files_modified + output_files:
            if await self._validation_service.reindex_file(f):
                changed_count += 1

        self._files_since_last_validation += max(1, changed_count)

        # Run validation if threshold met
        if self._files_since_last_validation >= self._validation_interval:
            task_title = task_data.get("title", task_data.get("task_id", ""))
            task_type = task_data.get("type", "")

            query = f"validate {task_type}: {task_title}"
            await self._run_and_publish_validation(
                focus_query=query,
                task_context=task_data,
            )
            self._files_since_last_validation = 0

    async def _handle_task_failed(self, event: Event) -> None:
        """On task failure, run deep validation focused on error context."""
        if not self._validation_service or not self._epic_active:
            return

        task_data = event.data or {}
        error_msg = task_data.get("error_message", task_data.get("error", ""))
        task_type = task_data.get("type", "")

        # Track error as anti-pattern
        if error_msg:
            self._validation_service.add_failed_error(error_msg)

        # Deep validation focused on the error
        query = f"fix {task_type} error: {error_msg[:200]}"
        await self._run_and_publish_validation(
            focus_query=query,
            task_context=task_data,
        )

    async def _handle_file_change(self, event: Event) -> None:
        """Track file changes for incremental re-indexing."""
        if not self._validation_service or not self._epic_active:
            return

        file_path = event.data.get("file_path", event.file_path or "")
        if file_path:
            if await self._validation_service.reindex_file(file_path):
                self._files_since_last_validation += 1

    async def _handle_code_generated(self, event: Event) -> None:
        """On code generation, re-index generated files."""
        if not self._validation_service or not self._epic_active:
            return

        files = event.data.get("files", [])
        for f in files:
            if isinstance(f, str):
                if await self._validation_service.reindex_file(f):
                    self._files_since_last_validation += 1

    async def _handle_error_event(self, event: Event) -> None:
        """On BUILD_FAILED/TYPE_ERROR, run repair-mode validation."""
        if not self._validation_service or not self._epic_active:
            return

        error_msg = event.error_message or event.data.get("message", "")
        from ..services.fungus_validation_service import ValidationJudgeMode

        query = f"repair: {error_msg[:200]}"
        await self._run_and_publish_validation(
            focus_query=query,
            mode=ValidationJudgeMode.DEPENDENCY_CHECK,
        )

    async def _handle_epic_end(self, event: Event) -> None:
        """Stop validation service when epic completes."""
        if not self._validation_service:
            return

        reports = await self._validation_service.stop()

        total_findings = sum(len(r.findings) for r in reports)
        total_errors = sum(
            len([f for f in r.findings if f.severity == "error"])
            for r in reports
        )

        await self.event_bus.publish(Event(
            type=EventType.FUNGUS_VALIDATION_STOPPED,
            source=self.name,
            data={
                "epic_id": self._current_epic_id,
                "total_rounds": len(reports),
                "total_findings": total_findings,
                "total_errors": total_errors,
            },
        ))

        self.logger.info(
            "validation_stopped",
            epic_id=self._current_epic_id,
            rounds=len(reports),
            total_findings=total_findings,
            total_errors=total_errors,
        )

        self._epic_active = False
        self._validation_service = None
        self._current_epic_id = None

    # ------------------------------------------------------------------
    # Internal: Validation + Event Publishing
    # ------------------------------------------------------------------

    async def _run_and_publish_validation(
        self,
        focus_query: str,
        task_context: Optional[dict] = None,
        mode=None,
    ) -> None:
        """Run a validation round and publish findings as events."""
        if not self._validation_service:
            return

        from ..services.fungus_validation_service import ValidationJudgeMode

        if mode is None:
            mode = ValidationJudgeMode.PATTERN_CHECK

        report = await self._validation_service.run_validation_round(
            focus_query=focus_query,
            mode=mode,
            task_context=task_context,
        )

        # Publish individual findings
        for finding in report.findings:
            # Always publish as FUNGUS_VALIDATION_ISSUE
            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_VALIDATION_ISSUE,
                source=self.name,
                data={
                    "finding_type": finding.finding_type,
                    "severity": finding.severity,
                    "file_path": finding.file_path,
                    "related_files": finding.related_files,
                    "description": finding.description,
                    "suggested_fix": finding.suggested_fix,
                    "confidence": finding.confidence,
                },
                file_path=finding.file_path,
                success=finding.severity != "error",
            ))

            # Bridge high-confidence errors to CODE_FIX_NEEDED
            if (
                finding.severity == "error"
                and finding.confidence >= self._auto_fix_threshold
            ):
                await self.event_bus.publish(Event(
                    type=EventType.CODE_FIX_NEEDED,
                    source=self.name,
                    data={
                        "description": finding.description,
                        "file_path": finding.file_path,
                        "related_files": finding.related_files,
                        "suggested_fix": finding.suggested_fix,
                        "fungus_evidence": finding.evidence[:3],
                        "source_type": "fungus_validation",
                    },
                    file_path=finding.file_path,
                    error_message=finding.description,
                    success=False,
                ))

        # Publish aggregated report
        errors = len([f for f in report.findings if f.severity == "error"])
        warnings = len([f for f in report.findings if f.severity == "warning"])

        await self.event_bus.publish(Event(
            type=EventType.FUNGUS_VALIDATION_REPORT,
            source=self.name,
            data={
                "round": report.round_number,
                "findings_count": len(report.findings),
                "errors": errors,
                "warnings": warnings,
                "files_analyzed": report.files_analyzed,
                "files_indexed": report.files_indexed,
                "judge_confidence": report.judge_confidence,
                "focus_query": report.focus_query,
            },
            success=errors == 0,
        ))

        # If no findings, publish PASSED
        if not report.findings:
            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_VALIDATION_PASSED,
                source=self.name,
                data={
                    "round": report.round_number,
                    "focus_query": report.focus_query,
                    "files_analyzed": report.files_analyzed,
                },
            ))
