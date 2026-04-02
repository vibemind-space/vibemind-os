"""
Parallel Executor - High-level executor for the coding engine.

This module provides:
1. End-to-end job execution from JSON to files
2. Progress tracking and reporting
3. File assembly and output
"""
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import structlog

from src.engine.dag_parser import DAGParser
from src.engine.slicer import Slicer, SliceManifest
from src.engine.project_context import ProjectContext, create_project_context
from src.autogen.orchestrator import AutoGenOrchestrator, JobResult
from src.autogen.cli_wrapper import GeneratedFile

logger = structlog.get_logger()


@dataclass
class ExecutionProgress:
    """Progress information for job execution."""
    job_id: int
    status: str  # pending, parsing, slicing, executing, assembling, completed, failed
    total_slices: int = 0
    completed_slices: int = 0
    failed_slices: int = 0
    current_batch: int = 0
    total_batches: int = 0
    files_generated: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        if self.total_slices == 0:
            return 0.0
        return (self.completed_slices / self.total_slices) * 100

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total_slices": self.total_slices,
            "completed_slices": self.completed_slices,
            "failed_slices": self.failed_slices,
            "current_batch": self.current_batch,
            "total_batches": self.total_batches,
            "progress_percent": self.progress_percent,
            "files_generated": self.files_generated,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error,
        }


class ParallelExecutor:
    """
    High-level executor that runs the entire pipeline.

    Pipeline:
    1. Parse requirements JSON
    2. Build DAG
    3. Slice into parallel batches
    4. Execute with AutoGen + CLI
    5. Assemble output files
    """

    def __init__(
        self,
        output_dir: str,
        max_concurrent: int = 5,
        slice_size: int = 10,
        progress_callback: Optional[Callable[[ExecutionProgress], None]] = None,
    ):
        self.output_dir = Path(output_dir)
        self.max_concurrent = max_concurrent
        self.slice_size = slice_size
        self.progress_callback = progress_callback

        self.parser = DAGParser()
        self.slicer = Slicer(slice_size, working_dir=str(self.output_dir))

        self.logger = logger.bind(component="parallel_executor")

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute_from_file(
        self,
        requirements_file: str,
        job_id: int = 1,
    ) -> JobResult:
        """Execute from a requirements JSON file."""
        with open(requirements_file, 'r', encoding='utf-8') as f:
            requirements_json = f.read()

        return await self.execute(requirements_json, job_id)

    async def execute(
        self,
        requirements_json: str,
        job_id: int = 1,
    ) -> JobResult:
        """
        Execute the complete pipeline.

        Args:
            requirements_json: JSON string with requirements
            job_id: Job ID for tracking

        Returns:
            JobResult with all generated files
        """
        progress = ExecutionProgress(
            job_id=job_id,
            status="parsing",
            start_time=datetime.now(),
        )
        self._report_progress(progress)

        try:
            # Step 1: Parse requirements
            self.logger.info("step_1_parsing", job_id=job_id)
            data = json.loads(requirements_json)
            req_data = self.parser.parse(data)

            # Step 2: Create slices
            progress.status = "slicing"
            self._report_progress(progress)

            self.logger.info("step_2_slicing", job_id=job_id)
            manifest = self.slicer.slice_requirements(
                req_data, job_id, strategy="hybrid"
            )

            progress.total_slices = manifest.total_slices
            self._report_progress(progress)

            # Step 2.5: Create project context for all agents
            self.logger.info("creating_project_context", job_id=job_id)
            project_context = create_project_context(
                req_data=req_data,
                manifest=manifest,
                project_name=f"Job-{job_id}",
            )

            # Step 3: Execute with AutoGen
            progress.status = "executing"
            self._report_progress(progress)

            self.logger.info(
                "step_3_executing",
                job_id=job_id,
                slices=manifest.total_slices,
                project=project_context.project_name,
            )

            orchestrator = AutoGenOrchestrator(
                working_dir=str(self.output_dir),
                max_concurrent=self.max_concurrent,
                project_context=project_context,
            )

            result = await orchestrator.execute_job(manifest)

            # Update progress from result
            progress.completed_slices = result.completed_slices
            progress.failed_slices = result.failed_slices
            progress.files_generated = len(result.all_files)

            # Step 4: Write output files
            progress.status = "assembling"
            self._report_progress(progress)

            self.logger.info(
                "step_4_assembling",
                job_id=job_id,
                files=len(result.all_files),
            )

            await self._write_output_files(result.all_files, job_id)

            # Complete
            progress.status = "completed"
            progress.end_time = datetime.now()
            self._report_progress(progress)

            self.logger.info(
                "execution_complete",
                job_id=job_id,
                success=result.success,
                files=len(result.all_files),
            )

            return result

        except Exception as e:
            self.logger.error("execution_failed", job_id=job_id, error=str(e))
            progress.status = "failed"
            progress.error = str(e)
            progress.end_time = datetime.now()
            self._report_progress(progress)
            raise

    async def _write_output_files(
        self,
        files: list[GeneratedFile],
        job_id: int,
    ):
        """Write generated files to the output directory."""
        job_dir = self.output_dir / f"job_{job_id}"
        job_dir.mkdir(exist_ok=True)

        for file in files:
            # Create full path
            file_path = job_dir / file.path

            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file.content)

            self.logger.debug("file_written", path=str(file_path))

        # Write manifest
        manifest_path = job_dir / "manifest.json"
        manifest_data = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "files": [
                {"path": f.path, "language": f.language}
                for f in files
            ],
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2)

    def _report_progress(self, progress: ExecutionProgress):
        """Report progress via callback if available."""
        if self.progress_callback:
            self.progress_callback(progress)


async def main():
    """CLI entry point for running the executor."""
    import argparse

    parser = argparse.ArgumentParser(description="Execute coding engine job")
    parser.add_argument(
        "requirements_file",
        help="Path to requirements JSON file",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        default=1,
        help="Job ID for tracking",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent CLI calls",
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=10,
        help="Requirements per slice",
    )

    args = parser.parse_args()

    def print_progress(progress: ExecutionProgress):
        print(f"[{progress.status}] {progress.progress_percent:.1f}% "
              f"({progress.completed_slices}/{progress.total_slices} slices)")

    executor = ParallelExecutor(
        output_dir=args.output_dir,
        max_concurrent=args.max_concurrent,
        slice_size=args.slice_size,
        progress_callback=print_progress,
    )

    result = await executor.execute_from_file(
        args.requirements_file,
        args.job_id,
    )

    print(f"\nJob complete!")
    print(f"  Success: {result.success}")
    print(f"  Slices: {result.completed_slices}/{result.total_slices}")
    print(f"  Files generated: {len(result.all_files)}")
    print(f"  Time: {result.total_execution_time_ms}ms")


if __name__ == "__main__":
    asyncio.run(main())
