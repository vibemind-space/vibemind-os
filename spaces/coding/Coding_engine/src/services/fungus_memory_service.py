# -*- coding: utf-8 -*-
"""
Fungus Memory Service - Phase 18

Memory-augmented MCMP (Mycelial Collective Pheromone Search) service that
searches Supermemory alongside code files. The MCMP swarm discovers cross-domain
correlations between past experiences (memories) and current code via pheromone
trails.

Features:
1. Mixed MCMP corpus: code files + Supermemory memories
2. Memory-correlation Judge LLM (pattern recall, fix recall, learning)
3. Learning loop: stores successful patterns back to Supermemory
4. Graceful degradation without SUPERMEMORY_API_KEY or OPENROUTER_API_KEY
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
from typing import Any, Dict, List, Optional

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

class MemoryJudgeMode(Enum):
    """Memory-specific judge modes."""
    PATTERN_RECALL = "pattern_recall"
    ERROR_FIX_RECALL = "error_fix_recall"
    CONTEXT_ENRICHMENT = "context_enrichment"
    LEARNING = "learning"


@dataclass
class MemoryCorrelation:
    """A discovered correlation between a memory and code."""
    memory_id: str = ""
    memory_category: str = ""
    memory_content: str = ""
    related_code_files: List[str] = field(default_factory=list)
    correlation_type: str = ""  # similar_pattern, applicable_fix, architecture_match
    relevance_score: float = 0.0
    description: str = ""
    suggested_action: str = ""


@dataclass
class MemoryReport:
    """Aggregated report from a memory search round."""
    round_number: int = 0
    correlations: List[MemoryCorrelation] = field(default_factory=list)
    memories_searched: int = 0
    code_files_analyzed: int = 0
    simulation_steps: int = 0
    new_patterns_found: int = 0
    focus_query: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# FungusMemoryService
# ---------------------------------------------------------------------------

class FungusMemoryService:
    """
    Memory-augmented MCMP search service.

    Composes MCMPBackgroundSimulation + SupermemoryTools to discover
    correlations between past experiences and current code via MCMP
    pheromone trails.
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
        job_id: str = "memory_search",
    ):
        self.working_dir = Path(working_dir)
        self._event_bus = event_bus
        self._job_id = job_id
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

        # Supermemory corpus loader (shared utility, lazy init)
        self._corpus_loader = None
        self._supermemory = None
        self._supermemory_available = False

        # State
        self._running = False
        self._round_number = 0
        self._reports: List[MemoryReport] = []
        self._file_hashes: Dict[str, str] = {}
        self._indexed_count = 0
        self._memory_count = 0
        self._loaded_memory_ids: set = set()
        self._llm_client = None
        self._new_patterns: List[Dict[str, Any]] = []

        self.logger = logger.bind(component="FungusMemory", job_id=job_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, seed_queries: Optional[List[str]] = None) -> bool:
        """
        Start the memory service.

        Args:
            seed_queries: Initial queries to fetch memories for.

        Returns:
            True if started successfully.
        """
        if self._running:
            self.logger.warning("already_running")
            return False

        # IMPORTANT: Initialize the MCMP retriever BEFORE importing
        # SupermemoryTools. The src.tools package __init__.py triggers
        # 4000+ module imports (anthropic, aiohttp, etc.) that poison
        # JAX's DLL initialization on Windows.
        self._simulation._init_retriever()

        # Initialize Supermemory client (may trigger large import chain)
        await self._init_supermemory()

        # Index code files
        indexed = await self.reindex_project()

        # Load initial memories if Supermemory is available
        if self._supermemory_available and seed_queries:
            for query in seed_queries[:5]:
                await self.load_memories(query=query, limit=20)

        # Need at least some documents (code or memories)
        total = self._indexed_count + self._memory_count
        if total == 0:
            self.logger.warning("no_documents", working_dir=str(self.working_dir))
            return False

        self._running = True
        self.logger.info(
            "memory_service_started",
            files_indexed=self._indexed_count,
            memories_loaded=self._memory_count,
            supermemory_available=self._supermemory_available,
        )
        return True

    async def reindex_project(self) -> int:
        """
        Index all source files in the working directory.

        Returns:
            Number of files indexed.
        """
        documents = []

        for ext in self.INDEX_EXTENSIONS:
            for f in self.working_dir.rglob(f"*{ext}"):
                if any(skip in f.parts for skip in self.SKIP_DIRS):
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    content_hash = hashlib.md5(content.encode()).hexdigest()
                    rel_path = str(f.relative_to(self.working_dir))

                    if self._file_hashes.get(rel_path) == content_hash:
                        continue

                    self._file_hashes[rel_path] = content_hash
                    doc = f"// File: {rel_path}\n{content[:4000]}"
                    documents.append(doc)

                except Exception as e:
                    self.logger.debug("file_read_error", path=str(f), error=str(e))

        if documents:
            self._simulation.clear_documents()
            added = self._simulation.add_documents(documents)
            self._indexed_count = added
            self.logger.info("project_indexed", files=added)
            return added

        return self._indexed_count

    async def reindex_file(self, file_path: str) -> bool:
        """
        Incrementally re-index a single file.

        Returns:
            True if file was re-indexed (content changed).
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
                return False

            self._file_hashes[rel_path] = content_hash
            self.logger.debug("file_changed", path=rel_path)
            return True

        except Exception as e:
            self.logger.debug("reindex_file_error", path=file_path, error=str(e))
            return False

    async def load_memories(
        self,
        query: str,
        category: str = "all",
        limit: int = 50,
    ) -> int:
        """
        Fetch memories from Supermemory and add to MCMP corpus.

        Delegates to SupermemoryCorpusLoader for fetch + dedup, then
        adds formatted documents to the MCMP simulation.

        Returns:
            Number of new memories added.
        """
        if not self._corpus_loader or not self._corpus_loader.available:
            return 0

        memory_docs = await self._corpus_loader.fetch_as_mcmp_documents(
            query=query,
            category=category,
            limit=limit,
        )

        if memory_docs:
            self._simulation.add_documents(memory_docs)
            self._memory_count += len(memory_docs)

        return len(memory_docs)

    async def run_memory_round(
        self,
        focus_query: str,
        mode: MemoryJudgeMode = MemoryJudgeMode.PATTERN_RECALL,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> MemoryReport:
        """
        Run one memory search round with Judge evaluation.

        Args:
            focus_query: What to search for
            mode: Memory judge mode
            task_context: Optional context from current task

        Returns:
            MemoryReport with correlations.
        """
        self._round_number += 1
        report = MemoryReport(
            round_number=self._round_number,
            memories_searched=self._memory_count,
            code_files_analyzed=self._indexed_count,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            focus_query=focus_query,
        )

        # Re-index if files changed
        await self.reindex_project()

        # Load fresh memories for this query if Supermemory is available
        if self._supermemory_available:
            await self.load_memories(query=focus_query, limit=30)

        # Start simulation for the focus query
        started = await self._simulation.start(
            query=focus_query,
            mode=JudgeMode.DEEP,
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

        top_results = results.get("top_results", [])

        # Run memory Judge
        correlations, new_patterns = await self._run_memory_judge(
            focus_query=focus_query,
            mode=mode,
            top_results=top_results,
            task_context=task_context,
        )

        report.correlations = correlations
        report.new_patterns_found = len(new_patterns)

        # Track new patterns for later storage
        self._new_patterns.extend(new_patterns)

        # Stop simulation for this round
        await self._simulation.stop()

        self._reports.append(report)

        self.logger.info(
            "memory_round_complete",
            round=self._round_number,
            correlations=len(correlations),
            new_patterns=len(new_patterns),
        )

        return report

    async def store_pattern(
        self,
        content: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store a new pattern back to Supermemory.

        Delegates to SupermemoryCorpusLoader.

        Returns:
            True if stored successfully.
        """
        if not self._corpus_loader or not self._corpus_loader.available:
            return False

        return await self._corpus_loader.store_pattern(
            content=content,
            category=category,
            metadata={
                "source": "fungus_memory",
                **(metadata or {}),
            },
        )

    async def store_pending_patterns(self) -> int:
        """Store all accumulated new patterns to Supermemory."""
        stored = 0
        for pattern in self._new_patterns:
            content = pattern.get("content", "")
            category = pattern.get("category", "code_pattern")
            if content and await self.store_pattern(content, category, pattern.get("metadata")):
                stored += 1

        self._new_patterns.clear()
        return stored

    async def stop(self) -> List[MemoryReport]:
        """Stop the memory service and return all reports."""
        self._running = False

        if self._simulation.is_running:
            await self._simulation.stop()

        self.logger.info(
            "memory_service_stopped",
            rounds=len(self._reports),
            total_correlations=sum(len(r.correlations) for r in self._reports),
        )

        return self._reports

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def reports(self) -> List[MemoryReport]:
        return list(self._reports)

    @property
    def indexed_count(self) -> int:
        return self._indexed_count

    @property
    def memory_count(self) -> int:
        return self._memory_count

    # ------------------------------------------------------------------
    # Private: Supermemory initialization
    # ------------------------------------------------------------------

    async def _init_supermemory(self) -> None:
        """Initialize Supermemory client via shared corpus loader."""
        from .supermemory_corpus_loader import SupermemoryCorpusLoader

        self._corpus_loader = SupermemoryCorpusLoader(job_id=self._job_id)
        await self._corpus_loader.initialize()
        self._supermemory_available = self._corpus_loader.available
        # Keep direct reference for store operations used by store_pattern()
        self._supermemory = self._corpus_loader._supermemory if self._corpus_loader.available else None

    # ------------------------------------------------------------------
    # Private: Memory Judge
    # ------------------------------------------------------------------

    async def _run_memory_judge(
        self,
        focus_query: str,
        mode: MemoryJudgeMode,
        top_results: List[Dict[str, Any]],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        Run memory-correlation Judge LLM on mixed code+memory results.

        Returns:
            (correlations, new_patterns) tuple.
        """
        if not top_results:
            return [], []

        if not await self._init_llm_client():
            return self._heuristic_correlation(top_results), []

        try:
            prompt = self._build_memory_prompt(
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
                self.logger.warning("memory_judge_failed", status=response.status_code)
                return self._heuristic_correlation(top_results), []

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            return self._parse_memory_response(content, top_results)

        except Exception as e:
            self.logger.warning("memory_judge_error", error=str(e))
            return self._heuristic_correlation(top_results), []

    def _build_memory_prompt(
        self,
        focus_query: str,
        mode: MemoryJudgeMode,
        top_results: List[Dict[str, Any]],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the memory-correlation Judge prompt."""

        # Format discovered snippets (mixed code + memories)
        snippets = []
        for i, r in enumerate(top_results[:10]):
            content = r.get("content", "")[:600]
            score = r.get("relevance_score", 0.0)
            doc_type = "MEMORY" if content.startswith("// Memory:") else "CODE"
            snippets.append(f"[{i}] ({doc_type}) score={score:.3f}\n{content}")

        snippets_text = "\n---\n".join(snippets)

        # Task context
        task_text = ""
        if task_context:
            task_text = f"\nCurrent task: \"{task_context.get('title', '')}\" (type: {task_context.get('type', '')})"
            if task_context.get("error_message"):
                task_text += f"\nError: {task_context['error_message'][:200]}"

        # Mode-specific instructions
        mode_instructions = {
            MemoryJudgeMode.PATTERN_RECALL: (
                "Focus on PATTERN RECALL:\n"
                "- Which memories describe patterns similar to the current code?\n"
                "- Are there reusable patterns from past projects?\n"
                "- Which code files would benefit from applying remembered patterns?"
            ),
            MemoryJudgeMode.ERROR_FIX_RECALL: (
                "Focus on ERROR FIX RECALL:\n"
                "- Do any error_fix memories describe fixes for the current error?\n"
                "- Which past fixes could be applied to resolve the issue?\n"
                "- What was the root cause in similar past errors?"
            ),
            MemoryJudgeMode.CONTEXT_ENRICHMENT: (
                "Focus on CONTEXT ENRICHMENT:\n"
                "- What additional context do memories provide for the current task?\n"
                "- Are there architecture decisions from past projects that apply?\n"
                "- Which memories help understand the current codebase better?"
            ),
            MemoryJudgeMode.LEARNING: (
                "Focus on LEARNING:\n"
                "- What new patterns in the code are worth remembering?\n"
                "- Are there successful strategies that should be stored?\n"
                "- What error fixes or architecture decisions should be preserved?"
            ),
        }

        analysis_focus = mode_instructions.get(mode, mode_instructions[MemoryJudgeMode.PATTERN_RECALL])

        return f"""You are a memory-correlation judge analyzing connections between past experiences (MEMORY documents) and current code (CODE documents).

Query: "{focus_query}"
{task_text}

The MCMP swarm simulation discovered these code+memory correlations:
{snippets_text}

{analysis_focus}

Return a JSON object:
{{
  "correlations": [
    {{
      "memory_id": "id from // Memory: header or empty",
      "memory_category": "code_pattern|error_fix|architecture|project_generation",
      "correlation_type": "similar_pattern|applicable_fix|architecture_match|context_enrichment",
      "related_code_files": ["path/to/file"],
      "relevance_score": 0.0-1.0,
      "description": "what the correlation means",
      "suggested_action": "what to do with this correlation"
    }}
  ],
  "new_patterns_to_store": [
    {{
      "content": "pattern description worth remembering",
      "category": "code_pattern|error_fix|architecture",
      "metadata": {{"framework": "Hono", "context": "..."}}
    }}
  ]
}}

Rules:
- Only report correlations with relevance >= 0.5
- Extract memory IDs from // Memory: headers (format: category/id)
- Extract file paths from // File: headers
- For LEARNING mode, focus on new_patterns_to_store
- If no meaningful correlations found, return empty arrays"""

    def _parse_memory_response(
        self,
        response: str,
        top_results: List[Dict[str, Any]],
    ) -> tuple:
        """Parse Judge LLM memory response into correlations + new patterns."""
        parsed = self._parse_json_response(response)
        if not parsed:
            return [], []

        correlations = []
        for c in parsed.get("correlations", []):
            if not isinstance(c, dict):
                continue

            score = float(c.get("relevance_score", 0.0))
            if score < 0.5:
                continue

            correlations.append(MemoryCorrelation(
                memory_id=c.get("memory_id", ""),
                memory_category=c.get("memory_category", ""),
                memory_content="",
                related_code_files=c.get("related_code_files", []),
                correlation_type=c.get("correlation_type", ""),
                relevance_score=score,
                description=c.get("description", ""),
                suggested_action=c.get("suggested_action", ""),
            ))

        new_patterns = []
        for p in parsed.get("new_patterns_to_store", []):
            if isinstance(p, dict) and p.get("content"):
                new_patterns.append(p)

        return correlations, new_patterns

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
    # Private: Heuristic correlation (fallback without LLM)
    # ------------------------------------------------------------------

    def _heuristic_correlation(
        self,
        top_results: List[Dict[str, Any]],
    ) -> List[MemoryCorrelation]:
        """
        Basic heuristic correlation without LLM.

        Finds code<->memory correlations by keyword matching.
        """
        correlations = []
        memories = []
        code_files = []

        # Separate memories and code
        for r in top_results:
            content = r.get("content", "")
            if content.startswith("// Memory:"):
                memories.append(r)
            elif content.startswith("// File:"):
                code_files.append(r)

        # Find keyword overlaps between memories and code
        for mem in memories:
            mem_content = mem.get("content", "")
            mem_header = mem_content.split("\n", 1)[0]
            mem_id = ""
            mem_category = ""
            if mem_header.startswith("// Memory: "):
                parts = mem_header.replace("// Memory: ", "").strip()
                if "/" in parts:
                    mem_category, mem_id = parts.split("/", 1)

            # Extract keywords from memory
            mem_words = set(re.findall(r'\b\w{4,}\b', mem_content.lower()))

            best_match_file = ""
            best_overlap = 0

            for code in code_files:
                code_content = code.get("content", "")
                code_words = set(re.findall(r'\b\w{4,}\b', code_content.lower()))

                overlap = len(mem_words & code_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    file_header = code_content.split("\n", 1)[0]
                    best_match_file = file_header.replace("// File: ", "").strip()

            if best_overlap >= 3 and best_match_file:
                score = min(1.0, best_overlap / 10.0)
                correlations.append(MemoryCorrelation(
                    memory_id=mem_id,
                    memory_category=mem_category,
                    memory_content=mem_content[:200],
                    related_code_files=[best_match_file],
                    correlation_type="similar_pattern",
                    relevance_score=score,
                    description=f"Keyword overlap ({best_overlap} shared terms) between memory and code",
                    suggested_action="Review memory for applicable patterns",
                ))

        return correlations

    # ------------------------------------------------------------------
    # Private: LLM client
    # ------------------------------------------------------------------

    async def _init_llm_client(self) -> bool:
        """Initialize async LLM client for memory Judge."""
        if self._llm_client is not None:
            return True

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            self.logger.debug("no_openrouter_key", msg="Using heuristic correlation only")
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
        pass
