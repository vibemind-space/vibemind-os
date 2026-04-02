"""
SessionMemory - Within-Session Pattern Learning.

Tracks successful fixes during a generation session and applies
learned patterns to similar errors. No external dependencies.

Key Features:
1. Records fix outcomes with error signatures
2. Matches new errors against past successes
3. Suggests prompts/approaches that worked before
4. Provides statistics for convergence monitoring
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FixRecord:
    """Record of a single fix attempt."""

    error_hash: str  # SHA-256 of normalized error
    error_type: str  # e.g., "type_error", "import_error"
    error_category: str  # e.g., "TS2339", "ModuleNotFoundError"
    error_message: str  # Original error message
    fix_prompt: str  # Prompt that was used
    fix_approach: str  # Brief description of approach
    fix_succeeded: bool
    files_modified: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    escalation_level: int = 2  # Default to LLM_TARGETED
    confidence_score: float = 0.5


@dataclass
class FixSuggestion:
    """Suggestion based on past successful fixes."""

    similarity_score: float  # 0.0 - 1.0, higher is more similar
    past_record: FixRecord
    suggested_prompt_hint: str  # Key elements from successful prompt
    reasoning: str  # Why this suggestion is relevant


class SessionMemory:
    """
    Tracks fix patterns within a generation session.

    Instead of treating each error as new, learns from successful
    fixes and applies patterns to similar errors.

    No external dependencies - all in-memory, session-scoped.
    """

    def __init__(self, max_records: int = 500) -> None:
        self._records: list[FixRecord] = []
        self._max_records = max_records
        self._success_by_category: dict[str, list[FixRecord]] = {}
        self._failure_by_category: dict[str, list[FixRecord]] = {}
        self.logger = logger.bind(component="SessionMemory")

    def record_fix(
        self,
        error_type: str,
        error_message: str,
        fix_prompt: str,
        fix_succeeded: bool,
        files_modified: Optional[list[str]] = None,
        fix_approach: str = "",
        escalation_level: int = 2,
        confidence_score: float = 0.5,
    ) -> FixRecord:
        """
        Record a fix attempt outcome.

        Args:
            error_type: Categorized error type
            error_message: Full error message
            fix_prompt: The prompt used to fix
            fix_succeeded: Whether the fix worked
            files_modified: List of files that were changed
            fix_approach: Brief description of the approach
            escalation_level: EscalationLevel used
            confidence_score: Confidence before attempting

        Returns:
            The created FixRecord
        """
        # Generate error hash
        error_hash = self._hash_error(error_message)
        error_category = self._extract_category(error_message)

        record = FixRecord(
            error_hash=error_hash,
            error_type=error_type.lower(),
            error_category=error_category,
            error_message=error_message[:1000],  # Truncate for memory
            fix_prompt=fix_prompt[:2000],  # Truncate for memory
            fix_approach=fix_approach,
            fix_succeeded=fix_succeeded,
            files_modified=files_modified or [],
            escalation_level=escalation_level,
            confidence_score=confidence_score,
        )

        # Add to records
        self._records.append(record)

        # Enforce max records limit (FIFO)
        if len(self._records) > self._max_records:
            removed = self._records.pop(0)
            self._remove_from_category_index(removed)

        # Index by category for fast lookup
        category_key = f"{error_type}:{error_category}"
        if fix_succeeded:
            if category_key not in self._success_by_category:
                self._success_by_category[category_key] = []
            self._success_by_category[category_key].append(record)
        else:
            if category_key not in self._failure_by_category:
                self._failure_by_category[category_key] = []
            self._failure_by_category[category_key].append(record)

        self.logger.debug(
            "fix_recorded",
            error_type=error_type,
            category=error_category,
            success=fix_succeeded,
            total_records=len(self._records),
        )

        return record

    def _remove_from_category_index(self, record: FixRecord) -> None:
        """Remove a record from category indexes."""
        category_key = f"{record.error_type}:{record.error_category}"

        if record.fix_succeeded and category_key in self._success_by_category:
            try:
                self._success_by_category[category_key].remove(record)
            except ValueError:
                pass
        elif category_key in self._failure_by_category:
            try:
                self._failure_by_category[category_key].remove(record)
            except ValueError:
                pass

    def find_similar_successes(
        self,
        error_type: str,
        error_message: str,
        limit: int = 3,
    ) -> list[FixSuggestion]:
        """
        Find successful fixes for similar errors.

        Uses multiple matching strategies:
        1. Exact hash match (highest confidence)
        2. Category + keyword match (high confidence)
        3. Structural pattern match (medium confidence)

        Args:
            error_type: Type of error to match
            error_message: Error message to match against
            limit: Maximum suggestions to return

        Returns:
            List of FixSuggestions, sorted by similarity (highest first)
        """
        suggestions: list[FixSuggestion] = []
        error_hash = self._hash_error(error_message)
        error_category = self._extract_category(error_message)
        keywords = self._extract_keywords(error_message)

        # Strategy 1: Exact hash match
        for record in self._records:
            if record.fix_succeeded and record.error_hash == error_hash:
                suggestions.append(
                    FixSuggestion(
                        similarity_score=1.0,
                        past_record=record,
                        suggested_prompt_hint=self._extract_prompt_hint(record.fix_prompt),
                        reasoning="Exact same error seen before, this fix worked",
                    )
                )

        # Strategy 2: Category + keyword match
        category_key = f"{error_type}:{error_category}"
        if category_key in self._success_by_category:
            for record in self._success_by_category[category_key]:
                if record.error_hash == error_hash:
                    continue  # Already added above

                record_keywords = self._extract_keywords(record.error_message)
                overlap = len(set(keywords) & set(record_keywords))
                if overlap > 0:
                    similarity = min(0.9, 0.5 + (overlap * 0.1))
                    suggestions.append(
                        FixSuggestion(
                            similarity_score=similarity,
                            past_record=record,
                            suggested_prompt_hint=self._extract_prompt_hint(
                                record.fix_prompt
                            ),
                            reasoning=f"Same error category with {overlap} matching keywords",
                        )
                    )

        # Strategy 3: Error type match with pattern similarity
        for record in self._records:
            if not record.fix_succeeded:
                continue
            if record.error_type != error_type.lower():
                continue
            if any(s.past_record.error_hash == record.error_hash for s in suggestions):
                continue  # Already added

            # Check for structural similarity
            pattern_score = self._calculate_pattern_similarity(
                error_message, record.error_message
            )
            if pattern_score >= 0.4:
                suggestions.append(
                    FixSuggestion(
                        similarity_score=pattern_score,
                        past_record=record,
                        suggested_prompt_hint=self._extract_prompt_hint(record.fix_prompt),
                        reasoning=f"Similar error pattern (score: {pattern_score:.2f})",
                    )
                )

        # Sort by similarity and limit
        suggestions.sort(key=lambda s: s.similarity_score, reverse=True)
        return suggestions[:limit]

    def _hash_error(self, error_message: str) -> str:
        """
        Generate normalized hash of error message.

        Normalizes:
        - Removes file paths (which may vary)
        - Removes line numbers
        - Lowercases
        - Removes extra whitespace
        """
        normalized = error_message.lower()

        # Remove file paths
        normalized = re.sub(r"[/\\][\w\-./\\]+\.\w+", "<FILE>", normalized)

        # Remove line:column numbers
        normalized = re.sub(r":\d+:\d+", ":<LINE>", normalized)
        normalized = re.sub(r"line \d+", "line <N>", normalized)

        # Remove specific variable/property names (keep structure)
        normalized = re.sub(r"'[\w]+'\s+does not exist", "'<NAME>' does not exist", normalized)
        normalized = re.sub(r"property '[\w]+'", "property '<NAME>'", normalized)

        # Normalize whitespace
        normalized = " ".join(normalized.split())

        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _extract_category(self, error_message: str) -> str:
        """Extract error category/code from message."""
        # TypeScript error codes
        ts_match = re.search(r"TS\d+", error_message)
        if ts_match:
            return ts_match.group()

        # Python errors
        py_match = re.search(r"(\w+Error):", error_message)
        if py_match:
            return py_match.group(1)

        # ESLint rules
        eslint_match = re.search(r"@[\w-]+/[\w-]+", error_message)
        if eslint_match:
            return eslint_match.group()

        # Generic patterns
        if "cannot find module" in error_message.lower():
            return "ModuleNotFound"
        if "is not defined" in error_message.lower():
            return "UndefinedReference"
        if "syntax error" in error_message.lower():
            return "SyntaxError"

        return "Unknown"

    def _extract_keywords(self, error_message: str) -> list[str]:
        """Extract important keywords from error message."""
        # Common important tokens
        important_patterns = [
            r"'([\w]+)'",  # Quoted identifiers
            r"(undefined|null|missing|expected|unexpected)",
            r"(import|export|module|require)",
            r"(type|interface|function|class|component)",
            r"(property|method|argument|parameter)",
        ]

        keywords = []
        message_lower = error_message.lower()

        for pattern in important_patterns:
            matches = re.findall(pattern, message_lower)
            keywords.extend(matches)

        return list(set(keywords))[:10]

    def _calculate_pattern_similarity(self, msg1: str, msg2: str) -> float:
        """
        Calculate structural similarity between two error messages.

        Uses normalized token overlap.
        """
        tokens1 = set(re.findall(r"\w+", msg1.lower()))
        tokens2 = set(re.findall(r"\w+", msg2.lower()))

        # Remove very common words
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to"}
        tokens1 -= stopwords
        tokens2 -= stopwords

        if not tokens1 or not tokens2:
            return 0.0

        # Jaccard similarity
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def _extract_prompt_hint(self, prompt: str) -> str:
        """
        Extract key elements from a successful prompt.

        Returns a concise hint about what approach worked.
        """
        # Look for specific patterns in the prompt
        hints = []

        if "add import" in prompt.lower():
            hints.append("Added missing import")
        if "fix type" in prompt.lower():
            hints.append("Fixed type definition")
        if "update interface" in prompt.lower():
            hints.append("Updated interface")
        if "add property" in prompt.lower():
            hints.append("Added missing property")
        if "remove" in prompt.lower() and "unused" in prompt.lower():
            hints.append("Removed unused code")
        if "null check" in prompt.lower() or "undefined check" in prompt.lower():
            hints.append("Added null/undefined check")
        if "async" in prompt.lower() or "await" in prompt.lower():
            hints.append("Fixed async/await handling")

        if hints:
            return "; ".join(hints)

        # Default: extract first actionable phrase
        sentences = prompt.split(".")
        for sentence in sentences[:3]:
            if any(word in sentence.lower() for word in ["fix", "add", "update", "change", "remove"]):
                return sentence.strip()[:100]

        return "Applied targeted fix"

    def get_success_rate(self, error_type: Optional[str] = None) -> float:
        """
        Get overall or category-specific success rate.

        Args:
            error_type: Optional error type to filter by

        Returns:
            Success rate as float (0.0 - 1.0)
        """
        if error_type:
            filtered = [r for r in self._records if r.error_type == error_type.lower()]
        else:
            filtered = self._records

        if not filtered:
            return 0.5  # Neutral default

        successes = sum(1 for r in filtered if r.fix_succeeded)
        return successes / len(filtered)

    def get_effective_strategies(self, error_type: str) -> list[str]:
        """
        Get list of approaches that worked for this error type.

        Returns list of fix_approach descriptions.
        """
        successful = [
            r.fix_approach
            for r in self._records
            if r.error_type == error_type.lower() and r.fix_succeeded and r.fix_approach
        ]

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for approach in successful:
            if approach not in seen:
                seen.add(approach)
                unique.append(approach)

        return unique[:5]  # Top 5

    def get_failed_approaches(self, error_type: str) -> list[str]:
        """
        Get list of approaches that DIDN'T work for this error type.

        Useful for avoiding repeated failures.
        """
        failed = [
            r.fix_approach
            for r in self._records
            if r.error_type == error_type.lower()
            and not r.fix_succeeded
            and r.fix_approach
        ]

        seen = set()
        unique = []
        for approach in failed:
            if approach not in seen:
                seen.add(approach)
                unique.append(approach)

        return unique[:5]

    def enhance_prompt(
        self,
        original_prompt: str,
        error_type: str,
        error_message: str,
    ) -> str:
        """
        Enhance a fix prompt with lessons learned.

        Adds hints from past successes and warns about past failures.
        """
        suggestions = self.find_similar_successes(error_type, error_message, limit=2)
        failed_approaches = self.get_failed_approaches(error_type)

        additions = []

        # Add success hints
        if suggestions:
            hints = [s.suggested_prompt_hint for s in suggestions]
            additions.append(
                f"\n\nPreviously successful approaches for similar errors:\n"
                + "\n".join(f"- {h}" for h in hints)
            )

        # Add failure warnings
        if failed_approaches:
            additions.append(
                f"\n\nApproaches that did NOT work (avoid these):\n"
                + "\n".join(f"- {a}" for a in failed_approaches[:3])
            )

        if additions:
            return original_prompt + "".join(additions)

        return original_prompt

    def get_statistics(self) -> dict:
        """Get session memory statistics."""
        total = len(self._records)
        successes = sum(1 for r in self._records if r.fix_succeeded)

        # By error type
        by_type: dict[str, dict] = {}
        for record in self._records:
            if record.error_type not in by_type:
                by_type[record.error_type] = {"total": 0, "success": 0}
            by_type[record.error_type]["total"] += 1
            if record.fix_succeeded:
                by_type[record.error_type]["success"] += 1

        # Calculate rates
        for type_stats in by_type.values():
            type_stats["rate"] = (
                type_stats["success"] / type_stats["total"]
                if type_stats["total"] > 0
                else 0
            )

        return {
            "total_records": total,
            "successes": successes,
            "failures": total - successes,
            "overall_rate": successes / total if total > 0 else 0,
            "by_error_type": by_type,
            "unique_categories": len(self._success_by_category) + len(self._failure_by_category),
        }

    def reset(self) -> None:
        """Reset session memory (for new session)."""
        record_count = len(self._records)
        self._records.clear()
        self._success_by_category.clear()
        self._failure_by_category.clear()

        self.logger.info("session_memory_reset", cleared_records=record_count)
