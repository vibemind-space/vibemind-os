# -*- coding: utf-8 -*-
"""
Differential Analysis Service - Phase 20

Compares documentation/requirements against generated code to identify
implementation gaps. Uses MCMP (Mycelial Collective Pheromone Search)
simulation with a differential Judge LLM to discover what's documented
but NOT implemented.

Architecture:
    Documentation corpus (SHOULD exist) ──┐
                                           ├──→ MCMP Simulation → Differential Judge → Gap Report
    Code corpus (DOES exist)         ─────┘

The Judge evaluates each requirement against discovered code and assigns:
- IMPLEMENTED: Code fully satisfies the requirement
- PARTIAL: Code exists but is incomplete
- MISSING: No corresponding code found
- UNKNOWN: Could not determine (insufficient context)

Features:
1. Loads user_stories.json, epic tasks, MASTER_DOCUMENT.md as doc corpus
2. Loads generated .ts/.prisma/.json files as code corpus
3. MCMP swarm finds cross-references between docs and code
4. Differential Judge produces structured GapFindings
5. Optional Supermemory enrichment (past implementation patterns)
6. Produces JSON gap report with traceability
"""

import asyncio
import hashlib
import json
import os
import re
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
from src.llm_config import get_model

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------


class ImplementationStatus(str, Enum):
    """Status of a requirement's implementation."""
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    MISSING = "missing"
    UNKNOWN = "unknown"


class GapSeverity(str, Enum):
    """Severity of an implementation gap."""
    CRITICAL = "critical"    # MUST requirement missing
    HIGH = "high"            # SHOULD requirement missing
    MEDIUM = "medium"        # COULD requirement missing / partial MUST
    LOW = "low"              # Minor gaps or cosmetic


class AnalysisMode(str, Enum):
    """Focus mode for differential analysis."""
    REQUIREMENT_COVERAGE = "requirement_coverage"
    API_COMPLETENESS = "api_completeness"
    SCHEMA_COVERAGE = "schema_coverage"
    USER_STORY_TRACE = "user_story_trace"
    FULL_DIFFERENTIAL = "full_differential"


@dataclass
class GapFinding:
    """A single implementation gap discovered by the analysis."""
    requirement_id: str = ""
    requirement_title: str = ""
    requirement_description: str = ""
    priority: str = ""  # MUST, SHOULD, COULD
    status: ImplementationStatus = ImplementationStatus.UNKNOWN
    severity: GapSeverity = GapSeverity.MEDIUM
    confidence: float = 0.0
    matched_files: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    gap_description: str = ""
    suggested_tasks: List[str] = field(default_factory=list)
    linked_user_stories: List[str] = field(default_factory=list)
    linked_tasks: List[str] = field(default_factory=list)


@dataclass
class DifferentialReport:
    """Complete differential analysis report."""
    project_name: str = ""
    analysis_mode: str = ""
    timestamp: str = ""
    total_requirements: int = 0
    implemented: int = 0
    partial: int = 0
    missing: int = 0
    unknown: int = 0
    coverage_percent: float = 0.0
    findings: List[GapFinding] = field(default_factory=list)
    doc_files_loaded: int = 0
    code_files_loaded: int = 0
    simulation_steps: int = 0
    judge_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dict."""
        return {
            "project_name": self.project_name,
            "analysis_mode": self.analysis_mode,
            "timestamp": self.timestamp,
            "summary": {
                "total_requirements": self.total_requirements,
                "implemented": self.implemented,
                "partial": self.partial,
                "missing": self.missing,
                "unknown": self.unknown,
                "coverage_percent": round(self.coverage_percent, 2),
            },
            "doc_files_loaded": self.doc_files_loaded,
            "code_files_loaded": self.code_files_loaded,
            "simulation_steps": self.simulation_steps,
            "judge_confidence": round(self.judge_confidence, 2),
            "findings": [
                {
                    "requirement_id": f.requirement_id,
                    "requirement_title": f.requirement_title,
                    "priority": f.priority,
                    "status": f.status.value,
                    "severity": f.severity.value,
                    "confidence": round(f.confidence, 2),
                    "matched_files": f.matched_files,
                    "evidence": f.evidence[:3],
                    "gap_description": f.gap_description,
                    "suggested_tasks": f.suggested_tasks,
                    "linked_user_stories": f.linked_user_stories,
                    "linked_tasks": f.linked_tasks,
                }
                for f in self.findings
            ],
        }


# ---------------------------------------------------------------------------
# DifferentialAnalysisService
# ---------------------------------------------------------------------------


class DifferentialAnalysisService:
    """
    Compares documentation against generated code to find implementation gaps.

    Composes MCMPBackgroundSimulation with a differential Judge that evaluates
    whether documented requirements are present in the generated codebase.

    Usage::

        service = DifferentialAnalysisService(
            data_dir="Data/all_services/whatsapp",
            code_dir="Data/all_services/whatsapp/output",
        )
        await service.start()
        report = await service.run_analysis(mode=AnalysisMode.FULL_DIFFERENTIAL)
        print(json.dumps(report.to_dict(), indent=2))
        await service.stop()
    """

    # File extensions to index from code
    CODE_EXTENSIONS = {
        ".ts", ".tsx", ".js", ".jsx",
        ".py",
        ".prisma", ".sql",
        ".json",
        ".yaml", ".yml",
    }

    # Directories to skip when indexing code
    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", "dist", "build",
        ".next", ".cache", "coverage", ".vscode",
    }

    def __init__(
        self,
        data_dir: str,
        code_dir: Optional[str] = None,
        event_bus: Optional[Any] = None,
        config: Optional[SimulationConfig] = None,
        job_id: str = "differential",
        enable_supermemory: bool = True,
        epic_id: Optional[str] = None,
    ):
        """
        Initialize the differential analysis service.

        Args:
            data_dir: Path to the service data directory (e.g. Data/all_services/whatsapp)
                      containing user_stories.json, tasks/, MASTER_DOCUMENT.md
            code_dir: Path to the generated code directory. If None, uses data_dir/output
            event_bus: Optional EventBus for event publishing
            config: MCMP simulation configuration
            job_id: Unique job identifier for this analysis
            enable_supermemory: Whether to enrich analysis with Supermemory patterns
            epic_id: Optional epic ID to filter analysis to a single epic
                     (e.g. "EPIC-001"). When set, only tasks and requirements
                     related to this epic are loaded and analyzed.
        """
        self.data_dir = Path(data_dir)
        self.code_dir = Path(code_dir) if code_dir else self.data_dir / "output"
        self._event_bus = event_bus
        self._job_id = job_id
        self._enable_supermemory = enable_supermemory
        self._epic_id = epic_id

        self._config = config or SimulationConfig(
            num_agents=150,
            max_iterations=40,
            judge_every=5,
            steering_every=5,
            enable_llm_steering=True,
        )

        # Composed simulation engine
        self._simulation = MCMPBackgroundSimulation(
            config=self._config,
            on_context_update=self._on_simulation_update,
        )

        # Supermemory corpus loader (lazy init)
        self._corpus_loader = None

        # Loaded data
        self._user_stories: List[Dict[str, Any]] = []
        self._tasks: List[Dict[str, Any]] = []
        self._requirements: List[Dict[str, Any]] = []
        self._task_map: Dict[str, Dict[str, Any]] = {}  # task_id -> task
        self._epic_requirements: set = set()  # requirement IDs for this epic

        # State
        self._running = False
        self._reports: List[DifferentialReport] = []
        self._doc_count = 0
        self._code_count = 0
        self._llm_client = None

        self.logger = logger.bind(
            component="DifferentialAnalysis",
            job_id=job_id,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def reports(self) -> List[DifferentialReport]:
        return list(self._reports)

    @property
    def user_story_count(self) -> int:
        return len(self._user_stories)

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def requirement_count(self) -> int:
        return len(self._requirements)

    # ------------------------------------------------------------------
    # Initialization
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
                job_id=f"differential_{self._job_id}"
            )
            await self._corpus_loader.initialize()
        except Exception as e:
            self.logger.debug("supermemory_init_failed", error=str(e))

    async def start(self) -> bool:
        """
        Start the differential analysis service.

        Loads documentation and code into the MCMP corpus.

        Returns:
            True if started successfully.
        """
        if self._running:
            self.logger.warning("already_running")
            return False

        # Load documentation
        doc_count = await self._load_documentation()
        if doc_count == 0:
            self.logger.warning("no_docs_loaded", data_dir=str(self.data_dir))
            return False

        # Load generated code
        code_count = await self._load_code()

        # Load Supermemory patterns
        await self._init_supermemory()
        if self._corpus_loader and self._corpus_loader.available:
            memory_docs = await self._corpus_loader.fetch_as_mcmp_documents(
                query="implementation completeness requirements coverage",
                limit=15,
            )
            if memory_docs:
                self._simulation.add_documents(memory_docs)
                self.logger.info("memory_patterns_loaded", count=len(memory_docs))

        self._running = True
        self.logger.info(
            "differential_started",
            docs_loaded=doc_count,
            code_loaded=code_count,
            user_stories=len(self._user_stories),
            tasks=len(self._tasks),
        )
        return True

    async def stop(self) -> None:
        """Stop the analysis service and clean up."""
        self._running = False

        try:
            if self._simulation.is_running:
                await self._simulation.stop()
        except Exception:
            pass

        if self._corpus_loader:
            try:
                await self._corpus_loader.close()
            except Exception:
                pass

        if self._llm_client:
            try:
                await self._llm_client.close()
            except Exception:
                pass

        self.logger.info("differential_stopped", reports=len(self._reports))

    # ------------------------------------------------------------------
    # Documentation Loading
    # ------------------------------------------------------------------

    async def _load_documentation(self) -> int:
        """
        Load all documentation files into the MCMP corpus.

        Returns:
            Number of documents loaded.
        """
        documents = []

        # 1. Load epic task files first (populates _epic_requirements for filtering)
        task_docs = await self._load_tasks()
        documents.extend(task_docs)

        # 2. Load user stories (filtered by _epic_requirements when epic_id is set)
        us_docs = await self._load_user_stories()
        documents.extend(us_docs)

        # 3. Load MASTER_DOCUMENT.md sections
        master_docs = await self._load_master_document()
        documents.extend(master_docs)

        # 4. Load journal (requirement nodes) if exists
        journal_docs = await self._load_journal()
        documents.extend(journal_docs)

        if documents:
            added = self._simulation.add_documents(documents)
            self._doc_count = added
            self.logger.info("documentation_loaded", documents=added)
            return added

        return 0

    async def _load_user_stories(self) -> List[str]:
        """Load user_stories.json as MCMP documents.

        When ``_epic_requirements`` is populated (per-epic mode), only stories
        whose ``id`` or ``linked_requirement`` matches are loaded.
        """
        path = self.data_dir / "user_stories.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stories = data if isinstance(data, list) else data.get("user_stories", [])

            docs = []
            for story in stories:
                # Per-epic filter: skip stories not related to this epic
                if self._epic_requirements:
                    story_id = story.get("id", "")
                    linked_req = story.get("linked_requirement", "")
                    if (
                        story_id not in self._epic_requirements
                        and linked_req not in self._epic_requirements
                    ):
                        continue
                story_id = story.get("id", "")
                title = story.get("title", "")
                priority = story.get("priority", "COULD")
                linked_req = story.get("linked_requirement", "")
                description = story.get("description", "")
                as_a = story.get("as_a", "")
                i_want = story.get("i_want", "")
                so_that = story.get("so_that", "")

                # Build MCMP document
                doc = (
                    f"// Requirement: {linked_req} | UserStory: {story_id}\n"
                    f"// Priority: {priority}\n"
                    f"// Title: {title}\n"
                    f"As a {as_a}, I want {i_want}, so that {so_that}\n"
                    f"{description[:2000]}"
                )
                docs.append(doc)

                # Track for analysis
                self._user_stories.append(story)
                self._requirements.append({
                    "id": linked_req or story_id,
                    "title": title,
                    "description": description or f"As a {as_a}, I want {i_want}, so that {so_that}",
                    "priority": priority,
                    "source": "user_story",
                    "user_story_id": story_id,
                })

            self.logger.info("user_stories_loaded", count=len(docs))
            return docs

        except Exception as e:
            self.logger.warning("user_stories_load_error", error=str(e))
            return []

    async def _load_tasks(self) -> List[str]:
        """Load epic task JSON files as MCMP documents.

        When ``_epic_id`` is set, only the matching task file is loaded
        (e.g. ``epic-001-tasks.json`` for ``EPIC-001``) and the requirement
        IDs referenced by those tasks are collected into ``_epic_requirements``.
        """
        tasks_dir = self.data_dir / "tasks"
        if not tasks_dir.exists():
            return []

        # Determine which files to load
        if self._epic_id:
            # Derive file name from epic_id: "EPIC-001" -> "epic-001-tasks.json"
            slug = self._epic_id.lower().replace("_", "-")
            matching = [
                f for f in sorted(tasks_dir.glob("*.json"))
                if slug in f.stem.lower()
            ]
            task_files = matching if matching else sorted(tasks_dir.glob("*.json"))
        else:
            task_files = sorted(tasks_dir.glob("*.json"))

        docs = []
        for task_file in task_files:
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                tasks = data.get("tasks", [])
                epic_id = data.get("epic_id", "")
                epic_name = data.get("epic_name", "")

                for task in tasks:
                    task_id = task.get("id", "")
                    title = task.get("title", "")
                    desc = task.get("description", "")
                    status = task.get("status", "pending")
                    task_type = task.get("type", "")
                    output_files = task.get("output_files", [])
                    related_reqs = task.get("related_requirements", [])
                    related_stories = task.get("related_user_stories", [])

                    doc = (
                        f"// Task: {task_id} | Epic: {epic_id}\n"
                        f"// Type: {task_type} | Status: {status}\n"
                        f"// Title: {title}\n"
                        f"// Output: {', '.join(output_files[:5])}\n"
                        f"// Requirements: {', '.join(related_reqs)}\n"
                        f"{desc[:2000]}"
                    )
                    docs.append(doc)

                    self._tasks.append(task)
                    self._task_map[task_id] = task

                    # Collect requirement IDs for per-epic filtering
                    if self._epic_id:
                        self._epic_requirements.update(related_reqs)
                        self._epic_requirements.update(related_stories)

            except Exception as e:
                self.logger.debug("task_load_error", file=str(task_file), error=str(e))

        self.logger.info("tasks_loaded", count=len(docs))
        return docs

    async def _load_master_document(self) -> List[str]:
        """Load MASTER_DOCUMENT.md sections as MCMP documents."""
        path = self.data_dir / "MASTER_DOCUMENT.md"
        if not path.exists():
            return []

        try:
            content = path.read_text(encoding="utf-8")

            # Split by top-level headers (## or ###)
            sections = re.split(r'\n(?=#{2,3}\s)', content)
            docs = []
            for section in sections:
                section = section.strip()
                if not section or len(section) < 50:
                    continue
                # Take first 4000 chars of each section
                doc = f"// Documentation: MASTER_DOCUMENT.md\n{section[:4000]}"
                docs.append(doc)

            self.logger.info("master_document_loaded", sections=len(docs))
            return docs

        except Exception as e:
            self.logger.warning("master_doc_load_error", error=str(e))
            return []

    async def _load_journal(self) -> List[str]:
        """Load journal.json requirement nodes as MCMP documents."""
        path = self.data_dir / "journal.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            nodes = data.get("nodes", {})

            docs = []
            for node_key, node in nodes.items():
                req_id = node.get("requirement_id", "")
                title = node.get("title", "")
                description = node.get("description", "")
                req_type = node.get("type", "")
                priority = node.get("priority", "")
                acceptance = node.get("acceptance_criteria", [])
                stage = node.get("stage_name", "")

                acceptance_str = "\n".join(f"- {ac}" for ac in acceptance[:5])

                doc = (
                    f"// Journal: {req_id}\n"
                    f"// Type: {req_type} | Priority: {priority} | Stage: {stage}\n"
                    f"// Title: {title}\n"
                    f"{description[:1500]}\n"
                    f"Acceptance Criteria:\n{acceptance_str}"
                )
                docs.append(doc)

            self.logger.info("journal_loaded", nodes=len(docs))
            return docs

        except Exception as e:
            self.logger.debug("journal_load_error", error=str(e))
            return []

    # ------------------------------------------------------------------
    # Code Loading
    # ------------------------------------------------------------------

    async def _load_code(self) -> int:
        """
        Load generated code files into the MCMP corpus.

        Returns:
            Number of code files loaded.
        """
        if not self.code_dir.exists():
            self.logger.warning("code_dir_missing", path=str(self.code_dir))
            return 0

        documents = []

        for ext in self.CODE_EXTENSIONS:
            for f in self.code_dir.rglob(f"*{ext}"):
                if any(skip in f.parts for skip in self.SKIP_DIRS):
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    rel_path = str(f.relative_to(self.code_dir))
                    doc = f"// Code: {rel_path}\n{content[:4000]}"
                    documents.append(doc)

                except Exception as e:
                    self.logger.debug("code_read_error", path=str(f), error=str(e))

        if documents:
            added = self._simulation.add_documents(documents)
            self._code_count = added
            self.logger.info("code_loaded", files=added)
            return added

        return 0

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    async def run_analysis(
        self,
        mode: AnalysisMode = AnalysisMode.FULL_DIFFERENTIAL,
        focus_requirements: Optional[List[str]] = None,
    ) -> DifferentialReport:
        """
        Run the differential analysis.

        Args:
            mode: Analysis focus mode
            focus_requirements: Optional list of requirement IDs to focus on.
                              If None, analyzes all loaded requirements.

        Returns:
            DifferentialReport with gap findings.
        """
        if not self._running:
            self.logger.error("not_started")
            return DifferentialReport()

        report = DifferentialReport(
            project_name=self.data_dir.name,
            analysis_mode=mode.value,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            doc_files_loaded=self._doc_count,
            code_files_loaded=self._code_count,
        )

        # Filter requirements
        # Auto-focus on epic requirements when epic_id is set
        effective_focus = focus_requirements
        if not effective_focus and self._epic_requirements:
            effective_focus = list(self._epic_requirements)

        requirements = self._requirements
        if effective_focus:
            requirements = [
                r for r in requirements
                if r["id"] in effective_focus
            ]

        report.total_requirements = len(requirements)

        # Build the differential query based on mode
        query = self._build_analysis_query(mode, requirements)

        # Load mode-specific Supermemory patterns
        if self._corpus_loader and self._corpus_loader.available:
            mem_query = f"{mode.value} implementation patterns"
            memory_docs = await self._corpus_loader.fetch_as_mcmp_documents(
                query=mem_query, limit=10,
            )
            if memory_docs:
                self._simulation.add_documents(memory_docs)

        # Start MCMP simulation
        started = await self._simulation.start(
            query=query,
            mode=JudgeMode.DEEP,
        )

        if not started:
            self.logger.warning("simulation_start_failed")
            self._reports.append(report)
            return report

        # Wait for simulation to complete
        while self._simulation.is_running:
            await asyncio.sleep(0.5)

        # Get simulation results
        results = self._simulation.get_results()
        report.simulation_steps = results.get("steps_completed", 0)

        top_results = results.get("top_results", [])

        # Run differential analysis on each requirement
        findings = await self._evaluate_requirements(
            requirements=requirements,
            top_results=top_results,
            mode=mode,
        )

        report.findings = findings

        # Compute summary stats
        for f in findings:
            if f.status == ImplementationStatus.IMPLEMENTED:
                report.implemented += 1
            elif f.status == ImplementationStatus.PARTIAL:
                report.partial += 1
            elif f.status == ImplementationStatus.MISSING:
                report.missing += 1
            else:
                report.unknown += 1

        if report.total_requirements > 0:
            report.coverage_percent = (
                (report.implemented + 0.5 * report.partial)
                / report.total_requirements
                * 100
            )

        # Average judge confidence
        if findings:
            report.judge_confidence = sum(f.confidence for f in findings) / len(findings)

        # Store significant gaps to Supermemory
        await self._store_significant_gaps(findings)

        self._reports.append(report)

        self.logger.info(
            "analysis_complete",
            mode=mode.value,
            total=report.total_requirements,
            implemented=report.implemented,
            partial=report.partial,
            missing=report.missing,
            coverage=f"{report.coverage_percent:.1f}%",
        )

        return report

    # ------------------------------------------------------------------
    # Requirement Evaluation
    # ------------------------------------------------------------------

    async def _evaluate_requirements(
        self,
        requirements: List[Dict[str, Any]],
        top_results: List[Dict[str, Any]],
        mode: AnalysisMode,
    ) -> List[GapFinding]:
        """
        Evaluate each requirement against discovered code using LLM Judge.
        """
        return await self._llm_evaluate(requirements, top_results, mode)

    async def _llm_evaluate(
        self,
        requirements: List[Dict[str, Any]],
        top_results: List[Dict[str, Any]],
        mode: AnalysisMode,
    ) -> List[GapFinding]:
        """Use LLM Judge to evaluate requirement coverage."""
        import httpx

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not set — LLM Judge requires an API key"
            )

        if not self._llm_client:
            self._llm_client = httpx.AsyncClient(timeout=60.0)

        # Build code context from top results
        code_context = "\n\n".join(
            r.get("content", "")[:1500]
            for r in top_results[:15]
        )

        findings = []
        max_retries = 2

        # Process in batches of 5 requirements
        for batch_start in range(0, len(requirements), 5):
            batch = requirements[batch_start:batch_start + 5]

            req_text = ""
            for req in batch:
                req_text += (
                    f"\n--- Requirement {req['id']} ---\n"
                    f"Title: {req['title']}\n"
                    f"Priority: {req['priority']}\n"
                    f"Description: {req['description'][:500]}\n"
                )

            prompt = self._build_judge_prompt(req_text, code_context, mode)

            # Retry loop for transient failures
            for attempt in range(max_retries + 1):
                try:
                    response = await self._llm_client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": get_model("judge"),
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1,
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]
                        batch_findings = self._parse_judge_response(content, batch)
                        findings.extend(batch_findings)
                        break  # success
                    elif response.status_code in (429, 500, 502, 503):
                        # Retryable error
                        wait = 2 ** attempt
                        self.logger.warning(
                            "llm_judge_retrying",
                            status=response.status_code,
                            attempt=attempt + 1,
                            wait=wait,
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(wait)
                        else:
                            self.logger.error(
                                "llm_judge_failed",
                                status=response.status_code,
                                body=response.text[:200],
                            )
                    else:
                        self.logger.error(
                            "llm_judge_error",
                            status=response.status_code,
                            body=response.text[:200],
                        )
                        break  # non-retryable

                except httpx.TimeoutException:
                    if attempt < max_retries:
                        self.logger.warning(
                            "llm_judge_timeout_retry",
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise

        return findings

    def _build_judge_prompt(
        self,
        req_text: str,
        code_context: str,
        mode: AnalysisMode,
    ) -> str:
        """Build the differential Judge prompt."""
        mode_instruction = {
            AnalysisMode.REQUIREMENT_COVERAGE: "Focus on whether each requirement has corresponding implementation code.",
            AnalysisMode.API_COMPLETENESS: "Focus on whether API endpoints are implemented for each requirement.",
            AnalysisMode.SCHEMA_COVERAGE: "Focus on whether database schemas/models cover the data requirements.",
            AnalysisMode.USER_STORY_TRACE: "Focus on whether user stories are traceable to implemented features.",
            AnalysisMode.FULL_DIFFERENTIAL: "Comprehensively evaluate all aspects: code, APIs, schemas, and features.",
        }.get(mode, "Evaluate implementation completeness.")

        return f"""You are a Differential Analysis Judge. Compare requirements against generated code.

TASK: {mode_instruction}

For each requirement below, determine:
1. STATUS: "implemented" | "partial" | "missing"
2. CONFIDENCE: 0.0-1.0
3. EVIDENCE: Which code files (if any) implement this requirement
4. GAP: What's missing (if not fully implemented)
5. TASKS: Suggested implementation tasks (if incomplete)

REQUIREMENTS:
{req_text}

GENERATED CODE CONTEXT:
{code_context[:6000]}

OUTPUT FORMAT (one JSON block per requirement):
```json
[
  {{
    "requirement_id": "...",
    "status": "implemented|partial|missing",
    "confidence": 0.85,
    "matched_files": ["file1.ts", "file2.prisma"],
    "evidence": ["Found UserController with login endpoint"],
    "gap_description": "Missing password reset flow",
    "suggested_tasks": ["Implement POST /auth/reset-password endpoint"]
  }}
]
```

IMPORTANT:
- Be conservative: mark as "implemented" only if code clearly satisfies the requirement
- Mark "partial" if some aspects are present but incomplete
- Mark "missing" if no relevant code was found
- Include specific file names in matched_files
- Provide actionable suggested_tasks for gaps"""

    def _parse_judge_response(
        self,
        content: str,
        requirements: List[Dict[str, Any]],
    ) -> List[GapFinding]:
        """Parse LLM Judge response into GapFindings."""
        findings = []

        # Try to extract JSON from response (greedy to capture full array)
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            try:
                items = json.loads(json_match.group())

                # Map requirement IDs for lookup
                req_map = {r["id"]: r for r in requirements}

                for item in items:
                    req_id = item.get("requirement_id", "")
                    req = req_map.get(req_id, {})

                    status_str = item.get("status", "unknown")
                    try:
                        status = ImplementationStatus(status_str)
                    except ValueError:
                        status = ImplementationStatus.UNKNOWN

                    priority = req.get("priority", "COULD")
                    severity = self._compute_severity(status, priority)

                    finding = GapFinding(
                        requirement_id=req_id,
                        requirement_title=req.get("title", ""),
                        requirement_description=req.get("description", "")[:200],
                        priority=priority,
                        status=status,
                        severity=severity,
                        confidence=float(item.get("confidence", 0.5)),
                        matched_files=item.get("matched_files", []),
                        evidence=item.get("evidence", []),
                        gap_description=item.get("gap_description", ""),
                        suggested_tasks=item.get("suggested_tasks", []),
                        linked_user_stories=[req.get("user_story_id", "")],
                    )

                    # Cross-reference with tasks
                    finding.linked_tasks = self._find_related_tasks(req_id)

                    findings.append(finding)

                return findings

            except json.JSONDecodeError:
                self.logger.debug("json_parse_error", content=content[:200])

        # If JSON parsing fails, create findings from the requirements list
        for req in requirements:
            findings.append(GapFinding(
                requirement_id=req["id"],
                requirement_title=req.get("title", ""),
                priority=req.get("priority", "COULD"),
                status=ImplementationStatus.UNKNOWN,
                confidence=0.0,
                gap_description="Judge response could not be parsed",
            ))

        return findings

    def _heuristic_evaluate(
        self,
        requirements: List[Dict[str, Any]],
        top_results: List[Dict[str, Any]],
    ) -> List[GapFinding]:
        """
        Heuristic evaluation when LLM is not available.

        Matches requirements against code using keyword overlap.
        """
        findings = []

        # Build code keyword index
        code_keywords: Dict[str, List[str]] = {}
        for result in top_results:
            content = result.get("content", "").lower()
            doc_id = result.get("id", "")
            # Extract identifiers (camelCase, snake_case, etc.)
            words = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', content))
            for w in words:
                # Split camelCase
                parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', w)
                for p in parts:
                    p_lower = p.lower()
                    if p_lower not in code_keywords:
                        code_keywords[p_lower] = []
                    code_keywords[p_lower].append(doc_id)

        for req in requirements:
            title = req.get("title", "").lower()
            desc = req.get("description", "").lower()
            priority = req.get("priority", "COULD")

            # Extract keywords from requirement
            req_words = set(re.findall(r'[a-z]{3,}', f"{title} {desc}"))
            # Remove common stop words
            stop_words = {"the", "and", "for", "with", "that", "this", "from", "have", "can", "will", "should", "must"}
            req_words -= stop_words

            # Count matches
            matched_docs = set()
            match_count = 0
            for w in req_words:
                if w in code_keywords:
                    match_count += 1
                    matched_docs.update(code_keywords[w][:3])

            # Determine status based on match ratio
            if len(req_words) > 0:
                ratio = match_count / len(req_words)
            else:
                ratio = 0

            if ratio >= 0.5:
                status = ImplementationStatus.IMPLEMENTED
                confidence = min(0.7, ratio)
            elif ratio >= 0.2:
                status = ImplementationStatus.PARTIAL
                confidence = 0.4
            else:
                status = ImplementationStatus.MISSING
                confidence = 0.3

            severity = self._compute_severity(status, priority)

            finding = GapFinding(
                requirement_id=req["id"],
                requirement_title=req.get("title", ""),
                requirement_description=req.get("description", "")[:200],
                priority=priority,
                status=status,
                severity=severity,
                confidence=confidence,
                matched_files=list(matched_docs)[:5],
                gap_description="" if status == ImplementationStatus.IMPLEMENTED
                    else f"Low keyword overlap ({ratio:.0%}) between requirement and code",
                linked_user_stories=[req.get("user_story_id", "")],
                linked_tasks=self._find_related_tasks(req["id"]),
            )
            findings.append(finding)

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_analysis_query(
        self,
        mode: AnalysisMode,
        requirements: List[Dict[str, Any]],
    ) -> str:
        """Build the MCMP query for the analysis mode."""
        base = "differential analysis: compare documentation requirements against generated code"

        if mode == AnalysisMode.API_COMPLETENESS:
            return f"{base} focusing on API endpoints, routes, controllers"
        elif mode == AnalysisMode.SCHEMA_COVERAGE:
            return f"{base} focusing on database schemas, Prisma models, data entities"
        elif mode == AnalysisMode.USER_STORY_TRACE:
            return f"{base} focusing on user story traceability to implementation"
        elif mode == AnalysisMode.REQUIREMENT_COVERAGE:
            # Include some requirement titles for focused search
            titles = [r["title"] for r in requirements[:10]]
            return f"{base}: {', '.join(titles)}"
        else:
            return base

    def _compute_severity(self, status: ImplementationStatus, priority: str) -> GapSeverity:
        """Compute gap severity from status and requirement priority."""
        if status == ImplementationStatus.IMPLEMENTED:
            return GapSeverity.LOW

        priority_upper = priority.upper()
        if status == ImplementationStatus.MISSING:
            if priority_upper == "MUST":
                return GapSeverity.CRITICAL
            elif priority_upper == "SHOULD":
                return GapSeverity.HIGH
            else:
                return GapSeverity.MEDIUM
        elif status == ImplementationStatus.PARTIAL:
            if priority_upper == "MUST":
                return GapSeverity.HIGH
            elif priority_upper == "SHOULD":
                return GapSeverity.MEDIUM
            else:
                return GapSeverity.LOW

        return GapSeverity.MEDIUM

    def _find_related_tasks(self, requirement_id: str) -> List[str]:
        """Find tasks related to a requirement."""
        related = []
        for task in self._tasks:
            related_reqs = task.get("related_requirements", [])
            related_stories = task.get("related_user_stories", [])
            if requirement_id in related_reqs or requirement_id in related_stories:
                related.append(task.get("id", ""))
        return related[:10]

    async def _store_significant_gaps(self, findings: List[GapFinding]) -> int:
        """Store significant gaps to Supermemory for future reference."""
        if not self._corpus_loader or not self._corpus_loader.available:
            return 0

        stored = 0
        for finding in findings:
            if (
                finding.status in (ImplementationStatus.MISSING, ImplementationStatus.PARTIAL)
                and finding.confidence >= 0.6
                and finding.severity in (GapSeverity.CRITICAL, GapSeverity.HIGH)
            ):
                content = (
                    f"Implementation gap: {finding.requirement_id}\n"
                    f"Title: {finding.requirement_title}\n"
                    f"Status: {finding.status.value}\n"
                    f"Gap: {finding.gap_description}\n"
                    f"Tasks: {', '.join(finding.suggested_tasks[:3])}"
                )
                success = await self._corpus_loader.store_pattern(
                    content=content,
                    category="implementation_gap",
                    metadata={
                        "requirement_id": finding.requirement_id,
                        "severity": finding.severity.value,
                        "status": finding.status.value,
                    },
                )
                if success:
                    stored += 1

        if stored:
            self.logger.info("gaps_stored_to_supermemory", count=stored)
        return stored

    async def _on_simulation_update(self, update: Dict[str, Any]) -> None:
        """Callback from MCMP simulation updates."""
        if self._event_bus:
            try:
                await self._event_bus.publish(
                    "differential_analysis_update",
                    {
                        "job_id": self._job_id,
                        "step": update.get("step", 0),
                        "top_results_count": len(update.get("top_results", [])),
                    },
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_report(self, output_path: Optional[str] = None) -> str:
        """
        Export the latest report as JSON.

        Args:
            output_path: Path to write the JSON file. If None, uses data_dir.

        Returns:
            Path to the written file.
        """
        if not self._reports:
            return ""

        report = self._reports[-1]
        report_dict = report.to_dict()

        if not output_path:
            output_path = str(self.data_dir / "differential_report.json")

        Path(output_path).write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        self.logger.info("report_exported", path=output_path)
        return output_path

    def get_missing_requirements(self) -> List[GapFinding]:
        """Get all requirements marked as MISSING across all reports."""
        missing = []
        for report in self._reports:
            for f in report.findings:
                if f.status == ImplementationStatus.MISSING:
                    missing.append(f)
        return missing

    def get_critical_gaps(self) -> List[GapFinding]:
        """Get all CRITICAL severity gaps across all reports."""
        critical = []
        for report in self._reports:
            for f in report.findings:
                if f.severity == GapSeverity.CRITICAL:
                    critical.append(f)
        return critical
