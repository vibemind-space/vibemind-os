"""
Skill Dataclass.

Represents an Agent Skill loaded from a SKILL.md file.
Skills enable progressive disclosure - metadata is always loaded (~100 tokens),
while full instructions are loaded on-demand (~3-5k tokens).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Skill:
    """
    Represents an Agent Skill loaded from SKILL.md.

    Skills are modular capabilities that can be injected into agents.
    Each skill has:
    - name: Unique identifier (e.g., "code-generation")
    - description: Short description from YAML frontmatter
    - instructions: Full markdown body with detailed instructions
    - trigger_events: Events that activate this skill
    - resources: Additional files in the skill directory

    Token Efficiency:
    - Metadata (~100 tokens): name, description, trigger_events
    - Instructions (~3-5k tokens): Full SKILL.md body (loaded on-demand)

    Tier-Based Loading (v2.0):
    - Minimal (~200 tokens): Trigger events + critical rules only
    - Standard (~800 tokens): Add workflow + error patterns
    - Full (~1600+ tokens): Complete with code examples

    Skills can include tier markers:
    - <!-- END_TIER_MINIMAL --> marks end of minimal content
    - <!-- END_TIER_STANDARD --> marks end of standard content
    """

    name: str  # e.g., "code-generation"
    description: str  # From YAML frontmatter
    instructions: str  # Body of SKILL.md (full instructions)
    path: Path  # Path to skill directory
    trigger_events: list[str] = field(default_factory=list)
    resources: list[Path] = field(default_factory=list)  # Additional files

    # Tier support (v2.0)
    tier_tokens: dict[str, int] = field(default_factory=dict)  # From frontmatter
    tier_boundaries: dict[str, int] = field(default_factory=dict)  # Char positions

    @property
    def metadata_tokens(self) -> int:
        """
        Approximate tokens for metadata (always loaded).

        Returns rough estimate using character count / 4.
        """
        metadata_chars = len(self.name) + len(self.description)
        for event in self.trigger_events:
            metadata_chars += len(event)
        return metadata_chars // 4

    @property
    def instruction_tokens(self) -> int:
        """
        Approximate tokens for full instructions (on-demand).

        Returns rough estimate using character count / 4.
        """
        return len(self.instructions) // 4

    @property
    def total_tokens(self) -> int:
        """Total estimated tokens for full skill."""
        return self.metadata_tokens + self.instruction_tokens

    def to_dict(self) -> dict:
        """Convert skill to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "trigger_events": self.trigger_events,
            "path": str(self.path),
            "metadata_tokens": self.metadata_tokens,
            "instruction_tokens": self.instruction_tokens,
            "resources": [str(r) for r in self.resources],
        }

    def get_metadata_prompt(self) -> str:
        """
        Get minimal metadata for skill selection (low token count).

        Used when listing available skills without loading full instructions.
        """
        events_str = ", ".join(self.trigger_events) if self.trigger_events else "manual"
        return f"- **{self.name}**: {self.description} (triggers: {events_str})"

    def get_full_prompt(self) -> str:
        """
        Get complete skill prompt for agent injection.

        Includes full instructions - use only when skill is activated.
        """
        return f"""## Skill: {self.name}

{self.description}

---

{self.instructions}
"""

    def get_tier_content(self, tier: str = "full") -> str:
        """
        Get skill content for a specific tier.

        Args:
            tier: "minimal", "standard", or "full"

        Returns:
            Skill instructions truncated to the tier boundary
        """
        if tier == "full" or tier not in self.tier_boundaries:
            return self.instructions

        boundary = self.tier_boundaries.get(tier, len(self.instructions))
        return self.instructions[:boundary].strip()

    def get_tier_prompt(self, tier: str = "full") -> str:
        """
        Get formatted prompt for a tier level.

        Args:
            tier: "minimal", "standard", or "full"

        Returns:
            Skill prompt with tier-appropriate content
        """
        content = self.get_tier_content(tier)
        return f"""## Skill: {self.name}

{self.description}

---

{content}
"""

    @property
    def tier_token_estimate(self) -> dict[str, int]:
        """
        Estimated tokens per tier.

        Returns dict with keys: minimal, standard, full
        Uses tier_tokens from frontmatter if available,
        otherwise calculates from boundaries.
        """
        if self.tier_tokens:
            return self.tier_tokens

        # Calculate from boundaries
        return {
            "minimal": len(self.get_tier_content("minimal")) // 4,
            "standard": len(self.get_tier_content("standard")) // 4,
            "full": self.instruction_tokens,
        }

    def has_tier_support(self) -> bool:
        """Check if skill has tier markers defined."""
        return bool(self.tier_boundaries)

    def matches_event(self, event_type: str) -> bool:
        """Check if this skill should trigger for given event type."""
        event_upper = event_type.upper()
        return any(
            trigger.upper() == event_upper or event_upper.endswith(trigger.upper())
            for trigger in self.trigger_events
        )

    def __repr__(self) -> str:
        return (
            f"Skill(name={self.name!r}, "
            f"events={len(self.trigger_events)}, "
            f"tokens={self.total_tokens})"
        )
