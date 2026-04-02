"""
AutoGen Orchestrator - Coordinates multi-agent code generation.

This orchestrator:
1. Takes a SliceManifest as input
2. Executes slices in parallel batches
3. Uses specialized agents for each slice type
4. Assembles results from all agents
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import structlog

from src.engine.slicer import SliceManifest, TaskSlice
from src.autogen.cli_wrapper import ClaudeCLI, ClaudeCLIPool, CLIResponse, GeneratedFile
from src.engine.project_context import ProjectContext

logger = structlog.get_logger()


@dataclass
class SliceResult:
    """Result from processing a single slice."""
    slice_id: str
    success: bool
    files: list[GeneratedFile] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class JobResult:
    """Result from processing an entire job."""
    job_id: int
    success: bool
    total_slices: int
    completed_slices: int
    failed_slices: int
    all_files: list[GeneratedFile] = field(default_factory=list)
    slice_results: list[SliceResult] = field(default_factory=list)
    total_execution_time_ms: int = 0


# System prompts for each agent type
AGENT_PROMPTS = {
    "frontend": """You are an expert frontend developer.
Implement the following UI requirements.
Output complete, working code files with proper TypeScript types.
Use React with functional components and hooks.""",

    "backend": """You are an expert backend developer.
Implement the following API/database requirements.
Output complete Python code using FastAPI and SQLAlchemy.
Include proper error handling and validation.""",

    "testing": """You are an expert QA engineer.
Write comprehensive tests for the following requirements.
Use pytest for Python code.
Include unit tests, edge cases, and error scenarios.""",

    "security": """You are a security expert.
Review the requirements and implement secure code.
Follow OWASP guidelines.
Include input validation and proper authentication.""",

    "devops": """You are a DevOps expert.
Create infrastructure and deployment configurations.
Output Dockerfiles, Kubernetes manifests, or CI/CD pipelines as needed.
Follow security best practices.""",

    "general": """You are a skilled software engineer.
Implement the following requirements.
Output clean, well-documented code.""",
}


class AutoGenOrchestrator:
    """
    Orchestrates multi-agent code generation using Claude CLI.

    Uses parallel execution with dependency awareness.
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        max_concurrent: int = 5,
        project_context: Optional[ProjectContext] = None,
    ):
        self.working_dir = working_dir or str(Path.cwd())
        self.max_concurrent = max_concurrent
        self.cli_pool = ClaudeCLIPool(max_concurrent, working_dir)
        self.project_context = project_context
        self.logger = logger.bind(component="autogen_orchestrator")

    async def execute_job(self, manifest: SliceManifest) -> JobResult:
        """
        Execute all slices in a job.

        Processes slices in parallel batches respecting dependencies.
        """
        import time
        start_time = time.time()

        self.logger.info(
            "starting_job",
            job_id=manifest.job_id,
            total_slices=manifest.total_slices,
        )

        # Get parallel batches from slicer
        from src.engine.slicer import Slicer
        slicer = Slicer(working_dir=self.working_dir)
        batches = slicer.get_parallel_batches(manifest)

        all_results: list[SliceResult] = []
        all_files: list[GeneratedFile] = []
        failed_count = 0

        # Process each batch
        for batch_idx, batch in enumerate(batches):
            self.logger.info(
                "processing_batch",
                batch=batch_idx + 1,
                total_batches=len(batches),
                slices_in_batch=len(batch),
            )

            # Execute batch in parallel
            batch_results = await self._execute_batch(batch)

            for result in batch_results:
                all_results.append(result)
                if result.success:
                    all_files.extend(result.files)
                else:
                    failed_count += 1

        total_time = int((time.time() - start_time) * 1000)

        job_result = JobResult(
            job_id=manifest.job_id,
            success=failed_count == 0,
            total_slices=manifest.total_slices,
            completed_slices=manifest.total_slices - failed_count,
            failed_slices=failed_count,
            all_files=all_files,
            slice_results=all_results,
            total_execution_time_ms=total_time,
        )

        self.logger.info(
            "job_complete",
            job_id=manifest.job_id,
            success=job_result.success,
            files_generated=len(all_files),
            total_time_ms=total_time,
        )

        return job_result

    async def _execute_batch(self, slices: list[TaskSlice]) -> list[SliceResult]:
        """Execute a batch of slices in parallel."""
        # Build prompts for each slice
        prompts: list[tuple[str, str]] = []

        for s in slices:
            prompt = self._build_slice_prompt(s)
            prompts.append((s.slice_id, prompt))

        # Execute all in parallel
        responses = await self.cli_pool.execute_batch(prompts)

        # Convert to SliceResults
        results = []
        for s in slices:
            response = responses.get(s.slice_id)
            if response:
                result = SliceResult(
                    slice_id=s.slice_id,
                    success=response.success,
                    files=response.files,
                    output=response.output,
                    error=response.error,
                    execution_time_ms=response.execution_time_ms,
                )
            else:
                result = SliceResult(
                    slice_id=s.slice_id,
                    success=False,
                    error="No response received",
                )
            results.append(result)

        return results

    def _build_slice_prompt(self, slice: TaskSlice) -> str:
        """Build the prompt for a slice with full project context."""
        # Get agent-specific system prompt
        system_prompt = AGENT_PROMPTS.get(slice.agent_type, AGENT_PROMPTS["general"])

        # Add project context if available
        project_context_str = ""
        if self.project_context:
            project_context_str = self.project_context.to_prompt_context(
                slice.agent_type, slice
            )

        # Build requirement list
        req_list = "\n".join([
            f"- [{r.get('id') or r.get('req_id', '')}] {r.get('label', r.get('title', r.get('description', '')))}"
            for r in slice.requirement_details
        ])

        # Include project context if available
        context_section = ""
        if project_context_str:
            context_section = project_context_str
        else:
            context_section = f"""
## Requirements to Implement

{req_list}
"""

        prompt = f"""{system_prompt}

{context_section}

## Instructions

1. Implement each requirement listed above
2. Create well-structured, production-ready code
3. Use appropriate file organization matching the project structure
4. Include necessary imports and dependencies
5. Add error handling where appropriate
6. Ensure your code integrates with other components

## Output Format

For each file you create, use this format:

```language:path/to/file.ext
// file content here
```

Example:
```typescript:src/components/Button.tsx
import React from 'react';

interface ButtonProps {{
  label: string;
  onClick: () => void;
}}

export const Button: React.FC<ButtonProps> = ({{ label, onClick }}) => {{
  return <button onClick={{onClick}}>{{label}}</button>;
}};
```

Now implement the requirements. Remember to use the correct file paths for your agent type.
"""
        return prompt

    async def execute_single_slice(self, slice: TaskSlice) -> SliceResult:
        """Execute a single slice (for testing or sequential execution)."""
        cli = ClaudeCLI(working_dir=self.working_dir)
        prompt = self._build_slice_prompt(slice)

        response = await cli.execute(prompt)

        return SliceResult(
            slice_id=slice.slice_id,
            success=response.success,
            files=response.files,
            output=response.output,
            error=response.error,
            execution_time_ms=response.execution_time_ms,
        )


async def run_job(
    requirements_json: str,
    job_id: int = 1,
    working_dir: Optional[str] = None,
    max_concurrent: int = 5,
) -> JobResult:
    """
    Convenience function to run a complete job.

    Args:
        requirements_json: JSON string of requirements
        job_id: Job ID for tracking
        working_dir: Working directory for output
        max_concurrent: Max parallel CLI calls

    Returns:
        JobResult with all generated files
    """
    import json
    from src.engine.dag_parser import DAGParser
    from src.engine.slicer import Slicer

    # Parse requirements
    parser = DAGParser()
    data = json.loads(requirements_json)
    req_data = parser.parse(data)

    # Create slices
    slicer = Slicer(working_dir=working_dir)
    manifest = slicer.slice_requirements(req_data, job_id, strategy="hybrid")

    # Execute
    orchestrator = AutoGenOrchestrator(working_dir, max_concurrent)
    result = await orchestrator.execute_job(manifest)

    return result
