"""
Fungus Validation Service - Phase 17

Autonomous code validation using MCMP (Mycelial Collective Pheromone Search)
simulation. Composes MCMPBackgroundSimulation with validation-oriented Judge
prompts to discover code issues during epic generation.

Features:
1. Continuous codebase re-indexing as files are generated
2. Validation-oriented Judge LLM (pattern checks, dependency integrity, etc.)
3. Seed strategy with known-good patterns from completed tasks
4. Publishes ValidationFindings as structured results
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

from .mcmp_background import (
    JudgeMode,
    MCMPBackgroundSimulation,
    SimulationConfig,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class ValidationJudgeMode(Enum):
    """Validation-specific judge modes."""
    PATTERN_CHECK = "pattern_check"
    DEPENDENCY_CHECK = "dependency_check"
    SCHEMA_CONSISTENCY = "schema_consistency"
    API_CONTRACT = "api_contract"
    CROSS_FILE = "cross_file"


@dataclass
class ValidationFinding:
    """A single validation issue found by the Fungus simulation."""
    finding_type: str
    severity: str
    file_path: str
    related_files: List[str] = field(default_factory=list)
    description: str = ""
    suggested_fix: str = ""
    confidence: float = 0.0
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregated validation report from a simulation round."""
    round_number: int
    findings: List[ValidationFinding] = field(default_factory=list)
    files_analyzed: int = 0
    files_indexed: int = 0
    simulation_steps: int = 0
    judge_confidence: float = 0.0
    timestamp: str = ""
    focus_query: str = ""


# ---------------------------------------------------------------------------
# FungusValidationService
# ---------------------------------------------------------------------------

class FungusValidationService:
    """
    Continuous validation service using MCMP simulation.

    Composes MCMPBackgroundSimulation + MCPMRetriever for validation-specific
    behavior. Instead of search-relevance judging, uses validation-oriented
    Judge prompts that evaluate code patterns and produce structured findings.
    """

    # File extensions to index
    INDEX_EXTENSIONS = {
        ".ts", ".tsx", ".js", ".jsx",
        ".py",
        ".prisma", ".sql",
        ".json",
        ".yaml", ".yml",
        ".env",
    }

    # Directories to skip
    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", "dist", "build",
        ".next", ".cache", "coverage", ".vscode",
    }

    def __init__(
        self,
        working_dir: str,
        event_bus: Optional[Any] = None,
        config: Optional[SimulationConfig] = None,
        job_id: str = "validation",
        enable_supermemory: bool = True,
    ):
        self.working_dir = Path(working_dir)
        self._event_bus = event_bus
        self._job_id = job_id
        self._enable_supermemory = enable_supermemory
        self._config = config or SimulationConfig(
            num_agents=100,
            max_iterations=30,
            judge_every=5,
            steering_every=5,
            enable_llm_steering=True,
        )

        # Composed simulation engine
        self._simulation = MCMPBackgroundSimulation(
            config=self._config,
            on_context_update=self._on_simulation_update,
        )

        # Phase 19: Supermemory corpus loader (lazy init)
        self._corpus_loader = None

        # State
        self._running = False
        self._round_number = 0
        self._reports: List[ValidationReport] = []
        self._file_hashes: Dict[str, str] = {}
        self._indexed_count = 0
        self._seed_patterns: Dict[str, Any] = {}
        self._completed_tasks: List[Dict[str, Any]] = []
        self._failed_task_errors: List[str] = []
        self._llm_client = None

        self.logger = logger.bind(component="FungusValidation", job_id=job_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def _init_supermemory(self) -> None:
        """Lazy-initialize Supermemory corpus loader."""
        if self._corpus_loader is not None:
            return
        if not self._enable_supermemory:
            return

        try:
            from .supermemory_corpus_loader import SupermemoryCorpusLoader

            self._corpus_loader = SupermemoryCorpusLoader(
                job_id=f"validation_{self._job_id}"
            )
            await self._corpus_loader.initialize()
        except Exception as e:
            self.logger.debug("supermemory_init_failed", error=str(e))

    async def start(self, seed_patterns: Optional[Dict[str, Any]] = None) -> bool:
        """
        Start the validation service.

        Args:
            seed_patterns: Known-good patterns to seed the Judge with.
                Example: {"framework": "Hono", "orm": "Prisma", ...}

        Returns:
            True if started successfully.
        """
        if self._running:
            self.logger.warning("already_running")
            return False

        if seed_patterns:
            self._seed_patterns = seed_patterns

        # Index the full project
        indexed = await self.reindex_project()
        if indexed == 0:
            self.logger.warning("no_files_indexed", working_dir=str(self.working_dir))
            return False

        # Phase 19: Load past validation patterns from Supermemory
        await self._init_supermemory()
        if self._corpus_loader and self._corpus_loader.available:
            seed_query = "validation patterns code quality"
            if seed_patterns:
                framework = seed_patterns.get("framework", "")
                orm = seed_patterns.get("orm", "")
                if framework or orm:
                    seed_query = f"{framework} {orm} validation patterns"

            memory_docs = await self._corpus_loader.fetch_as_mcmp_documents(
                query=seed_query,
                category="all",
                limit=20,
            )
            if memory_docs:
                self._simulation.add_documents(memory_docs)
                self.logger.info("validation_memories_loaded", count=len(memory_docs))

        self._running = True
        self.logger.info(
            "validation_started",
            files_indexed=indexed,
            seed_patterns=bool(seed_patterns),
        )
        return True

    async def reindex_project(self) -> int:
        """
        Index all source files in the working directory.

        Returns:
            Number of files indexed.
        """
        documents = []
        file_paths = []

        for ext in self.INDEX_EXTENSIONS:
            for f in self.working_dir.rglob(f"*{ext}"):
                # Skip excluded directories
                if any(skip in f.parts for skip in self.SKIP_DIRS):
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    # Check if file changed since last index
                    content_hash = hashlib.md5(content.encode()).hexdigest()
                    rel_path = str(f.relative_to(self.working_dir))

                    if self._file_hashes.get(rel_path) == content_hash:
                        continue  # No change

                    self._file_hashes[rel_path] = content_hash

                    # Prepend file path as header for context
                    doc = f"// File: {rel_path}\n{content[:4000]}"
                    documents.append(doc)
                    file_paths.append(rel_path)

                except Exception as e:
                    self.logger.debug("file_read_error", path=str(f), error=str(e))

        if documents:
            # Clear previous corpus and re-add all
            self._simulation.clear_documents()
            added = self._simulation.add_documents(documents)
            self._indexed_count = added
            self.logger.info("project_indexed", files=added, paths=len(file_paths))
            return added

        return self._indexed_count

    async def reindex_file(self, file_path: str) -> bool:
        """
        Incrementally re-index a single file.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            True if file was re-indexed.
        """
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.working_dir / path

            if not path.exists():
                return False

            if path.suffix not in self.INDEX_EXTENSIONS:
                return False

            content = path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                return False

            content_hash = hashlib.md5(content.encode()).hexdigest()
            rel_path = str(path.relative_to(self.working_dir))

            if self._file_hashes.get(rel_path) == content_hash:
                return False  # No change

            self._file_hashes[rel_path] = content_hash

            # For incremental updates we need to re-index the full project
            # since MCPMRetriever doesn't support single-document updates.
            # We track the change and batch re-index on next validation round.
            self.logger.debug("file_changed", path=rel_path)
            return True

        except Exception as e:
            self.logger.debug("reindex_file_error", path=file_path, error=str(e))
            return False

    async def run_validation_round(
        self,
        focus_query: str,
        mode: ValidationJudgeMode = ValidationJudgeMode.PATTERN_CHECK,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> ValidationReport:
        """
        Run one validation round with Judge evaluation.

        Args:
            focus_query: What to validate (e.g., "validate auth module patterns")
            mode: Validation mode determining Judge prompt focus
            task_context: Optional context from the current task

        Returns:
            ValidationReport with findings.
        """
        self._round_number += 1
        report = ValidationReport(
            round_number=self._round_number,
            files_indexed=self._indexed_count,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            focus_query=focus_query,
        )

        # Re-index if files changed
        await self.reindex_project()

        # Phase 19: Load focus-specific memories before validation
        if self._corpus_loader and self._corpus_loader.available:
            memory_docs = await self._corpus_loader.fetch_as_mcmp_documents(
                query=focus_query,
                limit=10,
            )
            if memory_docs:
                self._simulation.add_documents(memory_docs)

        # Start simulation for the focus query
        started = await self._simulation.start(
            query=focus_query,
            mode=JudgeMode.DEEP,  # Use deep mode for thorough analysis
        )

        if not started:
            self.logger.warning("simulation_start_failed", query=focus_query[:50])
            self._reports.append(report)
            return report

        # Wait for simulation to complete
        while self._simulation.is_running:
            await asyncio.sleep(0.5)

        # Get simulation results
        results = self._simulation.get_results()
        report.simulation_steps = results.get("steps_completed", 0)

        # Get top results for validation
        top_results = results.get("top_results", [])
        report.files_analyzed = len(top_results)

        # Run validation Judge
        findings = await self._run_validation_judge(
            focus_query=focus_query,
            mode=mode,
            top_results=top_results,
            task_context=task_context,
        )

        report.findings = findings

        # Extract confidence from judge evaluations
        judge_evals = results.get("judge_evaluations", [])
        if judge_evals:
            report.judge_confidence = judge_evals[-1].get("confidence", 0.0)

        # Stop simulation for this round
        await self._simulation.stop()

        # Phase 19: Store high-confidence findings back to Supermemory
        stored = await self._store_significant_findings(findings, focus_query)

        self._reports.append(report)

        self.logger.info(
            "validation_round_complete",
            round=self._round_number,
            findings=len(findings),
            errors=len([f for f in findings if f.severity == "error"]),
            warnings=len([f for f in findings if f.severity == "warning"]),
            memories_stored=stored,
        )

        return report

    async def _store_significant_findings(
        self, findings: List[ValidationFinding], focus_query: str
    ) -> int:
        """Store high-confidence validation findings to Supermemory for future projects."""
        if not self._corpus_loader or not self._corpus_loader.available:
            return 0

        stored = 0
        for finding in findings:
            if finding.confidence >= 0.8 and finding.severity in ("error", "warning"):
                content = (
                    f"Validation finding: {finding.finding_type}\n"
                    f"File: {finding.file_path}\n"
                    f"Description: {finding.description}\n"
                    f"Fix: {finding.suggested_fix}\n"
                    f"Context: {focus_query}"
                )
                success = await self._corpus_loader.store_pattern(
                    content=content,
                    category="validation_finding",
                    metadata={
                        "finding_type": finding.finding_type,
                        "severity": finding.severity,
                        "confidence": finding.confidence,
                    },
                )
                if success:
                    stored += 1

        return stored

    def add_completed_task(self, task: Dict[str, Any]) -> None:
        """Track a completed task for seed pattern building."""
        self._completed_tasks.append(task)

    def add_failed_error(self, error_message: str) -> None:
        """Track a failed task error as anti-pattern."""
        self._failed_task_errors.append(error_message)

    async def stop(self) -> List[ValidationReport]:
        """Stop the validation service and return all reports."""
        self._running = False

        if self._simulation.is_running:
            await self._simulation.stop()

        self.logger.info(
            "validation_stopped",
            rounds=len(self._reports),
            total_findings=sum(len(r.findings) for r in self._reports),
        )

        return self._reports

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def reports(self) -> List[ValidationReport]:
        return list(self._reports)

    @property
    def indexed_count(self) -> int:
        return self._indexed_count

    # ------------------------------------------------------------------
    # Private: Validation Judge
    # ------------------------------------------------------------------

    async def _run_validation_judge(
        self,
        focus_query: str,
        mode: ValidationJudgeMode,
        top_results: List[Dict[str, Any]],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> List[ValidationFinding]:
        """
        Run validation-oriented Judge LLM on discovered code patterns.

        Instead of evaluating search relevance, the Judge evaluates code
        correctness and produces structured findings.
        """
        if not top_results:
            return []

        if not await self._init_llm_client():
            # Fallback: basic heuristic validation without LLM
            return self._heuristic_validation(top_results)

        try:
            prompt = self._build_validation_prompt(
                focus_query=focus_query,
                mode=mode,
                top_results=top_results,
                task_context=task_context,
            )

            response = await self._llm_client.post(
                "/chat/completions",
                json={
                    "model": self._config.judge_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                },
            )

            if response.status_code != 200:
                self.logger.warning("validation_judge_failed", status=response.status_code)
                return self._heuristic_validation(top_results)

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            return self._parse_validation_response(content, top_results)

        except Exception as e:
            self.logger.warning("validation_judge_error", error=str(e))
            return self._heuristic_validation(top_results)

    def _build_validation_prompt(
        self,
        focus_query: str,
        mode: ValidationJudgeMode,
        top_results: List[Dict[str, Any]],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the validation-oriented Judge prompt."""

        # Format discovered code snippets
        code_snippets = []
        for i, r in enumerate(top_results[:10]):
            content = r.get("content", "")[:600]
            score = r.get("relevance_score", 0.0)
            code_snippets.append(f"[{i}] score={score:.3f}\n{content}")

        snippets_text = "\n---\n".join(code_snippets)

        # Build seed patterns section
        seed_text = ""
        if self._seed_patterns:
            seed_lines = []
            for key, value in self._seed_patterns.items():
                seed_lines.append(f"- {key}: {value}")
            seed_text = f"\nKnown good patterns (seeded):\n" + "\n".join(seed_lines)

        # Build anti-patterns section
        anti_text = ""
        if self._failed_task_errors:
            errors = self._failed_task_errors[-5:]  # Last 5
            anti_text = f"\nKnown anti-patterns from failed tasks:\n"
            anti_text += "\n".join(f"- {e[:150]}" for e in errors)

        # Build task context section
        task_text = ""
        if task_context:
            task_text = f"\nCurrent task: \"{task_context.get('title', '')}\" (type: {task_context.get('type', '')})"
            if task_context.get("description"):
                task_text += f"\nDescription: {task_context['description'][:200]}"

        # Mode-specific analysis instructions
        mode_instructions = {
            ValidationJudgeMode.PATTERN_CHECK: (
                "Focus on PATTERN CONSISTENCY:\n"
                "- Are naming conventions consistent across files?\n"
                "- Do import styles match the project standard?\n"
                "- Is error handling consistent?"
            ),
            ValidationJudgeMode.DEPENDENCY_CHECK: (
                "Focus on DEPENDENCY INTEGRITY:\n"
                "- Are all import/require statements resolvable?\n"
                "- Do referenced modules exist in the discovered code?\n"
                "- Are there circular dependency risks?"
            ),
            ValidationJudgeMode.SCHEMA_CONSISTENCY: (
                "Focus on SCHEMA-CODE ALIGNMENT:\n"
                "- Do TypeScript interfaces match Prisma model definitions?\n"
                "- Are API DTOs consistent with database schemas?\n"
                "- Are field names and types aligned?"
            ),
            ValidationJudgeMode.API_CONTRACT: (
                "Focus on API CONTRACT COMPLIANCE:\n"
                "- Do controllers implement the expected HTTP methods?\n"
                "- Are request/response types matching the spec?\n"
                "- Is authentication middleware applied correctly?"
            ),
            ValidationJudgeMode.CROSS_FILE: (
                "Focus on CROSS-FILE REFERENCES:\n"
                "- Are exported functions imported correctly elsewhere?\n"
                "- Are route registrations complete?\n"
                "- Are barrel file (index.ts) exports up to date?"
            ),
        }

        analysis_focus = mode_instructions.get(mode, mode_instructions[ValidationJudgeMode.PATTERN_CHECK])

        return f"""You are a code validation judge analyzing a generated codebase.

Query: "{focus_query}"
{task_text}
{seed_text}
{anti_text}

The MCMP swarm simulation discovered these related code patterns:
{snippets_text}

{analysis_focus}

Analyze the discovered code and return a JSON object:
{{
  "findings": [
    {{
      "finding_type": "missing_import|type_mismatch|dead_reference|pattern_violation|schema_drift|missing_export",
      "severity": "error|warning|info",
      "file_path": "path/to/file",
      "related_files": ["other/file"],
      "description": "what is wrong",
      "suggested_fix": "how to fix it",
      "confidence": 0.0-1.0
    }}
  ],
  "overall_health": 0.0-1.0,
  "additional_queries": ["next queries to explore"]
}}

Rules:
- Only report findings you are confident about (>= 0.5 confidence)
- Include evidence from the code snippets
- If no issues found, return empty findings array with high overall_health
- Be specific about file paths (extract from // File: headers in snippets)"""

    def _parse_validation_response(
        self,
        response: str,
        top_results: List[Dict[str, Any]],
    ) -> List[ValidationFinding]:
        """Parse Judge LLM validation response into ValidationFinding objects."""
        parsed = self._parse_json_response(response)
        if not parsed:
            return []

        findings = []
        for f in parsed.get("findings", []):
            if not isinstance(f, dict):
                continue

            confidence = float(f.get("confidence", 0.0))
            if confidence < 0.5:
                continue  # Skip low-confidence findings

            # Build evidence from top results
            evidence = []
            for r in top_results[:3]:
                evidence.append({
                    "content": r.get("content", "")[:300],
                    "score": r.get("relevance_score", 0.0),
                })

            findings.append(ValidationFinding(
                finding_type=f.get("finding_type", "unknown"),
                severity=f.get("severity", "warning"),
                file_path=f.get("file_path", ""),
                related_files=f.get("related_files", []),
                description=f.get("description", ""),
                suggested_fix=f.get("suggested_fix", ""),
                confidence=confidence,
                evidence=evidence,
            ))

        return findings

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response (handles markdown code blocks)."""
        try:
            return json.loads(response)
        except Exception:
            pass

        try:
            text = response.strip()
            if text.startswith("```"):
                lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
                text = "\n".join(lines)
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass

        return {}

    # ------------------------------------------------------------------
    # Private: Heuristic validation (fallback without LLM)
    # ------------------------------------------------------------------

    def _heuristic_validation(
        self,
        top_results: List[Dict[str, Any]],
    ) -> List[ValidationFinding]:
        """
        Basic heuristic validation without LLM.

        Checks for common issues by pattern matching in discovered code.
        """
        findings = []

        for r in top_results:
            content = r.get("content", "")
            metadata = r.get("metadata", {})

            # Extract file path from content header
            file_path = ""
            if content.startswith("// File: "):
                first_line = content.split("\n", 1)[0]
                file_path = first_line.replace("// File: ", "").strip()

            # Check for TODO/FIXME markers (incomplete implementation)
            for marker in ["TODO", "FIXME", "HACK", "XXX"]:
                if marker in content:
                    findings.append(ValidationFinding(
                        finding_type="incomplete_implementation",
                        severity="warning",
                        file_path=file_path,
                        description=f"Contains {marker} marker indicating incomplete implementation",
                        confidence=0.7,
                        evidence=[{"content": content[:200], "score": r.get("relevance_score", 0)}],
                    ))
                    break

            # Check for empty catch blocks
            if "catch" in content and "catch {" in content.replace(" ", ""):
                findings.append(ValidationFinding(
                    finding_type="pattern_violation",
                    severity="warning",
                    file_path=file_path,
                    description="Empty or minimal catch block - errors may be silently swallowed",
                    confidence=0.6,
                    evidence=[{"content": content[:200], "score": r.get("relevance_score", 0)}],
                ))

            # Check for hardcoded secrets patterns
            for pattern in ["password = \"", "secret = \"", "api_key = \"", "token = \""]:
                if pattern in content.lower():
                    findings.append(ValidationFinding(
                        finding_type="pattern_violation",
                        severity="error",
                        file_path=file_path,
                        description="Possible hardcoded secret detected",
                        confidence=0.8,
                        evidence=[{"content": content[:200], "score": r.get("relevance_score", 0)}],
                    ))
                    break

        return findings

    # ------------------------------------------------------------------
    # Private: LLM client
    # ------------------------------------------------------------------

    async def _init_llm_client(self) -> bool:
        """Initialize async LLM client for validation Judge."""
        if self._llm_client is not None:
            return True

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            self.logger.debug("no_openrouter_key", msg="Using heuristic validation only")
            return False

        try:
            import httpx
            self._llm_client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            return True
        except Exception as e:
            self.logger.warning("llm_client_init_failed", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Private: Simulation callback
    # ------------------------------------------------------------------

    async def _on_simulation_update(self, update: Dict[str, Any]) -> None:
        """Callback from MCMPBackgroundSimulation on each step."""
        # Could be used to stream progress to dashboard in the future
        pass
