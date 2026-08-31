# Skill Curator — Design Spec

## Purpose

VibeMind's Adaptive Skills System (`skills/`) has no lifecycle maintenance: `SKILL.md` frontmatter already declares `confidence`, `attempts`, `successes`, `last_adjusted` fields, but nothing writes to them. Skills accumulate forever; nothing ever gets flagged stale or archived. This spec ports the one genuinely non-redundant idea found in a comparison against `hermes-agent`'s skill system (see project memory `project_hermes_skill_writer_comparison`): an idle-triggered background **curator** that decays and archives skills based on real usage, without requiring a human to remember to clean up.

This is scoped narrowly. It does **not** port hermes-agent's skill-authoring flow (VibeMind already has an equivalent via `_skill_save_and_index`), its multi-platform gateway, or its memory system.

## Scope boundary (safety-critical)

The curator only ever touches skills where `agent_created: true`. VibeMind's ~350 existing skills (bundled science/office/devops skills, imports) are 100% human/import-curated and are **never** touched by the curator, regardless of usage. This mirrors hermes-agent's own invariant ("only touches agent-created skills"). The curator has near-zero effect today and grows in relevance as the agent creates more of its own skills via `_skill_save_and_index`.

## Components

### 1. Frontmatter additions (`skills/_loader.py`)

Add to the `Skill` dataclass and to the frontmatter contract documented in `skills/README.md`:

- `agent_created: bool` (default `false`) — set server-side only, never trusted from caller-supplied frontmatter dicts.
- `last_searched: str | None` (ISO-8601, default `null`) — updated on every `skill_search` hit. Distinct from `last_adjusted`, which continues to mean "last edited."
- `curator_status: "active" | "stale" | "archived"` (default `"active"`).
- `pinned: bool` (default `false`) — escape hatch that exempts a skill from curator transitions even if `agent_created: true`.

`attempts` and `successes` already exist in the dataclass and keep their current types. `successes` stays unpopulated in this iteration (see "Non-goals").

### 2. Usage tracking (`spaces/desktop/Automation_ui/backend/moire_agents/mcp_server_handoff.py`)

- `_skill_search`: for every result actually returned to the caller (post `limit` truncation), best-effort increment `attempts` and set `last_searched = now()` in that skill's `SKILL.md` frontmatter. Failures to write (e.g. locked file) are logged and swallowed — a tracking write must never fail the search itself.
- `_skill_save_and_index`: when writing a **new** `SKILL.md` (path does not already exist), inject `agent_created: true`, `attempts: 0`, `curator_status: "active"`, `last_searched: null`, `pinned: false` into the frontmatter dict server-side if the caller didn't already supply them. If the path already exists (an edit to a skill that already has `agent_created: false`, i.e. a human-curated skill being edited by an agent), do **not** flip `agent_created` to `true` — editing a human skill doesn't make it agent-owned.

### 3. `skills/_curator.py` (new module)

```python
review(dry_run: bool = False) -> CuratorReport
```

- Iterates `discover_skills()`, filters to `agent_created == True and pinned == False`.
- For each: compute `idle_days = now - (last_searched or file_mtime)`.
  - `idle_days >= ARCHIVE_AFTER_DAYS` (default 90): move the skill directory to `skills/<app>/_archive/<skill_name>/` (atomic: write to temp path, then `os.replace`), set `curator_status: "archived"`. Never delete.
  - `idle_days >= STALE_AFTER_DAYS` (default 30): set `curator_status: "stale"`, multiply `confidence` by a fixed `STALE_DECAY_FACTOR` (default `0.7`), floored at `0.0`. Applied once per transition into `stale` (re-running `review()` while already `stale` does not re-multiply).
  - Otherwise: leave as `active`.
- All thresholds are env-overridable (`VIBEMIND_CURATOR_STALE_DAYS`, `VIBEMIND_CURATOR_ARCHIVE_DAYS`, `VIBEMIND_CURATOR_INTERVAL_HOURS`, default interval 168h/weekly).
- Per-skill processing wrapped in try/except — a parse error on one skill logs and continues, never aborts the run.
- Persists run metadata to `skills/.curator_state.json`: `last_run_at`, `run_count`, `paused`.
- `dry_run=True` computes and logs intended transitions without writing anything (used for the smoke test and for manual invocation).

**Consolidation (optional, off by default):** if `VIBEMIND_CURATOR_CONSOLIDATE=true`, after the deterministic pass, spawn one LLM review pass (existing agent-dispatch mechanism, not a new one) that reads all `active`/`stale` agent-created skills and proposes merges of near-duplicates. This **writes a report only** (`skills/.curator_reports/<timestamp>.md`) — it never auto-applies a merge, matching the existing `autoskill` promote-gate precedent. This is the smallest slice of scope; if it adds risk during implementation, it can be deferred to a follow-up spec.

### 4. Trigger: periodic OpenFang agent

A new `skill-curator` OpenFang agent, config-registered the same way as the existing Error-Monitor agent (periodic, not a long-lived process). Default cadence: every `VIBEMIND_CURATOR_INTERVAL_HOURS` (168h). Its job body is exactly: call `skills/_curator.py`'s `review()`, log the resulting `CuratorReport` (counts: reviewed / staled / archived / errors).

This spec does **not** cover writing the OpenFang agent *registration* itself in exhaustive detail (exact YAML/JSON shape) — that's an implementation-plan-level task once the existing Error-Monitor agent's registration is read as a template.

## Non-goals (explicitly out of scope for this iteration)

- `successes` tracking. There is no ground-truth signal for "the skill actually worked" without either self-report (rejected — violates the project's standing `feedback_always_real_signals` rule) or a user-confirmation flow (noted by the user as a future direction, possibly voice-based). The curator's decay logic uses only `attempts`/`last_searched`, not success rate.
- Touching any of the ~350 existing human-curated skills.
- Auto-applying LLM-proposed consolidations.
- Building a new scheduler/cron mechanism — reuses the existing periodic-agent pattern.

## Testing

- Unit tests for `_curator.py`'s pure decay/archive threshold functions, with `now` injected (no real-clock dependency).
- Fixture-based test: temp `skills/` directory with synthetic old/new/pinned/human-curated `SKILL.md` files; assert only the intended agent-created+unpinned+stale ones transition, and human-curated ones are never touched.
- Fixture-based test: archive move is atomic and reversible (file still readable at new path, original path gone, content unchanged).
- Manual dry-run smoke test against the real `skills/` tree: expected result is 0 transitions today (no agent-created skills exist yet), proving the scope boundary holds in practice.
- Unit tests for the new `_skill_search`/`_skill_save_and_index` frontmatter-injection behavior in `mcp_server_handoff.py` (new skill gets the new fields; editing an existing human skill does not flip `agent_created`).

## Error handling

- Curator run: never crash the periodic agent, never delete a file, never touch a skill outside the `agent_created && !pinned` filter.
- Usage-tracking write-back in `_skill_search`: best-effort, logged, never blocks/fails the search response.
- Archive move: atomic (temp + `os.replace`), so a crash mid-move can't leave a half-moved skill.
