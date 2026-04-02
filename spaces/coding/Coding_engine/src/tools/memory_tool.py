"""
Memory Tool - High-level interface for agent memory operations.

This module provides structured methods for agents to:
1. Search for similar errors, projects, and patterns
2. Store test results, fixes, and insights
3. Build continuous learning capabilities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Any
import structlog

from src.tools.supermemory_tools import SupermemoryTools, MemorySearchResult, MemoryStoreResult

logger = structlog.get_logger()


@dataclass
class ErrorFixPattern:
    """Pattern of a successful error fix."""
    error_type: str
    error_message: str
    fix_description: str
    files_modified: List[str]
    confidence: float
    project_type: str


@dataclass
class ProjectMemory:
    """Memory of a complete project generation."""
    project_name: str
    requirements_count: int
    success: bool
    iterations_needed: int
    files_generated: int
    key_insights: str


class MemoryTool:
    """
    High-level memory tool for agents.

    Provides structured methods for storing and retrieving:
    - Error fixes and patterns
    - Test run results
    - Convergence metrics
    - Runtime debugging insights
    - Architecture patterns
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        enabled: bool = True,
        container_tag: str = "coding_engine_v1"
    ):
        """
        Initialize memory tool.

        Args:
            api_key: Supermemory API key (or use SUPERMEMORY_API_KEY env var)
            enabled: Whether memory operations are enabled
            container_tag: Container tag for all memories
        """
        self.enabled = enabled
        self.container_tag = container_tag
        self.logger = logger.bind(tool="memory")

        # Initialize Supermemory tools
        self.supermemory = SupermemoryTools(api_key=api_key) if enabled else None

        if self.enabled and self.supermemory and self.supermemory.client:
            self.logger.info("memory_tool_initialized", container_tag=container_tag)
        else:
            self.logger.warning("memory_tool_disabled", reason="supermemory_not_configured")
            self.enabled = False

    async def search_similar_errors(
        self,
        error_type: str,
        error_message: str,
        project_type: Optional[str] = None,
        limit: int = 5,
        rerank: bool = True
    ) -> List[ErrorFixPattern]:
        """
        Search for similar error fixes with intelligent reranking.

        Args:
            error_type: Type of error (e.g., "TypeScript", "RuntimeError")
            error_message: Error message or description
            project_type: Optional project type filter (e.g., "electron", "node")
            limit: Max results
            rerank: Enable reranking for better relevance (default: True)

        Returns:
            List of error fix patterns
        """
        if not self.enabled:
            return []

        self.logger.info(
            "searching_error_fixes",
            error_type=error_type,
            project_type=project_type,
            rerank=rerank
        )

        # Build search query
        query = f"{error_type} {error_message}"
        if project_type:
            query = f"{project_type} {query}"

        result = await self.supermemory.search(
            query=query,
            category="error_fix",
            limit=limit,
            container_tag=self.container_tag,
            rerank=rerank
        )

        # Parse results into ErrorFixPattern objects
        patterns = []
        for item in result.results:
            metadata = item.get("metadata", {})
            patterns.append(ErrorFixPattern(
                error_type=metadata.get("error_type", error_type),
                error_message=metadata.get("error_message", ""),
                fix_description=item.get("content", "")[:200],
                files_modified=metadata.get("files_modified", []),
                confidence=item.get("score", 0),
                project_type=metadata.get("project_type", "unknown")
            ))

        self.logger.info("error_fixes_found", count=len(patterns))
        return patterns

    async def search_similar_projects(
        self,
        requirements: List[str],
        project_type: Optional[str] = None,
        limit: int = 3
    ) -> List[ProjectMemory]:
        """
        Search for similar projects.

        Args:
            requirements: List of requirement descriptions
            project_type: Optional project type filter
            limit: Max results

        Returns:
            List of project memories
        """
        if not self.enabled:
            return []

        # Build search query from requirements
        query = " ".join(requirements[:3])  # Use first 3 requirements
        if project_type:
            query = f"{project_type} {query}"

        result = await self.supermemory.search(
            query=query,
            category="project_generation",
            limit=limit,
            container_tag=self.container_tag
        )

        # Parse results into ProjectMemory objects
        projects = []
        for item in result.results:
            metadata = item.get("metadata", {})
            projects.append(ProjectMemory(
                project_name=metadata.get("project_name", ""),
                requirements_count=metadata.get("requirements_count", 0),
                success=metadata.get("success", False),
                iterations_needed=metadata.get("iterations_needed", 0),
                files_generated=metadata.get("files_generated", 0),
                key_insights=item.get("content", "")[:300]
            ))

        return projects

    async def search_architecture_patterns(
        self,
        query: str,
        project_type: Optional[str] = None,
        limit: int = 5,
        rerank: bool = True
    ) -> MemorySearchResult:
        """
        Search for architecture patterns with intelligent reranking.

        Args:
            query: What to search for (e.g., "API authentication", "state management")
            project_type: Optional project type filter
            limit: Max results
            rerank: Enable reranking for better relevance (default: True)

        Returns:
            MemorySearchResult with architecture patterns
        """
        if not self.enabled:
            return MemorySearchResult(found=False, query=query, results=[], total_results=0)

        search_query = f"{project_type} {query}" if project_type else query

        return await self.supermemory.search(
            query=search_query,
            category="architecture",
            limit=limit,
            container_tag=self.container_tag,
            rerank=rerank
        )

    async def search_validation_fixes(
        self,
        check_type: str,
        error_message: str,
        project_type: Optional[str] = None,
        limit: int = 5,
        rerank: bool = True
    ) -> List[ErrorFixPattern]:
        """
        Search for similar validation fixes with intelligent reranking.

        Args:
            check_type: Type of validation check (e.g., "electron", "typescript", "build")
            error_message: Error message or description
            project_type: Optional project type filter
            limit: Max results
            rerank: Enable reranking for better relevance (default: True)

        Returns:
            List of error fix patterns for validation issues
        """
        if not self.enabled:
            return []

        self.logger.info(
            "searching_validation_fixes",
            check_type=check_type,
            project_type=project_type,
            rerank=rerank
        )

        # Build search query
        query = f"validation {check_type} {error_message}"
        if project_type:
            query = f"{project_type} {query}"

        result = await self.supermemory.search(
            query=query,
            category="error_fix",
            limit=limit,
            container_tag=self.container_tag,
            rerank=rerank
        )

        # Parse results into ErrorFixPattern objects
        patterns = []
        for item in result.results:
            metadata = item.get("metadata", {})
            patterns.append(ErrorFixPattern(
                error_type=metadata.get("error_type", check_type),
                error_message=metadata.get("error_message", error_message),
                fix_description=item.get("content", "")[:500],
                files_modified=metadata.get("files_modified", []),
                confidence=item.get("score", 0.5),
                project_type=metadata.get("project_type", project_type or "unknown"),
            ))

        return patterns

    async def search_test_patterns(
        self,
        query: str,
        project_type: Optional[str] = None,
        limit: int = 5,
        rerank: bool = True
    ) -> MemorySearchResult:
        """
        Search for test patterns and strategies with intelligent reranking.

        Args:
            query: What to search for (e.g., "UI testing electron", "E2E test patterns")
            project_type: Optional project type filter
            limit: Max results
            rerank: Enable reranking for better relevance (default: True)

        Returns:
            MemorySearchResult with test patterns
        """
        if not self.enabled:
            return MemorySearchResult(found=False, query=query, results=[], total_results=0)

        self.logger.info(
            "searching_test_patterns",
            query=query[:100],
            project_type=project_type,
            rerank=rerank
        )

        search_query = f"{project_type} {query}" if project_type else query

        return await self.supermemory.search(
            query=search_query,
            category="test_run",
            limit=limit,
            container_tag=self.container_tag,
            rerank=rerank
        )

    def select_top_memories(
        self,
        search_results: List[Dict[str, Any]],
        max_tokens: int = 1000,
        tokens_per_char: float = 0.25,
        temporal_decay_days: int = 30
    ) -> str:
        """
        Intelligently select and format top memories based on scoring + temporal decay.

        This implements Supermemory's approach:
        1. Score by semantic relevance (from search results)
        2. Apply temporal decay (recent memories weighted higher)
        3. Select top-ranked memories that fit token budget

        Args:
            search_results: Raw search results from Supermemory
            max_tokens: Maximum token budget for context
            tokens_per_char: Approximate tokens per character (0.25 = 4 chars/token)
            temporal_decay_days: Days over which relevance decays by 50%

        Returns:
            Formatted context string with top-ranked memories
        """
        if not search_results:
            return ""

        # Calculate max characters from token budget
        max_chars = int(max_tokens / tokens_per_char)

        # Score and rank memories
        scored_memories = []
        now = datetime.utcnow()

        for result in search_results:
            # Get base relevance score from search
            relevance_score = result.get("score", 0.5)

            # Apply temporal decay
            metadata = result.get("metadata", {})
            timestamp_str = metadata.get("timestamp")

            if timestamp_str:
                try:
                    memory_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    days_old = (now - memory_time).total_seconds() / 86400
                    # Exponential decay: score *= 0.5 ^ (days_old / temporal_decay_days)
                    temporal_factor = 0.5 ** (days_old / temporal_decay_days)
                    final_score = relevance_score * (0.7 + 0.3 * temporal_factor)  # 70% relevance, 30% recency
                except (ValueError, AttributeError):
                    final_score = relevance_score
            else:
                final_score = relevance_score

            scored_memories.append({
                "content": result.get("content", ""),
                "score": final_score,
                "metadata": metadata
            })

        # Sort by final score (highest first)
        scored_memories.sort(key=lambda x: x["score"], reverse=True)

        # Select memories that fit budget
        selected_context = []
        total_chars = 0

        for memory in scored_memories:
            content = memory["content"]
            content_length = len(content)

            # Check if adding this memory exceeds budget
            if total_chars + content_length + 20 > max_chars:  # +20 for formatting
                # Try to fit a truncated version
                remaining = max_chars - total_chars - 20
                if remaining > 100:  # Only include if we can fit meaningful content
                    content = content[:remaining] + "..."
                    selected_context.append(content)
                break

            selected_context.append(content)
            total_chars += content_length + 20

        # Format as context
        if selected_context:
            return "\n\n".join(selected_context)
        return ""

    async def store_architecture_pattern(
        self,
        content: str,
        metadata: Dict[str, Any],
        project_type: str
    ) -> MemoryStoreResult:
        """
        Store a successful architecture pattern.

        Args:
            content: Architecture description and contracts summary
            metadata: Metadata dict with project info, contracts, etc.
            project_type: Type of project (electron-app, node, etc.)

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        timestamp = datetime.utcnow().isoformat()
        project_name = metadata.get("project_name", "unknown")

        # Sanitize custom_id: only alphanumeric, hyphens, underscores
        custom_id = f"{project_name}_architecture_{timestamp}".replace(":", "-").replace(".", "-")

        return await self.supermemory.store(
            content=content,
            description=f"Architecture pattern for {project_type} project",
            category="architecture",
            tags=["architecture", project_type, "contracts"],
            context=metadata,
            container_tag=self.container_tag,
            custom_id=custom_id[:100]  # Max 100 chars
        )

    async def store_error_fix(
        self,
        error_type: str,
        error_message: str,
        fix_description: str,
        files_modified: List[str],
        project_type: str,
        project_name: str,
        iteration: int,
        success: bool
    ) -> MemoryStoreResult:
        """
        Store a successful error fix.

        Args:
            error_type: Type of error
            error_message: Error message
            fix_description: How it was fixed
            files_modified: List of files modified
            project_type: Project type (electron, node, etc.)
            project_name: Project name
            iteration: Iteration number where fix was applied
            success: Whether the fix was successful

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        content = f"""## Error
**Type:** {error_type}
**Message:** {error_message}

## Fix Applied
{fix_description}

## Files Modified
{chr(10).join(f"- {f}" for f in files_modified)}

## Outcome
{'Fix successful' if success else 'Fix unsuccessful'}
"""

        timestamp = datetime.utcnow().isoformat()
        # Sanitize custom_id: only alphanumeric, hyphens, underscores
        custom_id = f"{project_name}_{error_type}_{timestamp}".replace(":", "-").replace(".", "-")

        return await self.supermemory.store(
            content=content,
            description=f"{error_type} fix in {project_type} project",
            category="error_fix",
            tags=[error_type, project_type, "fix"],
            context={
                "error_type": error_type,
                "error_message": error_message,
                "files_modified": files_modified,
                "project_type": project_type,
                "project_name": project_name,
                "iteration": iteration,
                "success": success,
                "timestamp": timestamp
            },
            container_tag=self.container_tag,
            custom_id=custom_id[:100]  # Max 100 chars
        )

    async def store_test_run(
        self,
        project_name: str,
        project_type: str,
        test_framework: str,
        total_tests: int,
        passed: int,
        failed: int,
        execution_time_ms: int,
        iteration: int,
        failure_details: Optional[List[Dict[str, str]]] = None
    ) -> MemoryStoreResult:
        """
        Store test run results.

        Args:
            project_name: Project name
            project_type: Project type
            test_framework: Test framework used (pytest, jest, vitest)
            total_tests: Total tests run
            passed: Tests passed
            failed: Tests failed
            execution_time_ms: Execution time in milliseconds
            iteration: Iteration number
            failure_details: Optional list of failure details

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0

        content = f"""## Test Run Results
**Project:** {project_name}
**Framework:** {test_framework}
**Pass Rate:** {pass_rate:.1f}% ({passed}/{total_tests})
**Execution Time:** {execution_time_ms}ms

## Failures
{chr(10).join(f"- {f.get('test_name', 'Unknown')}: {f.get('error', 'No details')}" for f in (failure_details or [])[:5])}
"""

        timestamp = datetime.utcnow().isoformat()

        return await self.supermemory.store(
            content=content,
            description=f"Test run for {project_name} (iteration {iteration})",
            category="test_run",
            tags=[test_framework, project_type, "testing"],
            context={
                "project_name": project_name,
                "project_type": project_type,
                "test_framework": test_framework,
                "total_tests": total_tests,
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
                "execution_time_ms": execution_time_ms,
                "iteration": iteration,
                "timestamp": timestamp
            },
            container_tag=self.container_tag
        )

    async def store_convergence_metrics(
        self,
        project_name: str,
        iteration: int,
        confidence_score: float,
        test_pass_rate: float,
        build_success: bool,
        validation_errors: int,
        type_errors: int,
        converged: bool,
        blocking_reasons: Optional[List[str]] = None
    ) -> MemoryStoreResult:
        """
        Store convergence iteration metrics.

        Args:
            project_name: Project name
            iteration: Iteration number
            confidence_score: Confidence score (0-1)
            test_pass_rate: Test pass rate (0-1)
            build_success: Whether build succeeded
            validation_errors: Number of validation errors
            type_errors: Number of type errors
            converged: Whether converged
            blocking_reasons: Reasons blocking convergence

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        content = f"""## Convergence Metrics (Iteration {iteration})
**Confidence:** {confidence_score*100:.1f}%
**Test Pass Rate:** {test_pass_rate*100:.1f}%
**Build:** {'SUCCESS' if build_success else 'FAILED'}
**Validation Errors:** {validation_errors}
**Type Errors:** {type_errors}
**Converged:** {'Yes' if converged else 'No'}

## Blocking Reasons
{chr(10).join(f"- {r}" for r in (blocking_reasons or []))}
"""

        timestamp = datetime.utcnow().isoformat()

        return await self.supermemory.store(
            content=content,
            description=f"Convergence metrics for {project_name} iteration {iteration}",
            category="convergence",
            tags=["convergence", "metrics"],
            context={
                "project_name": project_name,
                "iteration": iteration,
                "confidence_score": confidence_score,
                "test_pass_rate": test_pass_rate,
                "build_success": build_success,
                "validation_errors": validation_errors,
                "type_errors": type_errors,
                "converged": converged,
                "blocking_reasons": blocking_reasons or [],
                "timestamp": timestamp
            },
            container_tag=self.container_tag
        )

    async def store_runtime_debug(
        self,
        project_name: str,
        project_type: str,
        runtime_success: bool,
        crashed: bool,
        errors: List[Dict[str, Any]],
        fix_suggestions: Optional[List[str]] = None
    ) -> MemoryStoreResult:
        """
        Store runtime debugging session.

        Args:
            project_name: Project name
            project_type: Project type (electron, node, python)
            runtime_success: Whether runtime test succeeded
            crashed: Whether app crashed
            errors: List of errors encountered
            fix_suggestions: Optional list of fix suggestions applied

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        content = f"""## Runtime Debug Session
**Project:** {project_name}
**Type:** {project_type}
**Result:** {'SUCCESS' if runtime_success else 'FAILED'}
**Crashed:** {'Yes' if crashed else 'No'}

## Errors
{chr(10).join(f"- {e.get('error_type', 'Unknown')}: {e.get('message', '')[:100]}" for e in errors[:5])}

## Fix Suggestions
{chr(10).join(f"- {s}" for s in (fix_suggestions or [])[:5])}
"""

        timestamp = datetime.utcnow().isoformat()

        return await self.supermemory.store(
            content=content,
            description=f"Runtime debug for {project_name}",
            category="runtime_debug",
            tags=[project_type, "runtime", "debug"],
            context={
                "project_name": project_name,
                "project_type": project_type,
                "runtime_success": runtime_success,
                "crashed": crashed,
                "error_count": len(errors),
                "timestamp": timestamp
            },
            container_tag=self.container_tag
        )

    async def store_project_generation(
        self,
        project_name: str,
        project_type: str,
        requirements_count: int,
        success: bool,
        iterations_needed: int,
        files_generated: int,
        converged: bool,
        key_insights: str
    ) -> MemoryStoreResult:
        """
        Store complete project generation outcome.

        Args:
            project_name: Project name
            project_type: Project type
            requirements_count: Number of requirements
            success: Whether generation succeeded
            iterations_needed: Iterations needed
            files_generated: Files generated
            converged: Whether it converged
            key_insights: Key insights from the generation

        Returns:
            MemoryStoreResult
        """
        if not self.enabled:
            return MemoryStoreResult(success=False, error="Memory tool disabled")

        content = f"""## Project Generation: {project_name}
**Type:** {project_type}
**Requirements:** {requirements_count}
**Result:** {'SUCCESS' if success else 'FAILED'}
**Iterations:** {iterations_needed}
**Files Generated:** {files_generated}
**Converged:** {'Yes' if converged else 'No'}

## Key Insights
{key_insights}
"""

        timestamp = datetime.utcnow().isoformat()
        # Sanitize custom_id: only alphanumeric, hyphens, underscores
        custom_id = f"{project_name}_generation_{timestamp}".replace(":", "-").replace(".", "-")

        return await self.supermemory.store(
            content=content,
            description=f"Project generation: {project_name}",
            category="project_generation",
            tags=[project_type, "project", "generation"],
            context={
                "project_name": project_name,
                "project_type": project_type,
                "requirements_count": requirements_count,
                "success": success,
                "iterations_needed": iterations_needed,
                "files_generated": files_generated,
                "converged": converged,
                "timestamp": timestamp
            },
            container_tag=self.container_tag,
            custom_id=custom_id[:100]
        )

    async def store_contracts(
        self,
        contracts_json: str,
        job_id: int,
        project_name: str,
    ) -> MemoryStoreResult:
        """
        Store InterfaceContracts in Supermemory for parallel batch context.

        Delegates to SupermemoryTools.store_contracts() if available.

        Args:
            contracts_json: JSON-serialized InterfaceContracts
            job_id: Job ID for container tagging
            project_name: Project name for metadata

        Returns:
            MemoryStoreResult
        """
        if not self.enabled or not self.supermemory:
            return MemoryStoreResult(success=False, error="Supermemory not enabled")

        # Check if supermemory has store_contracts method
        if not hasattr(self.supermemory, 'store_contracts'):
            self.logger.warning("store_contracts_not_available")
            return MemoryStoreResult(success=False, error="store_contracts not available")

        return await self.supermemory.store_contracts(
            contracts_json=contracts_json,
            job_id=job_id,
            project_name=project_name,
        )

    async def close(self):
        """Close connections."""
        if self.supermemory:
            await self.supermemory.close()
