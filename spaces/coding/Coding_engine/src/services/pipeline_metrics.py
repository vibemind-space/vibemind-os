"""
Pipeline Metrics Aggregator — Collects and exposes metrics from all emergent pipeline subsystems.

Subscribes to EventBus events and maintains real-time metrics for:
- Package ingestion status
- TreeQuest verification findings
- ShinkaEvolve evolution runs
- Minibook collaboration activity
- Pipeline convergence state
- Agent liveness

Used by DaveLovable dashboard and OpenClaw status queries.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState

logger = structlog.get_logger(__name__)


@dataclass
class PipelineMetrics:
    """Aggregated pipeline metrics snapshot."""

    # Timing
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    # Package
    package_name: str = ""
    package_tasks: int = 0
    package_epics: int = 0
    package_completeness: float = 0.0

    # Build/Test
    build_count: int = 0
    build_success_count: int = 0
    build_fail_count: int = 0
    test_pass_count: int = 0
    test_fail_count: int = 0

    # TreeQuest Verification
    verification_runs: int = 0
    findings_total: int = 0
    findings_critical: int = 0
    findings_warning: int = 0
    findings_info: int = 0

    # ShinkaEvolve
    evolution_runs: int = 0
    evolution_improved: int = 0
    evolution_failed: int = 0
    evolution_applied: int = 0

    # Minibook
    minibook_posts: int = 0
    minibook_comments: int = 0
    minibook_mentions: int = 0

    # Pipeline
    pipeline_phase: str = "idle"
    pipeline_iterations: int = 0
    convergence_score: float = 0.0

    # Code generation
    files_generated: int = 0
    files_fixed: int = 0
    code_fix_requests: int = 0

    # Agent activity
    agent_events: Dict[str, int] = field(default_factory=dict)

    # Event flow (last N events)
    recent_events: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timing": {
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "duration_seconds": self.duration_seconds,
            },
            "package": {
                "name": self.package_name,
                "tasks": self.package_tasks,
                "epics": self.package_epics,
                "completeness": self.package_completeness,
            },
            "build_test": {
                "builds": self.build_count,
                "build_success": self.build_success_count,
                "build_fail": self.build_fail_count,
                "test_pass": self.test_pass_count,
                "test_fail": self.test_fail_count,
            },
            "verification": {
                "runs": self.verification_runs,
                "total_findings": self.findings_total,
                "critical": self.findings_critical,
                "warning": self.findings_warning,
                "info": self.findings_info,
            },
            "evolution": {
                "runs": self.evolution_runs,
                "improved": self.evolution_improved,
                "failed": self.evolution_failed,
                "applied": self.evolution_applied,
            },
            "minibook": {
                "posts": self.minibook_posts,
                "comments": self.minibook_comments,
                "mentions": self.minibook_mentions,
            },
            "pipeline": {
                "phase": self.pipeline_phase,
                "iterations": self.pipeline_iterations,
                "convergence_score": self.convergence_score,
            },
            "code": {
                "files_generated": self.files_generated,
                "files_fixed": self.files_fixed,
                "fix_requests": self.code_fix_requests,
            },
            "agents": self.agent_events,
            "recent_events": self.recent_events[-20:],
        }


class PipelineMetricsCollector:
    """Subscribes to EventBus and collects real-time metrics."""

    MAX_RECENT_EVENTS = 100

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.metrics = PipelineMetrics()
        self._start_time: Optional[float] = None
        self._subscribe()

    def _subscribe(self):
        """Subscribe to all relevant events."""
        event_handlers = {
            # Pipeline lifecycle
            EventType.PIPELINE_STARTED: self._on_pipeline_started,
            EventType.PIPELINE_COMPLETED: self._on_pipeline_completed,
            EventType.PIPELINE_FAILED: self._on_pipeline_failed,
            EventType.PIPELINE_PHASE_CHANGED: self._on_phase_changed,

            # Package
            EventType.PACKAGE_READY: self._on_package_ready,

            # Build/Test
            EventType.BUILD_SUCCEEDED: self._on_build_success,
            EventType.BUILD_FAILED: self._on_build_fail,
            EventType.TEST_PASSED: self._on_test_pass,
            EventType.TEST_FAILED: self._on_test_fail,

            # TreeQuest
            EventType.TREEQUEST_VERIFICATION_STARTED: self._on_verification_started,
            EventType.TREEQUEST_VERIFICATION_COMPLETE: self._on_verification_complete,
            EventType.TREEQUEST_FINDING_CRITICAL: self._on_finding_critical,
            EventType.TREEQUEST_FINDING_WARNING: self._on_finding_warning,
            EventType.TREEQUEST_FINDING_INFO: self._on_finding_info,

            # ShinkaEvolve
            EventType.EVOLUTION_STARTED: self._on_evolution_started,
            EventType.EVOLUTION_IMPROVED: self._on_evolution_improved,
            EventType.EVOLUTION_FAILED: self._on_evolution_failed,
            EventType.EVOLUTION_APPLIED: self._on_evolution_applied,

            # Minibook
            EventType.MINIBOOK_POST_CREATED: self._on_minibook_post,
            EventType.MINIBOOK_COMMENT_ADDED: self._on_minibook_comment,
            EventType.MINIBOOK_AGENT_MENTIONED: self._on_minibook_mention,

            # Code
            EventType.CODE_GENERATED: self._on_code_generated,
            EventType.CODE_FIXED: self._on_code_fixed,
            EventType.CODE_FIX_NEEDED: self._on_fix_needed,

            # Convergence
            EventType.CONVERGENCE_UPDATE: self._on_convergence,

            # Agents
            EventType.AGENT_STARTED: self._on_agent_event,
            EventType.AGENT_COMPLETED: self._on_agent_event,
        }

        for event_type, handler in event_handlers.items():
            self.event_bus.subscribe(event_type, handler)

    def _record_event(self, event: Event):
        """Record event in recent events list."""
        entry = {
            "type": event.type.value,
            "timestamp": datetime.now().isoformat(),
            "agent": event.data.get("agent", ""),
            "correlation_id": getattr(event, "correlation_id", None),
            "span_id": getattr(event, "span_id", None),
        }
        self.metrics.recent_events.append(entry)
        if len(self.metrics.recent_events) > self.MAX_RECENT_EVENTS:
            self.metrics.recent_events = self.metrics.recent_events[-self.MAX_RECENT_EVENTS:]

    # --- Handlers ---

    async def _on_pipeline_started(self, event: Event):
        self._start_time = time.time()
        self.metrics.started_at = datetime.now().isoformat()
        self.metrics.pipeline_phase = "running"
        self._record_event(event)

    async def _on_pipeline_completed(self, event: Event):
        self.metrics.completed_at = datetime.now().isoformat()
        if self._start_time:
            self.metrics.duration_seconds = time.time() - self._start_time
        self.metrics.pipeline_phase = "completed"
        self.metrics.pipeline_iterations = event.data.get("iterations", 0)
        self._record_event(event)

    async def _on_pipeline_failed(self, event: Event):
        self.metrics.completed_at = datetime.now().isoformat()
        if self._start_time:
            self.metrics.duration_seconds = time.time() - self._start_time
        self.metrics.pipeline_phase = "failed"
        self._record_event(event)

    async def _on_phase_changed(self, event: Event):
        self.metrics.pipeline_phase = event.data.get("phase", "unknown")
        self._record_event(event)

    async def _on_package_ready(self, event: Event):
        self.metrics.package_name = event.data.get("project_name", "")
        self.metrics.package_tasks = event.data.get("total_tasks", 0)
        self.metrics.package_epics = event.data.get("total_epics", 0)
        self.metrics.package_completeness = event.data.get("completeness", 0.0)
        self._record_event(event)

    async def _on_build_success(self, event: Event):
        self.metrics.build_count += 1
        self.metrics.build_success_count += 1
        self._record_event(event)

    async def _on_build_fail(self, event: Event):
        self.metrics.build_count += 1
        self.metrics.build_fail_count += 1
        self._record_event(event)

    async def _on_test_pass(self, event: Event):
        self.metrics.test_pass_count += 1
        self._record_event(event)

    async def _on_test_fail(self, event: Event):
        self.metrics.test_fail_count += 1
        self._record_event(event)

    async def _on_verification_started(self, event: Event):
        self.metrics.verification_runs += 1
        self._record_event(event)

    async def _on_verification_complete(self, event: Event):
        self.metrics.findings_total += event.data.get("total_findings", 0)
        self._record_event(event)

    async def _on_finding_critical(self, event: Event):
        self.metrics.findings_critical += 1
        self._record_event(event)

    async def _on_finding_warning(self, event: Event):
        self.metrics.findings_warning += 1
        self._record_event(event)

    async def _on_finding_info(self, event: Event):
        self.metrics.findings_info += 1
        self._record_event(event)

    async def _on_evolution_started(self, event: Event):
        self.metrics.evolution_runs += 1
        self._record_event(event)

    async def _on_evolution_improved(self, event: Event):
        self.metrics.evolution_improved += 1
        self._record_event(event)

    async def _on_evolution_failed(self, event: Event):
        self.metrics.evolution_failed += 1
        self._record_event(event)

    async def _on_evolution_applied(self, event: Event):
        self.metrics.evolution_applied += 1
        self._record_event(event)

    async def _on_minibook_post(self, event: Event):
        self.metrics.minibook_posts += 1
        self._record_event(event)

    async def _on_minibook_comment(self, event: Event):
        self.metrics.minibook_comments += 1
        self._record_event(event)

    async def _on_minibook_mention(self, event: Event):
        self.metrics.minibook_mentions += 1
        self._record_event(event)

    async def _on_code_generated(self, event: Event):
        self.metrics.files_generated += 1
        self._record_event(event)

    async def _on_code_fixed(self, event: Event):
        self.metrics.files_fixed += 1
        self._record_event(event)

    async def _on_fix_needed(self, event: Event):
        self.metrics.code_fix_requests += 1
        self._record_event(event)

    async def _on_convergence(self, event: Event):
        self.metrics.convergence_score = event.data.get("score", 0.0)
        self.metrics.pipeline_iterations += 1
        self._record_event(event)

    async def _on_agent_event(self, event: Event):
        agent_name = event.data.get("agent", "unknown")
        self.metrics.agent_events[agent_name] = (
            self.metrics.agent_events.get(agent_name, 0) + 1
        )
        self._record_event(event)

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics as a dictionary."""
        return self.metrics.to_dict()

    def get_summary(self) -> str:
        """Get a human-readable summary string."""
        m = self.metrics
        lines = [
            f"Pipeline: {m.pipeline_phase}",
            f"Package: {m.package_name} ({m.package_tasks} tasks)",
            f"Builds: {m.build_success_count}/{m.build_count} succeeded",
            f"Tests: pass={m.test_pass_count}, fail={m.test_fail_count}",
            f"Verification: {m.verification_runs} runs, {m.findings_critical} critical, {m.findings_warning} warnings",
            f"Evolution: {m.evolution_runs} runs, {m.evolution_improved} improved, {m.evolution_applied} applied",
            f"Code: {m.files_generated} generated, {m.files_fixed} fixed",
            f"Duration: {m.duration_seconds:.1f}s",
        ]
        return "\n".join(lines)
