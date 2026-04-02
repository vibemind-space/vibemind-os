"""
Token Estimator - Manages token counting and budget allocation for prompts.

This module provides utilities for:
1. Estimating token counts from text
2. Token-aware truncation (preserving semantic boundaries)
3. Budget allocation across different prompt sections
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import Optional
import structlog

logger = structlog.get_logger()


# Default token budgets for different context types
DEFAULT_TOKEN_BUDGETS = {
    "skill_instructions": 5000,
    "engine_claude_md": 2000,
    "project_claude_md": 1500,
    "contracts": 1500,
    "requirements": 1000,
    "debug_report": 800,
    "component_tree": 800,
    "test_spec": 600,
    "impl_plan": 600,
    "supermemory": 800,
}

# Total budget for prompts (leaving room for response)
DEFAULT_TOTAL_BUDGET = 15000


class TokenEstimator:
    """
    Estimates token counts for text content.

    Uses a simple heuristic (chars / 4) by default, but can be extended
    to use tiktoken or other tokenizers for more accuracy.
    """

    def __init__(self, chars_per_token: float = 4.0):
        """
        Initialize the token estimator.

        Args:
            chars_per_token: Average characters per token (default: 4.0)
        """
        self.chars_per_token = chars_per_token
        self.logger = logger.bind(component="token_estimator")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        return int(len(text) / self.chars_per_token)

    def truncate_to_tokens(
        self,
        text: str,
        max_tokens: int,
        preserve_sections: bool = True,
        add_truncation_marker: bool = True,
    ) -> str:
        """
        Truncate text to fit within a token budget.

        Args:
            text: The text to truncate
            max_tokens: Maximum tokens allowed
            preserve_sections: Try to preserve markdown section boundaries
            add_truncation_marker: Add "... (truncated)" marker if truncated

        Returns:
            Truncated text
        """
        if not text:
            return ""

        current_tokens = self.estimate_tokens(text)
        if current_tokens <= max_tokens:
            return text

        # Calculate target character count
        target_chars = int(max_tokens * self.chars_per_token)

        if preserve_sections:
            # Try to truncate at section boundaries
            truncated = self._truncate_at_section_boundary(text, target_chars)
        else:
            truncated = text[:target_chars]

        if add_truncation_marker:
            truncated = truncated.rstrip() + "\n... (truncated)"

        self.logger.debug(
            "text_truncated",
            original_tokens=current_tokens,
            max_tokens=max_tokens,
            final_chars=len(truncated),
        )

        return truncated

    def _truncate_at_section_boundary(self, text: str, target_chars: int) -> str:
        """
        Truncate text at the nearest markdown section boundary.

        Args:
            text: The text to truncate
            target_chars: Target character count

        Returns:
            Text truncated at a section boundary
        """
        if len(text) <= target_chars:
            return text

        # Find all section headers (## Header)
        section_pattern = re.compile(r'^#{1,4}\s+.+$', re.MULTILINE)
        matches = list(section_pattern.finditer(text))

        if not matches:
            # No sections, truncate at paragraph boundary
            return self._truncate_at_paragraph(text, target_chars)

        # Find the last section that fits within target
        last_valid_pos = 0
        for match in matches:
            if match.start() <= target_chars:
                last_valid_pos = match.start()
            else:
                break

        if last_valid_pos > 0:
            # Find the end of the previous section
            prev_section_end = text.rfind('\n', 0, last_valid_pos)
            if prev_section_end > target_chars // 2:
                return text[:prev_section_end]

        return self._truncate_at_paragraph(text, target_chars)

    def _truncate_at_paragraph(self, text: str, target_chars: int) -> str:
        """
        Truncate text at the nearest paragraph boundary.

        Args:
            text: The text to truncate
            target_chars: Target character count

        Returns:
            Text truncated at a paragraph boundary
        """
        if len(text) <= target_chars:
            return text

        # Find the last double newline before target
        last_para = text.rfind('\n\n', 0, target_chars)
        if last_para > target_chars // 2:
            return text[:last_para]

        # Fall back to single newline
        last_newline = text.rfind('\n', 0, target_chars)
        if last_newline > target_chars // 2:
            return text[:last_newline]

        # Fall back to hard truncation
        return text[:target_chars]


@dataclass
class TokenBudget:
    """
    Manages token budget allocation across different prompt sections.

    Tracks allocations and ensures the total doesn't exceed the budget.
    """

    total_budget: int = DEFAULT_TOTAL_BUDGET
    allocations: dict[str, int] = field(default_factory=dict)
    used: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.logger = logger.bind(component="token_budget")
        self.estimator = TokenEstimator()

    @property
    def remaining(self) -> int:
        """Get remaining available tokens."""
        return self.total_budget - sum(self.used.values())

    @property
    def total_used(self) -> int:
        """Get total tokens used."""
        return sum(self.used.values())

    def allocate(self, category: str, max_tokens: Optional[int] = None) -> int:
        """
        Allocate tokens for a category.

        Args:
            category: The category name (e.g., "claude_md", "skill_instructions")
            max_tokens: Maximum tokens to allocate (uses default if not specified)

        Returns:
            Number of tokens allocated
        """
        if max_tokens is None:
            max_tokens = DEFAULT_TOKEN_BUDGETS.get(category, 500)

        # Don't exceed remaining budget
        available = self.remaining
        allocated = min(max_tokens, available)

        self.allocations[category] = allocated

        self.logger.debug(
            "tokens_allocated",
            category=category,
            requested=max_tokens,
            allocated=allocated,
            remaining=self.remaining - allocated,
        )

        return allocated

    def use(self, category: str, text: str) -> str:
        """
        Use allocated tokens for a category, truncating if necessary.

        Args:
            category: The category name
            text: The text content

        Returns:
            Text truncated to fit allocation
        """
        allocation = self.allocations.get(category)
        if allocation is None:
            allocation = self.allocate(category)

        truncated = self.estimator.truncate_to_tokens(text, allocation)
        self.used[category] = self.estimator.estimate_tokens(truncated)

        return truncated

    def get_summary(self) -> dict:
        """Get a summary of budget usage."""
        return {
            "total_budget": self.total_budget,
            "total_used": self.total_used,
            "remaining": self.remaining,
            "allocations": self.allocations.copy(),
            "used": self.used.copy(),
        }


class ContentDeduplicator:
    """
    Deduplicates content sections to avoid redundancy.

    Uses content hashing to detect duplicate sections between
    different context sources (e.g., Engine CLAUDE.md vs Project CLAUDE.md).
    """

    def __init__(self):
        self.seen_hashes: set[str] = set()
        self.logger = logger.bind(component="content_deduplicator")

    def _hash_section(self, content: str) -> str:
        """Generate a hash for a content section."""
        # Normalize whitespace before hashing
        normalized = re.sub(r'\s+', ' ', content.strip().lower())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def deduplicate(self, text: str) -> str:
        """
        Remove duplicate sections from text.

        Args:
            text: The text to deduplicate

        Returns:
            Text with duplicate sections removed
        """
        if not text:
            return ""

        # Split into sections by markdown headers
        section_pattern = re.compile(r'^(#{1,4}\s+.+)$', re.MULTILINE)
        parts = section_pattern.split(text)

        result_parts = []
        current_header = None
        duplicates_removed = 0

        for i, part in enumerate(parts):
            if section_pattern.match(part):
                current_header = part
            elif current_header:
                # This is section content
                section = current_header + '\n' + part
                section_hash = self._hash_section(section)

                if section_hash not in self.seen_hashes:
                    self.seen_hashes.add(section_hash)
                    result_parts.append(section)
                else:
                    duplicates_removed += 1

                current_header = None
            else:
                # Content before first header
                if part.strip():
                    part_hash = self._hash_section(part)
                    if part_hash not in self.seen_hashes:
                        self.seen_hashes.add(part_hash)
                        result_parts.append(part)

        if duplicates_removed > 0:
            self.logger.debug(
                "sections_deduplicated",
                duplicates_removed=duplicates_removed,
            )

        return '\n\n'.join(result_parts)

    def reset(self):
        """Reset the deduplicator for a new prompt."""
        self.seen_hashes.clear()


# Convenience functions for direct use
_default_estimator = TokenEstimator()


def estimate_tokens(text: str) -> int:
    """Estimate tokens in text using default estimator."""
    return _default_estimator.estimate_tokens(text)


def truncate_to_tokens(
    text: str,
    max_tokens: int,
    preserve_sections: bool = True,
) -> str:
    """Truncate text to token limit using default estimator."""
    return _default_estimator.truncate_to_tokens(
        text, max_tokens, preserve_sections
    )
