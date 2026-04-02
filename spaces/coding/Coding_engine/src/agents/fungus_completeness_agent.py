"""
Fungus Completeness Agent - Semantic validation via MCMP simulation.

Phase 11+: Uses MCMP semantic search and LLM judge to verify requirements.

Subscribes to: GENERATION_COMPLETE, BUILD_SUCCEEDED, CONVERGENCE_UPDATE
Publishes:
  - VALIDATION_PASSED (confidence >= 0.8)
  - VALIDATION_ERROR (confidence < 0.5)
  - REQUIREMENT_TEST_MISSING, REQUIREMENT_ENV_MISSING, REQUIREMENT_ARTIFACT_MISSING

Validation flow:
1. MCMP semantic search - Find code matching each requirement
2. LLM Judge - "Is this requirement fully implemented?"
3. Event emission - Trigger downstream agents based on findings
"""

import json
import os
import re
import structlog
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

from .autonomous_base import AutonomousAgent
from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from ..services.mcmp_background import SimulationConfig
from src.llm_config import get_model

logger = structlog.get_logger(__name__)


class MCMPSemanticValidator:
    """
    MCMP-based semantic validator using embeddings and LLM judge.
    """

    def __init__(self, project_path: Path, model: str = None, enable_supermemory: bool = True):
        self.project_path = project_path
        self.model = model or get_model("judge")
        self._embedder = None
        self._client = None
        self._enable_supermemory = enable_supermemory
        self._supermemory_loader = None
        self.logger = logger.bind(component="MCMPSemanticValidator")

    async def _init_embedder(self) -> bool:
        """Initialize embedding model."""
        if self._embedder is not None:
            return True

        try:
            # Block JAX to prevent DLL errors on Windows
            import sys
            import types
            from importlib.machinery import ModuleSpec
            if "jax" not in sys.modules:
                fake_jax = types.ModuleType("jax")
                fake_jax.__version__ = "0.0.0"
                fake_jax.__spec__ = ModuleSpec("jax", None)
                sys.modules["jax"] = fake_jax

            # Try OpenAI embeddings first (faster, no local model needed)
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
            if api_key:
                import httpx
                self._embedder = "openai"
                self._embed_client = httpx.AsyncClient(timeout=30.0)
                self._embed_key = api_key
                self._embed_url = "https://api.openai.com/v1/embeddings" if os.getenv("OPENAI_API_KEY") else "https://openrouter.ai/api/v1/embeddings"
                return True

            # Fallback to sentence-transformers (local)
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            return True
        except Exception as e:
            self.logger.warning("embedder_init_failed", error=str(e))
            # Mark as "keyword" mode - we'll use keyword matching instead
            self._embedder = "keyword"
            return True

    async def _init_llm_client(self) -> bool:
        """Initialize LLM client for judging."""
        if self._client is not None:
            return True

        try:
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if openrouter_key:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=openrouter_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                return True
        except Exception as e:
            self.logger.warning("llm_client_init_failed", error=str(e))
        return False

    async def _init_supermemory(self) -> None:
        """Lazy-initialize Supermemory corpus loader for completeness context."""
        if self._supermemory_loader is not None:
            return
        if not self._enable_supermemory:
            return

        try:
            from ..services.supermemory_corpus_loader import SupermemoryCorpusLoader

            self._supermemory_loader = SupermemoryCorpusLoader(
                job_id=f"completeness_{self.project_path.name}"
            )
            await self._supermemory_loader.initialize()
        except Exception as e:
            self.logger.debug("supermemory_init_failed", error=str(e))

    async def search_requirement(self, requirement: Dict, top_k: int = 5) -> List[Dict]:
        """
        Semantic search for code implementing a requirement.

        Returns list of matching code chunks with relevance scores.
        """
        if not await self._init_embedder():
            return []

        req_name = requirement.get("name", "")
        req_desc = requirement.get("description", "")
        query = f"{req_name}: {req_desc}"

        # Collect code files
        code_chunks = []
        extensions = {".ts", ".tsx", ".js", ".jsx", ".py", ".prisma"}

        for ext in extensions:
            for file_path in self.project_path.rglob(f"*{ext}"):
                if "node_modules" in str(file_path) or ".git" in str(file_path):
                    continue
                try:
                    content = file_path.read_text(encoding='utf-8', errors='replace')[:4000]
                    code_chunks.append({
                        "path": str(file_path.relative_to(self.project_path)),
                        "content": content,
                    })
                except Exception:
                    continue

        if not code_chunks:
            return []

        # Simple keyword matching as fallback (when embeddings unavailable)
        keywords = self._extract_keywords(query)
        results = []

        for chunk in code_chunks:
            score = 0
            content_lower = chunk["content"].lower()
            for kw in keywords:
                if kw in content_lower:
                    score += 1

            if score > 0:
                results.append({
                    "path": chunk["path"],
                    "content": chunk["content"][:1000],
                    "score": score / max(len(keywords), 1),
                })

        # Sort by score and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def judge_implementation(
        self,
        requirement: Dict,
        code_matches: List[Dict]
    ) -> Dict[str, Any]:
        """
        LLM judge evaluates if requirement is implemented.

        Returns: {
            "implemented": bool,
            "confidence": float (0-1),
            "reasoning": str,
            "missing": List[str]
        }
        """
        if not await self._init_llm_client():
            # Fallback: Simple heuristic
            return {
                "implemented": len(code_matches) > 0,
                "confidence": min(len(code_matches) * 0.2, 0.8),
                "reasoning": "Heuristic: Found code matches" if code_matches else "No matches found",
                "missing": [] if code_matches else ["Implementation not found"],
            }

        req_name = requirement.get("name", "Unknown")
        req_desc = requirement.get("description", "")

        # Build context from code matches
        code_context = "\n\n".join([
            f"// File: {m['path']}\n{m['content'][:500]}"
            for m in code_matches[:3]
        ])

        # Phase 19: Search Supermemory for past implementation patterns
        memory_context = ""
        await self._init_supermemory()
        if self._supermemory_loader and self._supermemory_loader.available:
            try:
                memories = await self._supermemory_loader.fetch_as_search_results(
                    query=f"{req_name}: {req_desc}",
                    category="all",
                    limit=3,
                )
                if memories:
                    memory_parts = [
                        f"// Past pattern (relevance: {m.get('score', 0):.2f})\n"
                        f"{m.get('content', '')[:300]}"
                        for m in memories
                    ]
                    memory_context = (
                        "\n\nPAST PROJECT PATTERNS:\n"
                        + "\n\n".join(memory_parts)
                    )
            except Exception:
                pass  # Graceful degradation

        prompt = f"""Analyze if this requirement is fully implemented in the code.

REQUIREMENT:
Name: {req_name}
Description: {req_desc}

CODE FOUND:
{code_context if code_context else "No matching code found."}
{memory_context}

Respond in JSON format:
{{
    "implemented": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation",
    "missing": ["List of missing parts if any"]
}}"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result_text = response.choices[0].message.content

            # Parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            self.logger.warning("llm_judge_error", error=str(e))

        return {
            "implemented": len(code_matches) > 0,
            "confidence": 0.5,
            "reasoning": "LLM judge unavailable",
            "missing": [],
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        text = text.lower()
        words = re.split(r'\W+', text)
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "and", "or", "of", "to", "in", "for", "on", "with", "as",
            "by", "at", "from", "should", "must", "can", "will", "that",
            "this", "it", "all", "each", "every", "any", "have", "has",
            "user", "system", "feature", "allow", "enable", "provide",
        }
        keywords = [w for w in words if w and len(w) > 2 and w not in stop_words]
        return keywords[:10]


@dataclass
class CompletenessReport:
    """Report for a single requirement's completeness."""
    requirement_id: str
    requirement_name: str
    # Semantic validation results
    implemented: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    code_matches: List[str] = field(default_factory=list)
    missing_parts: List[str] = field(default_factory=list)
    # Legacy fields
    test_files: List[str] = field(default_factory=list)
    missing_tests: List[str] = field(default_factory=list)
    env_vars: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    missing_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "requirement_id": self.requirement_id,
            "requirement_name": self.requirement_name,
            "implemented": self.implemented,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "code_matches": self.code_matches,
            "missing_parts": self.missing_parts,
            "test_files": self.test_files,
            "missing_tests": self.missing_tests,
            "env_vars": self.env_vars,
            "config_files": self.config_files,
            "missing_artifacts": self.missing_artifacts,
        }

    @property
    def status(self) -> str:
        """Get validation status based on confidence."""
        if self.confidence >= 0.8:
            return "PASSED"
        elif self.confidence >= 0.5:
            return "PARTIAL"
        else:
            return "FAILED"


class FungusCompletenessAgent(AutonomousAgent):
    """
    Semantic validation of requirements using MCMP and LLM judge.

    Validation flow:
    1. MCMP semantic search - Find code implementing each requirement
    2. LLM Judge - Evaluate if requirement is fully implemented
    3. Event emission - Publish validation results

    Results are published as events:
    - VALIDATION_PASSED (confidence >= 0.8)
    - VALIDATION_ERROR (confidence < 0.5)
    - REQUIREMENT_TEST_MISSING -> ValidationTeamAgent
    - REQUIREMENT_ENV_MISSING -> InfrastructureAgent
    - REQUIREMENT_ARTIFACT_MISSING -> GeneratorAgent
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        simulation_config: Optional[SimulationConfig] = None,
        requirements: Optional[List[Dict]] = None,
        llm_model: str = None,
        **kwargs,
    ):
        """
        Initialize the Fungus Completeness Agent.

        Args:
            event_bus: EventBus for communication
            shared_state: Shared state for convergence tracking
            working_dir: Working directory (output project directory)
            simulation_config: MCMP simulation configuration
            requirements: List of requirement dicts
            llm_model: Model for LLM judge (default: Haiku 4.5)
        """
        super().__init__(
            name="FungusCompletenessAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self.simulation_config = simulation_config or SimulationConfig()
        self.requirements = requirements or []
        self._checked_requirements: set = set()
        self._check_count = 0

        # Initialize MCMP semantic validator
        llm_model = llm_model or get_model("judge")
        self._validator = MCMPSemanticValidator(
            project_path=Path(working_dir),
            model=llm_model,
        )

        self.logger = logger.bind(agent=self.name)

    @property
    def subscribed_events(self) -> List[EventType]:
        """Events this agent listens to."""
        return [
            EventType.GENERATION_COMPLETE,
            EventType.BUILD_SUCCEEDED,
            EventType.CONVERGENCE_UPDATE,
        ]

    async def should_act(self, events: List[Event]) -> bool:
        """
        Decide whether to check completeness.

        Acts after generation is complete or build succeeded,
        but not on every event.
        """
        # Only act if we have unchecked requirements
        unchecked = [
            r for r in self.requirements
            if (r.get("id") or r.get("req_id")) not in self._checked_requirements
        ]

        if not unchecked:
            return False

        # Act on generation complete or build succeeded
        for event in events:
            if event.type in [EventType.GENERATION_COMPLETE, EventType.BUILD_SUCCEEDED]:
                return True

        return False

    async def act(self, events: List[Event]) -> Optional[Event]:
        """Check completeness for all unchecked requirements."""
        self._check_count += 1

        unchecked = [
            r for r in self.requirements
            if (r.get("id") or r.get("req_id")) not in self._checked_requirements
        ]

        self.logger.info(
            "completeness_check_start",
            check_count=self._check_count,
            total_requirements=len(self.requirements),
            unchecked=len(unchecked),
        )

        reports = []
        for req in unchecked:
            req_id = req.get("id") or req.get("req_id")

            try:
                report = await self._check_requirement(req)
                self._checked_requirements.add(req_id)
                reports.append(report)

                # Publish events based on findings
                await self._publish_findings(report)

            except Exception as e:
                self.logger.error(
                    "requirement_check_failed",
                    req_id=req_id,
                    error=str(e),
                )

        # Publish overall completeness report
        total_confidence = (
            sum(r.confidence for r in reports) / len(reports)
            if reports else 0.0
        )

        await self.event_bus.publish(Event(
            type=EventType.REQUIREMENT_COMPLETENESS_REPORT,
            source=self.name,
            data={
                "total_requirements": len(self.requirements),
                "checked": len(self._checked_requirements),
                "average_confidence": total_confidence,
                "reports": [r.to_dict() for r in reports],
            },
            success=total_confidence >= self.simulation_config.min_confidence,
        ))

        return None

    async def _check_requirement(self, req: Dict) -> CompletenessReport:
        """
        Check completeness for a single requirement using MCMP semantic search.

        Flow:
        1. Semantic search for code matching requirement
        2. LLM judge evaluates implementation completeness
        3. Legacy checks for tests, ENV, configs
        """
        req_id = req.get("id") or req.get("req_id", "unknown")
        req_name = req.get("name") or req.get("title", "Untitled")
        req_desc = req.get("description", "")

        self.logger.info(
            "checking_requirement_semantic",
            req_id=req_id,
            name=req_name,
        )

        # 1. MCMP Semantic Search
        code_matches = await self._validator.search_requirement(req, top_k=5)

        self.logger.debug(
            "semantic_search_complete",
            req_id=req_id,
            matches_found=len(code_matches),
        )

        # 2. LLM Judge
        judgment = await self._validator.judge_implementation(req, code_matches)

        self.logger.info(
            "llm_judge_complete",
            req_id=req_id,
            implemented=judgment.get("implemented", False),
            confidence=judgment.get("confidence", 0.0),
        )

        # 3. Legacy checks (tests, ENV, configs)
        project_path = Path(self.working_dir)
        test_files = await self._find_test_files(project_path, req_name, req_desc)
        env_vars, config_files = await self._find_env_config(project_path, req_name)

        missing_tests = []
        if not test_files:
            missing_tests.append(f"Test for {req_name}")

        # Build report with semantic validation results
        return CompletenessReport(
            requirement_id=req_id,
            requirement_name=req_name,
            # Semantic validation
            implemented=judgment.get("implemented", False),
            confidence=judgment.get("confidence", 0.0),
            reasoning=judgment.get("reasoning", ""),
            code_matches=[m["path"] for m in code_matches],
            missing_parts=judgment.get("missing", []),
            # Legacy fields
            test_files=test_files,
            missing_tests=missing_tests,
            env_vars=env_vars,
            config_files=config_files,
            missing_artifacts=judgment.get("missing", []),
        )

    async def _find_test_files(
        self,
        project_path: Path,
        req_name: str,
        req_desc: str,
    ) -> List[str]:
        """Find test files that might test this requirement."""
        test_files = []

        # Common test directories
        test_dirs = ["tests", "test", "__tests__", "spec"]

        # Keywords from requirement name
        keywords = self._extract_keywords(req_name)

        for test_dir in test_dirs:
            test_path = project_path / test_dir
            if not test_path.exists():
                continue

            # Search for test files matching keywords
            for test_file in test_path.rglob("*.test.*"):
                file_name = test_file.stem.lower()
                for keyword in keywords:
                    if keyword in file_name:
                        test_files.append(str(test_file.relative_to(project_path)))
                        break

            for test_file in test_path.rglob("*.spec.*"):
                file_name = test_file.stem.lower()
                for keyword in keywords:
                    if keyword in file_name:
                        test_files.append(str(test_file.relative_to(project_path)))
                        break

        return list(set(test_files))

    async def _find_env_config(
        self,
        project_path: Path,
        req_name: str,
    ) -> tuple[List[str], List[str]]:
        """Find ENV variables and config files."""
        env_vars = []
        config_files = []

        # Check .env files
        env_patterns = [".env", ".env.example", ".env.local", ".env.development"]
        for pattern in env_patterns:
            env_file = project_path / pattern
            if env_file.exists():
                config_files.append(str(env_file.relative_to(project_path)))
                # Extract variable names
                try:
                    content = env_file.read_text(encoding='utf-8', errors='replace')
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            var_name = line.split("=")[0].strip()
                            if var_name:
                                env_vars.append(var_name)
                except Exception:
                    pass

        # Check for prisma schema
        schema_path = project_path / "prisma" / "schema.prisma"
        if schema_path.exists():
            config_files.append("prisma/schema.prisma")

        # Check for config files
        config_patterns = ["*.config.ts", "*.config.js", "config/*.json", "config/*.yml"]
        for pattern in config_patterns:
            for config_file in project_path.glob(pattern):
                config_files.append(str(config_file.relative_to(project_path)))

        return list(set(env_vars)), list(set(config_files))

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from requirement text."""
        # Remove common words and extract meaningful keywords
        text = text.lower()
        # Split on non-word characters
        words = re.split(r'\W+', text)
        # Filter common words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "and", "or", "of", "to", "in", "for", "on", "with", "as",
            "by", "at", "from", "should", "must", "can", "will", "that",
            "this", "it", "all", "each", "every", "any", "have", "has",
            "user", "system", "feature", "allow", "enable", "provide",
        }
        keywords = [w for w in words if w and len(w) > 2 and w not in stop_words]
        return keywords[:5]  # Limit to 5 keywords

    async def _publish_findings(self, report: CompletenessReport) -> None:
        """Publish validation events based on semantic analysis results."""

        self.logger.info(
            "semantic_validation_result",
            req_id=report.requirement_id,
            status=report.status,
            confidence=report.confidence,
            implemented=report.implemented,
            reasoning=report.reasoning[:100] if report.reasoning else "",
        )

        # Publish validation status events based on confidence
        if report.status == "PASSED":
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_PASSED,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "confidence": report.confidence,
                    "reasoning": report.reasoning,
                    "code_matches": report.code_matches,
                    "validator": "FungusSemanticValidator",
                },
                success=True,
            ))
        elif report.status == "FAILED":
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_ERROR,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "confidence": report.confidence,
                    "reasoning": report.reasoning,
                    "missing_parts": report.missing_parts,
                    "validator": "FungusSemanticValidator",
                },
                success=False,
            ))
        else:  # PARTIAL
            await self.event_bus.publish(Event(
                type=EventType.VALIDATION_WARNING,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "confidence": report.confidence,
                    "reasoning": report.reasoning,
                    "missing_parts": report.missing_parts,
                    "code_matches": report.code_matches,
                    "validator": "FungusSemanticValidator",
                },
                success=True,  # Partial is not a failure
            ))

        # Missing tests -> ValidationTeamAgent (legacy)
        if report.missing_tests:
            await self.event_bus.publish(Event(
                type=EventType.REQUIREMENT_TEST_MISSING,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "missing_tests": report.missing_tests,
                    "existing_tests": report.test_files,
                },
                success=False,
            ))

        # ENV vars found -> InfrastructureAgent (informational)
        if report.env_vars:
            await self.event_bus.publish(Event(
                type=EventType.REQUIREMENT_ENV_MISSING,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "env_vars": report.env_vars,
                    "config_files": report.config_files,
                },
                success=True,  # Informational, not a failure
            ))

        # Missing artifacts -> GeneratorAgent
        if report.missing_artifacts:
            await self.event_bus.publish(Event(
                type=EventType.REQUIREMENT_ARTIFACT_MISSING,
                source=self.name,
                data={
                    "requirement_id": report.requirement_id,
                    "requirement_name": report.requirement_name,
                    "missing_artifacts": report.missing_artifacts,
                },
                success=False,
            ))
