# Schicht 5 — Minimum Viable Brevo (MVB)

**Ziel:** Vibemind Marketing-Ops Space bietet die Kern-funktionen einer
selbst-gehosteten Brevo-Alternative. Mailcow bleibt die SMTP-engine, wir
bauen Tracking + Event-bus + Engagement-scoring drumherum.

**Out of scope für MVB:** Multi-tenant (white-label), IP-warmup-scheduler,
WYSIWYG-editor. Diese kommen in Schicht 6+ wenn ein zweiter Kunde existiert
oder ein konkreter use-case sie fordert.

---

## Inventur — was schon steht (Stand 2026-06-08)

### Datenmodell
- `marketing.emails` — recipients mit `consent_given_at`, `unsubscribed_at`, `smtp_valid`, `bounced_at`, `handle`
- `marketing.audiences` + `audience_members` — listen
- `marketing.templates` — subject + body_text (merge-fields via `{{first_name}}` etc.)
- `marketing.campaigns` — campaign metadata, `status`, `sent_at`
- `marketing.campaign_sends` (email) — `sent_at`, `bounced_at`, `bounce_reason`, `message_id`
- `marketing.campaign_sends_telegram` — telegram-counterpart
- `marketing.campaign_sends_openfang` — multi-channel counterpart (Schicht 4 geliefert)
- `marketing.inbound_emails` + `inbound_reply_linkage` — replies linked to campaigns (007)
- `marketing.audit_log` — every state-change written
- `marketing.events_outbox` (existiert via 004_sync_triggers!) — bereits ein outbox-pattern

### Send-pipeline
- `_send_paranoid.py` — 12-gate SMTP-stack (Mailcow/Mailpit)
- `_send_telegram.py` — 12-gate Telegram bot-API
- `_send_openfang.py` — 12-gate OpenFang multi-channel (Schicht 4)
- `merge_render()` — sicheres template-rendering mit `_ALLOWED_MERGE_FIELDS` whitelist

### DSGVO + Compliance
- `consent_given_at = NULL` invariant (alle imports default)
- signed unsubscribe-token (HMAC-SHA256, `_compute_unsub_token`, `/api/unsubscribe`)
- ALLOWED_DOMAINS frozenset (gate 5)
- Postfix loopback-block (gate 8)
- FREEZE_PATH file → all sends abort
- MARKETING_PROPOSAL_API_KEY env-gate für mutating routes

### Metriken
- `v_campaign_metrics` view (email + telegram + openfang sent/bounced counts)
- `dns_alignment.py` (SPF/DKIM/DMARC pro sender)
- `/api/metrics` routes (stack health, campaign metrics, activity, DNS)

### Inbound
- Worker C: IMAP-sync → `marketing.inbound_emails`
- reply-linkage worker matches inbound to campaigns (Message-ID + In-Reply-To)
- bounce-propagation worker writes `marketing.emails.bounced_at` (009)

### What we DON'T have
- **Open-tracking** (no pixel, no opens table, no template-injection)
- **Click-tracking** (no link-rewrite, no clicks table, no redirect route)
- **External webhook delivery** (events_outbox exists but only feeds internal sync;
  no per-event publish to user-configured HTTP endpoints)
- **Engagement score** (per-recipient: opens + clicks + replies weighted)
- **Per-campaign performance view** (open-rate, click-rate, CTR)

---

## Gap-Schichten

Vier diskrete Schichten. Jede ist selbst-getestet + dokumentiert + atomar
(kann ohne die folgenden landen ohne die Pipeline zu brechen).

### Schicht 5.1 — Open-tracking (5h)

**Was:** pixel-injection beim render, route schreibt opens.

**Migration 020_email_opens.sql:**
```sql
CREATE TABLE marketing.email_opens (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     uuid NOT NULL REFERENCES marketing.campaigns(id),
    email           citext NOT NULL,
    opened_at       timestamptz NOT NULL DEFAULT now(),
    user_agent      text,
    ip              inet,
    msgid_core      text   -- correlation with campaign_sends.message_id
);
CREATE INDEX ON marketing.email_opens (campaign_id, email);
CREATE INDEX ON marketing.email_opens (email, opened_at DESC);
```

**Code:**
- `tools/tracking.py` (neu) — `compute_open_token(campaign_id, email, msgid_core) -> hex`
  - HMAC-SHA256 mit `MARKETING_TRACKING_SECRET` (separate env, NICHT
    proposal-api-key; Tracking-secret darf weiter verbreitet sein, Proposal-secret nicht)
  - Token-format: `<campaign_id_short>.<email_hash_short>.<hmac_short>`
- `_send_paranoid.merge_render()` extension — accepts optional `inject_tracking_pixel: bool` param. Wenn true, hängt `<img src="{base}/t/o/{token}" width="1" height="1" alt=""/>` ans body_text-Ende (für HTML-templates) oder erweitert nichts wenn nur plain-text.
- `api/server.py` neue route `GET /t/o/{token}`:
  - parse token, HMAC-verify, lookup campaign/email
  - INSERT in email_opens (idempotent über UNIQUE(campaign_id, email, day)?
    NEIN — multiple opens sind wertvolle metric, nicht dedup)
  - return 1x1 GIF (43 bytes)
  - NO authentication required (recipient-facing, public)

**Dashboard:** neue tile in mockup.html — `Opens last 7d` mit chart.

**Tests:** `test_open_tracking.py`
- token deterministic + tampering rejected
- pixel injected only if html-flag set
- route writes row, returns 1x1 GIF
- multiple opens by same recipient = multiple rows (not dedup'd)

### Schicht 5.2 — Click-tracking (8h)

**Was:** template-pre-pass rewrites every `<a href="X">` to a redirect-URL.

**Migration 021_email_clicks.sql:**
```sql
CREATE TABLE marketing.email_clicks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     uuid NOT NULL REFERENCES marketing.campaigns(id),
    email           citext NOT NULL,
    clicked_at      timestamptz NOT NULL DEFAULT now(),
    url             text NOT NULL,
    user_agent      text,
    ip              inet,
    msgid_core      text
);
CREATE INDEX ON marketing.email_clicks (campaign_id, email);
CREATE INDEX ON marketing.email_clicks (url);
```

**Code:**
- `tools/tracking.py` extension — `rewrite_links(html, campaign_id, email, msgid_core) -> str`
  - Parser: re.sub matching `href="https?://[^"]+"` (NOT mailto:, NOT anchor #..., NOT existing tracking-domain)
  - Build token over (campaign_id, email, url-hash, msgid_core)
  - Replace href with `{base}/t/c/{token}?u={urlencoded_original}`
- `api/server.py` neue route `GET /t/c/{token}`:
  - parse token + verify HMAC + verify `u` matches the hash in token
  - INSERT in email_clicks
  - HTTP 302 Location: <original URL>
  - tampering with `u` query-param invalidates → 404

**Sicherheits-prinzip:** original URL hangt im query-param, aber Token bindet
URL-hash mit ins HMAC. Wenn jemand den Link auf eine Phishing-Site editiert,
verifiziert der token nicht mehr → 404. So kann unsere tracking-domain nicht
als Open-Redirect missbraucht werden.

**Dashboard:** neue tiles in mockup.html — `Clicks last 7d`, `Top URLs`, `CTR per campaign`.

**Tests:** `test_click_tracking.py`
- href-rewrite covers http, https, mailto: skipped, anchors skipped
- token + url tampering rejected (URL must match hash)
- redirect actually returns 302 to original
- circular self-link blocked (would loop tracking-domain)

### Schicht 5.3 — Webhook-event-bus (4h)

**Was:** lifecycle-events (sent, open, click, bounce, unsub, reply) gepushed an konfigurierte HTTP-endpoints.

**Migration 022_webhook_subscriptions.sql:**
```sql
CREATE TABLE marketing.webhook_subscriptions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    url             text NOT NULL,
    events          text[] NOT NULL,   -- ['sent', 'open', 'click', 'bounce', 'unsubscribe', 'reply']
    secret          text NOT NULL,      -- HMAC-key for signing payloads
    active          boolean NOT NULL DEFAULT true,
    failure_count   int NOT NULL DEFAULT 0,
    last_success_at timestamptz,
    last_failure_at timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

`marketing.events_outbox` existiert schon (004). Wir erweitern es um event_kind:
```sql
ALTER TABLE marketing.events_outbox
    ADD COLUMN IF NOT EXISTS event_kind text,
    ADD COLUMN IF NOT EXISTS delivered_to_webhooks_at timestamptz;
```

Triggers oder send-loop schreiben:
- `_send_paranoid`: nach sent → INSERT outbox event_kind='sent'
- email_opens INSERT trigger → outbox 'open'
- email_clicks INSERT trigger → outbox 'click'
- bounce-worker → outbox 'bounce'
- _do_unsubscribe → outbox 'unsubscribe'
- inbound_reply_linkage trigger → outbox 'reply'

**Code:**
- `workers/webhook_delivery.py` (neu) — picks outbox rows where `delivered_to_webhooks_at IS NULL`, fans out to all matching subscriptions, signs payload `X-Vibemind-Signature: sha256=<hex>`, marks delivered. Retries on 5xx with exponential backoff, disable subscription after 50 failures.
- `api/server.py` CRUD routes for webhook_subscriptions (with `_require_proposal_api_key` guard).

**Tests:** `test_webhook_delivery.py`
- payload signed with subscription's secret
- 200 = success + mark delivered
- 5xx = retry, increment failure_count
- 50-failure = auto-disable
- delete subscription stops further deliveries

### Schicht 5.4 — Engagement view (2h)

**Was:** per-recipient + per-campaign aggregated view.

**Migration 023_engagement_views.sql:**
```sql
CREATE OR REPLACE VIEW marketing.v_recipient_engagement AS
SELECT
    e.email,
    COUNT(DISTINCT cs.campaign_id) AS campaigns_received,
    COUNT(DISTINCT eo.campaign_id) AS campaigns_opened,
    COUNT(DISTINCT ec.campaign_id) AS campaigns_clicked,
    COUNT(DISTINCT ir.campaign_id) AS campaigns_replied,
    -- Engagement score: weighted sum
    -- open=1, click=3, reply=5, unsub=-10
    COALESCE(SUM(CASE WHEN eo.id IS NOT NULL THEN 1 ELSE 0 END), 0)
      + COALESCE(SUM(CASE WHEN ec.id IS NOT NULL THEN 3 ELSE 0 END), 0)
      + COALESCE(SUM(CASE WHEN ir.id IS NOT NULL THEN 5 ELSE 0 END), 0)
      - CASE WHEN e.unsubscribed_at IS NOT NULL THEN 10 ELSE 0 END
        AS engagement_score,
    MAX(GREATEST(
        eo.opened_at, ec.clicked_at, ir.received_at
    )) AS last_activity_at
FROM marketing.emails e
LEFT JOIN marketing.campaign_sends cs ON cs.email = e.email
LEFT JOIN marketing.email_opens    eo ON eo.email = e.email
LEFT JOIN marketing.email_clicks   ec ON ec.email = e.email
LEFT JOIN marketing.inbound_emails ir ON ir.from_email = e.email
GROUP BY e.email;

CREATE OR REPLACE VIEW marketing.v_campaign_performance AS
SELECT
    c.id AS campaign_id,
    c.name AS campaign_name,
    c.channel,
    c.sent_at,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE campaign_id = c.id AND sent_at IS NOT NULL) AS delivered,
    (SELECT COUNT(*) FROM marketing.campaign_sends WHERE campaign_id = c.id AND bounced_at IS NOT NULL) AS bounced,
    (SELECT COUNT(DISTINCT email) FROM marketing.email_opens WHERE campaign_id = c.id) AS unique_opens,
    (SELECT COUNT(*) FROM marketing.email_opens WHERE campaign_id = c.id) AS total_opens,
    (SELECT COUNT(DISTINCT email) FROM marketing.email_clicks WHERE campaign_id = c.id) AS unique_clicks,
    (SELECT COUNT(*) FROM marketing.email_clicks WHERE campaign_id = c.id) AS total_clicks,
    (SELECT COUNT(*) FROM marketing.inbound_reply_linkage WHERE campaign_id = c.id) AS replies
FROM marketing.campaigns c;
```

**API routes:**
- `GET /api/metrics/campaigns/{id}/performance` — single campaign with open-rate, click-rate, CTR
- `GET /api/metrics/recipients/top-engaged?limit=N` — for cherry-picking next outreach

**Dashboard:** mockup.html bekommt einen "Performance" tab mit chart-rendering.

**Tests:** `test_engagement_views.py`
- score formula correct for known fixtures
- unsub blocks score (10 penalty applied)
- last_activity_at picks the max across opens/clicks/replies

---

## Auswirkungen auf bestehende Systeme

### _send_paranoid.py — minimale Änderungen
- `merge_render()` bekommt einen `tracking_context: Optional[TrackingContext]` parameter
- Wenn gesetzt: links durch `rewrite_links()` ersetzt + pixel angehängt
- TrackingContext = `{campaign_id, email, msgid_core, tracking_base_url}`
- DEFAULT: kein tracking (LEGACY-pfad bleibt rein)
- Gates 1–12 bleiben unverändert

### _send_telegram.py / _send_openfang.py
- KEIN tracking — Telegram bot-messages haben kein href-rewrite-äquivalent, Discord-message-tracking macht Discord selber
- Nur Email-channel bekommt tracking

### Sicherheitsmodell
- **Tracking-secret separate from proposal-secret.** Tracking-base-URL ist public, jeder der einen URL sieht kennt unsere tracking-domain — der Schlüssel darf "leichter" leben. Proposal-key bleibt operator-only.
- **HMAC verifiziert URL-hash in click-token** → Open-Redirect-attacke ausgeschlossen.
- **Pixel + redirect-routes ohne auth** (recipient-facing). Aber jede Anfrage validiert HMAC. Tampered tokens → 404.
- **Webhook payloads HMAC-signed** mit subscription-secret. Empfänger verifiziert wie GitHub-webhooks.

### Operative
- **Tracking optional per template:** `marketing.templates.tracking_enabled boolean DEFAULT false`. Nur templates mit `tracking_enabled=true` bekommen pixel + link-rewrite. Felix kann transactional emails (z.B. opt-in-confirmation) ohne tracking lassen.
- **Tracking-domain config:** `MARKETING_TRACKING_BASE_URL` env (z.B. `https://track.vibemind.space`). Production braucht dafür A-record + cert.
- **Pixel + redirect performance:** beide routes synchron schreiben in DB. Bei Volumen über 1k/sec wird das eng — Schicht 6 wäre dann ein async outbox-pattern.

---

## Risiken / open questions

- **DSGVO + tracking pixel:** Open-tracking ist in DE Cookie-rechtlich grau. Lösung in Schicht 5.1: tracking nur wenn `marketing.emails.tracking_consent_given_at IS NOT NULL` (separates consent vom marketing-consent). Pixel-injection-helper verifiziert das vor inject.
- **Click-tracking via redirect** verändert URLs in der mail. Spam-filter könnten das ahnden. Mitigation: tracking-domain hat reverse-DNS auf vibemind.space + ist im SPF/DKIM whitelisted.
- **events_outbox überladung:** wenn 50k opens am Tag durchlaufen sind das 50k outbox-rows. Worker muss in batches arbeiten + alte rows wegräumen (cron job, Schicht 6).
- **Webhook-receiver authn:** wir signieren outbound. Aber sollten wir auch IPs/origins whitelisten? Erstmal nicht — User vertraut, dass nur Felix Subscriptions anlegen kann (proposal-api-key guard).

---

## Aufwand-Summe

| Schicht | Aufwand | Selbst-getestet | Liefert |
|---|---|---|---|
| 5.1 Open-tracking | 5h | ✓ | Pixel + opens-table + dashboard tile |
| 5.2 Click-tracking | 8h | ✓ | Link-rewrite + clicks-table + CTR |
| 5.3 Webhook-bus | 4h | ✓ | Subscriptions-CRUD + signed delivery worker |
| 5.4 Engagement view | 2h | ✓ | Score view + top-engaged route + perf tab |
| **MVB total** | **19h** | | **Vibemind = MVP-Brevo** |

Schicht 6 (multi-tenant, WYSIWYG, IP-warmup) ist KEIN MVB. Erst wenn ein
zweiter Kunde oder ein konkreter Markt-use-case sie braucht.

---

## Reihenfolgen-Empfehlung

```
5.3 Webhook-bus FIRST  (4h)
   → liefert sofortigen Discord/Telegram-nutzen via Schicht-4-channels
     (send-event → discord-notify), keine Tracking-events nötig
5.1 Open-tracking      (5h)
   → emittet 'open' events über den fertigen webhook-bus
5.2 Click-tracking     (8h)
   → emittet 'click' events
5.4 Engagement view    (2h)
   → joint alles zusammen, final dashboard
```

Aber: jede Reihenfolge funktioniert — Schichten sind unabhängig. Wenn
Tracking sichtbarer ist als Webhook-bus (sichtbares feature für Felix), dann
**5.1 → 5.2 → 5.3 → 5.4** mit retrofit der bereits geschriebenen open/click
rows in den event-bus (one-time backfill).
