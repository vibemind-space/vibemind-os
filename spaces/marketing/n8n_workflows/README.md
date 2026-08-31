# n8n Workflows for Marketing-Ops

DSGVO-konforme Workflows die das marketing-system orchestrieren.

## Workflows

| File | Workflow | Trigger | Status |
|------|----------|---------|--------|
| `01_inbound_classifier.json` | Inbound classifier | webhook 'inbound_received' | Schicht 6.2 |
| `02_reply_enrichment.json` | Reply enrichment via Rowboat | webhook 'inbound_classified' (classification='reply') | Schicht 6.3 (TBD) |
| `03_approval_orchestrator.json` | Approval via OpenFang | webhook 'reply_proposal_created' | Schicht 6.5 (TBD) |

## DSGVO compliance

Alle workflows folgen drei prinzipien:

1. **No external LLM calls.** Klassifikation passiert lokal via Ollama
   (`MARKETING_CLASSIFIER_ALLOW_OLLAMA=true`). Keine Daten verlassen die Box.
2. **Sanitized payloads.** n8n sieht NIE den vollen mail-body oder headers,
   nur webhook-payload (from_email + subject + pre_classification + inbound_id).
3. **Audit-trail without PII.** Jeder n8n→marketing-API call wird in
   `marketing.n8n_api_audit` geloggt (route, method, status, workflow_hint).
   Niemals der api-key oder payload-inhalt.

## Import-Anleitung (one-time)

### 1. n8n credential anlegen

In n8n UI (http://localhost:5678):

- Settings → Credentials → "+ Add"
- Type: **Header Auth**
- Name: **Marketing n8n API key**
- Header name: `Authorization`
- Header value: `Bearer ${MARKETING_N8N_API_KEY}` (use the value from your `.env`)

### 2. Workflow importieren

- Workflows → Import from File → Upload `01_inbound_classifier.json`
- Verify alle Nodes haben die "Marketing n8n API key" credential
  zugewiesen (HTTP-Request-Nodes)
- Activate workflow

### 3. Webhook subscription anlegen

Damit marketing-API events an n8n schickt:

```bash
curl -X POST http://127.0.0.1:5510/api/webhook_subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "<MARKETING_PROPOSAL_API_KEY>",
    "name": "n8n-inbound-classifier",
    "url": "http://host.docker.internal:5678/webhook/marketing-inbound-classifier",
    "events": ["inbound_received"],
    "secret": "<32+ char random string>"
  }'
```

**`host.docker.internal`** ist wichtig wenn n8n im Container läuft +
marketing-API auf host (Windows/Docker-Desktop). Auf Linux: `172.17.0.1`
oder den host-IP.

### 4. Smoke-test

Manuell ein `inbound_received` event triggern:

```bash
curl -X POST http://127.0.0.1:5510/api/webhook_subscriptions/<sub_id>/test \
  -H "Content-Type: application/json" \
  -d '{"api_key": "<MARKETING_PROPOSAL_API_KEY>"}'
```

→ n8n sollte den event empfangen + ggf. ollama-call machen + classify zurückrufen.
Im n8n-UI: Executions → letzte execution prüfen.

## Workflow 1 — Inbound Classifier

```
Webhook
  ↓
Filter: event_kind == 'inbound_received'?
  ↓
Skip wenn needs_review=false  ──→  Respond "skipped"
  ↓
Skip wenn pre_classification ∈ {bounce, opt-out}  ──→  Respond "skipped"
  ↓
POST /api/n8n/classify_helper/ollama  (server-side local inference)
  ↓
PATCH /api/n8n/inbound_messages/{id}/classify  (record result)
  ↓
Respond "classified"
```

**Skip-logic** (eingebaut für effizienz + ollama-load):
- `needs_review=false` → Worker C hat bereits high-confidence classification gemacht (bounce/opt-out). Kein n8n-call nötig.
- `pre_classification` ∈ {bounce, opt-out} → gleiches signal.
- Restliche fälle: ollama-call.

Bei 10k inbound/tag (typisches volumen für ein team) sind 60-80% bounces
und werden NICHT durch ollama geleitet. Nur die `unknown`-fälle (~20%)
brauchen LLM-inference.

## Workflow 2 — Reply Enrichment (Schicht 6.3, geplant)

```
Webhook (inbound_classified, classification='reply')
  ↓
GET /api/n8n/recipients/{from}/consent
  ↓ wenn can_send=false → log + stop
GET /api/n8n/templates  → wähle passendes reply-template
  ↓
POST Rowboat /api/v1/chat (fire-and-forget) für context
  ↓
POST /api/n8n/proposals/reply  → erstellt draft
  ↓
Curator sieht draft im Curator-Space-UI, Rowboat-context kommt async dazu
```

## Workflow 3 — Approval Orchestrator (Schicht 6.5, geplant)

```
Webhook (reply_proposal_status_changed → 'pending_approval')
  ↓
POST OpenFang /api/agents/approval-handler/message
  card: {proposal_id, draft_preview, approve_url, reject_url}
  channel: telegram (default)
  ↓
Wait for callback
  ↓
Branch:
  approved  → POST /api/proposals/{id}/approve  (with signed token)
  rejected  → POST /api/proposals/{id}/reject
```

## Troubleshooting

### Webhook never fires

1. Check subscription is active:
   `curl http://127.0.0.1:5510/api/webhook_subscriptions?api_key=...`
2. Check webhook-delivery worker is running:
   `Get-Process | Where-Object { $_.MainWindowTitle -like "*webhook*" }`
3. Check `marketing.webhook_deliveries` for failed-attempts:
   ```sql
   SELECT * FROM marketing.webhook_deliveries
   WHERE delivered_at IS NULL AND retry_count > 0
   ORDER BY attempted_at DESC LIMIT 10;
   ```

### Ollama classify returns 503

- Check Ollama is running: `curl http://127.0.0.1:11434/api/tags`
- Check model is loaded: should show `phi3:mini` or your configured model
- Check `MARKETING_CLASSIFIER_ALLOW_OLLAMA=true` is in the marketing-API process env
- If you restart marketing-API, the env must be loaded BEFORE the spawn

### n8n call returns 409 "curator-classified"

- The inbound message was already classified by the curator (Schicht 6.4
  UI). n8n MUST NOT override curator decisions. This is by design.

### Audit log explosion

- `marketing.n8n_api_audit` retention: 90 days, prune via
  `SELECT marketing.prune_n8n_audit();` (daily cron recommended).
