# Phase 2 Plan — Markdown-Renderer

**Status:** Plan-Phase. Kein Code, nur Design. Felix-review vor Implementation.

## Context

Phase 1 ist durch: pathx → Supabase mit 14.742 accounts + 350 emails + 9.297 strategies + 14 runs. Alle emails `consent_given_at=NULL`, `investor_already_sent=false`. RLS Phase-1 lockt anon+authenticated aus, nur service_role kommt rein.

Phase 2 baut die **read-only Pull-Komponente** des Sync-Systems: eine pure Funktion `render_person_md(handle) -> markdown_str`. Sie hat keine Side-Effects, keine FS-Writes, keine DB-Mutations — sie nimmt einen handle und liefert den ge-renderten Markdown-Content als String zurück.

Die Funktion wird später (Phase 4) vom Sync-Worker A aufgerufen und das Ergebnis aufs Filesystem geschrieben. In Phase 2 testen wir nur den Renderer isoliert mit Snapshot-Tests.

## Outcome

Eine Python-Funktion `render_person_md(supa_conn, handle: str) -> str` die für jeden der 14.742 imported pathx-Accounts ein deterministisches, voll-renderbares Markdown-File liefert. Plus eine `--dry-run` CLI-Schnittstelle:

```
python spaces/marketing/sync/render_md.py --handle kennethharris
python spaces/marketing/sync/render_md.py --all --output-dir /tmp/render-test  # nur für Test
python spaces/marketing/sync/render_md.py --diff <handle>  # vergleicht live vs file
```

**Voll-render heißt:** alle Joins gegen `marketing.*` Tabellen aufgelöst. Frontmatter strukturiert + maschinenlesbar. Body human-lesbar.

## Output-Spec — exaktes Markdown-Format

```
---
sync_id: 7f3a8b2c-1234-5678-90ab-cdef01234567
sync_version: 1
sync_source: supabase
sync_path: marketing.accounts/{handle}
last_synced_at: 2026-06-02T11:45:00+00:00

handle: kennethharris
display_name: Kenneth Harris
niche: US
source: namegen
followers: 0
created_at: 2026-03-31T13:10:06+00:00

primary_email: hkenneth@gmail.com
all_emails:
  - email: hkenneth@gmail.com
    confidence: 0.95
    mx_valid: true
    smtp_valid: 1
    domain: gmail.com
    country: US
    catch_all: false
    consent_given_at: null
    consent_source: pathfinder-import-no-consent
    unsubscribed_at: null
    bounce_count: 0
    last_engagement_at: null
    investor_already_sent: false

tags: []

audience_memberships: []

send_history_count: 0
last_send_at: null
last_open_at: null
last_click_at: null
last_reply_at: null

inbound_count: 0
last_inbound_at: null
---

# Kenneth Harris

**Handle:** `kennethharris`
**Region:** US
**Source:** namegen (pathfinder-import-no-consent)
**Followers:** 0
**Created:** 2026-03-31

## Emails

| Email | Confidence | MX | SMTP | Consent | Last Engagement | Lockout |
|---|---:|:-:|:-:|---|---|:-:|
| hkenneth@gmail.com | 0.95 | ✓ | OK | _none_ | — | _open_ |

## Tags

_None._

## Audience Memberships

_Not in any audience._

## Send History

_No campaigns sent to this person yet._

## Reply History

_No inbound messages._

## Strategies that Generated This Person

| Strategy ID | Pattern | Domain | Fitness | Successes |
|---|---|---|---:|---:|
| email_0007 | `<firstinitial><lastname>@<domain>` | gmail.com | 0.95 | 268 |

---

<!-- ──────────────────────────────────────────────────────────────────── -->
<!-- Custom notes below this line.                                         -->
<!-- Everything BELOW this fence is owned by the user and will NOT be      -->
<!-- overwritten by the sync worker. Frontmatter and sections ABOVE        -->
<!-- this fence are DB-rendered and re-generated on every sync.            -->
<!-- ──────────────────────────────────────────────────────────────────── -->
```

## Why YAML frontmatter, not JSON

- Obsidian + Foam + Logseq + most knowledge-vault tools parse YAML frontmatter natively → Felix kann die Profile in seinem bevorzugten Tool öffnen
- Multi-line lists (`all_emails:`, `audience_memberships:`) lesbarer als JSON
- Comments möglich (`# Auto-generated. ...`)
- Diff-friendly bei Git-Tracking (Zeilen-basiert)
- RAG-Indexer haben gute YAML-Support out-of-the-box

## Data-Sources pro Sektion

| Section | Source-Tables | Query Strategy |
|---|---|---|
| Frontmatter `sync_*` | `marketing.accounts.sync_id` (vor render via UUID-default-generated wenn NULL) | Lazy: erstes Render generiert UUID, persisted in DB |
| Frontmatter Profil | `marketing.accounts` | Single-row SELECT WHERE handle=? |
| `all_emails` | `marketing.emails WHERE handle=?` | Single SELECT with ORDER BY confidence DESC |
| `tags` | `marketing.email_tags JOIN tags` (für jede Email der Person) | DISTINCT tag.name UNION über alle Emails |
| `audience_memberships` | `marketing.audience_members JOIN audiences` | Same — per-email-aggregated |
| Send History | `marketing.campaign_sends JOIN campaigns` (über emails der Person) | COUNT + MAX(sent/open/click/reply_at) |
| Reply History | `marketing.inbound_messages WHERE from_email IN (...)` | COUNT + MAX(received_at) |
| Strategies | `marketing.strategies WHERE id IN (SELECT strategy_id FROM emails ...)` | Distinct strategies that produced any email of this person |

**Eine einzige große Query** vs **mehrere kleine**: Wir nehmen eine **single query mit JSON aggregation** (postgres `json_build_object` + `array_agg`) → ein round-trip pro Render. Bei 14k Personen × 0.5ms = 7s für full re-render. Akzeptabel; Sync ist trotzdem incremental.

## Frontmatter-Schema (canonical)

Damit Frontmatter-Diff zuverlässig ist (Worker B muss detektieren ob Felix das Frontmatter editiert hat = nicht erlaubt), ist die Reihenfolge **fixed** und alphabetisch innerhalb Gruppen. Schema-Version (`sync_version: 1`) erlaubt zukünftige Migrationen.

**Gruppen** (in dieser Reihenfolge):
1. Sync-Meta (`sync_id, sync_version, sync_source, sync_path, last_synced_at`)
2. Identity (`handle, display_name, niche, source, followers, created_at`)
3. Email-Roll-up (`primary_email, all_emails`)
4. Tag-Roll-up (`tags`)
5. Audience-Roll-up (`audience_memberships`)
6. Engagement-Roll-up (counts + max timestamps)
7. Inbound-Roll-up

`primary_email` = `emails` row mit höchstem `confidence` (Tie-Break: kleinste `created_at`).

## Body-Schema

Body wird in Sections gerendert. **Jede Section ist deterministisch** (gleicher DB-State → gleiches Markdown, bis aufs Byte). Sortierung explizit dokumentiert:

- **Emails-Tabelle:** sortiert nach `confidence DESC, created_at ASC`
- **Tags-Liste:** alphabetisch
- **Audience-Memberships:** sortiert nach `audience.name`
- **Send-History:** _"No campaigns yet"_ statisch oder Liste sortiert nach `sent_at DESC LIMIT 20`
- **Reply-History:** ähnlich, `received_at DESC LIMIT 20`
- **Strategies:** sortiert nach `fitness DESC`

Längen-Caps für Body-Sections: `LIMIT 20` pro History-Section. Sonst werden die .md-Files bei aktiven Recipients riesig. Pagination-Hinweis am Ende der Section ("... and N more, see marketing.campaign_sends").

## Empty-State Handling

Pro Section eine standardisierte Empty-State-Zeile:
- Emails: _Wirklich kein? Dann ist der Account vermutlich nur ein generated handle ohne emails._ → `_No emails (handle exists in marketing.accounts but no entries in marketing.emails)._`
- Tags: `_None._`
- Audience: `_Not in any audience._`
- Send: `_No campaigns sent to this person yet._`
- Reply: `_No inbound messages._`
- Strategies: `_No strategies recorded._` (sollte nur passieren wenn pathx nicht migriert wurde)

## Edge Cases

| Case | Behaviour |
|---|---|
| Handle existiert, aber 0 emails (= 14.392 von 14.742) | Frontmatter `primary_email: null, all_emails: []`. Emails-Section "_No emails._" |
| Handle hat 5+ emails (rare bei pathx, häufiger künftig) | Alle in `all_emails` Liste, primary = highest confidence |
| Display-name enthält `:` oder `"` oder Linebreaks | YAML-quoten: `display_name: "Foo: Bar"` |
| Handle enthält Unicode | Frontmatter behält Unicode (UTF-8 file write). Filename wird sanitized → ASCII-only |
| pathx hatte NULL display_name | Frontmatter `display_name: ""` (leerer string), nicht null — RAG-Indexer reagieren besser auf empty als auf null |
| `created_at` ist `NULL` in DB | Frontmatter `created_at: null` |
| Sehr alter `last_engagement_at` (> 90 Tage) | Im Body-Table: `_stale_` statt formatiertem Datum |

## Sanitization für Filename

Handle ist nicht 1:1 als Filename verwendbar. Sanitization:

```
filename = re.sub(r'[^a-z0-9._-]', '_', handle.lower())[:80]
if filename != handle.lower():
    # Log warning, store original handle in frontmatter
```

Beispiel: `handle = "Hans Müller"` → `filename = "hans_m_ller.md"`, frontmatter behält `handle: "Hans Müller"`.

## Render-Funktion API

```python
def render_person_md(conn, handle: str) -> tuple[str, dict]:
    """Render a single person's Markdown file.

    Returns (markdown_text, debug_info).
    debug_info has 'query_count', 'render_ms', 'truncated_sections'.
    """
```

```python
def render_all(conn, output_dir: Path, only_changed: bool = False) -> RenderReport:
    """Render every account in marketing.accounts.

    only_changed=True: skip accounts whose last_synced_at >= max(updated_at across joined tables)
    """
```

## Snapshot Tests (Phase-2 Deliverable)

`spaces/marketing/sync/tests/test_render_md.py`

1. **Empty account:** handle exists, 0 emails, 0 tags → check empty-state strings present
2. **Single-email account:** typical pathx-migrated → check primary_email = single email, table has 1 row
3. **Multi-email account:** synthetic test row with 3 emails of varying confidence → check ordering + primary_email is correct
4. **With tags + audience:** add tags + audience_member rows → check Body sections render
5. **With send_history:** add campaign_sends row → check counts + max timestamps in frontmatter
6. **Determinism:** call render twice → identical bytes
7. **Special chars:** handle `O'Brien` + display `Mary "Mike" O'Brien` → YAML quotes correct
8. **Unicode:** handle `müller_handle_01` + display `Müller, J.` → UTF-8 correct
9. **Length caps:** seed 50 campaign_sends → render shows LIMIT 20 + "... 30 more"
10. **Null timestamps:** create_at=NULL → frontmatter `created_at: null`

## Render Performance Targets

| Operation | Target | Justification |
|---|---|---|
| Single render | < 50 ms | Worker A processes ~20 events/s peak |
| Full re-render of 14.742 | < 30 s | Acceptable for ad-hoc rebuild |
| Snapshot test (10 cases) | < 2 s | Pytest dev-loop |

## What Phase 2 does NOT do

- **No file writes.** Pure function returning string. Worker A in Phase 4 handles the FS.
- **No sync_id persistence.** Phase 2 generates a UUID for tests but doesn't write back to `marketing.accounts.sync_id`. Migration 006 (vor Phase 4) wird die `sync_id` Spalte hinzufügen + Defaults backfillen.
- **No watching.** Pure pull.
- **No incremental detection.** `only_changed` ist nur ein Stub für Phase 4.

## Implementation Outline

```
spaces/marketing/sync/
  __init__.py
  render_md.py            # 400-500 LOC — main module
  _queries.py             # ~150 LOC — SQL constants
  _frontmatter.py         # ~80 LOC — YAML serialization with stable order
  _filename.py            # ~40 LOC — sanitization
  tests/
    test_render_md.py     # 10 snapshot tests
    __snapshots__/        # generated snapshot files committed to repo
```

Dependencies (Python stdlib + 1 external):
- `psycopg[binary]` for DB
- `PyYAML` for frontmatter (or hand-rolled for full control over ordering)

## Open Decisions (Felix-Review)

1. **YAML library oder hand-roll?** Hand-roll gibt uns volle Kontrolle über Ordering und Quoting (wichtig für deterministic diff). PyYAML ist convenient. **Vorschlag: hand-roll** (~60 LOC, simpel weil nur unsere fixed schema).
2. **LIMIT 20 ok für send-history?** Bei Power-Recipients (100+ Sends) zeigt das File nur die letzten 20. Alternative: scrollable "see more in DB" link. **Vorschlag: LIMIT 20 + Hinweis**.
3. **Stale-Threshold für `_stale_`?** Plan sagt 90 Tage. **Vorschlag: 90 Tage**, konfigurierbar via `MARKETING_STALE_DAYS=90` Env.
4. **Snapshot-Tests in `__snapshots__/` committen?** Ja → CI sieht Drift. **Vorschlag: ja**.
5. **Welcher Filename bei Unicode-Handle?** Plan sagt sanitize zu ASCII, behält Original in frontmatter. **Vorschlag: ok**.

## Aufwand-Schätzung

- `_queries.py` Single-Query mit JSON aggregations: 1.5–2h
- `_frontmatter.py` deterministic YAML: 1h
- `_filename.py`: 30min
- `render_md.py` main + CLI: 2h
- Snapshot-Tests (10 cases): 2.5h
- Performance-Tuning + Edge-Case-Fixes: 1h

**Gesamt Phase 2: 8–9h** (passt zum Master-Plan-Range "12–18h" für alle Phasen)

## Next steps (after Felix sign-off auf diesen Plan)

1. Implement `render_md.py` + helpers
2. Run snapshot tests
3. Manual review: `python render_md.py --handle kennethharris` → ist das Markdown lesbar/correct?
4. Render-all dry-run gegen Dummy-Output-Dir → verifiziere 14.742 Files entstehen, alle valid
5. Performance-Measurement (single render + full re-render)
6. **Dann erst Phase 3** (DB Triggers): Renderer ist die Voraussetzung dass die Trigger sinnvoll sein können

## Verbunden mit

- Master-Plan: [marketing-data-sync.md](file:///C:/Users/User/.claude/plans/marketing-data-sync.md)
- Migration 005 (already applied): `spaces/marketing/db/005_investor_sent_flag.sql`
- Migration 001 (schema base): `spaces/marketing/db/001_marketing_schema.sql`
- Migration 002 (RLS): `spaces/marketing/db/002_rls_baseline.sql`
- Migration 003 (service_role): `spaces/marketing/db/003_service_role_grants.sql`
- Phase 1 Script (done): `spaces/marketing/scripts/migrate_pathx_to_supabase.py`
- Memory: [[mailcow-community]] — DSGVO baseline
- Memory: [[marketing-ops-space]] — overall context
