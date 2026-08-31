# Live-Beweis: `video.status` erreicht Laura — zwei Lanes, eigener Einstiegspunkt (R14)

**Datum/Zeit:** 2026-08-22, 19:16–19:22 Uhr (MESZ, +02:00)
**Autor:** Claude Code (Task 6, `laura-video-space`-Plan)
**Methode:** überstimmt durch Ruling R14 — nicht `POST /api/multihop/execute`, sondern jede
Lane an ihrem eigenen Einstiegspunkt geprüft (siehe Begründung unten).

## Warum die Methode geändert wurde (R14)

Der Plan wollte `video.status` durch `POST /api/multihop/execute` beweisen. Das ist
unmöglich: `brain/the_brain/data/capabilities.yaml` enthält keinen Video-Eintrag —
verifiziert mit `grep -in "video" brain/the_brain/data/capabilities.yaml` → **0 Treffer**
(Datei hat 1585 Zeilen, ~188 Top-Level-Keys/Capability-Einträge). Der Multihop-Planner
bekommt exakt diese Liste als Werkzeugkasten; ohne `video.*`-Eintrag kann kein Plan je
einen `video.status`-Hop erzeugen. `capabilities.yaml` zu ändern hätte eine von einer
anderen Session geclaimte Datei angefasst und einen Config-Version-Bump gebraucht — beides
außerhalb des Scopes dieser Aufgabe. Zusätzlich: freies RAM lag bei ~3,4 GB — Brain-Server
+ 2-GB-Chatterbox-Sidecar zu starten wäre nicht zu rechtfertigen gewesen.

Also: jede Lane an ihrem eigenen Einstiegspunkt.

## Versionen im Spiel

| Komponente | Pin/HEAD | Bemerkung |
|---|---|---|
| `vibemind-os` HEAD | `d3a8f3f343ff280d1adfe6af101cf122e5a8fc4f` | Commit-Zeit 2026-08-22 14:44:06 +0200 |
| `spaces/video/laura` (Laura-Submodul) | `909a43d499ffe00f4fd3d779127da45debf64f0c` | Branch `main`; im Index gepinnt = tatsächlicher Checkout (übereinstimmend) |
| `openfang` (Submodul) | Checkout: `22bd44f58c2b8cf5e0001ff59e85cfcd3d795b58` (Branch `feat/mcp-tool-hub`) | **Abweichung:** im `vibemind-os`-Index/HEAD ist als Gitlink `f6d2b382b66b6860d10e27196b6ce665bee6f389` eingetragen (`git ls-tree HEAD openfang`) — der tatsächliche Checkout ist neuer als der committete Pin. Läuft unter dem Checkout-Stand, nicht unter dem gepinnten. `git submodule status` markiert das korrekt mit `+`. |
| `openfang.exe` Version | `0.6.9` (`openfang system version`) | Binary aus `openfang/target/release/openfang.exe` |

## Ausgangszustand (vor Task-Start, empirisch geprüft)

- Laura läuft bereits auf `127.0.0.1:8765` (fremd gestartet) — **nicht neu gestartet, nicht
  gestoppt.**
- `~/.openfang/daemon.json` existierte **nicht** (`Test-Path` → `False`) — kein stale File,
  nichts zu verschieben.
- OpenFang-Daemon (`:4200`) lief nicht — musste gestartet werden.
- **Abweichung vom Briefing:** Das Briefing ging davon aus, der TTS-Sidecar (`:8898`) laufe
  nicht. Empirisch (`docker ps`) lief er tatsächlich: Container `laura-runtime-voice`
  (Image `laura-runtime-voice:local`), **Up 9 hours (healthy)**, Port-Mapping
  `0.0.0.0:8898->8898/tcp`. Ein direkter `GET http://127.0.0.1:8898/healthz` bestätigte
  `{"ok": true, "ready": true, ..., "provider": "piper", ...}`. Windows-`netstat`/
  `Get-NetTCPConnection` zeigten keinen Owner-Prozess (Docker-Portforwarding via WSL2 ist
  aus nativer Windows-Sicht unsichtbar) — daher vermutlich die Fehleinschätzung im
  Briefing. Das ändert an der Beweisführung selbst nichts (siehe Lane B unten), aber es ist
  ein Negativbefund gegenüber der Aufgabenstellung und wird hier festgehalten statt
  stillschweigend "passend gemacht".

## Lane A — OpenFang/MCP

### Schritt 1: stale `daemon.json` prüfen

```powershell
Test-Path "$env:USERPROFILE\.openfang\daemon.json"
```

Ergebnis: `False`. Datei existierte nicht — nichts zu verschieben, kein Startup-Blocker.
(`daemon.json` erschien danach als **eigenes** Artefakt des von mir gestarteten Daemons,
Zeitstempel `19:16`, kongruent mit dem Prozessstart.)

### Schritt 2: Daemon starten mit `.env` im Prozess-Environment

`.env` (Repo-Root, 15 aktive Key-Zeilen) wurde in dieselbe PowerShell-Prozessumgebung
geladen, in der `openfang.exe start` dann direkt aufgerufen wurde (beides im selben
Aufruf, da PowerShell-Tool-Aufrufe keine Umgebung über Aufrufe hinweg teilen):

```powershell
Get-Content .env | ForEach-Object { ... [System.Environment]::SetEnvironmentVariable($name, $val, "Process") }
Start-Process -FilePath "openfang\target\release\openfang.exe" -ArgumentList "start" `
  -WorkingDirectory <repo> -RedirectStandardOutput openfang_stdout.log `
  -RedirectStandardError openfang_stderr.log -PassThru -WindowStyle Hidden
```

Ergebnis: PID `40556`, gestartet `19:16:50`. Sanity-Check vor dem Start bestätigte
`OPENAI_API_KEY` und `OPENROUTER_API_KEY` als gesetzt (Werte nicht ausgegeben).
`LAURA_TOKEN` kommt separat aus `~/.openfang/secrets.env` (OpenFang lädt diese Datei
selbst — nicht aus dem Root-`.env`).

`GET http://127.0.0.1:4200/api/health` antwortete nach 0s mit Status `200` — Daemon war
sofort erreichbar.

**Negativbefund aus dem Boot-Log** (nicht Teil dieser Gate-Frage, aber ehrlich
festzuhalten): `openfang_stderr.log` Zeile 24:
```
2026-08-22T17:16:51.080758Z ERROR openfang_runtime::audit: Audit trail integrity check FAILED on boot: chain break at seq 8995: expected prev_hash 1589da709fb0b87080655cb544919a3e350fcb88bf0eb40bcc20991e31669129 but found b0ab0608b70627b7d4ec2137333930443ebad98152dbcc443c1a3b800878ae7a
```
Der Daemon startete trotzdem und funktionierte für diesen Test — aber die Audit-Chain ist
gebrochen. Nicht selbst untersucht/behoben (außerhalb des Scopes), aber gemeldet.

### Schritt 3: `GET /api/mcp/servers`

**Erster Aufruf** (`19:17:08`, `request_id=fe4476e6-...`), ~18 Sekunden nach Daemon-Start:

```json
{"configured":[{"name":"vibemind-db",...},{"name":"laura","env":["LAURA_TOKEN"],"transport":{"command":"uv","args":["run","--directory","C:/Users/User/Desktop/Vibemind_V1/vibemind-os/spaces/video/laura/services/mcp","laura-mcp"],"type":"stdio"}}],
 "connected":[{"connected":true,"name":"vibemind-db","tools":[...30 tools...],"tools_count":30}],
 "total_configured":2,"total_connected":1}
```

`laura` war zu diesem Zeitpunkt **konfiguriert, aber noch nicht verbunden**
(`total_connected: 1` von 2). Das Boot-Log erklärt warum: `uv run` baute beim allerersten
Start das `laura-mcp`-venv frisch (43 Pakete, u. a. `cryptography`, `mypy`, `ruff`,
`pywin32` — mehrere MB Downloads), das dauerte länger als die 18 Sekunden bis zu meinem
ersten Poll.

**Zweiter Aufruf** (`19:17:2x`, nach Abschluss des `uv`-Builds):

```json
{"total_configured":2,"total_connected":2}
server=vibemind-db connected=True tools_count=30
server=laura        connected=True tools_count=28
```

Log-Beleg (`openfang_stderr.log`):
```
Building laura-mcp @ file:///.../spaces/video/laura/services/mcp
Downloading ast-serialize / pygments / cryptography / mypy / ruff / pydantic-core / pywin32
Built laura-mcp @ file:///.../spaces/video/laura/services/mcp
Installed 43 packages in 1.06s
2026-08-22T17:17:18.667155Z  INFO serve_inner: rmcp::service: Service initialized as client peer_info=... server_info: Implementation { name: "laura", ..., version: "1.29.0", ... }
2026-08-22T17:17:18.670366Z  INFO openfang_runtime::mcp: MCP server connected server=laura tools=28
2026-08-22T17:17:18.670767Z  INFO openfang_kernel::kernel: MCP: 58 tools available from 2 server(s)
```

28 Tools von `laura`, u. a.: `mcp_laura_laura_api`, `mcp_laura_list_projects`,
`mcp_laura_import_media`, `mcp_laura_get_transcript`, `mcp_laura_get_timeline`,
`mcp_laura_edit_timeline`, `mcp_laura_render_timeline`, `mcp_laura_auto_produce`,
`mcp_laura_start_production`, `mcp_laura_propose_scenes`, `mcp_laura_approve_script`,
`mcp_laura_get_frame` — vollständige Liste (28 Namen) im Rohdump
`mcp_servers_2.json` (dieser Session, nicht ins Repo übernommen).

**Verdikt Lane A, Teil „MCP-Server":** `laura` ist erreichbar und liefert 28 Tools über
OpenFang. Der erste Poll war ein echter, aber harmloser Zeit-Race (venv-Erstbau via `uv`),
kein Fehlschlag der Verdrahtung — beim zweiten Poll war der Server sauber verbunden.

### Schritt 4: Agent-Scope für `brain-video`

`GET /api/agents` listet Agenten ohne `mcp_servers`-Detail. Namensbasierter Detail-Call
(`GET /api/agents/brain-video`) schlug mit `400 Bad Request` fehl — der Endpoint erwartet
eine UUID. ID aus der Liste entnommen (`409a7b00-89e0-49ff-8cc5-38ae7993fe68`), dann:

```
GET http://127.0.0.1:4200/api/agents/409a7b00-89e0-49ff-8cc5-38ae7993fe68
```

Relevanter Ausschnitt der Antwort:

```json
{
  "name": "brain-video",
  "mcp_servers": ["laura", "vibemind-db"],
  "mcp_servers_mode": "allowlist",
  "state": "Running",
  "ready": true
}
```

**Verdikt:** Der Daemon hat die Allowlist aus `agent.toml`
(`C:\Users\User\.openfang\agents\brain-video\agent.toml`, `mcp_servers = ["laura", "vibemind-db"]`)
tatsächlich geladen und hält sie im laufenden Agent-Record — `laura` ist Teil des
effektiven Scopes von `brain-video`, nicht nur im TOML auf der Platte.

### Lane-A-Gesamtverdikt

**Erreichbar.** `laura` ist als MCP-Server bei OpenFang konfiguriert, verbindet sich
(28 Tools, nach kurzem einmaligem `uv`-Build-Race), und `brain-video` führt `laura` in
seiner tatsächlich geladenen Allowlist. Kein Fehlschlag zu berichten für diese Lane.

## Lane B — Redis/VideoBackendAgent (ohne Redis)

`spaces/video/agents/video_agent.py:36` mappt `"video.status": "video_status"` in
`EVENT_TO_TOOL`. Bewiesen ohne Redis: `VideoBackendAgent` instanziiert (Konstruktor
verbindet nicht eager — `EventBus` wird lazy über die `.bus`-Property geladen, hier nie
angefasst), `._get_tool_name("video.status")` aufgerufen, das Ergebnis in `.tools`
nachgeschlagen (löst `_load_tools()` aus, importiert die echten Funktionen aus
`spaces/video/tools/video_tools.py`), dann die aufgelöste Funktion direkt aufgerufen —
exakt der Pfad, den `BaseBackendAgent._handle_event()` auch nimmt, nur ohne den
Redis-Event drumherum.

Skript (`video_status_probe.py`, Scratchpad dieser Session), ausgeführt mit
`voice\.venv312\Scripts\python.exe`.

### Normal-Lauf (kein `LAURA_API_URL` gesetzt → Modul-Default `http://127.0.0.1:8765`)

```json
{
  "event_type": "video.status",
  "resolved_tool_name": "video_status",
  "tool_fn_found": true,
  "LAURA_API_URL_env_at_process_start": "<unset -> module default>",
  "module_LAURA_URL_constant": "http://127.0.0.1:8765",
  "result": {
    "success": true,
    "message": "Video-Space: Laura erreichbar, Sidecar erreichbar, FaceSwap installiert",
    "laura": {"ok": true, "status": 200, "url": "http://127.0.0.1:8765"},
    "voiceover": {"ok": true, "status": 200, "url": "http://127.0.0.1:8898"},
    "faceswap_installed": true,
    "vibevideo_installed": true,
    "deepfake_installed": true,
    "available_tools": ["team", "vision", "demo", "lipsync", "voice"]
  }
}
```

`laura.ok = true` — Laura ist über den echten `EVENT_TO_TOOL`-Pfad erreichbar.
`voiceover.ok = true` — abweichend von der Aufgabenannahme läuft der Sidecar tatsächlich
(siehe Ausgangszustand oben: Docker-Container `laura-runtime-voice`, healthy). Das ist der
reale beobachtete Wert, nicht der im Briefing angenommene.

### Gegentest (separater Prozess, `LAURA_API_URL=http://127.0.0.1:8799`, Port unbelegt)

`LAURA_URL` in `video_tools.py` wird beim Modul-Import als Konstante aus der
Prozessumgebung gelesen (`LAURA_URL = os.environ.get("LAURA_API_URL", ...)`) — daher
musste die Variable **vor** dem Python-Start eines **neuen** Prozesses gesetzt werden,
nicht nachträglich:

```powershell
$env:LAURA_API_URL = "http://127.0.0.1:8799"
& voice\.venv312\Scripts\python.exe video_status_probe.py
```

```
healthz probe failed for http://127.0.0.1:8799: <urlopen error timed out>
{
  "event_type": "video.status",
  "resolved_tool_name": "video_status",
  "tool_fn_found": true,
  "LAURA_API_URL_env_at_process_start": "http://127.0.0.1:8799",
  "module_LAURA_URL_constant": "http://127.0.0.1:8799",
  "result": {
    "success": true,
    "message": "Video-Space: Laura NICHT erreichbar, Sidecar erreichbar, FaceSwap installiert",
    "laura": {"ok": false, "error": "<urlopen error timed out>", "url": "http://127.0.0.1:8799"},
    "voiceover": {"ok": true, "status": 200, "url": "http://127.0.0.1:8898"},
    ...
  }
}
```

**Die Antwort kippte** von `"Laura erreichbar"` auf `"Laura NICHT erreichbar"`, exakt am
Punkt, an dem der Port ins Leere zeigt. `laura.ok` wechselte `true → false`,
`laura.error` bekam den echten `urlopen`-Timeout-Text. `voiceover` blieb unverändert
`ok=true` (unabhängige `LAURA_VOICEOVER_URL`-Variable, korrekterweise nicht betroffen).

**Verdikt Gegentest: bestanden.** Der Wert kommt nachweislich aus einer echten Probe
(`urlopen(f"{base_url}/healthz", timeout=2.0)`), nicht aus einer festen/gecachten Antwort —
hätte sich die Meldung nicht geändert, wäre das Gate laut Vorgabe gescheitert. Sie hat sich
geändert.

### Lane-B-Gesamtverdikt

**Bestanden.** `video.status` löst über `EVENT_TO_TOOL` korrekt zu `video_status` auf, die
Funktion führt eine echte HTTP-Probe gegen Laura aus, und der Gegentest beweist, dass diese
Probe nicht fabriziert ist.

## Was dieser Beweis NICHT zeigt

Dieser Test beweist, dass **beide Lanes je für sich** funktionieren: OpenFang kann Laura
als MCP-Server ansprechen, und `VideoBackendAgent` kann `video.status` real gegen Laura
auflösen. Er beweist **nicht**, dass der Pfad **„Sprache/Chat → Brain-Intent → Event"**
funktioniert — also dass ein Nutzer per Voice oder Chat tatsächlich `video.status`
auslösen kann.

Grund: `brain/the_brain/data/capabilities.yaml` enthält keinen `video.*`-Eintrag
(verifiziert, 0 Treffer für „video" in der Datei). Der Multihop-Planner erhält exakt diese
Capability-Liste als seinen Werkzeugkasten; ohne einen `video.status`-Eintrag darin kann
kein von ihm erzeugter Plan je einen `video.*`-Hop enthalten — unabhängig davon, wie gut
Laura oder der VideoBackendAgent selbst funktionieren. Der Video-Space kann also aktuell
**nicht** über die vom Spec vorgesehene Sprach-/Chat-Route angesteuert werden; beide
bewiesenen Lanes sind nur über ihren jeweiligen direkten Einstiegspunkt erreichbar
(OpenFang-API bzw. direkter Python-Import), nicht über den End-to-End-Nutzerpfad.

**Das ist die verbleibende Lücke, bevor der Video-Space wie spezifiziert per Sprache
oder Chat angesteuert werden kann:** ein `video.*`-Capability-Eintrag muss in
`capabilities.yaml` ergänzt und ein Config-Version-Bump vorgenommen werden — beides bewusst
außerhalb des Scopes dieser Aufgabe gelassen (R14), da die Datei von einer anderen Session
geclaimt ist.

## Negativbefunde (Zusammenfassung, unbeschönigt)

1. **TTS-Sidecar lief entgegen der Aufgabenannahme bereits** (Docker-Container
   `laura-runtime-voice`, healthy, 9h uptime) — die Aufgabenstellung ging von einem
   heruntergefahrenen Sidecar aus. Ändert nichts an der Gültigkeit des Gegentests (der
   testet die Laura-URL, nicht die Sidecar-URL), ist aber eine falsche Prämisse im
   Briefing, die hier korrigiert wird.
2. **Audit-Trail-Integritätsbruch beim Daemon-Boot** (`chain break at seq 8995`) — nicht
   untersucht (außerhalb des Scopes), aber im Log sichtbar und hier gemeldet.
3. **`openfang`-Submodul-Checkout weicht vom im `vibemind-os`-Index gepinnten Gitlink ab**
   (`22bd44f...` läuft, `f6d2b382...` ist gepinnt) — vermutlich Folge paralleler
   Session-Arbeit am `openfang`-Submodul; für diesen Test irrelevant (lief unter dem
   tatsächlichen Checkout), aber als Zustand festgehalten.
4. **Erster `GET /api/mcp/servers`-Poll zeigte `laura` fälschlich als nicht verbunden** —
   reiner Zeit-Race durch den einmaligen `uv`-venv-Build beim allerersten Start dieses
   MCP-Servers auf dieser Maschine, kein struktureller Fehler. Durch einen zweiten Poll
   ~15s später aufgelöst.
5. `GET /api/agents/brain-video` (Name statt UUID) scheitert mit `400 Bad Request` — der
   Endpoint erwartet die Agent-UUID, keine Namensauflösung. Kein Blocker, aber
   dokumentationswürdig für zukünftige Aufrufer.

## Aufräumen

Der für diese Aufgabe gestartete OpenFang-Daemon (PID `40556`) wurde nach Abschluss der
Beweisführung gestoppt. Laura (`:8765`, fremd gestartet) blieb unangetastet und lief beim
Verlassen dieser Aufgabe weiter — sie war nicht meiner Verantwortung zu stoppen.
