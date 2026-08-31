import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _curator import maybe_run_curator, review  # noqa: E402


def _write_skill(root: Path, app: str, name: str, **frontmatter_overrides) -> Path:
    fm = {
        "name": name,
        "description": "test skill",
        "app": app,
        "agents": ["*"],
        "trigger": "test",
        "inputs": [],
        "expected_state": {},
        "secrets": [],
        "confidence": 0.8,
        "attempts": 0,
        "successes": 0,
        "last_adjusted": None,
        "agent_created": False,
        "last_searched": None,
        "curator_status": "active",
        "pinned": False,
    }
    fm.update(frontmatter_overrides)
    skill_dir = root / app / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\nBody text.\n",
        encoding="utf-8",
    )
    return path


NOW = datetime(2026, 7, 10, tzinfo=timezone.utc)


def test_review_ignores_human_curated_skills(tmp_path):
    _write_skill(tmp_path, "app1", "old-human-skill", agent_created=False)

    report = review(root=tmp_path, now=NOW)

    assert report.reviewed == 0
    assert report.staled == []
    assert report.archived == []


def test_review_ignores_pinned_skills(tmp_path):
    _write_skill(
        tmp_path, "app1", "pinned-skill", agent_created=True, pinned=True,
        last_searched=(NOW - timedelta(days=200)).isoformat(),
    )

    report = review(root=tmp_path, now=NOW)

    assert report.reviewed == 0


def test_review_stales_skill_idle_past_threshold(tmp_path):
    path = _write_skill(
        tmp_path, "app1", "idle-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=45)).isoformat(), confidence=0.8,
    )

    report = review(root=tmp_path, now=NOW)

    assert report.staled == ["app1/idle-skill"]
    fm = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
    assert fm["curator_status"] == "stale"
    assert fm["confidence"] == pytest.approx(0.8 * 0.7)


def test_review_archives_skill_idle_past_archive_threshold(tmp_path):
    _write_skill(
        tmp_path, "app1", "ancient-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=120)).isoformat(),
    )

    report = review(root=tmp_path, now=NOW)

    assert report.archived == ["app1/ancient-skill"]
    assert not (tmp_path / "app1" / "ancient-skill").exists()
    archived_path = tmp_path / "_archive" / "app1" / "ancient-skill" / "SKILL.md"
    assert archived_path.exists()
    fm = yaml.safe_load(archived_path.read_text(encoding="utf-8").split("---")[1])
    assert fm["curator_status"] == "archived"


def test_review_leaves_recently_used_skill_active(tmp_path):
    path = _write_skill(
        tmp_path, "app1", "fresh-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=2)).isoformat(),
    )

    report = review(root=tmp_path, now=NOW)

    assert report.staled == []
    assert report.archived == []
    assert path.exists()


def test_review_dry_run_computes_without_writing(tmp_path):
    path = _write_skill(
        tmp_path, "app1", "idle-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=45)).isoformat(), confidence=0.8,
    )
    original_text = path.read_text(encoding="utf-8")

    report = review(root=tmp_path, dry_run=True, now=NOW)

    assert report.staled == ["app1/idle-skill"]
    assert path.read_text(encoding="utf-8") == original_text


def test_review_falls_back_to_file_mtime_when_never_searched(tmp_path):
    path = _write_skill(tmp_path, "app1", "never-searched", agent_created=True, last_searched=None)
    import os
    old_time = (NOW - timedelta(days=100)).timestamp()
    os.utime(path, (old_time, old_time))

    report = review(root=tmp_path, now=NOW)

    assert report.archived == ["app1/never-searched"]


def test_maybe_run_curator_skips_when_interval_not_elapsed(tmp_path):
    _write_skill(
        tmp_path, "app1", "idle-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=45)).isoformat(),
    )
    first = maybe_run_curator(root=tmp_path, now=NOW)
    assert first is not None

    second = maybe_run_curator(root=tmp_path, now=NOW + timedelta(hours=1))
    assert second is None


def test_review_recovers_from_crash_between_move_and_original_cleanup(tmp_path):
    # Regression test: a prior run can crash after os.replace() has already
    # moved the skill into the archive but before the leftover original
    # directory gets removed. The next review() must finish the cleanup
    # instead of raising when it finds dest_dir already occupied.
    _write_skill(
        tmp_path, "app1", "crash-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=120)).isoformat(),
    )

    first_report = review(root=tmp_path, now=NOW)

    assert first_report.archived == ["app1/crash-skill"]
    assert first_report.errors == []
    archived_dir = tmp_path / "_archive" / "app1" / "crash-skill"
    original_dir = tmp_path / "app1" / "crash-skill"
    assert archived_dir.exists()
    assert not original_dir.exists()

    # Simulate the crash: re-create the original directory with the
    # already-archived content, so both locations exist simultaneously —
    # exactly the state a crash between os.replace() and shutil.rmtree()
    # would leave behind.
    shutil.copytree(archived_dir, original_dir)
    archived_content_before = (archived_dir / "SKILL.md").read_text(encoding="utf-8")

    second_report = review(root=tmp_path, now=NOW)

    assert second_report.errors == []
    assert not original_dir.exists()
    assert archived_dir.exists()
    assert (archived_dir / "SKILL.md").read_text(encoding="utf-8") == archived_content_before


def test_maybe_run_curator_runs_again_after_interval(tmp_path):
    _write_skill(
        tmp_path, "app1", "idle-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=45)).isoformat(),
    )
    first = maybe_run_curator(root=tmp_path, now=NOW)
    assert first is not None

    second = maybe_run_curator(root=tmp_path, now=NOW + timedelta(hours=169))
    assert second is not None
