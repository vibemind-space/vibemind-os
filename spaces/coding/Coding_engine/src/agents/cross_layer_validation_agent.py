# -*- coding: utf-8 -*-
"""
Cross-Layer Validation Agent - Phase 23

Autonomous agent that validates frontend-backend consistency after epic
execution or generation completes. Uses pure static analysis (no LLM)
to detect API route mismatches, DTO divergence, security inconsistencies,
and broken imports.

Event lifecycle:
    EPIC_EXECUTION_COMPLETED  -> Run cross-layer validation on completed epic
    EPIC_PHASE_COMPLETED      -> Run after FE/API phases complete
    GENERATION_COMPLETE       -> Run after full generation pipeline

Publishes:
    CROSS_LAYER_VALIDATION_STARTED  -> Validation initialized
    CROSS_LAYER_VALIDATION_ISSUE    -> Per-finding (check_mode, severity, files)
    CROSS_LAYER_VALIDATION_COMPLETE -> Validation finished with summary
    CROSS_LAYER_VALIDATION_REPORT   -> Full alignment report
    CODE_FIX_NEEDED                 -> For CRITICAL findings (bridge to fix agents)
"""

import json
from pathlib import Path
from typing import Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class CrossLayerValidationAgent(AutonomousAgent):
    """
    Autonomous cross-layer consistency validation agent.

    Scans frontend and backend source code to detect misalignments
    between API routes, DTOs, security patterns, and imports.
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        project_dir: Optional[str] = None,
        auto_fix_critical: bool = True,
        auto_fix_threshold: float = 0.8,
        **kwargs,
    ):
        """
        Initialize the cross-layer validation agent.

        Args:
            name: Agent name
            event_bus: EventBus for pub/sub
            shared_state: Shared state singleton
            working_dir: Working directory for the agent
            project_dir: Path to generated project code directory
            auto_fix_critical: Whether to publish CODE_FIX_NEEDED for critical findings
            auto_fix_threshold: Minimum confidence to bridge to CODE_FIX_NEEDED
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self._project_dir = project_dir
        self._auto_fix_critical = auto_fix_critical
        self._auto_fix_threshold = auto_fix_threshold

        # Runtime state
        self._validation_service = None
        self._validation_running = False
        self._last_report = None

    # ------------------------------------------------------------------
    # AutonomousAgent interface
    # ------------------------------------------------------------------

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.EPIC_PHASE_COMPLETED,
            EventType.GENERATION_COMPLETE,
        ]

    async def should_act(self, events: list) -> bool:
        """Act when epic/generation completes."""
        return any(e.type in self.subscribed_events for e in events)

    async def act(self, events: list) -> Optional[Event]:
        """Process events and drive cross-layer validation."""
        for event in events:
            if event.source == self.name:
                continue

            try:
                if event.type == EventType.EPIC_EXECUTION_COMPLETED:
                    await self._handle_epic_completed(event)
                elif event.type == EventType.EPIC_PHASE_COMPLETED:
                    await self._handle_phase_completed(event)
                elif event.type == EventType.GENERATION_COMPLETE:
                    await self._handle_generation_complete(event)
            except Exception as e:
                self.logger.error(
                    "event_handling_error",
                    event_type=event.type.value,
                    error=str(e),
                )

        return None

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    async def _handle_epic_completed(self, event: Event) -> None:
        """Run full cross-layer validation after epic execution completes."""
        project_dir = self._resolve_project_dir(event)
        if not project_dir:
            self.logger.warning("no_project_dir", msg="Cannot determine project directory")
            return

        await self._run_validation(project_dir, trigger="epic_completed")

    async def _handle_phase_completed(self, event: Event) -> None:
        """Run validation after specific phases (API/FE) complete."""
        phase = event.data.get("phase", "")
        # Only run after API or frontend phases
        if phase not in ("api", "frontend", "fe", "api_generation", "code_generation"):
            return

        project_dir = self._resolve_project_dir(event)
        if not project_dir:
            return

        await self._run_validation(project_dir, trigger=f"phase_{phase}")

    async def _handle_generation_complete(self, event: Event) -> None:
        """Run validation after full generation pipeline completes."""
        project_dir = self._resolve_project_dir(event)
        if not project_dir:
            return

        await self._run_validation(project_dir, trigger="generation_complete")

    # ------------------------------------------------------------------
    # Core Validation
    # ------------------------------------------------------------------

    async def _run_validation(self, project_dir: str, trigger: str) -> None:
        """Run the full cross-layer validation."""
        if self._validation_running:
            self.logger.info("validation_already_running")
            return

        self._validation_running = True

        try:
            from ..services.cross_layer_validation_service import (
                CrossLayerCheckMode,
                CrossLayerValidationService,
                FindingSeverity,
            )

            # Publish start event
            await self.event_bus.publish(Event(
                type=EventType.CROSS_LAYER_VALIDATION_STARTED,
                source=self.name,
                data={"project_dir": project_dir, "trigger": trigger},
            ))

            # Initialize service
            self._validation_service = CrossLayerValidationService(
                project_dir=project_dir,
                event_bus=self.event_bus,
            )

            started = await self._validation_service.start()
            if not started:
                self.logger.warning("validation_start_failed")
                return

            # Run full cross-layer validation
            report = await self._validation_service.run_validation(
                mode=CrossLayerCheckMode.FULL,
            )
            self._last_report = report

            # Publish individual findings
            for finding in report.findings:
                await self.event_bus.publish(Event(
                    type=EventType.CROSS_LAYER_VALIDATION_ISSUE,
                    source=self.name,
                    data=finding.to_dict(),
                ))

                # Bridge critical findings to CODE_FIX_NEEDED
                if (
                    self._auto_fix_critical
                    and finding.severity == FindingSeverity.CRITICAL
                    and finding.confidence >= self._auto_fix_threshold
                ):
                    await self.event_bus.publish(Event(
                        type=EventType.CODE_FIX_NEEDED,
                        source=self.name,
                        data={
                            "reason": finding.description,
                            "source_analysis": "cross_layer_validation",
                            "check_mode": finding.check_mode.value if hasattr(finding.check_mode, 'value') else str(finding.check_mode),
                            "frontend_file": finding.frontend_file,
                            "backend_file": finding.backend_file,
                            "suggestion": finding.suggestion,
                            "confidence": finding.confidence,
                        },
                    ))

            # Publish completion event
            await self.event_bus.publish(Event(
                type=EventType.CROSS_LAYER_VALIDATION_COMPLETE,
                source=self.name,
                data={
                    "alignment_score": report.alignment_score,
                    "total_findings": len(report.findings),
                    "critical_count": sum(1 for f in report.findings if f.severity == FindingSeverity.CRITICAL),
                    "high_count": sum(1 for f in report.findings if f.severity == FindingSeverity.HIGH),
                    "routes_checked": report.routes_checked,
                    "routes_aligned": report.routes_aligned,
                    "dtos_checked": report.dtos_checked,
                    "dtos_aligned": report.dtos_aligned,
                    "security_issues": report.security_issues,
                    "import_issues": report.import_issues,
                    "trigger": trigger,
                },
            ))

            # Update SharedState for convergence (Phase 27)
            if self.shared_state:
                critical_count = sum(
                    1 for f in report.findings
                    if f.severity == FindingSeverity.CRITICAL
                )
                await self.shared_state.update_cross_layer(
                    issues=len(report.findings),
                    critical_issues=critical_count,
                )

            # Publish full report
            await self.event_bus.publish(Event(
                type=EventType.CROSS_LAYER_VALIDATION_REPORT,
                source=self.name,
                data=report.to_dict(),
            ))

            self.logger.info(
                "cross_layer_validation_complete",
                alignment=f"{report.alignment_score:.1f}%",
                findings=len(report.findings),
                critical=sum(1 for f in report.findings if f.severity == FindingSeverity.CRITICAL),
            )

        except Exception as e:
            self.logger.error("validation_error", error=str(e))
        finally:
            self._validation_running = False

            if self._validation_service:
                try:
                    await self._validation_service.stop()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_project_dir(self, event: Event) -> Optional[str]:
        """Resolve the project directory from event or config."""
        if self._project_dir:
            return self._project_dir

        # Try from event data
        for key in ("project_dir", "output_dir", "code_dir"):
            val = event.data.get(key, "")
            if val and Path(val).exists():
                return val

        # Convention: working_dir/output or working_dir/src
        working = Path(self.working_dir)
        if (working / "output" / "src").exists():
            return str(working / "output")
        if (working / "src").exists():
            return str(working)

        return None
