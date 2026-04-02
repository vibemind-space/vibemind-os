# -*- coding: utf-8 -*-
"""
Differential Analysis Agent - Phase 20

Autonomous agent that compares documentation/requirements against generated
code to identify implementation gaps. Subscribes to epic lifecycle events
and publishes gap findings so other agents can react (e.g., GeneratorAgent
creates missing implementations).

Event lifecycle:
    EPIC_EXECUTION_COMPLETED  -> Run differential analysis on the completed epic
    GENERATION_COMPLETE       -> Run analysis after full generation pipeline
    CONVERGENCE_ACHIEVED      -> Final coverage report

Publishes:
    DIFFERENTIAL_ANALYSIS_STARTED   -> Analysis initialized
    DIFFERENTIAL_GAP_FOUND          -> Per-gap finding (requirement_id, severity, status)
    DIFFERENTIAL_ANALYSIS_COMPLETE  -> Analysis finished with summary
    DIFFERENTIAL_COVERAGE_REPORT    -> Full coverage report
    CODE_FIX_NEEDED                 -> For CRITICAL missing requirements (bridge to generators)
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class DifferentialAnalysisAgent(AutonomousAgent):
    """
    Autonomous gap detection agent using MCMP differential analysis.

    Compares documentation (user stories, tasks, requirements) against
    generated code and publishes structured gap findings via EventBus.
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        data_dir: Optional[str] = None,
        code_dir: Optional[str] = None,
        auto_fix_critical: bool = True,
        enable_supermemory: bool = True,
        coverage_threshold: float = 80.0,
        **kwargs,
    ):
        """
        Initialize the differential analysis agent.

        Args:
            name: Agent name
            event_bus: EventBus for pub/sub
            shared_state: Shared state singleton
            working_dir: Working directory for the agent
            data_dir: Path to documentation data directory
            code_dir: Path to generated code directory
            auto_fix_critical: Whether to publish CODE_FIX_NEEDED for critical gaps
            enable_supermemory: Whether to use Supermemory patterns
            coverage_threshold: Coverage percentage to consider an epic validated (0-100)
        """
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self._data_dir = data_dir
        self._code_dir = code_dir
        self._auto_fix_critical = auto_fix_critical
        self._enable_supermemory = enable_supermemory
        self._coverage_threshold = coverage_threshold

        # Runtime state
        self._analysis_service = None
        self._analysis_running = False

    # ------------------------------------------------------------------
    # AutonomousAgent interface
    # ------------------------------------------------------------------

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.GENERATION_COMPLETE,
            EventType.CONVERGENCE_ACHIEVED,
        ]

    async def should_act(self, events: list) -> bool:
        """Act when epic completes or generation finishes."""
        return any(e.type in self.subscribed_events for e in events)

    async def act(self, events: list) -> Optional[Event]:
        """Process events and drive differential analysis."""
        for event in events:
            if event.source == self.name:
                continue

            try:
                if event.type == EventType.EPIC_EXECUTION_COMPLETED:
                    await self._handle_epic_completed(event)
                elif event.type == EventType.GENERATION_COMPLETE:
                    await self._handle_generation_complete(event)
                elif event.type == EventType.CONVERGENCE_ACHIEVED:
                    await self._handle_convergence(event)
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
        """Run per-epic differential analysis after epic execution completes."""
        epic_id = event.data.get("epic_id")
        data_dir = self._resolve_data_dir(event)
        code_dir = self._resolve_code_dir(event)

        if not data_dir:
            self.logger.warning("no_data_dir", msg="Cannot determine documentation directory")
            return

        if epic_id:
            await self._run_epic_analysis(data_dir, code_dir, epic_id)
        else:
            await self._run_analysis(data_dir, code_dir, trigger="epic_completed")

    async def _handle_generation_complete(self, event: Event) -> None:
        """Run differential analysis after generation pipeline completes."""
        data_dir = self._resolve_data_dir(event)
        code_dir = self._resolve_code_dir(event)

        if not data_dir:
            return

        await self._run_analysis(data_dir, code_dir, trigger="generation_complete")

    async def _handle_convergence(self, event: Event) -> None:
        """Publish final coverage report at convergence."""
        if self._analysis_service and self._analysis_service.reports:
            latest = self._analysis_service.reports[-1]
            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_COVERAGE_REPORT,
                source=self.name,
                data={
                    "coverage_percent": latest.coverage_percent,
                    "total_requirements": latest.total_requirements,
                    "implemented": latest.implemented,
                    "partial": latest.partial,
                    "missing": latest.missing,
                    "critical_gaps": len(self._analysis_service.get_critical_gaps()),
                },
            ))

    # ------------------------------------------------------------------
    # Core Analysis
    # ------------------------------------------------------------------

    async def _run_analysis(
        self,
        data_dir: str,
        code_dir: Optional[str],
        trigger: str,
    ) -> None:
        """Run the full differential analysis."""
        if self._analysis_running:
            self.logger.info("analysis_already_running")
            return

        self._analysis_running = True

        try:
            from ..services.differential_analysis_service import (
                AnalysisMode,
                DifferentialAnalysisService,
                ImplementationStatus,
                GapSeverity,
            )

            # Publish start event
            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_ANALYSIS_STARTED,
                source=self.name,
                data={"data_dir": data_dir, "trigger": trigger},
            ))

            # Initialize service
            self._analysis_service = DifferentialAnalysisService(
                data_dir=data_dir,
                code_dir=code_dir,
                event_bus=self.event_bus,
                job_id=f"agent_{trigger}",
                enable_supermemory=self._enable_supermemory,
            )

            started = await self._analysis_service.start()
            if not started:
                self.logger.warning("analysis_start_failed")
                return

            # Run full differential analysis
            report = await self._analysis_service.run_analysis(
                mode=AnalysisMode.FULL_DIFFERENTIAL,
            )

            # Publish individual gap findings
            for finding in report.findings:
                if finding.status != ImplementationStatus.IMPLEMENTED:
                    await self.event_bus.publish(Event(
                        type=EventType.DIFFERENTIAL_GAP_FOUND,
                        source=self.name,
                        data={
                            "requirement_id": finding.requirement_id,
                            "requirement_title": finding.requirement_title,
                            "status": finding.status.value,
                            "severity": finding.severity.value,
                            "confidence": finding.confidence,
                            "gap_description": finding.gap_description,
                            "suggested_tasks": finding.suggested_tasks,
                        },
                    ))

                    # Bridge critical gaps to CODE_FIX_NEEDED
                    if (
                        self._auto_fix_critical
                        and finding.severity == GapSeverity.CRITICAL
                        and finding.confidence >= 0.6
                    ):
                        await self.event_bus.publish(Event(
                            type=EventType.CODE_FIX_NEEDED,
                            source=self.name,
                            data={
                                "reason": f"Missing implementation: {finding.requirement_title}",
                                "requirement_id": finding.requirement_id,
                                "gap_description": finding.gap_description,
                                "suggested_tasks": finding.suggested_tasks,
                                "source_analysis": "differential",
                            },
                        ))

            # Export report
            report_path = self._analysis_service.export_report()

            # Publish completion event
            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_ANALYSIS_COMPLETE,
                source=self.name,
                data={
                    "coverage_percent": report.coverage_percent,
                    "total": report.total_requirements,
                    "implemented": report.implemented,
                    "partial": report.partial,
                    "missing": report.missing,
                    "report_path": report_path,
                    "trigger": trigger,
                },
            ))

            # Update SharedState for convergence (Phase 27)
            if self.shared_state:
                critical_count = len(self._analysis_service.get_critical_gaps())
                await self.shared_state.update_differential(
                    coverage_percent=report.coverage_percent,
                    gaps_critical=critical_count,
                    gaps_total=len(report.findings),
                )

            self.logger.info(
                "differential_analysis_complete",
                coverage=f"{report.coverage_percent:.1f}%",
                missing=report.missing,
                critical=len(self._analysis_service.get_critical_gaps()),
            )

        except Exception as e:
            self.logger.error("analysis_error", error=str(e))
        finally:
            self._analysis_running = False

            if self._analysis_service:
                try:
                    await self._analysis_service.stop()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Per-Epic Analysis
    # ------------------------------------------------------------------

    async def _run_epic_analysis(
        self,
        data_dir: str,
        code_dir: Optional[str],
        epic_id: str,
    ) -> None:
        """
        Run differential analysis scoped to a single epic.

        Filters tasks and requirements to only those belonging to the epic,
        then publishes DIFFERENTIAL_EPIC_VALIDATED or DIFFERENTIAL_EPIC_FAILED.
        """
        if self._analysis_running:
            self.logger.info("analysis_already_running")
            return

        self._analysis_running = True

        try:
            from ..services.differential_analysis_service import (
                AnalysisMode,
                DifferentialAnalysisService,
            )

            self.logger.info("epic_analysis_starting", epic_id=epic_id)

            # Publish start event
            await self.event_bus.publish(Event(
                type=EventType.DIFFERENTIAL_ANALYSIS_STARTED,
                source=self.name,
                data={"data_dir": data_dir, "trigger": "epic_completed", "epic_id": epic_id},
            ))

            # Create service scoped to this epic
            service = DifferentialAnalysisService(
                data_dir=data_dir,
                code_dir=code_dir,
                event_bus=self.event_bus,
                job_id=f"epic_{epic_id}",
                enable_supermemory=self._enable_supermemory,
                epic_id=epic_id,
            )

            started = await service.start()
            if not started:
                self.logger.warning("epic_analysis_start_failed", epic_id=epic_id)
                return

            # Run requirement coverage analysis for this epic
            report = await service.run_analysis(
                mode=AnalysisMode.REQUIREMENT_COVERAGE,
            )

            # Determine pass/fail
            coverage = report.coverage_percent
            passed = coverage >= self._coverage_threshold

            # Build gap summary for event payload
            gaps = [
                {
                    "requirement_id": f.requirement_id,
                    "requirement_title": f.requirement_title,
                    "status": f.status.value,
                    "severity": f.severity.value,
                }
                for f in report.findings
                if f.status.value != "implemented"
            ]

            result_data = {
                "epic_id": epic_id,
                "coverage_percent": round(coverage, 2),
                "total_requirements": report.total_requirements,
                "implemented": report.implemented,
                "partial": report.partial,
                "missing": report.missing,
                "gaps": gaps,
            }

            if passed:
                await self.event_bus.publish(Event(
                    type=EventType.DIFFERENTIAL_EPIC_VALIDATED,
                    source=self.name,
                    data=result_data,
                ))
                self.logger.info(
                    "epic_validated",
                    epic_id=epic_id,
                    coverage=f"{coverage:.1f}%",
                )
            else:
                await self.event_bus.publish(Event(
                    type=EventType.DIFFERENTIAL_EPIC_FAILED,
                    source=self.name,
                    data=result_data,
                ))
                self.logger.warning(
                    "epic_failed",
                    epic_id=epic_id,
                    coverage=f"{coverage:.1f}%",
                    threshold=f"{self._coverage_threshold:.1f}%",
                    missing=report.missing,
                )

                # Bridge critical gaps to CODE_FIX_NEEDED
                if self._auto_fix_critical:
                    from ..services.differential_analysis_service import (
                        GapSeverity,
                    )
                    for finding in report.findings:
                        if (
                            finding.severity == GapSeverity.CRITICAL
                            and finding.confidence >= 0.6
                        ):
                            await self.event_bus.publish(Event(
                                type=EventType.CODE_FIX_NEEDED,
                                source=self.name,
                                data={
                                    "reason": f"[{epic_id}] Missing: {finding.requirement_title}",
                                    "requirement_id": finding.requirement_id,
                                    "epic_id": epic_id,
                                    "gap_description": finding.gap_description,
                                    "suggested_tasks": finding.suggested_tasks,
                                    "source_analysis": "differential_epic",
                                },
                            ))

            # Update SharedState for convergence (Phase 27)
            if self.shared_state:
                from ..services.differential_analysis_service import GapSeverity as _GS
                critical_count = sum(
                    1 for f in report.findings
                    if f.severity == _GS.CRITICAL
                )
                await self.shared_state.update_differential(
                    coverage_percent=coverage,
                    gaps_critical=critical_count,
                    gaps_total=len(report.findings),
                )

            # Export report
            service.export_report()

        except Exception as e:
            self.logger.error("epic_analysis_error", epic_id=epic_id, error=str(e))
        finally:
            self._analysis_running = False
            try:
                await service.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_data_dir(self, event: Event) -> Optional[str]:
        """Resolve the documentation data directory from event or config."""
        if self._data_dir:
            return self._data_dir

        # Try from event data
        data_dir = event.data.get("data_dir", "")
        if data_dir:
            return data_dir

        # Try from working_dir convention
        working = Path(self.working_dir)
        if (working / "user_stories.json").exists():
            return str(working)
        if (working / "tasks").exists():
            return str(working)

        return None

    def _resolve_code_dir(self, event: Event) -> Optional[str]:
        """Resolve the generated code directory from event or config."""
        if self._code_dir:
            return self._code_dir

        code_dir = event.data.get("code_dir", event.data.get("output_dir", ""))
        if code_dir:
            return code_dir

        # Convention: data_dir/output
        data_dir = self._resolve_data_dir(event)
        if data_dir:
            output = Path(data_dir) / "output"
            if output.exists():
                return str(output)

        return None
