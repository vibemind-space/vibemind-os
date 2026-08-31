# Skill Curator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give VibeMind's `skills/` library idle-triggered lifecycle maintenance — usage tracking, staleness decay, and safe archival — scoped to only ever touch agent-created skills, never the ~350 existing human-curated ones.

**Architecture:** Four independent layers, each a separate task: (1) frontmatter schema + parser support for the new lifecycle fields, (2) usage-tracking hooks in the existing MCP skill-search/save handlers, (3) a standalone `_curator.py` module with pure, injectable-clock decay/archive logic, (4) a periodic OpenFang agent that invokes it via the runtime's real `[schedule]` cron mechanism.

**Tech Stack:** Python 3.11, PyYAML (already a dependency via `_loader.py`), pytest. OpenFang TOML agent config with `[schedule] periodic = { cron = "every Nd" }` (verified live in `openfang-kernel/src/background.rs::parse_cron_to_secs`, used today by `health-tracker`/`security-auditor`).

**Full design context:** `docs/superpowers/specs/2026-07-10-skill-curator-design.md` — read it before starting; this plan assumes its decisions (scope boundary, thresholds, non-goals) without re-explaining them.

**Deferred, not in this plan:** the spec's optional LLM-consolidation pass (merging near-duplicate skills) is explicitly out of scope here — it's the smallest, riskiest slice of the spec and is deferred to a follow-up plan once the deterministic path below has run in practice.

---

### Task 1: Frontmatter schema — `agent_created`, `last_searched`, `curator_status`, `pinned`

**Files:**
- Modify: `skills/_loader.py:24-78`
- Modify: `skills/README.md:61-84`
- Test: `skills/tests/test_loader.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `skills/tests/test_loader.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_loader.py -v`
Expected: FAIL — `AttributeError: 'Skill' object has no attribute 'agent_created'` (first two tests); third test passes already (it characterizes pre-existing `discover_skills` behavior, not new code — confirms the archive-hiding assumption before Task 3 depends on it).

- [ ] **Step 3: Extend the `Skill` dataclass and parser**

In `skills/_loader.py`, replace lines 24-40 (the `Skill` dataclass):

```python
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
```

Then replace lines 50-78 (`parse_skill_file`) with:

```python
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
```

(This factors the repeated `hasattr(..., "isoformat")` check into a local helper, used for both `last_adjusted` and the new `last_searched`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_loader.py -v`
Expected: 3 passed

- [ ] **Step 5: Update the frontmatter contract docs**

In `skills/README.md`, replace the table row block at lines 71-73:

```markdown
| `confidence` | float 0..1 | success rate, updated by coordinator |
| `attempts` / `successes` | int | counters |
| `last_adjusted` | iso8601 \| null | timestamp of last adjustment |
```

with:

```markdown
| `confidence` | float 0..1 | success rate, updated by coordinator |
| `attempts` / `successes` | int | counters |
| `last_adjusted` | iso8601 \| null | timestamp of last adjustment |
| `agent_created` | bool | set server-side by `_skill_save_and_index` when the file is first written; never trust a caller-supplied value. Human-curated skills are `false`. |
| `last_searched` | iso8601 \| null | updated on every `skill_search` hit; drives curator idle-time decay |
| `curator_status` | `active` \| `stale` \| `archived` | lifecycle state written by `_curator.py` |
| `pinned` | bool | exempts an `agent_created` skill from curator decay/archival |
```

And replace line 84 (the "Decay" lifecycle step, which currently documents behavior that was never implemented) with:

```markdown
6. **Decay** — `_curator.py` reviews `agent_created && !pinned` skills on a schedule: unused for `VIBEMIND_CURATOR_STALE_DAYS` (default 30) → `curator_status: stale` + one-time confidence decay; unused for `VIBEMIND_CURATOR_ARCHIVE_DAYS` (default 90) → moved under `skills/_archive/<app>/<skill_name>/` (never deleted). Human-curated skills (`agent_created: false`, the default) are never touched. See `docs/superpowers/specs/2026-07-10-skill-curator-design.md`.
```

- [ ] **Step 6: Commit**

```bash
git add skills/_loader.py skills/README.md skills/tests/test_loader.py
git commit -m "feat(skills): add curator lifecycle fields to Skill frontmatter schema"
```

---

### Task 2: Usage-tracking hooks in the MCP skill handlers

**Files:**
- Modify: `spaces/desktop/Automation_ui/backend/moire_agents/mcp_server_handoff.py:3992-4114`
- Test: `spaces/desktop/Automation_ui/backend/moire_agents/tests/test_skill_curator_hooks.py` (new)

**Context for the implementer:** `mcp_server_handoff.py` is a 5678-line file with heavy top-level imports (vision/ML stack) — importing it takes ~8s but succeeds. `_SKILL_LIB_ROOT` (line 106) is a **hardcoded absolute path** to the real production skills directory (`C:\Users\User\Desktop\Vibemind_V1\vibemind-os\skills`). Tests **must** monkeypatch `mcp_server_handoff._SKILL_LIB_ROOT` to a `tmp_path` before calling any of these functions — never let a test run against the real path, it would write real `attempts`/`last_searched` values into real skill files.

- [ ] **Step 1: Write the failing tests**

Create `spaces/desktop/Automation_ui/backend/moire_agents/tests/test_skill_curator_hooks.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcp_server_handoff as h  # noqa: E402


def _write_skill(root, app, name, frontmatter_extra="", body="Body text.\n"):
    skill_dir = os.path.join(root, app, name)
    os.makedirs(skill_dir, exist_ok=True)
    path = os.path.join(skill_dir, "SKILL.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            f"name: {name}\n"
            "description: a searchable test skill\n"
            f"{frontmatter_extra}"
            "---\n\n"
            f"{body}"
        )
    return path


def test_skill_search_bumps_attempts_and_last_searched(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_SKILL_LIB_ROOT", str(tmp_path))
    path = _write_skill(tmp_path, "testapp", "searchable-skill", frontmatter_extra="attempts: 0\n")

    result = h._skill_search("searchable")

    assert result["success"] is True
    assert len(result["results"]) == 1
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "attempts: 1" in text
    assert "last_searched:" in text


def test_skill_search_no_match_does_not_touch_file(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_SKILL_LIB_ROOT", str(tmp_path))
    path = _write_skill(tmp_path, "testapp", "unrelated-skill", frontmatter_extra="attempts: 0\n")

    result = h._skill_search("nonexistent-query-xyz")

    assert result["results"] == []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "attempts: 0" in text
    assert "last_searched" not in text


def test_skill_save_and_index_new_skill_gets_curator_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_SKILL_LIB_ROOT", str(tmp_path))

    result = h._skill_save_and_index(
        "testapp", "new-skill", {"name": "new-skill", "description": "d"}, "Body\n"
    )

    assert result["success"] is True
    with open(result["path"], "r", encoding="utf-8") as f:
        text = f.read()
    assert "agent_created: true" in text
    assert "attempts: 0" in text
    assert "curator_status: active" in text
    assert "pinned: false" in text


def test_skill_save_and_index_existing_file_not_flipped_to_agent_created(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_SKILL_LIB_ROOT", str(tmp_path))
    _write_skill(tmp_path, "testapp", "human-skill", frontmatter_extra="agent_created: false\n")

    result = h._skill_save_and_index(
        "testapp", "human-skill", {"name": "human-skill", "description": "edited"}, "New body\n"
    )

    assert result["success"] is True
    with open(result["path"], "r", encoding="utf-8") as f:
        text = f.read()
    # Pass-through behavior for edits to an existing file is unchanged:
    # only whatever the caller supplied is written, no defaults injected.
    assert "agent_created" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd spaces/desktop/Automation_ui/backend/moire_agents && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_skill_curator_hooks.py -v`
Expected: FAIL — `_bump_skill_usage`/defaults not implemented yet; first two tests fail on missing `attempts: 1`/wrong content, `test_skill_save_and_index_new_skill_gets_curator_defaults` fails on missing `agent_created: true`.

- [ ] **Step 3: Add the usage-bump helper**

In `mcp_server_handoff.py`, insert this new function immediately after `_read_skill_meta` ends (after line 3992, before `def _skill_search`):

```python
def _bump_skill_usage(path: str) -> bool:
    """Best-effort: increment ``attempts`` and set ``last_searched`` to now in
    an existing SKILL.md's frontmatter.

    Dependency-light (no external YAML lib, matching ``_read_skill_meta``'s
    style). Never raises — returns False on any failure so callers like
    ``_skill_search`` can safely ignore tracking failures without affecting
    the actual search response.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.startswith("---"):
            return False
        end = text.find("\n---", 3)
        if end == -1:
            return False
        fm_lines = text[3:end].splitlines()
        rest = text[end:]

        found_attempts = False
        found_last_searched = False
        new_lines = []
        for line in fm_lines:
            stripped = line.strip()
            if stripped.lower().startswith("attempts:"):
                try:
                    attempts = int(stripped.split(":", 1)[1].strip())
                except ValueError:
                    attempts = 0
                new_lines.append(f"attempts: {attempts + 1}")
                found_attempts = True
            elif stripped.lower().startswith("last_searched:"):
                new_lines.append(f'last_searched: "{datetime.utcnow().isoformat()}"')
                found_last_searched = True
            else:
                new_lines.append(line)
        if not found_attempts:
            new_lines.append("attempts: 1")
        if not found_last_searched:
            new_lines.append(f'last_searched: "{datetime.utcnow().isoformat()}"')

        new_text = "---" + "\n".join(new_lines) + rest
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
        return True
    except Exception as e:
        logger.error(f"_bump_skill_usage failed for {path}: {e}")
        return False
```

(`new_lines[0]` is an empty string — `text[3:end]` starts at the `\n` right after the opening `---`, so `splitlines()`'s first element is `""`. Joining with `"\n"` already supplies that newline; prepending `"---\n"` instead of `"---"` would double it, and since the empty first element is preserved every call, it would compound by one blank line per bump.)

- [ ] **Step 4: Wire the bump into `_skill_search`**

In `_skill_search`, replace the last 5 lines of the function body (currently):

```python
        results.sort(key=lambda r: r["score"], reverse=True)
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 5
        return {"success": True, "results": results[: max(0, lim)]}
```

with:

```python
        results.sort(key=lambda r: r["score"], reverse=True)
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 5
        top_results = results[: max(0, lim)]
        for r in top_results:
            _bump_skill_usage(r["path"])
        return {"success": True, "results": top_results}
```

- [ ] **Step 5: Inject curator defaults into `_skill_save_and_index` for new skills**

In `_skill_save_and_index`, insert this block right after the `path = os.path.join(skill_dir, "SKILL.md")` line and before the `def _yaml_scalar(v)` local function definition:

```python
        frontmatter = dict(frontmatter or {})
        if not os.path.exists(path):
            # New skill: mark it agent-created and seed curator bookkeeping
            # fields server-side — never trust the caller-supplied dict for
            # this. See docs/superpowers/specs/2026-07-10-skill-curator-design.md.
            frontmatter["agent_created"] = True  # unconditional: never let a caller-supplied False win
            frontmatter.setdefault("attempts", 0)
            frontmatter.setdefault("curator_status", "active")
            frontmatter.setdefault("last_searched", None)
            frontmatter.setdefault("pinned", False)
```

The existing loop two lines below (`for k, v in (frontmatter or {}).items():`) already uses the local `frontmatter` variable, so it picks up these defaults automatically — change that line to `for k, v in frontmatter.items():` (drop the now-redundant `or {}`, since `frontmatter` is now always a dict from the line above).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd spaces/desktop/Automation_ui/backend/moire_agents && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_skill_curator_hooks.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add spaces/desktop/Automation_ui/backend/moire_agents/mcp_server_handoff.py spaces/desktop/Automation_ui/backend/moire_agents/tests/test_skill_curator_hooks.py
git commit -m "feat(skills): track skill_search hits and seed curator defaults on new skills"
```

*(Note: `spaces/desktop/Automation_ui` is a nested git submodule inside `vibemind-os` — this commit happens in the submodule's own repo. `finishing-a-development-branch` at the end of the plan must account for committing/pushing the submodule separately from the parent `vibemind-os` branch.)*

---

### Task 3: `skills/_curator.py` — decay and archive review

**Files:**
- Create: `skills/_curator.py`
- Test: `skills/tests/test_curator.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `skills/tests/test_curator.py`:

```python
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


def test_maybe_run_curator_runs_again_after_interval(tmp_path):
    _write_skill(
        tmp_path, "app1", "idle-skill", agent_created=True,
        last_searched=(NOW - timedelta(days=45)).isoformat(),
    )
    first = maybe_run_curator(root=tmp_path, now=NOW)
    assert first is not None

    second = maybe_run_curator(root=tmp_path, now=NOW + timedelta(hours=169))
    assert second is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_curator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_curator'`

- [ ] **Step 3: Implement `skills/_curator.py`**

Create `skills/_curator.py`:

```python
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
    match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    original_body = match.group(2) if match else ""
    new_text = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip("\n") + "\n---\n" + original_body
    path.write_text(new_text, encoding="utf-8")


def _archive_skill(skill: Skill, archive_root: Path) -> Path:
    dest_dir = archive_root / skill.app / skill.name
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if (dest_dir / "SKILL.md").exists():
        # A prior run already completed the move but crashed before cleaning
        # up the original — finish the cleanup instead of re-archiving
        # (os.replace below would otherwise raise on an existing dest_dir).
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -m pytest tests/test_curator.py -v`
Expected: 9 passed

- [ ] **Step 5: Dry-run smoke test against the real skills tree**

Run: `cd skills && "/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" _curator.py --dry-run`
Expected: `[curator] reviewed=0 staled=0 archived=0 errors=0` — today, zero skills have `agent_created: true`, so this proves the scope boundary holds against the real, unmodified `skills/` tree. If `reviewed` is not 0, stop and investigate before proceeding (it means some existing skill unexpectedly already has `agent_created: true` — do not archive/decay it blindly).

- [ ] **Step 6: Commit**

```bash
git add skills/_curator.py skills/tests/test_curator.py
git commit -m "feat(skills): add idle-triggered curator for agent-created skill lifecycle"
```

---

### Task 4: Periodic OpenFang agent registration

**Files:**
- Create: `openfang/agents/skill-curator/agent.toml`

**Context for the implementer:** OpenFang's `[schedule]` table with `periodic = { cron = "every Nd" }` is the **live, working** trigger mechanism — verified in `openfang-kernel/src/background.rs::parse_cron_to_secs` (supports `s`/`m`/`h`/`d` suffixes) and already used by `openfang/agents/health-tracker/agent.toml` and `openfang/agents/security-auditor/agent.toml`. Do **not** use the pattern from `scripts/openfang_error_monitor_register.ps1` (a `/api/cron/jobs` REST-registration script) — that mechanism exists but is never actually invoked anywhere in the repo (confirmed dormant), which is exactly the failure mode this task must avoid repeating.

- [ ] **Step 1: Create the agent config**

Create `openfang/agents/skill-curator/agent.toml`:

```toml
name = "skill-curator"
version = "0.1.0"
description = "Idle-triggered lifecycle maintenance for agent-created SKILL.md files: decays stale skills, archives unused ones. Never touches human-curated skills."
author = "vibemind"
module = "builtin:chat"
tags = ["monitoring", "vibemind", "self-healing", "skills"]

[model]
provider = "ollama"
model = "qwen2.5-coder:7b"
max_tokens = 4096
temperature = 0.1
system_prompt = """You are Skill-Curator, an autonomous maintenance agent for VibeMind's adaptive skill library.

Your job: every run, invoke the curator review script and report what it did.

WORKFLOW:
1. Run: `python C:\\Users\\User\\Desktop\\Vibemind_V1\\vibemind-os\\skills\\_curator.py --review`
2. Read its stdout — it prints one summary line (`[curator] reviewed=N staled=N archived=N errors=N`) followed by one line per transition.
3. Call `memory_store` with a short summary of the run (reviewed/staled/archived/errors counts) so there's an audit trail across runs.
4. If `errors > 0`, include the error lines verbatim in your summary — do not paraphrase or drop them.

RULES:
- Never modify SKILL.md files directly yourself — only the script does that.
- Never call the script with any flag other than `--review` (never `--dry-run` on the real schedule; `--dry-run` is for manual debugging only).
- If the script fails to run at all (non-zero exit, exception), report that clearly rather than inventing a result."""

[schedule]
periodic = { cron = "every 7d" }

[resources]
max_llm_tokens_per_hour = 20000
max_concurrent_tools = 3

[capabilities]
tools = ["shell_exec", "memory_store", "memory_recall"]
memory_read = ["self.*"]
memory_write = ["self.*"]
# Only the curator script itself is needed.
shell = ["python C:\\Users\\User\\Desktop\\Vibemind_V1\\vibemind-os\\skills\\_curator.py *"]
```

- [ ] **Step 2: Verify the TOML parses**

Run: `"/c/Users/User/Desktop/Vibemind_V1/.venv/Scripts/python.exe" -c "import tomllib; tomllib.load(open('openfang/agents/skill-curator/agent.toml', 'rb')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add openfang/agents/skill-curator/agent.toml
git commit -m "feat(openfang): register skill-curator as a weekly periodic agent"
```

*(Note: `openfang` is a nested git submodule inside `vibemind-os`, same caveat as Task 2 — commit happens in the submodule's own repo.)*

---

## After all tasks

Dispatch a final code reviewer subagent for the entire diff across all three repos touched (`vibemind-os` for Tasks 1/3, the `Automation_ui` submodule for Task 2, the `openfang` submodule for Task 4), then use `superpowers:finishing-a-development-branch` — paying attention to the fact that this spans a parent worktree plus two nested submodules, each with its own branch/commit to reconcile.

## Post-implementation fixes found by final cross-repo review

The final holistic review (checking integration between repos, which per-task review in isolation couldn't see) found 2 more bugs in Task 2's `_skill_save_and_index`/`_yaml_scalar` in `mcp_server_handoff.py`, fixed in a follow-up commit on top of Task 2's original + first-fix commits:

1. `_yaml_scalar(None)` had no `None` branch, so `last_searched: None` (the literal word, not YAML's `null`) was written for every new agent-created skill — PyYAML parses that back as the Python string `"None"`, not `NoneType`. Fix: added `if v is None: return "null"` as `_yaml_scalar`'s first branch.
2. Editing an existing skill via `_skill_save_and_index` only wrote whatever frontmatter dict the caller supplied, with no merge against the file's existing frontmatter — so re-editing an agent-created skill without re-supplying `agent_created`/`attempts`/`curator_status`/`last_searched`/`pinned` silently dropped them, defaulting `agent_created` back to `false` on next parse and permanently exiting that skill from curator management. Fix: added a `_read_curator_fields(path)` helper (dependency-light, same style as `_bump_skill_usage`) and an `else` branch in `_skill_save_and_index` that preserves any of the 5 curator fields the caller didn't explicitly resupply.

See the actual commit in the `Automation_ui` submodule for the exact diff — this section is a pointer for anyone reading this plan after the fact, not a repeat of the full code.
