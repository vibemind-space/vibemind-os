# Vibemind Marketing-Ops Space

**Status:** Foundation komplett (2026-06-02), bereit für Schicht 2 HTML-Mockup.

This space lives at `vibemind-os/spaces/marketing/` (moved here 2026-08-17). It was
originally kept at the outer repo root to avoid `vibemind-os/spaces/` being a git
submodule that reset on pulls (lost an iteration that way 2026-05-26 → 06-02) — that no
longer applies (`vibemind-os/spaces/` is a plain tracked dir now). Path handling was
split first: `PKG_ROOT` (parent of `spaces/`, for imports) vs `REPO_ROOT` (nearest
ancestor with a `vibemind-os/` dir, for `.env` / payment-infra / logs / skills), both
derived from `__file__` so they resolve correctly here. The launcher runs the sidecars
with `WorkDir = <repo>/vibemind-os` so `python -m spaces.marketing.workers.*` resolves.

## What is this

A Vibemind-Space for **multi-channel marketing operations**, comparable to Brevo / Mailchimp / HubSpot but:

- **Self-hosted** (DSGVO, data stays in your stack)
- **Multi-Channel** beyond email — 28 OpenFang channels marked production-ready (Telegram, Slack, LinkedIn, Mastodon, BlueSky, Discord, Webhook, Mastodon, …)
- **AI-native** — Brain generates content, scores leads, optimises sends
- **Integrated** with existing Vibemind stack (Supabase storage, Mailcow SMTP, OpenFang channels, n8n workflows, Rowboat AI-RAG)

Full plan: [`C:\Users\User\.claude\plans\vibemind-marketing-ops.md`](file:///C:/Users/User/.claude/plans/vibemind-marketing-ops.md)

## What's live

### Storage layer

- **Supabase-DB schema `marketing`** with 13 tables (DEPLOYED 2026-05-26):
  `accounts, emails, strategies, runs, tags, email_tags, audiences, audience_members, templates, campaigns, campaign_sends, inbound_messages, audit_log`
- DDL: [`db/001_marketing_schema.sql`](db/001_marketing_schema.sql)
- Live DB dump: [`db/_live_marketing_dump.sql`](db/_live_marketing_dump.sql)
- 0 rows in any table (clean slate)

### Mail infrastructure

- **Mailcow** (WSL, separate compose, not in vibemind-stack):
  - Domain: `vibemind.space` configured (DKIM 2048-bit ready)
  - Service accounts: `marketing@vibemind.space`, `noreply@vibemind.space` (32-char random passwords in `.env`)
  - 50 test audience mailboxes (Faker-generated names, tags, signup_dates) — credentials in `docs/test-audience.json` (file lives in mailcow run folder, NOT committed)
  - **Loopback-mode active**: Postfix rejects external recipients with `554 LOOPBACK-MODE` (anti-foot-gun)

- **Mailpit (= supabase-inbucket)** as in-stack sandbox:
  - Web UI: http://127.0.0.1:54324
  - SMTP receive: 127.0.0.1:54325 (may need re-publishing — check `docker service inspect vibemind_supabase-inbucket`)
  - API: http://127.0.0.1:54324/api/v1/messages
  - Setting in `.env`: `MAILPIT_*` block

### Channel layer

- **OpenFang `openfang-channels` crate**: 42 channel modules, of which 28 are `ready` (outbound+inbound+oauth+http, non-trivial LOC) and 14 are `outbound-only`. Inventory: [`docs/openfang-channels.md`](docs/openfang-channels.md) (when restored).

### What's not here (yet)

- ❌ MarketingAgent Python code (skeleton documented but not written)
- ❌ ClawPort Marketing-Tab in Electron-Dashboard
- ❌ HTML-Mockup of UI (Schicht 2)
- ❌ IMAP-Sync worker (Mailcow → `marketing.inbound_messages`)
- ❌ AI-content-generation via Brain

## Architectural decisions (foundation-phase outputs)

| Topic | Decision |
|---|---|
| **Storage** | Supabase `marketing.*` schema (NOT separate `marketing-postgres`) |
| **Auth** | Phase 1 admin-only (service-role-key); Phase 2 Supabase-Auth + RLS |
| **Workflows** | Phase 1 self-contained Python (no n8n custom nodes); Phase 2 optional |
| **Identity bridge** | Phase 2 — Supabase-Auth-user ↔ Mailcow-mailbox auto-provisioning |
| **Sending** | Loopback-only until Production-Cutover at Homelab-Deploy |

## Inventory documents

These were lost in the submodule-reset 2026-06-02 and need rebuilding from the plan file (`~/.claude/plans/vibemind-marketing-ops.md`) + live state. Status:

- [ ] `docs/mailcow-inventory.md` — 1 domain, 53 mailboxes, DKIM ready
- [ ] `docs/rowboat-inventory.md` — NOT a CRM; AI-workflow engine, 7945 source_docs
- [ ] `docs/brain-kg-inventory.md` — 9 Qdrant collections, all empty
- [ ] `docs/pathfinder-emails-db.md` — schema heritage, 350 emails (data NOT migrated)
- [ ] `docs/openfang-channels.md` — 42 channels, 28 ready
- [ ] `docs/supabase-inventory.md` — full stack live, 27 public tables empty
- [ ] `docs/loopback-mode.md` — postfix recipient-block active + reversal command
- [ ] `docs/space-pattern.md` — BackendAgent + EVENT_TO_TOOL skeleton
- [ ] `docs/n8n-decision.md` — no custom nodes phase 1
- [ ] `docs/auth-concept.md` — admin-only phase 1

The **plan file** has all the original content from before — these docs are a derivative.

## Helper scripts (in `scripts/`, repo root)

| Script | Purpose |
|---|---|
| `_mailcow_inventory.ps1` | Full mailcow read-only inventory via API |
| `_mailcow_create_service_accounts.ps1` | Idempotent create marketing@ + noreply@ |
| `_mailcow_create_test_audience.py` | 50 Faker mailboxes with tags |
| `_mailcow_smoke_send.py` | Send personalised newsletter to all 50 |
| `_mailcow_outbound_block.sh` | Apply postfix loopback-block |
| `_mailcow_test_outbound_block.py` | Verify block (negative + positive test) |
| `_openfang_channels_inventory.py` | Static scan of 42 channel modules |
| `_qdrant_inventory.sh` | Brain-KG collections + sample payloads |
| `_rowboat_inventory.sh` | MongoDB collections in rowboat DB |

## Next steps

1. Rebuild detail docs (optional — plan file has everything)
2. Re-publish Mailpit SMTP port if missing
3. **Schicht 2: HTML Mockup** — 8 tabs (Dashboard, Campaigns, Audiences, Templates, Channels, Inbox, Analytics, Settings) with mock data fed from Supabase + Mailcow inventory + OpenFang channel statuses
4. **Schicht 3: Implementation** — MarketingAgent Python skeleton + ClawPort Marketing-Tab + IMAP sync worker
