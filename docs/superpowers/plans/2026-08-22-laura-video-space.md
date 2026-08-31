# Laura als VibeMind Video-Space — Implementierungsplan (Teil 1: Fundament + erstes Gate)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Laura ist aus VibeMind heraus erreichbar, und `video.status` ist als erstes Event end-to-end über `multihop_execute` bewiesen.

**Architecture:** Laura kommt als Git-Submodul unter `spaces/video/laura` (gepinnt auf `origin/main` `909a43d`). OpenFang bekommt einen stdio-MCP-Server-Eintrag `laura`, wodurch alle 28 Laura-Tools ohne eigenen Adapter verfügbar werden. Die Registry-Sektion `video` wird von `db_*`-Platzhaltern auf echte Tools umgestellt, und `video_status` lernt, Laura und den TTS-Sidecar per `/healthz` zu prüfen. Bewusst **ein** Event zuerst: das Zwei-Lane-Routing (Redis-`VideoBackendAgent` neben der OpenFang-Lane) ist das größte Risiko dieser Arbeit.

**Tech Stack:** Python 3.11, pytest, PyYAML, Git-Submodule, OpenFang (Rust-Daemon, TOML-Config), Laura (FastAPI :8765 + `laura-mcp` stdio via `uv`), Chatterbox-TTS-Sidecar (:8898).

**Spec:** `docs/superpowers/specs/2026-08-22-laura-video-space-design.md` (Commit `d99de9a`)

## Global Constraints

- **Python 3.11**, Tests mit `pytest`. Kein `print` in committed Code — der projektlokale `logger` in `video_tools.py` ist der Weg.
- **Conventional Commits.** Gearbeitet wird im Submodul `vibemind-os` (aktuell Branch `feat/mcp-tool-hub`), nicht im äußeren Repo.
- **Kein Deploy, kein Stack-Deploy, kein Outer-Gitlink-Bump** aus dieser Arbeit (Spec, Nicht-Ziele).
- **`voice/.venv312` NICHT anfassen.** Dort liegen insightface + onnxruntime-gpu (FaceSwap-Aufnahme-Pfad), und OpenFang nutzt es als `[python] interpreter` (`~/.openfang/config.toml:79`).
- **Secrets nie in die Registry.** In OpenFang-Configs stehen nur Variablen*namen* (`env = ["LAURA_TOKEN"]`); Werte in `~/.openfang/secrets.env`.
- **OpenFang-Config gibt es zweimal:** `openfang/openfang.vibemind.toml` ist die versionierte Vorlage, wirksam ist `~/.openfang/config.toml`. Beide pflegen, sonst wirkt nichts.
- **Echte Signale.** Ein Event gilt erst als bewiesen, wenn es durch `multihop_execute` gelaufen ist — nicht, wenn eine Komponente isoliert grün ist.
- Vor jedem Commit: nur die eigenen Dateien stagen. Das Repo trägt echte fremde uncommittete Arbeit.

---

## File Structure

| Datei | Verantwortung |
|---|---|
| `.gitmodules` (modify) | Submodul-Eintrag `spaces/video/laura` |
| `spaces/video/laura/` (new, submodule) | Laura, gepinnt auf `909a43d` |
| `openfang/openfang.vibemind.toml` (modify) | versionierte Vorlage des `laura`-MCP-Eintrags |
| `~/.openfang/config.toml` (modify, außerhalb des Repos) | der wirksame `laura`-MCP-Eintrag |
| `spaces/video/tools/video_tools.py` (modify) | `_probe()` + erweitertes `video_status()` |
| `spaces/video/tests/test_laura_wiring.py` (new) | Submodul-Pin + MCP-Entry-Point + TOML-Vorlage |
| `spaces/video/tests/test_video_status.py` (new) | `video_status`-Verhalten bei up/down |
| `config/space_agent_registry.yml` (modify) | `video`-Sektion: `mcp_servers` + `video.status` |
| `brain/the_brain/configs/agents/brain-video.yaml` (new) | Event-Claim `video.status` → `brain-video` |
| `docs/operations/2026-08-22-video-status-live-proof.md` (new) | Evidenz des E2E-Gates |

---

### Task 1: Laura als Submodul einhängen

**Files:**
- Modify: `.gitmodules`
- Create: `spaces/video/laura` (Submodul)
- Test: `spaces/video/tests/test_laura_wiring.py`

**Interfaces:**
- Consumes: nichts (erste Task)
- Produces: Pfad `spaces/video/laura` mit `services/mcp/pyproject.toml` (Entry-Point `laura-mcp`), auf den Task 2 seinen MCP-Command zeigt.

- [ ] **Step 1: Auf das richtige GitHub-Konto wechseln**

`gh` hat zwei Konten im Keyring; aktiv ist `Flissel`, aber das Repo gehört `Vibemind-LAB`. Ohne den Wechsel scheitert der Klon mit „could not read Password".

```bash
gh auth switch --user Vibemind-LAB
gh auth status
```

Erwartet: `Active account: true` unter `Vibemind-LAB`.

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

Erstelle `spaces/video/tests/test_laura_wiring.py`:

```python
"""Laura-Anbindung: Submodul-Pin und MCP-Entry-Point.

Billige Struktur-Tests, die Drift fangen: wandert der Pin oder verschwindet
der Entry-Point, laeuft der MCP-Server nicht mehr an und die 28 Tools sind weg.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LAURA_DIR = REPO_ROOT / "spaces" / "video" / "laura"


def test_gitmodules_declares_laura():
    text = (REPO_ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert 'path = spaces/video/laura' in text
    assert "Lauras_star" in text


def test_laura_mcp_entrypoint_declared():
    pyproject = LAURA_DIR / "services" / "mcp" / "pyproject.toml"
    assert pyproject.exists(), f"Laura-Submodul nicht ausgecheckt: {pyproject}"
    text = pyproject.read_text(encoding="utf-8")
    assert 'laura-mcp = "laura_mcp.server:main"' in text
```

- [ ] **Step 3: Test laufen lassen — muss fehlschlagen**

Aus `vibemind-os`:

```bash
python -m pytest spaces/video/tests/test_laura_wiring.py -v
```

Erwartet: beide FAIL — `.gitmodules` kennt Laura nicht, das Verzeichnis existiert nicht.

- [ ] **Step 4: Submodul hinzufügen und auf den Pin setzen**

```bash
git submodule add https://github.com/Vibemind-LAB/Lauras_star.git spaces/video/laura
git -C spaces/video/laura fetch origin
git -C spaces/video/laura checkout 909a43d
```

- [ ] **Step 5: Pin verifizieren**

```bash
git -C spaces/video/laura rev-parse HEAD
```

Erwartet: beginnt mit `909a43d`. Falls nicht: nicht weitermachen — ein falscher Pin bedeutet, dass `build_narrated_reel` fehlt (es existiert erst seit Merge PR #16).

- [ ] **Step 6: Tests laufen lassen — müssen bestehen**

```bash
python -m pytest spaces/video/tests/test_laura_wiring.py -v
```

Erwartet: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add .gitmodules spaces/video/laura spaces/video/tests/test_laura_wiring.py
git commit -m "feat(video): add laura submodule pinned to 909a43d"
```

---

### Task 2: `laura`-MCP-Server in OpenFang eintragen

**Files:**
- Modify: `openfang/openfang.vibemind.toml`
- Modify: `~/.openfang/config.toml` (außerhalb des Repos — der wirksame Ort)
- Modify: `~/.openfang/secrets.env`
- Test: `spaces/video/tests/test_laura_wiring.py` (erweitern)

**Interfaces:**
- Consumes: Submodul-Pfad `spaces/video/laura/services/mcp` aus Task 1.
- Produces: MCP-Server-Name `laura`, auf den Task 4 in `mcp_servers: [laura, vibemind-db]` verweist.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `spaces/video/tests/test_laura_wiring.py` anhängen:

```python
def test_openfang_template_declares_laura_mcp():
    """Die versionierte Vorlage muss den laura-Eintrag tragen.

    Wirksam ist ~/.openfang/config.toml (channel_bridge.rs:1814 loest
    home_dir/config.toml auf) — die Vorlage haelt ihn reproduzierbar.
    """
    import tomllib
    toml_path = REPO_ROOT / "openfang" / "openfang.vibemind.toml"
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    servers = {s.get("name"): s for s in data.get("mcp_servers", [])}
    assert "laura" in servers, f"laura fehlt; vorhanden: {sorted(servers)}"
    laura = servers["laura"]
    assert laura["transport"]["type"] == "stdio"
    # Nur der NAME der Variable gehoert in die Config, nie der Wert
    assert laura.get("env") == ["LAURA_TOKEN"]
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

```bash
python -m pytest spaces/video/tests/test_laura_wiring.py::test_openfang_template_declares_laura_mcp -v
```

Erwartet: FAIL mit `laura fehlt; vorhanden: [...]`.

- [ ] **Step 3: Eintrag in die versionierte Vorlage schreiben**

In `openfang/openfang.vibemind.toml`, direkt nach dem bestehenden `vibemind-db`-Block:

```toml
# 2026-08-22: Laura-MCP (28 Tools, lokaler Videoeditor auf 127.0.0.1:8765).
# WIRKSAM wird der Eintrag erst in ~/.openfang/config.toml — diese Datei ist
# die versionierte Vorlage. Beide muessen uebereinstimmen.
[[mcp_servers]]
name = "laura"
env = ["LAURA_TOKEN"]

[mcp_servers.transport]
type = "stdio"
command = "uv"
args = [
    "run",
    "--directory",
    "C:/Users/User/Desktop/Vibemind_V1/vibemind-os/spaces/video/laura/services/mcp",
    "laura-mcp",
]
```

- [ ] **Step 4: Test laufen lassen — muss bestehen**

```bash
python -m pytest spaces/video/tests/test_laura_wiring.py -v
```

Erwartet: 3 passed.

- [ ] **Step 5: Denselben Eintrag in die wirksame Config schreiben**

`~/.openfang/config.toml` — denselben Block wie in Step 3 anhängen. Diese Datei ist **nicht** im Repo; ohne diesen Schritt sieht der Daemon Laura nie.

- [ ] **Step 6: Token hinterlegen**

In `~/.openfang/secrets.env` die Zeile `LAURA_TOKEN=<wert>` ergänzen. Der Wert steht in Lauras `.env` (`C:\Users\User\Desktop\Laura\.env`). **Nicht** in eine Repo-Datei schreiben.

- [ ] **Step 7: Config-Syntax verifizieren**

```bash
python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path.home().joinpath('.openfang/config.toml').read_text(encoding='utf-8')); print([s['name'] for s in d['mcp_servers']])"
```

Erwartet: `['vibemind-db', 'laura']`. Ein TOML-Parsefehler hier legt den Daemon beim Start lahm — deshalb vor dem Neustart prüfen.

- [ ] **Step 8: Commit**

```bash
git add openfang/openfang.vibemind.toml spaces/video/tests/test_laura_wiring.py
git commit -m "feat(openfang): register laura mcp server (template + runtime)"
```

---

### Task 3: `video_status` prüft Laura und den TTS-Sidecar

**Files:**
- Modify: `spaces/video/tools/video_tools.py:135-152` (`video_status`)
- Test: `spaces/video/tests/test_video_status.py`

**Interfaces:**
- Consumes: nichts aus Task 1/2 zur Laufzeit (reines HTTP).
- Produces: `video_status() -> dict` mit den Schlüsseln `laura`, `voiceover`, `faceswap_installed` — Task 4 bindet `video.status` genau auf diese Funktion, Task 6 beweist sie end-to-end.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Erstelle `spaces/video/tests/test_video_status.py`:

```python
"""video_status meldet Laura + Sidecar ehrlich — auch wenn sie tot sind.

Ein toter Dienst ist ein BEFUND, kein Absturz und kein Timeout: die Spec
verlangt eine klare Meldung statt eines haengenden Events.
"""
import pytest

from spaces.video.tools import video_tools


class _FakeResponse:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_reports_both_services_up(monkeypatch):
    monkeypatch.setattr(video_tools, "urlopen", lambda url, timeout=2.0: _FakeResponse(200))
    result = video_tools.video_status()
    assert result["success"] is True
    assert result["laura"]["ok"] is True
    assert result["voiceover"]["ok"] is True


def test_down_service_is_a_finding_not_an_exception(monkeypatch):
    def _boom(url, timeout=2.0):
        raise OSError("connection refused")
    monkeypatch.setattr(video_tools, "urlopen", _boom)
    result = video_tools.video_status()
    assert result["success"] is True          # das Tool selbst funktioniert
    assert result["laura"]["ok"] is False     # der Dienst nicht
    assert "connection refused" in result["laura"]["error"]


def test_faceswap_is_reported(monkeypatch):
    """FaceSwap ist der Aufnahme-Pfad und muss sichtbar bleiben."""
    monkeypatch.setattr(video_tools, "urlopen", lambda url, timeout=2.0: _FakeResponse(200))
    assert "faceswap_installed" in video_tools.video_status()
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Aus `vibemind-os`:

```bash
python -m pytest spaces/video/tests/test_video_status.py -v
```

Erwartet: FAIL — `video_tools` hat kein Attribut `urlopen`, und die Schlüssel fehlen.

- [ ] **Step 3: Implementieren**

In `spaces/video/tools/video_tools.py` oben bei den Imports ergänzen:

```python
import os
from urllib.request import urlopen
```

und direkt vor `video_status` einfügen:

```python
LAURA_URL = os.environ.get("LAURA_API_URL", "http://127.0.0.1:8765")
VOICEOVER_URL = os.environ.get("LAURA_VOICEOVER_URL", "http://127.0.0.1:8898")


def _probe(base_url: str, timeout: float = 2.0) -> Dict[str, Any]:
    """GET <base_url>/healthz. Wirft nie — ein toter Dienst ist ein Befund."""
    try:
        with urlopen(f"{base_url}/healthz", timeout=timeout) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status, "url": base_url}
    except Exception as e:
        logger.warning("healthz probe failed for %s: %s", base_url, e)
        return {"ok": False, "error": str(e), "url": base_url}
```

Dann `video_status` ersetzen:

```python
def video_status(**kwargs) -> Dict[str, Any]:
    """Status des Video-Space: Laura, TTS-Sidecar, FaceSwap, Alt-Tools."""
    faceswap_ok = (DEEPFAKE_DIR / "faceswap" / "batch.py").exists()
    laura = _probe(LAURA_URL)
    voiceover = _probe(VOICEOVER_URL)

    parts = []
    parts.append("Laura " + ("erreichbar" if laura["ok"] else "NICHT erreichbar"))
    parts.append("Sidecar " + ("erreichbar" if voiceover["ok"] else "NICHT erreichbar"))
    if faceswap_ok:
        parts.append("FaceSwap installiert")

    return {
        "success": True,
        "message": "Video-Space: " + ", ".join(parts),
        "laura": laura,
        "voiceover": voiceover,
        "faceswap_installed": faceswap_ok,
    }
```

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

```bash
python -m pytest spaces/video/tests/test_video_status.py -v
```

Erwartet: 3 passed.

- [ ] **Step 5: Gegen die echten Dienste prüfen**

Laura und Sidecar starten, dann:

```bash
python -c "from spaces.video.tools.video_tools import video_status; print(video_status()['message'])"
```

Erwartet bei laufenden Diensten: `Video-Space: Laura erreichbar, Sidecar erreichbar, FaceSwap installiert`. Bei gestoppten Diensten dieselbe Zeile mit `NICHT erreichbar` — und **ohne** Hänger.

- [ ] **Step 6: Commit**

```bash
git add spaces/video/tools/video_tools.py spaces/video/tests/test_video_status.py
git commit -m "feat(video): video_status probes laura and tts sidecar healthz"
```

---

### Task 4: Registry-Sektion `video` real verdrahten

**Files:**
- Modify: `config/space_agent_registry.yml:255-273`
- Test: `spaces/video/tests/test_video_registry.py`

**Interfaces:**
- Consumes: MCP-Server-Name `laura` (Task 2), Funktionsname `video_status` (Task 3).
- Produces: Registry-Sektion, aus der `scripts/sync_openfang_agents.py` `openfang/agents/brain-video/agent.toml` mit `[mcp_allowed] servers = ["laura", "vibemind-db"]` erzeugt.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Erstelle `spaces/video/tests/test_video_registry.py`:

```python
"""Die video-Sektion muss echte Tools binden, keine db_*-Platzhalter."""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = REPO_ROOT / "config" / "space_agent_registry.yml"


def _video_section():
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return data["spaces"]["video"]


def test_video_space_has_laura_scope():
    assert _video_section()["mcp_servers"] == ["laura", "vibemind-db"]


def test_video_status_binds_the_real_tool():
    events = _video_section()["events"]
    assert events["video.status"]["tool"] == "video_status"


def test_no_db_placeholders_left_on_wired_events():
    """db_query/db_update auf video.status war der Platzhalter-Zustand."""
    events = _video_section()["events"]
    assert not events["video.status"]["tool"].startswith("db_")
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

```bash
python -m pytest spaces/video/tests/test_video_registry.py -v
```

Erwartet: FAIL — `mcp_servers` ist `[vibemind-db]`, `video.status` ist `db_query`.

- [ ] **Step 3: Registry anpassen**

In `config/space_agent_registry.yml`, Sektion `video`: `mcp_servers` erweitern und `video.status` binden. Die übrigen Events bleiben in diesem Plan **unverändert** — sie kommen erst nach dem Gate (Task 6) dran.

```yaml
    mcp_servers: [laura, vibemind-db]
```

und in `events:`:

```yaml
      video.status:       { tool: video_status,               required_params: [] }
```

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

```bash
python -m pytest spaces/video/tests/test_video_registry.py -v
```

Erwartet: 3 passed.

- [ ] **Step 5: agent.toml synchronisieren**

```bash
python scripts/sync_openfang_agents.py --dry-run
python scripts/sync_openfang_agents.py
python scripts/sync_openfang_agents.py --check
```

Erwartet: `--dry-run` zeigt `would video -> brain-video`, der Lauf schreibt `update video -> brain-video`, `--check` endet mit `0 drift` (Exit 0).

- [ ] **Step 6: Scope im erzeugten agent.toml verifizieren**

```bash
python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('openfang/agents/brain-video/agent.toml').read_text(encoding='utf-8')); print(d['mcp_allowed']['servers'])"
```

Erwartet: `['laura', 'vibemind-db']`.

- [ ] **Step 7: Commit**

```bash
git add config/space_agent_registry.yml openfang/agents/brain-video/agent.toml spaces/video/tests/test_video_registry.py
git commit -m "feat(registry): wire video space to laura scope and video.status"
```

---

### Task 5: Event-Claim `video.status` für `brain-video`

**Files:**
- Create: `brain/the_brain/configs/agents/brain-video.yaml`
- Test: `brain/the_brain/tests/test_video_agent_claim.py`

**Interfaces:**
- Consumes: Agent-Name `brain-video` aus der Registry (Task 4).
- Produces: Auflösung `video.status` → `brain-video` über `AgentYamlRegistry`, die der Routing-Pfad in Task 6 nutzt.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Erstelle `brain/the_brain/tests/test_video_agent_claim.py`:

```python
"""brain-video beansprucht video.status — genau einmal.

AgentYamlRegistry-Invariante: pro Event genau EIN Agent. Ein doppelter
Claim ist ein Routing-Bug, der sich sonst erst zur Laufzeit zeigt.
"""
from core.agent_yaml_registry import AgentYamlRegistry


def test_video_status_resolves_to_brain_video():
    reg = AgentYamlRegistry()
    assert reg.get_event_agent("video.status") == "brain-video"


def test_registry_has_no_conflicts():
    reg = AgentYamlRegistry()
    assert reg.validate() == []
```

- [ ] **Step 2: Test laufen lassen — muss fehlschlagen**

Aus `brain/the_brain`:

```bash
python -m pytest tests/test_video_agent_claim.py -v
```

Erwartet: erster Test FAIL (`None != 'brain-video'`).

- [ ] **Step 3: Agent-YAML anlegen**

Erstelle `brain/the_brain/configs/agents/brain-video.yaml`:

```yaml
agent: brain-video
description: "Videoproduktion mit Laura: Import, Reel-Bau, Render-Status, Publish"
default_namespace: video
events:
  - video.status
notes: |
  Fundament-Stufe (Plan 2026-08-22, Teil 1): nur video.status ist beansprucht.
  Die uebrigen video.*-Events kommen erst nach dem end-to-end-Beweis dazu —
  das Zwei-Lane-Routing (Redis-VideoBackendAgent + OpenFang) wird bewusst
  an genau einem Event verifiziert, bevor es breit verdrahtet wird.
```

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

```bash
python -m pytest tests/test_video_agent_claim.py -v
```

Erwartet: 2 passed.

- [ ] **Step 5: Keine Regression in der Brain-Suite**

```bash
python -m pytest tests/ -q
```

Erwartet: Die Anzahl der Fehlschläge ist **unverändert** gegenüber dem Lauf vor dieser Task (vorher notieren). Ein neuer Fehlschlag bedeutet einen Event-Konflikt.

- [ ] **Step 6: Commit**

```bash
git add brain/the_brain/configs/agents/brain-video.yaml brain/the_brain/tests/test_video_agent_claim.py
git commit -m "feat(brain): claim video.status for brain-video agent"
```

---

### Task 6: Das Gate — `video.status` end-to-end über `multihop_execute`

**Files:**
- Create: `docs/operations/2026-08-22-video-status-live-proof.md`

**Interfaces:**
- Consumes: alles aus Task 1–5.
- Produces: die Freigabe für Plan 2 (Vollverdrahtung). Ohne diesen Beweis wird kein weiteres Event verdrahtet.

- [ ] **Step 1: Dienste starten**

Vier Dienste, jeder in einer eigenen Shell. Laura (`:8765`), aus `spaces/video/laura`:

```powershell
cd spaces\video\laura\services\local-api
uv sync
uv run laura-api
```

TTS-Sidecar (`:8898`) — läuft in Chatterbox' eigenem venv, nicht in Lauras:

```powershell
$env:HF_HUB_OFFLINE = "1"
E:\chatterbox\.venv\Scripts\python.exe `
  C:\Users\User\Desktop\Vibemind_V1\vibemind-os\spaces\video\laura\services\tts-sidecar\chatterbox_sidecar.py `
  --port 8898
```

Brain (`:5000`), aus `brain/the_brain`:

```powershell
python -m web.brain_server
```

OpenFang-Daemon (`:4200`): **muss neu gestartet werden** — die Config-Änderung aus Task 2 wirkt erst nach einem Neustart. Dabei `.env` zuerst in die Prozessumgebung laden, sonst antwortet der LLM-Pfad mit HTTP 500 (Auth). Falls der Start blockiert: eine veraltete `~/.openfang/daemon.json` verhindert ihn — Datei entfernen und erneut starten.

Erreichbarkeit einzeln prüfen, bevor es weitergeht:

```powershell
curl.exe -s -o NUL -w "laura=%{http_code}`n"   http://127.0.0.1:8765/healthz
curl.exe -s -o NUL -w "sidecar=%{http_code}`n" http://127.0.0.1:8898/healthz
curl.exe -s -o NUL -w "brain=%{http_code}`n"   http://127.0.0.1:5000/health
```

Erwartet: dreimal `200`.

- [ ] **Step 2: Prüfen, dass OpenFang Laura überhaupt sieht**

```bash
curl -s http://127.0.0.1:4200/api/mcp/servers
```

Erwartet: `laura` ist gelistet. Fehlt es, ist Step 5 aus Task 2 (`~/.openfang/config.toml`) nicht wirksam geworden — dort weitersuchen, nicht im Repo-TOML.

- [ ] **Step 3: Das Event durch den echten Pfad schicken**

```bash
curl -s -X POST http://127.0.0.1:5000/api/multihop/execute \
  -H "Content-Type: application/json" \
  -d '{"query": "wie ist der status vom video space?"}'
```

- [ ] **Step 4: Die Antwort gegen die Wahrheit prüfen**

Die Antwort muss die echten Health-Werte tragen (`Laura erreichbar`, `Sidecar erreichbar`). Gegenprobe, die den Beweis erst zu einem macht: **den Sidecar stoppen und erneut ausführen** — die Antwort muss auf `Sidecar NICHT erreichbar` umschlagen. Bleibt sie gleich, kommt sie nicht aus dem echten Tool, und das Gate ist **nicht** bestanden.

- [ ] **Step 5: Evidenz festhalten**

Erstelle `docs/operations/2026-08-22-video-status-live-proof.md` mit: Zeitstempel, exaktem Request, exakter Antwort für beide Läufe (Sidecar an/aus), `plan_id` und `trace_id` aus dem Envelope sowie den beteiligten Versionen (Laura-Pin `909a43d`, OpenFang-Config-Stand). Negativbefunde ehrlich aufschreiben.

- [ ] **Step 6: Commit**

```bash
git add docs/operations/2026-08-22-video-status-live-proof.md
git commit -m "docs(ops): video.status end-to-end live proof"
```

---

## Vor Task 6 zu klären (Befunde des Abschluss-Reviews)

1. **`scripts/sync_openfang_agents.py` schreibt ein Schema, das OpenFang nicht kennt.**
   Das Skript emittiert `[mcp_allowed] servers = [...]` in die generierten
   `agent.toml`-Dateien. Diesen Key gibt es im Manifest-Schema des Daemons nicht —
   `openfang-types/src/agent.rs:461` deklariert stattdessen `mcp_servers`. Die vom
   Skript erzeugten Dateien sind damit VibeMind-seitige Artefakte, die der Daemon
   schlicht ignoriert. Das ist vorbestehend (nicht durch diesen Plan verursacht).
   Der wirksame Scope muss direkt in `~/.openfang/agents/<agent>/agent.toml` unter
   `mcp_servers` gesetzt werden, oder über `PUT /api/agents/{id}/mcp_servers`.

2. **`capabilities.yaml` kennt keine Video-Capability — der Planner kann keinen
   `video.status`-Hop erzeugen.** `brain/the_brain/data/capabilities.yaml` enthält
   66 Einträge (43 `supabase:`, 10 `openfang:`, 13 `null`) und keinen einzigen für
   Video. Der Multihop-Planner bekommt genau diese Liste als Futter — ohne einen
   Video-Eintrag kann aktuell kein Plan das Event tatsächlich emittieren, egal wie
   gut Laura/Sidecar verdrahtet sind. Zwei Auswege: entweder einen
   Capability-Eintrag ergänzen, oder das Event über die Voice-/Prefix-Lane
   (`BrainOpenFangBridge`) beweisen, die den Space per Prefix-Bindung erreicht,
   ohne eine Brain-Capability zu brauchen.

3. **Task 6 Step 3 schickt das falsche Payload-Feld.** Der Plan postet
   `{"query": ...}`, aber `brain/the_brain/web/routers/introspection.py:2445`
   liest nur `plan`, `intent` und `message`. So wie der Schritt aktuell
   formuliert ist, käme eine leere Intent an. Das Payload muss vor dem nächsten
   Versuch korrigiert werden (z. B. auf `message`).

---

## Nach diesem Plan (Folge-Pläne, je eigenständig testbar)

Erst nach bestandenem Gate aus Task 6:

- **Teil 2 — Projekt-Tools + Vollverdrahtung.** `create_project` / `select_project` im Laura-MCP (inkl. `name` → `project_id`-Auflösung, `ok:false` bei mehrdeutig), dann die restlichen Events aus §4 der Spec plus 3–5 Brain-Intent-Beispiele je Event.
- **Teil 3 — Rowboat-Publish.** `video_note_template.py`, `register_laura_export`, Umbau von `publish_videos_to_rowboat`.
- **Teil 4 — Alt-Pipe-Rückbau.** `vibevideo` raus, Chatterbox auf den Sidecar umbiegen — mit der FaceSwap-Regression aus der Spec als Abnahmebedingung (`venv312` importiert insightface/onnxruntime, `:8098` liefert Frames, OpenFang startet).
- **Teil 5 — Sora-Naht.** `sora_generate_clips` (Prompts → Clips in den Media-Root), Build-Hälfte an Laura abgeben, `video.vision` als Legacy behalten.
- **Teil 6 — Launcher-Preset + UI-Embed.** `laura-backend` + `tts-sidecar` als verwaltete Prozesse, Laura-UI als Webview-Tab.
