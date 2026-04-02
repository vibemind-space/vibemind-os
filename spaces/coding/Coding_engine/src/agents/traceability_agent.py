"""
TraceabilityAgent - LLM-powered requirement-to-code tracing.

This agent:
1. Maps requirements to implemented code files
2. Calculates implementation coverage percentage
3. Identifies missing/incomplete implementations
4. Provides verification evidence for compliance

Events:
- Subscribes to: GENERATION_COMPLETE, BUILD_SUCCEEDED, VALIDATION_ERROR
- Publishes: TRACEABILITY_REPORT_CREATED, REQUIREMENT_COVERAGE_UPDATED
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from src.agents.autonomous_base import AutonomousAgent
from src.mind.event_bus import Event, EventType

logger = structlog.get_logger(__name__)


@dataclass
class RequirementTrace:
    """Traceability information for a single requirement."""
    requirement_id: str
    requirement_text: str
    implementing_files: list[str] = field(default_factory=list)
    coverage_percent: int = 0
    missing_aspects: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    last_verified: Optional[datetime] = None


@dataclass
class TraceabilityReport:
    """Complete traceability report for a project."""
    project_id: str
    total_requirements: int = 0
    fully_implemented: int = 0
    partially_implemented: int = 0
    not_implemented: int = 0
    overall_coverage: float = 0.0
    traces: list[RequirementTrace] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "total_requirements": self.total_requirements,
            "fully_implemented": self.fully_implemented,
            "partially_implemented": self.partially_implemented,
            "not_implemented": self.not_implemented,
            "overall_coverage": self.overall_coverage,
            "traces": [
                {
                    "requirement_id": t.requirement_id,
                    "requirement_text": t.requirement_text,
                    "implementing_files": t.implementing_files,
                    "coverage_percent": t.coverage_percent,
                    "missing_aspects": t.missing_aspects,
                    "evidence": t.evidence,
                    "confidence": t.confidence,
                }
                for t in self.traces
            ],
            "generated_at": self.generated_at.isoformat(),
        }


class TraceabilityAgent(AutonomousAgent):
    """
    LLM-powered requirement-to-code traceability agent.

    Uses Claude to semantically map requirements to implementation files,
    providing evidence-based coverage analysis for compliance and verification.
    """

    COOLDOWN_SECONDS = 60.0  # Run at most once per minute

    def __init__(
        self,
        name: str = "TraceabilityAgent",
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
        self._last_report: Optional[TraceabilityReport] = None
        self._requirements_cache: list[dict] = []
        self.logger = logger.bind(agent=name)

        self.logger.info(
            "traceability_agent_initialized",
            working_dir=working_dir,
        )

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
            EventType.VALIDATION_ERROR,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """Decide if we should run traceability analysis."""
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Always act on GENERATION_COMPLETE
            if event.type == EventType.GENERATION_COMPLETE:
                return True

            # Act on BUILD_SUCCEEDED if we have requirements
            if event.type == EventType.BUILD_SUCCEEDED:
                if len(self._requirements_cache) > 0 or self._load_requirements():
                    return True

        return False

    async def act(self, events: list[Event]) -> None:
        """Perform traceability analysis."""
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self.logger.info(
            "starting_traceability_analysis",
            event_type=event.type.value,
            project_id=event.data.get("project_id") if event.data else None,
        )

        try:
            # Load requirements if not cached
            if not self._requirements_cache:
                self._load_requirements()

            if not self._requirements_cache:
                self.logger.warning("no_requirements_found")
                return

            # Get list of implementation files
            impl_files = self._discover_implementation_files()

            if not impl_files:
                self.logger.warning("no_implementation_files_found")
                return

            # Perform traceability analysis
            report = await self._analyze_traceability(
                self._requirements_cache,
                impl_files,
                event.data.get("project_id", "default") if event.data else "default",
            )

            self._last_report = report

            # Publish report
            if self.event_bus:
                await self.event_bus.publish(Event(
                    type=EventType.DOCUMENT_CREATED,
                    source=self.name,
                    data={
                        "document_type": "traceability_report",
                        "project_id": report.project_id,
                        "report": report.to_dict(),
                        "overall_coverage": report.overall_coverage,
                        "fully_implemented": report.fully_implemented,
                        "total_requirements": report.total_requirements,
                    },
                ))

            # Update shared state
            if self.shared_state:
                self.shared_state.set(
                    f"traceability_{report.project_id}",
                    {
                        "overall_coverage": report.overall_coverage,
                        "fully_implemented": report.fully_implemented,
                        "total_requirements": report.total_requirements,
                    }
                )

            self.logger.info(
                "traceability_analysis_complete",
                total_requirements=report.total_requirements,
                fully_implemented=report.fully_implemented,
                overall_coverage=f"{report.overall_coverage:.1f}%",
            )

        except Exception as e:
            self.logger.error("traceability_analysis_failed", error=str(e))

    def _load_requirements(self) -> bool:
        """Load requirements from requirements.json or similar files."""
        working_path = Path(self.working_dir)

        # Common requirement file locations
        req_files = [
            working_path / "requirements.json",
            working_path / "requirements" / "requirements.json",
            working_path / "docs" / "requirements.json",
            working_path / "spec" / "requirements.json",
        ]

        for req_file in req_files:
            if req_file.exists():
                try:
                    content = json.loads(req_file.read_text(encoding="utf-8"))

                    # Handle different requirement formats
                    if isinstance(content, dict):
                        if "features" in content:
                            self._requirements_cache = content["features"]
                        elif "requirements" in content:
                            self._requirements_cache = content["requirements"]
                        else:
                            # Assume the dict itself contains requirements
                            self._requirements_cache = [
                                {"id": k, "description": v}
                                for k, v in content.items()
                                if isinstance(v, str)
                            ]
                    elif isinstance(content, list):
                        self._requirements_cache = content

                    self.logger.info(
                        "requirements_loaded",
                        file=str(req_file),
                        count=len(self._requirements_cache),
                    )
                    return True

                except Exception as e:
                    self.logger.debug("requirements_load_failed", file=str(req_file), error=str(e))

        return False

    def _discover_implementation_files(self) -> list[str]:
        """Discover implementation files in the project."""
        working_path = Path(self.working_dir)
        src_dir = working_path / "src"

        if not src_dir.exists():
            src_dir = working_path

        files = []
        skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", ".next"}
        extensions = {".ts", ".tsx", ".js", ".jsx", ".py", ".vue", ".svelte"}

        for file_path in src_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if any(skip in file_path.parts for skip in skip_dirs):
                continue
            if file_path.suffix not in extensions:
                continue

            try:
                rel_path = str(file_path.relative_to(working_path))
                files.append(rel_path)
            except ValueError:
                files.append(str(file_path))

        return files[:100]  # Limit to 100 files for LLM context

    async def _analyze_traceability(
        self,
        requirements: list[dict],
        impl_files: list[str],
        project_id: str,
    ) -> TraceabilityReport:
        """
        Use LLM to analyze requirement-to-code traceability.

        Args:
            requirements: List of requirement dicts
            impl_files: List of implementation file paths
            project_id: Project identifier

        Returns:
            TraceabilityReport with coverage analysis
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        report = TraceabilityReport(project_id=project_id)
        report.total_requirements = len(requirements)

        # Format requirements for LLM
        req_text = "\n".join([
            f"[REQ-{i}] {r.get('id', f'req_{i}')}: {r.get('description', r.get('name', str(r)))[:200]}"
            for i, r in enumerate(requirements[:20])
        ])

        # Format files for LLM
        files_text = "\n".join(impl_files[:50])

        prompt = f"""Analyze requirement-to-code traceability for this project.

## REQUIREMENTS:
{req_text}

## IMPLEMENTATION FILES:
{files_text}

## ANALYSIS TASK:

For each requirement, determine:
1. Which files implement it (partially or fully)
2. What percentage is implemented (0-100%)
3. What aspects are missing (if any)
4. Evidence: specific functions/classes that implement it

## RESPONSE FORMAT:

Respond with JSON array:
```json
[
  {{
    "requirement_index": 0,
    "implementing_files": ["src/components/UserForm.tsx", "src/api/users.ts"],
    "coverage_percent": 80,
    "missing_aspects": ["validation", "error handling"],
    "evidence": ["UserForm component handles user input", "createUser API endpoint exists"],
    "confidence": 0.85
  }}
]
```

Be realistic about coverage. If a requirement has no clear implementation, set coverage to 0.
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=120)
            result = await tool.execute(
                prompt=prompt,
                context="Requirement traceability analysis",
                agent_type="traceability_analyzer",
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                traces_data = json.loads(json_match.group(1))

                for trace_data in traces_data:
                    idx = trace_data.get("requirement_index", 0)
                    if idx < len(requirements):
                        req = requirements[idx]
                        trace = RequirementTrace(
                            requirement_id=req.get("id", f"req_{idx}"),
                            requirement_text=req.get("description", req.get("name", str(req)))[:200],
                            implementing_files=trace_data.get("implementing_files", []),
                            coverage_percent=trace_data.get("coverage_percent", 0),
                            missing_aspects=trace_data.get("missing_aspects", []),
                            evidence=trace_data.get("evidence", []),
                            confidence=trace_data.get("confidence", 0.5),
                            last_verified=datetime.now(),
                        )
                        report.traces.append(trace)

                        # Update counters
                        if trace.coverage_percent >= 90:
                            report.fully_implemented += 1
                        elif trace.coverage_percent > 0:
                            report.partially_implemented += 1
                        else:
                            report.not_implemented += 1

                # Calculate overall coverage
                if report.traces:
                    report.overall_coverage = sum(t.coverage_percent for t in report.traces) / len(report.traces)

        except Exception as e:
            self.logger.warning("llm_traceability_analysis_failed", error=str(e))

        return report

    async def trace_single_requirement(
        self, requirement: dict, impl_files: list[str] = None
    ) -> RequirementTrace:
        """
        Trace a single requirement to implementation files.

        Args:
            requirement: Requirement dict with id, description
            impl_files: Optional list of files to check (uses discovery if None)

        Returns:
            RequirementTrace with implementation details
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        if impl_files is None:
            impl_files = self._discover_implementation_files()

        req_id = requirement.get("id", "unknown")
        req_desc = requirement.get("description", requirement.get("name", str(requirement)))

        prompt = f"""Find code that implements this requirement:

## REQUIREMENT:
ID: {req_id}
Description: {req_desc}

## CODEBASE FILES:
{chr(10).join(impl_files[:50])}

## ANALYSIS:

1. Which files are most likely to implement this requirement?
2. What specific functions/components implement it?
3. What percentage of the requirement is covered?
4. What's missing?

Respond with JSON:
```json
{{
    "implementing_files": ["file1.ts", "file2.tsx"],
    "coverage_percent": 75,
    "missing_aspects": ["error handling", "validation"],
    "evidence": ["createUser() function in users.ts", "UserForm component"],
    "confidence": 0.8
}}
```
"""

        try:
            tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=60)
            result = await tool.execute(
                prompt=prompt,
                context=f"Tracing requirement {req_id}",
                agent_type="requirement_tracer",
            )

            json_match = re.search(r'```json\s*(.*?)\s*```', result.output or "", re.DOTALL)
            if json_match:
                trace_data = json.loads(json_match.group(1))
                return RequirementTrace(
                    requirement_id=req_id,
                    requirement_text=req_desc[:200],
                    implementing_files=trace_data.get("implementing_files", []),
                    coverage_percent=trace_data.get("coverage_percent", 0),
                    missing_aspects=trace_data.get("missing_aspects", []),
                    evidence=trace_data.get("evidence", []),
                    confidence=trace_data.get("confidence", 0.5),
                    last_verified=datetime.now(),
                )

        except Exception as e:
            self.logger.warning("single_trace_failed", req_id=req_id, error=str(e))

        return RequirementTrace(
            requirement_id=req_id,
            requirement_text=req_desc[:200],
            coverage_percent=0,
            confidence=0.0,
        )

    def get_coverage_summary(self) -> dict:
        """Get summary of current traceability coverage."""
        if not self._last_report:
            return {
                "status": "no_report",
                "message": "No traceability report generated yet",
            }

        return {
            "status": "available",
            "project_id": self._last_report.project_id,
            "total_requirements": self._last_report.total_requirements,
            "fully_implemented": self._last_report.fully_implemented,
            "partially_implemented": self._last_report.partially_implemented,
            "not_implemented": self._last_report.not_implemented,
            "overall_coverage": f"{self._last_report.overall_coverage:.1f}%",
            "generated_at": self._last_report.generated_at.isoformat(),
        }
