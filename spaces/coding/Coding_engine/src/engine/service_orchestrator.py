"""Service Orchestrator — orchestrates generation of all services in dependency order."""
from __future__ import annotations

import logging
from pathlib import Path

from src.engine.spec_parser import ParsedSpec
from src.engine.skeleton_generator import SkeletonGenerator
from src.engine.service_pipeline import ServicePipeline, ServiceResult
from src.engine.code_fill_agent import CodeFillAgent
from src.engine.context_injector import ContextInjector
from src.engine.validation_engine import ValidationEngine
from src.engine.traceability_tracker import TraceabilityTracker

logger = logging.getLogger(__name__)


class ServiceOrchestrator:
    def __init__(self, spec: ParsedSpec, output_dir: str | Path, tool=None):
        self.spec = spec
        self.output_dir = Path(output_dir)
        self.tool = tool
        self.completed: dict[str, Path] = {}
        self.tracker = TraceabilityTracker()
        self.tracker.register_from_spec(spec)

    def run_skeleton_only(self) -> dict[str, Path]:
        gen = SkeletonGenerator(self.spec, self.output_dir)
        return gen.generate_all()

    async def run_all(self, resume_from: str | None = None) -> dict[str, ServiceResult]:
        skeleton_dirs = self.run_skeleton_only()

        start_idx = 0
        if resume_from and resume_from in self.spec.generation_order:
            start_idx = self.spec.generation_order.index(resume_from)
            # Mark prior services as completed
            for svc_name in self.spec.generation_order[:start_idx]:
                if svc_name in skeleton_dirs:
                    self.completed[svc_name] = skeleton_dirs[svc_name]
            logger.info("Resuming from %s (skipping %d completed)", resume_from, start_idx)

        results: dict[str, ServiceResult] = {}
        for svc_name in self.spec.generation_order[start_idx:]:
            svc = self.spec.services[svc_name]
            svc_dir = skeleton_dirs[svc_name]
            logger.info("=== Generating %s (%d endpoints) ===", svc_name, len(svc.endpoints))

            agent = CodeFillAgent(self.tool)
            injector = ContextInjector(self.spec, self.completed)
            engine = ValidationEngine()
            pipeline = ServicePipeline(agent, injector, engine, self.tracker)

            try:
                result = await pipeline.execute(svc, svc_dir)
                results[svc_name] = result
                self.completed[svc_name] = svc_dir
            except Exception as e:
                logger.error("Service %s failed: %s — continuing with next", svc_name, e)
                continue

            logger.info("=== %s: %s (%d files) ===", svc_name, result.status, len(result.filled_files))

        self.tracker.save_json(self.output_dir / "traceability.json")
        self.tracker.save_markdown(self.output_dir / "TRACEABILITY.md")
        return results

    async def run_single(self, service_name: str) -> ServiceResult:
        if service_name not in self.spec.services:
            raise ValueError(f"Unknown service: {service_name}")
        svc = self.spec.services[service_name]
        svc_dir = self.output_dir / service_name
        gen = SkeletonGenerator(self.spec, self.output_dir)
        gen.generate_service(svc, svc_dir)
        agent = CodeFillAgent(self.tool)
        injector = ContextInjector(self.spec, self.completed)
        engine = ValidationEngine()
        pipeline = ServicePipeline(agent, injector, engine, self.tracker)
        return await pipeline.execute(svc, svc_dir)
