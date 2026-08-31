# Channel-Piloten — Setup-Anleitung

**3 channels in parallel: Discord, LinkedIn, Reddit.**
Du sammelst credentials, ich automatisiere den rest.

---

## Discord — schnellster Pilot

**Status:** DISCORD_BOT_TOKEN ist bereits in .env. Bot vermutlich angelegt aber noch nicht eingeladen + getestet.

### Was du noch tun musst (5 min)

1. **Bot zu einem Discord-Server invitieren** (falls noch nicht):
   - Gehe zu `https://discord.com/developers/applications/<dein-bot-app-id>/oauth2/url-generator`
   - Scopes: ✅ `bot` + ✅ `applications.commands`
   - Bot Permissions: ✅ `Send Messages` (+ ggf. `Embed Links`, `Attach Files`)
   - Copy URL, in Browser öffnen, Server auswählen, Authorize
2. **Developer-mode aktivieren in Discord-Client:**
   - Settings (zahnrad) → Advanced → Developer Mode = ON
3. **Channel-ID kopieren** vom test-channel:
   - Rechtsklick auf einen channel → "Copy ID"
4. **An mich:** Die channel-ID (sieht aus wie `1234567890123456789`, 18-19 digits)

### Was ich autonom mache (15 min)

1. `POST http://127.0.0.1:4200/api/channels/discord/configure` mit DISCORD_BOT_TOKEN aus env
2. `POST http://127.0.0.1:4200/api/channels/discord/test` mit test-message
3. `python -m spaces.marketing.tools.sign_recipient --channel discord --recipient-id <deine-CH-ID> --approved-by felix --label "test-channel" --insert`
4. `UPDATE marketing.channel_config SET enabled=true WHERE channel='discord'`
5. Test-campaign mit `channel='discord'` erstellen
6. DRY_RUN → confirm_token bekommen
7. LIVE → Nachricht im Discord-channel
8. Verify in `marketing.campaign_sends_openfang`

### Aufwand-summary

- **Du:** 5 min (channel-ID + ggf bot-invite)
- **Ich:** 15 min autonom
- **Resultat:** Discord live

---

## LinkedIn — OAuth flow

**Status:** Noch keine LinkedIn-app, keine credentials.

### Was du tun musst (15 min)

1. **LinkedIn-Developer-account:**
   - Gehe zu `https://developer.linkedin.com/`
   - Sign in mit deinem normalen LinkedIn-account
2. **App erstellen:**
   - "Create App" → Name: "VibeMind Marketing"
   - Logo, LinkedIn-Page (deine Company-Page oder personal), Privacy-URL (kann später)
3. **Products hinzufügen (wichtig!):**
   - Tab "Products" → "Share on LinkedIn" anfordern (für post-erstellen)
   - Auch "Sign In with LinkedIn using OpenID Connect" (für OAuth)
   - Approval kann 0-24h dauern, meistens instant
4. **OAuth-credentials kopieren:**
   - Tab "Auth" → "Application credentials"
   - Client ID + Client Secret notieren
5. **Redirect-URL eintragen:**
   - Tab "Auth" → "Authorized redirect URLs" → `http://localhost:15678/rest/oauth2-credential/callback`
6. **An mich:**
   - Client ID
   - Client Secret
   - LinkedIn-Person-URN (siehe unten)

### Person-URN ermitteln

LinkedIn-Posts brauchen `author=urn:li:person:XXXXX`. Dein URN bekommst du via:

- Login → Profil-Foto klicken → in der URL: `linkedin.com/in/<deinHandle>/` → Handle merken
- Oder: `GET https://api.linkedin.com/v2/me` mit OAuth-token → `id`-feld ist der URN

(Ich kann das später auch selber via OAuth-flow holen.)

### Was ich autonom mache (45 min)

1. **n8n-credential anlegen** "LinkedIn OAuth2" mit client_id + secret
2. **n8n-workflow `marketing-linkedin-broadcast`** erstellen:
   - Webhook trigger
   - LinkedIn-node "Create a post" mit `{{ $json.body_text }}`
   - Callback an `/api/curator/broadcasts/{id}/result`
3. **Test-template + audience anlegen:**
   - Audience: nur dein LinkedIn-URN (1 row in neuer table `marketing.linkedin_recipients`)
   - Template: kurzer test-post
4. **DRY_RUN** → confirm_token
5. **LIVE** → echter post auf deinem LinkedIn

### Caveat

- **Personal posts:** posten als du (`author=urn:li:person:XXXX`)
- **Company-Page-posts:** posten als Firma (`author=urn:li:organization:XXXX`), braucht Org-Admin-permission
- Rate-limit: ~25 posts/day für personal, ~100/day für Org

### Aufwand-summary

- **Du:** 15 min (developer-app + URN)
- **Ich:** 45 min autonom
- **Resultat:** LinkedIn live für personal-posts

---

## Reddit — Script-App

**Status:** Noch keine Reddit-app, keine credentials.

### Was du tun musst (10 min)

1. **Reddit-account verifiziert** (E-Mail bestätigt, mindestens 1 woche alt — sonst posting-restrictions)
2. **App registrieren:**
   - Gehe zu `https://www.reddit.com/prefs/apps`
   - Scroll runter → "create another app..." button
   - **Wichtig: type = "script"** (NICHT "web app")
   - Name: "VibeMind Marketing"
   - About URL: deine site oder leer
   - Redirect URI: `http://localhost:15678/rest/oauth2-credential/callback`
   - "create app"
3. **Credentials kopieren:**
   - Unter dem App-namen: client_id (14 chars, direkt unter "personal use script")
   - Secret: button "show" daneben
4. **An mich:**
   - client_id
   - client_secret
   - dein reddit-username (z.B. `felix_vibemind`)
   - dein reddit-password (für script-app benötigt)
   - test-subreddit-name (z.B. `r/test` ist neutrale option)

### Was ich autonom mache (45 min)

1. **n8n-credential anlegen** "Reddit OAuth2" mit allen credentials
2. **n8n-workflow `marketing-reddit-broadcast`** erstellen:
   - Webhook trigger
   - Reddit-node "Submit post" mit subreddit + title + body
   - Callback an marketing
3. **Marketing-side:**
   - Migration: `marketing.reddit_recipients` (subreddit_name) — analog zu telegram_recipients
   - Signed allowlist-entry für `r/test` (oder welcher subreddit du nennst)
4. **DRY_RUN → LIVE → Test-post in r/test**

### Caveat

- Subreddits haben **eigene rules** (kein self-promotion, karma-mindesten, etc.)
- `r/test` ist explizit für tests, keine moderation
- Andere subreddits können dich bannen wenn auto-posts gegen rules verstoßen
- Rate-limit: ~10 posts/10min für authenticated user

### Aufwand-summary

- **Du:** 10 min (app + credentials)
- **Ich:** 45 min autonom
- **Resultat:** Reddit live für r/test

---

## Status-table

| Pilot | Was wir brauchen | Wer | Status |
|---|---|---|---|
| Discord | Channel-ID | Du | ⏳ warten |
| LinkedIn | Developer-app + Client_ID + Secret + URN | Du | ⏳ warten |
| Reddit | Script-app + Client_ID + Secret + Username + Password + Subreddit | Du | ⏳ warten |

**Sobald du mir die Daten gibst (auch nur für einen), starte ich automatisch.**

---

## Was alle 3 Piloten gemeinsam beweisen werden

1. **n8n als channel-transport** funktioniert: marketing-API ruft webhook, n8n posted, callback an marketing
2. **Time-to-channel-live** in der Praxis: wie schnell wirklich pro channel
3. **Credential-store-comparison:** n8n-UI vs OpenFang-CLI für token-management
4. **Audit-trail-completeness:** sehen wir alle posts in marketing.campaign_sends?
5. **Rate-limit-handling:** wie n8n's retry-logic mit channel-rate-limits umgeht

## Nach den 3 Piloten

Ich schreibe eine **Vergleichstabelle** (n8n native vs OpenFang native) mit konkretem aufwand pro channel + qualität. Dann entscheidest du:

- Soll der finale stack n8n-only sein für ALL channels außer email+telegram?
- Oder hybrid: OpenFang für einige, n8n für andere?
- Oder umgekehrt — alle native (OpenFang/code)?

Das ist die echte architecture-entscheidung, danach läuft Schicht 7C automatisch durch.
