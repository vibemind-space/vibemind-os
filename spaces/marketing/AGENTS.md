# Marketing-Ops — Agent + Developer Guide

This file is the entry-point for any agent (or human) touching
`spaces/marketing/`. It enumerates the modules, their contracts, the
12+3 safety gates between an LLM-Hand discovery and a sent mail, and
the things that look like footguns but are deliberate.

If you came here from a Claude Code session: read the **Hard Rules**
section first, then **Gate graph**, then **Module map**. Skip the rest.

---

## Hard Rules — read before touching ANY file under spaces/marketing/

1. **Never write `consent_given_at` to a non-NULL value** from code.
   It is the GDPR signal that a recipient has affirmatively opted in.
   No path in the current codebase sets it. New paths must not either.
2. **Never write `investor_already_sent = true`** from code. The DB
   trigger `trg_flip_investor_sent` (migration 005) is the only allowed
   writer; it fires when `campaign_sends.delivered_at` transitions
   NULL→set. Worker D (`workers/delivered_webhook.py`) is the only
   process that should call `mark_delivered`. Skip-listed in tests.
3. **Never write `campaign_sends.delivered_at`** from code outside
   Worker D. The send-worker (`tools/_send_paranoid.py`) DELIBERATELY
   leaves it NULL on success — verified by `gate12_*` tests.
4. **Never bypass `_require_proposal_api_key`** on a new POST route.
   The `test_auth_guard.test_other_mutating_routes_also_guarded` test
   fails CI if you do. The helper refuses (503) when the env is unset
   — fail-closed by design.
5. **Never lift `external_sources.can_send` above false** without a
   new migration that drops the CHECK constraint AND documents the
   replacement gate stack for that channel. The constraint exists
   precisely so this requires a code review.
6. **Never send to a non-`@vibemind.space` recipient** from any path.
   The send-worker has a hardcoded `ALLOWED_DOMAINS = {"vibemind.space"}`
   plus an IDNA round-trip check against unicode lookalikes (gate 5).
   Postfix has a PCRE block as the second line of defense.
7. **Never embed an OpenAI/Anthropic/Mailcow API key in this codebase.**
   They live in `.env` only; tools read them from `os.environ` at call
   time so a rotated key takes effect on next request.

---

## Gate graph — what stands between a Hand discovery and a sent mail

15 independent layers. Removing any one of them is a separate, reviewable
migration or commit. Numbers match the gates discussed in commit messages.

```
INPUT
 │
 │  Hand discovery (Lead/Researcher/Collector) · Gmail · Notion ·
 │  Sheets · Tavily · manual CSV · or operator HTTP POST
 │
 │  ALLOWLIST                          (Python frozenset, hardcoded)
 ▼  ALLOWED_INTEGRATION_KINDS
 │      see tools/integrations.py
 │
 │  CHECK CONSTRAINT                   (schema, can_send = false)
 ▼  marketing.external_sources
 │
 │  PROPOSAL STAGING                   (audit + status='pending_review')
 ▼  propose_audience / propose_audience_from_source
 │      writes marketing.audience_proposals + lead_candidates
 │
 │  HUMAN GATE                         (HTTP 503 if env unset, 401 if wrong)
 ▼  MARKETING_PROPOSAL_API_KEY
 │      _require_proposal_api_key in api/server.py
 │
 │  MX VALIDATION (DNS only, never SMTP)
 ▼  validate_proposal_mx
 │      sets smtp_valid = 1/0/-1
 │
 │  ATOMIC PROMOTION                   (stored function, all-or-rollback)
 ▼  marketing.approve_audience_proposal()
 │      writes accounts + emails (consent_given_at = NULL) + members
 │
 │  GATE 1  kill-switch                MARKETING_SEND_ENABLED == "true"
 │  GATE 2  freeze-file absent         logs/marketing/FREEZE
 │  GATE 3  campaign status terminal?
 │  GATE 4  recipient snapshot + cap   HARD_RECIPIENT_CAP=1000
 │  GATE 5  domain allowlist + IDNA    {vibemind.space} only
 │  GATE 6  investor-lockout re-check  defense-in-depth recount
 │  GATE 7  confirm-token              SHA256 over sorted recipient set
 │  GATE 8  SHADOW pre-ping            (SHADOW mode only)
 │  GATE 9  Postfix loopback probe     RCPT TO external = expect 554
 │  GATE 10 per-recipient RCPT probe   on SAME connection (TOCTOU defense)
 │          + atomic claim             ON CONFLICT (campaign_id, email)
 │  GATE 11 mailq post-send audit      external in queue = FREEZE
 │  GATE 12 atomic status flip         campaigns.status='sent'
 ▼
 │  POSTFIX SERVER-SIDE                check_recipient_access PCRE
 ▼      554 LOOPBACK-MODE for any non-vibemind.space
 │
 ▼  MAIL EXTERN (only if all 15 layers pass)
```

`delivered_at` is written ONLY by Worker D (`workers/delivered_webhook.py`)
which has its own ALLOWED_DOMAINS defense-in-depth recheck.

---

## Module map

```
spaces/marketing/
├── db/                                 — migrations 001..012
├── sync/                               — DB ↔ markdown vault
│   ├── worker_db_to_fs.py              Worker A: DB → ~/.rowboat/.../People/*.md
│   ├── worker_fs_to_db.py              Worker B: vault deletes → DB
│   └── worker_imap_sync.py             Worker C: Mailcow IMAP → inbound_messages
├── workers/
│   ├── send_worker.py                  CLI: python -m spaces.marketing.workers.send_worker
│   └── delivered_webhook.py            Worker D: ONLY writer of delivered_at
├── agents/
│   ├── marketing_agent.py              BaseBackendAgent — 13 events ↔ 13 tools
│   └── runner.py                       Standalone Redis-stream consumer
├── tools/
│   ├── marketing_tools.py              Swarm-tool façade (re-exports all entries)
│   ├── _send_paranoid.py               12-gate Phase-2 send-worker
│   ├── hand_bridge.py                  OpenFang Hand request (Track C)
│   ├── integrations.py                 5 external sources (Track A+B)
│   ├── approval.py                     proposal → audience promotion
│   └── tests/                          ~80 tests (see Test matrix)
├── api/
│   ├── server.py                       FastAPI — 18 routes
│   └── tests/                          auth-guard + unsubscribe tests
├── scripts/
│   ├── real_case_test.py               End-to-end loopback smoke
│   ├── snapshot_pathx_data.py          CSV dump of all 13 tables
│   └── migrate_pathx_to_supabase.py    One-shot pathx → supabase import
├── mockup/index.html                   8 tabs + live-binding to /api/*
└── AGENTS.md                           you are here
```

---

## Event ↔ tool table (MarketingBackendAgent)

| event_type                       | tool function                       | writes to                                     |
|----------------------------------|-------------------------------------|-----------------------------------------------|
| `marketing.stats`                | `get_stats`                         | (read-only)                                   |
| `marketing.list_audiences`       | `list_audiences`                    | (read-only)                                   |
| `marketing.list_templates`       | `list_templates`                    | (read-only)                                   |
| `marketing.list_campaigns`       | `list_campaigns`                    | (read-only)                                   |
| `marketing.inbox`                | `get_inbox_unread`                  | (read-only)                                   |
| `marketing.audience_count`       | `audience_count`                    | (read-only)                                   |
| `marketing.create_audience`      | `create_audience`                   | `marketing.audiences`                         |
| `marketing.create_template`      | `create_template`                   | `marketing.templates`                         |
| `marketing.send_campaign`        | `send_campaign`                     | `marketing.campaign_sends` (NOT delivered_at) |
| `marketing.audience_proposal`    | `propose_audience`                  | `audience_proposals` + `lead_candidates`      |
| `marketing.list_proposals`       | `list_proposals`                    | (read-only)                                   |
| `marketing.get_proposal`         | `get_proposal`                      | (read-only)                                   |
| `marketing.request_hand`         | `request_hand_research`             | `audit_log` only (Hand callback later)        |

Param-aliasing (DE/EN) lives in `marketing_agent.py:PARAM_MAPPING`.

---

## HTTP route table (api/server.py)

| Method | Path                                    | Auth                  | Writes               |
|--------|-----------------------------------------|-----------------------|----------------------|
| GET    | `/api/health`                           | none                  | —                    |
| GET    | `/api/stats`                            | none                  | —                    |
| GET    | `/api/audiences`                        | none                  | —                    |
| GET    | `/api/audiences/{id}/count`             | none                  | —                    |
| GET    | `/api/templates`                        | none                  | —                    |
| GET    | `/api/campaigns`                        | none                  | —                    |
| GET    | `/api/inbox`                            | none                  | —                    |
| GET    | `/api/audit`                            | none                  | —                    |
| GET    | `/api/proposals[?status=...]`           | none                  | —                    |
| GET    | `/api/proposals/{id}`                   | none                  | —                    |
| GET    | `/api/integrations[?enabled_only=...]`  | none                  | —                    |
| GET    | `/api/integrations/{kind}`              | none                  | —                    |
| POST   | `/api/proposals`                        | MARKETING_PROPOSAL_API_KEY | proposals + candidates |
| POST   | `/api/proposals/{id}/approve`           | MARKETING_PROPOSAL_API_KEY | audiences + emails + members |
| POST   | `/api/proposals/{id}/reject`            | MARKETING_PROPOSAL_API_KEY | proposals.status='rejected' |
| POST   | `/api/proposals/{id}/validate_mx`       | MARKETING_PROPOSAL_API_KEY | lead_candidates.smtp_valid |
| POST   | `/api/proposals/request_hand`           | MARKETING_PROPOSAL_API_KEY | audit_log only       |
| POST   | `/api/integrations/{kind}/import`       | MARKETING_PROPOSAL_API_KEY | proposals + candidates |
| GET/POST | `/api/unsubscribe?email&msg&t`        | per-recipient HMAC token | emails.unsubscribed_at |
| GET    | `/mockup/`                              | none                  | —                    |

`MARKETING_PROPOSAL_API_KEY` MUST be set; helper returns 503 if absent.

---

## Schema reality (from psql, not commit messages)

Several columns have non-obvious names because the original pathx
import dictated them:

- `marketing.emails.handle` — FK to `marketing.accounts(handle)`. NOT
  named `account_handle`.
- `marketing.emails.strategy_id` — text provenance label, NOT named
  `source`. The approval flow stores `'proposal:<uuid>'` here.
- `marketing.emails.smtp_valid` — smallint tri-state (-1/0/1), NOT a
  boolean `is_verified`. The send-worker requires `=1`; MX validation
  flips to 1, NXDOMAIN to 0; default -1.
- `marketing.audiences.filter_dsl` — jsonb, NOT named `definition`.
- `marketing.audience_members` — composite PK (`audience_id`, `email`).
- `marketing.campaign_sends.message_id` — text, no `<>`, partial UNIQUE
  index (where NOT NULL). Migration 007.
- `marketing.campaign_sends` UNIQUE (`campaign_id`, `email`). Migration
  008. The atomic claim depends on this.

`marketing.audit_log` columns:
`id, actor, action, target_table, target_id, payload (jsonb), created_at`.

---

## Send-worker modes (`tools/_send_paranoid.py`)

```
SendMode.DRY_RUN   - resolves recipients + computes confirm_token; NEVER opens SMTP
SendMode.SHADOW    - opens SMTP to MARKETING_SHADOW_HOST:PORT (default 127.0.0.1:0 = disabled);
                     send goes to Mailpit, never to extern. Aborts loud if envs unset.
SendMode.LIVE      - all 12 gates fire. Requires MARKETING_SEND_ENABLED=true,
                     FREEZE-file absent, valid confirm_token, real SMTP creds.
```

The auto-mode classifier in Claude Code blocks `--mode live` by default;
it's a deliberate operator action, not a dev-flow side-effect.

---

## Env vars

Required for full operation:

```
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / SMTP_FROM
MAILCOW_URL / MAILCOW_API_KEY
MARKETING_PROPOSAL_API_KEY       — required for ANY POST endpoint
MARKETING_UNSUB_SECRET           — ≥32 chars; required to build/verify unsubscribe tokens
```

Required only for specific modes:

```
MARKETING_SEND_ENABLED=true      — LIVE send mode (per-run env, not .env recommended)
MARKETING_SHADOW_HOST / _PORT    — SHADOW mode pin (Mailpit container)
MARKETING_WEBHOOK_SECRET         — delivered_webhook HTTP listener
MARKETING_API_KEY                — optional global X-API-Key on all /api/* (vs the per-route key)
```

Optional sync workers:

```
MARKETING_VAULT_DIR              — default ~/.rowboat/knowledge/Marketing/People/
MARKETING_HASH_STORE             — Worker A/B SHA256 echo-defense state
MARKETING_IMAP_*                 — Worker C IMAP creds + poll-interval
```

---

## Test matrix

```
test_send_paranoid       32  12 gates + bug regressions + unicode lookalike
test_unsubscribe          6  RFC 8058 one-click + drift-guard
test_auth_guard           8  Auth helper + regression-guard for new routes
test_delivered_webhook    5  Defense-in-depth + non-allowlist refuses
test_hand_bridge          9  Hand A/B/C bridge + key normalisation
test_integrations        14  5 extractors + allowlist + CHECK + no-send-spy
test_approval            12  Atomic + idempotent + MX-mock + no-send-spy
────────────────────────────
Total                    86  All PASS, zero regressions
```

Run all: `for t in spaces.marketing.tools.tests.test_send_paranoid \
spaces.marketing.api.tests.test_unsubscribe \
spaces.marketing.api.tests.test_auth_guard \
spaces.marketing.workers.tests.test_delivered_webhook \
spaces.marketing.tools.tests.test_hand_bridge \
spaces.marketing.tools.tests.test_integrations \
spaces.marketing.tools.tests.test_approval; do python -m "$t"; done`

---

## Common pitfalls (real bugs I made)

- **`query_via_docker` wraps SQL in `SELECT ... FROM (<sql>) t`** — does
  NOT work for `INSERT ... RETURNING`. Use `execute_via_docker` + parse
  the stdout (drop the trailing `INSERT N M` status line). Bug fixed
  in commit `3aec7f1`.
- **PL/pgSQL variable names matching table columns** cause "ambiguous"
  errors on `ON CONFLICT (col_name)`. Use `v_<short>` prefixes that
  don't collide. Bug fixed in `36f0e47`.
- **Swarm-mode docker ports don't support hostip binding** — `"54325:1025"`
  binds 0.0.0.0:54325, not 127.0.0.1:54325. For loopback-only sinks,
  start an extra non-stack container. Bug fixed in `070a2a2`.
- **`audiences.member_count` is a cached column** — does NOT auto-update
  on `audience_members` INSERT. The approval stored function recomputes
  it inside the same transaction.

---

## When a future change wants to add a send-path

It must do all four:

1. New migration that registers the channel in `marketing.external_sources`
   with `can_send=true` AND simultaneously drops the CHECK constraint
   for that row only (or rewrite the check to allow specific kinds).
2. New module in `spaces/marketing/tools/` that mirrors the 12-gate
   structure of `_send_paranoid.py`: kill-switch, freeze-file, allowlist,
   confirm-token, per-recipient pre-flight, atomic claim, post-send
   audit. Don't take shortcuts; the gates compose.
3. New 30+ tests covering each gate, plus a `never_calls_other_channels`
   regression-guard.
4. Update this file + STATUS.md before merging.

Code-review checklist: any commit that grows `_send_paranoid.py` or
adds new SMTP/HTTP-out-to-recipient calls is automatically suspect.
The reviewer should see `Co-Authored-By: <name>` in the commit and at
least one new gate-test.
