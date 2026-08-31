# VibeMind Adaptive Skill Library

App-specific desktop-automation skills, indexed semantically in Qdrant and selected by a coordinator agent.

**📊 [Full catalog: INDEX.md](INDEX.md)** — 278 skills across 21 namespaces (auto-generated).

## Use as a git submodule

```bash
# In any other VibeMind-compatible project
git submodule add https://github.com/Flissel/Vibemind_V1.git vibemind  # full monorepo
# OR pin only the skills directory using sparse-checkout

# Then point your loader / coordinator at <repo>/vibemind-os/skills/
```

The skill format (`name`, `description` + body) is **compatible** with
[Anthropic Claude Skills](https://github.com/anthropics/skills), so any
loader that consumes that format will also accept these skills.

## Importing more skills from the community

```bash
# Install any skill pack listed in awesome-claude-skills
python scripts/install_skill_pack.py \
  --repo https://github.com/<owner>/<pack> \
  --app <your-namespace>

# Re-index Qdrant after import
QDRANT_URL=http://localhost:6730 \
  python vibemind-os/skills/_indexer.py --rebuild

# Refresh the human-readable catalog
python scripts/generate_skill_catalog.py
```

Bidirectional format conversion (between vibemind, anthropic, and OpenClaw
formats) is in `scripts/skill_format_bridge.py`.

## Layout

```
skills/
  excel/
    fill-cell/SKILL.md
    select-range/SKILL.md
    ...
  word/
  file-explorer/
  vscode/
  claude-desktop/
  chrome/
  _loader.py        # parses SKILL.md frontmatter + body
  _indexer.py       # syncs to Qdrant collection 'vibemind_skills'
```

## SKILL.md format

YAML frontmatter + Markdown body. Required fields:

| Field | Type | Purpose |
|---|---|---|
| `name` | string | unique slug (`<app>-<verb>-<noun>`) |
| `description` | string | one-line, used as embedding source |
| `app` | string | `excel`, `word`, etc. |
| `agents` | list | which agents may load this skill (`desktop`, `openclaude`, `*`) |
| `trigger` | string (regex) | natural-language phrases that should activate the skill |
| `inputs` | list | named args the skill expects (cell, value, …) |
| `expected_state` | object | `{description, verification_tool}` for the validator |
| `secrets` | list | optional credential prompts (see Secrets section) |
| `confidence` | float 0..1 | success rate, updated by coordinator |
| `attempts` / `successes` | int | counters |
| `last_adjusted` | iso8601 \| null | timestamp of last adjustment |
| `agent_created` | bool | set server-side by `_skill_save_and_index` when the file is first written; never trust a caller-supplied value. Human-curated skills are `false`. |
| `last_searched` | iso8601 \| null | updated on every `skill_search` hit; drives curator idle-time decay |
| `curator_status` | `active` \| `stale` \| `archived` | lifecycle state written by `_curator.py` |
| `pinned` | bool | exempts an `agent_created` skill from curator decay/archival |

The Markdown body holds the **steps** — sequential instructions that the executor LLM follows to perform the action via desktop-automation MCP tools (`handoff_action`, `handoff_get_focus`, `vision_analyze`, etc.).

## Lifecycle

1. **Manual seed** — write SKILL.md by hand for the most common app interactions.
2. **Indexer** — `python _indexer.py --rebuild` embeds every SKILL.md into Qdrant.
3. **Selection** — Skill-Coordinator queries Qdrant with the user's natural-language request, gets top-K candidates filtered by `agents` whitelist.
4. **Execution** — selected SKILL.md is injected into the executor agent's prompt, the agent runs the steps via MCP.
5. **Validation** — coordinator runs `vision_analyze` against `expected_state.description`; success=True → increment `successes`, recompute `confidence`. Failure → diagnose + adjust + retry.
6. **Decay** — `_curator.py` reviews `agent_created && !pinned` skills on a schedule: unused for `VIBEMIND_CURATOR_STALE_DAYS` (default 30) → `curator_status: stale` + one-time confidence decay; unused for `VIBEMIND_CURATOR_ARCHIVE_DAYS` (default 90) → moved under `skills/_archive/<app>/<skill_name>/` (never deleted). Human-curated skills (`agent_created: false`, the default) are never touched. See `docs/superpowers/specs/2026-07-10-skill-curator-design.md`.

## Secrets

If a skill needs credentials, declare them in frontmatter:

```yaml
secrets:
  - credential_id: github_pat
    form_schema:
      - {name: token, label: "GitHub PAT", type: password, required: true}
```

The skill-runner calls `handoff_clarify` with `form_schema=…`, which renders an HTML form on `http://localhost:8007/api/clarify/<id>/form`. After the user submits, the value is stored encrypted via Windows DPAPI; the skill receives only an opaque token (`{{secret:github_pat}}`) that resolves at run-time.
