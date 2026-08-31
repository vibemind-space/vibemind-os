"""Idle-triggered lifecycle maintenance for agent-created skills.

Reviews every skill under ``skills/`` where ``agent_created: true`` and
``pinned: false``, and:
  - marks skills unused for STALE_AFTER_DAYS as ``curator_status: stale``
    and applies a one-time confidence decay
  - archives skills unused for ARCHIVE_AFTER_DAYS by moving them under
    ``skills/_archive/<app>/<skill_name>/`` (never deletes)

Never touches human-curated skills (``agent_created`` missing or false) or
pinned skills. See docs/superpowers/specs/2026-07-10-skill-curator-design.md.

Usage::

    python skills/_curator.py --review
    python skills/_curator.py --dry-run
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

from _loader import FRONTMATTER_RE, SKILLS_ROOT, Skill, discover_skills

STALE_AFTER_DAYS = int(os.environ.get("VIBEMIND_CURATOR_STALE_DAYS", "30"))
ARCHIVE_AFTER_DAYS = int(os.environ.get("VIBEMIND_CURATOR_ARCHIVE_DAYS", "90"))
INTERVAL_HOURS = int(os.environ.get("VIBEMIND_CURATOR_INTERVAL_HOURS", str(24 * 7)))
STALE_DECAY_FACTOR = float(os.environ.get("VIBEMIND_CURATOR_STALE_DECAY_FACTOR", "0.7"))


@dataclass
class CuratorReport:
    reviewed: int = 0
    staled: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _idle_days(skill: Skill, now: datetime) -> float:
    reference = _parse_iso(skill.last_searched)
    if reference is None:
        try:
            reference = datetime.fromtimestamp(skill.path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            reference = now
    return (now - reference).total_seconds() / 86400.0


def _write_frontmatter(path: Path, fm: dict) -> None:
    # Defensive normalization: guard against live datetime objects sneaking
    # into raw_frontmatter (e.g. an unquoted "field: 2026-05-04T..." in the
    # source YAML gets parsed by PyYAML as a datetime, not a str). yaml.dump
    # can serialize datetimes, but round-tripping them as native YAML
    # timestamps is a needless format change; normalize to ISO strings.
    fm = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in fm.items()}
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    original_body = match.group(2) if match else ""
    new_text = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip("\n") + "\n---\n" + original_body
    path.write_text(new_text, encoding="utf-8")


def _archive_skill(skill: Skill, archive_root: Path) -> Path:
    dest_dir = archive_root / skill.app / skill.name
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if (dest_dir / "SKILL.md").exists():
        # A prior run already completed the move (os.replace succeeded) but
        # crashed/died before removing the original directory. Don't
        # re-archive (dest_dir already exists, so os.replace would raise);
        # just finish the interrupted cleanup so the skill stops appearing
        # in both locations on every future run.
        shutil.rmtree(skill.path.parent)
        return dest_dir / "SKILL.md"
    tmp_dest = dest_dir.with_name(dest_dir.name + ".tmp-move")
    if tmp_dest.exists():
        shutil.rmtree(tmp_dest)
    shutil.copytree(skill.path.parent, tmp_dest)
    os.replace(tmp_dest, dest_dir)
    shutil.rmtree(skill.path.parent)
    return dest_dir / "SKILL.md"


def _load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"last_run_at": None, "run_count": 0, "paused": False}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_run_at": None, "run_count": 0, "paused": False}


def _save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def review(root: Path = SKILLS_ROOT, dry_run: bool = False, now: Optional[datetime] = None) -> CuratorReport:
    root = Path(root)
    now = now or _now()
    archive_root = root / "_archive"
    state_file = root / ".curator_state.json"
    report = CuratorReport(dry_run=dry_run)

    for skill in discover_skills(root=root):
        if not skill.agent_created or skill.pinned:
            continue
        report.reviewed += 1
        try:
            idle = _idle_days(skill, now)
            if idle >= ARCHIVE_AFTER_DAYS:
                report.archived.append(f"{skill.app}/{skill.name}")
                if not dry_run:
                    fm = dict(skill.raw_frontmatter)
                    fm["curator_status"] = "archived"
                    _write_frontmatter(skill.path, fm)
                    _archive_skill(skill, archive_root)
            elif idle >= STALE_AFTER_DAYS and skill.curator_status != "stale":
                report.staled.append(f"{skill.app}/{skill.name}")
                if not dry_run:
                    fm = dict(skill.raw_frontmatter)
                    fm["curator_status"] = "stale"
                    fm["confidence"] = max(0.0, skill.confidence * STALE_DECAY_FACTOR)
                    _write_frontmatter(skill.path, fm)
        except Exception as exc:
            report.errors.append(f"{skill.app}/{skill.name}: {exc}")

    if not dry_run:
        state = _load_state(state_file)
        state["last_run_at"] = now.isoformat()
        state["run_count"] = int(state.get("run_count", 0)) + 1
        _save_state(state_file, state)

    return report


def maybe_run_curator(root: Path = SKILLS_ROOT, now: Optional[datetime] = None) -> Optional[CuratorReport]:
    """Run review() only if not paused and INTERVAL_HOURS has elapsed since the last run."""
    root = Path(root)
    state_file = root / ".curator_state.json"
    state = _load_state(state_file)
    if state.get("paused"):
        return None
    now = now or _now()
    last_run_at = _parse_iso(state.get("last_run_at"))
    if last_run_at is not None and (now - last_run_at) < timedelta(hours=INTERVAL_HOURS):
        return None
    return review(root=root, now=now)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--review", action="store_true", help="run a curator review now, ignoring the interval")
    parser.add_argument("--dry-run", action="store_true", help="compute transitions without writing")
    args = parser.parse_args()

    if args.review or args.dry_run:
        r = review(dry_run=args.dry_run)
        print(f"[curator] reviewed={r.reviewed} staled={len(r.staled)} archived={len(r.archived)} errors={len(r.errors)}")
        for s in r.staled:
            print(f"  stale: {s}")
        for a in r.archived:
            print(f"  archived: {a}")
        for e in r.errors:
            print(f"  ERROR: {e}")
    else:
        parser.print_help()
