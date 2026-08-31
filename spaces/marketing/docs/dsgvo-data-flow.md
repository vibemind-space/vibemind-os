# DSGVO Data-Flow Documentation

Marketing-Ops + Schicht 6 (n8n + Rowboat + Curator-Space).

**Stand: 2026-06-09.**

Dieses Dokument erfüllt die Dokumentationspflicht aus DSGVO **Art. 30**
(Verzeichnis von Verarbeitungstätigkeiten) für das Marketing-System.

---

## 1. Verarbeitungstätigkeit

| Bereich | Inhalt |
|---|---|
| Verantwortlicher | Felix (operator), VibeMind |
| Zweck der Verarbeitung | Marketing-outreach (campaigns) + inbound-curation (replies, support) |
| Rechtsgrundlage | Art. 6 Abs. 1 lit. a (Einwilligung) für outreach, Art. 6 Abs. 1 lit. f (berechtigtes Interesse) für reply-handling |
| Betroffene Personen | Empfänger von Marketing-Mails, Absender von Inbound-Mails |
| Datenkategorien | E-Mail-Adressen, Namen (sofern in From-Field), Subject + Body von Inbound-Mails, Tracking-events (opens, clicks) bei Einwilligung |

---

## 2. Datenflüsse

### Outbound (Campaign)

```
Operator (Curator-UI)
    ↓ erstellt Campaign + Audience + Template
DB (marketing.campaigns, .audiences, .templates)
    ↓ /api/campaigns/{id}/send-paranoid (LIVE mode, mit confirm_token)
_send_paranoid.py (12-gate Stack)
    ↓ - prüft consent_given_at IS NOT NULL
    ↓ - prüft tracking_consent_given_at für Pixel/Link-Tracking
    ↓ - prüft unsubscribed_at IS NULL
Mailcow SMTP :465
    ↓ Empfänger erhält Mail
    ↓ optional: Pixel-Fetch → /t/o/{token}   (nur wenn tracking_consent_given_at)
    ↓ optional: Click → /t/c/{token}?u=...   (nur wenn tracking_consent_given_at)
DB (marketing.email_opens, .email_clicks)
    ↓ Trigger: marketing.emit_webhook_event('open' / 'click' / 'sent' / 'bounce')
webhook_events → webhook_deliveries → external HTTP-receiver
```

### Inbound (Reply-Curation)

```
Empfänger antwortet auf @vibemind.space
    ↓ IMAP
Mailcow inbox
    ↓ Worker C (worker_imap_sync.py, polls 60s)
    ↓ pre_classify() — RFC 3464 DSN-detection, opt-out keywords, In-Reply-To matching
DB (marketing.inbound_messages, pre_classification + needs_review)
    ↓ Trigger: emit_webhook_event('inbound_received')
n8n Workflow 1 (Inbound-Classifier)
    ↓ skip wenn pre_classification ∈ {bounce, opt-out}
    ↓ sonst: POST /api/n8n/classify_helper/ollama (LOCAL Ollama, kein external LLM)
    ↓ PATCH /api/n8n/inbound_messages/{id}/classify
DB (classification set)
    ↓ Trigger: emit_webhook_event('inbound_classified')
n8n Workflow 2 (Reply-Enrichment) — nur bei classification='reply'
    ↓ GET /api/n8n/recipients/{email}/consent (bool summary)
    ↓ wenn can_send=false → stop (kein draft)
    ↓ POST Rowboat /api/v1/chat (LOCAL :3100, no external)
    ↓ POST /api/n8n/proposals/reply (draft created)
DB (marketing.reply_proposals)
    ↓ Trigger: emit_webhook_event('reply_proposal_created')
Curator (Curator-UI)
    ↓ Reviewt + editiert + POST /api/curator/reply_proposals/{id}/request_approval
DB (status='pending_approval', approval_token_hash set)
    ↓ Trigger: emit_webhook_event('reply_proposal_status_changed')
n8n Workflow 3 (Approval-Orchestrator)
    ↓ POST OpenFang /api/agents/approval-handler/message
OpenFang approval-handler agent
    ↓ channel_send (Telegram chat_id aus TELEGRAM_ALLOWED_CHAT_IDS)
Operator empfängt Card im Telegram
    ↓ APPROVE-Reply → POST /api/reply_proposals/{id}/approve mit signed-token
DB (status='approved' → 'sent')
    ↓ _send_paranoid → Mailcow SMTP → Empfänger
```

---

## 3. Speicherorte

| Datentyp | Speicherort | Zugriff |
|---|---|---|
| Marketing-E-Mails (consent, unsubscribed_at, etc.) | `marketing.emails` (Postgres) | Layer-1 (PROPOSAL_API_KEY) |
| Inbound-Messages (subject, body, headers) | `marketing.inbound_messages` (Postgres) | Layer-1 + Layer-2 (n8n) bei sanitized read |
| Reply-Drafts (subject + body) | `marketing.reply_proposals` (Postgres) | Layer-1 only |
| Tracking-events (opens, clicks) | `marketing.email_opens`, `.email_clicks` (Postgres) | Layer-1 |
| Webhook-deliveries | `marketing.webhook_deliveries` (Postgres) | Layer-1 |
| Audit-logs | `marketing.audit_log`, `.n8n_api_audit` | Layer-1 |
| Rowboat-RAG-context | `marketing.reply_proposals.rowboat_context` (jsonb) | Layer-1 |
| Mailcow IMAP | `~/Documents/mailcow-deployment/` (lokal) | Felix only |
| OpenFang channel-tokens | `~/.openfang/config.toml` (DPAPI-verschlüsselt) | Felix only |

**Keine Daten auf externen Cloud-Services.** Alle LLM-Inferenz (Ollama, Rowboat) lokal.

---

## 4. Auftragsverarbeitung (AVV)

| Auftragnehmer | Zweck | AVV-Status |
|---|---|---|
| Mailcow (Selbsthosting) | SMTP-relay | Self-hosted, no AVV needed |
| Ollama (Selbsthosting) | Lokale LLM-Klassifikation | Self-hosted, no AVV needed |
| Rowboat (Selbsthosting Docker) | RAG-knowledge | Self-hosted, no AVV needed |
| n8n (Selbsthosting Docker) | Workflow-orchestration | Self-hosted, no AVV needed |
| Telegram (BotAPI) | Approval-cards | Drittland-USA. **AVV nötig falls nicht-Felix.** Im aktuellen setup: nur die konfigurierte Operator-Chat-ID (TELEGRAM_ALLOWED_CHAT_IDS), keine Kunden-Daten gehen rein. |
| OpenFang | Agent-runtime | Self-hosted, no AVV needed |

---

## 5. Speicherbegrenzung (Art. 5 Abs. 1 lit. e)

Retention via `marketing.run_retention_once_v2()`:

| Tabelle | Retention | Begründung |
|---|---|---|
| `marketing.inbound_messages` | 180 Tage | Datenminimierung; nach 6 Monaten nicht mehr für reply-flow relevant |
| `marketing.reply_proposals` (rejected/draft) | 180 Tage | wie inbound |
| `marketing.reply_proposals` (sent/approved) | 730 Tage | Audit-trail für gesendete Mails (steuerlich/rechtlich) |
| `marketing.email_opens`, `.email_clicks` | 365 Tage | Analytics-relevanz |
| `marketing.webhook_events` | 90 Tage | technisches log |
| `marketing.webhook_deliveries` (sent) | 90 Tage | technisches log |
| `marketing.webhook_deliveries` (dead) | 180 Tage | forensik |
| `marketing.n8n_api_audit` | 90 Tage | technisches log |
| `marketing.audit_log` | 730 Tage | rechtlich/audit floor |

Operator wires `SELECT marketing.run_retention_once_v2();` zu pg_cron oder
Scheduled-task (daily 03:00).

---

## 6. Betroffenenrechte

### Art. 15 (Auskunftsrecht)

Operator-skript (zukünftig — Schicht 7):
```sql
SELECT e.*, ARRAY(SELECT row_to_json(o) FROM marketing.email_opens o WHERE o.email = e.email) AS opens
FROM marketing.emails e
WHERE e.email = <betroffener>;
```

### Art. 17 (Recht auf Vergessenwerden)

Operator-skript (zukünftig — Schicht 7):
```sql
DELETE FROM marketing.email_opens WHERE email = <betroffener>;
DELETE FROM marketing.email_clicks WHERE email = <betroffener>;
DELETE FROM marketing.campaign_sends WHERE email = <betroffener>;
DELETE FROM marketing.inbound_messages WHERE from_email = <betroffener>;
DELETE FROM marketing.emails WHERE email = <betroffener>;
INSERT INTO marketing.audit_log (actor, action, target_table, payload)
VALUES ('art17:erasure', 'subject_data_erased', 'marketing.*',
        jsonb_build_object('email_hash', sha256_text(<betroffener>)));
```

### Art. 21 (Widerspruch)

Heute via signed-unsubscribe-token im Mail-Footer (RFC 8058 one-click).
Setzt `marketing.emails.unsubscribed_at` → send-worker prüft das in gate 6.

---

## 7. Sicherheitsmaßnahmen (Art. 32)

### Encryption at rest
- Postgres: nicht standardmäßig; Felix's home-FS ist BitLocker-verschlüsselt
- OpenFang channel-tokens: DPAPI (per-user verschlüsselt)
- Mailcow: AES-Speicher per Standard

### Access controls
- **Layer-1** (MARKETING_PROPOSAL_API_KEY): Curator + Operator-Routes, voller Zugriff
- **Layer-2** (MARKETING_N8N_API_KEY): n8n facade-routes, schmal + auditiert
- **Layer-3** (MARKETING_TRACKING_SECRET): URL-signing, nur für Tracking-routes
- Alle 3 Layer in `.env` (gitignored), nie in Code commited

### Audit
- Jede Layer-2-call → `marketing.n8n_api_audit` (90d retention, kein api_key/payload)
- Jede classification-änderung → `marketing.audit_log` mit actor
- Jede approval-action → `audit_log` mit token-hash (nie raw token)

### Pseudonymisierung
- Tracking-tokens hashen E-Mail (sha256, erste 12 chars) — kein direct lookup von external
- HMAC-bound URL hashes verhindern open-redirect

### Loop-prevention
- Worker C: refuses `Auto-Submitted: auto-replied` (RFC 3834)
- API: refuses reply-proposal creation für `is_autoreply=true` inbound

---

## 8. Datenschutz-Folgenabschätzung (Art. 35)

**Pflicht zur DSFA:** Nein für aktuelles Setup. Begründung:
- Keine systematische Profilbildung (keine ML-scores die in Bot-decisions münden)
- Keine besonderen Kategorien (Art. 9): kein Gesundheits- / Religions- / etc.-Tracking
- Keine large-scale processing: <20.000 Subscribers
- Volumen: ~50 Faker-Test-Empfänger heute, <10.000 erwartet bis Q4 2026

**DSFA wird Pflicht bei:**
- Integration externer LLM-APIs (OpenAI etc.) — heute nicht der Fall
- Verarbeitung von >50.000 Subscribers
- Score-basiertes ranking das outreach-decisions beeinflusst (heute: nur read-only views)

---

## 9. Open issues / next steps

- [ ] Schicht 7: Auskunfts-Skript (`/api/curator/subject_access_request`)
- [ ] Schicht 7: Auto-Erasure-Skript (`/api/curator/subject_data_delete`)
- [ ] Schicht 7: Datenschutzerklärung pages (für Empfänger im Mail-Footer)
- [ ] Schicht 7: Multi-tenant-Trennung (Workspace-isolation)
- [ ] AVV mit Telegram klären falls non-Felix chat_ids ins Approval kommen
- [ ] pg_cron-job für `run_retention_once_v2()` etablieren

---

## 10. Kontakt-Datenschutz

Bei DSGVO-Anfragen: <to-be-filled-once-DPO-or-equivalent-designated>.
