"""Pipeline progress reporter.

Reports and tracks pipeline execution progress as percentage.
Each report tracks a pipeline's step-by-step progress, including
completed steps, total steps, and a computed completion percentage.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProgressReport:
    """A single progress report entry."""
    report_id: str = ""
    pipeline_id: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    percentage: float = 0.0
    message: str = ""
    created_at: float = 0.0
    seq: int = 0


class PipelineProgressReporter:
    """Reports and tracks pipeline execution progress as percentage."""

    def __init__(self, max_entries: int = 10000):
        self._reports: Dict[str, ProgressReport] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._seq: int = 0
        self._max_entries = max(1, max_entries)

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self, seed: str) -> str:
        """Generate a unique ID with prefix 'ppr-'."""
        self._seq += 1
        raw = f"{seed}:{time.time()}:{self._seq}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"ppr-{digest}"

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove oldest entries when at capacity."""
        if len(self._reports) < self._max_entries:
            return
        sorted_reports = sorted(
            self._reports.values(), key=lambda r: (r.created_at, r.seq)
        )
        remove_count = len(self._reports) - self._max_entries + 1
        for report in sorted_reports[:remove_count]:
            del self._reports[report.report_id]

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def start_report(self, pipeline_id: str, total_steps: int) -> str:
        """Start a progress report for a pipeline.

        Args:
            pipeline_id: Identifier of the pipeline being tracked.
            total_steps: Total number of steps in the pipeline.

        Returns:
            The report ID, or empty string on failure.
        """
        if not pipeline_id or total_steps <= 0:
            return ""

        self._prune_if_needed()

        report_id = self._next_id(pipeline_id)
        now = time.time()

        self._reports[report_id] = ProgressReport(
            report_id=report_id,
            pipeline_id=pipeline_id,
            total_steps=total_steps,
            completed_steps=0,
            percentage=0.0,
            message="",
            created_at=now,
            seq=self._seq,
        )

        logger.info(
            "progress_report_started",
            report_id=report_id,
            pipeline_id=pipeline_id,
            total_steps=total_steps,
        )
        self._fire("report_started", {
            "report_id": report_id,
            "pipeline_id": pipeline_id,
            "total_steps": total_steps,
        })
        return report_id

    def update_progress(
        self, report_id: str, completed_steps: int, message: str = ""
    ) -> bool:
        """Update progress for an existing report.

        Args:
            report_id: The report to update.
            completed_steps: Number of steps completed so far.
            message: Optional status message.

        Returns:
            True if updated successfully, False otherwise.
        """
        report = self._reports.get(report_id)
        if not report:
            return False
        if completed_steps < 0 or completed_steps > report.total_steps:
            return False

        report.completed_steps = completed_steps
        report.percentage = (
            (completed_steps / report.total_steps) * 100.0
            if report.total_steps > 0
            else 0.0
        )
        report.message = message

        logger.info(
            "progress_updated",
            report_id=report_id,
            completed_steps=completed_steps,
            percentage=round(report.percentage, 1),
        )
        self._fire("progress_updated", {
            "report_id": report_id,
            "completed_steps": completed_steps,
            "percentage": report.percentage,
        })
        return True

    def get_progress(self, report_id: str) -> Optional[Dict]:
        """Get progress details for a report.

        Returns:
            Dict with pipeline_id, total_steps, completed_steps,
            percentage, and message; or None if not found.
        """
        report = self._reports.get(report_id)
        if not report:
            return None
        return {
            "pipeline_id": report.pipeline_id,
            "total_steps": report.total_steps,
            "completed_steps": report.completed_steps,
            "percentage": round(report.percentage, 2),
            "message": report.message,
        }

    def get_latest_report(self, pipeline_id: str) -> Optional[Dict]:
        """Get the most recent report for a pipeline.

        Uses (created_at, seq) for ordering to break ties.

        Returns:
            Dict with progress details, or None if no reports exist.
        """
        matching = [
            r for r in self._reports.values()
            if r.pipeline_id == pipeline_id
        ]
        if not matching:
            return None

        latest = max(matching, key=lambda r: (r.created_at, r.seq))
        return {
            "pipeline_id": latest.pipeline_id,
            "total_steps": latest.total_steps,
            "completed_steps": latest.completed_steps,
            "percentage": round(latest.percentage, 2),
            "message": latest.message,
        }

    def list_pipelines(self) -> List[str]:
        """List all pipeline IDs that have reports."""
        seen: Dict[str, None] = {}
        for r in self._reports.values():
            if r.pipeline_id not in seen:
                seen[r.pipeline_id] = None
        return list(seen.keys())

    def get_report_count(self) -> int:
        """Get the total number of active reports."""
        return len(self._reports)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_change(self, name: str, cb: Callable) -> bool:
        """Register a change callback."""
        if name in self._callbacks:
            return False
        self._callbacks[name] = cb
        return True

    def remove_callback(self, name: str) -> bool:
        """Remove a registered callback."""
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Get reporter statistics."""
        return {
            "total_reports": len(self._reports),
            "unique_pipelines": len(self.list_pipelines()),
            "max_entries": self._max_entries,
            "seq": self._seq,
        }

    def reset(self) -> None:
        """Reset all state."""
        self._reports.clear()
        self._callbacks.clear()
        self._seq = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire(self, action: str, detail: Dict) -> None:
        """Fire all registered callbacks."""
        for cb in list(self._callbacks.values()):
            try:
                cb(action, detail)
            except Exception:
                pass
