"""
Code Quality Gate — Automated code quality scoring and gating.

Provides:
- Multi-dimension quality scoring (complexity, style, coverage, security, docs)
- Configurable pass/fail thresholds
- Quality trend tracking across runs
- Per-file and aggregate scoring
- Quality report generation
- Gate enforcement (block pipeline on low quality)

Usage:
    gate = CodeQualityGate(min_score=70.0)

    # Score a file
    gate.score_file("main.py", metrics={
        "complexity": 5,
        "lines": 120,
        "functions": 8,
        "docstring_coverage": 0.75,
        "test_coverage": 0.85,
        "lint_issues": 2,
    })

    # Check if quality gate passes
    result = gate.check_gate()
    if not result.passed:
        print(f"Quality gate failed: {result.score} < {result.threshold}")
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class QualityDimension(str, Enum):
    COMPLEXITY = "complexity"
    STYLE = "style"
    COVERAGE = "coverage"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    MAINTAINABILITY = "maintainability"


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class FileScore:
    """Quality score for a single file."""
    file_path: str
    scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    overall_score: float = 0.0
    scored_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "overall_score": round(self.overall_score, 1),
            "scores": {k: round(v, 1) for k, v in self.scores.items()},
            "issues": self.issues[:20],
            "issue_count": len(self.issues),
            "metrics": self.metrics,
        }


@dataclass
class GateResult:
    """Result of a quality gate check."""
    gate_id: str
    status: GateStatus
    score: float
    threshold: float
    file_count: int
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    failing_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return self.status in (GateStatus.PASSED, GateStatus.WARNING)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "score": round(self.score, 1),
            "threshold": self.threshold,
            "passed": self.passed,
            "file_count": self.file_count,
            "dimension_scores": {k: round(v, 1) for k, v in self.dimension_scores.items()},
            "failing_files": self.failing_files[:20],
            "warnings": self.warnings[:10],
        }


class CodeQualityGate:
    """Automated code quality scoring and gating system."""

    def __init__(
        self,
        min_score: float = 70.0,
        warning_score: float = 80.0,
        dimension_weights: Optional[Dict[str, float]] = None,
        file_min_score: float = 50.0,
    ):
        self._min_score = min_score
        self._warning_score = warning_score
        self._file_min_score = file_min_score

        # Dimension weights (must sum to ~1.0)
        self._weights = dimension_weights or {
            QualityDimension.COMPLEXITY.value: 0.25,
            QualityDimension.STYLE.value: 0.15,
            QualityDimension.COVERAGE.value: 0.25,
            QualityDimension.SECURITY.value: 0.15,
            QualityDimension.DOCUMENTATION.value: 0.10,
            QualityDimension.MAINTAINABILITY.value: 0.10,
        }

        # File scores
        self._file_scores: Dict[str, FileScore] = {}

        # Gate history
        self._gate_history: List[GateResult] = []
        self._max_history = 50

        # Stats
        self._total_files_scored = 0
        self._total_gate_checks = 0
        self._total_passed = 0
        self._total_failed = 0

    @property
    def min_score(self) -> float:
        return self._min_score

    @property
    def weights(self) -> Dict[str, float]:
        return dict(self._weights)

    # ── File Scoring ──────────────────────────────────────────────────

    def score_file(
        self,
        file_path: str,
        metrics: Dict[str, Any],
    ) -> FileScore:
        """Score a file based on provided metrics."""
        scores = {}
        issues = []

        # Complexity score (lower is better)
        complexity = metrics.get("complexity", 0)
        if complexity <= 5:
            scores["complexity"] = 100.0
        elif complexity <= 10:
            scores["complexity"] = 80.0
        elif complexity <= 20:
            scores["complexity"] = 60.0
        elif complexity <= 30:
            scores["complexity"] = 40.0
        else:
            scores["complexity"] = 20.0
            issues.append(f"High complexity: {complexity}")

        # Style score (lint issues)
        lint_issues = metrics.get("lint_issues", 0)
        lines = max(metrics.get("lines", 1), 1)
        issue_density = lint_issues / lines * 100

        if issue_density == 0:
            scores["style"] = 100.0
        elif issue_density < 1:
            scores["style"] = 90.0
        elif issue_density < 3:
            scores["style"] = 70.0
        elif issue_density < 5:
            scores["style"] = 50.0
        else:
            scores["style"] = 30.0
            issues.append(f"High lint issue density: {issue_density:.1f}%")

        # Coverage score
        test_coverage = metrics.get("test_coverage", 0.0)
        scores["coverage"] = min(test_coverage * 100, 100.0)
        if test_coverage < 0.5:
            issues.append(f"Low test coverage: {test_coverage:.0%}")

        # Security score
        security_issues = metrics.get("security_issues", 0)
        if security_issues == 0:
            scores["security"] = 100.0
        elif security_issues <= 2:
            scores["security"] = 70.0
            issues.append(f"Security issues found: {security_issues}")
        else:
            scores["security"] = 30.0
            issues.append(f"Critical: {security_issues} security issues")

        # Documentation score
        docstring_coverage = metrics.get("docstring_coverage", 0.0)
        scores["documentation"] = min(docstring_coverage * 100, 100.0)
        if docstring_coverage < 0.3:
            issues.append(f"Low documentation coverage: {docstring_coverage:.0%}")

        # Maintainability score (based on file size and function count)
        functions = max(metrics.get("functions", 1), 1)
        avg_func_length = lines / functions

        if avg_func_length <= 20:
            scores["maintainability"] = 100.0
        elif avg_func_length <= 40:
            scores["maintainability"] = 80.0
        elif avg_func_length <= 60:
            scores["maintainability"] = 60.0
        else:
            scores["maintainability"] = 40.0
            issues.append(f"Long functions: avg {avg_func_length:.0f} lines")

        # Calculate weighted overall score
        overall = 0.0
        for dim, weight in self._weights.items():
            if dim in scores:
                overall += scores[dim] * weight

        file_score = FileScore(
            file_path=file_path,
            scores=scores,
            issues=issues,
            metrics=metrics,
            overall_score=overall,
        )

        self._file_scores[file_path] = file_score
        self._total_files_scored += 1

        logger.debug(
            "file_scored",
            component="code_quality_gate",
            file=file_path,
            score=round(overall, 1),
            issues=len(issues),
        )

        return file_score

    def get_file_score(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get score for a specific file."""
        fs = self._file_scores.get(file_path)
        return fs.to_dict() if fs else None

    def get_all_scores(self) -> List[Dict[str, Any]]:
        """Get scores for all files, sorted by score ascending."""
        scores = sorted(
            self._file_scores.values(),
            key=lambda s: s.overall_score,
        )
        return [s.to_dict() for s in scores]

    # ── Gate Check ────────────────────────────────────────────────────

    def check_gate(self) -> GateResult:
        """Check if the quality gate passes."""
        gate_id = f"gate-{uuid.uuid4().hex[:8]}"
        self._total_gate_checks += 1

        if not self._file_scores:
            result = GateResult(
                gate_id=gate_id,
                status=GateStatus.SKIPPED,
                score=0.0,
                threshold=self._min_score,
                file_count=0,
            )
            self._gate_history.append(result)
            return result

        # Calculate aggregate dimension scores
        dimension_scores = {}
        for dim in self._weights:
            dim_values = [
                fs.scores.get(dim, 0)
                for fs in self._file_scores.values()
                if dim in fs.scores
            ]
            if dim_values:
                dimension_scores[dim] = sum(dim_values) / len(dim_values)

        # Calculate overall score
        overall = 0.0
        for dim, weight in self._weights.items():
            if dim in dimension_scores:
                overall += dimension_scores[dim] * weight

        # Find failing files
        failing_files = [
            fp for fp, fs in self._file_scores.items()
            if fs.overall_score < self._file_min_score
        ]

        # Determine status
        warnings = []
        if overall >= self._warning_score:
            status = GateStatus.PASSED
        elif overall >= self._min_score:
            status = GateStatus.WARNING
            warnings.append(f"Score {overall:.1f} below warning threshold {self._warning_score}")
        else:
            status = GateStatus.FAILED
            warnings.append(f"Score {overall:.1f} below minimum {self._min_score}")

        if failing_files:
            warnings.append(f"{len(failing_files)} files below minimum score {self._file_min_score}")

        if status == GateStatus.PASSED or status == GateStatus.WARNING:
            self._total_passed += 1
        else:
            self._total_failed += 1

        result = GateResult(
            gate_id=gate_id,
            status=status,
            score=overall,
            threshold=self._min_score,
            file_count=len(self._file_scores),
            dimension_scores=dimension_scores,
            failing_files=failing_files,
            warnings=warnings,
        )

        self._gate_history.append(result)
        if len(self._gate_history) > self._max_history:
            self._gate_history.pop(0)

        logger.info(
            "gate_checked",
            component="code_quality_gate",
            gate_id=gate_id,
            status=status.value,
            score=round(overall, 1),
            threshold=self._min_score,
            file_count=len(self._file_scores),
        )

        return result

    # ── Reports ───────────────────────────────────────────────────────

    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive quality report."""
        gate_result = self.check_gate()

        # Top issues across all files
        all_issues = []
        for fs in self._file_scores.values():
            for issue in fs.issues:
                all_issues.append({"file": fs.file_path, "issue": issue})

        # Worst files
        worst_files = sorted(
            self._file_scores.values(),
            key=lambda s: s.overall_score,
        )[:5]

        # Best files
        best_files = sorted(
            self._file_scores.values(),
            key=lambda s: -s.overall_score,
        )[:5]

        return {
            "gate_result": gate_result.to_dict(),
            "summary": {
                "total_files": len(self._file_scores),
                "average_score": round(gate_result.score, 1),
                "passing_files": sum(
                    1 for fs in self._file_scores.values()
                    if fs.overall_score >= self._file_min_score
                ),
                "failing_files": len(gate_result.failing_files),
                "total_issues": len(all_issues),
            },
            "dimension_scores": {
                k: round(v, 1)
                for k, v in gate_result.dimension_scores.items()
            },
            "worst_files": [f.to_dict() for f in worst_files],
            "best_files": [f.to_dict() for f in best_files],
            "top_issues": all_issues[:20],
        }

    # ── History & Trends ──────────────────────────────────────────────

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get gate check history."""
        return [r.to_dict() for r in reversed(self._gate_history)][:limit]

    def get_trend(self) -> Dict[str, Any]:
        """Get quality trend over recent gate checks."""
        if len(self._gate_history) < 2:
            return {"trend": "insufficient_data", "checks": len(self._gate_history)}

        scores = [r.score for r in self._gate_history]
        recent = scores[-5:] if len(scores) >= 5 else scores
        older = scores[:-5] if len(scores) > 5 else scores[:1]

        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        delta = avg_recent - avg_older

        if delta > 2:
            trend = "improving"
        elif delta < -2:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "current_score": round(scores[-1], 1),
            "average_recent": round(avg_recent, 1),
            "delta": round(delta, 1),
            "checks": len(scores),
        }

    # ── Configuration ─────────────────────────────────────────────────

    def set_threshold(self, min_score: float, warning_score: Optional[float] = None):
        """Update quality thresholds."""
        self._min_score = min_score
        if warning_score is not None:
            self._warning_score = warning_score

    def set_weight(self, dimension: str, weight: float):
        """Update weight for a quality dimension."""
        self._weights[dimension] = weight

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get quality gate statistics."""
        return {
            "total_files_scored": self._total_files_scored,
            "total_gate_checks": self._total_gate_checks,
            "total_passed": self._total_passed,
            "total_failed": self._total_failed,
            "pass_rate": round(
                self._total_passed / max(self._total_gate_checks, 1) * 100, 1
            ),
            "current_file_count": len(self._file_scores),
            "min_score": self._min_score,
            "warning_score": self._warning_score,
        }

    def reset(self):
        """Reset all scoring data."""
        self._file_scores.clear()
        self._gate_history.clear()
        self._total_files_scored = 0
        self._total_gate_checks = 0
        self._total_passed = 0
        self._total_failed = 0
