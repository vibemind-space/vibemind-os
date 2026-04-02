"""
Kilo Code Tool - Wraps Kilo CLI as a callable tool for agents.

This tool allows agents to invoke Kilo Code CLI for code generation.
Kilo Code handles both generation AND file writing in one call.

Similar to ClaudeCodeTool but uses Kilo AI instead of Claude.
Enables multi-LLM support in the generation pipeline.

Key Differences from ClaudeCodeTool:
- CLI Command: 'kilocode' instead of 'claude'
- Auto Mode: '--auto' instead of '--dangerously-skip-permissions'
- JSON Output: '--json' flag
- Working Dir: '--workspace' flag
- Skills: '.kilocode/skills/' or falls back to '.claude/skills/'
"""
import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.skills.skill import Skill

from src.autogen.kilo_cli_wrapper import KiloCLI, KiloCLIPool, KiloCLIResponse, GeneratedFile
from src.config import get_settings

logger = structlog.get_logger()


@dataclass
class CodeGenerationResult:
    """Result from code generation."""
    success: bool
    files: list[GeneratedFile] = field(default_factory=list)
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    json_data: Optional[dict] = None  # Kilo-specific JSON response

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "files": [{"path": f.path, "language": f.language, "lines": len(f.content.splitlines())} for f in self.files],
            "output": self.output[:500] if self.output else "",
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


# Context profiles for selective loading based on agent type
CONTEXT_PROFILES = {
    "fixer": ["impl_plan", "debug_report"],
    "frontend": ["claude_md", "component_tree"],
    "backend": ["claude_md", "test_spec"],
    "testing": ["claude_md", "test_spec", "impl_plan"],
    "security": ["claude_md"],
    "devops": ["claude_md"],
    "general": ["claude_md", "debug_report", "impl_plan"],
}


class KiloCodeTool:
    """
    Tool that wraps Kilo Code CLI for use by agents.

    This is an alternative to ClaudeCodeTool for multi-LLM support.
    Kilo Code:
    - Generates code based on prompts
    - Writes files directly to the filesystem
    - Supports multiple agent modes (architect, code, orchestrator)
    - Returns structured JSON responses
    """

    # Class-level semaphore
    _default_max_concurrent = 2
    _cli_semaphore: Optional[asyncio.Semaphore] = None

    # Tool definition for Agent SDK
    TOOL_DEFINITION = {
        "name": "generate_code_kilo",
        "description": """Generate code using Kilo Code CLI.
This tool generates code files based on the given prompt and requirements.
Kilo Code will create the files directly in the working directory.
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
                },
                "mode": {
                    "type": "string",
                    "enum": ["code", "architect", "orchestrator", "test", "debug"],
                    "description": "Kilo agent mode for specialized behavior"
                }
            },
            "required": ["prompt"]
        }
    }

    def __init__(
        self,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        max_concurrent: int = 2,
        load_context: bool = True,
        mode: str = "code",
        skill: Optional["Skill"] = None,
        skill_tier: Optional[str] = None,
    ):
        self.working_dir = working_dir
        self.timeout = timeout if timeout is not None else get_settings().cli_timeout
        self.max_concurrent = max_concurrent
        self.load_context = load_context
        self.mode = mode
        self.skill = skill
        self.skill_tier = skill_tier
        self._skill_cache: dict[str, "Skill"] = {}
        self.logger = logger.bind(tool="kilo_code")

        # CLI backend
        self.cli = KiloCLI(working_dir=working_dir, timeout=self.timeout, mode=mode)
        self.cli_pool = KiloCLIPool(max_concurrent=max_concurrent, working_dir=working_dir, mode=mode)

        # Initialize semaphore
        if KiloCodeTool._cli_semaphore is None or KiloCodeTool._default_max_concurrent != max_concurrent:
            KiloCodeTool._cli_semaphore = asyncio.Semaphore(max_concurrent)
            KiloCodeTool._default_max_concurrent = max_concurrent
            self.logger.info("kilo_semaphore_initialized", max_concurrent=max_concurrent)

    async def _load_claude_md(self) -> str:
        """
        Load CLAUDE.md or KILO.md from working directory.

        Falls back to CLAUDE.md if KILO.md doesn't exist.
        """
        if not self.working_dir:
            return ""

        try:
            # Try KILO.md first (Kilo-specific context)
            kilo_md = Path(self.working_dir) / "KILO.md"
            if kilo_md.exists():
                content = kilo_md.read_text(encoding='utf-8', errors='replace')
                self.logger.debug("kilo_md_loaded", path=str(kilo_md))
                return content

            # Fall back to CLAUDE.md
            claude_md = Path(self.working_dir) / "CLAUDE.md"
            if claude_md.exists():
                content = claude_md.read_text(encoding='utf-8', errors='replace')
                self.logger.debug("claude_md_loaded_for_kilo", path=str(claude_md))
                return content

        except Exception as e:
            self.logger.debug("md_load_failed", error=str(e))

        return ""

    async def _load_all_context_parallel(
        self,
        query: Optional[str] = None,
        agent_type: str = "general",
    ) -> dict[str, str]:
        """
        Load context sources selectively based on agent type.

        Args:
            query: Optional query for semantic search
            agent_type: Type of agent

        Returns:
            Dict with context from each source
        """
        profile = CONTEXT_PROFILES.get(agent_type, CONTEXT_PROFILES["general"])

        context = {
            "claude_md": "",
            "debug_report": "",
            "impl_plan": "",
            "test_spec": "",
            "component_tree": "",
        }

        # Load CLAUDE.md/KILO.md
        if "claude_md" in profile:
            context["claude_md"] = await self._load_claude_md()

        return context

    def _get_skill_for_agent(self, agent_type: str) -> Optional["Skill"]:
        """
        Get skill for a specific agent type with caching.

        Checks for Kilo-specific skills first, then falls back to Claude skills.
        """
        if self.skill:
            return self.skill

        if agent_type in self._skill_cache:
            return self._skill_cache[agent_type]

        try:
            from src.skills.loader import SkillLoader

            AGENT_SKILL_MAP = {
                "general": "code-generation",
                "backend": "code-generation",
                "frontend": "code-generation",
                "testing": "test-generation",
                "security": "auth-setup",
                "database": "database-schema-generation",
                "devops": "environment-config",
                "api": "api-generation",
            }

            engine_root = Path(__file__).parent.parent.parent

            # Try Kilo-specific skills first
            kilo_skills_dir = engine_root / ".kilocode" / "skills"
            if kilo_skills_dir.exists():
                loader = SkillLoader(engine_root, skills_dir=".kilocode/skills")
            else:
                # Fall back to Claude skills
                loader = SkillLoader(engine_root)

            skill_name = AGENT_SKILL_MAP.get(agent_type, "code-generation")
            skill = loader.load_skill(skill_name)

            if skill:
                self._skill_cache[agent_type] = skill
                self.logger.debug(
                    "skill_loaded_for_kilo",
                    agent_type=agent_type,
                    skill_name=skill_name,
                )
            return skill
        except Exception as e:
            self.logger.warning(
                "skill_load_failed_kilo",
                agent_type=agent_type,
                error=str(e),
            )
            return None

    async def execute(
        self,
        prompt: str,
        context: Optional[str] = None,
        agent_type: str = "general",
        mode: Optional[str] = None,
    ) -> CodeGenerationResult:
        """
        Execute code generation via Kilo CLI.

        Args:
            prompt: The code generation prompt
            context: Additional context (contracts, types, etc.)
            agent_type: Type of agent for specialized prompts
            mode: Optional Kilo mode override (architect, code, orchestrator)

        Returns:
            CodeGenerationResult with generated files
        """
        # Load context
        auto_context = {}
        if self.load_context:
            auto_context = await self._load_all_context_parallel(
                query=prompt[:300],
                agent_type=agent_type,
            )

        # Build full prompt
        full_prompt = await self._build_enriched_prompt(prompt, context, agent_type, auto_context)

        # Map agent_type to Kilo mode if not specified
        effective_mode = mode
        if not effective_mode:
            mode_map = {
                "fixer": "debug",
                "testing": "test",
                "devops": "orchestrator",
            }
            effective_mode = mode_map.get(agent_type, self.mode)

        self.logger.info(
            "KILO_CLI_START",
            agent_type=agent_type,
            mode=effective_mode,
            prompt_preview=prompt[:200].replace("\n", " "),
            prompt_length=len(full_prompt),
            working_dir=str(self.working_dir),
        )

        # Execute via CLI
        import time
        start_time = time.time()

        async with self._cli_semaphore:
            response = await self.cli.execute(
                full_prompt,
                mode=effective_mode,
                output_format="json",
            )

        actual_duration_ms = int((time.time() - start_time) * 1000)

        # Log completion
        files_info = [f.path for f in response.files[:5]] if response.files else []
        self.logger.info(
            "KILO_CLI_COMPLETE",
            success=response.success,
            files_generated=len(response.files),
            files=files_info,
            duration_ms=actual_duration_ms,
            has_json=response.json_data is not None,
            error=response.error[:100] if response.error else None,
        )

        return CodeGenerationResult(
            success=response.success,
            files=response.files,
            output=response.output,
            error=response.error,
            execution_time_ms=response.execution_time_ms,
            json_data=response.json_data,
        )

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
        # Load context once for all prompts
        auto_context = {}
        if self.load_context:
            auto_context = await self._load_all_context_parallel(agent_type="general")

        # Build full prompts
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
                json_data=response.json_data,
            )

        return results

    async def _build_enriched_prompt(
        self,
        prompt: str,
        context: Optional[str],
        agent_type: str,
        auto_context: dict[str, str],
    ) -> str:
        """
        Build the full prompt with all context sources including Skills.

        Args:
            prompt: Main task prompt
            context: User-provided context
            agent_type: Type of agent
            auto_context: Auto-loaded context

        Returns:
            Complete enriched prompt
        """
        parts = []

        # Load skill if available
        skill = self._get_skill_for_agent(agent_type)
        if skill:
            tier = self.skill_tier or "full"
            if skill.has_tier_support():
                skill_prompt = skill.get_tier_prompt(tier)
            else:
                skill_prompt = skill.get_full_prompt()

            parts.append(skill_prompt)
            parts.append("\n---\n\n")

            self.logger.debug(
                "skill_injected_kilo",
                skill=skill.name,
                agent_type=agent_type,
                tier=tier,
            )

        # Add agent-specific prefix
        agent_prefixes = {
            "frontend": """As a frontend expert specializing in React and TypeScript:
- Create React functional components with TypeScript
- Use modern React patterns (hooks, context)
- Ensure responsive design and accessibility
""",
            "backend": """As a backend expert:
- Create clean API endpoints
- Use proper error handling
- Follow REST best practices
""",
            "testing": """As a testing expert:
- Create comprehensive tests
- Use real implementations, NO MOCKS
- Achieve high coverage
""",
            "fixer": """As a code debugging expert:
- Analyze error messages carefully
- Identify root causes
- Fix with minimal changes
""",
            "general": "",
        }
        parts.append(agent_prefixes.get(agent_type, ""))

        # Add CLAUDE.md/KILO.md context
        if auto_context.get("claude_md"):
            parts.append("## Project Context\n\n")
            parts.append(auto_context["claude_md"][:3000])  # Truncate for token efficiency
            parts.append("\n\n")

        # Add user-provided context
        if context:
            parts.append(f"## Additional Context\n\n{context}\n\n")

        # Add main prompt
        parts.append(f"## Task\n\n{prompt}\n\n")

        # Add output format instructions
        parts.append("""## Output Format

For each file you create, use this format:

```language:path/to/file.ext
// file content here
```

Create complete, production-ready code files.""")

        return "".join(parts)

    def set_skill(self, skill: Optional["Skill"]) -> None:
        """Set or update the skill for prompt enrichment."""
        self.skill = skill
        if skill:
            self.logger.debug("skill_set_kilo", skill=skill.name)

    @property
    def backend_type(self) -> str:
        """Return the backend type ('kilo')."""
        return "kilo"

    async def check_installed(self) -> bool:
        """Check if Kilo CLI is installed."""
        return await self.cli.check_installed()


# Convenience function for direct tool use
async def kilo_code_tool(
    prompt: str,
    context: Optional[str] = None,
    agent_type: str = "general",
    working_dir: Optional[str] = None,
    mode: str = "code",
) -> CodeGenerationResult:
    """
    Convenience function to generate code using Kilo Code CLI.

    Args:
        prompt: What to implement
        context: Additional context (contracts, etc.)
        agent_type: Type of agent
        working_dir: Working directory for output
        mode: Kilo agent mode

    Returns:
        CodeGenerationResult with generated files
    """
    tool = KiloCodeTool(working_dir=working_dir, mode=mode)
    return await tool.execute(prompt, context, agent_type)
