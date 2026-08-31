# Bubble-Auto-Dispatch — Selbst-klassifizierende Bubbles + per-Channel-Fan-Out + Crowdfunding-Pipeline

**Datum:** 2026-07-02
**Owner:** Marketing-Ops + Brain-Router
**Status:** Plan-Phase. Design mit User abgestimmt. Noch nicht implementiert.

---

## In 60 Sekunden verstehen (die Geschichte)

Heute muss der User bei jedem Post-Draft **manuell** `target_channel="linkedin"` setzen und Bubbles selbst einer Kategorie zuordnen. Das ist Reibung — und es skaliert nicht wenn ein Bubble in **mehreren** Kanälen live gehen soll (LinkedIn UND X UND Email).

**Das Ziel:** Bubbles klassifizieren sich selbst. Der User tippt nur den Text ein — Brain figuriert autonom:
- **Was für ein Bubble ist das?** (Marketing? Code-Project? Research? Crowdfunding?)
- **Welche Farbe** entspricht dem? (rot/blau/lila/orange/weiß)
- **Welche Channels** sind dafür passend? (LinkedIn+X für Marketing, Email für Crowdfunding, Gitea für Code-Project…)
- **Dann fan-outt es autonom** — pro Channel ein separater n8n-Workflow, pro Channel eine separate Approval-Karte in OpenFang für den Curator.

**Woher weiß Brain das?** Die schon existente `bubble_evaluate`-Capability wird erweitert um Klassifikations-Schritt: Qwen3-Embedding + kNN-Search über schon-klassifizierte Bubbles + Mirofish-Persona-Simulation. Ergebnis: `category`, `color`, `channels[]`, `confidence`.

**Das größere Bild:** Crowdfunding kommt als neue Kategorie dazu — mit eigener Pipeline (Payment-Links generieren, tracken) die dem LinkedIn-Post-Muster 1:1 folgt. Payment-Provider läuft dabei als **eigener unabhängiger Workflow** (Payment-Infra) unter dem Crowdfunding-Layer, analog Mailcow/SMTP unter dem Email-Layer.

---

## Vorher vs. Nachher — ein Bild

```text
VORHER (Stand heute):
──────────────────────
  User erstellt Bubble
  User wählt manuell: kind=post_draft, target_channel="linkedin"
    │
    ▼
  bubble_predict_runner.py → Mirofish score
    │
    ▼
  User klickt "publish"
    │
    ▼
  1 broadcast_proposal → 1 OpenFang-Karte → Curator approved
    │
    ▼
  04_linkedin_broadcast.json (n8n, mit IF-filter drin)
    │
    ▼
  LinkedIn Post
  [Nur EIN Channel pro Bubble. Manuelle Klassifikation. Keine Crowdfunding.]


NACHHER (nach diesem Plan):
──────────────────────────
  User erstellt Bubble mit Text
    │
    ▼
  bubble_evaluate (erweitert) — autonom
    → category="marketing", color=🔴, channels=["linkedin","x","email"], conf=0.87
    │
    ▼
  bubble_dispatcher.py — Fan-Out
    → 3 broadcast_proposals angelegt (linkedin, x, email)
    → 3 OpenFang-Approval-Karten, jede mit channel-optimiertem Text
    │
    ▼
  Curator: LinkedIn ✅ · X ❌ · Email ✅
    │
    ├─── 04_linkedin_broadcast.json (isoliert, KEIN IF-filter)
    │       → LinkedIn API
    │
    └─── 06_email_broadcast.json (isoliert)
            → send_worker.py :5510 (12-Gate-Enforcer)
              → Mailcow

  Bubble-Status aggregiert: "partially_sent" (X wurde rejected)

  [N Channels pro Bubble. Autonome Klassifikation. Crowdfunding als eigene category.]
```

---

## Glossar — die Begriffe die im Plan vorkommen

| Begriff | Was es bedeutet |
|---|---|
| **Bubble** | Eintrag in `public.ideas` — jede User-Idee ist eine Bubble |
| **category** | Zuständigkeits-Klasse: `marketing` \| `crowdfunding` \| `code_project` \| `research` \| `general` |
| **color** | UI-Farbe abgeleitet aus category — rein visuell, dient Overview |
| **channels[]** | JSONB-Array möglicher Kanäle für diese Bubble — z.B. `["linkedin","x","email"]` |
| **auto_classified** | Boolean — hat der Classifier das gesetzt oder der User manuell |
| **confidence** | 0.0..1.0 — wie sicher ist der Classifier. Unter Threshold = bleibt weiß/general |
| **Fan-Out** | Pro Channel eine broadcast_proposal-Row anlegen bei Klassifikation |
| **broadcast_proposal** | Approval-gated DB-Row pro (bubble, channel). Existiert heute schon |
| **OpenFang-Karte** | Approval-Anzeige in OpenFang UI :4200 (Curator klickt approve/reject) |
| **n8n-Workflow** | Ein isolierter n8n-Flow pro Channel (`04_linkedin_broadcast.json`, `05_x_broadcast.json`, …) |
| **Webhook-Bus** | `db/020_webhook_bus.sql` + `workers/webhook_delivery.py` — routet DB-Events zu n8n |
| **Payment-Infra** | Neuer Layer — Provider-agnostisch (PayPal first), lebt außerhalb Vibemind_V1 |
| **Crowdfunding-Batch** | Analog broadcast_proposal, aber Multi-Recipient — 1 Batch pro (bubble, channel) |
| **Template-Skill** | Claude-Skill der Backer-Outreach-Nachrichten LLM-rendered pro Channel |
| **Browser-Automation-Skill** | Claude-Skill der PayPal-Dev-Dashboard via openclaw-visible durchklickt |

---

## Ein konkretes Beispiel — "VibeMind Beta Launch" durchgespielt

Angenommen der User schreibt eine neue Bubble: **"Nach 8 Monaten Bau öffnet VibeMind heute den Beta-Zugang für indie hackers. Wir haben einen agentic OS gebaut, der einer Person erlaubt eine ganze SaaS-Firma zu betreiben. Schaut vorbei auf vibemind.space/beta"**

**Schritt 1 — Klassifikation (bubble_evaluate erweitert):**
- Qwen3-Embedding der Description → 1024-dim Vektor
- kNN-Search in Qdrant → 8 der Top-10 ähnlichsten Bubbles sind classified als `marketing`
- Mirofish-Persona-Sim: 5 Personas evaluieren "was ist das für ein content?"
  - PR-Persona: "Launch-Announcement — LinkedIn + X ideal"
  - Content-Marketer: "auch Reddit Founders subreddit"
  - Community-Manager: "Discord + Telegram für Ankündigung"
  - Skeptiker: "vielleicht auch Email an Newsletter"
- Aggregation: category=`marketing`, color=`#dc2626`, channels=`["linkedin","x","email","reddit","discord"]`, confidence=0.87
- DB-Update: `public.ideas` gefüllt

**Schritt 2 — Fan-Out (bubble_dispatcher.py):**
Sidecar-Worker sieht neue klassifizierte Bubble → legt für jeden Channel eine broadcast_proposal an:

| bp_id | bubble_id | channel | status | approval_token_hash | draft_body_text |
|---|---|---|---|---|---|
| `bp_A` | `bubble_XY` | linkedin | draft | (leer) | `<via Template-Skill gerendert für LinkedIn>` |
| `bp_B` | `bubble_XY` | x | draft | (leer) | `<via Template-Skill gerendert für X, max 280 chars>` |
| `bp_C` | `bubble_XY` | email | draft | (leer) | `<via Template-Skill gerendert für Email, mit Subject>` |
| `bp_D` | `bubble_XY` | reddit | draft | (leer) | `<via Template-Skill gerendert für Reddit>` |
| `bp_E` | `bubble_XY` | discord | draft | (leer) | `<via Template-Skill gerendert für Discord>` |

**Schritt 3 — Approval-Request pro bp:**
Für jedes bp wird ein HMAC-Token generiert + OpenFang-Approval-Card angelegt. 5 Karten in OpenFang UI :4200 für den Curator.

**Schritt 4 — Curator entscheidet:**
- LinkedIn ✅ approve
- X ❌ reject (Grund: "Text passt nicht in 280 chars ohne Substanz-Verlust")
- Email ✅ approve
- Reddit ❌ reject (Grund: "Subreddit-Rules brauchen längeren Kontext, mach neuen Draft")
- Discord ✅ approve

**Schritt 5 — Auto-Dispatch der approved bps:**
Webhook-Bus emitted 3 events (nur die approveden). Jedes trifft seinen isolierten n8n-Workflow:
- `04_linkedin_broadcast.json` → LinkedIn API → post URN in `campaign_sends.sent_external_id`
- `06_email_broadcast.json` → HTTP zu `send_worker.py :5510` → SMTP über Mailcow (mit 12 Gates) → delivered_at
- `07_discord_broadcast.json` → Discord API → message ID

**Schritt 6 — Bubble-Status aggregiert (Migration 037):**
5 broadcast_proposals: 3 sent, 2 rejected → `bubble.status='partially_sent'` (neuer Wert). Wenn später beide rejecteten manuell neu approved würden → 5 sent → `bubble.status='sent'`.

**Schritt 7 (Crowdfunding-Variante):**
Wenn dieselbe Bubble stattdessen als **Crowdfunding-Ankündigung** klassifiziert würde (weil Text z.B. "Support us on backing.vibemind" enthält), category=`crowdfunding`, channels=`["email","linkedin-dm"]`. Dann werden 2 `crowdfunding_batches` angelegt (statt broadcast_proposals). Jede Batch trigger'd `batch_sender.py`, der pro Empfänger eine unique PayPal-Order über Payment-Infra generiert.

---

## Was schon da ist (kein Neubau nötig)

- [`spaces/marketing/db/030_broadcast_proposals.sql`](../db/030_broadcast_proposals.sql) — **1 row pro (bubble, channel)** — Schema supported Fan-Out schon direkt
- [`spaces/marketing/db/031_openfang_approval_bridge.sql`](../db/031_openfang_approval_bridge.sql) — HMAC-Token + openfang_approval_id
- [`spaces/marketing/db/033_bubble_post_drafts.sql`](../db/033_bubble_post_drafts.sql) — `bubble.broadcast_proposal_id` link
- [`spaces/marketing/db/034_bubble_status_propagate.sql`](../db/034_bubble_status_propagate.sql) — heute 1:1-Mirror (bp.status → bubble.status), **muss zu Aggregation umgebaut werden** → Migration 037
- [`spaces/marketing/workers/openfang_approval_bridge.py`](../workers/openfang_approval_bridge.py) — Sidecar der OpenFang→Marketing-API relayt. Funktioniert für N bps unverändert.
- [`spaces/marketing/workers/webhook_delivery.py`](../workers/webhook_delivery.py) + `db/020_webhook_bus.sql` — Event-Bus zu n8n. Muss channel-aware routen.
- [`spaces/marketing/n8n_workflows/04_linkedin_broadcast.json`](../n8n_workflows/04_linkedin_broadcast.json) — Basis-Muster für n8n workflow pro channel. IF-filter wird entfernt.
- [`spaces/marketing/workers/send_worker.py`](../workers/send_worker.py) — 12-Gate-Safeguard für Email. **Bleibt Enforcer**, n8n triggert nur via HTTP.
- [`spaces/marketing/workers/bubble_predict_runner.py`](../workers/bubble_predict_runner.py) — Mirofish-Sim-Runner. Bleibt für Marketing-post-Bubbles.
- [`vibemind-os/brain/the_brain/data/capabilities.yaml`](../../../vibemind-os/brain/the_brain/data/capabilities.yaml) — `bubble_evaluate` capability existiert (execution_target `supabase:bubble.evaluate`). Wird um Classifier-Step erweitert.
- [`vibemind-os/brain/the_brain/core/qdrant_kg.py`](../../../vibemind-os/brain/the_brain/core/qdrant_kg.py) — Qwen3-Embedder-Singleton. Wiederverwenden für Classifier, nicht neu laden!
- `Desktop/VibeMind-OS/backer-checkout/` — PayPal-Client + Flask-App (Smart-Buttons On-Page-Variante). Wird auseinandergezogen in Payment-Infra + Crowdfunding-Worker.

## Was fehlt (was dieser Plan baut) — die 6 Bausteine

1. **Bubble-Schema-Erweiterung** — category/color/channels[]/auto_classified/confidence (Migration 036)
2. **Status-Aggregations-Trigger** — N bp.status → 1 bubble.status mit `partially_sent`-Wert (Migration 037)
3. **Classifier in `bubble_evaluate`** — Embedding kNN + Mirofish-Persona → autonome Klassifikation
4. **`bubble_dispatcher.py`** — Sidecar der Fan-Out bei Klassifikation macht (N broadcast_proposals + N approvals)
5. **Payment-Infra + Crowdfunding-Pipeline** — analog LinkedIn-Muster, aber Multi-Recipient + Payment-Provider drunter
6. **Template-Skill + Browser-Automation-Skill** — Content-Rendering + PayPal-Onboarding

## Out of Scope (bewusst NICHT in diesem Plan)

- **Retry/regenerate rejected bps** — wenn Curator eine bp rejected, bleibt sie rejected. Kein Auto-Regenerate mit neuer Persona-Variante. (User-Entscheidung getroffen.)
- **UI-Redesign OpenFang-Karten** — Karten zeigen channel im Header, mehr nicht. Vollumfängliches Curator-Dashboard = eigener Plan.
- **Live-Payments** — alles bleibt sandbox. Live-Modus = separater Plan mit Extra-Gates.
- **Multi-Provider** (Stripe/Klarna/…) — Payment-Infra hat Provider-Interface aber initial nur PayPal.
- **Klassifikations-Drift-Detection** — wenn sich "was ist marketing" semantisch ändert, kein Auto-Retraining.

---

## Warum diese Reihenfolge? (Der rote Faden)

Die Phasen bauen so aufeinander auf dass **jede Phase eine sinnvolle Zwischenstufe** liefert — man kann jederzeit pausieren ohne dass halb-fertiger Code rumliegt:

```text
Phase 0 — Safety-Net (Tests die IST-Zustand fixieren)
  ↓
Phase 1 — Bubble-Schema-Erweiterung + Status-Aggregation (036+037)
  ↓ [ab hier hat jede Bubble Platz für category/color/channels[]]
Phase 2 — Classifier in bubble_evaluate (Embedding + Mirofish)
  ↓ [ab hier klassifiziert sich jede neue Bubble autonom]
Phase 3 — bubble_dispatcher (Fan-Out + Multi-Approval)
  ↓ [ab hier fließen N broadcast_proposals + OpenFang-Karten pro Bubble]
Phase 4 — n8n-Workflows pro Channel (04-11 broadcast)
  ↓ [ab hier feuern isolierte per-channel-Sends]
Phase 5 — Payment-Infra (standalone) + Browser-Automation-Skill parallel
  ↓ [ab hier kann PayPal Sandbox-Zahlungen abwickeln]
Phase 6 — Crowdfunding-DB-Schema + batch_sender.py + Template-Skill
  ↓ [ab hier fließen Backer-Outreach-Nachrichten mit unique Links raus]
Phase 7 — Live-Modus-Gates + paypal_webhook_handler
  ↓ [ab hier echte $-Flows tracked]
```

**Wenn die Zeit ausgeht:** Phase 0-4 reichen für das **Bubble-Auto-Dispatch-Feature** (LinkedIn/X/Email autonom). Phase 5-7 sind das **Crowdfunding-Add-on** — können später kommen.

---

## Phase 0 — Safety-Net: Tests die den heutigen Zustand einfrieren

**Was mache ich?**
Zwei Tests die dokumentieren wie heute läuft:
- Test A: Bubble mit `kind=post_draft, target_channel=linkedin` erzeugt exakt 1 broadcast_proposal, Migration 034-Trigger propagiert 1:1
- Test B: `bubble_evaluate` liefert heute nur 5-Dim-Score, keine category/channels

**Warum jetzt?**
Weil ab Phase 1 das Schema und die `bubble_evaluate`-Semantik erweitert werden. Ich will schwarz auf weiß dass ich alte Verhalten nicht heimlich kaputtmache.

**Wann ist es fertig?**
- ✅ 2 grüne Tests dokumentieren IST-Verhalten
- ✅ `spaces/marketing/db/035_bubble_pipeline_view.sql` existiert schon (Cockpit-View), wird als Basis für Test-Assertions genutzt

**Deliverables:** 2 Test-Files. Keine Code-Änderung.
**Aufwand:** 1-2 Stunden.

---

## Phase 1 — Bubble-Schema-Erweiterung + Status-Aggregation

**Was mache ich?**

**Migration 036:** neue Columns auf `public.ideas`:

```sql
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS color text;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS channels jsonb DEFAULT '[]';
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS auto_classified boolean DEFAULT false;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS classification_confidence numeric;
ALTER TABLE public.ideas ADD COLUMN IF NOT EXISTS classified_at timestamptz;

ALTER TABLE public.ideas ADD CONSTRAINT ideas_category_known
  CHECK (category IS NULL OR category IN
    ('marketing','crowdfunding','code_project','research','general'));

ALTER TABLE public.ideas ADD CONSTRAINT ideas_channels_is_array
  CHECK (jsonb_typeof(channels) = 'array');
```

**Migration 037:** neuer Aggregations-Trigger — ersetzt 034's 1:1-Mirror:

```sql
CREATE OR REPLACE FUNCTION marketing.aggregate_bubble_status()
RETURNS TRIGGER AS $$
DECLARE
  linked_bubble_id text;
  counts_json jsonb;
  new_status text;
BEGIN
  SELECT bubble_id INTO linked_bubble_id
  FROM public.ideas WHERE broadcast_proposal_id = NEW.id LIMIT 1;
  IF linked_bubble_id IS NULL THEN RETURN NEW; END IF;

  SELECT jsonb_object_agg(status, cnt) INTO counts_json FROM (
    SELECT bp.status, count(*) cnt
    FROM marketing.broadcast_proposals bp
    JOIN public.ideas i ON i.broadcast_proposal_id = bp.id
    WHERE i.id = linked_bubble_id GROUP BY bp.status
  ) t;

  new_status := CASE
    WHEN counts_json ? 'pending_approval' THEN 'pending_approval'
    WHEN counts_json ? 'sent' AND NOT (counts_json ? 'rejected') THEN 'sent'
    WHEN counts_json ? 'sent' AND counts_json ? 'rejected' THEN 'partially_sent'
    WHEN counts_json ? 'rejected' AND NOT (counts_json ? 'sent') THEN 'rejected'
    WHEN counts_json ? 'failed' THEN 'send_failed'
    WHEN counts_json ? 'approved' THEN 'approved'
    WHEN counts_json ? 'draft' THEN 'draft'
    ELSE 'unknown'
  END;

  UPDATE public.ideas SET status = new_status
   WHERE id = linked_bubble_id AND status IS DISTINCT FROM new_status;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_broadcast_propagate_to_bubble ON marketing.broadcast_proposals;
CREATE TRIGGER trg_broadcast_aggregate_to_bubble
  AFTER INSERT OR UPDATE OF status ON marketing.broadcast_proposals
  FOR EACH ROW EXECUTE FUNCTION marketing.aggregate_bubble_status();

-- Update Constraint für neuen `partially_sent`-Wert
ALTER TABLE public.ideas DROP CONSTRAINT IF EXISTS ideas_status_known;
ALTER TABLE public.ideas ADD CONSTRAINT ideas_status_known CHECK (
  status IN ('draft','pending_approval','approved','rejected',
             'sent','partially_sent','send_failed','predicting',
             'ready_to_post','eval_failed','raw','idea')
);
```

**Warum jetzt?**
Ohne Schema-Erweiterung kann Phase 2 (Classifier) nirgends hinschreiben. Und ohne Aggregations-Trigger führen die N broadcast_proposals aus Phase 3 zu inkonsistentem bubble.status. Beide Migrations müssen vor allem anderen laufen.

**Wann ist es fertig?**
- ✅ Beide Migrations applied gegen Live-DB
- ✅ Test: Bubble mit 3 bps (2 approved, 1 rejected) → bubble.status='partially_sent'
- ✅ Regressions-Test: Bubble mit 1 bp (approved) → bubble.status='approved' (kein Bruch)

**Deliverables:**
- `spaces/marketing/db/036_bubble_classifier_columns.sql` (neu)
- `spaces/marketing/db/037_bubble_status_aggregation.sql` (neu, ersetzt Logik aus 034)
- `spaces/marketing/tests/test_bubble_aggregation.py`

**Aufwand:** 0.5 Tag.

---

## Phase 2 — Classifier in `bubble_evaluate`

**Was mache ich?**

Erweitere die schon existente `bubble_evaluate`-Capability (Location: heute in Supabase-Function, target=`supabase:bubble.evaluate`) um einen Klassifikations-Schritt VOR den 5 Dimensions-Score:

```
Input: bubble.description (user_text)
   ↓
1. Qwen3-Embedding (Singleton-Import aus core/qdrant_kg.py)
   ↓
2. kNN-Search in Qdrant Collection `brain-bubble-classes` (top_k=10)
   → schon-klassifizierte Bubbles, dominante category unter den Top-10
   → wenn Collection leer (cold start): skip zu step 3
   ↓
3. Mirofish 5-Persona-Sim mit Prompt-Erweiterung:
   "Für diesen Content: welche category (marketing/crowdfunding/code_project/research/general)?
    Welche channels[]?"
   Jede Persona antwortet strukturiert.
   ↓
4. Aggregation:
   - category = argmax der Persona-Votes gewichtet mit kNN-Ergebnis
   - color = lookup(category) — fest gemapped
   - channels[] = union der Persona-Suggestions, deduped, in fixer Reihenfolge
   - confidence = wie einig waren die Personas (0.0..1.0)
   ↓
5. UPDATE public.ideas
   SET category=..., color=..., channels=..., 
       auto_classified=true, classification_confidence=..., classified_at=now()
   ↓
6. INSERT in Qdrant Collection brain-bubble-classes:
   (bubble_id, embedding, category) — für zukünftige kNN
```

**Farb-Mapping (fest):**
- `marketing` → `#dc2626` (rot)
- `crowdfunding` → `#ea580c` (orange)
- `code_project` → `#2563eb` (blau)
- `research` → `#9333ea` (lila)
- `general` → `#ffffff` (weiß)

**Confidence-Threshold (0.7):** unter 0.7 wird die Bubble NICHT auto_classified — bleibt kategorielos (color=`#ffffff` general), User entscheidet manuell.

**Warum jetzt?**
Weil Phase 3 (dispatcher) daraufhin agiert — der reagiert auf `category`-Änderung. Wenn Phase 2 noch nicht da ist, gibt es keine `category`-Änderungen und Phase 3 sitzt leer.

**Wann ist es fertig?**
- ✅ 5 Test-Bubbles mit unterschiedlichen Descriptions → 5 unterschiedliche categories
- ✅ Cold-Start-Test: Erste Bubble klassifiziert nur via Mirofish (Qdrant leer)
- ✅ Confidence-Test: bewusst ambiguer Text → confidence < 0.7 → bleibt general
- ✅ Qdrant Collection `brain-bubble-classes` überlebt Brain-Restart

**Deliverables:**
- Supabase-Function `bubble_classify` erweitert (SQL/pl/pgsql)
- `vibemind-os/brain/the_brain/core/bubble_classifier.py` — Python-Helper der die Persona-Sim orchestriert
- Qdrant-Collection-Setup-Script
- Tests

**Aufwand:** 1 Tag.

**Risiko + Mitigation:** Doppel-Loading des Qwen3-Embedder-Modells (~3GB VRAM). **Zwingend** den Singleton aus `core/qdrant_kg.py` wiederverwenden.

---

## Phase 3 — bubble_dispatcher.py (Fan-Out-Worker)

**Was mache ich?**

Neuer long-lived Sidecar-Worker analog `bubble_predict_runner.py`. Polled `public.ideas WHERE auto_classified=true AND category IS NOT NULL AND broadcast_proposal_id IS NULL AND array_length(channels) > 0`.

Für jede solche Bubble:
1. Loop über `bubble.channels`:
   - Rendere channel-optimierten Text via **Template-Skill** (Phase 6-Vorgriff — im MVP: Bubble-Description wird 1:1 kopiert)
   - INSERT broadcast_proposal mit (bubble_id, channel=X, draft_body_text=<rendered>, status=draft)
2. Für alle N neuen bps: mint HMAC-Token, request_approval, POST /api/approvals an OpenFang
3. Link bubble.broadcast_proposal_id auf **eine** bp (arbiträr — die aggregation trigger macht den Rest)

**Empty-channels-Fall:** `channels=[]` → kein Fan-Out, Bubble bleibt Notiz. Log-Warning.

**Category=`general`-Fall:** kein Fan-Out — Bubble bleibt in `general`-Pool. User kann manuell in UI Kategorie ändern.

**Category=`crowdfunding`-Fall:** statt broadcast_proposals werden `crowdfunding_batches` angelegt (Phase 6, wenn Schema da).

**Warum jetzt?**
Weil ab hier der Fan-Out-Pfad live wird. Alle Downstream-Phasen (n8n workflows, Crowdfunding) verlassen sich darauf dass für jede klassifizierte Bubble die richtige Anzahl bps/batches entsteht.

**Wann ist es fertig?**
- ✅ Sidecar starten, dann Bubble mit `channels=["linkedin","x","email"]` triggern → 3 bps + 3 OpenFang-Karten
- ✅ Curator klickt in OpenFang UI, bridge relayt → Status-Aggregation propagiert korrekt
- ✅ Cold-restart des Sidecars picke id nicht doppelt (idempotenz check gegen `bubble.broadcast_proposal_id NOT NULL`)

**Deliverables:**
- `spaces/marketing/workers/bubble_dispatcher.py` (neu, ~200 LOC)
- Registriert im Launcher (`Vibemind.debug.ps1` Phase 3)
- Tests

**Aufwand:** 1 Tag.

---

## Phase 4 — n8n-Workflows pro Channel (isoliert, kein IF-filter)

**Was mache ich?**

Für jeden Channel ein separater n8n-Workflow. Naming-Convention `<nn>_<channel>_<action>.json`:

| # | File | Channel | Send-Backend |
|---|---|---|---|
| 04 | `04_linkedin_broadcast.json` | linkedin | n8n linkedIn-Node (existiert) |
| 05 | `05_x_broadcast.json` | x | n8n twitter-Node oder HTTP zu tweepy-Worker |
| 06 | `06_email_broadcast.json` | email | **HTTP-Call zu `send_worker.py :5510`** (12 Gates bleiben da) |
| 07 | `07_discord_broadcast.json` | discord | n8n discord-Node oder HTTP zu Discord-API |
| 08 | `08_telegram_broadcast.json` | telegram | n8n telegram-Node |
| 09 | `09_reddit_broadcast.json` | reddit | n8n reddit-Node |
| 10 | `10_mastodon_broadcast.json` | mastodon | HTTP zu Mastodon-API |
| 11 | `11_instagram_broadcast.json` | instagram | HTTP zu Instagram Graph API |

**Jeder Workflow: gleiches Skelett:**
```
Webhook (path="marketing-<channel>-broadcast")
  → Provider-Call (native n8n-Node ODER HTTP zu Worker)
  → HTTP-Callback zu marketing-API :5510 für audit
  → RespondToWebhook OK
Error-Branch:
  → HTTP-Callback zu marketing-API mit error-status
  → RespondToWebhook failed
```

**KEIN IF-filter** — der Webhook-Path selbst diskriminiert den Channel. `webhook_delivery.py` mapped das Event auf den korrekten Path.

**Warum jetzt?**
Weil Phase 3's Fan-Out ohne Empfänger-Workflows im n8n leerläuft. Erst wenn die Workflows registriert sind, kann eine approved bp tatsächlich einen Send auslösen.

**Wann ist es fertig?**
- ✅ Alle Workflows in n8n :15678 importiert + aktiviert
- ✅ Test-Bubble mit channel=`linkedin` approved → Post erscheint in LinkedIn (sandbox oder test account)
- ✅ Test-Bubble mit channel=`email` approved → `send_worker.py` triggert, Mailpit :54324 zeigt Mail
- ✅ `webhook_delivery.py` erweitert um channel-aware routing

**Deliverables:**
- 8 neue `n8n_workflows/*.json` (04 existiert)
- `spaces/marketing/workers/webhook_delivery.py` erweitert
- `spaces/marketing/n8n_workflows/import.ps1` erweitert für Batch-Import
- Tests

**Aufwand:** 1 Tag (je Workflow ~1h).

---

## Phase 5 — Payment-Infra (standalone) + Browser-Automation-Skill

> **UPDATE 2026-07-02 (User-Entscheidung): PayPal-MCP-first.**
> Es existiert ein offizieller **claude.ai-PayPal-MCP-Connector** (in der Session sichtbar,
> braucht noch OAuth-Autorisierung über claude.ai-Connector-Settings). Entscheidung:
> **Der MCP-Connector ist der primäre Weg für Order/Link-Erstellung + Status-Abfragen.**
> Konsequenzen für diese Phase:
> - `providers/paypal.py` (eigener REST-Client) wird **Fallback**, nicht primär —
>   gebaut wird er nur für das, was der MCP nicht abdeckt.
> - Der **Browser-Automation-Skill schrumpft**: Sandbox-App + Credentials
>   entfallen möglicherweise komplett (MCP bringt eigene Auth mit). Bleibt: Webhook-
>   Registrierung im Dashboard, falls der MCP das nicht kann.
> - **Was der MCP sicher NICHT kann** (bleibt eigene Infra): den `/return`-Redirect-
>   Endpoint hosten und **PayPal-Webhooks empfangen** — ein MCP macht ausgehende
>   Agent-Calls, er ist kein HTTP-Server. `app.py` (:5060) + `paypal_webhook_handler.py`
>   (Phase 7) bleiben also unverändert nötig.
> - **Erster Schritt dieser Phase ist jetzt ein Tool-Inventar:** Connector autorisieren,
>   dann via ToolSearch prüfen welche Tools er exposed (create_order? payment_links?
>   invoices? refunds? webhook-mgmt?) und die Provider-Schnittstelle darauf mappen.
> - Aufwandsschätzung sinkt voraussichtlich von 1.5d auf ~1d, wenn der MCP
>   Order-Erstellung mit Redirect-URLs unterstützt.
>
> **UPDATE 2 (gleicher Tag): Phase-0-Spike per REST BESTANDEN.** Sandbox-Credentials
> liegen in `Vibemind_V1/.env` (PAYPAL_CLIENT_ID + PAYPAL_SECRET) und sind verifiziert:
> OAuth ✅, Order v2 mit `experience_context` ✅, `payer-action`-Link generiert ✅
> (Order `7PA11461KG265005W`). Konsequenzen:
> - Browser-Automation-Skill Steps 01-03 (App anlegen, Credentials extrahieren)
>   sind für Sandbox **obsolet** — Credentials existieren schon.
> - Webhook-Registrierung geht auch per REST (`POST /v1/notifications/webhooks`) —
>   Browser-Automation evtl. komplett unnötig.
> - Der eigene REST-Client ist damit **bewiesen und einsatzbereit** — der PayPal-MCP
>   wird zur optionalen Convenience (Tool-Inventar trotzdem machen wenn autorisiert),
>   ist aber **kein Blocker mehr** für Phase 5/6.
>
> **UPDATE 3 (gleicher Tag): Kompletter E2E-Zahlungs-Loop BESTANDEN.** Sandbox-Buyer
> hat einen generierten Link real bezahlt, Capture automatisch gefeuert:
> Order `6M511271B1499743T` → APPROVED nach ~460s → `CAPTURE COMPLETED`
> (capture_id `74924231986097626`, **1.00 EUR**). Bewiesene Kette:
> OAuth → Order+Redirect-Context → unique Link → Buyer zahlt → Status-Poll erkennt
> APPROVED → Auto-Capture. Learnings:
> - **Währung: EUR** (nicht USD) — deutsche Buyer-Accounts stolpern über
>   Cross-Currency-Conversion im Checkout. Beantwortet offene Frage #4 des
>   ursprünglichen backer-checkout-Plans: `BACKER_CURRENCY=EUR`.
> - **Browser-Automation für Sandbox-Zahlungen scheitert an Bot-Detection**
>   (Playwright kam durch Login+Review, aber PayPal verwirft den finalen
>   Pay-Submit im automatisierten Browser still). Klick-Tests laufen manuell;
>   Stealth-Automation nur falls später CI-Bedarf.
> - **Status-Polling (GET /v2/checkout/orders/{id}) funktioniert als
>   Tracking-Fallback** neben Webhooks — wichtig für `paypal_webhook_handler`-
>   Design in Phase 7: Polling als Backstop einbauen, nicht nur Webhook.

**Was mache ich?**

**Payment-Infra** in `Desktop/VibeMind-OS/payment-infra/`:

```
payment-infra/
  providers/
    __init__.py            # get_provider("paypal") -> instance
    paypal.py              # PayPalProvider mit den 3 Kernmethoden
    stripe.py              # Stub für später
  app.py                   # optionaler Flask HTTP-Service :5060
                           #   POST /v1/payment-links
                           #   GET  /return?token=<oid>
                           #   POST /webhook
                           #   GET  /orders/<id>
  templates/return.html
  tests/
  requirements.txt
  .env.example
```

**Provider-Interface:**
```python
class PaymentProvider(Protocol):
    def create_payment_link(
        self, amount: str, currency: str,
        return_url: str, cancel_url: str,
        metadata: dict | None = None,
    ) -> PaymentLinkResult: ...  # {order_id, approve_url}
    
    def capture(self, order_id: str) -> CaptureResult: ...
    
    def verify_webhook(
        self, headers: dict, raw_body: bytes,
    ) -> WebhookVerification: ...  # {ok: bool, event_type, order_id}
```

PayPalProvider implementiert das über Orders v2 REST API (Refactor aus existierendem `paypal_client.py` + neue `create_order_with_link` mit `experience_context`).

**Browser-Automation-Skill** in `Vibemind_V1/vibemind-os/skills/paypal-dev-onboarding/`:

```
paypal-dev-onboarding/
  SKILL.md                # Trigger-Pattern, Anleitung
  steps/
    01_login.md           # openclaw-visible öffnet https://developer.paypal.com
    02_create_sandbox_app.md
    03_extract_credentials.md
    04_register_webhook.md
    05_create_sandbox_buyer.md
    06_write_env.md
```

Skill wird über openclaw-visible ausgeführt (sichtbares Chrome). User macht 2FA manuell, Skill klickt den Rest, füllt am Ende `payment-infra/.env`.

**Warum jetzt?**
Weil ohne Sandbox-Credentials Payment-Infra nicht testbar ist. Und ohne Payment-Infra kann Phase 6 (Crowdfunding) nichts tun. Diese Phase ist der Fundament-Layer für alles Crowdfunding-Verwandte.

**Wann ist es fertig?**
- ✅ `payment_infra.providers.get_provider("paypal").create_payment_link(...)` liefert `approve_url`
- ✅ Manueller Sandbox-Zahlungs-Test: Link → paypal.com → zahlen → Redirect auf `/return` → capture → COMPLETED
- ✅ Webhook-Verify mit echtem Sample-Event
- ✅ Browser-Automation-Skill füllt `.env` erfolgreich

**Deliverables:**
- Payment-Infra-Repo/-Ordner mit Python-Package + Flask-Service
- Browser-Automation-Skill
- Beide getestet in Sandbox

**Aufwand:** 1.5 Tag (parallel möglich zu Phase 4).

---

## Phase 6 — Crowdfunding-Pipeline + Template-Skill

**Was mache ich?**

**Crowdfunding-DB-Schema** (Migrations 040-043 in `spaces/marketing/crowdfunding/db/`):

```sql
-- 040: crowdfunding_batches (analog broadcast_proposals)
CREATE TABLE marketing.crowdfunding_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bubble_id text REFERENCES public.ideas(id),
    channel text NOT NULL,              -- email, linkedin-dm, x-dm, ...
    status text NOT NULL DEFAULT 'draft',
    recipients_audience_id uuid REFERENCES marketing.audiences(id),
    amount text NOT NULL DEFAULT '1.00',
    currency text NOT NULL DEFAULT 'USD',
    -- Approval flow (spiegelt broadcast_proposals)
    approval_channel text,
    approval_requested_at timestamptz,
    approval_token_hash text,
    approval_token_raw text,
    openfang_approval_id uuid,
    approved_at timestamptz, approved_by text,
    rejected_at timestamptz, rejected_by text, rejection_reason text,
    -- Send result
    sent_at timestamptz, sent_batch_size int,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT crowdfunding_status_known CHECK (
      status IN ('draft','pending_approval','approved','rejected','sent','failed'))
);

-- 041: crowdfunding_contributions (Ledger — pro Empfänger 1 row)
CREATE TABLE marketing.crowdfunding_contributions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id uuid REFERENCES marketing.crowdfunding_batches(id),
    recipient_id text NOT NULL,
    recipient_name text,
    order_id text UNIQUE,               -- PayPal order ID
    approve_url text NOT NULL,
    amount text NOT NULL, currency text NOT NULL,
    status text NOT NULL DEFAULT 'created',
                                        -- created | approved | paid | failed
    created_at timestamptz NOT NULL DEFAULT now(),
    paid_at timestamptz,                -- NUR paypal_webhook_handler schreibt
    payment_metadata jsonb,
    UNIQUE (batch_id, recipient_id)     -- Idempotenz-Schutz
);

-- 042: Status-Propagation (analog 037 für crowdfunding)
-- Trigger: bp-approve → auto emit crowdfunding.distribute event

-- 043: v_crowdfunding_pipeline View (analog 035)
```

**batch_sender.py** analog send_worker.py — 3 Modi (dry_run/shadow/live), 12 Gates spezifisch für Payment:

```
G1 kill-switch (MARKETING_CROWDFUNDING_SEND_ENABLED)
G2 FREEZE-file (logs/marketing/CROWDFUNDING_FREEZE)
G3 batch-resolve + status='approved'
G4 payment-infra reachable
G5 PAYPAL_ENV=sandbox (default) oder --allow-live
G6 recipients-snapshot (frozen)
G7 idempotency-check gegen ledger
G8 confirm-token
G9 payment-provider-loopback-probe (test-order create+cancel)
G10 outbox-preview-count matches recipient-count (dry-run)
G11 atomic ledger claim (INSERT ... ON CONFLICT DO NOTHING)
G12 paid_at NUR von paypal_webhook_handler
```

Pro Recipient:
```python
approve_url = payment_infra.create_payment_link(
    amount=batch.amount, currency=batch.currency,
    return_url=f"{PUBLIC_BASE_URL}/return",
    cancel_url=f"{PUBLIC_BASE_URL}/cancel",
    metadata={"recipient_id": r.id, "batch_id": batch.id}
).approve_url

message = template_skill.render(
    channel=batch.channel,
    recipient=r,
    approve_url=approve_url,
    batch=batch,
)

if mode == "dry_run":
    (outbox / f"{r.id}.txt").write_text(message)
    ledger.upsert_created(recipient_id=r.id, batch_id=batch.id,
                           order_id=..., approve_url=approve_url)
elif mode == "live":
    dispatch_via_channel(batch.channel, r, message)  # Email/DM/etc
    ledger.mark_sent(order_id)
```

**Template-Skill** `vibemind-os/skills/backer-outreach-template/`:

```
backer-outreach-template/
  SKILL.md                # Trigger + Signature: render(channel, recipient, approve_url, batch)
  templates/
    email.md              # Basis-Template mit {{recipient_name}}, {{approve_url}}, {{amount}}
    linkedin_dm.md
    x_dm.md
    discord_dm.md
  examples/
```

MVP: einfaches String-Templating. V2: LLM-basierte Persona-Anpassung.

**n8n workflows** für Crowdfunding (12-15):
```
12_crowdfunding_email.json      → HTTP-Call zu batch_sender.py :5510
13_crowdfunding_linkedin_dm.json → HTTP-Call zu batch_sender.py :5510
14_crowdfunding_x_dm.json
15_crowdfunding_discord_dm.json
```

**Warum jetzt?**
Weil erst jetzt alle Fundamente da sind: Bubble kann classified werden als `crowdfunding` (Phase 2), dispatcher legt crowdfunding_batches an (Phase 3 mit Erweiterung), Payment-Provider kann Links machen (Phase 5).

**Wann ist es fertig?**
- ✅ Bubble mit "Crowdfunding-Text" → category=crowdfunding, channels=["email"]
- ✅ 1 crowdfunding_batch angelegt, Approval-Karte in OpenFang
- ✅ Curator approved → n8n workflow feuert → batch_sender.py --mode=dry_run
- ✅ outbox/ enthält N Nachrichten mit N unique approve_urls
- ✅ Ledger hat N rows mit status='created'

**Deliverables:**
- 4 Migrations
- `spaces/marketing/crowdfunding/workers/batch_sender.py`
- `spaces/marketing/crowdfunding/tools/_paypal_paranoid.py`
- `spaces/marketing/crowdfunding/api/routes.py`
- Template-Skill
- 4 n8n workflows

**Aufwand:** 2 Tage.

---

## Phase 7 — Live-Modus + PayPal-Webhook-Handler

**Was mache ich?**

**paypal_webhook_handler.py** — analog `delivered_webhook.py`:
- Long-lived Sidecar oder `--serve :5514` HTTP-Endpoint
- Empfängt PayPal-Webhooks (`PAYMENT.CAPTURE.COMPLETED`)
- Verifies Signatur via `payment_infra.verify_webhook`
- **Einziger Writer** von `crowdfunding_contributions.paid_at` (Gate G12)
- Atomicity: `WHERE paid_at IS NULL` guard, zweiter Webhook = no-op

**Live-Modus-Gates** in `_paypal_paranoid.py` scharfschalten:
- G5 checked auf `--allow-live` flag
- G9 loopback-probe muss gegen live-API succeeden (mit tiny amount, immediate cancel)
- G12 test bestätigt: `batch_sender.py` schreibt nirgends `paid_at`

**Warum jetzt?**
Alles davor war sandbox. Erst wenn Backer-Outreach-Nachrichten wirklich rausgehen könnten (live), brauchen wir den Tracking-Layer.

**Wann ist es fertig?**
- ✅ Sandbox-Zahlung fließt komplett durch: link click → paypal → return → capture → paypal-webhook → paid_at gesetzt
- ✅ Zweiter Webhook-Call für same order_id = no-op (test)
- ✅ Live-Gate-Test: `--mode=live` ohne `--allow-live` → abort
- ✅ View `v_crowdfunding_pipeline` zeigt Batch-Status (created / paid / pending)

**Deliverables:**
- `spaces/marketing/crowdfunding/workers/paypal_webhook_handler.py`
- Live-Gate-Tests
- Config-Doku für Webhook-Registrierung in PayPal-Dashboard (nutzt Browser-Automation-Skill aus Phase 5)

**Aufwand:** 1 Tag.

---

## Die Roadmap auf einen Blick

```text
Tag 1                Tag 2-3             Tag 4-6            Tag 7-8
─────────────────────────────────────────────────────────────────────
Phase 0  Phase 1     Phase 2   Phase 3   Phase 4  Phase 5   Phase 6  Phase 7
Tests    Schema      Classifier Fan-Out  n8n WFs  Payment-  Crowdfunding Live
1-2h     0.5d        1d         1d       1d       Infra+    2d           1d
                                                  Browser
                                                  1.5d (par)
▓        ▓▓▓▓        ▓▓▓▓▓▓▓▓  ▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓  ▓▓▓▓▓▓   ▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓
                                                                       
[Nach Phase 4 ist Bubble-Auto-Dispatch für ALLE Channels live —
 Marketing-Post läuft autonom. Phase 5-7 = Crowdfunding-Add-On.]
```

**Notausstieg:**
- Nach Phase 4 (~4 Tage): Auto-Klassifikation + Multi-Channel-Fan-Out für Marketing-Bubbles ist fertig. Crowdfunding kann später kommen.
- Payment-Infra + Crowdfunding (Phase 5-7) sind **das Add-On** — man kann sie beliebig weit nach hinten schieben.

---

## Implementierungs-Reihenfolge (TL;DR)

| Phase | Aufwand | Wert | Abhängigkeit |
|---|---|---|---|
| 0 — Safety-Net | 1-2h | Vorbereitung | — |
| **1 — Schema (036+037)** | **0.5d** | Fundament für alles | Phase 0 |
| **2 — Classifier** | **1d** | größter neuer Fähigkeits-Sprung | Phase 1 |
| 3 — bubble_dispatcher | 1d | aktiviert Fan-Out | Phase 1+2 |
| **4 — n8n Workflows** | **1d** | **User-sichtbar** — Multi-Channel-Send live | Phase 3 |
| 5 — Payment-Infra + Browser-Skill | 1.5d | parallel möglich | ab Phase 0 parallel |
| 6 — Crowdfunding | 2d | Crowdfunding-Feature | Phase 5 |
| 7 — Live + Webhook-Handler | 1d | Real-Money-Tracking | Phase 6 |

**Gesamt:** ~7-8 Tage für Phase 0-7. Wenn nur Bubble-Auto-Dispatch (ohne Crowdfunding): **Phase 0-4 = 4 Tage**.

---

## 3 Entscheidungen die du treffen musst

### 1. Payment-Infra-Location?

- **A)** `Desktop/VibeMind-OS/payment-infra/` — standalone Ordner im Meta-Repo neben `backer-checkout/` und `x-pathfinder/`. Open-Source-tauglich später.
- **B)** `Vibemind_V1/vibemind-os/payment-infra/` — im Haupt-Repo als weiterer Modul-Ordner.

**Meine Empfehlung: A** — Payment-Infra hat nichts mit VibeMind-Spezifika zu tun, ist eine wiederverwendbare Library/Service. Standalone gibt Option auf Open-Source ohne Repo-Split später.

### 2. Confidence-Threshold für Auto-Klassifikation?

- **A)** 0.5 — aggressiv, viel läuft autonom, mehr Fehl-Klassifikationen die Curator korrigiert
- **B)** 0.7 — Standard, ausgewogen
- **C)** 0.85 — konservativ, viel bleibt weiß/general, User klassifiziert oft manuell

**Meine Empfehlung: B** (0.7). Start-Wert der später via Config anpassbar sein sollte. Kalibrierung auf Basis erster echter Klassifikations-Runs.

### 3. Backpressure für Fan-Out?

- **A)** Unlimited — Bubble mit 6 channels feuert 6 parallele n8n runs
- **B)** Cap auf N=3 concurrent — extras queuen
- **C)** Sequentiell — 1 nach dem anderen, Curator sieht Karten in Reihenfolge

**Meine Empfehlung: A** — n8n handled Concurrency selbst. Zusätzliches Throttling ist premature optimization. Kann später via n8n-Queue-Config nachgeschoben werden falls nötig.

---

## Fazit — die 3 Sätze zum Mitnehmen

1. **Der schwere Teil des Musters ist schon gebaut** — 1-bp-pro-(bubble,channel), OpenFang-Approval-Bridge, Webhook-Bus, n8n-Workflow-Pattern. Wir bauen kein neues Muster, wir **skalieren** das existente.

2. **Der Sprung ist die autonome Klassifikation** — Bubble beschreibt sich selbst (category+color+channels+confidence), der Rest folgt aus der Fan-Out-Regel.

3. **Phase 0-4 ist der User-sichtbare Kern** (~4 Tage) — danach kannst du **Crowdfunding als Add-On** in Phase 5-7 in Ruhe nachziehen.

---

## Referenzen

- [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) — Top-Level VibeMind-Architektur
- [`spaces/marketing/README.md`](../README.md) — Marketing-Ops Overview
- [`spaces/marketing/AGENTS.md`](../AGENTS.md) — Marketing-Hard-Rules (7 kritische, 15 Gate-Ebenen)
- [`spaces/marketing/db/030_broadcast_proposals.sql`](../db/030_broadcast_proposals.sql) — bp-Schema (Basis für per-channel Fan-Out)
- [`spaces/marketing/db/031_openfang_approval_bridge.sql`](../db/031_openfang_approval_bridge.sql) — Bridge-Design + HMAC-Token
- [`spaces/marketing/db/034_bubble_status_propagate.sql`](../db/034_bubble_status_propagate.sql) — 1:1-Mirror den Migration 037 zu Aggregation ersetzt
- [`spaces/marketing/db/035_bubble_pipeline_view.sql`](../db/035_bubble_pipeline_view.sql) — Pipeline-View (aus früherem Cockpit-Friction-Fix)
- [`spaces/marketing/workers/openfang_approval_bridge.py`](../workers/openfang_approval_bridge.py) — Bridge-Worker (bleibt unverändert bei Fan-Out)
- [`spaces/marketing/workers/send_worker.py`](../workers/send_worker.py) — 12-Gate-Enforcer für Email (bleibt Enforcer, n8n triggert nur)
- [`spaces/marketing/n8n_workflows/04_linkedin_broadcast.json`](../n8n_workflows/04_linkedin_broadcast.json) — Vorbild für 05-11 Broadcast + 12-15 Crowdfunding
- [`spaces/marketing/mirofish/predict_post_reception.py`](../mirofish/predict_post_reception.py) — Mirofish-Persona-Sim (wird für Classifier wiederverwendet)
- [`vibemind-os/brain/the_brain/data/capabilities.yaml`](../../../vibemind-os/brain/the_brain/data/capabilities.yaml) — `bubble_evaluate`-Capability die erweitert wird
- [`vibemind-os/brain/the_brain/core/qdrant_kg.py`](../../../vibemind-os/brain/the_brain/core/qdrant_kg.py) — Qwen3-Embedder-Singleton (wiederverwenden!)
- `Desktop/VibeMind-OS/backer-checkout/` — Existierender PayPal-Sandbox-Testboden, wird zerlegt in Payment-Infra + Crowdfunding
- Memory `project_marketing_ops_space` — Marketing-Ops-Space-Design
- Memory `project_openfang_agent_ops` — OpenFang-Approvals-UI-Design
