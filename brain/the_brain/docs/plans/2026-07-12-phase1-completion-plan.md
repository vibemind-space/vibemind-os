# Phase-1-Abschluss: Live-Beweis + Coverage + Task-Klassen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die committete Phase-1-Kette (Hop-Signale → KotlinGraph-Tagebuch) live beweisen, die zwei bekannten Folgerisiken schließen (auto_mine-Hot-Path, Ground-Truth-Coverage) und Task-Klassen-Clustering als letzten Phase-1-Baustein liefern.

**Architecture:** Alles brain-seitig in `vibemind-os/brain/the_brain/` (Voice bleibt unberührt). Neuer Read-only-Endpoint macht das Tagebuch beobachtbar; die Coverage wird per Ratchet-Test eingefroren und mit 6 konkreten `truth:`-Validatoren angehoben; der Clusterer ist injection-first (kein Modell-Load in Tests) und default-OFF im Hot-Path.

**Tech Stack:** Python 3.11, pytest, FastAPI TestClient, YAML (capabilities.yaml), Qdrant/Qwen-Embedder (nur Task 4, lazy).

## Global Constraints

- Git IMMER über PowerShell (git-bash crasht — Memory `feedback_git_powershell`); Commits conventional; Branch `feat/mcp-tool-hub` (vibemind-os) — nie master.
- TDD zwingend: Test zuerst, RED beobachten (Output festhalten), dann GREEN. Regression nach jedem Task: `python -m pytest tests/test_multihop_kotlin_adapter.py tests/test_hop_learning_signal.py tests/test_multihop_ingest_e2e.py tests/test_kotlin_graph.py tests/test_dual_graph.py tests/test_multihop_response_contract.py -q` → **132 passed** (Baseline).
- Brain-Package importiert NIE aus dem voice-Tree.
- Alle Hooks im Executor-Pfad: best-effort, nie raisen (Stil: try/except + logger.debug/warning).
- Kein zweiter Embedder-Load — ausschließlich den `core.qdrant_kg.Embedder`-Singleton wiederverwenden (Memory: ~3GB VRAM pro Doppel-Load).
- Tests laufen aus `C:/Users/User/Desktop/Vibemind_V1/vibemind-os/brain/the_brain` (conftest setzt sys.path); KEIN Modell-/Netz-Zugriff in Unit-Tests.
- Arbeits-Checkout ist V1 (`Vibemind_V1/vibemind-os`); der OS-Baum ist nur Referenz.

---

### Task 1: Read-only Tagebuch-Endpoint `GET /api/diary/stats`

Ohne Beobachtbarkeit ist der Live-Beweis (Task 5) blind. Der Endpoint liest nur `app.state.dual_graph`.

**Files:**
- Modify: `web/routers/introspection.py` (Router-Datei, `router = APIRouter()` existiert; neuen Handler ans Datei-Ende vor evtl. Helper-Schluss setzen)
- Test: `tests/test_diary_stats_endpoint.py` (neu)

**Interfaces:**
- Consumes: `app.state.dual_graph` (DualGraph mit `.kotlingraph`: `.events` List[BrainEvent], `.stats` dict, `.current_episode_id`).
- Produces: `GET /api/diary/stats` → JSON `{total_events, total_episodes, multihop_events, current_episode_id, last_event}` — Task 5 verifiziert hierüber.

- [ ] **Step 1: Failing Test schreiben**

```python
"""Phase 1 — Observability für das episodische Tagebuch (Live-Beweis-Grundlage)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.introspection import router
from core.dual_graph import DualGraph
from core.multihop_kotlin_adapter import record_plan


class _Plan:
    plan_id = "plan_diary_test"
    intent = "diary endpoint test"
    trace_id = "tr_diary"


def _client(dual_graph):
    app = FastAPI()
    app.include_router(router)
    app.state.dual_graph = dual_graph
    return TestClient(app)


def test_diary_stats_reports_multihop_events(tmp_path):
    dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)
    executed = {
        "s1": {"ok": True, "contract_pass": True, "reward": 1.0,
               "capability": "bubble_create", "target": "supabase:bubble.create"},
        "s2": {"ok": True, "contract_pass": None, "reward": 0.0,
               "capability": "idea_add", "target": "supabase:idea.create"},
    }
    assert record_plan(dg, _Plan(), executed) == 2

    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] == 2
    assert body["total_episodes"] == 1
    assert body["multihop_events"] == 2
    assert body["last_event"]["done"] is True
    assert body["last_event"]["plan_id"] == "plan_diary_test"


def test_diary_stats_503_without_dual_graph():
    app = FastAPI()
    app.include_router(router)
    app.state.dual_graph = None
    resp = TestClient(app).get("/api/diary/stats")
    assert resp.status_code == 503
```

- [ ] **Step 2: RED beobachten**

Run: `cd C:/Users/User/Desktop/Vibemind_V1/vibemind-os/brain/the_brain && python -m pytest tests/test_diary_stats_endpoint.py -q`
Expected: FAIL — `404 Not Found` (Route existiert nicht). Output-Zeile festhalten.

- [ ] **Step 3: Endpoint implementieren** (in `introspection.py`, Stil der Nachbar-Routen: graceful bei fehlendem Modul, nie 500 aus Versehen)

```python
@router.get("/api/diary/stats")
async def diary_stats(request: Request):
    """Phase 1 — Read-only Blick ins episodische Tagebuch (KotlinGraph).
    Grundlage für den Live-Beweis: schreibt der Multihop-Ingest real?"""
    dg = getattr(request.app.state, "dual_graph", None)
    if dg is None:
        return JSONResponse({"error": "dual_graph not loaded"}, status_code=503)
    try:
        kg = dg.kotlingraph
        multihop = sum(
            1 for e in kg.events
            if (getattr(e, "metadata", None) or {}).get("source") == "multihop"
        )
        last = kg.events[-1] if kg.events else None
        return JSONResponse({
            "total_events": kg.stats.get("total_events", 0),
            "total_episodes": kg.stats.get("total_episodes", 0),
            "multihop_events": multihop,
            "current_episode_id": kg.current_episode_id,
            "last_event": ({
                "action": last.action,
                "done": last.done,
                "reward": last.reward,
                "plan_id": (last.metadata or {}).get("plan_id"),
                "episode_success": (last.metadata or {}).get("episode_success"),
            } if last else None),
        })
    except Exception as e:  # noqa: BLE001 — Introspection darf nie crashen
        return JSONResponse({"error": str(e)[:200]}, status_code=500)
```

- [ ] **Step 4: GREEN + Regression**

Run: `python -m pytest tests/test_diary_stats_endpoint.py -q` → Expected: `2 passed`.
Run: Regression-Kommando aus Global Constraints → Expected: `132 passed` (plus die 2 neuen separat).

- [ ] **Step 5: Commit (PowerShell)**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/web/routers/introspection.py brain/the_brain/tests/test_diary_stats_endpoint.py
git commit -m "feat(phase1): read-only diary stats endpoint (GET /api/diary/stats)"
```

---

### Task 2: auto_mine aus dem Hot-Path (Intervall-Bump)

Review-Follow-up aus Phase 1: `DualGraph(save_dir='data/moltbook')` nutzt Default `auto_mine_interval=10` — jeder 10. Plan zahlt einen synchronen Full-History-Mining-Pass im `finally` des Executors, unter dem Adapter-Write-Lock. Fix = konservativster Eingriff: Intervall auf 200 (Mining bleibt, 20× seltener; `force_mine()` existiert für on-demand). KEIN Async-Umbau (der Cortical-ResponseAgent teilt dieses DualGraph).

**Files:**
- Modify: `web/brain_server.py` (~Zeile 1026: `state.dual_graph = DualGraph(save_dir='data/moltbook')` und der FOLLOW-UP-Kommentar ~1035-1042)

**Interfaces:**
- Consumes: bestehende `DualGraph(save_dir, auto_mine_interval)`-Signatur.
- Produces: nichts Neues — reine Konfiguration.

- [ ] **Step 1: Zeile ändern**

```python
        state.dual_graph = DualGraph(
            save_dir='data/moltbook',
            # Phase 1 — auto-mine off the hot path: default 10 mined the FULL
            # history synchronously inside plan_executor's finally (under the
            # ingest write lock) every 10th episode. 200 keeps mining alive at
            # 1/20th the cadence; force_mine() covers on-demand needs.
            auto_mine_interval=200,
        )
```

- [ ] **Step 2: Den alten FOLLOW-UP-Kommentar** (direkt vor `state.plan_executor.attach_dual_graph(...)`) **kürzen** auf:

```python
        # Phase 1 — wire episodic task diary into the plan executor.
        # (auto_mine cadence: see DualGraph construction above; background
        # mining remains a future option if plan volume grows further.)
```

- [ ] **Step 3: Verifizieren**

Run: `python -m py_compile web/brain_server.py` → kein Output (OK).
Run: `grep -n "auto_mine_interval=200" web/brain_server.py` → 1 Treffer.

- [ ] **Step 4: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/web/brain_server.py
git commit -m "perf(phase1): raise diary auto_mine_interval 10->200 (hot-path follow-up)"
```

---

### Task 3: Ground-Truth-Coverage — Ratchet-Test + 6 neue truth:-Validatoren

Ist-Zustand (verifiziert): 22/66 Caps mit `truth:`-Validator. Ziel dieses Tasks: 28/66 + ein Ratchet-Test, der Rückschritte verbietet. Die 6 Kandidaten sind Schreib-Caps mit `supabase:`-Target OHNE Validator (verifizierte Liste): `idea_add`, `idea_create_batch`, `component_note_write`, `bubble_evaluate`, `idea_auto_link`, `idea_link_to_root`. (Read-only-Caps wie `bubble_list`/`idea_count` bekommen bewusst KEINEN Fake-Validator; der `openfang:`-Seam braucht das §5.5-Default-Contract-Design — beides explizit Folgearbeit.)

**Files:**
- Modify: `data/capabilities.yaml` (6 Validator-Blöcke; Datei ist top-level eine LISTE von Cap-Dicts)
- Test: `tests/test_capability_truth_coverage.py` (neu)

**Interfaces:**
- Consumes: capabilities.yaml-Schema — Validator-Blöcke exakt nach dem Muster bestehender Caps. Vorbild ROW-Check: `bubble_create` (~:232-247, `kind: truth:supabase_row`); Vorbild EDGE-Check: `idea_connect` (~:405-418, `kind: truth:supabase_edge`). **Vor dem Schreiben beide Vorbild-Blöcke lesen und die postcondition-Felder 1:1 übernehmen** (nur op/Parameter anpassen) — die exakte postcondition-Schema-Struktur ist dort definiert, nicht hier erfinden.
- Produces: `_truth_coverage() -> tuple[int, int]` im Testmodul; Ratchet-Konstante `MIN_TRUTH_VALIDATORS = 28`.

- [ ] **Step 1: Ratchet-Test schreiben (RED gegen heutigen Stand: 22 < 28)**

```python
"""Phase 1 — Ground-Truth-Coverage-Ratchet (§5.5 Reward-Coverage).

Zählt Caps mit truth:-Validator in capabilities.yaml. Der Ratchet darf NUR
steigen — sinkt er, hat jemand Ground-Truth entfernt (Reward-Blindheit).
Ziel-Trajektorie: 22 (vor diesem Plan) -> 28 (dieser Plan) -> >=53 (~80%,
braucht das openfang:-Default-Contract-Design, eigener Plan).
"""
from pathlib import Path

import yaml

CAPS_PATH = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
MIN_TRUTH_VALIDATORS = 28
EXPECTED_NEW = {
    "idea_add", "idea_create_batch", "component_note_write",
    "bubble_evaluate", "idea_auto_link", "idea_link_to_root",
}


def _truth_coverage():
    caps = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    covered = {
        c["capability"] for c in caps
        if isinstance(c.get("validator"), dict)
        and str(c["validator"].get("kind", "")).startswith("truth:")
    }
    return covered, len(caps)


def test_truth_coverage_ratchet():
    covered, total = _truth_coverage()
    assert len(covered) >= MIN_TRUTH_VALIDATORS, (
        f"truth coverage regressed: {len(covered)}/{total} < {MIN_TRUTH_VALIDATORS}"
    )


def test_the_six_new_write_caps_are_covered():
    covered, _ = _truth_coverage()
    missing = EXPECTED_NEW - covered
    assert not missing, f"write caps still without ground truth: {missing}"


def test_yaml_still_parses_and_has_66_caps():
    caps = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    assert isinstance(caps, list) and len(caps) == 66
```

- [ ] **Step 2: RED beobachten**

Run: `python -m pytest tests/test_capability_truth_coverage.py -q`
Expected: 2 FAIL (Ratchet 22<28; 6 Caps fehlen), 1 PASS. Output festhalten.

- [ ] **Step 3: Die 6 Validator-Blöcke eintragen.** Pro Cap direkt unter dessen `execution_target:`-Zeile, Muster vom jeweiligen Vorbild kopieren:
  - `idea_add`, `idea_create_batch`, `component_note_write`, `bubble_evaluate` → ROW-Muster von `bubble_create` (Re-Query, dass die Zeile real existiert / geändert wurde), `on_fail: report`.
  - `idea_auto_link`, `idea_link_to_root` → EDGE-Muster von `idea_connect`.
  - Jeder Block bekommt eine Kommentarzeile `# truth: Phase-1 coverage lift (2026-07-12) — ground truth via world_observer re-query`.
  - WICHTIG: capabilities.yaml ist hot-reloadbar (Memory) — nur YAML, keine Code-Änderung nötig.

- [ ] **Step 4: GREEN + bestehende Validator-Semantik prüfen**

Run: `python -m pytest tests/test_capability_truth_coverage.py -q` → Expected: `3 passed`.
Run: Regression-Kommando (Global Constraints) → `132 passed`.

- [ ] **Step 5: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/data/capabilities.yaml brain/the_brain/tests/test_capability_truth_coverage.py
git commit -m "feat(phase1): truth-validator coverage 22->28 + ratchet test"
```

---

### Task 4: `task_class_clusterer.py` — semantische Task-Klassen (injection-first, Flag OFF)

Phase-2-Baustein des task-trace-Plans: ähnliche Intents → gemeinsame `task_class_id`, damit KuroGraph pro Klasse minen kann und `measured_difficulty` einen Schlüssel hat. Design-Zwänge: (a) Embedder-Singleton wiederverwenden, NIE neu laden; (b) Unit-Tests ohne Modell/Qdrant (Stubs injizieren); (c) im Executor-Hot-Path default-OFF (`TASK_CLASS_CLUSTERING=0`), weil CPU-Encode 4-5s kostet (Memory `reference_brain_embedder_cpu_cuda`).

**Files:**
- Create: `core/task_class_clusterer.py`
- Modify: `core/multihop_kotlin_adapter.py` (optionaler Parameter `task_class_id`)
- Modify: `core/plan_executor.py` (Ingest-Hook im `finally`: flag-gated Clusterer-Aufruf)
- Test: `tests/test_task_class_clusterer.py` (neu)

**Interfaces:**
- Consumes: `core.qdrant_kg.Embedder.get()` (Singleton, `.encode(text) -> vector`); Qdrant-Client-Objekt mit `search(collection, vector, limit)` und `upsert(collection, points)` (lazy aus qdrant_kg beziehen — beim Implementieren dort nachsehen, wie der Client konstruiert wird, und denselben Weg nutzen).
- Produces:
  - `TaskClassClusterer(embedder=None, client=None, collection="brain-task-classes", threshold=0.85)`
  - `.cluster_id(user_text: str) -> str` — `tc_<uuid12>`; bestehende ID bei Cosine ≥ threshold, sonst neue Klasse angelegt. Wirft nie (Fallback: `""`).
  - `record_plan(..., task_class_id: str = "")` — wenn non-empty, landet `task_class_id` in JEDEM Event-Metadata.

- [ ] **Step 1: Failing Tests schreiben** (alles mit Stubs, kein I/O)

```python
"""Phase 1/2 — Task-Klassen-Clustering, injection-first (kein Modell-Load)."""
from core.task_class_clusterer import TaskClassClusterer


class _StubEmbedder:
    """Deterministische 3D-'Embeddings': bekannte Texte -> feste Vektoren."""
    VECS = {
        "review my docker image": [1.0, 0.0, 0.0],
        "check das docker image": [0.98, 0.199, 0.0],   # cos ~0.98 zum ersten
        "erstelle eine bubble":   [0.0, 1.0, 0.0],       # orthogonal
    }
    def encode(self, text):
        return self.VECS[text]


class _StubStore:
    """In-Memory-Ersatz für die Qdrant-Collection."""
    def __init__(self):
        self.points = []  # [(id, vector)]
    def search(self, vector, limit=1):
        import math
        def cos(a, b):
            num = sum(x * y for x, y in zip(a, b))
            den = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b))
            return num / den if den else 0.0
        scored = sorted(((cos(vector, v), pid) for pid, v in self.points), reverse=True)
        return [{"id": pid, "score": s} for s, pid in scored[:limit]]
    def upsert(self, point_id, vector):
        self.points.append((point_id, vector))


def _clusterer():
    return TaskClassClusterer(embedder=_StubEmbedder(), client=_StubStore())


def test_similar_intents_share_a_class():
    c = _clusterer()
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("check das docker image")
    assert a.startswith("tc_") and a == b


def test_dissimilar_intent_gets_new_class():
    c = _clusterer()
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("erstelle eine bubble")
    assert a != b and b.startswith("tc_")


def test_never_raises_on_broken_embedder():
    class _Broken:
        def encode(self, text):
            raise RuntimeError("model down")
    c = TaskClassClusterer(embedder=_Broken(), client=_StubStore())
    assert c.cluster_id("whatever") == ""


def test_adapter_threads_task_class_into_metadata(tmp_path):
    from core.dual_graph import DualGraph
    from core.multihop_kotlin_adapter import record_plan

    class _Plan:
        plan_id, intent, trace_id = "plan_tc", "tc test", "tr_tc"

    dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)
    executed = {"s1": {"ok": True, "contract_pass": True, "reward": 1.0,
                       "capability": "x", "target": "direct:a:b"}}
    record_plan(dg, _Plan(), executed, task_class_id="tc_abc123")
    ev = dg.kotlingraph.events[-1]
    assert ev.metadata["task_class_id"] == "tc_abc123"
```

- [ ] **Step 2: RED beobachten**

Run: `python -m pytest tests/test_task_class_clusterer.py -q`
Expected: FAIL bei Collection — `ModuleNotFoundError: No module named 'core.task_class_clusterer'`. Festhalten.

- [ ] **Step 3: Clusterer implementieren** — Kernlogik (Adapter für echten Qdrant-Client beim Implementieren an `core/qdrant_kg.py` ausrichten; die Stub-API oben — `search(vector, limit)` / `upsert(point_id, vector)` — ist der interne Vertrag, echte Qdrant-Aufrufe hinter einer kleinen privaten Wrapper-Klasse kapseln):

```python
"""Phase 1/2 — TaskClassClusterer: Intent -> stabile task_class_id.

Injection-first: embedder/client sind injizierbar (Tests laufen ohne Modell
und ohne Qdrant). Live: core.qdrant_kg.Embedder.get()-Singleton (NIE neu
laden) + Qdrant-Collection "brain-task-classes". Wirft nie — Fallback "".
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "brain-task-classes"
DEFAULT_THRESHOLD = 0.85


class TaskClassClusterer:
    def __init__(self, embedder: Any = None, client: Any = None,
                 collection: str = DEFAULT_COLLECTION,
                 threshold: float = DEFAULT_THRESHOLD) -> None:
        self._embedder = embedder
        self._client = client
        self._collection = collection
        self._threshold = threshold

    def _get_embedder(self):
        if self._embedder is None:
            from core.qdrant_kg import Embedder  # lazy — nie beim Import laden
            self._embedder = Embedder.get()
        return self._embedder

    def cluster_id(self, user_text: str) -> str:
        """Stabile Klassen-ID für semantisch ähnliche Intents; "" bei Fehler."""
        text = (user_text or "").strip()
        if not text:
            return ""
        try:
            vec = list(self._get_embedder().encode(text))
            hits = self._client.search(vector=vec, limit=1)
            if hits and float(hits[0].get("score", 0.0)) >= self._threshold:
                return str(hits[0]["id"])
            new_id = f"tc_{uuid.uuid4().hex[:12]}"
            self._client.upsert(point_id=new_id, vector=vec)
            return new_id
        except Exception as e:  # noqa: BLE001 — Clustering darf nie blocken
            logger.debug(f"[task-class] cluster_id failed: {e}")
            return ""
```

- [ ] **Step 4: Adapter-Parameter** — in `record_plan(...)` Signatur um `task_class_id: str = ""` erweitern; im Metadata-Bau: `if task_class_id: md["task_class_id"] = task_class_id` (jedes Event, auch der Abort-Closer).

- [ ] **Step 5: Executor-Hook** — im Phase-1-Ingest-Block in `plan_executor.py` (finally), VOR `record_plan`:

```python
                    _tc = ""
                    # Default OFF: CPU-Encode kostet 4-5s — erst aktivieren,
                    # wenn der Embedder nachweislich auf GPU läuft.
                    if os.environ.get("TASK_CLASS_CLUSTERING", "0") in ("1", "true", "True"):
                        try:
                            from core.task_class_clusterer import TaskClassClusterer
                            _tc = TaskClassClusterer().cluster_id(plan.intent or "")
                        except Exception:
                            _tc = ""
```
und `record_plan(..., task_class_id=_tc)`.

- [ ] **Step 6: GREEN + Regression**

Run: `python -m pytest tests/test_task_class_clusterer.py -q` → `4 passed`.
Run: Regression (Global Constraints) → `132 passed` + neue Dateien.

- [ ] **Step 7: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/core/task_class_clusterer.py brain/the_brain/core/multihop_kotlin_adapter.py brain/the_brain/core/plan_executor.py brain/the_brain/tests/test_task_class_clusterer.py
git commit -m "feat(phase1): task-class clusterer (injection-first, flag-gated hot-path)"
```

---

### Task 5: Live-Beweis — Brain neu starten, echter Multihop-Lauf, Tagebuch verifizieren

Komponenten-grün ≠ echter Lauf (Memory `feedback_test_real_execution_mode`). Dieser Task schreibt KEINEN Code — er beweist die Kette end-to-end und protokolliert das Ergebnis.

**Files:**
- Create: `docs/plans/2026-07-12-phase1-live-proof.md` (Protokoll der Beweisergebnisse — Rohoutputs einfügen)

**Interfaces:**
- Consumes: laufender OpenFang `:4200`; Brain `:5000` mit NEUEM Code; `GET /api/diary/stats` (Task 1); `POST /api/multihop/execute`; `POST /api/multihop/plan/{plan_id}/reward`.

- [ ] **Step 1: Brain-Prozess identifizieren** (verifiziert: KEIN Docker-Container — nativer Prozess)

```powershell
Get-NetTCPConnection -LocalPort 5000 -State Listen | Select-Object OwningProcess
Get-Process -Id <PID> | Select-Object Id,ProcessName,Path,StartTime
```
Erwartung: ein python-Prozess. Kommandozeile ermitteln: `(Get-CimInstance Win32_Process -Filter "ProcessId=<PID>").CommandLine` — festhalten (Startbefehl + Arbeitsverzeichnis für den Neustart).

- [ ] **Step 2: Sauber neu starten** — Prozess mit exakt derselben Kommandozeile/CWD neu starten (`Stop-Process -Id <PID> -Confirm:$false`, dann Start via `Start-Process` mit der ermittelten CommandLine; falls `.env`-Variablen nötig sind: Memory `feedback_openfang_restart`-Muster — `.env` zuerst in die Process-Env). Warten bis `curl -s -m 5 http://127.0.0.1:5000/api/health` (oder `/api/multihop/history?limit=1`) 200 liefert.

- [ ] **Step 3: Neuen Code bestätigen (MH-5a-Marker + Diary-Endpoint)**

```bash
curl -s http://127.0.0.1:5000/api/diary/stats
```
Erwartung: 200 mit `total_events`/`multihop_events` (Startwert je nach geladener Persistenz). 404 = alter Code läuft noch → Step 2 wiederholen/debuggen, NICHT weitermachen.

- [ ] **Step 4: Baseline festhalten, dann echter Lauf**

```bash
curl -s http://127.0.0.1:5000/api/diary/stats > /tmp/diary_before.json
curl -s -X POST http://127.0.0.1:5000/api/multihop/execute \
  -H "Content-Type: application/json" \
  -d '{"intent": "erstelle eine bubble namens Phase1-LiveProof und füge die idee Tagebuch-Test hinzu"}'
```
Erwartung in der Response: `"ok": true`, **top-level `"plan_id"`** (MH-5a live!), `trace_id`, `executed` mit ≥2 Hops. plan_id notieren.

- [ ] **Step 5: Tagebuch-Delta verifizieren**

```bash
curl -s http://127.0.0.1:5000/api/diary/stats
```
Erwartung vs. Baseline: `multihop_events` um Hop-Zahl gestiegen, `total_episodes` um ≥1, `last_event.done == true`, `last_event.plan_id == <plan_id aus Step 4>`. Bei `contract_pass`-tragenden Hops (bubble_create/idea_add haben jetzt truth-Validatoren aus Task 3): `last_event.reward != 0.0` wäre der Voll-Beweis; `0.0` mit `episode_success: true` ist akzeptabel, dann Ursache notieren (Validator gefeuert? `validator_verdict` im executed der Step-4-Response prüfen).

- [ ] **Step 6: Reward-Loop live schließen**

```bash
curl -s -X POST http://127.0.0.1:5000/api/multihop/plan/<plan_id>/reward \
  -H "Content-Type: application/json" -d '{"delta": 1.0, "reason": "phase1 live proof"}'
curl -s "http://127.0.0.1:5000/api/multihop/plan/<plan_id>"
```
Erwartung: erster Call `{"ok": true, ...}`; zweiter zeigt `reward_score: 1.0`.

- [ ] **Step 7: Protokoll schreiben + committen** — `docs/plans/2026-07-12-phase1-live-proof.md` mit den Rohoutputs (before/after diary, multihop-Response gekürzt, reward-Response) und einem ehrlichen Fazit (was bewiesen ist, was nicht — z.B. Rewards nur 0.0 weil Validator X nicht feuerte). Negativbefunde sind Ergebnisse, keine Fehler (Memory `feedback_verify_empirically_not_pitch`).

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/docs/plans/2026-07-12-phase1-live-proof.md
git commit -m "docs(phase1): live proof protocol — multihop -> diary -> reward loop"
```

---

### Task 6: Branches pushen (Backup)

~15 lokale Commits über 3 Repo-Ebenen sind ungesichert. ACHTUNG Memory `project_github_dual_account_gotcha`: gh hat 2 Accounts — vor Push aktiven Account prüfen.

**Files:** keine (reine Git-Operation).

- [ ] **Step 1: Remotes + Account prüfen**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os\voice; git remote -v
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os; git remote -v
cd C:\Users\User\Desktop\Vibemind_V1; git remote -v
gh auth status
```
Falls ein Flissel/*-Remote „Repository not found" liefert: `gh auth switch --user Flissel`.

- [ ] **Step 2: Pushen (NUR die Feature-Branches, nie master, kein --force)**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os\voice; git push origin feat/canvas-bidi-reformat
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os; git push origin feat/mcp-tool-hub
cd C:\Users\User\Desktop\Vibemind_V1; git push origin feat/mcp-tool-hub
```
Erwartung: 3× erfolgreicher Push. Reihenfolge wichtig (innen → außen), damit Submodule-Pointer auf gepushte SHAs zeigen.

- [ ] **Step 3: Verifizieren** — `git log origin/feat/mcp-tool-hub -1 --oneline` == lokaler HEAD (in beiden äußeren Repos).

---

## Explizit NICHT in diesem Plan (Folgearbeit)

- **`openfang:`-Default-Contract** (§5.5 fail-closed für die ~20 Agent-Caps) — braucht world_observer-Erweiterung, eigener Plan; erst damit ist ≥80% Coverage erreichbar.
- **Golden-Set** — braucht menschliches Labeling (Owner/Größe offen).
- **Background-Mining** — nur falls Task 2s Intervall-Bump bei realem Volumen nicht reicht.
- **Phase-3-Bandit / measured_difficulty-Cutover** — gated auf Coverage + ≥30 Trajektorien pro Klasse.
