# Schicht 7 — Multi-Channel + Routing + Management-UI

**Status:** Planung, kein Code geschrieben
**Datum:** 2026-06-09
**Use-cases aus User-Feedback:**

> "Nicht jedes Template ist email conform.
> Nicht jeder incoming braucht ein respond.
> Incoming braucht routing an die richtige person.
> Aber wir wollen auch zb reals über Insta, und restlichen Konsorten schicken (openfang-channels)."

---

## Drei distinkte Konzerne

### Konzern A — Channel-spezifische Templates

**Problem:** `marketing.templates` heute hat:

| Feld | Email | Telegram | Discord | Mastodon | Instagram |
|---|---|---|---|---|---|
| `subject` | ✅ erforderlich | ❌ ignoriert | ❌ ignoriert | ❌ ignoriert | ❌ ignoriert |
| `body_text` | ✅ | ✅ (Markdown) | ✅ (Markdown) | ✅ (text+url) | ❌ caption only |
| `body_html` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `tracking_enabled` | ✅ pixel+link | ❌ | ❌ | ❌ | ❌ |
| `image_url` | als attachment | als photo | als embed | als media | ✅ pflicht für reel |
| `video_url` | als attachment | als video | als embed | als media | ✅ für reel |
| `hashtags` | ❌ | ❌ | ❌ | ✅ erweitern caption | ✅ pflicht |
| `parse_mode` | n/a | MarkdownV2/HTML | n/a | n/a | n/a |
| `thread_id` | n/a | reply-to | discord-channel | n/a | n/a |

Ein single-table-template kann das nicht abbilden ohne null-felder + channel-conditional-logic.

**Lösung:** Template-vererbung mit per-channel-varianten:

```sql
-- existing
marketing.templates (id, name, default_channel, created_at, ...)
  ↓
-- new: per-channel variants of a template
marketing.template_variants (
  id, template_id, channel, content jsonb, created_at, ...
)
```

`content jsonb` mit channel-spezifischer schema-validation:
- email: `{subject, body_text, body_html, tracking_enabled, attachments[]}`
- telegram: `{body_text, parse_mode, reply_markup, photo_url, video_url, ...}`
- discord: `{body_text, embed, image_url, thread_id, ...}`
- mastodon: `{body_text, media_ids[], visibility, language, ...}`
- bluesky: `{body_text, embed, langs[], ...}`
- instagram: `{caption, media_url, media_type, hashtags[], ...}` (manual flow)

**Vorteile:**
- Ein "campaign-message" hat 1+ variants — operator wählt welche channels für diese campaign
- Template-namensgebung bleibt zentral (z.B. "Product-launch-v3")
- Per-channel-rendering ist getrennt — `_send_email` rendert nur das email-variant, `_send_telegram` nur das telegram-variant
- Schema-validation pro channel im backend

**Migration 030 + neue API:**
```sql
CREATE TABLE marketing.template_variants (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id  uuid NOT NULL REFERENCES marketing.templates(id) ON DELETE CASCADE,
    channel      text NOT NULL REFERENCES marketing.channel_config(channel),
    content      jsonb NOT NULL,
    is_default   boolean DEFAULT false,
    created_at   timestamptz DEFAULT now(),
    updated_at   timestamptz DEFAULT now(),
    UNIQUE (template_id, channel)
);
```

**Code-impact:**
- `_send_paranoid.py` liest `template_variants.content` statt `templates.body_text/body_html`
- `_send_telegram.py` liest variant für `channel='telegram'`
- `_send_openfang.py` liest variant für openfang-routed channels
- Migration 030 ist additive (alte single-table templates bleiben kompatibel mit `is_default=true` variant)

---

### Konzern B — Inbound-Routing an die richtige Person

**Problem:** Heute landet jede inbound mail bei `marketing@vibemind.space` und nur **du** als curator siehst sie.

**Realer Anwendungsfall:**
- Sales-questions → Sales-Lead
- Technical-bug-reports → Dev-Team
- Press-inquiries → PR-Person
- Refund-requests → Support-Lead
- Spam → trash (kein human-touch)
- Bounces → auto-handled (heute schon)

**Lösung:** Routing-rules + Curator-roles:

```sql
-- Curators (mehrere humans die inbound bearbeiten können)
CREATE TABLE marketing.curators (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text NOT NULL,
    email        citext UNIQUE,
    telegram_chat_id bigint,
    discord_user_id text,
    active       boolean DEFAULT true,
    created_at   timestamptz DEFAULT now()
);

-- Rules: welche classification + welche conditions -> welcher curator
CREATE TABLE marketing.inbound_routing_rules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    priority    int NOT NULL DEFAULT 100,  -- niedriger = höher priorität
    conditions  jsonb NOT NULL,             -- {classification: 'reply', subject_regex: '^Sales:', from_domain: 'acme.com'}
    target_curator_id uuid REFERENCES marketing.curators(id),
    target_action text DEFAULT 'assign',    -- 'assign' | 'auto_reply_template' | 'archive' | 'forward'
    auto_reply_template_id uuid REFERENCES marketing.templates(id),  -- für target_action='auto_reply_template'
    active      boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

-- Assignment-state per inbound message
ALTER TABLE marketing.inbound_messages
    ADD COLUMN assigned_curator_id uuid REFERENCES marketing.curators(id),
    ADD COLUMN assigned_at timestamptz,
    ADD COLUMN assigned_by text;            -- 'rule:<rule_id>' or 'manual:felix'
```

**Workflow:**
1. n8n workflow 1 klassifiziert inbound (bereits da)
2. **Neuer Workflow 4 — Routing:** triggert auf `inbound_classified` event
   - holt alle aktiven routing_rules sortiert nach priority
   - prüft jede regel gegen die inbound-message (regex + jsonpath conditions)
   - erste matching rule → assigned_curator_id setzen
   - target_action ausführen:
     - `assign` → Curator-UI zeigt's beim entsprechenden curator
     - `auto_reply_template` → reply_proposal mit template_id erstellen
     - `archive` → status auto-archive, kein curator-touch nötig
     - `forward` → forward mail an externen empfänger
3. Notification an target_curator (Telegram-card via OpenFang)

**Curator-UI:**
- Multi-curator-login (jeder curator sieht nur seine zugewiesenen messages)
- Manuelle re-assignment möglich
- Rules-management-UI (drag-drop priority, condition-builder)

**Migration 031.**

---

### Konzern C — Mehr OpenFang-Channels (Mastodon, Bluesky, Instagram, ...)

**Heute funktioniert:** email (Mailcow), telegram (direct API)

**OpenFang channel_send tool unterstützt** (siehe `openfang-channels/src/`):
- ✅ discord.rs — Bot API (heute prep-state, allowlist fehlt)
- ✅ slack.rs — Socket Mode + Bot Token
- ✅ mastodon.rs — OAuth
- ✅ bluesky.rs — App Password
- ✅ matrix.rs — Access Token
- ✅ signal.rs — REST (signal-cli)
- ✅ whatsapp.rs — Business API (kompliziert)
- ✅ teams.rs — Bot Framework
- ✅ reddit.rs — OAuth
- ✅ linkedin.rs — OAuth (für post, nicht messaging)
- ✅ ntfy.rs — webhook
- ✅ gotify.rs — App Token
- ❌ instagram — **keine offizielle bot-API** für reels-posting; nur Business-Manager-flow
- ❌ tiktok — keine offizielle bot-API für post

**Per-channel-aktivierung** ist ein 4-Schritt-prozess (heute manuell):

1. **Bot-account anlegen** beim Provider (mastodon-account, discord-bot, etc.)
2. **OAuth-token / Bot-secret** in OpenFang config eintragen via `POST /api/channels/{name}/configure`
3. **Recipient signieren** mit HMAC und in `marketing.channel_recipient_allowlist` einfügen via `tools/sign_recipient.py`
4. **Flippen** `marketing.channel_config.enabled=true` und ggf. `openfang_capable=true`

Für jeden zusätzlichen channel = ~30 min wenn der bot-account schon da ist.

**Instagram & TikTok — explizit out of scope für Schicht 7.** Diese brauchen:
- Business-Manager-Account (verifiziert)
- Webhook-callbacks für reach-metriken
- Manuelle media-asset-upload (kein direct bot-post)

→ Wenn du wirklich Insta-reels brauchst: separates Schicht 8 mit Buffer / Hootsuite / Later API als zwischenschaltung.

---

## Konzern D — Management-UI (UI-priorisiert per User-Wunsch)

**Plan: 4 neue Tabs im Curator-Space**

Heute hat der curator-space 3 tabs: Inbound Queue, Reply Proposals, Audit. Wir erweitern auf 7:

```
[Inbound Queue] [Reply Proposals] [Audit]
[Channels]      [Templates]       [Recipients] [Campaigns]
```

### Tab "Channels"

**Was:** Live-overview welche channels real funktionieren

**Pro channel-zeile:**
- name, label
- send_implemented (true/false)
- enabled (toggle button)
- openfang_capable (true/false)
- bot-token status: ✅ in OpenFang config OR ⚠️ fehlt
- recipient-count im allowlist
- last_send_at + success/fail-count letzte 24h

**Actions:**
- Enable/disable toggle (POST /api/curator/channels/{name}/toggle)
- "Configure bot-token" → opens OpenFang-link http://127.0.0.1:4200 → /api/channels/{name}/configure
- "Test connectivity" button (calls OpenFang /api/channels/{name}/test)
- "View recipients" → goes to recipients tab pre-filtered by channel

**Backend:** Existing routes `/api/channels`, `/api/channels/{channel}`, `/api/channels/ready`, `/api/channels/refresh` — alle haben wir schon.

### Tab "Templates"

**Was:** Template management mit per-channel-varianten (Konzern A)

**Master-template-list:**
- name, default_channel, created_at, variants_count, tracking_enabled

**Click → Template-detail:**
- Master-info edit
- Variants-list mit tabs pro channel
- Per channel-variant: schema-validated form (email: subject/body_html; telegram: parse_mode/photo_url; etc.)
- Preview pro variant (render mit dummy-fields)

**Actions:**
- Create new template
- Add variant for channel X
- Duplicate template
- Delete (only if no campaigns reference it)

**Backend:** Migration 030 + new routes `/api/curator/templates`, `/api/curator/templates/{id}`, `/api/curator/templates/{id}/variants`

### Tab "Recipients & Allowlists"

**Two sub-tabs:**

**Sub-tab 1: Email recipients (`marketing.emails`)**
- Search + filter (consent given, opted out, hard bounced, last engagement)
- Per row: consent_given_at, tracking_consent_given_at, unsubscribed_at, last activity, score
- Actions: edit consent, manual unsubscribe, view audit-trail per recipient

**Sub-tab 2: Channel allowlists (`marketing.channel_recipient_allowlist`)**
- Filter by channel
- Pro row: channel, recipient_id (chat_id/channel_id), approved_by, hmac_sig valid?, revoked
- Actions: add new (calls `sign_recipient.py` server-side), revoke, re-verify HMAC

**Backend:** Existing-mockup hat email-recipients-management; allowlist-UI ist new (~150 LOC HTML+endpoints).

### Tab "Campaigns"

**Was:** Liste + create + DRY_RUN trigger

**Liste:**
- name, channel, status, template, audience, sent_at, total_sent, total_bounced, total_replies
- Filter by status (draft, sent, cancelled)

**Click → Campaign-detail:**
- Edit (only if status=draft)
- Channel-picker (dropdown der enabled-channels)
- Template-picker (dropdown der templates die ein variant für diesen channel haben — automatic filter)
- Audience-picker
- DRY_RUN button → zeigt result inline (recipient_count + confirm_token)
- SHADOW button (wenn Mailpit configured)
- LIVE button (mit confirm-dialog "ECHTE MAIL — sicher?")

**Backend:** Existing-mockup hat campaigns-list; create+trigger-actions sind partial-implemented.

---

## Gesamt-Migration-Plan

| Migration | Schicht | Was |
|---|---|---|
| 030 | 7A | `marketing.template_variants` + per-channel-content jsonb |
| 031 | 7B | `marketing.curators` + `marketing.inbound_routing_rules` + `inbound_messages.assigned_curator_id` |
| 032 | 7D | (optional) `marketing.channel_recipient_allowlist_pending` für UI-driven 2FA-style enable-flow |

## Code-impact

**Per Schicht:**

| Schicht | Aufwand | Was berührt wird |
|---|---|---|
| **7A** Template-variants | 6h | Migration 030, `_send_paranoid`/`telegram`/`openfang` lesen variants statt templates direkt, neue API-routes `/api/curator/templates/{id}/variants`, 4-5 tests |
| **7B** Inbound-routing | 8h | Migration 031, neuer n8n workflow 4, Curator-UI multi-tenant-mode, OpenFang notification an target_curator, 6-8 tests |
| **7C** More channels | 3h pro channel | bot-account anlegen (extern), OpenFang configure (1x curl), recipient-sign (`sign_recipient.py`), enable-flip — kein code-change pro channel, alle via existing helpers |
| **7D** Curator-UI 4 neue tabs | 8h | UI: 4 neue Alpine.js components (~800 LOC), backend: ~10 neue/erweiterte routes, 8-10 tests |
| **Total** | **~22h + 3h pro channel** | |

---

## Empfohlene Bauphasen-Reihenfolge

```
Phase 7.1 (8h) — UI-Skelett (Schicht 7D ohne backend-deps)
  ├── 4 neue Tabs in curator/index.html
  ├── Channels-tab: list-view mit existing /api/channels routes
  ├── Templates-tab: list + edit single-template (without variants yet)
  ├── Recipients-tab: marketing.emails CRUD
  └── Campaigns-tab: list + DRY_RUN button (mit existing endpoint)

Phase 7.2 (6h) — Template-variants (Schicht 7A)
  ├── Migration 030
  ├── Send-workers lesen variants
  ├── Templates-tab: variant-tabs per channel
  └── Schema-validation pro channel-content

Phase 7.3 (3h pro channel) — Channels einzeln aktivieren
  ├── Discord: bot anlegen, token, recipient-sign, enable
  ├── Mastodon: oauth, sign, enable
  ├── Bluesky: app-password, sign, enable
  └── (du wählst welche zuerst)

Phase 7.4 (8h) — Inbound-routing (Schicht 7B)
  ├── Migration 031
  ├── n8n workflow 4
  ├── Multi-curator-UI mode
  └── OpenFang notification an target_curator
```

**Total ohne 7.3:** ~22h.
**Mit 3 zusätzlichen channels in 7.3:** +9h.

---

## Was du SOFORT nach UI hast (Phase 7.1 — 8h)

Ohne weitere migrationen oder channel-aktivierungen kannst du nach Phase 7.1:

✅ **Pro campaign auswählen welcher channel** verwendet wird (dropdown der enabled channels)
✅ **Pro template editieren** und tracking-flag toggeln
✅ **Pro recipient sehen** ob consent + tracking-consent + bounce-status
✅ **Manuell channel deaktivieren** wenn ein bot kaputt geht
✅ **DRY_RUN aus der UI** triggern statt python-shell

Was du noch NICHT kannst:
❌ Per-channel-content für eine campaign (template ist single-form, alle channels erben gleichen body)
❌ Inbound-routing an andere personen (single-curator-mode)
❌ Mastodon/Bluesky/etc. senden (nicht aktiviert)

## Was Insta/Tiktok-reels betrifft

**Ehrliche Wahrheit:**

- **Instagram** hat keine bot-friendly API für reels-posting. Buffer/Hootsuite/Later sind workarounds aber nicht open-source. Eigene Lösung würde 40+ h kosten (Selenium-bot der Instagram-app durchklickt — fragil, regelmäßig broken durch UI-changes).
- **TikTok** ähnlich, plus Captcha-shenanigans.
- **YouTube** hat eine API für uploads — diese könnte realistisch.

**Vorschlag:** Schicht 8 für "social media broadcast" wenn das wirklich nötig wird. Heute (Schicht 7) konzentrieren auf channels mit echten APIs: Mastodon, Bluesky, LinkedIn-posts, Reddit, Discord, Slack.

---

## Frage zum diskutieren

Bevor wir bauen:

1. **Multi-curator JA / NEIN?** Heute single-curator (du). Wenn JA → Curator-table braucht auth-system (Schicht 7B braucht ~3h extra für login).
2. **Wer ist außer dir Curator?** Sales-person, dev-lead, jemand spezielles? Bestimmt prioritäten für routing-rules.
3. **Welche channels zuerst** in Phase 7.3? Discord (heute prep-state) ist zero-extra-aufwand. Mastodon ist 2h (oauth-setup) und du hast schon einen account?
4. **Inbound-routing per LLM** (zusätzlich zu regex-rules)? Falls regex nicht reicht: Ollama-call mit "an wen sollte das gehen?" — kostet ~500ms pro classify-step, deutlich smarter. ~2h zusätzlich.
5. **Template-variants jsonb schema-validation:** strict (per channel JSON-schema) oder loose (free-form jsonb)? Strict ist sicherer aber mehr maintainance.
