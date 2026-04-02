"""
Complexity Detector - Determines task complexity for tier-based skill loading.

Analyzes:
- Error type and count
- File scope (single vs multi-file)
- Error message patterns
- Task description keywords
- Event type

Now includes LLM-based complexity prediction for more accurate assessment.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog


logger = structlog.get_logger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels."""

    SIMPLE = "simple"  # Tier 1: ~200 tokens
    MEDIUM = "medium"  # Tier 2: ~800 tokens
    COMPLEX = "complex"  # Tier 3: ~1600 tokens


@dataclass
class ComplexityResult:
    """Result of complexity detection."""

    complexity: TaskComplexity
    tier: str  # "minimal", "standard", "full"
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation


class ComplexityDetector:
    """
    Detects task complexity to determine skill tier loading.

    Simple tasks (Tier 1 - minimal):
    - Single type error
    - Missing import
    - Single file fix
    - Typo corrections

    Medium tasks (Tier 2 - standard):
    - Multiple related errors
    - Component creation
    - 2-5 file modifications
    - API endpoint fixes

    Complex tasks (Tier 3 - full):
    - Architecture changes
    - New feature implementation
    - 5+ file changes
    - Multiple unrelated errors
    """

    # Error patterns that indicate simple fixes
    SIMPLE_PATTERNS = [
        r"Property '[^']+' does not exist",
        r"Cannot find name '[^']+'",
        r'Module \'"[^"]+"\' has no exported member',
        r"Type '[^']+' is not assignable to type '[^']+'",
        r"'[^']+' is declared but.*never used",
        r"Expected \d+ arguments?, but got \d+",
        r"Missing semicolon",
        r"Unexpected token",
        r"Cannot find module '[^']+'",
        r"has no default export",
        r"is not a module",
    ]

    # Keywords that indicate complex tasks
    COMPLEX_INDICATORS = [
        "architecture",
        "refactor",
        "new feature",
        "implement from scratch",
        "create new component",
        "add authentication",
        "database schema",
        "api design",
        "multi-step",
        "redesign",
        "overhaul",
        "migration",
    ]

    # Event types that typically need minimal context
    SIMPLE_EVENTS = [
        "TYPE_ERROR",
        "VALIDATION_ERROR",
        "LINT_ERROR",
    ]

    # Event types that typically need full context
    COMPLEX_EVENTS = [
        "GENERATION_COMPLETE",
        "E2E_TEST_FAILED",
        "UX_ISSUE_FOUND",
        "DEBUG_REPORT_CREATED",
    ]

    def detect(
        self,
        prompt: str,
        error_messages: Optional[list[str]] = None,
        files_affected: Optional[list[str]] = None,
        error_count: int = 0,
        event_type: Optional[str] = None,
    ) -> ComplexityResult:
        """
        Detect complexity based on task characteristics.

        Args:
            prompt: The task/fix prompt
            error_messages: List of error messages
            files_affected: List of files mentioned
            error_count: Number of errors to fix
            event_type: The triggering event type

        Returns:
            ComplexityResult with tier recommendation
        """
        score = 0  # Higher = more complex
        reasons = []

        error_messages = error_messages or []
        files_affected = files_affected or []

        # Check error count
        if error_count == 0:
            error_count = len(error_messages)

        if error_count == 0:
            # No explicit errors - check prompt for complexity
            pass
        elif error_count == 1:
            score -= 2
            reasons.append("single error")
        elif error_count <= 3:
            score += 1
            reasons.append(f"{error_count} errors")
        else:
            score += 3
            reasons.append(f"{error_count} errors (many)")

        # Check file scope
        file_count = len(set(files_affected))
        if file_count == 0:
            # Try to extract from prompt
            file_matches = re.findall(
                r'(?:src/|\.tsx?|\.jsx?|\.py)[^\s\'"]+', prompt
            )
            file_count = len(set(file_matches))

        if file_count <= 1:
            score -= 1
            reasons.append("single file")
        elif file_count <= 3:
            score += 1
            reasons.append(f"{file_count} files")
        else:
            score += 3
            reasons.append(f"{file_count} files (many)")

        # Check for simple error patterns
        simple_matches = 0
        for error in error_messages:
            for pattern in self.SIMPLE_PATTERNS:
                if re.search(pattern, error, re.IGNORECASE):
                    simple_matches += 1
                    break

        if simple_matches > 0 and simple_matches == len(error_messages):
            score -= 2
            reasons.append("simple error patterns")

        # Check prompt for complex indicators
        prompt_lower = prompt.lower()
        for indicator in self.COMPLEX_INDICATORS:
            if indicator in prompt_lower:
                score += 2
                reasons.append(f"complex: '{indicator}'")
                break

        # Event type heuristics
        if event_type:
            event_upper = event_type.upper()
            if any(s in event_upper for s in self.SIMPLE_EVENTS):
                score -= 1
                reasons.append(f"simple event")
            elif any(c in event_upper for c in self.COMPLEX_EVENTS):
                score += 2
                reasons.append(f"complex event")

        # Determine tier from score
        if score <= -1:
            complexity = TaskComplexity.SIMPLE
            tier = "minimal"
            confidence = 0.9 if score <= -2 else 0.7
        elif score <= 2:
            complexity = TaskComplexity.MEDIUM
            tier = "standard"
            confidence = 0.8
        else:
            complexity = TaskComplexity.COMPLEX
            tier = "full"
            confidence = 0.85 if score >= 4 else 0.7

        return ComplexityResult(
            complexity=complexity,
            tier=tier,
            confidence=confidence,
            reason="; ".join(reasons[:3]) if reasons else "default assessment",
        )

    async def detect_with_llm(
        self,
        prompt: str,
        error_messages: Optional[list[str]] = None,
        files_affected: Optional[list[str]] = None,
        code_context: Optional[str] = None,
        working_dir: str = ".",
    ) -> ComplexityResult:
        """
        Use LLM to detect task complexity more accurately.

        This provides better assessment for edge cases where rule-based
        detection might fail, such as:
        - Errors that seem simple but have complex root causes
        - Tasks with implicit cross-file dependencies
        - Context-dependent complexity

        Args:
            prompt: The task/fix prompt
            error_messages: List of error messages
            files_affected: List of files mentioned
            code_context: Optional code snippets for context
            working_dir: Working directory for Claude tool

        Returns:
            ComplexityResult with LLM-based tier recommendation
        """
        from src.tools.claude_code_tool import ClaudeCodeTool

        error_messages = error_messages or []
        files_affected = files_affected or []

        # First, get rule-based assessment as fallback
        rule_based = self.detect(
            prompt=prompt,
            error_messages=error_messages,
            files_affected=files_affected,
        )

        # Prepare context for LLM
        errors_text = "\n".join(error_messages[:10]) if error_messages else "No explicit errors"
        files_text = "\n".join(files_affected[:10]) if files_affected else "Unknown files"

        llm_prompt = f"""Predict the complexity of this coding task.

## TASK DESCRIPTION:
{prompt[:1500]}

## ERRORS (if any):
{errors_text[:1000]}

## FILES AFFECTED:
{files_text}

## CODE CONTEXT:
{code_context[:2000] if code_context else "No code context provided"}

## COMPLEXITY CRITERIA:

**MINIMAL (simple)** - Use when:
- Single type error or import fix
- One file modification
- Clear, isolated problem
- Pattern-based fix (add import, fix typo)

**STANDARD (medium)** - Use when:
- 2-5 related errors in multiple files
- Component creation or API endpoint fix
- Cross-file type mismatches
- Need to understand some context

**FULL (complex)** - Use when:
- Architecture or design changes
- New feature implementation
- 5+ files need changes
- Multiple unrelated errors
- Need deep codebase understanding

## ANALYSIS REQUIRED:
1. How many files likely need modification?
2. Are the errors related or independent?
3. Is there implicit complexity (async, types, state)?
4. What's the risk of breaking other code?

Respond with this JSON:
```json
{{
    "complexity": "minimal|standard|full",
    "confidence": 0.8,
    "reasoning": "Brief explanation",
    "estimated_files": 2,
    "cross_file_risk": "low|medium|high"
}}
```
"""

        try:
            claude_tool = ClaudeCodeTool(working_dir=working_dir)
            result = await claude_tool.execute(
                prompt=llm_prompt,
                skill="chunk-planning",
                skill_tier="minimal",  # Use minimal tier for efficiency
            )

            # Parse JSON response
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                llm_result = json.loads(json_match.group(1))

                complexity_map = {
                    "minimal": TaskComplexity.SIMPLE,
                    "standard": TaskComplexity.MEDIUM,
                    "full": TaskComplexity.COMPLEX,
                }

                tier_map = {
                    "minimal": "minimal",
                    "standard": "standard",
                    "full": "full",
                }

                complexity_str = llm_result.get("complexity", "standard").lower()

                return ComplexityResult(
                    complexity=complexity_map.get(complexity_str, TaskComplexity.MEDIUM),
                    tier=tier_map.get(complexity_str, "standard"),
                    confidence=llm_result.get("confidence", 0.75),
                    reason=f"LLM: {llm_result.get('reasoning', 'No reason')}",
                )

            # Fallback to rule-based if JSON parse fails
            logger.warning("llm_complexity_json_parse_failed")
            return rule_based

        except Exception as e:
            logger.warning("llm_complexity_detection_failed", error=str(e))
            return rule_based


async def detect_complexity_with_llm(
    prompt: str,
    error_messages: Optional[list[str]] = None,
    files_affected: Optional[list[str]] = None,
    code_context: Optional[str] = None,
    working_dir: str = ".",
) -> ComplexityResult:
    """
    Async convenience function for LLM-based complexity detection.

    Args:
        prompt: The task/fix prompt
        error_messages: List of error messages
        files_affected: List of files mentioned
        code_context: Optional code snippets
        working_dir: Working directory

    Returns:
        ComplexityResult with LLM-based tier recommendation
    """
    detector = ComplexityDetector()
    return await detector.detect_with_llm(
        prompt=prompt,
        error_messages=error_messages,
        files_affected=files_affected,
        code_context=code_context,
        working_dir=working_dir,
    )


def detect_complexity(
    prompt: str,
    error_messages: Optional[list[str]] = None,
    files_affected: Optional[list[str]] = None,
    error_count: int = 0,
    event_type: Optional[str] = None,
) -> ComplexityResult:
    """
    Convenience function for complexity detection.

    Args:
        prompt: The task/fix prompt
        error_messages: List of error messages
        files_affected: List of files mentioned
        error_count: Number of errors to fix
        event_type: The triggering event type

    Returns:
        ComplexityResult with tier recommendation
    """
    detector = ComplexityDetector()
    return detector.detect(
        prompt=prompt,
        error_messages=error_messages,
        files_affected=files_affected,
        error_count=error_count,
        event_type=event_type,
    )
