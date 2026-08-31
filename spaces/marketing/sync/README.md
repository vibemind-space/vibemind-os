# Marketing Sync — Worker Lifecycle

Bi-directional sync between Supabase `marketing.*` and `~/.rowboat/knowledge/Marketing/People/` markdown files.

## Components

| File | Role |
|---|---|
| `render_md.py` | Pure-function renderer: handle → markdown string |
| `worker_db_to_fs.py` | Worker A: drains `marketing.sync_outbox`, writes .md files |
| `worker_fs_to_db.py` | Worker B: watches vault folder, propagates deletes to DB |
| `_db.py` | Postgres access via `docker exec psql` |
| `_queries.py` | Single big JSON-aggregating query per render |
| `_frontmatter.py` | Deterministic YAML serialiser + parser |
| `_filename.py` | Handle → safe `.md` filename |

DB-side:
- `marketing.sync_outbox` table (append-only event log)
- `marketing.emit_sync_event()` trigger function on all 12 marketing tables
- `marketing._resolve_handle()` mapper
- `marketing.mark_outbox_applied()` worker callback
- Session GUC `marketing.sync_origin` for loop-prevention

## Run

```bash
# Worker A — drain outbox, render files
PYTHONIOENCODING=utf-8 python -m spaces.marketing.sync.worker_db_to_fs

# Worker B — watch vault, propagate deletes
PYTHONIOENCODING=utf-8 python -m spaces.marketing.sync.worker_fs_to_db
```

Both should be running side-by-side. Worker A polls outbox every 5 s by default (fallback for LISTEN/NOTIFY). Worker B uses `watchdog` for inotify-based live events.

Stop with `Ctrl-C`.

## One-shot ops

```bash
# Render a single handle to stdout
python -m spaces.marketing.sync.render_md --handle kennethharris

# Render all 14k handles to a test dir (~80 min via docker-exec)
python -m spaces.marketing.sync.render_md --all --output-dir /tmp/render-all-test

# Drain outbox once and exit (useful after batch DB inserts)
python -m spaces.marketing.sync.worker_db_to_fs --once
```

## Environment

| Var | Default |
|---|---|
| `MARKETING_VAULT_DIR` | `~/.rowboat/knowledge/Marketing/People/` |
| `MARKETING_HASH_STORE` | `~/.rowboat/knowledge/Marketing/.sync_hashes.json` |
| `MARKETING_POLL_SEC` | `30` (Worker A poll-fallback) |
| `MARKETING_FS_POLL_SEC` | `5` (Worker B polling-mode fallback) |
| `MARKETING_STALE_DAYS` | `90` (last_engagement_at threshold for "_stale_") |

## Verification

```bash
# Snapshot tests
PYTHONIOENCODING=utf-8 python -m spaces.marketing.sync.tests.test_render_md

# End-to-end roundtrip (INSERT → render → UPDATE → re-render → DELETE → rm → DB-delete → loop check)
PYTHONIOENCODING=utf-8 python -m spaces.marketing.sync.tests.test_e2e
```

Expected: 9/9 snapshot tests, 14/14 E2E checks.

## Architecture decisions

- **Push-not-Pull for all tables.** Every marketing.* INSERT/UPDATE/DELETE emits an outbox row. Write-amplification is acceptable; loopback-block on Postfix caps the realistic write rate.
- **Loop prevention via session GUC.** Worker B sets `marketing.sync_origin = 'fs'` before its DELETE; the trigger checks and skips outbox emit. No echo back to Worker A.
- **Content-hash echo prevention.** Worker A stores SHA256 of every file it writes in `.sync_hashes.json`. Worker B compares each incoming file event against that store: identical = own echo, ignore.
- **Phase-1 Worker B = delete-only.** File modifications are logged but NOT propagated to DB. Felix can edit the body section (below the user-fence) freely; that content stays file-only.
- **Cascade-delete:** `marketing.accounts` deletion fans out via FK CASCADE to emails/email_tags/audience_members/etc. Worker A removes the .md on `accounts DELETE`; downstream emails are not separately rendered (orphans were already gone with the parent file).

## Known limitations (Phase 1)

- **Fan-out events** (`affected_handle = NULL` in outbox) — happens when tags/audiences/campaigns/templates change. Worker A skips them silently. Phase 2 should resolve to per-handle events.
- **docker-exec is slow** (~150 ms/render). For production move to long-lived `psycopg.Connection` with real `LISTEN`. Currently sufficient for dev volumes.
- **No frontmatter-edit propagation.** Felix-edited frontmatter is logged as a warning and ignored. Phase 2 could allow specific fields (tags, notes) to flow back.
- **Race**: simultaneous DB INSERT + FS rm of the same handle = one of them wins arbitrarily. Real conflict resolution would need versioning + CRDT-style merges. Phase 1 just guarantees no loop.

## Worker auto-start

Not yet wired into `Vibemind.debug.ps1`. To run permanently:

```bash
# Linux/macOS
nohup python -m spaces.marketing.sync.worker_db_to_fs >/tmp/worker_a.log 2>&1 &
nohup python -m spaces.marketing.sync.worker_fs_to_db >/tmp/worker_b.log 2>&1 &

# Windows / PowerShell
Start-Process -WindowStyle Hidden python -ArgumentList "-m","spaces.marketing.sync.worker_db_to_fs"
Start-Process -WindowStyle Hidden python -ArgumentList "-m","spaces.marketing.sync.worker_fs_to_db"
```

Future: launcher integration as background processes (analogous to `openfang_debugger_launch.py`).
