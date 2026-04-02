"""
RuntimeReportManager - Loads, aggregates, and cleans up runtime reports.

This module handles:
- Loading existing JSON reports from previous pipeline runs
- Aggregating architecture health, test priorities, validation status
- Providing context to agents for informed decisions
- Cleaning up reports after they've been processed

Report Types Handled:
- architecture_analyzer_*.json - Architecture health scores
- test_generation_*.json - Test priority files
- CRUD_VALIDATION_COMPLETE.json - CRUD endpoint validation
- VALIDATION_EXCEPTIONS.json - Entity clarifications
- architecture-health-report.json - Consolidated health report
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ArchitectureInsight:
    """Aggregated architecture health insights."""
    overall_score: float = 0.0
    worst_metrics: list[dict] = field(default_factory=list)  # metrics with score < 6
    anti_patterns: list[dict] = field(default_factory=list)
    critical_recommendations: list[dict] = field(default_factory=list)
    files_needing_refactor: list[str] = field(default_factory=list)


@dataclass
class TestPriority:
    """Test generation priorities from reports."""
    high_risk_files: list[dict] = field(default_factory=list)
    medium_risk_files: list[dict] = field(default_factory=list)
    coverage_estimate: float = 0.0


@dataclass
class ValidationStatus:
    """CRUD and validation status from reports."""
    total_endpoints: int = 0
    total_entities: int = 0
    full_crud_sets: int = 0
    entity_exceptions: dict = field(default_factory=dict)
    route_files: list[str] = field(default_factory=list)


@dataclass
class AggregatedReports:
    """All aggregated runtime reports."""
    architecture: ArchitectureInsight = field(default_factory=ArchitectureInsight)
    tests: TestPriority = field(default_factory=TestPriority)
    validation: ValidationStatus = field(default_factory=ValidationStatus)
    report_files_processed: list[str] = field(default_factory=list)
    loaded_at: datetime = field(default_factory=datetime.now)

    def has_architecture_issues(self) -> bool:
        """Check if there are significant architecture issues."""
        return (
            self.architecture.overall_score < 6.0 or
            len(self.architecture.anti_patterns) > 3 or
            len(self.architecture.critical_recommendations) > 0
        )

    def get_priority_test_files(self, limit: int = 10) -> list[str]:
        """Get top priority files for testing."""
        files = []
        for f in self.tests.high_risk_files[:limit]:
            files.append(f.get("file", ""))
        return [f for f in files if f]

    def to_prompt_context(self) -> str:
        """Convert to context string for prompts."""
        parts = []

        if self.architecture.overall_score > 0:
            parts.append(f"## Architecture Health: {self.architecture.overall_score:.1f}/10")

            if self.architecture.anti_patterns:
                parts.append("\n### Anti-Patterns Detected:")
                for ap in self.architecture.anti_patterns[:5]:
                    if isinstance(ap, dict):
                        parts.append(f"- {ap.get('name', 'Unknown')}: {ap.get('location', '')}")
                    else:
                        parts.append(f"- {ap}")

            if self.architecture.critical_recommendations:
                parts.append("\n### Critical Recommendations:")
                for rec in self.architecture.critical_recommendations[:3]:
                    if isinstance(rec, dict):
                        parts.append(f"- [{rec.get('priority', 'high')}] {rec.get('title', '')}")
                    else:
                        parts.append(f"- {rec}")

        if self.validation.total_endpoints > 0:
            parts.append(f"\n## Validation Status: {self.validation.total_endpoints} endpoints, {self.validation.total_entities} entities")

        return "\n".join(parts) if parts else ""


class RuntimeReportManager:
    """
    Manages runtime reports: loading, aggregating, and cleanup.

    Usage:
        manager = RuntimeReportManager(output_dir)
        reports = manager.load_all()  # Load and aggregate

        # Use reports...
        context = reports.to_prompt_context()

        # After processing
        manager.cleanup()  # Delete processed files
    """

    # Report file patterns
    ARCHITECTURE_PATTERN = "architecture_analyzer_*.json"
    ARCHITECTURE_HEALTH = "architecture-health-report.json"
    ARCHITECTURE_ASSESSMENT = "architecture-health-assessment.json"
    TEST_GENERATION_PATTERN = "test_generation_*.json"
    CRUD_VALIDATION = "CRUD_VALIDATION_COMPLETE.json"
    VALIDATION_EXCEPTIONS = "VALIDATION_EXCEPTIONS.json"

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self._loaded_files: list[Path] = []
        self._aggregated: Optional[AggregatedReports] = None
        self.logger = logger.bind(component="runtime_report_manager")

    def load_all(self) -> AggregatedReports:
        """
        Load and aggregate all runtime reports.

        Returns:
            AggregatedReports with all insights
        """
        self.logger.info("loading_runtime_reports", output_dir=str(self.output_dir))

        aggregated = AggregatedReports()
        self._loaded_files = []

        # Load architecture reports
        self._load_architecture_reports(aggregated)

        # Load test generation reports
        self._load_test_generation_reports(aggregated)

        # Load validation reports
        self._load_validation_reports(aggregated)

        aggregated.report_files_processed = [str(f) for f in self._loaded_files]
        self._aggregated = aggregated

        self.logger.info(
            "runtime_reports_loaded",
            files_processed=len(self._loaded_files),
            arch_score=aggregated.architecture.overall_score,
            anti_patterns=len(aggregated.architecture.anti_patterns),
            high_risk_files=len(aggregated.tests.high_risk_files),
            total_endpoints=aggregated.validation.total_endpoints,
        )

        return aggregated

    def _load_architecture_reports(self, aggregated: AggregatedReports) -> None:
        """Load architecture health reports."""
        # Try consolidated report first
        consolidated = self.output_dir / self.ARCHITECTURE_HEALTH
        if consolidated.exists():
            try:
                data = json.loads(consolidated.read_text(encoding="utf-8"))
                self._process_architecture_report(data, aggregated)
                self._loaded_files.append(consolidated)
            except Exception as e:
                self.logger.warning("failed_to_load_architecture_report", file=str(consolidated), error=str(e))

        # Also try assessment file
        assessment = self.output_dir / self.ARCHITECTURE_ASSESSMENT
        if assessment.exists():
            try:
                data = json.loads(assessment.read_text(encoding="utf-8"))
                self._process_architecture_report(data, aggregated)
                self._loaded_files.append(assessment)
            except Exception as e:
                self.logger.warning("failed_to_load_assessment", file=str(assessment), error=str(e))

        # Load timestamped reports (use latest if multiple)
        arch_files = sorted(self.output_dir.glob(self.ARCHITECTURE_PATTERN), reverse=True)
        for arch_file in arch_files[:3]:  # Only process latest 3
            try:
                data = json.loads(arch_file.read_text(encoding="utf-8"))
                self._process_architecture_report(data, aggregated)
                self._loaded_files.append(arch_file)
            except Exception as e:
                self.logger.warning("failed_to_load_arch_file", file=str(arch_file), error=str(e))

    def _process_architecture_report(self, data: dict, aggregated: AggregatedReports) -> None:
        """Process a single architecture report."""
        # Extract overall score
        if "overall_health_score" in data:
            score = data["overall_health_score"]
            if score > aggregated.architecture.overall_score:
                aggregated.architecture.overall_score = score

        # Extract scores with issues
        for score in data.get("scores", []):
            score_val = score.get("score", 10)
            if score_val < 6:
                aggregated.architecture.worst_metrics.append({
                    "metric": score.get("metric"),
                    "score": score_val,
                    "issues": score.get("issues", [])[:3],
                })

        # Extract anti-patterns
        for ap in data.get("anti_patterns", []):
            if isinstance(ap, dict):
                if ap not in aggregated.architecture.anti_patterns:
                    aggregated.architecture.anti_patterns.append(ap)
            elif isinstance(ap, str):
                if {"name": ap} not in aggregated.architecture.anti_patterns:
                    aggregated.architecture.anti_patterns.append({"name": ap})

        # Extract critical recommendations
        for rec in data.get("overall_recommendations", []):
            if isinstance(rec, dict):
                priority = rec.get("priority", "medium")
                if priority in ("critical", "high"):
                    if rec not in aggregated.architecture.critical_recommendations:
                        aggregated.architecture.critical_recommendations.append(rec)

    def _load_test_generation_reports(self, aggregated: AggregatedReports) -> None:
        """Load test generation priority reports."""
        test_files = sorted(self.output_dir.glob(self.TEST_GENERATION_PATTERN), reverse=True)

        seen_files = set()
        for test_file in test_files:
            try:
                data = json.loads(test_file.read_text(encoding="utf-8"))
                self._loaded_files.append(test_file)

                # Extract priority files
                for pf in data.get("priority_files", []):
                    file_path = pf.get("file", "")
                    if file_path and file_path not in seen_files:
                        seen_files.add(file_path)
                        risk = pf.get("risk", "medium")
                        entry = {
                            "file": file_path,
                            "reason": pf.get("reason", ""),
                            "risk": risk,
                        }
                        if risk == "high":
                            aggregated.tests.high_risk_files.append(entry)
                        else:
                            aggregated.tests.medium_risk_files.append(entry)

                # Track coverage estimate (use latest)
                if "coverage_estimate" in data:
                    aggregated.tests.coverage_estimate = data["coverage_estimate"]

            except Exception as e:
                self.logger.warning("failed_to_load_test_report", file=str(test_file), error=str(e))

    def _load_validation_reports(self, aggregated: AggregatedReports) -> None:
        """Load CRUD and validation reports."""
        # CRUD validation
        crud_file = self.output_dir / self.CRUD_VALIDATION
        if crud_file.exists():
            try:
                data = json.loads(crud_file.read_text(encoding="utf-8"))
                self._loaded_files.append(crud_file)

                summary = data.get("summary", {})
                aggregated.validation.total_endpoints = summary.get("totalEndpoints", 0)
                aggregated.validation.total_entities = summary.get("totalEntities", 0)
                aggregated.validation.full_crud_sets = summary.get("fullCRUDSets", 0)
                aggregated.validation.route_files = data.get("routeFiles", [])

            except Exception as e:
                self.logger.warning("failed_to_load_crud_validation", error=str(e))

        # Validation exceptions
        exceptions_file = self.output_dir / self.VALIDATION_EXCEPTIONS
        if exceptions_file.exists():
            try:
                data = json.loads(exceptions_file.read_text(encoding="utf-8"))
                self._loaded_files.append(exceptions_file)

                aggregated.validation.entity_exceptions = data.get("entity_clarifications", {})

            except Exception as e:
                self.logger.warning("failed_to_load_validation_exceptions", error=str(e))

    def cleanup(self, keep_consolidated: bool = True) -> int:
        """
        Delete processed report files.

        Args:
            keep_consolidated: If True, keep architecture-health-report.json

        Returns:
            Number of files deleted
        """
        deleted = 0

        for file_path in self._loaded_files:
            # Optionally keep consolidated reports
            if keep_consolidated and file_path.name in (
                self.ARCHITECTURE_HEALTH,
                self.CRUD_VALIDATION,
            ):
                continue

            try:
                if file_path.exists():
                    file_path.unlink()
                    deleted += 1
                    self.logger.debug("deleted_report_file", file=str(file_path))
            except Exception as e:
                self.logger.warning("failed_to_delete_report", file=str(file_path), error=str(e))

        self.logger.info("runtime_reports_cleaned", deleted=deleted)
        self._loaded_files = []
        return deleted

    def get_aggregated(self) -> Optional[AggregatedReports]:
        """Get previously loaded aggregated reports."""
        return self._aggregated

    def has_actionable_insights(self) -> bool:
        """Check if reports contain actionable insights for improvement."""
        if not self._aggregated:
            return False

        return (
            self._aggregated.has_architecture_issues() or
            len(self._aggregated.tests.high_risk_files) > 0
        )
