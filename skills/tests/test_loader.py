import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _loader import discover_skills, parse_skill_file  # noqa: E402


def _write_skill(root: Path, app: str, name: str, extra_frontmatter: str = "") -> Path:
    skill_dir = root / app / name
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\n"
        f"name: {name}\n"
        "description: test skill\n"
        f"app: {app}\n"
        "agents: ['*']\n"
        "trigger: test\n"
        "inputs: []\n"
        "expected_state: {}\n"
        "secrets: []\n"
        "confidence: 0.5\n"
        "attempts: 0\n"
        "successes: 0\n"
        "last_adjusted: null\n"
        f"{extra_frontmatter}"
        "---\n\nBody text.\n",
        encoding="utf-8",
    )
    return skill_path


def test_parse_skill_file_defaults_new_fields_when_absent(tmp_path):
    skill_path = _write_skill(tmp_path, "testapp", "test-skill")

    skill = parse_skill_file(skill_path)

    assert skill.agent_created is False
    assert skill.last_searched is None
    assert skill.curator_status == "active"
    assert skill.pinned is False


def test_parse_skill_file_reads_new_fields_when_present(tmp_path):
    skill_path = _write_skill(
        tmp_path,
        "testapp",
        "test-skill",
        extra_frontmatter=(
            "agent_created: true\n"
            'last_searched: "2026-06-01T00:00:00+00:00"\n'
            "curator_status: stale\n"
            "pinned: true\n"
        ),
    )

    skill = parse_skill_file(skill_path)

    assert skill.agent_created is True
    assert skill.last_searched == "2026-06-01T00:00:00+00:00"
    assert skill.curator_status == "stale"
    assert skill.pinned is True


def test_discover_skills_ignores_archive_directory(tmp_path):
    _write_skill(tmp_path, "testapp", "kept-skill")
    # Simulate an archived skill nested one level deeper than normal —
    # discover_skills globs exactly "*/*/SKILL.md" so this 3-level path is
    # structurally invisible, and the leading "_" is a second layer of
    # protection if that glob depth ever changes.
    archived_dir = tmp_path / "_archive" / "testapp" / "old-skill"
    archived_dir.mkdir(parents=True)
    (archived_dir / "SKILL.md").write_text(
        "---\nname: old-skill\ndescription: x\n---\nBody\n", encoding="utf-8"
    )

    found = discover_skills(root=tmp_path)

    assert [s.name for s in found] == ["kept-skill"]
