"""
Skill Loader.

Discovers and loads Agent Skills from .claude/skills/ directories.
Parses YAML frontmatter and extracts trigger events from markdown content.
"""

import re
from pathlib import Path
from typing import Optional

import yaml

from .skill import Skill


class SkillLoader:
    """
    Loads Skills from .claude/skills/ directories.

    Each skill is a directory containing a SKILL.md file with:
    - YAML frontmatter (name, description)
    - Markdown body (instructions)

    Example structure:
        .claude/skills/
        ├── code-generation/
        │   └── SKILL.md
        ├── test-generation/
        │   └── SKILL.md
        └── debugging/
            └── SKILL.md
    """

    SKILLS_DIR = ".claude/skills"
    SKILL_FILE = "SKILL.md"

    def __init__(self, project_root: Path | str):
        """
        Initialize SkillLoader.

        Args:
            project_root: Root directory of the project (where .claude/ is located)
        """
        self.project_root = Path(project_root)
        self.skills_path = self.project_root / self.SKILLS_DIR

    def discover_all_skills(self) -> list[str]:
        """
        Find all available skill names.

        Returns:
            List of skill directory names that contain SKILL.md
        """
        if not self.skills_path.exists():
            return []

        skills = []
        for d in self.skills_path.iterdir():
            if d.is_dir() and (d / self.SKILL_FILE).exists():
                skills.append(d.name)

        return sorted(skills)

    def load_skill(self, skill_name: str) -> Optional[Skill]:
        """
        Load a skill from its directory.

        Args:
            skill_name: Name of the skill directory (e.g., "code-generation")

        Returns:
            Skill object or None if not found
        """
        skill_dir = self.skills_path / skill_name
        skill_file = skill_dir / self.SKILL_FILE

        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {skill_file}: {e}")
            return None

        # Parse YAML frontmatter and body
        frontmatter, body = self._parse_frontmatter(content)

        # Find additional resources in skill directory
        resources = [
            f for f in skill_dir.iterdir()
            if f.is_file() and f.name != self.SKILL_FILE
        ]

        # Extract trigger events from the markdown body
        trigger_events = self._extract_trigger_events(body)

        # Parse tier boundaries from markers (v2.0)
        tier_boundaries = self._parse_tier_boundaries(body)

        # Extract tier_tokens from frontmatter if defined
        tier_tokens = frontmatter.get("tier_tokens", {})

        return Skill(
            name=frontmatter.get("name", skill_name),
            description=frontmatter.get("description", ""),
            instructions=body,
            path=skill_dir,
            trigger_events=trigger_events,
            resources=resources,
            tier_tokens=tier_tokens,
            tier_boundaries=tier_boundaries,
        )

    def load_all_skills(self) -> list[Skill]:
        """
        Load all available skills.

        Returns:
            List of all successfully loaded Skills
        """
        skills = []
        for skill_name in self.discover_all_skills():
            skill = self.load_skill(skill_name)
            if skill:
                skills.append(skill)
        return skills

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """
        Extract YAML frontmatter and body from markdown content.

        Args:
            content: Full SKILL.md content

        Returns:
            Tuple of (frontmatter_dict, body_string)
        """
        # Match YAML frontmatter between --- markers
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content, re.DOTALL)

        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1))
                body = match.group(2).strip()
                return frontmatter or {}, body
            except yaml.YAMLError as e:
                print(f"Warning: Could not parse YAML frontmatter: {e}")
                return {}, content

        # No frontmatter found, return empty dict and full content
        return {}, content.strip()

    def _parse_tier_boundaries(self, body: str) -> dict[str, int]:
        """
        Extract tier boundary markers from skill body.

        Tier markers in markdown:
        - <!-- END_TIER_MINIMAL --> marks end of minimal tier content
        - <!-- END_TIER_STANDARD --> marks end of standard tier content

        Args:
            body: Markdown body of the skill

        Returns:
            Dict mapping tier name to character position
        """
        boundaries = {}

        # Find minimal tier end
        minimal_match = re.search(r'<!--\s*END_TIER_MINIMAL\s*-->', body)
        if minimal_match:
            boundaries["minimal"] = minimal_match.start()

        # Find standard tier end
        standard_match = re.search(r'<!--\s*END_TIER_STANDARD\s*-->', body)
        if standard_match:
            boundaries["standard"] = standard_match.start()

        return boundaries

    def _extract_trigger_events(self, body: str) -> list[str]:
        """
        Extract event triggers from the skill body.

        Looks for tables with "Trigger Events" or "Event | Action" patterns,
        and extracts event names like BUILD_FAILED, CODE_FIXED, etc.

        Args:
            body: Markdown body of the skill

        Returns:
            List of event type names (uppercase)
        """
        events = set()

        # Pattern 1: Table cells with event names (e.g., | `BUILD_FAILED` |)
        table_pattern = r"\|\s*`?([A-Z][A-Z0-9_]+(?:_[A-Z0-9]+)+)`?\s*\|"
        for match in re.finditer(table_pattern, body):
            event = match.group(1)
            # Filter to likely event names (contain _ and typical suffixes)
            if any(suffix in event for suffix in [
                "_FAILED", "_SUCCEEDED", "_PASSED", "_STARTED",
                "_COMPLETE", "_CREATED", "_NEEDED", "_FOUND",
                "_READY", "_ERROR", "_FIXED", "_TAKEN"
            ]):
                events.add(event)

        # Pattern 2: EventType.XXX references
        enum_pattern = r"EventType\.([A-Z][A-Z0-9_]+)"
        for match in re.finditer(enum_pattern, body):
            events.add(match.group(1))

        # Pattern 3: event.type patterns in code blocks
        type_pattern = r"type[=:]?\s*['\"]?([A-Z][A-Z0-9_]+(?:_[A-Z0-9]+)+)['\"]?"
        for match in re.finditer(type_pattern, body):
            event = match.group(1)
            if "_" in event:
                events.add(event)

        return sorted(events)

    def get_skill_metadata(self, skill_name: str) -> Optional[dict]:
        """
        Get just the metadata for a skill (low token cost).

        Args:
            skill_name: Name of the skill

        Returns:
            Dict with name, description, trigger_events, or None
        """
        skill = self.load_skill(skill_name)
        if skill:
            return {
                "name": skill.name,
                "description": skill.description,
                "trigger_events": skill.trigger_events,
                "metadata_tokens": skill.metadata_tokens,
            }
        return None

    def __repr__(self) -> str:
        num_skills = len(self.discover_all_skills())
        return f"SkillLoader(path={self.skills_path}, skills={num_skills})"
