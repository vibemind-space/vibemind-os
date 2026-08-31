# Marketing-Cockpit Friction Log

**Datum:** 2026-06-18
**Kontext:** Realer end-to-end Run der 7-Schritt-Marketing-Pipeline um zu identifizieren wo ein
Cockpit-UI Mehrwert hätte. Aufgabe war: linearer Run **ohne n8n aktivieren** (also kein realer LinkedIn-Post).

## Verlauf

### Step 0 — Stack-Recovery (Infra)
- Docker daemon ging zwischendurch zweimal verloren (WSL Mirrored hang per [memory](feedback_docker_wsl_mirrored_hang.md))
- Stack vom Launcher hochgefahren: 30 Container starten, Supabase-DB braucht 75s bis ready
- Marketing-API (host-native), Bridge, Bubble-Predict-Runner manuell aus PowerShell + .env-Preload starten
- **FRICTION:** Drei host-native python Prozesse (api, bridge, runner) müssen separat gestartet werden,
  Launcher kennt sie nicht. Per memory [feedback_launcher_stop_openfang.md] bekanntes Pattern.

### Step 1 — Bubble erstellen
**Was ich machen wollte:** POST-Draft-Bubble für "LinkedIn Launch — Agentic OS Beta opens" anlegen.

**Was ich tatsächlich tun musste:**
1. Title + Body in PowerShell-Heredoc schreiben
2. Body in `$env:TEMP\bubble_body.txt` schreiben um Quoting-Hölle zu umgehen
3. `docker cp` body zum DB-Container
4. `INSERT INTO public.ideas ... pg_read_file('/tmp/body.txt')` via `docker exec psql`

**Friction:** Es gibt **keinen `POST /api/bubbles` endpoint** und kein UI. Nur die DB-Direct-Path geht.
**Cockpit-Wert:** ⭐⭐⭐⭐⭐ — "+New Post-Draft"-Form mit Title-Field + Markdown-Editor + Channel-Dropdown wäre
der größte UX-Win. ~50 LOC für form + POST-endpoint.

### Step 2 — Bubble-Sync → Rowboat-Vault
**Erwartung:** Bubble erscheint als `~/.rowboat/knowledge/Projects/VibeMind - LinkedIn Launch — ....md`

**Realität:** Daemon `_run_both.py` startet, aber:
```
[SupabaseDB] GET http://localhost:54321/rest/v1/ideas?... <urlopen error WinError 10061>
```
Stack exposed Supabase-Kong (`:8000`) und supabase-rest (`:3000`) **nur intern**, kein `:54321` auf Host.

**Friction:** Bestehende sync-config zeigt auf Port der nie published wurde. Per memory war der Sync
"ALLE 3 PHASEN FERTIG + SCHARFGESCHALTET IM DRY-RUN" — aber port-mapping fehlt scheinbar nach Stack-Recovery.
**Cockpit-Wert:** Falls Cockpit Rowboat-CDP einbettet, **brauchen wir bubble-sync gar nicht** für den Cockpit-Flow.
Direkter API → DB → Cockpit-Render reicht. Sync ist dann nice-to-have für Rowboat-Quereinsteiger.

### Step 3 — Mirofish-Predict
**Erwartung:** POST `/api/bubbles/c1c67f73/predict` → runner pickt auf → mirofish persona-sim auf llama3.1.

**Realität:** Mirofish-Backend port `:5101` ist im Container live (curl from inside = `{"status":"ok"}`),
aber **HOST kann nicht connecten**. Test-NetConnection 127.0.0.1:5101 → False. Auch nach `docker restart mirofish-app`.

**Friction:** WSL2-Docker port-forwarding flackert nach jedem WSL-Mirrored-hang. Windows-Reboot nötig.
**Cockpit-Wert:** Nicht Cockpit's Job — das ist Infra. Aber: Cockpit könnte einen "Mirofish-Health"-Badge
zeigen damit man sofort sieht ob Predict möglich ist BEVOR man auf den Button drückt.

### Step 4 — Validate in Rowboat
Blocked durch Step 2 (sync funktioniert nicht).

**Cockpit-Wert:** Wenn Cockpit Rowboat-CDP über iframe einbettet (siehe memory [project_rowboat_ui_cdp.md])
können wir das ganze Bubble-Sync-Spiel umgehen — direkt im Cockpit Bubble-text editieren, statt erst nach
Rowboat zu syncen, dort editieren, zurück-syncen, in der Marketing-API nachverarbeiten.

### Step 5-6 — Publish + Approve
Nicht ausgeführt weil Predict (Step 3) noch nicht durch ist und unsere Smokes vorhin schon den Approve-Pfad
verifiziert haben. Würden funktionieren, brauchen nur Marketing-API + OpenFang (beide UP).

## Erkenntnisse für das Cockpit-Design

### Top-Pain-Points (in Reihenfolge der Häufigkeit)

1. **Bubble-Erstellung ist DB-Direct.** Kein einziger end-user-friendly Pfad existiert. 5⭐ Pain.
2. ~~**Status-Monitoring erfordert SQL.** Ich musste 5+ mal `SELECT status, mirofish_score, broadcast_proposal_id FROM public.ideas` ausführen. 4⭐ Pain.~~ **GEFIXT 2026-06-20** in [035_bubble_pipeline_view.sql](../db/035_bubble_pipeline_view.sql) — `marketing.v_bubble_pipeline` liefert bubble + proposal + derived `pipeline_stage` in 1 query.
3. **Service-Health unklar.** Welche der 5 abhängigen Services (DB, mirofish-app, marketing-api, openfang, bridge) ist down? Erforderte 3 separate `Test-NetConnection`-Runs. 4⭐ Pain.
4. **Tab-Wechsel pro Step:** PowerShell (DB-query) → Browser (OpenFang Approvals) → PowerShell (verify) → Browser (LinkedIn check). 3⭐ Pain.

### Was das Cockpit BRAUCHT (Phase 1 MVP)

| Component | Wofür | Aufwand |
|---|---|---|
| Post-Drafts-Liste | Tabelle: title, channel, status, mirofish_score, last_modified | klein (1 GET) |
| "+ New Draft" Modal | Title + Channel-Dropdown + Markdown-Editor + Save → POST /api/bubbles | mittel (form + neuer endpoint) |
| Per-Row Actions | "Predict" + "Publish" Buttons + "View Report" link | klein (3 POSTs) |
| Health-Badges | DB ✓, Mirofish ✓, OpenFang ✓, n8n ✓/✗ — sichtbar oben | klein (5 health-pings) |
| Pending-Approvals-Liste | spiegelt OpenFang /api/approvals, ohne Tab-Wechsel | mittel (poll + display) |

### Was das Cockpit NICHT braucht (Phase 1)

- Rowboat-Embed (sobald wir Markdown-Editor haben, wozu noch sync nach Rowboat?)
- Video-Space-Asset-Picker (noch nicht specced)
- A/B-Test-UI (für 100+ posts/month sinnvoll, jetzt zero)
- Detail-Drilldown auf Personas (`drilldown_persona` reicht als API für später)

## Empfehlung

**Bauen, sobald wir eine echte Marketing-Aktion live hatten** (1× n8n aktiviert + 1 echter Post).
Vorher: Cockpit-Mockup, nicht Cockpit-Code. Die UX-Entscheidungen brauchen echte Daten, nicht
Vermutungen — und die haben wir nach 1 echtem Post.

Zwischenstand bis dahin: ~~**PostgreSQL-View** anlegen~~ **erledigt 2026-06-20** —
[035_bubble_pipeline_view.sql](../db/035_bubble_pipeline_view.sql) joint bubble + proposal + derived `pipeline_stage`.
Status-Check ist jetzt 1 query, killt Pain-Point #2.

```sql
-- Beispiel: "wo ist post c1c67f73?"
SELECT pipeline_stage, channel, mirofish_score, proposal_status
  FROM marketing.v_bubble_pipeline WHERE bubble_id = 'c1c67f73-...';
```

Stages: `draft | predicted | awaiting_approval | approved | sent | rejected | send_failed` (+ unbekannte states via fallback).
