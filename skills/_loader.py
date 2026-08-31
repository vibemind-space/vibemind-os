"""SKILL.md loader for the VibeMind adaptive skill library.

Discovers ``vibemind-os/skills/<app>/<skill_name>/SKILL.md`` files, parses
their YAML frontmatter, and returns ``Skill`` objects that the coordinator
agent and Qdrant indexer consume.

Frontmatter contract is documented in ``skills/README.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SKILLS_ROOT = Path(__file__).resolve().parent
SKILL_FILE = "SKILL.md"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    app: str
    agents: list[str]
    trigger: str
    inputs: list[dict[str, Any]]
    expected_state: dict[str, Any]
    secrets: list[dict[str, Any]]
    confidence: float
    attempts: int
    successes: int
    last_adjusted: str | None
    body: str
    path: Path
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    agent_created: bool = False
    last_searched: str | None = None
    curator_status: str = "active"
    pinned: bool = False

    def visible_to(self, agent_name: str) -> bool:
        return "*" in self.agents or agent_name in self.agents

    def embedding_text(self) -> str:
        """Concatenated text used to compute the vector embedding."""
        return f"{self.name}\n{self.description}\napp={self.app}\ntriggers: {self.trigger}"


def parse_skill_file(path: Path) -> Skill:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path} has no YAML frontmatter")
    fm_text, body = match.group(1), match.group(2).strip()
    fm = yaml.safe_load(fm_text) or {}

    def _iso_or_none(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else value

    return Skill(
        name=fm["name"],
        description=fm["description"],
        app=fm.get("app", path.parent.parent.name),
        agents=list(fm.get("agents", ["*"])),
        trigger=fm.get("trigger", ""),
        inputs=list(fm.get("inputs", [])),
        expected_state=dict(fm.get("expected_state", {})),
        secrets=list(fm.get("secrets", [])),
        confidence=float(fm.get("confidence", 0.0)),
        attempts=int(fm.get("attempts", 0)),
        successes=int(fm.get("successes", 0)),
        last_adjusted=_iso_or_none(fm.get("last_adjusted")),
        body=body,
        path=path,
        raw_frontmatter=fm,
        agent_created=bool(fm.get("agent_created", False)),
        last_searched=_iso_or_none(fm.get("last_searched")),
        curator_status=str(fm.get("curator_status", "active")),
        pinned=bool(fm.get("pinned", False)),
    )


def discover_skills(root: Path | str = SKILLS_ROOT) -> list[Skill]:
    root = Path(root)
    skills: list[Skill] = []
    for skill_md in root.glob("*/*/SKILL.md"):
        # Skip hidden / underscore folders (e.g. internal helpers).
        if any(part.startswith("_") for part in skill_md.relative_to(root).parts):
            continue
        try:
            skills.append(parse_skill_file(skill_md))
        except Exception as exc:
            print(f"[skill-loader] WARN: skipping {skill_md}: {exc}")
    return sorted(skills, key=lambda s: (s.app, s.name))


def filter_for_agent(skills: list[Skill], agent_name: str) -> list[Skill]:
    return [s for s in skills if s.visible_to(agent_name)]


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", help="filter to skills visible to this agent")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    found = discover_skills()
    if args.agent:
        found = filter_for_agent(found, args.agent)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "app": s.app,
                        "agents": s.agents,
                        "description": s.description,
                        "confidence": s.confidence,
                        "path": str(s.path),
                    }
                    for s in found
                ],
                indent=2,
            )
        )
    else:
        print(f"Discovered {len(found)} skills")
        for s in found:
            print(f"  [{s.app}/{s.name}] conf={s.confidence:.2f} agents={s.agents}")
