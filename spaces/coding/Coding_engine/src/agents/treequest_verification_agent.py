"""
TreeQuest Verification Agent - Uses AB-MCTS tree search to verify code against documentation.

This agent implements a Monte Carlo Tree Search (AB-MCTS) approach to systematically verify
that generated code is consistent with project documentation. It uses the TreeQuest library
from SakanaAI for the search algorithm and integrates with Fungus Memory for RAG-based
document retrieval.

Verification checks:
- API consistency: endpoints in code match documentation
- Data model consistency: entities/schemas match data dictionary
- Business logic: implementation matches user stories/requirements
- Security: authentication/authorization matches security requirements
- Performance: implementation follows performance guidelines
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from ..mind.event_bus import (
    EventBus,
    Event,
    EventType,
    agent_event,
    system_error_event,
)
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)

# Try importing TreeQuest (optional dependency)
try:
    from treequest import ABMCTSA
    from treequest.types import GenerateFnType, NodeStateT

    TREEQUEST_AVAILABLE = True
except ImportError:
    TREEQUEST_AVAILABLE = False
    logger.info("TreeQuest not installed, falling back to linear verification")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VerificationState:
    """State node for TreeQuest MCTS tree."""

    code_file: str
    code_chunk: str
    doc_chunks: List[str]
    finding_type: str  # api_consistency, data_model, business_logic, security, performance
    severity: str  # critical, high, medium, low, info
    confidence: float  # 0.0 - 1.0
    description: str = ""
    suggested_fix: str = ""
    line_range: Tuple[int, int] = (0, 0)
    parent_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code_file": self.code_file,
            "finding_type": self.finding_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "line_range": self.line_range,
        }


@dataclass
class VerificationFinding:
    """A verified finding from the tree search."""

    file: str
    line_range: Tuple[int, int]
    severity: str
    category: str
    description: str
    suggested_fix: str
    score: float  # Aggregated confidence score

    @property
    def fingerprint(self) -> str:
        raw = f"{self.file}:{self.line_range}:{self.category}:{self.description[:80]}"
        return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Code Chunker
# ---------------------------------------------------------------------------

class CodeChunker:
    """Splits source files into overlapping chunks for verification."""

    def __init__(self, chunk_size: int = 40, overlap: int = 5):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: Path) -> List[Tuple[str, Tuple[int, int]]]:
        """Return list of (chunk_text, (start_line, end_line))."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        lines = text.splitlines()
        if not lines:
            return []

        chunks: List[Tuple[str, Tuple[int, int]]] = []
        i = 0
        while i < len(lines):
            end = min(i + self.chunk_size, len(lines))
            chunk_text = "\n".join(lines[i:end])
            chunks.append((chunk_text, (i + 1, end)))
            i += self.chunk_size - self.overlap
        return chunks

    def chunk_project(self, project_dir: Path) -> List[Tuple[Path, str, Tuple[int, int]]]:
        """Chunk all source files in the project."""
        results: List[Tuple[Path, str, Tuple[int, int]]] = []
        extensions = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs",
            ".cs", ".rb", ".php", ".swift", ".kt", ".dart", ".vue", ".svelte",
        }
        for f in sorted(project_dir.rglob("*")):
            if f.suffix in extensions and "node_modules" not in str(f) and ".git" not in str(f):
                for chunk_text, line_range in self.chunk_file(f):
                    results.append((f, chunk_text, line_range))
        return results


# ---------------------------------------------------------------------------
# Document retrieval helpers
# ---------------------------------------------------------------------------

def _find_relevant_docs(
    code_chunk: str,
    project_dir: Path,
    check_type: str,
    fungus_search_fn: Any = None,
) -> List[str]:
    """Find documentation chunks relevant to a code chunk.

    Uses Fungus Memory RAG if available, else falls back to keyword matching.
    """
    # Try Fungus RAG first
    if fungus_search_fn is not None:
        try:
            results = fungus_search_fn(code_chunk, top_k=5)
            if results:
                return [r.get("content", r.get("text", str(r))) for r in results]
        except Exception as exc:
            logger.warning("fungus_search failed, falling back to keyword match", error=str(exc))

    # Keyword-based fallback
    doc_chunks: List[str] = []
    doc_dirs = {
        "api_consistency": ["api"],
        "data_model": ["data"],
        "business_logic": ["user_stories", "tasks"],
        "security": ["user_stories"],
        "performance": ["tech_stack"],
    }
    search_dirs = doc_dirs.get(check_type, ["tasks", "api", "data"])

    for d in search_dirs:
        doc_path = project_dir / d
        if not doc_path.exists():
            continue
        for f in sorted(doc_path.rglob("*")):
            if f.suffix in (".md", ".yaml", ".yml", ".json") and f.stat().st_size < 500_000:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    # Simple relevance: share any identifiers
                    code_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_chunk))
                    doc_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", content))
                    overlap = code_ids & doc_ids
                    if len(overlap) >= 3:
                        doc_chunks.append(content[:2000])
                except Exception:
                    continue

    return doc_chunks[:5]


# ---------------------------------------------------------------------------
# Scoring heuristics
# ---------------------------------------------------------------------------

def _score_consistency(
    code_chunk: str,
    doc_chunks: List[str],
    check_type: str,
) -> Tuple[float, str, str, str]:
    """Score code-doc consistency. Returns (score, severity, description, fix).

    score: 0.0 (bad) to 1.0 (good)
    """
    if not doc_chunks:
        return 0.5, "info", "No matching documentation found for this code section", ""

    combined_docs = "\n".join(doc_chunks)
    code_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_chunk))
    doc_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", combined_docs))

    if not code_ids:
        return 0.5, "info", "Code chunk has no identifiable symbols", ""

    overlap = code_ids & doc_ids
    overlap_ratio = len(overlap) / len(code_ids) if code_ids else 0

    # Check-type specific scoring
    if check_type == "api_consistency":
        # Look for HTTP methods and paths
        api_patterns = re.findall(r"(GET|POST|PUT|DELETE|PATCH)\s+[/\w{}]+", combined_docs, re.IGNORECASE)
        code_routes = re.findall(r"@(get|post|put|delete|patch|Get|Post|Put|Delete|Patch)|router\.(get|post|put|delete|patch)", code_chunk)
        if api_patterns and not code_routes:
            return 0.3, "high", "API endpoints documented but not found in code", "Implement missing API routes"
        if code_routes and not api_patterns:
            return 0.4, "medium", "Code defines routes not found in API documentation", "Update API documentation"

    elif check_type == "data_model":
        # Look for entity/schema definitions
        doc_entities = set(re.findall(r"(?:entity|model|table|schema)\s+(\w+)", combined_docs, re.IGNORECASE))
        code_classes = set(re.findall(r"class\s+(\w+)", code_chunk))
        if doc_entities and code_classes:
            missing = doc_entities - code_classes
            if missing:
                return 0.4, "high", f"Documented entities not in code: {', '.join(list(missing)[:5])}", "Add missing entity/model classes"

    elif check_type == "security":
        security_kw = {"auth", "token", "jwt", "session", "csrf", "cors", "encrypt", "password", "hash", "salt", "rbac", "role", "permission"}
        doc_has_security = bool(security_kw & {w.lower() for w in doc_ids})
        code_has_security = bool(security_kw & {w.lower() for w in code_ids})
        if doc_has_security and not code_has_security:
            return 0.3, "critical", "Security requirements in docs but no security implementation in code", "Add authentication/authorization"

    elif check_type == "performance":
        perf_kw = {"cache", "index", "pagination", "limit", "batch", "async", "queue", "pool", "buffer"}
        doc_has_perf = bool(perf_kw & {w.lower() for w in doc_ids})
        code_has_perf = bool(perf_kw & {w.lower() for w in code_ids})
        if doc_has_perf and not code_has_perf:
            return 0.4, "medium", "Performance patterns in docs but not implemented", "Add caching/pagination/async patterns"

    # General consistency score
    if overlap_ratio > 0.4:
        return min(0.5 + overlap_ratio, 1.0), "low", "Good documentation coverage", ""
    elif overlap_ratio > 0.2:
        return 0.4, "medium", f"Partial doc coverage ({overlap_ratio:.0%})", "Review code against documentation"
    else:
        return 0.3, "high", f"Low doc coverage ({overlap_ratio:.0%})", "Code may diverge from documentation"


# ---------------------------------------------------------------------------
# TreeQuest generate function factory
# ---------------------------------------------------------------------------

CHECK_TYPES = ["api_consistency", "data_model", "business_logic", "security", "performance"]


def create_verification_generate_fns(
    code_chunks: List[Tuple[Path, str, Tuple[int, int]]],
    project_dir: Path,
    fungus_search_fn: Any = None,
) -> Dict[str, Any]:
    """Create TreeQuest-compatible generate functions for verification.

    TreeQuest's step() expects a dict mapping action names to generate functions.
    Each generate function: (Optional[VerificationState]) -> Tuple[VerificationState, float]

    Returns: dict of {check_type_name: generate_fn}
    """
    def _make_generate_fn(check_type: str):
        chunk_idx = [0]

        def generate_fn(parent: Optional[VerificationState] = None) -> Tuple[VerificationState, float]:
            ci = chunk_idx[0] % len(code_chunks)
            chunk_idx[0] += 1

            file_path, chunk_text, line_range = code_chunks[ci]

            # Find relevant docs
            doc_chunks = _find_relevant_docs(chunk_text, project_dir, check_type, fungus_search_fn)

            # Score
            score, severity, description, fix = _score_consistency(chunk_text, doc_chunks, check_type)

            state = VerificationState(
                code_file=str(file_path),
                code_chunk=chunk_text[:500],
                doc_chunks=[d[:300] for d in doc_chunks[:3]],
                finding_type=check_type,
                severity=severity,
                confidence=score,
                description=description,
                suggested_fix=fix,
                line_range=line_range,
                parent_hash=parent.code_file if parent else "",
            )

            # Invert: lower consistency -> higher "interest" for MCTS
            search_score = 1.0 - score
            return state, search_score

        return generate_fn

    return {ct: _make_generate_fn(ct) for ct in CHECK_TYPES}


# ---------------------------------------------------------------------------
# TreeQuest Verification Runner
# ---------------------------------------------------------------------------

class TreeQuestVerificationRunner:
    """Orchestrates full verification of a project using AB-MCTS."""

    def __init__(
        self,
        project_dir: Path,
        max_steps: int = 200,
        top_k: int = 20,
        fungus_search_fn: Any = None,
    ):
        self.project_dir = project_dir
        self.max_steps = max_steps
        self.top_k = top_k
        self.fungus_search_fn = fungus_search_fn
        self.chunker = CodeChunker()

    def run(self) -> List[VerificationFinding]:
        """Run verification and return deduplicated findings."""
        chunks = self.chunker.chunk_project(self.project_dir)
        if not chunks:
            logger.warning("No code files found to verify", project=str(self.project_dir))
            return []

        logger.info(
            "Starting TreeQuest verification",
            chunks=len(chunks),
            max_steps=self.max_steps,
            treequest_available=TREEQUEST_AVAILABLE,
        )

        if TREEQUEST_AVAILABLE:
            return self._run_treequest(chunks)
        else:
            return self._run_linear(chunks)

    def _run_treequest(self, chunks: List[Tuple[Path, str, Tuple[int, int]]]) -> List[VerificationFinding]:
        """Run verification using AB-MCTS-A algorithm."""
        generate_fn = create_verification_generate_fns(
            chunks, self.project_dir, self.fungus_search_fn
        )

        algo = ABMCTSA()
        tree_state = algo.init_tree()

        for step_i in range(self.max_steps):
            tree_state = algo.step(tree_state, generate_fn, inplace=True)

        # Extract top-k findings
        pairs = algo.get_state_score_pairs(tree_state)
        pairs.sort(key=lambda x: x[1], reverse=True)
        top_pairs = pairs[: self.top_k]

        return self._pairs_to_findings(top_pairs)

    def _run_linear(self, chunks: List[Tuple[Path, str, Tuple[int, int]]]) -> List[VerificationFinding]:
        """Fallback linear verification (no TreeQuest)."""
        all_results: List[Tuple[VerificationState, float]] = []
        for file_path, chunk_text, line_range in chunks:
            for check_type in CHECK_TYPES:
                doc_chunks = _find_relevant_docs(
                    chunk_text, self.project_dir, check_type, self.fungus_search_fn
                )
                score, severity, description, fix = _score_consistency(
                    chunk_text, doc_chunks, check_type
                )
                state = VerificationState(
                    code_file=str(file_path),
                    code_chunk=chunk_text[:500],
                    doc_chunks=[d[:300] for d in doc_chunks[:3]],
                    finding_type=check_type,
                    severity=severity,
                    confidence=score,
                    description=description,
                    suggested_fix=fix,
                    line_range=line_range,
                )
                interest = 1.0 - score
                if interest > 0.4:
                    all_results.append((state, interest))

        all_results.sort(key=lambda x: x[1], reverse=True)
        return self._pairs_to_findings(all_results[: self.top_k])

    def _pairs_to_findings(
        self, pairs: List[Tuple[Any, float]]
    ) -> List[VerificationFinding]:
        """Convert state-score pairs to deduplicated findings."""
        seen: Set[str] = set()
        findings: List[VerificationFinding] = []

        for state, search_score in pairs:
            if isinstance(state, VerificationState):
                f = VerificationFinding(
                    file=state.code_file,
                    line_range=state.line_range,
                    severity=state.severity,
                    category=state.finding_type,
                    description=state.description,
                    suggested_fix=state.suggested_fix,
                    score=search_score,
                )
            else:
                continue

            if f.fingerprint not in seen and f.description:
                seen.add(f.fingerprint)
                findings.append(f)

        return findings


# ---------------------------------------------------------------------------
# Autonomous Agent wrapper
# ---------------------------------------------------------------------------

class TreeQuestVerificationAgent(AutonomousAgent):
    """Agent that verifies generated code against project documentation using tree search."""

    name = "TreeQuestVerificationAgent"

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.CODE_GENERATED,
            EventType.BUILD_SUCCEEDED,
            EventType.CODE_FIXED,
            EventType.VALIDATION_PASSED,
        ]

    def should_act(self, event: Event) -> bool:
        """Act when code generation or build succeeds."""
        return event.event_type in self.subscribed_events

    async def act(self, event: Event) -> None:
        """Run tree-search verification on the project."""
        shared = SharedState()
        project_dir = Path(shared.get("project_dir", self.working_dir))

        logger.info(
            "TreeQuestVerificationAgent triggered",
            event_type=event.event_type.value,
            project_dir=str(project_dir),
        )

        # Emit verification started
        bus = EventBus()
        await bus.publish(Event(
            type=EventType.TREEQUEST_VERIFICATION_STARTED,
            source=self.name,
            data={"agent": self.name, "project_dir": str(project_dir)},
        ))

        # Try to get Fungus search function
        fungus_fn = self._get_fungus_search_fn()

        runner = TreeQuestVerificationRunner(
            project_dir=project_dir,
            max_steps=200,
            top_k=20,
            fungus_search_fn=fungus_fn,
        )

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        findings = await loop.run_in_executor(None, runner.run)

        # Publish results
        critical = [f for f in findings if f.severity == "critical"]
        high = [f for f in findings if f.severity == "high"]

        logger.info(
            "Verification complete",
            total_findings=len(findings),
            critical=len(critical),
            high=len(high),
        )

        # Store findings in shared state
        shared.set(
            "treequest_findings",
            [f.to_dict() if hasattr(f, "to_dict") else {
                "file": f.file,
                "line_range": f.line_range,
                "severity": f.severity,
                "category": f.category,
                "description": f.description,
                "suggested_fix": f.suggested_fix,
                "score": f.score,
            } for f in findings],
        )

        # Emit events based on findings
        bus = EventBus()

        # Emit verification complete
        await bus.publish(Event(
            type=EventType.TREEQUEST_VERIFICATION_COMPLETE,
            source=self.name,
            data={
                "agent": self.name,
                "total_findings": len(findings),
                "critical": len(critical),
                "high": len(high),
            },
        ))

        if critical:
            # Emit critical finding events
            for finding in critical[:5]:
                await bus.publish(Event(
                    type=EventType.TREEQUEST_FINDING_CRITICAL,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "file": finding.file,
                        "line_range": finding.line_range,
                        "description": finding.description,
                        "category": finding.category,
                        "suggested_fix": finding.suggested_fix,
                    },
                ))

            # Also request code fix for critical items
            for finding in critical[:3]:
                await bus.publish(Event(
                    type=EventType.CODE_FIX_NEEDED,
                    source="treequest_verification",
                    data={
                        "file": finding.file,
                        "line_range": finding.line_range,
                        "reason": finding.description,
                        "fix_hint": finding.suggested_fix,
                        "severity": finding.severity,
                    },
                ))
        elif high:
            for finding in high[:5]:
                await bus.publish(Event(
                    type=EventType.TREEQUEST_FINDING_WARNING,
                    source=self.name,
                    data={
                        "agent": self.name,
                        "file": finding.file,
                        "description": finding.description,
                        "category": finding.category,
                    },
                ))
        else:
            await bus.publish(Event(
                type=EventType.TREEQUEST_NO_ISSUES,
                source=self.name,
                data={"agent": self.name, "total_checks": len(findings)},
            ))

    def _get_fungus_search_fn(self) -> Any:
        """Try to get the Fungus Memory search function."""
        try:
            from ..services.la_fungus_search import search as fungus_search
            return fungus_search
        except ImportError:
            pass
        try:
            shared = SharedState()
            return shared.get("fungus_search_fn", None)
        except Exception:
            return None
