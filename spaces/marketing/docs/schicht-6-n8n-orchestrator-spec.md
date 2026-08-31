# Schicht 6 — n8n + Rowboat + Mailcow Orchestration Spec

**Status:** Final-Plan, GO für Implementation.
**Datum:** 2026-06-09 (final-rev).
**Frage die geklärt wurde:** Wo macht n8n als Layer Sinn, wo NICHT, und wie
vermeiden wir doppelte source-of-truth.

---

## Felix' use-case (verbatim)

> Email rein → n8n (sortieren) → Rowboat könnte ich mir zb vorstellen
> Rowboat daten überprüfen / anpassen
> Rowboat → Mailcow → Approval → raus

Roundtrip-pipeline, NICHT klassisches Brevo-outbound.

---

## Final-Entscheidungen (alle 4 + extra)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | Inbound-routing: n8n alles oder split? | **Option 3** — Worker C macht pre-tagging (5 deterministic regex-rules: DSN-bounces, List-Unsubscribe, In-Reply-To, spam-headers). n8n sieht ALL inbound mit `pre_classification` column und kann override. Bounces (60-80% volumen) schleifen schnell durch, n8n hat trotzdem voll-sicht. |
| 2 | Rowboat sync oder async? | **Async** — n8n triggert Rowboat-call, Rowboat schreibt result-event zurück. Marketing-API blockt nie auf Rowboat-latenz. |
| 3 | Approval-card via Telegram oder Discord? | **OpenFang unified** — langfristig OpenFang als single approval-stage. Telegram (heute) und Discord (Schicht 4) sind nur OpenFang-channels. n8n ruft `request_approval` mit channel-name, OpenFang routet. |
| 4 | Curator-UI im mockup oder eigener space? | **Eigener Space mit eigner UI** — für daten-validierung. Marketing-mockup bleibt für outbound, neuer "Curator"-space für inbound-review. |

---

## Drei-Schichten-Auth-Pattern (NEU)

n8n kann NICHT die volle marketing-API-power haben (template-bodies, secrets,
send-pipeline). Stattdessen drei Schichten:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: MARKETING_PROPOSAL_API_KEY  (full, OPERATOR ONLY)  │
│  → mintet confirm-tokens                                     │
│  → configuriert channels, flippt enabled-flags               │
│  → liest secrets, raw template-bodies                        │
│  → Nutzer: Felix manuell, Marketing-mockup mit login        │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: MARKETING_N8N_API_KEY  (low-privilege, n8n)        │
│  Read-only checks:                                           │
│   - GET /api/templates (list, ohne body)                     │
│   - GET /api/recipients/{email}/consent (boolean summary)    │
│   - GET /api/recipients/{email}/allowed?channel=X (boolean)  │
│   - GET /api/inbound_messages?classification=null            │
│   - GET /api/inbound_messages/{id} (sanitized, no PII-leak)  │
│  Validated writes (schema + audit):                          │
│   - PATCH /api/inbound_messages/{id}/classify                │
│   - POST  /api/proposals/reply                               │
│   - POST  /api/proposals/{id}/request_approval               │
│  REFUSED:                                                    │
│   - POST /api/campaigns/{id}/send-paranoid (needs Layer 1)   │
│   - POST/PATCH /api/templates                                │
│   - PATCH /api/channel_config                                │
│   - POST /api/proposals/{id}/approve (only approval-callback)│
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: MARKETING_TRACKING_SECRET  (URL-signing, internal) │
│  → nur für /t/o/, /t/c/ token-verify                         │
│  → NIE in n8n, NIE in Curator-UI                             │
└─────────────────────────────────────────────────────────────┘
```

**Wichtig:** Die 6 ❌ aus dem urspr. spec werden so geregelt:

| ❌ aus altem spec | n8n bekommt | Wo bleibt das original |
|---|---|---|
| Template-storage | `GET /api/templates` (id+name+channel, KEIN body) | `marketing.templates.body_html` |
| Send-pipeline | `POST /api/proposals/{id}/request_approval` (triggert flow) | `_send_paranoid.py`, nur per Layer-1-token |
| Recipient-allowlist | `GET /api/recipients/{email}/allowed?channel=X` (bool) | `marketing.channel_recipient_allowlist` (signed HMAC) |
| DSGVO-state | `GET /api/recipients/{email}/consent` (summary {can_send, can_track, opted_out_at}) | `marketing.emails.consent_*` columns |
| Bot-tokens | OpenFang-API ruft channel_send tool | `~/.openfang/config.toml` (DPAPI) |
| DB-direkter-write | nur PATCH/POST-routes mit schema-validation | psql/supabase-direct = Layer 1 only |

---

## Was wir HEUTE haben

```
                    ┌──────────────┐
                    │ Mailcow IMAP │ (marketing@vibemind.space + noreply@)
                    └──────┬───────┘
                           │ poll 60s
                           ▼
                    ┌──────────────────┐
                    │ Worker C          │ spaces/marketing/sync/worker_imap_sync.py
                    │ imap_sync.py      │
                    └──────┬───────────┘
                           │ INSERT
                           ▼
                    ┌──────────────┐
                    │ marketing.    │ message_id, from_email, subject, body,
                    │ inbound_      │ in_reply_to (für reply-linkage)
                    │ messages      │
                    └──────┬───────┘
                           │ trigger (007)
                           ▼
                    ┌──────────────┐
                    │ reply_linkage │ → set campaign_sends.replied_at
                    └──────────────┘

OUTBOUND:
  marketing.campaigns + audiences + templates
    → /api/campaigns/{id}/send-paranoid
    → _send_paranoid.py (12-gate, Mailcow SMTP :465)
```

---

## Was wir BAUEN (Final-flow)

```
Step 1: EMAIL REIN [HEUTE schon]
    ▸ Mailcow IMAP → Worker C → marketing.inbound_messages

Step 2: WORKER C PRE-TAGGING [NEU, Schicht 6.1d]
    ▸ Worker C parst headers + body bei INSERT:
      - DSN bounce header → pre_classification='bounce'
      - List-Unsubscribe-Post body OR mailto:unsubscribe → 'opt-out'
      - In-Reply-To set + matches campaign_sends.message_id → 'reply'
      - X-Spam-Score > threshold OR SPF/DKIM fail → 'spam'
      - else → 'unknown'
    ▸ Schreibt pre_classification + pre_classified_by='worker_c:regex_v1'

Step 3: WEBHOOK-EMIT [NEU, Schicht 6.1]
    ▸ Trigger auf inbound_messages INSERT:
      emit_webhook_event('inbound', payload, ...)
    ▸ Bounce mails: needs_review=false (skip n8n by convention)
    ▸ Andere: needs_review=true → n8n picks up via webhook subscription

Step 4: N8N CLASSIFIER [NEU, Schicht 6.2]
    ▸ n8n Workflow 1 subscribed zu 'inbound' events
    ▸ Skip wenn pre_classification='bounce' OR needs_review=false
    ▸ Sonst: regex-rules + ggf. LLM-fallback
    ▸ Override pre_classification mit final classification
    ▸ HTTP PATCH /api/inbound_messages/{id}/classify

Step 5: ROWBOAT ENRICHMENT (ASYNC) [NEU, Schicht 6.3]
    ▸ Wenn classification='reply' → n8n Workflow 2 trigger
    ▸ n8n POST Rowboat /api/v1/{projectId}/chat
        message: "Was weißt du über {from_email}?"
    ▸ n8n WARTET NICHT — schreibt rowboat_request_id in DB
    ▸ Rowboat callback (eigener webhook) → schreibt context
    ▸ Marketing.proposals erstellt mit rowboat_context als jsonb

Step 6: CURATOR-SPACE [NEU, Schicht 6.4]
    ▸ Eigener space mit eigener UI (NICHT im mockup)
    ▸ Tab "Inbound Queue" — alle unclassified + reply-needs-review
    ▸ Tab "Reply Proposals" — drafts mit rowboat-context, edit + approve
    ▸ Tab "Validation" — daten-validierung der enrichment
    ▸ Auth: Layer 1 (PROPOSAL_API_KEY) — curator hat full power
    ▸ Edit-actions schreiben mit actor='curator:felix'

Step 7: APPROVAL-FLOW [NEU, Schicht 6.5]
    ▸ Curator klickt "Request Approval"
    ▸ marketing-API: POST /api/proposals/{id}/request_approval
    ▸ n8n Workflow 3 picks up event
    ▸ OpenFang unified approval-API: send card via configured channel
      (zunächst Telegram, später Discord wenn Schicht 4 live)
    ▸ User antwortet via Telegram/Discord → OpenFang callback
    ▸ Callback POST /api/proposals/{id}/approve mit signed-token
    ▸ Approval-handler ruft _send_paranoid.run() (12-gate, Mailcow → raus)
```

---

## Source-of-truth-Hierarchie

| Datum | Source-of-Truth | Wer schreibt | Wer liest |
|---|---|---|---|
| Inbound raw | `marketing.inbound_messages` | Worker C (IMAP) | n8n, Rowboat-sync, Curator |
| Pre-classification | `marketing.inbound_messages.pre_classification` | Worker C | n8n (skip-decision), Curator |
| Final classification | `marketing.inbound_messages.classification` | n8n via PATCH, Curator | Curator-UI, dashboard |
| Tags/segments | `marketing.email_tags` | Curator via PATCH | send-worker, dashboard |
| Person-knowledge | Rowboat /knowledge | manual upload + sync | n8n (RAG-query), Curator |
| Reply-draft | `marketing.proposals` | Curator (Layer 1) | n8n approval, send-worker |
| Approval-state | `marketing.proposals.status` | approval-handler | send-worker, audit |
| Send-result | `marketing.campaign_sends` | `_send_paranoid` | webhook-bus, dashboard |
| Lifecycle events | `marketing.webhook_events` | send-worker, tracking, inbound-trigger | n8n, external subs |

**Regel:** **Marketing-DB ist authoritative.** Rowboat ist read-only-RAG.
n8n ist orchestration-glue ohne eigenen storage. Curator-UI ist Layer-1
operator-UI mit volle rechte.

---

## Migrations

### Migration 026: inbound classification + pre-tagging

```sql
ALTER TABLE marketing.inbound_messages
    ADD COLUMN pre_classification text,           -- bounce|opt-out|reply|spam|unknown
    ADD COLUMN pre_classified_by text,            -- 'worker_c:regex_v1'
    ADD COLUMN pre_classified_at timestamptz,
    ADD COLUMN classification text,               -- final, can override pre_classification
    ADD COLUMN classified_by text,                -- 'n8n:flow-v3' or 'curator:felix'
    ADD COLUMN classified_at timestamptz,
    ADD COLUMN classification_confidence real,
    ADD COLUMN needs_review boolean DEFAULT true; -- false for auto-handled bounces

CREATE INDEX idx_inbound_needs_review
    ON marketing.inbound_messages (received_at)
    WHERE needs_review = true AND classification IS NULL;

CREATE INDEX idx_inbound_pre_class
    ON marketing.inbound_messages (pre_classification, received_at);

-- Audit constraint: classified_by must differ from pre_classified_by
-- if classification is set (otherwise it's just a copy of pre_classification)
ALTER TABLE marketing.inbound_messages
    ADD CONSTRAINT inbound_classification_audit
    CHECK (
        classification IS NULL
        OR classified_by IS NOT NULL
    );

-- Trigger: emit webhook event on classification change
CREATE OR REPLACE FUNCTION marketing._emit_inbound_classified() RETURNS trigger AS $$
BEGIN
    IF NEW.classification IS DISTINCT FROM OLD.classification THEN
        PERFORM marketing.emit_webhook_event(
            'inbound_classified',
            jsonb_build_object(
                'inbound_id', NEW.id,
                'from_email', NEW.from_email,
                'classification', NEW.classification,
                'classified_by', NEW.classified_by,
                'pre_classification', NEW.pre_classification
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Migration 027: reply-proposals

```sql
ALTER TABLE marketing.proposals
    ADD COLUMN proposal_type text DEFAULT 'campaign', -- 'campaign'|'reply'|'unsubscribe-confirm'
    ADD COLUMN reply_to_inbound_id uuid REFERENCES marketing.inbound_messages(id) ON DELETE SET NULL,
    ADD COLUMN draft_subject text,
    ADD COLUMN draft_body_text text,
    ADD COLUMN draft_body_html text,
    ADD COLUMN draft_to_email citext,
    ADD COLUMN draft_template_id uuid REFERENCES marketing.templates(id),
    ADD COLUMN rowboat_request_id text,                -- async Rowboat-call tracking
    ADD COLUMN rowboat_context jsonb,                   -- archived RAG hits
    ADD COLUMN rowboat_received_at timestamptz;

CREATE INDEX idx_proposals_inbound_reply
    ON marketing.proposals (reply_to_inbound_id)
    WHERE reply_to_inbound_id IS NOT NULL;
```

### Migration 028: n8n low-privilege API key audit

```sql
CREATE TABLE IF NOT EXISTS marketing.n8n_api_audit (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    route           text NOT NULL,
    method          text NOT NULL,
    payload_size    int,
    response_status int,
    workflow_hint   text,                              -- X-N8N-Workflow header
    -- NEVER store the api_key or full payload (PII concerns)
);
CREATE INDEX idx_n8n_api_audit_recent
    ON marketing.n8n_api_audit (occurred_at DESC);

-- Retention: 90 days
CREATE OR REPLACE FUNCTION marketing.prune_n8n_audit(p_keep_days int DEFAULT 90)
RETURNS int AS $$
DECLARE
    v_count int;
BEGIN
    WITH d AS (
        DELETE FROM marketing.n8n_api_audit
         WHERE occurred_at < now() - make_interval(days => p_keep_days)
        RETURNING 1
    ) SELECT COUNT(*) INTO v_count FROM d;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;
```

---

## Facade-endpoints für n8n (final-list)

Alle gated by `MARKETING_N8N_API_KEY` via `Authorization: Bearer <key>` header.

### Read-only checks

```python
@app.get("/api/n8n/templates")
def n8n_templates_list(_auth = Depends(require_n8n_key)):
    """List templates without body. Used by n8n for template-selection."""
    rows = _db.query_via_docker(
        "SELECT id::text, name, channel, tracking_enabled "
        "FROM marketing.templates "
        "WHERE deprecated_at IS NULL "
        "ORDER BY name"
    )
    return {"success": True, "data": rows}


@app.get("/api/n8n/recipients/{email}/consent")
def n8n_consent_check(email: str, _auth = Depends(require_n8n_key)):
    """Boolean summary, never timestamps (PII minimization)."""
    row = _db.query_one(
        f"SELECT consent_given_at IS NOT NULL AS can_send, "
        f"       tracking_consent_given_at IS NOT NULL "
        f"           AND tracking_consent_revoked_at IS NULL AS can_track, "
        f"       unsubscribed_at IS NOT NULL AS opted_out, "
        f"       smtp_valid = 0 OR bounce_count > 0 AS hard_bounced "
        f"FROM marketing.emails "
        f"WHERE email = {_db._sql_literal(email)}"
    )
    if not row:
        return {"success": True, "data": {"can_send": False, "can_track": False,
                                           "opted_out": False, "hard_bounced": False,
                                           "exists": False}}
    return {"success": True, "data": {**row, "exists": True}}


@app.get("/api/n8n/recipients/{email}/allowed")
def n8n_allowlist_check(email: str, channel: str = Query(...),
                        _auth = Depends(require_n8n_key)):
    """Channel-specific allowlist boolean. No HMAC-sig in response."""
    # For email channel: domain in ALLOWED_DOMAINS frozenset + consent
    # For other channels: row in channel_recipient_allowlist + sig verify
    # ... implementation reuses existing helpers
    return {"success": True, "data": {"allowed": bool, "reason": str}}


@app.get("/api/n8n/inbound_messages")
def n8n_inbound_list(classification: Optional[str] = Query(None),
                     pre_classification: Optional[str] = Query(None),
                     needs_review: bool = Query(True),
                     limit: int = Query(50, le=200),
                     _auth = Depends(require_n8n_key)):
    """List inbound messages for n8n classification queue."""
    where = ["received_at > now() - interval '7 days'"]
    if classification == "null":
        where.append("classification IS NULL")
    elif classification:
        where.append(f"classification = {_db._sql_literal(classification)}")
    if pre_classification:
        where.append(f"pre_classification = {_db._sql_literal(pre_classification)}")
    if needs_review:
        where.append("needs_review = true")
    rows = _db.query_via_docker(
        f"SELECT id::text, from_email, subject, "
        f"       received_at::text AS received_at, "
        f"       pre_classification, classification "
        f"FROM marketing.inbound_messages "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY received_at "
        f"LIMIT {int(limit)}"
    )
    return {"success": True, "data": rows}


@app.get("/api/n8n/inbound_messages/{msg_id}")
def n8n_inbound_get(msg_id: str, _auth = Depends(require_n8n_key)):
    """Sanitized single message. body_html stripped of secrets/auth-tokens
    via regex pre-filter so n8n never sees unsub-tokens leaked back."""
    # ... sanitize body before return
```

### Validated writes (schema + audit)

```python
@app.patch("/api/n8n/inbound_messages/{msg_id}/classify")
def n8n_classify(msg_id: str, payload: dict, _auth = Depends(require_n8n_key)):
    """n8n classifies an inbound message.
    Validates: classification ∈ known set, confidence ∈ [0,1].
    Refuses if already classified by curator (precedence rule)."""
    valid = {"bounce", "opt-out", "reply", "spam", "question", "other"}
    cl = payload.get("classification")
    if cl not in valid:
        return JSONResponse({"success": False, "message": f"invalid classification"}, 400)
    confidence = float(payload.get("confidence", 0))
    workflow = payload.get("workflow", "n8n:unknown")[:100]

    # Precedence: don't overwrite curator-classifications
    existing = _db.query_one(
        f"SELECT classified_by FROM marketing.inbound_messages "
        f"WHERE id = {_db._sql_literal(msg_id)}::uuid"
    )
    if existing and existing.get("classified_by", "").startswith("curator:"):
        return JSONResponse({"success": False,
                              "message": "curator-classified, n8n refused override"}, 409)

    _db.execute_via_docker(
        f"UPDATE marketing.inbound_messages "
        f"SET classification = {_db._sql_literal(cl)}, "
        f"    classified_by = {_db._sql_literal('n8n:' + workflow)}, "
        f"    classified_at = now(), "
        f"    classification_confidence = {confidence} "
        f"WHERE id = {_db._sql_literal(msg_id)}::uuid"
    )
    # Audit + emit (trigger handles emit)
    _audit_n8n_call("PATCH", "/api/n8n/inbound_messages/classify", 200, workflow)
    return {"success": True}


@app.post("/api/n8n/proposals/reply")
def n8n_create_reply_proposal(payload: dict, _auth = Depends(require_n8n_key)):
    """n8n creates a reply-proposal draft for curator-review.
    All fields validated, no raw SQL pass-through."""
    required = ["reply_to_inbound_id", "draft_to_email", "draft_subject", "draft_body_text"]
    for k in required:
        if not payload.get(k):
            return JSONResponse({"success": False, "message": f"missing {k}"}, 400)

    # Verify inbound_id exists + not already proposed
    inbound = _db.query_one(
        f"SELECT id FROM marketing.inbound_messages "
        f"WHERE id = {_db._sql_literal(payload['reply_to_inbound_id'])}::uuid"
    )
    if not inbound:
        return JSONResponse({"success": False, "message": "inbound not found"}, 404)

    existing = _db.query_one(
        f"SELECT id FROM marketing.proposals "
        f"WHERE reply_to_inbound_id = {_db._sql_literal(payload['reply_to_inbound_id'])}::uuid "
        f"  AND status NOT IN ('rejected', 'sent')"
    )
    if existing:
        return JSONResponse({"success": False,
                              "message": "open proposal exists for inbound"}, 409)

    # Build draft with template_id if given
    # ... INSERT logic with audit
    return {"success": True, "data": {"id": new_proposal_id, "status": "draft"}}


@app.post("/api/n8n/proposals/{proposal_id}/request_approval")
def n8n_request_approval(proposal_id: str, payload: dict,
                         _auth = Depends(require_n8n_key)):
    """n8n triggers approval-flow. Channel-name validated.
    OpenFang gets the actual card-send via its handoff_approval_request."""
    valid_channels = {"telegram", "discord", "openfang"}
    ch = payload.get("channel", "openfang")
    if ch not in valid_channels:
        return JSONResponse({"success": False,
                              "message": f"invalid channel"}, 400)

    # Lookup proposal + set status='pending_approval'
    # ... triggers OpenFang via channel_send to a dedicated 'approval-handler' agent
    # which sends card with APPROVE/REJECT buttons
    return {"success": True, "data": {"status": "pending_approval", "channel": ch}}
```

---

## Curator-Space (eigene UI)

**Pfad:** `spaces/marketing/curator/` (parallel zu `mockup/`)

**Stack:** Alpine.js + Tailwind (gleicher Stack wie mockup, weniger context-switch).

**Tabs:**
1. **Inbound Queue** — alle `needs_review=true AND classification IS NULL`
2. **Reply Proposals** — alle proposals mit `proposal_type='reply' AND status='draft'`
3. **Validation** — daten-validierung der enrichment-results
4. **Audit** — n8n_api_audit-log + proposals-audit

**Routes:**
```
GET  /curator/                       → SPA shell
GET  /api/curator/inbound_queue      → mit Layer-1 auth
GET  /api/curator/proposals          → mit Layer-1 auth
POST /api/curator/proposals/{id}/edit → mit Layer-1 auth
POST /api/curator/proposals/{id}/request_approval → mit Layer-1 auth
```

**Layer 1 (PROPOSAL_API_KEY) only** — Curator-UI hat volle rechte über
proposals, kann manuell klassifizieren, override n8n-decisions.

---

## n8n Workflows (3 total)

### Workflow 1: Inbound-Classifier
```
Trigger: HTTP webhook /n8n/inbound-arrived
  ↓
Skip-condition: pre_classification IN ('bounce', 'opt-out')
  ↓ (sonst)
Switch on subject/body/headers (regex-rules)
  ↓
HTTP PATCH /api/n8n/inbound_messages/{id}/classify
  X-N8N-Workflow: inbound-classifier-v1
```

### Workflow 2: Reply-Enrichment (async)
```
Trigger: webhook 'inbound_classified' WHERE classification='reply'
  ↓
HTTP GET /api/n8n/recipients/{from}/consent
  ↓
{can_send=false} → log + stop
{can_send=true}  ↓
HTTP GET /api/n8n/templates → pick relevant
  ↓
HTTP POST Rowboat /api/v1/chat (FIRE-AND-FORGET)
  message: "Context für {from_email}, vorschlag template?"
  callback_url: /api/curator/rowboat_callback/{request_id}
  ↓
HTTP POST /api/n8n/proposals/reply
  body: {reply_to_inbound_id, template_id, draft_subject, draft_body_text,
         rowboat_request_id}
  ↓
Done — Curator sieht proposal in queue, Rowboat-context kommt async dazu
```

### Workflow 3: Approval-Orchestrator
```
Trigger: webhook 'proposal.request_approval'
  ↓
HTTP POST OpenFang /api/agents/approval-handler/message
  card: {proposal_id, draft_preview, approve_url, reject_url}
  channel: telegram (default) or as configured
  ↓
Wait for callback (OpenFang sends back via webhook)
  ↓
Branch:
  approved → POST /api/proposals/{id}/approve (with signed-token from OpenFang)
  rejected → POST /api/proposals/{id}/reject + audit
  ↓
Notify result back to Curator-UI via webhook
```

---

## Schicht-Reihenfolge (final)

```
Schicht 6.1 (~4h) — Foundation
  ├── Migration 026 (classification cols + needs_review + trigger)
  ├── Migration 027 (proposal extensions for reply)
  ├── Migration 028 (n8n_api_audit table + retention)
  ├── MARKETING_N8N_API_KEY in .env + auth-helper require_n8n_key
  └── 8 tests (auth, classify-validate, reply-create, allowlist-check)

Schicht 6.2 (~6h) — Worker C pre-tagging + n8n classifier
  ├── Worker C extension: DSN-bounce-parser (RFC 3464), List-Unsubscribe-detector
  ├── Worker C writes pre_classification + needs_review on INSERT
  ├── Facade endpoints: /api/n8n/inbound_messages + /classify
  ├── n8n Workflow 1 deployed (via API import or manual)
  └── 6 tests (DSN-parser, opt-out-detector, classify-override-precedence)

Schicht 6.3 (~8h) — Rowboat async enrichment
  ├── Rowboat-client helper (lazy + async + retry)
  ├── Facade endpoints: /api/n8n/recipients/{}/consent + /allowed + /templates
  ├── /api/curator/rowboat_callback/{request_id} endpoint
  ├── n8n Workflow 2 deployed
  └── 7 tests (consent-summary, rowboat-timeout, async-callback)

Schicht 6.4 (~6h) — Curator-Space UI
  ├── spaces/marketing/curator/index.html + Alpine.js components
  ├── Tabs: inbound queue, reply proposals, validation, audit
  ├── Curator-API routes (Layer 1)
  ├── Static-mount at /curator/
  └── 4 tests (auth-gated, schema-validate, override-n8n)

Schicht 6.5 (~6h) — Approval-flow
  ├── OpenFang approval-handler agent (new agent.toml)
  ├── Facade endpoint: /api/n8n/proposals/{id}/request_approval
  ├── Approval-callback endpoint with signed-token verify
  ├── n8n Workflow 3 deployed
  ├── Telegram-card-template (markdown with approve/reject deep-links)
  └── 6 tests (approval-flow-e2e, signed-token-verify, channel-routing)

Schicht 6.6 (~3h) — Retention + DSGVO + cleanup
  ├── retention für inbound_messages (180d default)
  ├── retention für n8n_api_audit (90d)
  ├── retention für proposals (365d für approved/rejected)
  ├── auto-submitted-loop-prevention
  └── DSGVO-doc (data-flow + erasure-procedure)

Total: ~33h
```

---

## Risiken / open questions

1. **n8n-credentials-storage.** n8n's SQLite-store ist nicht DPAPI. Wenn
   n8n compromised → `MARKETING_N8N_API_KEY` leakt. **Mitigation:** key
   nur read-only-checks + 3 schmale writes. Kein send-trigger, kein
   template-body, kein full-PII-read. Worst-case n8n-leak = attacker
   kann classifications schreiben (audit zeigt n8n-actor, sofort sichtbar).

2. **Auto-reply-loops.** Auto-reply triggert auto-reply → endlos.
   **Mitigation:** Worker C refused `Auto-Submitted: auto-replied` header,
   reply-proposal-creation prüft `In-Reply-To`-chain max depth 1.

3. **Rowboat-availability.** Rowboat down = enrichment fails = proposals
   ohne context. **Mitigation:** workflow-step try-catch, fallback
   "no context available" + curator sieht plain proposal.

4. **Race auf classification.** Curator klassifiziert während n8n parallel.
   **Mitigation:** `classified_by`-precedence — curator > n8n > pre. n8n's
   PATCH refused mit 409 wenn `classified_by` startswith 'curator:'.

5. **OpenFang unified approval — Telegram + Discord parallel?** Beide
   gleichzeitig erlauben oder nur einen aktiv? **Antwort:** Approval-flow
   speichert configured channel in `proposals.approval_channel`, n8n-workflow
   liest das + routet zu OpenFang mit channel-arg. Default 'telegram'.

6. **Curator-UI cookie-auth vs API-key.** Layer 1 ist heute via query-param
   api_key. Curator-UI sollte session-cookie + CSRF haben.
   **Mitigation Schicht 6.4:** simple session-store mit HMAC-signed cookie,
   90min TTL. Production-grade später.

---

## Was NICHT in Schicht 6 ist

- ❌ Multi-tenant / Workspaces (Schicht 7)
- ❌ WYSIWYG-template-editor (Schicht 7)
- ❌ IP-warmup-scheduler (Schicht 7)
- ❌ Contact-scoring beyond engagement (Schicht 7)
- ❌ Media-library (Schicht 7)
- ❌ Calendly/Stripe/HubSpot externe triggers (kann später als zusätzliche
   n8n-workflows ohne core-changes)
