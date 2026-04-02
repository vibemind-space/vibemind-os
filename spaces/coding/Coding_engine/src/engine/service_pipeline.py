"""Service-by-Service Pipeline — Prio 3 of Pipeline Improvements."""
from __future__ import annotations

import logging
from pathlib import Path

from src.engine.spec_parser import ParsedService
from src.engine.code_fill_agent import CodeFillAgent, FillResult
from src.engine.context_injector import ContextInjector
from src.engine.validation_engine import ValidationEngine, ValidationReport
from src.engine.traceability_tracker import TraceabilityTracker
from src.validators.base_validator import ValidationSeverity

logger = logging.getLogger(__name__)


class ServiceResult:
    def __init__(self, service_name: str, filled_files: list[Path],
                 report: ValidationReport | None, trace_entries: list):
        self.service_name = service_name
        self.filled_files = filled_files
        self.report = report
        self.trace_entries = trace_entries
        self.status = "COMPLETE" if (report and not report.has_errors()) else "NEEDS_REVIEW"


class ServicePipeline:
    def __init__(self, agent: CodeFillAgent | None,
                 context_injector: ContextInjector | None,
                 validation_engine: ValidationEngine | None,
                 tracker: TraceabilityTracker | None):
        self.agent = agent
        self.context_injector = context_injector
        self.validation_engine = validation_engine
        self.tracker = tracker

    def get_fill_order(self, skeleton_dir: Path) -> list[Path]:
        """Compute fill order for any service based on file types."""
        all_files = list(skeleton_dir.rglob("*.ts")) + list(skeleton_dir.rglob("*.prisma"))
        seen: set[Path] = set()
        order: list[Path] = []

        def add(files):
            for f in sorted(files):
                if f not in seen:
                    seen.add(f)
                    order.append(f)

        add(f for f in all_files if f.name == "schema.prisma")
        add(f for f in all_files if "/shared/" in str(f).replace("\\", "/"))
        add(f for f in all_files if f.name.endswith(".service.ts"))
        add(f for f in all_files if f.name.endswith(".controller.ts"))
        add(f for f in all_files if "/dto/" in str(f).replace("\\", "/"))
        add(f for f in all_files if "/guards/" in str(f).replace("\\", "/") or "/middleware/" in str(f).replace("\\", "/"))
        add(f for f in all_files if f.name.endswith(".module.ts") and "app.module" not in f.name)
        add(f for f in all_files if "app.module" in f.name)
        add(f for f in all_files if f.name.endswith(".spec.ts"))
        add(f for f in all_files if f not in seen)

        return order

    async def execute(self, service: ParsedService, skeleton_dir: Path,
                      max_recovery: int = 3) -> ServiceResult:
        """Run the full fill+validate+recover loop for one service."""
        filled_files: list[Path] = []
        unfilled_files: list[Path] = []

        # Phase 1: File-by-file agent fill
        for file in self.get_fill_order(skeleton_dir):
            if self.agent and self.context_injector:
                context = self.context_injector.get_context_for(file, service)
                result = await self.agent.fill(file, context)
                if result.success and result.content:
                    file.write_text(result.content, encoding="utf-8")
                    filled_files.append(file)
                else:
                    result2 = await self.agent.fill(file, context)
                    if result2.success and result2.content:
                        file.write_text(result2.content, encoding="utf-8")
                        filled_files.append(file)
                    else:
                        unfilled_files.append(file)
                        logger.warning("UNFILLED: %s (agent failed twice)", file.name)
            else:
                filled_files.append(file)

        # Phase 2: Validation + Recovery loop
        report = None
        if self.validation_engine:
            for attempt in range(max_recovery):
                report = self.validation_engine.validate_service(service, skeleton_dir)
                if not report.has_errors():
                    break
                if not self.agent or attempt == max_recovery - 1:
                    logger.warning("Recovery exhausted for %s after %d attempts", service.name, attempt + 1)
                    break
                error_files = {Path(i.file_path) for i in report.issues
                               if i.severity == ValidationSeverity.ERROR and i.file_path}
                for file in error_files:
                    if file.exists() and self.context_injector:
                        context = self.context_injector.get_context_for(file, service)
                        result = await self.agent.fill(file, context)
                        if result.success and result.content:
                            file.write_text(result.content, encoding="utf-8")

        trace_entries = []
        if self.tracker:
            trace_entries = self.tracker.get_entries(service.name)
            status = "IMPLEMENTED" if (report and not report.has_errors()) else "PARTIAL"
            for entry in trace_entries:
                self.tracker.update_status(entry.requirement_id, service.name, status)

        return ServiceResult(service.name, filled_files, report, trace_entries)
