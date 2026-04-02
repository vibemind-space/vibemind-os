"""
A/B Solution Generator - Generate multiple solutions in parallel, vote on best.

Uses Kilo CLI parallel mode for branch-isolated generation and VotingAI
for democratic selection of the best solution.
"""

import asyncio
import structlog
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime

from src.autogen.kilo_cli_wrapper import KiloCLIParallel, KiloParallelResult
from src.mind.fix_voter import FixVoter, ProposedFix, ErrorContext, VotingResult, VotingMethod


logger = structlog.get_logger(__name__)


class SolutionStatus(Enum):
    """Status of a generated solution."""
    PENDING = "pending"
    GENERATED = "generated"
    BUILD_PASSED = "build_passed"
    BUILD_FAILED = "build_failed"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    SELECTED = "selected"
    REJECTED = "rejected"


@dataclass
class GeneratedSolution:
    """A single generated solution from parallel execution."""
    id: str
    branch_name: str
    worker_id: str
    status: SolutionStatus = SolutionStatus.PENDING
    files: list[dict] = field(default_factory=list)
    build_output: Optional[str] = None
    test_output: Optional[str] = None
    build_passed: bool = False
    test_passed: bool = False
    error_count: int = 0
    warning_count: int = 0
    execution_time_ms: int = 0
    quality_score: float = 0.0
    stability_score: float = 0.0
    minimal_change_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ABGenerationResult:
    """Result of A/B solution generation and voting."""
    winner: Optional[GeneratedSolution]
    alternatives: list[GeneratedSolution]
    voting_result: Optional[VotingResult]
    total_solutions: int
    successful_builds: int
    successful_tests: int
    generation_time_ms: int
    voting_time_ms: int
    merged: bool = False
    merge_error: Optional[str] = None


class ABSolutionGenerator:
    """
    Generate A/B solutions in parallel using Kilo CLI, vote on best.

    Workflow:
    1. Generate N solutions in parallel (separate git branches)
    2. Build and test each solution
    3. Vote on best solution using FixVoter
    4. Merge winning branch back to main
    """

    def __init__(
        self,
        working_dir: str,
        max_parallel: int = 3,
        timeout: int = 300,
        voting_method: VotingMethod = VotingMethod.RANKED_CHOICE,
        auto_merge: bool = True,
        require_build_pass: bool = True,
        require_test_pass: bool = False,
    ):
        """
        Initialize A/B solution generator.

        Args:
            working_dir: Directory for code generation
            max_parallel: Maximum parallel workers
            timeout: Timeout per generation in seconds
            voting_method: Method for voting on solutions
            auto_merge: Automatically merge winning branch
            require_build_pass: Only consider solutions that build
            require_test_pass: Only consider solutions that pass tests
        """
        self.working_dir = working_dir
        self.max_parallel = max_parallel
        self.timeout = timeout
        self.voting_method = voting_method
        self.auto_merge = auto_merge
        self.require_build_pass = require_build_pass
        self.require_test_pass = require_test_pass

        # Initialize components
        self.kilo = KiloCLIParallel(
            working_dir=working_dir,
            max_parallel=max_parallel,
            timeout=timeout,
        )
        self.voter = FixVoter(voting_method=voting_method)

        self.logger = logger.bind(component="ab_generator")

    async def generate_and_vote(
        self,
        task: str,
        num_solutions: int = 2,
        context: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> ABGenerationResult:
        """
        Generate multiple solutions and vote on the best one.

        Args:
            task: The generation task/prompt
            num_solutions: Number of solutions to generate (2-5)
            context: Additional context for generation
            mode: Kilo mode (code, architect, etc.)

        Returns:
            ABGenerationResult with winner, alternatives, and voting details
        """
        start_time = datetime.now()

        self.logger.info(
            "ab_generation_started",
            task=task[:100],
            num_solutions=num_solutions,
            mode=mode,
        )

        # Clamp num_solutions to reasonable range
        num_solutions = max(2, min(5, num_solutions))

        # Step 1: Generate solutions in parallel
        gen_start = datetime.now()
        parallel_results = await self._generate_solutions(task, num_solutions, context, mode)
        gen_time_ms = int((datetime.now() - gen_start).total_seconds() * 1000)

        # Step 2: Convert to GeneratedSolution objects
        solutions = self._convert_to_solutions(parallel_results)

        # Step 3: Build and test each solution
        await self._test_solutions(solutions)

        # Step 4: Filter candidates based on requirements
        candidates = self._filter_candidates(solutions)

        if not candidates:
            self.logger.warning(
                "no_valid_candidates",
                total=len(solutions),
                build_passed=sum(1 for s in solutions if s.build_passed),
                test_passed=sum(1 for s in solutions if s.test_passed),
            )
            return ABGenerationResult(
                winner=None,
                alternatives=solutions,
                voting_result=None,
                total_solutions=len(solutions),
                successful_builds=sum(1 for s in solutions if s.build_passed),
                successful_tests=sum(1 for s in solutions if s.test_passed),
                generation_time_ms=gen_time_ms,
                voting_time_ms=0,
                merged=False,
            )

        # Step 5: Vote on best solution
        vote_start = datetime.now()
        voting_result = await self._vote_on_solutions(task, candidates)
        vote_time_ms = int((datetime.now() - vote_start).total_seconds() * 1000)

        # Find winner
        winner = None
        if voting_result and voting_result.winner_id:
            for solution in candidates:
                if solution.id == voting_result.winner_id:
                    solution.status = SolutionStatus.SELECTED
                    winner = solution
                    break

        # Mark others as rejected
        for solution in solutions:
            if solution != winner and solution.status not in (SolutionStatus.BUILD_FAILED, SolutionStatus.TEST_FAILED):
                solution.status = SolutionStatus.REJECTED

        # Step 6: Merge winning branch if enabled
        merged = False
        merge_error = None
        if winner and self.auto_merge:
            try:
                merged = await self.kilo.merge_branch(winner.branch_name)
                if merged:
                    self.logger.info("winning_branch_merged", branch=winner.branch_name)
            except Exception as e:
                merge_error = str(e)
                self.logger.error("merge_failed", branch=winner.branch_name, error=str(e))

        total_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        self.logger.info(
            "ab_generation_complete",
            winner_id=winner.id if winner else None,
            winner_branch=winner.branch_name if winner else None,
            total_solutions=len(solutions),
            candidates=len(candidates),
            merged=merged,
            total_time_ms=total_time_ms,
        )

        return ABGenerationResult(
            winner=winner,
            alternatives=[s for s in solutions if s != winner],
            voting_result=voting_result,
            total_solutions=len(solutions),
            successful_builds=sum(1 for s in solutions if s.build_passed),
            successful_tests=sum(1 for s in solutions if s.test_passed),
            generation_time_ms=gen_time_ms,
            voting_time_ms=vote_time_ms,
            merged=merged,
            merge_error=merge_error,
        )

    async def generate_variants(
        self,
        task: str,
        variants: list[str],
        context: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> ABGenerationResult:
        """
        Generate solutions for different task variants and vote on best.

        Useful for trying different approaches explicitly.

        Args:
            task: Base task description
            variants: List of variant prompts (each tries a different approach)
            context: Additional context
            mode: Kilo mode

        Returns:
            ABGenerationResult with best variant selected
        """
        self.logger.info(
            "variant_generation_started",
            base_task=task[:100],
            num_variants=len(variants),
        )

        # Generate with different prompts
        start_time = datetime.now()

        # Combine base task with variant instructions
        full_prompts = [
            f"{task}\n\nApproach: {variant}"
            for variant in variants
        ]

        parallel_results = await self.kilo.execute(full_prompts, mode=mode)
        gen_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # Convert and test
        solutions = self._convert_to_solutions(parallel_results)
        await self._test_solutions(solutions)

        # Filter and vote
        candidates = self._filter_candidates(solutions)

        if not candidates:
            return ABGenerationResult(
                winner=None,
                alternatives=solutions,
                voting_result=None,
                total_solutions=len(solutions),
                successful_builds=sum(1 for s in solutions if s.build_passed),
                successful_tests=sum(1 for s in solutions if s.test_passed),
                generation_time_ms=gen_time_ms,
                voting_time_ms=0,
                merged=False,
            )

        vote_start = datetime.now()
        voting_result = await self._vote_on_solutions(task, candidates)
        vote_time_ms = int((datetime.now() - vote_start).total_seconds() * 1000)

        winner = None
        if voting_result and voting_result.winner_id:
            for solution in candidates:
                if solution.id == voting_result.winner_id:
                    solution.status = SolutionStatus.SELECTED
                    winner = solution
                    break

        # Merge if enabled
        merged = False
        merge_error = None
        if winner and self.auto_merge:
            try:
                merged = await self.kilo.merge_branch(winner.branch_name)
            except Exception as e:
                merge_error = str(e)

        return ABGenerationResult(
            winner=winner,
            alternatives=[s for s in solutions if s != winner],
            voting_result=voting_result,
            total_solutions=len(solutions),
            successful_builds=sum(1 for s in solutions if s.build_passed),
            successful_tests=sum(1 for s in solutions if s.test_passed),
            generation_time_ms=gen_time_ms,
            voting_time_ms=vote_time_ms,
            merged=merged,
            merge_error=merge_error,
        )

    async def _generate_solutions(
        self,
        task: str,
        num_solutions: int,
        context: Optional[str],
        mode: Optional[str],
    ) -> list[KiloParallelResult]:
        """Generate solutions using Kilo parallel mode."""
        # Build full prompt with context
        full_prompt = task
        if context:
            full_prompt = f"{context}\n\n{task}"

        # Use A/B test mode for same prompt multiple times
        results = await self.kilo.execute_ab_test(
            prompt=full_prompt,
            num_variants=num_solutions,
            mode=mode,
        )

        return results

    def _convert_to_solutions(self, results: list[KiloParallelResult]) -> list[GeneratedSolution]:
        """Convert Kilo results to GeneratedSolution objects."""
        solutions = []

        for result in results:
            solution = GeneratedSolution(
                id=f"solution_{result.worker_id}",
                branch_name=result.branch_name or f"kilo-parallel-{result.worker_id}",
                worker_id=result.worker_id,
                status=SolutionStatus.GENERATED if result.success else SolutionStatus.BUILD_FAILED,
                files=[{"path": f.path, "content": f.content[:500]} for f in result.files],
                execution_time_ms=result.execution_time_ms,
            )

            if not result.success:
                solution.build_output = result.error

            solutions.append(solution)

        return solutions

    async def _test_solutions(self, solutions: list[GeneratedSolution]) -> None:
        """Build and test each solution."""
        for solution in solutions:
            if solution.status == SolutionStatus.BUILD_FAILED:
                continue

            # Try to build
            build_passed, build_output = await self._run_build(solution.branch_name)
            solution.build_passed = build_passed
            solution.build_output = build_output

            if not build_passed:
                solution.status = SolutionStatus.BUILD_FAILED
                continue

            solution.status = SolutionStatus.BUILD_PASSED

            # Try to run tests
            test_passed, test_output = await self._run_tests(solution.branch_name)
            solution.test_passed = test_passed
            solution.test_output = test_output

            if test_passed:
                solution.status = SolutionStatus.TEST_PASSED
            else:
                solution.status = SolutionStatus.TEST_FAILED

    async def _run_build(self, branch_name: str) -> tuple[bool, str]:
        """Run build on a branch. Returns (success, output)."""
        try:
            # Checkout branch and run build
            process = await asyncio.create_subprocess_exec(
                "git", "checkout", branch_name,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()

            # Run npm build
            process = await asyncio.create_subprocess_exec(
                "npm", "run", "build",
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120,
            )

            output = stdout.decode() + stderr.decode()
            success = process.returncode == 0

            return success, output

        except asyncio.TimeoutError:
            return False, "Build timed out after 120 seconds"
        except Exception as e:
            return False, f"Build error: {str(e)}"

    async def _run_tests(self, branch_name: str) -> tuple[bool, str]:
        """Run tests on a branch. Returns (success, output)."""
        try:
            # Ensure on correct branch
            process = await asyncio.create_subprocess_exec(
                "git", "checkout", branch_name,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()

            # Run npm test
            process = await asyncio.create_subprocess_exec(
                "npm", "test", "--", "--run",
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=180,
            )

            output = stdout.decode() + stderr.decode()
            success = process.returncode == 0

            return success, output

        except asyncio.TimeoutError:
            return False, "Tests timed out after 180 seconds"
        except Exception as e:
            return False, f"Test error: {str(e)}"

    def _filter_candidates(self, solutions: list[GeneratedSolution]) -> list[GeneratedSolution]:
        """Filter solutions based on requirements."""
        candidates = []

        for solution in solutions:
            # Check build requirement
            if self.require_build_pass and not solution.build_passed:
                continue

            # Check test requirement
            if self.require_test_pass and not solution.test_passed:
                continue

            candidates.append(solution)

        return candidates

    async def _vote_on_solutions(
        self,
        task: str,
        candidates: list[GeneratedSolution],
    ) -> Optional[VotingResult]:
        """Vote on candidate solutions using FixVoter."""
        if not candidates:
            return None

        if len(candidates) == 1:
            # Only one candidate, no need to vote
            return VotingResult(
                winner_id=candidates[0].id,
                winner_description="Only valid candidate",
                confidence=1.0,
                votes={},
                reasoning="Single candidate selected automatically",
                rounds_taken=0,
            )

        # Convert solutions to ProposedFix format for voting
        proposed_fixes = []
        for solution in candidates:
            fix = ProposedFix(
                id=solution.id,
                description=f"Solution from {solution.worker_id}",
                code_changes=[{"branch": solution.branch_name, "files": len(solution.files)}],
                files_modified=[f["path"] for f in solution.files[:10]],  # First 10 files
                complexity="medium",  # Default
                branch_name=solution.branch_name,
                build_passed=solution.build_passed,
                test_passed=solution.test_passed,
            )
            proposed_fixes.append(fix)

        # Create error context (the task we're solving)
        error_context = ErrorContext(
            error_type="generation_task",
            error_message=task,
            file_path=self.working_dir,
            related_files=[],
        )

        # Vote with deliberation for better results
        voting_result = await self.voter.vote_with_deliberation(
            error=error_context,
            proposed_fixes=proposed_fixes,
            max_rounds=2,
        )

        return voting_result


# Convenience function for quick A/B generation
async def generate_ab_solutions(
    task: str,
    working_dir: str,
    num_solutions: int = 2,
    auto_merge: bool = True,
) -> ABGenerationResult:
    """
    Quick A/B solution generation.

    Args:
        task: Generation task
        working_dir: Working directory
        num_solutions: Number of solutions (default 2)
        auto_merge: Auto-merge winner (default True)

    Returns:
        ABGenerationResult
    """
    generator = ABSolutionGenerator(
        working_dir=working_dir,
        auto_merge=auto_merge,
    )
    return await generator.generate_and_vote(task, num_solutions)
