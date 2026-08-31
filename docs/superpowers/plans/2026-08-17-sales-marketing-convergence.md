# Sales ↔ Marketing Convergence — REVISED to infra-only (2026-08-17)

> **Status: superseded.** The original plan (share marketing's gated send / channel /
> approval **code**) was abandoned after Task E1 surfaced a premise-breaking fact. This
> document records why, and the small infra-only path that replaces it.

## Why the code-convergence plan was dropped

Reading `spaces/marketing/tools/_send_paranoid.py` and `_send_openfang.py` in full showed
that **all three** marketing delivery paths are the same shape: an internal
investor/broadcast safety system, not a general service.

- **`ALLOWED_DOMAINS = frozenset({"vibemind.space"})`** — a hard domain lock. Every send
  to a non-`@vibemind.space` address is rejected at the allowlist gate.
- Every gate is **campaign_id / audience_id-shaped**: snapshot recipients from
  `marketing.audience_members`, claim rows in `marketing.campaign_sends` /
  `..._openfang`, resolve a `marketing.campaigns` row for sender/template/channel,
  confirm-token over the recipient set, per-campaign rate limit, `campaign.status` flip.
- **Approval** (`tools/approval.py`) is `approve_audience_proposal` — audience/broadcast-
  shaped, not a general "sign off on this outbound draft".

**Sales does external cold-outreach to arbitrary prospect domains.** Marketing's paths
would reject 100% of it at the allowlist, and don't accept a non-campaign, single-
recipient send at all. The surface similarity ("both send email / use channels / have
approval") hid fundamentally different architectures: **internal broadcast vs external
outreach.** Forcing one through the other would mean gutting the allowlist or synthesizing
throwaway campaign rows in the live DB — both defeat the safety design.

The E1 scaffold (`transactional_send.py`) was reverted (commit `8ea5a83`).

## What actually converges: infrastructure, not code

The two spaces stay separate and each owns its own delivery logic. They share only the
**VibeMind infrastructure/transport**, entirely through env — **zero marketing (mkt-opus)
code edits, zero cross-repo import.**

`spaces/sales` is already prepared for exactly this: its `.env.example`,
`VIBEMIND_ADAPTATION.md`, and `docker-compose.vibemind.yml` already carry the VibeMind
env surface. "Wiring" = filling those vars with the real endpoints.

### Env → VibeMind endpoint mapping (the wiring recipe)

Set these in `spaces/sales/.env` (gitignored — secrets stay off-repo). Values marked
`<…>` are machine-specific; fill from the outer repo's `.env` / running services.

| sales env var | Points at | Value |
|---|---|---|
| `OPENAI_BASE_URL` | local LLM (Ollama/vLLM/LiteLLM) | `<local-llm>/v1` — smoke-tested per VIBEMIND_ADAPTATION.md |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | Mailcow (outreach send + iCal) | `<mailcow-host>` / 587 / `<user>` / `<secret>` / `sales@vibemind.space` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Proxmox Supabase (own `sales` schema: `leads/deals/activities/personas`) | `<proxmox-host>:8000` / `<key>` |
| `MCP_GATEWAY_URL` / `MCP_GATEWAY_AUTH_TOKEN` | OpenFang / Docker-MCP toolkit (channels, fetch/search) | **confirm:** OpenFang `:4200` MCP endpoint vs the Docker MCP gateway `:8808` — sales POSTs `{MCP_GATEWAY_URL}/tools/call` |
| `WHATSAPP_API_URL` / `WHATSAPP_API_TOKEN` / `WHATSAPP_SENDER` | WhatsApp bridge (replaces `send_sms`, per D-E2) | `<bridge>` / `<token>` / `<company number>` |
| `VOICEBOX_API_URL` | Voicebox (voice notes + call transcripts) | `<voicebox>` |

### Steps

1. Copy `spaces/sales/.env.example` → `spaces/sales/.env`, fill the table above from the
   outer `.env` and running services.
2. Point `SUPABASE_URL` at the same Proxmox Supabase marketing uses; create a separate
   `sales` schema (do NOT reuse `marketing.*`). CRM alignment (`leads`↔`accounts`) is
   deferred — see D-E1.
3. Apply the LLM base-url (D-E5) — one line, already proven.
4. Drop `send_sms` / Twilio (D-E2); route to `send_whatsapp` via the bridge.
5. Confirm the `MCP_GATEWAY_URL` target with a `dry_run` `/tools/call` round-trip.
6. Do **not** touch `spaces/marketing/**` — marketing owns its internal broadcast; sales
   owns its outreach. Only Mailcow / OpenFang / Supabase / local-LLM are shared, as infra.

## Open decisions (unchanged)

- **D-E1** CRM substrate: keep sales' own `sales` schema; share only the Supabase
  instance. (Recommended; no schema merge.)
- **D-E2** SMS → drop Twilio, WhatsApp only.
- **D-E5** local LLM base-url — apply anytime.

## Net

No marketing edits, no submodule↔parent Python coupling, far less work than the code-merge
plan, and it respects the real architectural split. The convergence is an operational
env-wiring task on the sales side, which sales was already built to accept.
