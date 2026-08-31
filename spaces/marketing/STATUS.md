# Marketing-Ops — Status snapshot

_Last refreshed: 2026-06-08 (committed). For live counts run
`python -c "from spaces.marketing.tools.marketing_tools import get_stats; print(get_stats())"`._

## Phase

**Phase 1 (no-mail-out)** — verified. Every send-eligible code path is
gated, the send-worker is operator-triggered only, and every test suite
includes a `never_calls_send_campaign` regression-guard.

Phase 2 (production) is **deliberately not active**: it would require
(a) `MARKETING_SEND_ENABLED=true` in env, (b) `logs/marketing/FREEZE`
absent, (c) confirm-token, AND (d) all 12 send-gates pass, AND (e) the
Postfix loopback-block PCRE that still rejects external recipients at
the server layer.

## What lives in this space

```
14 commits           7 test suites          86 unit + 5 stored-fn DB-smokes
17 Python modules    12 schema migrations   18 HTTP routes (FastAPI)
13 swarm tools       13 swarm events        ~6000 LOC excluding tests
```

## Components live

| Component                    | State      | Verified                                                                |
|------------------------------|------------|-------------------------------------------------------------------------|
| Schema 001–012               | applied    | live psql probes                                                        |
| Worker A (DB → vault md)     | runnable   | manual smoke; runs in PHASE 4.5 launcher when stack up                  |
| Worker B (vault → DB)        | runnable   | manual smoke                                                            |
| Worker C (IMAP → DB)         | live       | `--probe` reaches Mailcow :993 on marketing@ + noreply@                 |
| Worker D (delivered_at)      | runnable   | 5/5 unit tests; HTTP server boots; live invocation gated                |
| MarketingBackendAgent runner | importable | event ↔ tool sanity verified; Redis live-test pending stack-up           |
| Send-worker DRY_RUN          | live       | confirm_token deterministic; investor_already_sent stays 0               |
| Send-worker SHADOW           | pending    | needs `MARKETING_SHADOW_HOST/_PORT` envs + local Mailpit container       |
| Send-worker LIVE             | gated      | DELIBERATELY blocks; operator-only                                       |
| HTTP API server :5510        | live       | curl reaches /api/health + /api/stats + /api/audit + /api/audiences      |
| Mockup live-binding (8 tabs) | live       | Dashboard + Audiences + Proposals + Audit tabs render from /api/*        |

## DB counts (live as of 2026-06-08, after Schicht 3.7 approval flow)

```
accounts                14,746
emails                       3   (all smtp_valid=1, all consent_given_at NULL)
audiences                    3
audience_members             4
campaign_sends               0   (cleared after SHADOW tests)
audience_proposals           2   (both approved)
lead_candidates              3
external_sources             5
audit_log                   33   (+1 every approve / reject / import / migration)

Phase-1 invariants:
  consent_given_at NOT NULL     0   (expect 0)
  investor_already_sent = true  0   (expect 0)
  external_sources can_send     0   (CHECK-enforced)
  campaign_sends delivered_at   0   (only Worker D writes)
```

## Test matrix (151/151 PASS)

```
test_send_paranoid           38  Email gates 1-12.5 + merge_render + unicode-lookalike
test_unsubscribe              6  RFC 8058 one-click + drift-guard
test_auth_guard               8  Helper + regression for new mutating routes
test_delivered_webhook        5  Allowlist defense + non-allowlist refuses
test_mx_worker                9  Async queue + retry + no-send regression-spy
test_hand_bridge              9  Hand bridge A+B+C + key normalisation
test_integrations            14  5 extractors + allowlist + CHECK + no-send-spy
test_approval                12  Atomic stored-fn + MX-mock + no-send-spy
test_dns_alignment           16  SPF/DKIM/DMARC + strict-env gate + cache
test_channels_and_archival   14  Gate 4.5 + archive + restore + no-send-spy
test_telegram_send           20  Telegram 12-gate + dispatch + no-cross-channel
```

## Channels send-implemented (multi-channel readiness)

  email     -- send_implemented=true, enabled=false; _send_paranoid.py
  telegram  -- send_implemented=true, enabled=false; _send_telegram.py
              ALLOWED_CHAT_IDS = from TELEGRAM_ALLOWED_CHAT_IDS (empty = fail closed)
              kill-switch: TELEGRAM_SEND_ENABLED env

Both channels have separate 12-gate stacks. marketing_tools.send_campaign
dispatches by campaign.channel at the tool layer; no path can cross
channels (regression-guarded by `tg_never_calls_email_loop` test +
`dispatch_email_no_telegram` test).

Run all:
```
for t in spaces.marketing.tools.tests.test_send_paranoid \
         spaces.marketing.api.tests.test_unsubscribe \
         spaces.marketing.api.tests.test_auth_guard \
         spaces.marketing.workers.tests.test_delivered_webhook \
         spaces.marketing.tools.tests.test_hand_bridge \
         spaces.marketing.tools.tests.test_integrations \
         spaces.marketing.tools.tests.test_approval; do
  python -m "$t"; done
```

## Migrations

| #   | File                                  | Adds                                                          |
|-----|---------------------------------------|---------------------------------------------------------------|
| 001 | `001_marketing_schema.sql`            | 13 tables, indexes, RLS-baseline groundwork                   |
| 002 | `002_rls_baseline.sql`                | FORCE RLS on every table                                      |
| 003 | `003_service_role_grants.sql`         | service_role explicit USAGE+ALL                                |
| 004 | `004_sync_triggers.sql`               | Outbox + session-GUC loop-prevention                          |
| 005 | `005_investor_sent_flag.sql`          | Sticky lockout + auto-flip trigger                            |
| 006 | `006_sync_columns.sql`                | sync_id UUID + last_synced_at                                 |
| 007 | `007_inbound_reply_linkage.sql`       | campaign_sends.message_id + reply linkage trigger             |
| 008 | `008_campaign_sends_unique.sql`       | UNIQUE(campaign_id, email) atomic-claim guard                 |
| 009 | `009_bounce_propagation.sql`          | trg_propagate_bounce inbound → outbound                       |
| 010 | `010_audience_proposals.sql`          | Staging table for Hand-bridge / integrations proposals         |
| 011 | `011_external_sources.sql`            | Integrations registry with CHECK can_send=false               |
| 012 | `012_proposal_approval.sql`           | approve_audience_proposal() stored fn + member_count cache    |

## HTTP routes (18 total)

GET (read-only, no auth):
```
/api/health
/api/stats
/api/audiences
/api/audiences/{id}/count
/api/templates
/api/campaigns
/api/inbox
/api/audit
/api/proposals[?status=]
/api/proposals/{id}
/api/integrations[?enabled_only=]
/api/integrations/{kind}
```

POST (writes — MARKETING_PROPOSAL_API_KEY required, 503 if env unset):
```
/api/proposals
/api/proposals/{id}/approve
/api/proposals/{id}/reject
/api/proposals/{id}/validate_mx
/api/proposals/request_hand
/api/integrations/{kind}/import
```

GET/POST (per-recipient HMAC token, no shared key):
```
/api/unsubscribe?email&msg&t
```

Static:
```
/mockup/
```

## Working envs (.env reality)

```
SMTP_HOST=127.0.0.1
SMTP_PORT=465
SMTP_USER=marketing@vibemind.space
SMTP_PASS=<32 char>
SMTP_FROM=marketing@vibemind.space
MAILCOW_URL=https://127.0.0.1:8443
MAILCOW_API_KEY=<key>
MARKETING_PROPOSAL_API_KEY=<long random — REQUIRED for all POST routes>
MARKETING_UNSUB_SECRET=<≥32 chars — REQUIRED to build/verify unsub tokens>
```

Optional / per-mode:
```
MARKETING_SEND_ENABLED=true       # LIVE only -- pass per-invocation, not in .env
MARKETING_SHADOW_HOST=127.0.0.1   # SHADOW only -- requires local Mailpit container
MARKETING_SHADOW_PORT=54325
MARKETING_WEBHOOK_SECRET=<32+>    # Worker D HTTP listener
MARKETING_VAULT_DIR=~/.rowboat/knowledge/Marketing/People
```

## What's NOT done (in priority order)

1. **Voice intent classifier wiring** — MarketingAgent's 13 events are
   discoverable via `EVENT_TO_TOOL` but no IntentClassifier prompt
   training maps "wie viele leads?" → `marketing.stats`. Submodule-edit
   risk; deferred.
2. **Async MX validation queue** — `validate_proposal_mx` is synchronous
   blocking on DNS. Big audiences (>50 unique domains) timeout the HTTP
   request. Should move to a worker queue similar to Worker A/B.
3. **Approval auto-archival** — rejected/approved proposals stay in
   the table forever. Add a sweep job (e.g. archive proposals older
   than 90d) before this gets dataset-large.
4. **Real send-rate metrics** — `audit_log` records every approve but
   no aggregated dashboard view. Need a materialized view or a
   per-day rollup query.
5. **Multi-channel templates** — schema already has `channel text`,
   send-worker is email-only. Telegram/Twitter/Slack bring their own
   12-gate stack (deliberately not yet implemented; would be a separate
   `_send_channel.py` per channel).
6. **DKIM/SPF/DMARC alignment check** — pre-flight from send-worker is
   missing. Currently relies on Postfix/Mailcow config being correct.
   Phase-2b for production-cutover.

## Recent commits (newest first)

```
6729064  security(marketing): API-key required + validate_mx auth-gate
36f0e47  feat(marketing): proposal approval flow + MX validation (Phase-2b)
3aec7f1  feat(marketing): external integrations bridge -- proposal-only by schema
8e5dd18  feat(marketing): OpenFang Hand bridge -- A+B+C (proposal staging)
be70a72  security(marketing): HMAC unsubscribe + refuse empty/short secret
e637501  security(marketing): hmac.compare_digest + non-loopback bind refuse
615f9db  feat(marketing): cleanup + 12/12 gate-tests + delivered_webhook + one-click unsub
070a2a2  security(marketing): close 0.0.0.0:54325 Mailpit SMTP exposure
4bb1e04  feat(marketing): Mailpit SHADOW + bounce-trigger 009 + send-worker tests
9f28585  feat(marketing): Phase-2 send-worker (12-gate HYBRID) + UNIQUE constraint
0665ecc  feat(marketing): Schicht 3.1 - migration 007 + standalone runner + HTTP API + E2E
bd12936  fix(marketing): schema-correct tools + real-case loopback smoke + pathx snapshot
7d939bf  feat(marketing): Schicht 3 - launcher integration + IMAP sync + agent + HTML mockup
... (foundations + bi-directional sync further back)
```
