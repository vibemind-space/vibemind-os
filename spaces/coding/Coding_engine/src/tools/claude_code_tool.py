"""
Claude Code Tool - Wraps Claude CLI as a callable tool for agents.

This tool allows agents to invoke Claude Code CLI for code generation.
Claude Code handles both generation AND file writing in one call.

Enhanced with:
- Parallel context loading (asyncio.gather)
- CLAUDE.md integration
- DocumentRegistry Reports loading
- Claude Agent SDK integration with CLI fallback
- Skill-aware prompt enrichment (progressive disclosure)
- OpenRouter HTTP API backend (no CLI needed)

Backend Selection:
- Primary: OpenRouter HTTP API (if configured in LLM config)
- Secondary: Claude Agent SDK (requires ANTHROPIC_API_KEY)
- Fallback: Claude CLI (subprocess, uses OAuth login if no API key)
"""
import asyncio
import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from src.skills.skill import Skill

from src.autogen.cli_wrapper import ClaudeCLI, ClaudeCLIPool, CLIResponse, GeneratedFile
from src.config import get_settings
from src.utils.token_estimator import TokenBudget, ContentDeduplicator, truncate_to_tokens
from src.utils.complexity_detector import detect_complexity, ComplexityResult

# Kilo CLI support (optional)
def _get_kilo_cli():
    """Lazy import KiloCLI to avoid circular dependencies."""
    try:
        from src.autogen.kilo_cli_wrapper import KiloCLI, KiloCLIPool, KiloCLIResponse
        return KiloCLI, KiloCLIPool, KiloCLIResponse
    except ImportError:
        return None, None, None


def _sanitize_box_drawing(text: str) -> str:
    """
    Replace UTF-8 box-drawing characters with ASCII equivalents.

    This prevents encoding issues on Windows consoles and in CLI output
    where UTF-8 box chars appear as mojibake (e.g., ÔöîÔöÇ instead of ┌─).

    Args:
        text: Input text potentially containing box-drawing characters

    Returns:
        Text with box-drawing characters replaced by ASCII
    """
    replacements = {
        # Corners
        '┌': '+', '┐': '+', '└': '+', '┘': '+',
        # T-junctions
        '├': '+', '┤': '+', '┬': '+', '┴': '+', '┼': '+',
        # Lines
        '─': '-', '│': '|',
        # Double lines
        '═': '=', '║': '|',
        # Arrows
        '▼': 'v', '▲': '^', '►': '>', '◄': '<',
        # Checkmarks
        '✓': '[x]', '✗': '[ ]',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


# Context profiles for selective loading based on agent type
CONTEXT_PROFILES = {
    "fixer": ["impl_plan", "debug_report", "fungus", "redis_stream"],  # Add redis_stream for real-time context
    "frontend": ["claude_md", "skills_claude_md", "component_tree", "supermemory", "fungus", "redis_stream"],
    "backend": ["claude_md", "skills_claude_md", "test_spec", "supermemory", "fungus", "redis_stream"],
    "testing": ["claude_md", "test_spec", "impl_plan", "fungus", "redis_stream"],
    "security": ["claude_md", "skills_claude_md", "impl_plan"],
    "devops": ["claude_md", "skills_claude_md"],
    "general": ["claude_md", "skills_claude_md", "debug_report", "impl_plan", "component_tree", "fungus", "redis_stream"],
}

# Try to import Claude Agent SDK tool
def _get_claude_agent_tool():
    """Lazy import ClaudeAgentTool to avoid circular dependencies."""
    try:
        from src.tools.claude_agent_tool import (
            ClaudeAgentTool,
            AgentResponse,
            ClaudeCodeNotFoundError,
            is_claude_not_found_error,
        )
        return ClaudeAgentTool, AgentResponse, ClaudeCodeNotFoundError, is_claude_not_found_error
    except ImportError:
        return None, None, None, None

# Lazy imports to avoid circular dependencies
def _get_document_registry():
    """Lazy import DocumentRegistry."""
    try:
        from src.registry.document_registry import DocumentRegistry
        from src.registry.document_types import DocumentType
        return DocumentRegistry, DocumentType
    except ImportError:
        return None, None

def _get_supermemory_tools():
    """Lazy import SupermemoryTools for parallel batch context."""
    try:
        from src.tools.supermemory_tools import SupermemoryTools
        return SupermemoryTools
    except ImportError:
        return None

# AsyncGates für robuste Parallelisierung
def _get_async_gates():
    """Lazy import AsyncGates."""
    try:
        from src.engine.async_gates import AsyncGates, TaskResult, GateOutput
        return AsyncGates, TaskResult, GateOutput
    except ImportError:
        return None, None, None

logger = structlog.get_logger()


class FungusContextProvider:
    """
    Provides semantic code search via Qdrant/la_fungus_search.

    Singleton pattern to avoid repeated initialization across tool calls.
    """

    _instance: Optional["FungusContextProvider"] = None

    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self._agent: Optional[Any] = None
        self._initialized = False
        self._init_failed = False
        self.logger = logger.bind(component="FungusContextProvider")

    @classmethod
    def get_instance(cls, working_dir: str) -> "FungusContextProvider":
        """Get or create singleton instance for the working directory."""
        if cls._instance is None or cls._instance.working_dir != working_dir:
            cls._instance = cls(working_dir)
        return cls._instance

    async def initialize(self) -> bool:
        """Initialize FungusContextAgent and index project files."""
        if self._initialized:
            return True
        if self._init_failed:
            return False

        try:
            from src.agents.fungus_context_agent import FungusContextAgent
            from src.mind.event_bus import EventBus
            from src.mind.shared_state import SharedState

            self._agent = FungusContextAgent(
                name="FungusProvider",
                event_bus=EventBus(),
                shared_state=SharedState(),  # Create new instance
                working_dir=self.working_dir,
            )

            # Index project files
            indexed = await self._agent.index_project()
            self.logger.info("fungus_provider_initialized", indexed_files=indexed)
            self._initialized = True
            return True

        except Exception as e:
            self.logger.warning("fungus_provider_init_failed", error=str(e))
            self._init_failed = True
            return False

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search for relevant code context."""
        if not self._initialized or not self._agent:
            return []

        try:
            return await self._agent._search_context(query, top_k=top_k)
        except Exception as e:
            self.logger.debug("fungus_search_failed", error=str(e))
            return []


@dataclass
class CodeGenerationResult:
    """Result from code generation."""
    success: bool
    files: list[GeneratedFile] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "files": [{"path": f.path, "language": f.language, "lines": len(f.content.splitlines())} for f in self.files],
            "output": self.output[:500] if self.output else "",
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


class ClaudeCodeTool:
    """
    Tool that wraps Claude Code CLI for use by agents.

    This is the primary tool for code generation. Claude Code:
    - Generates code based on prompts
    - Writes files directly to the filesystem
    - Understands project context
    - Loads CLAUDE.md and Reports automatically for context
    - Loads related patterns from Supermemory for parallel batch context
    
    FIX-30: Now uses AsyncGates for robust parallel execution
    """

    # Class-level semaphore - reduced to 2 to avoid API rate limits
    _default_max_concurrent = 10
    _cli_semaphore: Optional[asyncio.Semaphore] = None
    _async_gates: Optional[Any] = None
    _supermemory: Optional[Any] = None
    _fungus: Optional[FungusContextProvider] = None

    # Async Context Prefetch (Continuous Feedback Loop)
    # These enable instant context retrieval by caching context in background
    _context_cache: dict[str, str] = {}  # Cached context per source
    _context_prefetch_task: Optional[asyncio.Task] = None
    _context_prefetch_query: Optional[str] = None
    _context_cache_timestamp: float = 0.0
    _context_cache_ttl: float = 5.0  # Refresh every 5 seconds

    # Fallback tracking (class-level for statistics)
    _fallback_count: int = 0
    _fallback_reason: Optional[str] = None

    # Tool definition for Agent SDK
    TOOL_DEFINITION = {
        "name": "generate_code",
        "description": """Generate code using Claude Code CLI.
This tool generates code files based on the given prompt and requirements.
Claude Code will create the files directly in the working directory.
Use this for implementing features, fixing bugs, or creating new components.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The code generation prompt describing what to implement"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context like interface contracts, shared types, etc."
                },
                "agent_type": {
                    "type": "string",
                    "enum": ["frontend", "backend", "testing", "security", "devops", "general", "fixer"],
                    "description": "The type of agent making the request (for specialized prompts)"
                }
            },
            "required": ["prompt"]
        }
    }

    def __init__(
        self,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        max_concurrent: int = 10,
        load_context: bool = True,  # Enable/disable auto context loading
        job_id: Optional[int] = None,  # NEW: Job ID for Supermemory container tag
        domain: Optional[str] = None,  # NEW: Domain for pattern filtering
        use_sdk: Optional[bool] = None,  # None = auto-detect, True = force SDK, False = force CLI
        skill: Optional["Skill"] = None,  # Skill for progressive disclosure prompt enrichment
        minimal_context: bool = False,  # Skip engine/skills docs for validation fixes
        skill_tier: Optional[str] = None,  # Override tier: "minimal", "standard", "full"
    ):
        self.working_dir = working_dir
        self.timeout = timeout if timeout is not None else get_settings().cli_timeout
        self.max_concurrent = max_concurrent
        self.load_context = load_context
        self.minimal_context = minimal_context  # Skip engine/skills docs for validation fixes
        self.job_id = job_id  # NEW
        self.domain = domain  # NEW
        self.skill = skill  # Skill for progressive disclosure
        self.skill_tier = skill_tier  # Tier override for skill loading
        self._skill_cache: dict[str, "Skill"] = {}  # Cache skills by agent_type
        self._doc_registry = None
        self.logger = logger.bind(tool="claude_code")

        # Backend selection: Check config for llm_backend (kilo/claude/openrouter)
        settings = get_settings()
        self._using_sdk = False
        self._sdk_backend = None
        self._using_kilo = False
        self._using_openrouter = False
        self._openrouter_model = None
        self._openrouter_max_tokens = 16384
        self._instance_fallback_reason: Optional[str] = None

        # Check if LLM config has OpenRouter models configured
        self._detect_openrouter_config()

        # Check for Kilo backend preference from config
        if settings.llm_backend == "kilo":
            KiloCLI, KiloCLIPool, _ = _get_kilo_cli()
            if KiloCLI is not None:
                try:
                    self.cli = KiloCLI(working_dir=working_dir, timeout=self.timeout)
                    self.cli_pool = KiloCLIPool(max_concurrent=max_concurrent, working_dir=working_dir, timeout=self.timeout)
                    self._using_kilo = True
                    self.logger.info(
                        "backend_selected",
                        backend="kilo",
                        reason="llm_backend=kilo in config",
                    )
                except Exception as e:
                    self.logger.warning(
                        "kilo_init_failed_fallback_to_claude",
                        error=str(e),
                    )
                    self._using_kilo = False

        # If not using Kilo, use Claude (SDK or CLI)
        if not self._using_kilo:
            ClaudeAgentTool, _, _, _ = _get_claude_agent_tool()

            # Check for environment variable to force CLI mode
            # Set CLAUDE_FORCE_CLI=true to bypass SDK and use CLI directly
            force_cli = os.getenv("CLAUDE_FORCE_CLI", "").lower() in ("true", "1", "yes")
            if force_cli:
                use_sdk = False
                self.logger.info("backend_forced", backend="cli", reason="CLAUDE_FORCE_CLI=true")

            # Auto-detect: Use SDK if API key is available
            if use_sdk is None:
                use_sdk = ClaudeAgentTool is not None and ClaudeAgentTool.is_available()

            if use_sdk and ClaudeAgentTool is not None:
                try:
                    self._sdk_backend = ClaudeAgentTool(
                        working_dir=working_dir or ".",
                        timeout=self.timeout,
                        max_tokens=4096,
                    )
                    self._using_sdk = True
                    self.logger.info(
                        "backend_selected",
                        backend="sdk",
                        reason="API key available",
                    )
                except Exception as e:
                    self.logger.warning(
                        "sdk_init_failed_fallback_to_cli",
                        error=str(e),
                    )
                    self._using_sdk = False

            if not self._using_sdk:
                self.logger.info(
                    "backend_selected",
                    backend="cli",
                    reason="No API key or SDK unavailable, using CLI with OAuth",
                )

            # Claude CLI backend (always initialized for fallback and batch operations)
            self.cli = ClaudeCLI(working_dir=working_dir, timeout=self.timeout)
            self.cli_pool = ClaudeCLIPool(max_concurrent=max_concurrent, working_dir=working_dir)
        
        # Dynamische Semaphore basierend auf max_concurrent
        if ClaudeCodeTool._cli_semaphore is None or ClaudeCodeTool._default_max_concurrent != max_concurrent:
            ClaudeCodeTool._cli_semaphore = asyncio.Semaphore(max_concurrent)
            ClaudeCodeTool._default_max_concurrent = max_concurrent
            self.logger.info("semaphore_initialized", max_concurrent=max_concurrent)
        
        # AsyncGates für robuste Parallelisierung
        AsyncGates, _, _ = _get_async_gates()
        if AsyncGates:
            ClaudeCodeTool._async_gates = AsyncGates(
                max_concurrent=max_concurrent,
                default_timeout=self.timeout,
            )
        
        # Initialize Supermemory client
        SupermemoryTools = _get_supermemory_tools()
        if SupermemoryTools and ClaudeCodeTool._supermemory is None:
            ClaudeCodeTool._supermemory = SupermemoryTools()
            if ClaudeCodeTool._supermemory.client:
                self.logger.info("supermemory_initialized_for_context")
        
        # Initialize DocumentRegistry if available and context loading enabled
        if load_context and working_dir:
            try:
                DocumentRegistry, _ = _get_document_registry()
                if DocumentRegistry:
                    self._doc_registry = DocumentRegistry(working_dir)
            except Exception as e:
                self.logger.debug("doc_registry_init_failed", error=str(e))

    async def _load_claude_md(
        self,
        budget: TokenBudget = None,
        tier: str = "full",
        project_only: bool = False,
    ) -> str:
        """
        Load CLAUDE.md from engine root AND/OR working directory with token budgeting.

        Priority:
        1. Engine CLAUDE.md (architecture, event types, agent guidelines) - SKIP if project_only
        2. Output project CLAUDE.md (if exists) - always load if exists

        When project_only=True, skips Engine CLAUDE.md and only loads the
        output project's CLAUDE.md. This is used when a skill is injected,
        as the skill already contains the needed context.

        Uses TokenBudget for intelligent truncation and ContentDeduplicator
        to avoid redundant sections between engine and project CLAUDE.md.

        Tier-based loading (v2.1):
        - minimal: 500 tokens (just commands + critical sections)
        - standard: 1000 tokens (+ agent overview)
        - full: 2000 tokens (complete CLAUDE.md)

        Args:
            budget: Optional TokenBudget for managing token allocation
            tier: Context tier ("minimal", "standard", "full")
            project_only: If True, skip Engine CLAUDE.md and only load project's

        Returns:
            Combined contents of CLAUDE.md files or empty string if not found
        """
        parts = []
        deduplicator = ContentDeduplicator()

        # Use provided budget or create default
        if budget is None:
            budget = TokenBudget()

        try:
            # 1. Load ENGINE CLAUDE.md (main architecture docs)
            # Skip if project_only=True (skill provides context)
            if not project_only:
                import os
                engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                engine_claude_md = Path(engine_root) / "CLAUDE.md"

                if engine_claude_md.exists():
                    content = engine_claude_md.read_text(encoding='utf-8', errors='replace')

                    # Sanitize box-drawing characters to prevent encoding issues
                    content = _sanitize_box_drawing(content)

                    # Tier-based token allocation for engine CLAUDE.md
                    tier_limits = {
                        "minimal": 500,   # Just commands + critical sections
                        "standard": 1000, # + Agent overview
                        "full": 2000,     # Complete CLAUDE.md
                    }
                    base_limit = tier_limits.get(tier, 2000)
                    max_tokens = budget.allocate("engine_claude_md", base_limit)
                    content = truncate_to_tokens(content, max_tokens, preserve_sections=True)
                    budget.used["engine_claude_md"] = budget.estimator.estimate_tokens(content)

                    # Deduplicate content
                    content = deduplicator.deduplicate(content)

                    parts.append("### Engine Architecture (from Coding_engine/CLAUDE.md)\n\n")
                    parts.append(content)
                    self.logger.debug(
                        "engine_claude_md_loaded",
                        path=str(engine_claude_md),
                        tokens=budget.used.get("engine_claude_md", 0),
                    )
            else:
                self.logger.debug("engine_claude_md_skipped", reason="project_only=True")

            # 2. Load OUTPUT project CLAUDE.md (if exists)
            if self.working_dir:
                project_claude_md = Path(self.working_dir) / "CLAUDE.md"
                if project_claude_md.exists():
                    content = project_claude_md.read_text(encoding='utf-8', errors='replace')

                    # Sanitize box-drawing characters
                    content = _sanitize_box_drawing(content)

                    # Tier-based token allocation for project CLAUDE.md
                    project_tier_limits = {
                        "minimal": 300,   # Just key sections
                        "standard": 700,  # + More details
                        "full": 1500,     # Complete project CLAUDE.md
                    }
                    project_base = project_tier_limits.get(tier, 1500)
                    max_tokens = budget.allocate("project_claude_md", project_base)
                    content = truncate_to_tokens(content, max_tokens, preserve_sections=True)
                    budget.used["project_claude_md"] = budget.estimator.estimate_tokens(content)

                    # Deduplicate - removes sections already seen in engine CLAUDE.md
                    content = deduplicator.deduplicate(content)

                    if content.strip():  # Only add if non-empty after deduplication
                        parts.append("\n\n### Project Context (from output/CLAUDE.md)\n\n")
                        parts.append(content)
                        self.logger.debug(
                            "project_claude_md_loaded",
                            path=str(project_claude_md),
                            tokens=budget.used.get("project_claude_md", 0),
                        )

        except Exception as e:
            self.logger.debug("claude_md_load_failed", error=str(e))

        return "".join(parts) if parts else ""

    async def _load_skills_claude_md(self, budget: TokenBudget = None) -> str:
        """
        Load CLAUDE.md from the Coding Engine's .claude/skills/ directory.

        This provides agents with skill discovery information.

        Args:
            budget: Optional TokenBudget for managing token allocation

        Returns:
            Contents of skills CLAUDE.md or empty string if not found
        """
        try:
            # Find the engine root (where .claude/skills/ is located)
            import os
            engine_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            skills_claude_md = Path(engine_root) / ".claude" / "skills" / "CLAUDE.md"

            if skills_claude_md.exists():
                content = skills_claude_md.read_text(encoding='utf-8', errors='replace')

                # Sanitize box-drawing characters
                content = _sanitize_box_drawing(content)

                # Token-aware truncation (1500 tokens for skills CLAUDE.md)
                if budget:
                    max_tokens = budget.allocate("skills_claude_md", 1500)
                    content = truncate_to_tokens(content, max_tokens, preserve_sections=True)
                    budget.used["skills_claude_md"] = budget.estimator.estimate_tokens(content)
                else:
                    content = truncate_to_tokens(content, 1500, preserve_sections=True)

                self.logger.debug("skills_claude_md_loaded", path=str(skills_claude_md))
                return content
        except Exception as e:
            self.logger.debug("skills_claude_md_load_failed", error=str(e))

        return ""

    async def _load_latest_debug_report(self) -> str:
        """
        Load latest DebugReport from DocumentRegistry.
        
        Returns:
            Summary of latest debug report or empty string
        """
        if not self._doc_registry:
            return ""
        
        try:
            _, DocumentType = _get_document_registry()
            if not DocumentType:
                return ""
            
            doc = await self._doc_registry.get_latest_by_type(DocumentType.DEBUG_REPORT)
            if doc:
                # Extract key info
                summary_parts = []
                if hasattr(doc, 'console_errors') and doc.console_errors:
                    summary_parts.append(f"Console errors: {len(doc.console_errors)}")
                    for err in doc.console_errors[:3]:
                        summary_parts.append(f"  - {err[:100]}")
                if hasattr(doc, 'root_cause_hypothesis') and doc.root_cause_hypothesis:
                    summary_parts.append(f"Root cause: {doc.root_cause_hypothesis[:200]}")
                if hasattr(doc, 'suggested_fixes') and doc.suggested_fixes:
                    summary_parts.append(f"Suggested fixes: {len(doc.suggested_fixes)}")
                    for fix in doc.suggested_fixes[:2]:
                        summary_parts.append(f"  - {fix.description[:100]}")
                
                if summary_parts:
                    return "\n".join(summary_parts)
        except Exception as e:
            self.logger.debug("debug_report_load_failed", error=str(e))
        
        return ""

    async def _load_implementation_plan(self) -> str:
        """
        Load latest ImplementationPlan from DocumentRegistry.
        
        Returns:
            Summary of implementation plan or empty string
        """
        if not self._doc_registry:
            return ""
        
        try:
            _, DocumentType = _get_document_registry()
            if not DocumentType:
                return ""
            
            doc = await self._doc_registry.get_latest_by_type(DocumentType.IMPLEMENTATION_PLAN)
            if doc:
                summary_parts = []
                if hasattr(doc, 'summary') and doc.summary:
                    summary_parts.append(doc.summary[:300])
                if hasattr(doc, 'fixes_planned') and doc.fixes_planned:
                    summary_parts.append(f"Planned tasks: {len(doc.fixes_planned)}")
                if hasattr(doc, 'test_focus_areas') and doc.test_focus_areas:
                    summary_parts.append(f"Test focus: {', '.join(doc.test_focus_areas[:3])}")
                
                if summary_parts:
                    return "\n".join(summary_parts)
        except Exception as e:
            self.logger.debug("impl_plan_load_failed", error=str(e))
        
        return ""

    async def _load_test_spec(self) -> str:
        """
        Load latest TestSpec from DocumentRegistry.
        
        Returns:
            Summary of test spec or empty string
        """
        if not self._doc_registry:
            return ""
        
        try:
            _, DocumentType = _get_document_registry()
            if not DocumentType:
                return ""
            
            doc = await self._doc_registry.get_latest_by_type(DocumentType.TEST_SPEC)
            if doc:
                summary_parts = []
                if hasattr(doc, 'results') and doc.results:
                    r = doc.results
                    summary_parts.append(f"Tests: {r.total} total, {r.passed} passed, {r.failed} failed")
                    if r.failures:
                        summary_parts.append("Recent failures:")
                        for f in r.failures[:2]:
                            summary_parts.append(f"  - {f.get('type', 'error')}: {str(f.get('samples', []))[:100]}")
                if hasattr(doc, 'coverage_targets') and doc.coverage_targets:
                    summary_parts.append(f"Coverage: {', '.join(doc.coverage_targets[:3])}")
                
                if summary_parts:
                    return "\n".join(summary_parts)
        except Exception as e:
            self.logger.debug("test_spec_load_failed", error=str(e))
        
        return ""

    async def _load_supermemory_context(self, query: str) -> str:
        """
        Load related patterns from Supermemory for context.
        
        Uses v4/search for speed-optimized queries.
        
        Args:
            query: Search query (usually from the prompt)
            
        Returns:
            Formatted context string with related patterns
        """
        if not ClaudeCodeTool._supermemory or not ClaudeCodeTool._supermemory.client:
            return ""
        
        try:
            # Build search with job/domain filtering
            result = await ClaudeCodeTool._supermemory.search_related_patterns(
                query=query[:500],  # Truncate for API
                domain=self.domain or "general",
                job_id=self.job_id,
                limit=3,
            )
            
            if not result.found or not result.results:
                return ""
            
            # Format results as context
            parts = ["### Related Patterns from Memory"]
            for idx, item in enumerate(result.results[:3], 1):
                title = item.get("title", f"Pattern {idx}")
                memory = item.get("memory", "")[:1500]  # Truncate long patterns
                similarity = item.get("similarity", 0)
                parts.append(f"\n**{title}** (similarity: {similarity:.2f})")
                parts.append(f"```\n{memory}\n```")
            
            self.logger.info(
                "supermemory_context_loaded",
                patterns_found=len(result.results),
                timing_ms=result.timing_ms,
            )
            
            return "\n".join(parts)
            
        except Exception as e:
            self.logger.debug("supermemory_context_failed", error=str(e))
            return ""

    async def _load_fungus_context(self, query: str) -> str:
        """
        Load relevant code context from Fungus/Qdrant.

        Uses semantic search via la_fungus_search to find code snippets
        relevant to the task. Replaces Supermemory when API is unavailable.

        Args:
            query: Search query (usually from the prompt)

        Returns:
            Formatted context string with relevant code snippets
        """
        # Allow disabling Fungus context via env var (avoids SentenceTransformer GPU segfaults)
        if os.environ.get("DISABLE_FUNGUS", "").lower() in ("1", "true", "yes"):
            return ""

        if not ClaudeCodeTool._fungus:
            if self.working_dir:
                ClaudeCodeTool._fungus = FungusContextProvider.get_instance(
                    str(self.working_dir)
                )
                await ClaudeCodeTool._fungus.initialize()

        if not ClaudeCodeTool._fungus:
            return ""

        try:
            results = await ClaudeCodeTool._fungus.search(query[:500], top_k=5)

            if not results:
                return ""

            parts = ["### Relevant Code from Project"]
            for idx, item in enumerate(results[:5], 1):
                file_path = item.get("file_path", f"snippet_{idx}")
                content = item.get("content", "")[:1500]
                score = item.get("score", 0)
                start_line = item.get("start_line", 0)
                end_line = item.get("end_line", 0)

                parts.append(f"\n**{file_path}:{start_line}-{end_line}** (relevance: {score:.2f})")
                parts.append(f"```\n{content}\n```")

            self.logger.info(
                "fungus_context_loaded",
                snippets_found=len(results),
            )

            return "\n".join(parts)

        except Exception as e:
            self.logger.debug("fungus_context_failed", error=str(e))
            return ""

    async def _load_redis_stream_context(self) -> str:
        """
        Load real-time context from Redis Fungus streams.

        Consumes context published by FungusWorker running in parallel:
        - fungus:context:{job_id} - Search results + context updates
        - fungus:steering:{job_id} - Architect steering decisions

        Returns:
            Formatted context string for Claude prompt enrichment
        """
        if not self.job_id:
            self.logger.warning(
                "redis_stream_no_job_id",
                msg="job_id not set - Redis stream context unavailable. Pass job_id to ClaudeCodeTool."
            )
            return ""

        try:
            from src.tools.redis_context_loader import RedisContextLoader
            import os

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            loader = RedisContextLoader(redis_url)

            # Load context from fungus worker stream
            context = await loader.load_context(
                job_id=str(self.job_id),
                max_entries=5,
                include_steering=True,
            )

            if context:
                self.logger.info(
                    "redis_stream_context_loaded",
                    job_id=self.job_id,
                    chars=len(context),
                )

            # Also load verification status if available
            verification = await loader.format_verification_status(str(self.job_id))
            if verification:
                context = f"{context}\n\n{verification}" if context else verification

            await loader.close()
            return context

        except ImportError:
            self.logger.debug("redis_context_loader_not_available")
            return ""
        except Exception as e:
            self.logger.debug("redis_stream_context_failed", error=str(e))
            return ""

    async def _load_component_tree(self) -> str:
        """
        Load component tree for React/Vue/Svelte projects.

        Provides hierarchical view of component structure with file paths,
        useful for understanding UI organization during code fixes.

        Returns:
            Formatted component tree or empty string if not applicable
        """
        if not self.working_dir:
            return ""

        try:
            from src.tools.component_tree_tool import ComponentTreeTool

            tool = ComponentTreeTool(str(self.working_dir))
            if not tool.is_applicable():
                return ""

            tree = await tool.generate_tree()
            context = tool.format_as_context(tree)

            if context:
                self.logger.debug(
                    "component_tree_loaded",
                    framework=tree.framework,
                    components=tree.total_components,
                )

            return context

        except ImportError:
            self.logger.debug("component_tree_import_failed")
            return ""
        except Exception as e:
            self.logger.debug("component_tree_load_failed", error=str(e))
            return ""

    async def _load_all_context_parallel(
        self,
        query: Optional[str] = None,
        agent_type: str = "general",
    ) -> dict[str, str]:
        """
        Load context sources selectively based on agent type using asyncio.gather.

        Uses CONTEXT_PROFILES to determine which context sources are relevant
        for each agent type, reducing token usage by ~40%.

        Args:
            query: Optional query for Supermemory semantic search
            agent_type: Type of agent (frontend, backend, fixer, etc.)

        Returns:
            Dict with context from each source
        """
        # Create shared token budget for this context loading session
        budget = TokenBudget()

        # Minimal context mode: skip heavy context for validation fixes
        if self.minimal_context:
            impl_plan = await self._load_implementation_plan()
            self.logger.debug("minimal_context_mode", impl_plan_loaded=bool(impl_plan))
            return {
                "claude_md": "",
                "skills_claude_md": "",
                "debug_report": "",
                "impl_plan": impl_plan,
                "test_spec": "",
                "component_tree": "",
                "supermemory": "",
                "fungus": "",
                "redis_stream": "",
            }

        # Get context profile for this agent type
        profile = CONTEXT_PROFILES.get(agent_type, CONTEXT_PROFILES["general"])
        self.logger.debug(
            "selective_context_loading",
            agent_type=agent_type,
            profile=profile,
        )

        # Helper for empty placeholder
        async def _empty_placeholder() -> str:
            return ""

        # Determine context tier from skill_tier or default to "full"
        context_tier = self.skill_tier or "full"

        # Check if a skill will be loaded for this agent type
        # If yes, use project_only=True to skip Engine CLAUDE.md
        skill_will_load = self._get_skill_for_agent(agent_type) is not None
        project_only = skill_will_load  # Skip engine CLAUDE.md when skill provides context

        self.logger.debug(
            "context_tier_selected",
            tier=context_tier,
            agent_type=agent_type,
            source="skill_tier" if self.skill_tier else "default",
            project_only=project_only,
            skill_will_load=skill_will_load,
        )

        # Build tasks list based on profile (selective loading)
        # Use project_only=True when skill will be loaded (skill provides context)
        context_loaders = {
            "claude_md": lambda: self._load_claude_md(budget, tier=context_tier, project_only=project_only),
            "skills_claude_md": lambda: self._load_skills_claude_md(budget),
            "debug_report": self._load_latest_debug_report,
            "impl_plan": self._load_implementation_plan,
            "test_spec": self._load_test_spec,
            "component_tree": self._load_component_tree,
            "supermemory": lambda: (
                self._load_supermemory_context(query)
                if query and ClaudeCodeTool._supermemory and ClaudeCodeTool._supermemory.client
                else _empty_placeholder()
            ),
            "fungus": lambda: (
                self._load_fungus_context(query)
                if query
                else _empty_placeholder()
            ),
            "redis_stream": lambda: (
                self._load_redis_stream_context()
                if self.job_id
                else _empty_placeholder()
            ),
        }

        # Only load context sources in the profile
        tasks = []
        task_keys = []
        for key in ["claude_md", "skills_claude_md", "debug_report", "impl_plan", "test_spec", "component_tree", "supermemory", "fungus", "redis_stream"]:
            if key in profile:
                tasks.append(context_loaders[key]())
                task_keys.append(key)

        # Parallel load selected context sources
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build context dict with empty strings for unloaded sources
        context = {
            "claude_md": "",
            "skills_claude_md": "",
            "debug_report": "",
            "impl_plan": "",
            "test_spec": "",
            "component_tree": "",
            "supermemory": "",
            "fungus": "",
            "redis_stream": "",
        }

        # Populate loaded results
        for i, key in enumerate(task_keys):
            if isinstance(results[i], str):
                context[key] = results[i]

        # Log what was loaded with token budget info
        loaded = [k for k, v in context.items() if v]
        if loaded:
            self.logger.info(
                "context_loaded_parallel",
                sources=loaded,
                agent_type=agent_type,
                total_tokens=budget.total_used,
                remaining_budget=budget.remaining,
            )

        return context

    # =========================================================================
    # Async Context Prefetch (Continuous Feedback Loop - Fastest Path)
    # =========================================================================

    @classmethod
    async def start_context_prefetch(
        cls,
        query: str,
        agent_type: str = "general",
        refresh_interval: float = 5.0,
    ) -> None:
        """
        Start background prefetching of context for instant retrieval.

        This enables the fastest possible context loading by caching context
        in the background and refreshing it periodically.

        Args:
            query: Query for semantic search (Supermemory, Fungus)
            agent_type: Agent type for context profile selection
            refresh_interval: How often to refresh cache (seconds)
        """
        # Stop any existing prefetch task
        if cls._context_prefetch_task and not cls._context_prefetch_task.done():
            cls._context_prefetch_task.cancel()
            try:
                await cls._context_prefetch_task
            except asyncio.CancelledError:
                pass

        cls._context_prefetch_query = query
        cls._context_cache_ttl = refresh_interval

        # Start new prefetch task
        cls._context_prefetch_task = asyncio.create_task(
            cls._prefetch_context_loop(query, agent_type, refresh_interval)
        )

        logger.info(
            "context_prefetch_started",
            query=query[:50] if query else None,
            agent_type=agent_type,
            refresh_interval=refresh_interval,
        )

    @classmethod
    async def stop_context_prefetch(cls) -> None:
        """Stop the background context prefetch task."""
        if cls._context_prefetch_task and not cls._context_prefetch_task.done():
            cls._context_prefetch_task.cancel()
            try:
                await cls._context_prefetch_task
            except asyncio.CancelledError:
                pass
            cls._context_prefetch_task = None

        logger.info("context_prefetch_stopped")

    @classmethod
    async def _prefetch_context_loop(
        cls,
        query: str,
        agent_type: str,
        refresh_interval: float,
    ) -> None:
        """
        Background loop that continuously prefetches context.

        Runs until cancelled, refreshing the cache every refresh_interval seconds.
        """
        import time

        # Create a minimal instance for context loading
        # (no working_dir needed for the prefetch)
        instance = cls.__new__(cls)
        instance.working_dir = None
        instance.load_context = True
        instance.minimal_context = False
        instance.job_id = None
        instance.domain = None
        instance.skill = None
        instance.skill_tier = None
        instance._skill_cache = {}
        instance.logger = logger.bind(tool="claude_code_prefetch")

        while True:
            try:
                start = time.time()

                # Load all context in parallel
                context = await instance._load_all_context_parallel(
                    query=query,
                    agent_type=agent_type,
                )

                # Update cache
                cls._context_cache = context
                cls._context_cache_timestamp = time.time()

                elapsed = time.time() - start
                logger.debug(
                    "context_cache_refreshed",
                    sources=[k for k, v in context.items() if v],
                    elapsed_ms=int(elapsed * 1000),
                )

                # Wait for next refresh
                await asyncio.sleep(refresh_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("context_prefetch_error", error=str(e))
                await asyncio.sleep(1)  # Brief pause on error

    @classmethod
    def get_cached_context(cls) -> dict[str, str]:
        """
        Get the cached context (instantly, no async).

        Returns empty dict if cache is stale or not available.
        Use is_cache_valid() to check freshness before using.
        """
        if cls._context_cache and cls.is_cache_valid():
            return cls._context_cache.copy()
        return {}

    @classmethod
    def is_cache_valid(cls) -> bool:
        """Check if the context cache is fresh and valid."""
        import time
        if not cls._context_cache:
            return False
        age = time.time() - cls._context_cache_timestamp
        return age < (cls._context_cache_ttl * 2)  # Allow 2x TTL before expiry

    async def execute(
        self,
        prompt: str,
        context: Optional[str] = None,
        agent_type: str = "general",
        context_files: Optional[list[str]] = None,
        claude_agent: Optional[str] = None,
        max_turns: Optional[int] = None,
    ) -> CodeGenerationResult:
        """
        Execute code generation via Claude Agent SDK or CLI (fallback).

        Args:
            prompt: The code generation prompt
            context: Additional context (contracts, types, etc.)
            agent_type: Type of agent for specialized prompts
            context_files: Optional list of file paths to include as context
            claude_agent: Optional .claude/agents/ agent name for --agent flag
            max_turns: Optional max agentic turns for --max-turns cost control

        Returns:
            CodeGenerationResult with generated files
        """
        # Read context files and add to context
        if context_files:
            file_context = self._read_context_files(context_files)
            if context:
                context = f"{context}\n\n{file_context}"
            else:
                context = file_context

        # Load additional context from Reports, CLAUDE.md, and Supermemory (parallel)
        # Uses agent_type for selective context loading (token optimization)
        auto_context = {}
        if self.load_context:
            # Use prompt as query for Supermemory semantic search
            auto_context = await self._load_all_context_parallel(
                query=prompt[:300],
                agent_type=agent_type,
            )

        # Build full prompt with all context
        full_prompt = await self._build_enriched_prompt(prompt, context, agent_type, auto_context)

        # Enhanced logging for visibility
        # Longer preview (500 chars) for better debugging visibility
        prompt_preview = prompt[:500].replace("\n", " ") + "..." if len(prompt) > 500 else prompt.replace("\n", " ")
        active_skill = self._get_skill_for_agent(agent_type)
        self.logger.info(
            "CLAUDE_CLI_START",
            agent_type=agent_type,
            prompt_preview=prompt_preview,
            prompt_length=len(full_prompt),
            working_dir=str(self.working_dir),
            has_claude_md=bool(auto_context.get("claude_md")),
            has_skills_md=bool(auto_context.get("skills_claude_md")),
            has_component_tree=bool(auto_context.get("component_tree")),
            has_reports=bool(auto_context.get("debug_report") or auto_context.get("impl_plan")),
            has_skill=active_skill is not None,
            skill_name=active_skill.name if active_skill else None,
            backend=self.backend_type,
        )

        # Debug log with full prompt for detailed troubleshooting
        self.logger.debug(
            "CLAUDE_CLI_FULL_PROMPT",
            agent_type=agent_type,
            full_prompt=full_prompt,
        )

        # Execute via Kilo (primary if configured) > OpenRouter > SDK > CLI (fallback)
        import time
        start_time = time.time()
        if self._using_kilo:
            # Kilo CLI: uses --auto (no root restriction like Claude CLI)
            result = await self._execute_via_cli(
                full_prompt,
                agent_type=agent_type,
                claude_agent=claude_agent,
                max_turns=max_turns,
            )
        elif self._using_openrouter:
            result = await self._execute_via_openrouter(full_prompt, agent_type=agent_type)
        elif self._using_sdk and self._sdk_backend:
            result = await self._execute_via_sdk(full_prompt, context_files)
        else:
            result = await self._execute_via_cli(
                full_prompt,
                agent_type=agent_type,
                claude_agent=claude_agent,
                max_turns=max_turns,
            )
        actual_duration_ms = int((time.time() - start_time) * 1000)

        # Enhanced completion logging
        files_info = [f.path for f in result.files[:5]] if result.files else []
        if len(result.files) > 5:
            files_info.append(f"... and {len(result.files) - 5} more")

        self.logger.info(
            "CLAUDE_CLI_COMPLETE",
            success=result.success,
            files_generated=len(result.files),
            files=files_info,
            duration_ms=actual_duration_ms,
            backend=self.backend_type,
            error=result.error[:100] if result.error else None,
        )

        return result

    async def _execute_via_sdk(
        self,
        prompt: str,
        context_files: Optional[list[str]] = None,
    ) -> CodeGenerationResult:
        """
        Execute code generation via Claude Agent SDK.

        Args:
            prompt: The enriched prompt
            context_files: Optional context files

        Returns:
            CodeGenerationResult
        """
        _, _, ClaudeCodeNotFoundError, is_claude_not_found_error = _get_claude_agent_tool()

        try:
            response = await self._sdk_backend.execute(
                prompt=prompt,
                tools=self._sdk_backend.DEFAULT_TOOLS,
                context_files=context_files,
                timeout=self.timeout,
            )

            # Convert AgentResponse to CodeGenerationResult
            files = [
                GeneratedFile(path=f.path, content=f.content, language=f.language)
                for f in response.files
            ]

            return CodeGenerationResult(
                success=response.success,
                files=files,
                output=response.output,
                error=response.error,
                execution_time_ms=response.execution_time_ms,
            )

        except Exception as e:
            # Check if this is a "Claude Code not found" error
            is_not_found = (
                (ClaudeCodeNotFoundError and isinstance(e, ClaudeCodeNotFoundError))
                or (is_claude_not_found_error and is_claude_not_found_error(e))
            )

            if is_not_found:
                # Track fallback reason
                fallback_reason = "Claude Code executable not found"
                ClaudeCodeTool._fallback_count += 1
                ClaudeCodeTool._fallback_reason = fallback_reason
                self._instance_fallback_reason = fallback_reason

                # Visible warning to user
                self.logger.warning(
                    "SDK_FALLBACK_TO_CLI",
                    reason=fallback_reason,
                    error=str(e),
                    fallback_count=ClaudeCodeTool._fallback_count,
                    message="SDK requires Claude Code executable. Falling back to CLI.",
                )

                # Switch to CLI for this instance and future calls
                self._using_sdk = False

                # Fallback to CLI
                if self.cli:
                    return await self._execute_via_cli(prompt)

                return CodeGenerationResult(
                    success=False,
                    error=f"SDK failed (Claude Code not found) and CLI unavailable: {e}",
                )

            # Other SDK errors - log and fallback
            self.logger.error("sdk_execution_failed", error=str(e))

            # Fallback to CLI on SDK failure
            if self.cli:
                self.logger.info("falling_back_to_cli", reason="SDK execution error")
                return await self._execute_via_cli(prompt)

            return CodeGenerationResult(
                success=False,
                error=f"SDK execution failed: {str(e)}",
            )

    async def _execute_via_cli(
        self,
        prompt: str,
        agent_type: str = "general",
        claude_agent: Optional[str] = None,
        max_turns: Optional[int] = None,
    ) -> CodeGenerationResult:
        """
        Execute code generation via Claude CLI (subprocess).

        Args:
            prompt: The enriched prompt
            agent_type: Type of agent for meaningful file naming
            claude_agent: .claude/agents/ agent name for --agent flag
            max_turns: Max agentic turns for --max-turns cost control

        Returns:
            CodeGenerationResult
        """
        # Execute via CLI with dynamic semaphore
        async with self._cli_semaphore:
            response = await self.cli.execute(
                prompt,
                file_context=agent_type,
                agent_name=claude_agent,
                max_turns=max_turns,
            )

        return CodeGenerationResult(
            success=response.success,
            files=response.files,
            output=response.output,
            error=response.error,
            execution_time_ms=response.execution_time_ms,
        )

    def _detect_openrouter_config(self):
        """Check LLM config for OpenRouter provider and enable HTTP backend."""
        try:
            config_path = Path("/app/config/llm_models.yml")
            if not config_path.exists():
                # Try local path
                engine_root = Path(__file__).parent.parent.parent
                config_path = engine_root / "config" / "llm_models.yml"

            if config_path.exists():
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f)

                models = cfg.get("models", {})
                primary = models.get("primary", {})

                provider = primary.get("provider", "")
                if provider in ("openrouter", "openai"):
                    self._using_openrouter = True
                    self._openrouter_model = primary.get("model", "qwen/qwen3-coder:free")
                    self._openrouter_max_tokens = primary.get("max_tokens", 16384)

                    # Get API key + base URL based on provider
                    if provider == "openai":
                        self._openrouter_api_key = os.getenv("OPENAI_API_KEY", "")
                        self._openrouter_base_url = "https://api.openai.com/v1"
                    else:
                        self._openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
                        self._openrouter_base_url = "https://openrouter.ai/api/v1"

                    if self._openrouter_api_key:
                        self.logger.info(
                            "backend_selected",
                            backend=provider,
                            model=self._openrouter_model,
                            reason="LLM config has %s primary provider" % provider,
                        )
                    else:
                        self._using_openrouter = False
                        self.logger.warning("api_no_key", reason="%s API key not set" % provider.upper())
        except Exception as e:
            self.logger.debug("openrouter_config_detect_failed", error=str(e))

    async def _execute_via_openrouter(
        self,
        prompt: str,
        agent_type: str = "general",
    ) -> "CodeGenerationResult":
        """
        Execute code generation via OpenRouter HTTP API.

        This sends the prompt to OpenRouter's chat completions endpoint
        and parses generated code files from the response.

        Includes exponential backoff retry logic for 429 rate limit responses.
        """
        import httpx

        base_url = getattr(self, "_openrouter_base_url", "https://openrouter.ai/api/v1")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://coding-engine.local",
            "X-Title": "Coding Engine",
        }

        # Build system prompt for code generation
        system_msg = (
            "You are a code generation assistant. Generate production-ready code files. "
            "For each file, output it in this format:\n"
            "```filepath: <relative/path/to/file>\n<code content>\n```\n"
            "Generate complete, working files. No placeholders or TODOs."
        )

        # GPT-5.4+ requires max_completion_tokens instead of max_tokens
        base_url = getattr(self, "_openrouter_base_url", "https://openrouter.ai/api/v1")
        is_openai = "openai.com" in base_url
        token_key = "max_completion_tokens" if is_openai else "max_tokens"

        payload = {
            "model": self._openrouter_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            token_key: self._openrouter_max_tokens,
            "temperature": 0.3,
        }

        max_retries = 5
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                    # Handle 429 rate limit with exponential backoff
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("retry-after")
                        if retry_after:
                            try:
                                wait = min(float(retry_after), 60)
                            except ValueError:
                                wait = min(2 ** attempt * 2, 60)
                        else:
                            wait = min(2 ** attempt * 2, 60)
                        self.logger.warning(
                            "openrouter_rate_limited",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                # Extract response text (some models like nemotron use 'reasoning' instead of 'content')
                msg = data.get("choices", [{}])[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""

                self.logger.info("openai_response_received",
                                content_length=len(content),
                                preview=content[:200])

                # Parse generated files from markdown code blocks
                files = self._parse_code_files(content)

                # Write files to working directory + sync to sandbox for live preview
                written_files = []
                if self.working_dir and files:
                    for gf in files:
                        try:
                            out_path = Path(self.working_dir) / gf.path
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            out_path.write_text(gf.content, encoding="utf-8")
                            written_files.append(gf)
                        except Exception as write_err:
                            self.logger.warning("file_write_failed", path=gf.path, error=str(write_err))

                    # Sync to sandbox container for live preview
                    if written_files:
                        self._sync_to_sandbox(written_files)

                model_used = data.get("model", self._openrouter_model)
                usage = data.get("usage", {})

                self.logger.info(
                    "openrouter_complete",
                    model=model_used,
                    files_generated=len(written_files),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )

                return CodeGenerationResult(
                    success=True,
                    files=written_files if written_files else files,
                    output=content[:500],  # Truncate for logging
                    error=None,
                    execution_time_ms=0,
                )

            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else 0
                error_body = e.response.text[:300] if e.response else str(e)

                # Retry on 429 (caught here if raise_for_status fires before our check)
                # and on 502/503/504 server errors
                if status in (429, 502, 503, 504) and attempt < max_retries - 1:
                    wait = min(2 ** attempt * 2, 60)
                    self.logger.warning(
                        "openrouter_retryable_error",
                        status=status,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait,
                    )
                    await asyncio.sleep(wait)
                    last_error = f"OpenRouter API error {status}: {error_body}"
                    continue

                self.logger.error("openrouter_http_error", status=status, error=error_body)
                return CodeGenerationResult(
                    success=False,
                    error=f"OpenRouter API error {status}: {error_body}",
                )
            except Exception as e:
                # Retry on connection errors
                if attempt < max_retries - 1:
                    wait = min(2 ** attempt * 2, 60)
                    self.logger.warning(
                        "openrouter_connection_error",
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait,
                    )
                    await asyncio.sleep(wait)
                    last_error = str(e)
                    continue

                self.logger.error("openrouter_execution_failed", error=str(e))
                return CodeGenerationResult(
                    success=False,
                    error=f"OpenRouter execution failed: {str(e)}",
                )

        # All retries exhausted
        self.logger.error("openrouter_all_retries_exhausted", attempts=max_retries, last_error=last_error)
        return CodeGenerationResult(
            success=False,
            error=f"OpenRouter failed after {max_retries} retries: {last_error}",
        )

    def _parse_code_files(self, content: str) -> list:
        """Parse code files from LLM response. Supports multiple formats."""
        files = []

        # Pattern 1: ```filepath: path/to/file\n...\n```
        pattern1 = r'```(?:filepath:\s*(.+?))\n(.*?)```'
        for filepath, code in re.findall(pattern1, content, re.DOTALL):
            filepath = filepath.strip()
            if filepath and "/" in filepath:
                files.append(GeneratedFile(
                    path=filepath, content=code.rstrip(),
                    language=self._detect_language(filepath),
                ))

        # Pattern 2: ```language:path/to/file.ext\n...\n``` (GPT-5.4 format)
        if not files:
            pattern2 = r'```\w+:([\w/._-]+\.\w+)\n(.*?)```'
            for filepath, code in re.findall(pattern2, content, re.DOTALL):
                filepath = filepath.strip()
                if filepath:
                    files.append(GeneratedFile(
                        path=filepath, content=code.rstrip(),
                        language=self._detect_language(filepath),
                    ))

        # Pattern 3: ```language\n// File: path/to/file\n...\n```
        if not files:
            pattern3 = r'```\w*\n(?://|#|/\*)\s*(?:File|filename|path):\s*(.+?)\n(.*?)```'
            for filepath, code in re.findall(pattern3, content, re.DOTALL):
                filepath = filepath.strip()
                if filepath:
                    files.append(GeneratedFile(
                        path=filepath, content=code.rstrip(),
                        language=self._detect_language(filepath),
                    ))

        # Pattern 4: **File:** `path/to/file.ext` followed by code block
        if not files:
            pattern4 = r'\*\*(?:File|Path)\*?\*?:?\s*`([^`]+)`\s*\n+```\w*\n(.*?)```'
            for filepath, code in re.findall(pattern4, content, re.DOTALL):
                filepath = filepath.strip()
                if filepath:
                    files.append(GeneratedFile(
                        path=filepath, content=code.rstrip(),
                        language=self._detect_language(filepath),
                    ))

        if files:
            self.logger.info("parsed_code_files", count=len(files),
                           paths=[f.path for f in files[:5]])

        return files

    def _sync_to_sandbox(self, files: list):
        """Write generated files to output dir (shared volume → sandbox sees them)."""
        from pathlib import Path as _P

        written = 0
        for gf in files:
            try:
                target = _P(self.working_dir) / gf.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(gf.content, encoding="utf-8")
                written += 1
            except Exception as e:
                self.logger.debug("file_write_failed", path=gf.path, error=str(e)[:100])

        self.logger.info("sandbox_synced", files=written,
                        working_dir=self.working_dir)

    def _detect_language(self, filepath: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript',
            '.jsx': 'javascript', '.py': 'python', '.prisma': 'prisma',
            '.json': 'json', '.yml': 'yaml', '.yaml': 'yaml',
            '.md': 'markdown', '.css': 'css', '.html': 'html',
            '.sql': 'sql', '.sh': 'bash', '.dockerfile': 'dockerfile',
        }
        ext = Path(filepath).suffix.lower()
        return ext_map.get(ext, 'text')

    @property
    def backend_type(self) -> str:
        """Return the current backend type ('openrouter', 'sdk', 'cli', or 'kilo')."""
        if self._using_openrouter:
            return "openrouter"
        if self._using_kilo:
            return "kilo"
        return "sdk" if self._using_sdk else "cli"

    @property
    def sdk_available(self) -> bool:
        """Check if SDK backend is available and active."""
        return self._using_sdk and self._sdk_backend is not None

    @property
    def kilo_enabled(self) -> bool:
        """Check if Kilo backend is enabled and active."""
        return self._using_kilo

    def set_skill(self, skill: Optional["Skill"]) -> None:
        """
        Set or update the skill for prompt enrichment.

        This allows agents to inject their skill after tool initialization,
        enabling progressive disclosure - skill instructions are only
        included when actually executing, not in idle state.

        Args:
            skill: The Skill to inject, or None to clear
        """
        self.skill = skill
        if skill:
            self.logger.debug(
                "skill_set",
                skill=skill.name,
                tokens=skill.instruction_tokens,
            )

    def has_skill(self) -> bool:
        """Check if a skill is set for this tool instance."""
        return self.skill is not None

    def _extract_errors_from_context(self, context: Optional[str]) -> list[str]:
        """
        Extract error messages from context for complexity detection.

        Args:
            context: The context string that may contain error messages

        Returns:
            List of extracted error message strings
        """
        if not context:
            return []

        import re
        errors = []

        # Pattern 1: TypeScript/JavaScript errors
        ts_errors = re.findall(r'(?:Error|error|TS\d+):[^\n]+', context)
        errors.extend(ts_errors)

        # Pattern 2: Python tracebacks
        py_errors = re.findall(r'(?:TypeError|ValueError|ImportError|SyntaxError)[^\n]+', context)
        errors.extend(py_errors)

        # Pattern 3: Build errors with file:line format
        build_errors = re.findall(r'[^\s]+\.\w+:\d+:\d*[^\n]*', context)
        errors.extend(build_errors[:5])  # Limit to avoid noise

        return errors[:10]  # Cap at 10 errors for efficiency

    def _get_skill_for_agent(self, agent_type: str) -> Optional["Skill"]:
        """
        Get skill for a specific agent type with caching.

        This enables dynamic skill loading per agent_type during batch execution,
        where different slices may have different agent types.

        Args:
            agent_type: The agent/domain type (e.g., 'backend', 'testing')

        Returns:
            Skill object or None if not found
        """
        # If a global skill is set, use that
        if self.skill:
            return self.skill

        # Check cache first
        if agent_type in self._skill_cache:
            return self._skill_cache[agent_type]

        # Load skill dynamically
        try:
            from pathlib import Path
            from src.skills.loader import SkillLoader

            # Agent type to skill mapping
            AGENT_SKILL_MAP = {
                "general": "code-generation",
                "backend": "code-generation",
                "frontend": "code-generation",
                "fullstack": "code-generation",
                "testing": "test-generation",
                "security": "auth-setup",
                "database": "database-schema-generation",
                "devops": "environment-config",
                "api": "api-generation",
                "auth": "auth-setup",
                "infrastructure": "environment-config",
                "architect": "api-contract-design",
            }

            # Find the engine root (where .claude/skills/ is located)
            engine_root = Path(__file__).parent.parent.parent
            loader = SkillLoader(engine_root)

            skill_name = AGENT_SKILL_MAP.get(agent_type, "code-generation")
            skill = loader.load_skill(skill_name)

            if skill:
                self._skill_cache[agent_type] = skill
                self.logger.debug(
                    "skill_loaded_for_agent",
                    agent_type=agent_type,
                    skill_name=skill_name,
                    instruction_tokens=skill.instruction_tokens,
                )
            return skill
        except Exception as e:
            self.logger.warning(
                "skill_load_failed",
                agent_type=agent_type,
                error=str(e),
            )
            return None

    async def execute_workflow(
        self,
        steps: list,  # list[WorkflowStep] from claude_agent_tool
        initial_context: Optional[dict] = None,
        on_step_complete: Optional[Any] = None,
    ):
        """
        Execute a multi-step workflow routine (SDK only).

        This method is only available when using the SDK backend.
        Falls back to sequential execute() calls if SDK is unavailable.

        Args:
            steps: List of WorkflowStep objects
            initial_context: Initial variables for the workflow context
            on_step_complete: Callback after each step completes

        Returns:
            WorkflowResult from SDK, or dict with sequential results
        """
        if self._using_sdk and self._sdk_backend:
            return await self._sdk_backend.workflow(
                steps=steps,
                initial_context=initial_context,
                on_step_complete=on_step_complete,
            )

        # Fallback: Execute steps sequentially via CLI
        self.logger.warning(
            "workflow_fallback_to_sequential",
            reason="SDK not available, executing steps sequentially",
        )

        results = []
        context = initial_context or {}

        for i, step in enumerate(steps):
            # Interpolate prompt with context
            prompt = step.prompt.format(**context)

            result = await self.execute(
                prompt=prompt,
                agent_type="general",
            )
            results.append(result)

            if on_step_complete:
                on_step_complete(i, step.name, result)

            if not result.success:
                return {
                    "success": False,
                    "steps_completed": i,
                    "total_steps": len(steps),
                    "results": results,
                    "error": result.error,
                }

        return {
            "success": True,
            "steps_completed": len(steps),
            "total_steps": len(steps),
            "results": results,
        }

    async def execute_parallel_with_gates(
        self,
        prompts: list[tuple[str, str, Optional[str], str]],
        strategy: str = "and",
        min_success: int = 1,
    ) -> dict[str, CodeGenerationResult]:
        """
        Execute multiple code generations with AsyncGates for robustness.
        
        Args:
            prompts: List of (id, prompt, context, agent_type) tuples
            strategy: Gate strategy - "and" (all), "or" (min_success), "majority"
            min_success: Minimum successful tasks for OR strategy
            
        Returns:
            Dict mapping id to CodeGenerationResult
        """
        if not ClaudeCodeTool._async_gates:
            self.logger.warning("async_gates_not_available_using_batch")
            return await self.execute_batch(prompts)
        
        # Load context once for all prompts (use "general" profile for batch operations)
        # Individual prompts may have different agent types, so we use the broadest profile
        auto_context = {}
        if self.load_context:
            auto_context = await self._load_all_context_parallel(agent_type="general")

        # Build tasks for AsyncGates
        tasks = []
        for id_, prompt, context, agent_type in prompts:
            async def create_task(p=prompt, c=context, at=agent_type, ac=auto_context):
                enriched = await self._build_enriched_prompt(p, c, at, ac)
                response = await self.cli.execute(enriched, file_context=at)
                return CodeGenerationResult(
                    success=response.success,
                    files=response.files,
                    output=response.output,
                    error=response.error,
                    execution_time_ms=response.execution_time_ms,
                )
            
            tasks.append((id_, create_task))
        
        # Execute with selected gate strategy
        self.logger.info(
            "parallel_gates_execution",
            task_count=len(tasks),
            strategy=strategy,
        )
        
        if strategy == "or":
            gate_result = await ClaudeCodeTool._async_gates.OR(tasks, min_success=min_success)
        elif strategy == "majority":
            gate_result = await ClaudeCodeTool._async_gates.MAJORITY(tasks)
        else:  # default: AND
            gate_result = await ClaudeCodeTool._async_gates.AND(tasks, fail_fast=False)
        
        # Convert gate results to CodeGenerationResults
        results = {}
        for task_result in gate_result.results:
            if task_result.success and task_result.result:
                results[task_result.task_id] = task_result.result
            else:
                results[task_result.task_id] = CodeGenerationResult(
                    success=False,
                    error=task_result.error or "Gate execution failed",
                )
        
        self.logger.info(
            "parallel_gates_complete",
            strategy=strategy,
            status=gate_result.status.value,
            successful=gate_result.successful_count,
            failed=gate_result.failed_count,
        )
        
        return results

    async def execute_batch(
        self,
        prompts: list[tuple[str, str, Optional[str], str]],
    ) -> dict[str, CodeGenerationResult]:
        """
        Execute multiple code generations in parallel.

        Args:
            prompts: List of (id, prompt, context, agent_type) tuples

        Returns:
            Dict mapping id to CodeGenerationResult
        """
        # Load context once for all prompts (use "general" profile for batch operations)
        auto_context = {}
        if self.load_context:
            auto_context = await self._load_all_context_parallel(agent_type="general")

        # Build full prompts with enriched context
        full_prompts = []
        for id_, prompt, context, agent_type in prompts:
            enriched = await self._build_enriched_prompt(prompt, context, agent_type, auto_context)
            full_prompts.append((id_, enriched))

        # Execute batch
        responses = await self.cli_pool.execute_batch(full_prompts)

        # Convert to results
        results = {}
        for id_, response in responses.items():
            results[id_] = CodeGenerationResult(
                success=response.success,
                files=response.files,
                output=response.output,
                error=response.error,
                execution_time_ms=response.execution_time_ms,
            )

        return results

    def _read_context_files(self, file_paths: list[str]) -> str:
        """Read file contents and format them as context."""
        parts = ["## Reference Files\n"]
        for file_path in file_paths:
            try:
                path = Path(file_path)
                if path.exists():
                    content = path.read_text(encoding='utf-8', errors='replace')
                    # Truncate very large files
                    if len(content) > 10000:
                        content = content[:10000] + "\n... (truncated)"
                    ext = path.suffix.lstrip('.') or 'txt'
                    parts.append(f"### {path.name}\n```{ext}\n{content}\n```\n")
            except Exception as e:
                self.logger.warning(f"Failed to read context file {file_path}: {e}")

        return "\n".join(parts) if len(parts) > 1 else ""

    async def _build_enriched_prompt(
        self,
        prompt: str,
        context: Optional[str],
        agent_type: str,
        auto_context: dict[str, str],
    ) -> str:
        """
        Build the full prompt with all context sources including Supermemory and Skills.

        Progressive Disclosure Pattern:
        - Skills are only loaded when the tool is actually executed
        - This saves ~3-5k tokens in idle state per agent

        Args:
            prompt: Main task prompt
            context: User-provided context
            agent_type: Type of agent
            auto_context: Auto-loaded context from CLAUDE.md, Reports, and Supermemory

        Returns:
            Complete enriched prompt
        """
        parts = []
        skill_injected = False  # Track if skill was injected (to skip redundant Skills CLAUDE.md)

        # SKILL INTEGRATION: Load skill dynamically based on agent_type
        # Skip skill instructions in minimal context mode (for validation fixes)
        # Uses tier-based loading for token efficiency (v2.0)
        if not self.minimal_context:
            skill = self._get_skill_for_agent(agent_type)
            if skill:
                # Determine skill tier: override > detection > full
                tier = self.skill_tier
                complexity_result: ComplexityResult | None = None

                if not tier:
                    # Detect complexity to determine tier
                    if skill.has_tier_support():
                        # Extract errors from both context and prompt for better detection
                        errors_from_context = self._extract_errors_from_context(context)
                        errors_from_prompt = self._extract_errors_from_context(prompt)
                        all_errors = errors_from_context + errors_from_prompt

                        complexity_result = detect_complexity(
                            prompt=prompt,
                            error_messages=all_errors,
                            event_type=auto_context.get("event_type"),
                        )
                        tier = complexity_result.tier
                    else:
                        tier = "full"  # No tier markers in skill
                    # Save detected tier for later skip logic (CLAUDE.md, agent prefix)
                    self.skill_tier = tier

                # Get tier-appropriate skill content
                if tier != "full" and skill.has_tier_support():
                    skill_prompt = skill.get_tier_prompt(tier)
                    tier_tokens = skill.tier_token_estimate.get(tier, skill.instruction_tokens)
                else:
                    skill_prompt = skill.get_full_prompt()
                    tier_tokens = skill.instruction_tokens
                    tier = "full"

                parts.append(skill_prompt)
                parts.append("\n---\n\n")
                skill_injected = True  # Mark skill as injected

                self.logger.debug(
                    "skill_instructions_injected",
                    skill=skill.name,
                    agent_type=agent_type,
                    tier=tier,
                    tokens=tier_tokens,
                    complexity=complexity_result.complexity.value if complexity_result else None,
                    complexity_reason=complexity_result.reason if complexity_result else None,
                )

        # Add agent-specific prefix with explicit technology instructions
        # Skip verbose prefixes in minimal mode OR when skill is injected with minimal tier
        # (The skill already contains role context)
        if self.minimal_context:
            # Only add a minimal fixer-style prefix
            parts.append("Fix the error with minimal changes. Do not refactor or add unnecessary code.\n\n")
        elif skill_injected and self.skill_tier == "minimal":
            # Skill already has role context, skip verbose prefix
            pass
        else:
            agent_prefixes = {
                "frontend": """As a frontend expert specializing in React and TypeScript:
- Create React functional components with TypeScript (.tsx files)
- Use modern React patterns (hooks, context, suspense)
- Create CSS modules or styled-components for styling
- Place components in src/components/
- Create hooks in src/hooks/
- Ensure responsive design and accessibility
""",
                "backend": """As a backend expert specializing in Python and FastAPI:
- Create FastAPI routes and endpoints
- Use Pydantic models for validation
- Create service classes for business logic
- Place API routes in src/api/
- Place services in src/services/
- Place models in src/models/
""",
                "testing": """As a testing expert:
- Create comprehensive unit tests and integration tests
- Use pytest for Python, vitest/jest for TypeScript
- Place tests in tests/ directory
- Achieve high code coverage
""",
                "security": """As a security expert:
- Implement authentication and authorization
- Use secure coding practices
- Handle sensitive data properly
- Implement input validation and sanitization
""",
                "devops": """As a DevOps expert:
- Create deployment configurations
- Write Dockerfiles and docker-compose files
- Configure CI/CD pipelines
- Set up infrastructure as code
""",
                "fixer": """As a code debugging expert:
- Analyze error messages carefully
- Identify root causes
- Fix the issue with minimal changes
- Ensure the fix doesn't break other code
""",
                "general": "",
            }
            parts.append(agent_prefixes.get(agent_type, ""))

        # Add CLAUDE.md context if available (project overview)
        # When skill is injected, only project's CLAUDE.md is loaded (not Engine's)
        # So we still show it, but with a different header
        if auto_context.get("claude_md"):
            # If skill injected, this is project-only CLAUDE.md (not Engine's)
            if skill_injected:
                parts.append("## Project Documentation\n\n")
            else:
                parts.append("## Project Context (from CLAUDE.md)\n\n")
            parts.append(auto_context["claude_md"])
            parts.append("\n\n")

        # Add Skills CLAUDE.md for agent skill discovery
        # Skip if skill was already injected (avoids redundant Skills Overview table)
        if auto_context.get("skills_claude_md") and not skill_injected:
            parts.append("## Skills Reference (from .claude/skills/CLAUDE.md)\n\n")
            parts.append(auto_context["skills_claude_md"])
            parts.append("\n\n")
        elif skill_injected:
            self.logger.debug("skills_claude_md_skipped", reason="skill already injected")

        # Add Supermemory context if available (related patterns)
        if auto_context.get("supermemory"):
            parts.append("## Related Patterns (from Memory)\n\n")
            parts.append(auto_context["supermemory"])
            parts.append("\n\n")

        # Add Fungus context if available (relevant code from project index)
        if auto_context.get("fungus"):
            parts.append("## Relevant Code Context (from Project Index)\n\n")
            parts.append(auto_context["fungus"])
            parts.append("\n\n")

        # Add Redis Stream context if available (real-time from async worker)
        if auto_context.get("redis_stream"):
            parts.append("## Real-Time Context (from Async Worker)\n\n")
            parts.append(auto_context["redis_stream"])
            parts.append("\n\n")

        # Add Component Tree for UI structure context
        if auto_context.get("component_tree"):
            parts.append(auto_context["component_tree"])
            parts.append("\n\n")

        # Add Reports context if available (current status)
        reports_sections = []
        if auto_context.get("debug_report"):
            reports_sections.append(f"### Latest Debug Report\n{auto_context['debug_report']}")
        if auto_context.get("impl_plan"):
            reports_sections.append(f"### Implementation Plan\n{auto_context['impl_plan']}")
        if auto_context.get("test_spec"):
            reports_sections.append(f"### Test Results\n{auto_context['test_spec']}")
        
        if reports_sections:
            parts.append("## Current Project Status\n\n")
            parts.append("\n\n".join(reports_sections))
            parts.append("\n\n")

        # Add user-provided context if available
        if context:
            parts.append(f"## Additional Context\n\n{context}\n\n")

        # Add main prompt
        parts.append(f"## Task\n\n{prompt}\n\n")

        # Add CLAUDE.md maintenance instructions for code generation agents
        if agent_type in ("frontend", "backend", "general") and not self.minimal_context:
            parts.append("""## CLAUDE.md Maintenance

After generating code, update the project's .claude/CLAUDE.md file if you:
1. Create new components/modules - add to "## Components" section
2. Add new API endpoints - update "## API Endpoints" section
3. Introduce new patterns - document in "## Patterns" section
4. Add dependencies - list in "## Dependencies" section

Keep CLAUDE.md accurate and synchronized with the codebase.

""")

        # Add output format instructions
        parts.append("""## Output Format

For each file you create, use this format:

```language:path/to/file.ext
// file content here
```

Create complete, production-ready code files.""")

        return "".join(parts)

    def _build_prompt(
        self,
        prompt: str,
        context: Optional[str],
        agent_type: str,
    ) -> str:
        """Legacy sync prompt builder. Use _build_enriched_prompt for async with context."""
        parts = []

        agent_prefixes = {
            "frontend": "As a frontend expert, ",
            "backend": "As a backend expert, ",
            "testing": "As a testing expert, ",
            "security": "As a security expert, ",
            "devops": "As a DevOps expert, ",
            "fixer": "As a code debugging expert, ",
            "general": "",
        }
        parts.append(agent_prefixes.get(agent_type, ""))

        if context:
            parts.append(f"## Context\n\n{context}\n\n")

        parts.append(f"## Task\n\n{prompt}\n\n")

        parts.append("""## Output Format

For each file you create, use this format:

```language:path/to/file.ext
// file content here
```

Create complete, production-ready code files.""")

        return "".join(parts)


# Convenience function for direct tool use
async def claude_code_tool(
    prompt: str,
    context: Optional[str] = None,
    agent_type: str = "general",
    working_dir: Optional[str] = None,
) -> CodeGenerationResult:
    """
    Convenience function to generate code using Claude Code CLI.

    Args:
        prompt: What to implement
        context: Additional context (contracts, etc.)
        agent_type: Type of agent
        working_dir: Working directory for output

    Returns:
        CodeGenerationResult with generated files
    """
    tool = ClaudeCodeTool(working_dir=working_dir)
    return await tool.execute(prompt, context, agent_type)
