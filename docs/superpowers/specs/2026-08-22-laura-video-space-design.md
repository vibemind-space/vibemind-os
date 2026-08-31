# Laura als VibeMind Video-Space

_Design-Spec, 2026-08-22. Entscheidungen mit dem User abgestimmt (Session Laura/Narrated-Reel):
alte Pipe weitgehend ersetzen, Rowboat-Publish mit Template, Konfiguration über die
Space-Registry → OpenFang, Event-Mapping „wie unser Chat", Laura-UI zunächst als Embed._

_Ergänzt 2026-08-22 (2. Session, nach Verifikation gegen den Code): FaceSwap als explizite
Behalten-Zeile in §1, korrigierter OpenFang-Config-Pfad in §2, präzisierte
`select_project`-Semantik, Ein-Event-Beweis in §4, Sora-Substanz-Audit als §7 und ein
Verifikations-Abschnitt. Alle Änderungen sind mit dem User abgestimmt._

_Präzisiert 2026-08-24: Laura ist die führende Oberfläche und Produktgrenze. Der alte
VibeMind-Video-Space wird nicht als zweite UI weitergeführt, sondern als Funktionsspender
für Sora, Aufnahme und FaceSwap ausgewertet. Bereits in Laura vorhandene Funktionen werden
nicht dupliziert. Die Übernahme erfolgt erst über Adapter und wird erst nach bewiesenem
Funktionsgleichstand stillgelegt._

## Kontext

Laura (Repo `vibemind-lab/lauras_star`) ist der frame-genaue, local-first KI-Videoeditor:
FastAPI-Backend auf `127.0.0.1:8765`, eigener MCP-Server (`services/mcp`, 28 Tools inkl.
`build_narrated_reel`), Chatterbox-TTS-Sidecar (`services/tts-sidecar`, Port 8898) und der
neue Narrated-Reel-Endpoint: Beat-Liste → Collage-Timeline mit Clone-Voice, Karaoke-Captions
und Render in einem Job. Der VibeMind-`video`-Space existiert bereits (Python-Backend-Agent
auf `events:tasks:video` + `brain-video`-Eintrag in der Registry), führt aber das alte
vibevideo-Stack (Team-Pipeline, Demo-Builder, eigenes Chatterbox) bzw. db_*-Platzhalter aus.

## Ziel

Der `video`-Space fährt Laura. Sprache/Chat („Mach ein Produktvideo aus …") → Brain-Intent →
`video.*`-Event → Laura-Tool. Fertige Videos landen automatisch als saubere Rowboat-Notizen
mit Summary und Metadaten. Die Laura-UI erscheint als Space-Tab in der VibeMind-Shell.

## Entscheidungen (bindend)

### 1. Alte Pipe: Ersetzen mit gezieltem Behalten

| Alt-Tool | Entscheidung |
|---|---|
| `team_run_step`, `team_pipeline_status` | **ersetzen** durch Laura-Production (deprecaten, Events umziehen) |
| `demo_analyze`, `demo_build` | **ersetzen** durch `video.reel` (Narrated-Reel kann das besser) |
| `voice_clone`, `voice_tts` | **umbiegen** auf den tts-sidecar (EINE Chatterbox-Instanz, ein GPU-Lock; altes In-Process-Chatterbox stilllegen) |
| `lipsync_run`, `lipsync_analyze` (MuseTalk) | **Backend übernehmen, UI nicht duplizieren.** Laura besitzt bereits `LipsyncPanel`, API, Job-/Idempotenzlogik, Consent-/Lizenz-Gates und einen austauschbaren VibeVideo-Sidecar. MuseTalk wird dort als Runtime hinter Lauras bestehendem Vertrag geführt. |
| **Live-Aufnahme + FaceSwap** (`video-ui` und `vibevideo_deepfake/faceswap/`) | **nach Laura übernehmen.** Bestehende Optionen bleiben erhalten: eyeTerm-Rohstream, Live-Vorschau ohne Swap, InsightFace-`inswapper` (~11 fps), `region-math` (~18 fps), Zielperson, Regionsprofil, Swap-Schalter und Start/Stop. Die Aufzeichnung bleibt unveränderlich der Rohstream; FaceSwap erzeugt nach Stop einen abgeleiteten Batch-Job. ⚠️ Beim Stilllegen des In-Process-Chatterbox **`voice/.venv312` NICHT abräumen**: dort liegen insightface + onnxruntime-gpu, der Live-Server läuft darin, und OpenFang nutzt dasselbe venv als `[python] interpreter` (`~/.openfang/config.toml:79`). |
| `vision_generate` (Sora) | **behalten, aber an der Naht auftrennen** — Substanz-Audit ist erbracht (siehe §7): Generator-Hälfte bleibt, Build-Hälfte weicht Laura. |
| `scan_video_outputs`, `import_videos`, `video_status` | **behalten und erweitern** (Filing + Health inkl. Laura/Sidecar) |
| `publish_videos_to_rowboat` | **behalten und auf das neue Template umbauen** (siehe 3.) |

### 2. Laura-Anbindung: MCP-Scope statt neuem Tool-Wrapper

OpenFang bekommt einen MCP-Server-Eintrag **`laura`** (stdio:
`uv run --directory <Laura>/services/mcp laura-mcp`, Env `LAURA_TOKEN`) — analog `vibemind-db`.
Damit stehen alle 28 Laura-Tools (inkl. `build_narrated_reel`, `import_media`, `job_status`,
`get_export`, `laura_api`) ohne eigenen Adapter zur Verfügung.

> **Korrektur (verifiziert): der Eintrag muss in `~/.openfang/config.toml`.**
> Der Daemon löst seine Config ausschließlich als `home_dir/config.toml` auf — Beleg in der
> Rust-Quelle: `channel_bridge.rs:1814` (`state.kernel.config.home_dir.join("config.toml")`)
> sowie `routes.rs:2598` und `routes.rs:2696`. Gegenprobe im Dateisystem: der bestehende
> `vibemind-db`-Eintrag steht real in `~/.openfang/config.toml` (Z. 7–14), während
> `vibemind-os/openfang/openfang.vibemind.toml` die **versionierte Vorlage** ist. Nur ins
> Repo-TOML geschrieben, erreicht `laura` den Daemon nie. Also **beide** pflegen: Vorlage im
> Repo (reproduzierbar) **und** `~/.openfang/config.toml` (wirksam).
>
> `LAURA_TOKEN` gehört dabei als **Name** in `env = ["LAURA_TOKEN"]` — der Schlüssel führt nur
> Variablennamen, den Wert zieht der Daemon aus seiner Prozessumgebung bzw.
> `~/.openfang/secrets.env`. Config-Änderungen wirken erst nach Daemon-Neustart.
Der Python-`VideoBackendAgent` (Redis-Lane) behält nur die Behalten-Tools aus 1.; neue
Events laufen über die Registry/OpenFang-Lane.

**Projekt anlegen/wechseln per Toolcall:** Ja. Anlegen geht heute in einem Call
(`POST /projects` braucht seit dem Narrated-Reel-Arc nur `{"name"}`; via `laura_api`-Tool).
Laura ist stateless — „wechseln" heißt: der Space-Agent hält `current_video_project` im
Kontext (`default_context`) und reicht die `project_id` in jeden Call. Dafür bekommt der
Laura-MCP zwei dedizierte Tools `create_project` / `select_project` und die Registry die Events
`video.project_create` / `video.project_switch`.

**Semantik von `select_project` (präzisiert):** Das Tool **löst `name` → `project_id` auf**
(via `list_projects`) und **gibt die `project_id` zurück**; gespeichert wird sie ausschließlich
im Agenten-Kontext (`current_video_project` in `default_context`). In Laura entsteht dabei
**kein** State — sonst wird aus einer Kontext-Operation versehentlich Server-State und die
Stateless-Eigenschaft ist hin. Mehrdeutiger oder unbekannter Name ⇒ `ok:false` mit Klartext
(D1-konform), nicht stillschweigend das erstbeste Projekt.

### 3. Rowboat-Publish mit Template (Summary + Metadaten)

Neues Notiz-Template in `spaces/video/tools/video_note_template.py` (ersetzt
`_build_video_note`), damit jedes Video **immer gleich** einsortiert wird:

```markdown
# {title}

## Summary
{summary}            ← bei Narrated Reels: die Beat-Zeilen (Narrationstext) — die beste
                       Zusammenfassung existiert schon; sonst 2-3 Sätze aus Transkript/VLM.

## Metadaten
| Feld | Wert |
|---|---|
| Space/Produkt | {product}        ← z. B. rowboat.space, Ideas.Space |
| Dauer | {duration_s} s |
| Erstellt | {created} |
| Quelle | Laura: project {project_id} / timeline {timeline_id} / export {export_id} |
| Stimme | {voice_backend} ({voice_ref}) |
| Datei | {file_path_oder_link} |

Tags: [video, {product}, {pipeline}]   node_type: video
```

`publish_videos_to_rowboat` nutzt das Template; Laura-Exporte werden nach Render-Erfolg
in die `VideoRepository` eingetragen (neues kleines Tool `register_laura_export`), damit
der bestehende Publish-Fluss (Mongo → Rowboat-Source) sie mitnimmt.

### 4. Event-Mapping + Brain („wie unser Chat")

`config/space_agent_registry.yml`, Sektion `video`, wird real verdrahtet
(`mcp_servers: [laura, vibemind-db]`), danach `scripts/sync_openfang_agents.py`:

```yaml
video.status:          { tool: video_status,        required_params: [] }
video.project_create:  { tool: create_project,      required_params: [name] }
video.project_switch:  { tool: select_project,      required_params: [name] }
video.import:          { tool: import_media,        required_params: [source] }
video.reel:            { tool: build_narrated_reel, required_params: [beats] }
video.job_status:      { tool: job_status,          required_params: [job_id] }
video.export_get:      { tool: get_export,          required_params: [export_id] }
video.publish:         { tool: publish_videos_to_rowboat, required_params: [] }
video.generate_clips:  { tool: sora_generate_clips, required_params: [prompts] }  # Sora-Generator, s. §7
video.vision:          { tool: vision_generate,     required_params: [] }         # legacy: das eine Fixvideo
video.lipsync:         { tool: lipsync_run,         required_params: [person] }
```

**Reihenfolge der Verdrahtung — ein Event zuerst, dann der Rest.** Das Zwei-Lane-Routing
(Redis-`VideoBackendAgent` behält die Behalten-Tools, neue Events laufen über die
Registry/OpenFang-Lane) ist das größte Integrationsrisiko dieser Arbeit: zwei Zustellwege,
zwei Tool-Registries, ein Event-Namensraum. Deshalb wird **`video.status` als erstes Event
end-to-end bewiesen** (Chat/Sprache → Brain-Intent → Lane → Tool → Antwort), und erst nach
diesem Beweis werden die übrigen Events verdrahtet. Komponenten-grün zählt hier nicht —
der Beweis läuft über `multihop_execute`, nicht gegen den Service direkt.

Deutsche Aliasse im PARAM_MAPPING-Stil (`datei`→source, `projekt`→name, `text`→beats-Hilfe).
**Brain:** für jedes Event 3–5 Intent-Trainingsbeispiele über `vibemind_brain_train`
(„importier das Video aus …", „bau ein Produktvideo über X", „wie weit ist der Render?",
„veröffentliche die Videos in Rowboat"). Beat-Planung v1: Beats kommen aus dem Chat/vom
Aufrufer; ein Planungs-Agent (Material sichten → Fenster frame-index-verifizieren →
Zeilen texten) ist ein eigener Folge-Arc.

### 5. Stack/Launcher

`laura-backend` (8765; Env `LAURA_WORKSPACE`, `LAURA_TOKEN`, `LAURA_VOICEOVER_URL`) und
`tts-sidecar` (8898; **`HF_HUB_OFFLINE=1`**, `CHATTERBOX_VOICE_REF`) werden als verwaltete
Prozesse in den VibeMind-Launcher aufgenommen (Preset „video"), `video_status` prüft beide
Healthz. Secrets bleiben in `.env`-Dateien, nie in der Registry.

### 6. UI und Produktgrenze: Laura profitiert vom Alt-Space

Laura bleibt die einzige Video-Produktoberfläche. Der VibeMind-`video`-Space lädt den echten
Laura-Renderer als eingebettete Vollansicht; er baut weder einen zweiten Beat-Editor noch
eine zweite Job-/Export-Ansicht. Dafür erhält Laura einen expliziten Embed-Modus, der seine
bestehende typisierte Preload-Bridge und Local-API-Verbindung behält. VibeMind besitzt nur
Lifecycle, Navigation und die Space-Grenze.

Die alte `voice/electron-app/video-ui` bleibt während der Migration als Referenz und
Gegenprobe erreichbar, ist aber kein Ziel-Frontend. Ihre Funktionen werden einzeln an
Lauras Verträge angeschlossen:

| Fähigkeit im Alt-Space | Ziel in Laura | Integrationsnaht | Ablöse-Gate |
|---|---|---|---|
| Sora: „Full Pipeline“ / „Nur Sora-Szenen“ | neuer Generator im vorhandenen Laura-Generate-Flow | `sora_generate_clips` liefert Clips in den Media-Root; Laura importiert und baut Timeline/Voice/Captions | zwei kurze echte Clips erzeugt, importiert und in Laura gerendert; Kostenparameter explizit |
| Lipsync-Wizard | vorhandenes `LipsyncPanel` | bestehende Laura-Lipsync-API und VibeVideo/MuseTalk-Sidecar | Consent/Lizenz, Idempotenz, Jobstatus und Qualitätsfehler über Laura-UI bewiesen |
| Live Capture | neues Laura-Capture-Panel | schmaler Capture-Adapter zu eyeTerm und Record-Start/Stop | Rohaufnahme kann in Laura gestartet, gestoppt, importiert und abgespielt werden |
| FaceSwap-Livevorschau | Capture-Panel-Modus | Adapter zu `live_server.py`, inklusive `inswapper` und `region-math` | beide Modi liefern sichtbare Frames; Ausfall wird klar gemeldet und blockiert Rohaufnahme nicht |
| FaceSwap-Aufnahme | abgeleiteter Laura-Job/Asset | Rohaufnahme bleibt Quelle; Stop stößt optional `batch.py` an | Original bleibt unverändert, Swap-Ausgabe ist eigenes Asset mit Provenienz, Consent und Kennzeichnung |
| Status/Output-Scan/Publish | Laura-Jobs, Exporte und Rowboat-Publish | vorhandene Space-Tools bleiben Orchestrierungsadapter | kein Erfolg ohne echten Laura-Job/Export; Rowboat-Metadaten vollständig |

Reihenfolge: zuerst Laura embed-fähig machen, dann Sora, Capture/FaceSwap und zuletzt die
Alt-UI entfernen. Jede Fähigkeit wird in Laura sichtbar und testbar, bevor ihr alter
Bedienpfad entfällt. Das verhindert einen Big-Bang und zugleich dauerhafte Doppelpflege.

### 7. Sora: Substanz-Audit erbracht — Generator behalten, Build-Hälfte an Laura

Der Audit, den die erste Fassung noch vertagt hatte, ist durchgeführt. Drei Befunde:

**Der Code ist echt, kein Stub.** `sora_vision.py` und `sora_backgrounds.py` rufen die reale
OpenAI-Video-API auf (`client.videos.create` / `.retrieve` / `.download_content`) inklusive
Polling und Download. Das SDK im `venv312` ist mit `openai 2.30.0` aktuell und hat
`client.videos` — technisch heute lauffähig.

**Er hat hier aber nie etwas produziert.** Ein `vision/`-Ausgabeverzeichnis existiert
überhaupt nicht. Es gibt also keinen Beleg für einen erfolgreichen Durchlauf — nur dafür,
dass die Kette plausibel gebaut ist. Das ist ausdrücklich **kein** „läuft".

**Es ist keine Pipe, sondern ein eingefrorenes Einzelvideo.** `SCENES` ist eine hartkodierte
Konstante: feste Prompts, fester Felix/Rachel-Dialog, feste Szenenlängen. `video.vision`
kann damit ausschließlich exakt dieses eine VibeMind-Vision-Video neu erzeugen.

**Entscheidung: an der natürlichen Naht auftrennen.** `sora_vision.py` macht heute zwei Jobs
— erzeugen (`generate_sora`) und schneiden (`build_video`, `combine_dialog`, TTS-Mix). Die
Schnitt-Hälfte ist genau das, was Laura besser kann und was §1 ohnehin ersetzt. Die
Generator-Hälfte ist einzigartig: **Laura hat keinerlei Videogenerierung** — sein
`tools_vision.py` ist `get_frame`/`get_contact_sheet`, also Frames aus vorhandenem Material
lesen, nicht erzeugen. Sora ist die einzige generative Quelle im ganzen Stack.

Die Produktvision-Pipe wird damit: **Prompts → Sora-Clips → `import_media` → `build_narrated_reel`
→ Render.** Sora liefert das B-Roll, Laura macht Schnitt, Voice und Captions. Neues Tool
`sora_generate_clips` (Prompts + Modell + Dauer → Clips in den Media-Root), Event
`video.generate_clips`. Der Chatterbox-Teil in `sora_vision.py` zieht dabei auf den
TTS-Sidecar um, konsistent mit §1. `video.vision` bleibt als Legacy-Event für das eine
Fixvideo erhalten. **Kostenhinweis:** `sora-2-pro` ist der Default und kostet echtes Geld
pro Clip — der Generator braucht ein explizites Modell-/Dauer-Argument statt stiller Defaults.

## Verifikation (gegen den Code geprüft, 2026-08-22)

Diese Spec ruht auf nachgeprüften Fakten, nicht auf Annahmen:

| Behauptung | Befund |
|---|---|
| Laura-Stand mit `build_narrated_reel` | `origin/main` = **`909a43d`** (Merge PR #16 `feat/generate-ui`) — Pin-Ziel fürs Submodul |
| 28 MCP-Tools | bestätigt auf `main`: 4 analysis, 4 editorial, 5 export, 1 jobs, 4 media, 7 production, 1 raw, 2 vision |
| Referenzierte Tools existieren | `build_narrated_reel`, `import_media`, `job_status`, `get_export`, `laura_api` — alle vorhanden |
| `create_project`/`select_project` | existieren **nicht** → korrekt als neu zu bauen spezifiziert |
| MCP-Entry-Point | `laura-mcp = "laura_mcp.server:main"` vorhanden |
| TTS-Sidecar-Port 8898 | `DEFAULT_VOICEOVER_URL` in `voiceover_backend.py` |
| `POST /projects` | `services/local-api/src/laura/api/projects.py:96` |
| Registry-`video`-Sektion | tatsächlich noch `db_*`-Platzhalter |
| OpenFang-Config-Pfad | `home_dir/config.toml` (`channel_bridge.rs:1814`, `routes.rs:2598/2696`) |

**Klon-Voraussetzung:** `gh` hat beide Konten im Keyring, aktiv ist aber `Flissel` —
`git fetch` gegen `Vibemind-LAB/Lauras_star` scheitert dann mit „could not read Password".
Vor `git submodule add` also `gh auth switch --user Vibemind-LAB` (Token hat `repo`-Scope).

## Nicht-Ziele

OpenFang-Treiber-Code (eigener Arc; der frühere `claude-codexsub`-Claim ist seit 2026-08-22
erledigt, PR `Flissel/openfang#21`), Nachbau der Laura-Oberfläche in VibeMind,
Auto-Beat-Planungs-Agent, Deploy/Gitlink-Bump aus dieser Arbeit.

## Fehlerfälle

Laura/Sidecar down → `video_status` meldet es, Events antworten mit klarer Meldung statt
Timeout (Healthz-Vorab-Check im Agenten-Hint). Render-Fehler → Laura räumt selbst auf
(Checkpoint-Rollback, seit Narrated-Reel-Arc); der Space meldet den Klartext-Fehler.
Publish ohne Mongo → bestehender Fallback des Alt-Tools bleibt.

## Tests

Registry-Sync erzeugt `brain-video/agent.toml` mit `laura`-Scope; Template-Unit-Test
(Summary aus Beats, Metadaten vollständig); `register_laura_export` legt VideoRepository-
Zeile mit allen Template-Feldern an; Event-Roundtrip-Test `video.reel` gegen gemocktes
Laura; Launcher-Preset startet/prüft beide Prozesse.

**Erstes Gate (vor allem anderen):** `video.status` end-to-end über `multihop_execute` —
beweist beide Lanes, bevor neun weitere Events verdrahtet werden.

**FaceSwap-Regression (nach dem Chatterbox-Rückbau, nicht verhandelbar):** `voice/.venv312`
importiert weiterhin `insightface` + `onnxruntime`, der Swap-Stream auf `:8098` liefert
Frames, und OpenFang startet mit seinem `[python] interpreter`. Der Rückbau gilt erst als
sauber, wenn diese drei grün sind — sonst ist der Aufnahme-Pfad still gestorben.

**Capture-Invariante:** Start/Stop schreibt immer zunächst die unveränderte eyeTerm-
Rohaufnahme. Ein ausgewählter FaceSwap-Modus erzeugt ein separates abgeleitetes Asset und
überschreibt niemals die Quelle. Automatisierte Tests prüfen Jobverkettung und Provenienz;
die sichtbare Live-Vorschau beider Modi wird als manuelles GPU-Gate protokolliert.

**UI-Ablöse-Gate:** VibeMind öffnet den echten Laura-Renderer im `video`-Space; Projekt,
Timeline, Jobs und Exporte funktionieren über Lauras bestehende Bridge. Für Sora, Lipsync,
Rohaufnahme und beide FaceSwap-Modi existiert je ein bestandener Laura-UI-Pfad. Erst dann
darf `voice/electron-app/video-ui` aus Navigation und Build entfernt werden.

**Sora:** `sora_generate_clips` erzeugt aus zwei Prompts echte Clips im Media-Root (der
erste belegte Durchlauf überhaupt, s. §7), die anschließend per `import_media` in Laura
landen. Kostenbewusst: kurze Dauer, `sora-2` statt `-pro` für den Beweis.

**Live-Gate (Abschluss):** ein Reel per Sprache/Chat aus VibeMind heraus, Notiz erscheint in
Rowboat mit Summary + Metadaten.
