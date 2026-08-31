# Plan — Marketing Data Sync (pathx → Supabase ↔ Rowboat Knowledge)

## Context

Felix hat 3 Daten-Layer, die in Beziehung gesetzt werden müssen:

1. **`pathx`** (`x-pathfinder-db`, Postgres :5434) — 14.742 generierte accounts + 350 validierte E-Mails. **Quelle für initialen Seed**, danach aufzulösen.
2. **Supabase `marketing.*`** (im `vibemind`-Stack) — strukturierter Store, Source-of-Truth für Profile, Tags, Send-History, Engagement-Metriken, Consent-Status. RLS-locked (Phase-1 = nur `service_role`).
3. **Rowboat Knowledge Vault** (`~/.rowboat/knowledge/People/`) — Markdown-Files pro Person, **RAG-indexed**. Brain/AI-Agents finden Personen via Semantic Search.

**Vision (Felix' Worte):** *"rowboat daten referenzieren im knowledge so dass wir später über die rag suche an die leute rankommen und die restlichen metadaten aus supabase bekommen. pathx db kann dann aufgelöst werden."*

**Outcome:** Eine Person existiert in beiden Stores. Supabase hat die strukturierten Daten. Rowboat Knowledge hat den ge-renderten Markdown-View. Beide bleiben **bi-direktional** synchron — Löschen in beide Richtungen kaskadiert.

## Datenmodell-Mapping

### Schema-Additions vor Migration (Migrations 005 + 006)

Vor Phase 1 brauchen wir zwei DDL-Additions:

**005 — `marketing.emails.investor_already_sent boolean`** (Felix-Entscheidung 2026-06-02):
- One-shot lockout pro Empfänger. Bei erstem erfolgreichen Send (`campaign_sends.delivered_at` wechselt NULL→not-NULL) wird der Bool via Trigger `trg_flip_investor_sent` auf `true` gesetzt.
- Audience-Builder filtert defaultmäßig `WHERE investor_already_sent = false` — überschreibbar nur via explizite UI-Bestätigung.
- Partial Index `idx_emails_investor_sent WHERE = true` für schnelle "wer hat schon" Lookups.
- Sticky über audience-refresh / campaign-purges — der durable Lockout, der retention-Window übersteht.
- Status: ✅ **applied 2026-06-02** (`spaces/marketing/db/005_investor_sent_flag.sql`).

**006 — sync-Spalten auf `marketing.accounts`**:
- `sync_id uuid PRIMARY KEY DEFAULT gen_random_uuid()` als zweite stabile ID neben `handle` (handle kann sich ändern, sync_id nie). Frontmatter-`sync_id` in Markdown referenziert diesen Wert.
- `last_synced_at timestamptz` für Worker-A-State.
- `sync_origin text DEFAULT 'db'` (transient via `set_config('marketing.sync_origin', ...)`) — Loop-Prevention.
- Wird vor Phase 4 (Worker A) angewendet.

### pathx → marketing.*  (one-time, transactional)

| pathx-Spalte | → | marketing-Tabelle.Spalte |
|---|---|---|
| `accounts.handle` | → | `accounts.handle` (PK) |
| `accounts.display_name` | → | `accounts.display_name` |
| `accounts.bio` | → | `accounts.bio` |
| `accounts.followers` | → | `accounts.followers` |
| `accounts.niche` (z.B. "US","DE") | → | `accounts.niche` |
| `accounts.source` ("namegen") | → | `accounts.source` |
| `accounts.created_at` | → | `accounts.created_at` |
| `emails.email` | → | `emails.email` (PK) |
| `emails.handle` (FK) | → | `emails.handle` |
| `emails.confidence/mx_valid/smtp_valid/...` | → | gleichnamig |
| **NEU bei migration** | + | `emails.consent_given_at = NULL` (DSGVO-Lock) |
| **NEU bei migration** | + | `emails.consent_source = 'pathfinder-import-no-consent'` |
| `strategies.*` | → | `strategies.*` (1:1) |
| `runs.*` | → | `runs.*` (1:1) |

**Wichtig:** Alle Migrationen erhalten `consent_given_at = NULL` — Audience-Builder filtert standardmäßig "nur mit Consent" raus. Loopback-Block fängt zusätzlich versehentliche Sends.

### marketing.* → ~/.rowboat/knowledge/People/<handle>.md (continuous)

Pro `marketing.accounts`-Row ein Markdown-File. Joins mit:
- `marketing.emails` (1:n) — alle bekannten E-Mails
- `marketing.email_tags` (n:m via tags) — Tags
- `marketing.audience_members` (n:m) — Audience-Memberships
- `marketing.campaign_sends` (n:1 via email) — Send-History
- `marketing.inbound_messages` (n:1 via from_email) — Reply-History

**File-Name:** `<handle>.md` (z.B. `kennethharris.md`)
**Location:** `~/.rowboat/knowledge/People/<handle>.md`

**Format (voll-renderbar):**

```markdown
---
# Auto-generated from supabase marketing schema. DO NOT EDIT METADATA HERE.
# (Body lines below the second '---' fence ARE editable and won't be overwritten.)
sync_id: <uuid>
handle: kennethharris
supabase_url: http://127.0.0.1:54321/rest/v1/marketing.accounts?handle=eq.kennethharris
display_name: Kenneth Harris
emails: [hkenneth@gmail.com]
primary_email: hkenneth@gmail.com
niche: US
source: namegen
created_at: 2026-03-31T13:10:06Z
last_sync_at: 2026-06-02T11:30:00Z
tags: [imported, no-consent]
followers: 0
---

# Kenneth Harris

**Handle:** kennethharris
**Region:** US
**Source:** namegen (pathfinder-import-no-consent)

## Emails

| Email | Confidence | MX | SMTP | Consent |
|---|---|---|---|---|
| hkenneth@gmail.com | 0.95 | ✓ | ✓ | _none_ |

## Tags

- imported
- no-consent

## Send History

_No campaigns sent yet._

## Reply History

_No inbound messages._

## Audience Memberships

_Not in any audience._

---

<!-- Custom notes (free-form, won't be overwritten by sync) -->
```

**Frontmatter zwischen den ersten `---` ist Source-of-Truth aus Supabase**, wird bei jedem Sync überschrieben. Der Bereich nach dem letzten `---` ist frei-editierbar. So kann Felix Custom-Notes machen ohne dass der Sync sie wegblättert.

## Architektur — bi-direktionaler Sync mit Loop-Prevention

### Komponenten

```
┌──────────────────────────────────────────────────────────────────────┐
│  SUPABASE supabase-db                                                │
│                                                                      │
│  marketing.accounts/emails/tags/...                                  │
│  └─ TRIGGER on INSERT/UPDATE/DELETE  → sync_outbox table             │
│                                       (records what changed)         │
│  marketing.sync_outbox  ← NEW TABLE                                  │
│  marketing.sync_inbox   ← NEW TABLE (deduplicated incoming changes)  │
│                                                                      │
│  LISTEN/NOTIFY channel 'marketing_sync'                              │
└────────────────┬─────────────────────────────────────────────────────┘
                 │                              ▲
                 │  (1) DB→FS direction         │  (2) FS→DB direction
                 ▼                              │
┌──────────────────────────────────────────────────────────────────────┐
│  SYNC WORKER (Python, runs as background process)                    │
│                                                                      │
│  Worker A:  LISTEN marketing_sync  → render markdown                 │
│              ─ dedupe via sync_outbox.sync_id                        │
│              ─ apply change to ~/.rowboat/knowledge/People/<h>.md    │
│              ─ tag file with `sync_origin: db` in frontmatter        │
│                                                                      │
│  Worker B:  watchdog observer on ~/.rowboat/knowledge/People/        │
│              ─ on file-DELETE  → DELETE FROM marketing.accounts...  │
│              ─ on file-CHANGE  → IF body-section changed, IGNORE     │
│                                  (only frontmatter is db-source)    │
│              ─ DELETEs tag the action as 'sync_origin: fs' to       │
│                prevent trigger from echoing back                     │
└──────────────────────────────────────────────────────────────────────┘
```

### Loop-Prevention

Klassisches Problem bi-direktionaler Sync: A schreibt → B sieht → schreibt → A sieht → wieder schreibt → infinite loop.

**Lösung:** Jeder Apply-Vorgang trägt einen `sync_origin`-Tag in einer transienten Session-Variable. Trigger schreibt nur ins outbox WENN `sync_origin != session-tag`.

Postgres-Side:
```sql
CREATE TABLE marketing.sync_outbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name text NOT NULL,
  row_key text NOT NULL,                    -- accounts.handle, emails.email, ...
  operation text NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
  payload jsonb NOT NULL,                   -- the full row content (or NULL on DELETE)
  origin text NOT NULL DEFAULT 'db',        -- 'db' or 'fs'
  emitted_at timestamptz DEFAULT now(),
  applied_at timestamptz                     -- NULL = not yet picked up by worker
);

CREATE OR REPLACE FUNCTION marketing.emit_sync_event() RETURNS trigger AS $$
DECLARE
  origin_tag text := current_setting('marketing.sync_origin', true);
BEGIN
  -- Skip emit if THIS change came from a sync apply itself (loop prevention)
  IF origin_tag = 'fs' THEN
    RETURN COALESCE(NEW, OLD);
  END IF;
  INSERT INTO marketing.sync_outbox (table_name, row_key, operation, payload, origin)
  VALUES (
    TG_TABLE_NAME,
    CASE TG_TABLE_NAME
      WHEN 'accounts' THEN COALESCE(NEW.handle, OLD.handle)
      WHEN 'emails'   THEN COALESCE(NEW.email,  OLD.email)
      ELSE COALESCE(NEW::text, OLD::text)
    END,
    TG_OP,
    CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END,
    'db'
  );
  -- Fire LISTEN/NOTIFY so the worker wakes up immediately
  PERFORM pg_notify('marketing_sync', '');
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
```

FS-Side (Worker B writes back to DB):
```python
# When applying a FS→DB change:
cur.execute("SELECT set_config('marketing.sync_origin', 'fs', true)")  # session-scoped
cur.execute("DELETE FROM marketing.accounts WHERE handle = %s", (handle,))
# Trigger sees origin='fs', skips outbox emit → no loop back to FS
```

### Idempotenz

Worker A speichert `last_processed_outbox_id` in einer kleinen state-Datei. Beim Start liest er alle `applied_at IS NULL` Rows aus outbox und applied sie nochmal — Apply-Funktion muss idempotent sein (re-write des .md-Files ist idempotent von Natur aus; DELETE ebenfalls).

Worker B trackt File-Inhalte vor und nach jeder Änderung via Content-Hash. Wenn der Inhalt identisch ist zu dem was wir gerade geschrieben haben (= Worker A's letztes write), wird das File-Event ignoriert.

### Conflict Resolution

Wenn beide Seiten gleichzeitig schreiben (z.B. Felix editiert .md, gleichzeitig kommt SMTP-Reply rein → marketing.inbound_messages-Insert → Re-Render):

- **Frontmatter (oben):** immer DB wins. Worker A überschreibt was Felix da rein editiert hat (er sollte es eh nicht editieren — Warnung im Header).
- **Body (unten, nach letztem `---`):** immer File wins. Worker A re-rendert nur Frontmatter + Sections oberhalb des letzten `---`.

### Cascade-Delete

| Aktion | Wirkung |
|---|---|
| `DELETE FROM marketing.accounts WHERE handle='X'` | Trigger emit → Worker A löscht `People/X.md` |
| `rm People/X.md` | Watchdog emit → Worker B sets sync_origin=fs, `DELETE FROM marketing.accounts WHERE handle='X'` |
| Cascade in DB: `accounts → emails → email_tags → audience_members → ...` | Foreign-key cascade existiert bereits in `001_marketing_schema.sql` (ON DELETE CASCADE) |

## Phasen

### Phase 1 — pathx → Supabase (one-time migration)

`spaces/marketing/scripts/migrate_pathx_to_supabase.py`

- Konnekt zu pathx (`localhost:5434`) + supabase-db (via docker exec)
- Iteriere durch pathx.accounts, pathx.emails, pathx.strategies, pathx.runs
- INSERT in marketing.* mit `ON CONFLICT (handle/email) DO UPDATE` (idempotent re-runs)
- `emails.consent_given_at = NULL`, `consent_source = 'pathfinder-import-no-consent'`
- Verifikation: COUNT(*) in beiden Stores stimmt
- Log: `marketing.audit_log` Eintrag mit migration:pathx-import

### Phase 2 — Markdown-Renderer (Standalone-Funktion)

`spaces/marketing/sync/render_md.py`

- Funktion `render_person_md(handle: str) -> str`: joined alle Tabellen, baut Markdown
- Idempotent — gleicher DB-State → gleicher Output
- Frontmatter mit `sync_id` (UUID), `last_sync_at`
- Tests gegen sample-Daten

### Phase 3 — DB-Trigger + outbox + LISTEN/NOTIFY

`spaces/marketing/db/004_sync_triggers.sql`

- `marketing.sync_outbox` Tabelle anlegen
- `emit_sync_event()` Funktion
- Trigger auf accounts/emails/email_tags/audience_members/campaign_sends/inbound_messages
- Pg-NOTIFY channel `marketing_sync`

### Phase 4 — Sync-Worker DB→FS

`spaces/marketing/sync/worker_db_to_fs.py`

- LISTEN auf `marketing_sync`
- Polling-Fallback alle 30s für alte outbox-Entries
- Pro outbox-Entry: render_md(handle) → write File mit atomic-rename
- Apply-Mark in outbox (`applied_at = now()`)

### Phase 5 — Watchdog FS→DB

`spaces/marketing/sync/worker_fs_to_db.py`

- watchdog Observer auf `~/.rowboat/knowledge/People/`
- File-DELETE → `SELECT set_config('marketing.sync_origin', 'fs', true); DELETE FROM marketing.accounts WHERE handle = ?`
- File-CHANGE: compare frontmatter checksum vs stored sync_id → if identical, no-op (= Worker A self-write); else log warning (Felix hat Frontmatter geändert, das ignorieren wir)

### Phase 6 — Conflict + Loop + Idempotenz

- Content-Hash-State-Datei für Worker B (last-seen hash per file)
- Tests: 100 schnelle Inserts in DB → 100 .md erscheinen, kein Echo zurück
- Tests: `rm 50 .md` → 50 Supabase-Rows weg, kein Echo zurück

### Phase 7 — End-to-End Verification

`spaces/marketing/scripts/test_sync_e2e.py`

1. `INSERT INTO marketing.accounts VALUES ('test1', ...)` → erwartet: `People/test1.md` erscheint mit korrekten Daten
2. `UPDATE marketing.accounts SET niche='DE' WHERE handle='test1'` → erwartet: `People/test1.md` Frontmatter aktualisiert
3. `rm People/test1.md` → erwartet: `marketing.accounts WHERE handle='test1'` ist weg
4. `INSERT INTO marketing.emails (email='x@y.z', handle='test1')` für **gelöschten** test1 → erwartet: 23xxx error (FK violation, weil cascade-delete schon weg)
5. Race-Test: 10× concurrent INSERT + 10× concurrent rm = endet konsistent (DB-Count = FS-Count)

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Infinite Loop wenn `sync_origin`-Tag verloren | Session-scoped, plus content-hash-vergleich in Worker B (no-op on identical content) |
| Trigger feuert zu oft (write-amplification) | **Update 2026-06-02 (Felix-Entscheidung): Trigger auf ALLE Tabellen** — accounts, emails, email_tags, audience_members, campaigns, campaign_sends, inbound_messages, tags. Vollständiger Live-Sync, keine Sections die "veralten". Watchdog-Echo-Problem wird via content-hash + sync_origin-Session-Tag verhindert (siehe Loop-Prevention). Performance: nicht critical bei < 1000 events/min — Mailcow-Send-Volume ist limited durch Loopback-Block. |
| Felix editiert Frontmatter | Warning-Comment + Body-Section unter zweitem `---` für Custom-Notes. Frontmatter wird ohne Warnung überschrieben. |
| ~/.rowboat/knowledge/People/ ist ausserhalb des Repos | Path konfigurierbar via `MARKETING_KNOWLEDGE_PATH` env. Default = `~/.rowboat/knowledge/People/`. |
| supabase-db restart killt LISTEN-Connection | Worker reconnect-loop mit exponential backoff; bei reconnect alle ungeprocessten outbox-rows nachholen. |
| pathx-Daten ohne Consent landen in Production-Send | Loopback-Block in Postfix (schon aktiv) + `consent_given_at = NULL` filter im Audience-Builder + .gitignore für `test-audience.json`. Drei Schichten. |
| .md-File mit unicode-Namen | Sanitize handle → lowercase ASCII + alphanumeric only; collision-detection via unique constraint. |

## Was NICHT in diesem Plan

- Subscription-/Webhook-Endpoint für externe Systeme (Phase 2+)
- Bi-dir Sync ZWISCHEN mehreren Rowboat-Vault-Instanzen (Phase 2+)
- Realtime UI-Updates via Supabase-Realtime (kommt in HTML-Mockup-Phase)
- Re-rendering bei Engagement-Events (campaign_sends etc.) — Phase 6 entscheidet, ob auch dort getriggert wird
- Pathx Lifecycle-Management (wann wird die DB wirklich gestoppt) — wenn Phase 1+E2E grün, kann pathx einfach gestoppt werden, sind dann nur Daten in Supabase
- Phase-2 RLS-User-Policies (kommen wenn Multi-User aktiviert)

## Konkret jetzt machen

1. **Diese Plan-Datei committen** (in `.claude/plans/` — überlebt Submodule-Resets, aber commit in Vibemind_V1 wäre noch sicherer; klären)
2. **Phase 1** (pathx → Supabase): `migrate_pathx_to_supabase.py` schreiben + ausführen. Verify counts.
3. **Phase 2** (Render): `render_md.py` mit Snapshot-Tests
4. **Phase 3** (Triggers): `004_sync_triggers.sql` + Apply
5. **Phase 4** (DB→FS): Worker A bauen, 1 manueller INSERT-Test
6. **Phase 5** (FS→DB): Worker B bauen, 1 manueller rm-Test
7. **Phase 6** (Loop-Prevention): formaler Race-Test mit `pytest`-Style assertions
8. **Phase 7** (E2E): 5-Schritt-Verify-Sequenz

Geschätzter Aufwand: 12–18h Vollzeit (komplexer als ich initial dachte; bi-direktional ist immer ~3× one-way).

## Verbunden mit

- Plan: [vibemind-marketing-ops.md](file:///C:/Users/User/.claude/plans/vibemind-marketing-ops.md) — Foundation steht, hier kommt die Daten-Schicht
- DDL: [001_marketing_schema.sql](file:///c:/Users/User/Desktop/Vibemind_V1/spaces/marketing/db/001_marketing_schema.sql) — bestehende Tabellen werden Quelle
- Memory: [[mailcow-community]] — keine Empfänger ohne Consent (Loopback-Block plus consent_given_at=NULL)
- Inventur: [[pathfinder-emails-db]] — 14.742 accounts + 350 emails als Initial-Seed
- Inventur: rowboat-inventory.md (in spaces/marketing/docs/ ehemals, jetzt in plan only) — Rowboat-Mongo ist nicht Marketing-Quelle, das `~/.rowboat/knowledge/People/` Vault-Folder ist getrennt davon
