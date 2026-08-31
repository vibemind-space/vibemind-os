# Tagebuch-Queue + Drain: Phase-1-Ingest swarm-tauglich machen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multihop-Episoden überleben im Swarm — statt in flüchtigen, pro-Worker getrennten RAM-Graphen zu verdampfen, laufen sie über eine Append-only-Queue zum einzigen Prozess, der persistiert.

**Architecture:** Wir spiegeln 1:1 das im Repo bereits erprobte Queue/Drain-Muster (`routing_matrix_autotrain.py` → `production/autotrain_drain.py`): der HTTP-Prozess **hängt an**, ein Single-Writer-Prozess **drainiert**. Kein geteilter State, kein Lock über Prozessgrenzen.

**Tech Stack:** Python 3.11, pytest, JSONL im geteilten Docker-Volume, Docker Swarm.

---

## 1. Warum — der empirische Befund (was ich gemessen habe, nicht vermutet)

Phase 1 ist test-grün und lief nativ sauber. **Im Swarm ist sie kaputt.** Vier Messungen:

| # | Befund | Wie gemessen |
|---|---|---|
| 1 | **Zwei getrennte Tagebücher.** brain-core läuft mit `BRAIN_HTTP_WORKERS=2` → zwei uvicorn-Prozesse, jeder mit eigenem `app.state.dual_graph`. | Derselbe `GET /api/diary/stats` lieferte erst `multihop_events: 1`, dann `0` — je nachdem, welcher Worker antwortete. |
| 2 | **In brain-core speichert niemand.** `web/brain_server.py`: `if _loops_enabled(): consolidator.start()` — brain-core setzt `BRAIN_BACKGROUND_LOOPS=0`, also wird der `MemoryConsolidator` **konstruiert, aber nie gestartet**. Er ist das Einzige, was je `dual_graph.save()` ruft. | Boot-Log: `[SKIP] MemoryConsolidator (BRAIN_BACKGROUND_LOOPS=0)` |
| 3 | **Der Swarm ersetzt brain-core-Tasks — das RAM-Tagebuch verdampft.** | `docker service ps`: Task „Running 17 min ago", davor zwei „Shutdown". Meine geschriebene Episode `plan_3da96e1a19` war danach **weg**. Zähler sprangen `10671 → 0`. |
| 4 | **brain-loops (der einzige Saver) sieht nie einen Hop.** Es ist ein *anderer Prozess* mit *eigenem* `dual_graph`, ohne HTTP — es persistiert also ein Tagebuch **ohne** Multihop-Events. | Persistierte Datei im Volume: **49 Events, davon 0 multihop.** `plan_3da96e1a19` nicht auf Platte. |

**Kernursache in einem Satz:** *Die Hops entstehen im Prozess, der nicht speichert; der Prozess, der speichert, sieht die Hops nie.*

Das ist genau die Integrations-Drift, die der native Einzelprozess-Beweis maskiert hat (dort waren Loops an → Consolidator lief → alles im selben Prozess).

## 2. Wie die Lösung funktioniert — der Datenfluss

```
  brain-core (HTTP, N=2 Worker, BRAIN_BACKGROUND_LOOPS=0)
  ────────────────────────────────────────────────────────
  POST /api/multihop/execute
        │
        ▼
  PlanExecutor.execute()  →  finally-Block
        │
        ▼
  enqueue_plan(plan, executed)                    [NEU, Task 1+3]
        │  baut die Episode als EINE JSON-Zeile
        │  und HÄNGT sie an (append-only, unter Lock)
        ▼
  /app/data/multihop_diary_queue.jsonl            ◄── geteiltes Volume (brain_data)
        │                                              beide Services mounten es
        │
        │  (brain-core schreibt NIE in sein eigenes dual_graph —
        │   das wäre flüchtig und pro Worker verschieden)
        │
  ══════╪══════════════════ Prozessgrenze ═══════════════════
        │
        ▼
  brain-loops (BRAIN_BACKGROUND_LOOPS=1, BRAIN_ROLE=learner)
  ─────────────────────────────────────────────────────────
  DiaryDrain-Thread (alle 30s)                    [NEU, Task 2]
        │  liest ab Byte-Offset aus <queue>.state.json
        │  → nur NEUE Zeilen, nie doppelt
        ▼
  für jede Episode: record_plan-Replay ins dual_graph
        │  (ein Thread, ein Prozess → Episoden-Reinheit trivial)
        ▼
  MemoryConsolidator (läuft HIER, weil Loops an)
        │
        ▼
  /app/data/moltbook/memory_kotlingraph.json      ◄── persistiert, überlebt Restarts
```

**Warum genau dieses Design — und nicht anders:**

- **Warum eine Queue-Datei und kein geteilter Speicher?** Weil die beiden Prozesse (brain-core, brain-loops) getrennte Container mit getrenntem RAM sind. Das einzige Geteilte ist das Volume. Eine Append-only-Datei ist der einfachste sichere Kanal — und ihr benutzt ihn hier schon (`ROUTING_AUTOTRAIN_QUEUE`).
- **Warum EINE Zeile pro PLAN (nicht pro Hop)?** Der Drain spielt die Episode als Ganzes ab — ein Thread, ein Prozess. Damit ist die Episoden-Reinheit (eine Episode = ein Plan) **strukturell** garantiert, ohne prozessübergreifendes Locking. Bei einer Zeile pro Hop müssten sich zwei parallel schreibende Worker die Episoden-Grenzen teilen — genau das Problem, das der Adapter heute mit einem *prozesslokalen* Lock löst (der über Prozessgrenzen nichts nützt).
- **Warum ein Byte-Offset statt Truncate?** Weil währenddessen weiter angehängt wird. Truncate wäre ein Race. Der Offset macht das Lesen idempotent und restart-sicher — exakt wie `autotrain_drain.py` es tut (inkl. Reset auf 0, wenn die Datei kleiner als der Offset ist = rotiert).
- **Warum schreibt brain-core gar nicht mehr in sein `dual_graph`?** Weil dieser Schreibvorgang nachweislich wertlos ist (Befunde 1–3): flüchtig, pro Worker verschieden, nie gespeichert. Ihn wegzulassen ist ehrlicher als ihn zu behalten.
- **Was passiert nativ (Einzelprozess)?** Dort sind Loops per Default **an** → der Drain-Thread läuft **im selben Prozess** → er drainiert die eigene Queue in das eigene `dual_graph`, das der Consolidator speichert. Verhalten bleibt wie heute, nur über den Umweg der Queue. **Ein Codepfad für beide Welten.**

## 3. Dateien — was entsteht und was sich ändert

| Datei | Rolle |
|---|---|
| `core/multihop_kotlin_adapter.py` | **geändert**: bekommt `build_episode()` (pure) + `enqueue_plan()` (append). `record_plan()` bleibt — es ist jetzt das, was der **Drain** benutzt. |
| `core/multihop_diary_drain.py` | **neu**: liest die Queue ab Offset, spielt Episoden ins `dual_graph`, schreibt State-Datei. |
| `web/brain_server.py` | **geändert**: startet den Drain-Thread — aber nur wenn `_loops_enabled()` (also in brain-loops + nativ, **nicht** in brain-core). |
| `core/plan_executor.py` | **geändert**: der Ingest-Block ruft `enqueue_plan()` statt `record_plan()`. `attach_dual_graph()` entfällt (wird nicht mehr gebraucht). |
| `web/routers/introspection.py` | **geändert**: `/api/diary/stats` bekommt einen `queue`-Block (enqueued/drained/pending) — der ist worker-unabhängig, weil er aus dem Volume liest. |
| `infra/swarm/vibemind-stack.yml` (**äußeres Repo!**) | **geändert**: `GROUND_TRUTH_ENABLED=1`, `MULTIHOP_DIARY_QUEUE`, Config-Bump `brain_capabilities_v7 → _v8`. |

## Global Constraints

- Git **immer** über PowerShell (git-bash crasht). Conventional Commits. Branch `feat/mcp-tool-hub` (vibemind-os **und** äußeres Repo) — nie master.
- TDD zwingend: Test zuerst, **RED beobachten und den Output festhalten**, dann GREEN.
- Regressions-Baseline nach jedem Task (aus `vibemind-os/brain/the_brain`):
  `python -m pytest tests/test_hop_learning_signal.py tests/test_multihop_kotlin_adapter.py tests/test_multihop_ingest_e2e.py tests/test_diary_stats_endpoint.py tests/test_capability_truth_coverage.py tests/test_truth_template_resolves.py tests/test_task_class_clusterer.py tests/test_kotlin_graph.py tests/test_dual_graph.py tests/test_multihop_response_contract.py -q` → aktuell **147 passed** (die Zahl ändert sich durch diesen Plan — jeder Task nennt seinen Sollwert).
- Brain-Package importiert **nie** aus dem voice-Tree.
- Alles im Executor-Pfad: best-effort, **nie raisen** (try/except + logger).
- **Queue-Pfad überall über eine Env-Variable**, Default relativ zum Repo — genau wie `ROUTING_AUTOTRAIN_QUEUE` es macht:
  `MULTIHOP_DIARY_QUEUE`, Default `<the_brain>/data/multihop_diary_queue.jsonl`.
- Swarm-Regeln (aus schmerzhafter Erfahrung): **nie** `docker service update` auf `vibemind_*` (räumt den Stack ab). Deploy nur über `docker stack deploy` / Launcher. Swarm-Configs sind **immutable** → Namensbump `_vN`. Der Launcher **verschluckt Docker-Fehler** — Exit-Code separat prüfen.

---

### Task 1: Adapter — Episode bauen (pure) + in die Queue hängen

**Warum zuerst:** Alles andere hängt am Zeilenformat. Wenn das steht, können Drain (Task 2) und Executor (Task 3) unabhängig darauf bauen.

**Files:**
- Modify: `core/multihop_kotlin_adapter.py`
- Test: `tests/test_multihop_diary_queue.py` (neu)

**Interfaces:**
- Consumes: nichts Neues.
- Produces (Task 2 und 3 verlassen sich hierauf):
  - `build_episode(plan, executed, *, trace_id="", task_class_id="") -> dict` — **pure**, kein I/O. Rückgabe:
    ```python
    {"v": 1, "plan_id": str, "trace_id": str, "task_class_id": str, "ts": float,
     "events": [ {"state": dict, "action": str, "next_state": dict,
                  "reward": float, "done": bool, "metadata": dict}, ... ]}
    ```
    Die `events`-Liste ist **exakt** das, was `record_plan` heute in `dual_graph.record_event(...)` steckt — dieselbe Reihenfolge, dieselbe Semantik (`done=True` nur beim letzten Event, `episode_success`/`plan_ok` in dessen Metadata).
  - `enqueue_plan(plan, executed, *, trace_id="", task_class_id="", queue_path=None) -> bool` — hängt **eine** JSON-Zeile an. `True` bei Erfolg, `False` bei Flag-off/leer/Fehler. **Wirft nie.**
  - `QUEUE_PATH` (Modul-Konstante) — aus Env `MULTIHOP_DIARY_QUEUE`, Default `<the_brain>/data/multihop_diary_queue.jsonl`.
  - `record_plan(...)` bleibt **unverändert in Signatur und Verhalten** (der Drain und die bestehenden Tests benutzen es weiter).

- [ ] **Step 1: Failing Tests schreiben** (`tests/test_multihop_diary_queue.py`)

```python
"""Phase 1 — Tagebuch-Queue: Episode bauen + append-only enqueuen.

Warum: brain-core (HTTP) hat 2 Worker und speichert nie; nur brain-loops
persistiert. Also schreibt brain-core die Episode als EINE Zeile in eine
geteilte Queue, die brain-loops drainiert.
"""
import json

from core.multihop_kotlin_adapter import build_episode, enqueue_plan


class _Plan:
    plan_id = "plan_q1"
    intent = "queue test"
    trace_id = "tr_q1"


EXECUTED = {
    "s1": {"ok": True, "contract_pass": True, "reward": 1.0,
           "capability": "bubble_create", "target": "supabase:bubble.create"},
    "s2": {"ok": True, "contract_pass": None, "reward": 0.0,
           "capability": "idea_add", "target": "supabase:idea.create"},
}


class TestBuildEpisode:
    def test_shape_and_event_count(self):
        ep = build_episode(_Plan(), EXECUTED, trace_id="tr_q1")
        assert ep["v"] == 1
        assert ep["plan_id"] == "plan_q1"
        assert ep["trace_id"] == "tr_q1"
        assert len(ep["events"]) == 2

    def test_only_last_event_closes_the_episode(self):
        ep = build_episode(_Plan(), EXECUTED)
        assert [e["done"] for e in ep["events"]] == [False, True]
        last = ep["events"][-1]
        assert "episode_success" in last["metadata"]
        assert "plan_ok" in last["metadata"]

    def test_is_json_serializable(self):
        # muss als EINE Zeile in JSONL passen
        line = json.dumps(build_episode(_Plan(), EXECUTED))
        assert "\n" not in line
        assert json.loads(line)["plan_id"] == "plan_q1"

    def test_empty_executed_yields_no_events(self):
        assert build_episode(_Plan(), {})["events"] == []

    def test_task_class_id_lands_in_every_event(self):
        ep = build_episode(_Plan(), EXECUTED, task_class_id="tc_abc")
        assert all(e["metadata"]["task_class_id"] == "tc_abc" for e in ep["events"])

    def test_no_task_class_key_when_empty(self):
        ep = build_episode(_Plan(), EXECUTED)
        assert all("task_class_id" not in e["metadata"] for e in ep["events"])


class TestEnqueuePlan:
    def test_appends_exactly_one_line_per_plan(self, tmp_path):
        q = tmp_path / "diary.jsonl"
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=q) is True
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=q) is True
        lines = q.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["plan_id"] == "plan_q1"
        assert len(json.loads(lines[0])["events"]) == 2

    def test_creates_parent_dir(self, tmp_path):
        q = tmp_path / "nested" / "deep" / "diary.jsonl"
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=q) is True
        assert q.exists()

    def test_empty_executed_writes_nothing(self, tmp_path):
        q = tmp_path / "diary.jsonl"
        assert enqueue_plan(_Plan(), {}, queue_path=q) is False
        assert not q.exists()

    def test_flag_off_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MULTIHOP_KOTLIN_INGEST", "0")
        q = tmp_path / "diary.jsonl"
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=q) is False
        assert not q.exists()

    def test_never_raises_on_bad_path(self, tmp_path):
        # eine Datei als "Verzeichnis" missbrauchen -> OSError im Innern
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=blocker / "sub" / "q.jsonl") is False

    def test_concurrent_appends_do_not_interleave(self, tmp_path):
        """8 Threads, 25 Pläne each -> 200 intakte JSON-Zeilen, keine zerrissene."""
        import threading
        q = tmp_path / "diary.jsonl"
        barrier = threading.Barrier(8)

        def worker(k):
            barrier.wait()
            for i in range(25):
                class P:
                    plan_id = f"plan_{k}_{i}"
                    intent = "x"
                    trace_id = ""
                enqueue_plan(P(), EXECUTED, queue_path=q)

        ts = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        lines = q.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 200
        ids = {json.loads(l)["plan_id"] for l in lines}   # jede Zeile parst
        assert len(ids) == 200
```

- [ ] **Step 2: RED beobachten**

Run: `cd C:/Users/User/Desktop/Vibemind_V1/vibemind-os/brain/the_brain && python -m pytest tests/test_multihop_diary_queue.py -q`
Expected: Collection-Error — `ImportError: cannot import name 'build_episode'`. Zeile im Report festhalten.

- [ ] **Step 3: Implementieren**

Der Adapter hat heute in `record_plan()` eine Schleife, die pro Hop `state/action/next_state/reward/done/metadata` baut und direkt `dual_graph.record_event(...)` ruft. **Ziehe genau diese Bau-Logik in `build_episode()` heraus** (pure, ohne I/O) und lasse `record_plan()` sie benutzen — Verhalten von `record_plan` bleibt damit bitgleich (bestehende Tests bleiben grün, das ist der Beweis).

Dann neu, im selben Modul:

```python
_QUEUE_LOCK = threading.Lock()

QUEUE_PATH = Path(
    os.environ.get(
        "MULTIHOP_DIARY_QUEUE",
        str(Path(__file__).resolve().parent.parent / "data" / "multihop_diary_queue.jsonl"),
    )
)


def enqueue_plan(plan, executed, *, trace_id="", task_class_id="", queue_path=None) -> bool:
    """Hängt die Episode als EINE JSONL-Zeile an die geteilte Queue.

    Der HTTP-Prozess (brain-core) hat N Worker und startet den
    MemoryConsolidator nicht (BRAIN_BACKGROUND_LOOPS=0) — er darf also NICHT
    in ein eigenes dual_graph schreiben (flüchtig, pro Worker verschieden).
    Stattdessen: append-only in die Queue; brain-loops (Single-Writer)
    drainiert sie und persistiert. Wirft nie."""
    if not ingest_enabled():
        return False
    try:
        ep = build_episode(plan, executed, trace_id=trace_id, task_class_id=task_class_id)
        if not ep["events"]:
            return False
        line = json.dumps(ep, ensure_ascii=False, default=str) + "\n"
        p = Path(queue_path) if queue_path else QUEUE_PATH
        with _QUEUE_LOCK:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
        return True
    except Exception as e:  # noqa: BLE001 — Ingest darf den Executor nie stören
        logger.warning(f"[diary-queue] enqueue failed: {e}", exc_info=True)
        return False
```

Hinweis zum Concurrency-Test: ein `write()` einer einzelnen Zeile im Append-Modus ist auf beiden relevanten OS atomar genug; der Modul-Lock deckt zusätzlich die Threads **eines** Prozesses ab. Über *Prozess*grenzen (2 uvicorn-Worker) trägt der O_APPEND-Modus — deshalb **eine** Zeile pro Plan und niemals Teilzeilen.

- [ ] **Step 4: GREEN + Regression**

Run: `python -m pytest tests/test_multihop_diary_queue.py -q` → Expected: `13 passed`
Run: Regressions-Kommando (Global Constraints) → Expected: **147 passed** (unverändert — `record_plan` verhält sich bitgleich; genau das beweist der grüne Adapter-Test).

- [ ] **Step 5: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git branch --show-current   # feat/mcp-tool-hub
git add brain/the_brain/core/multihop_kotlin_adapter.py brain/the_brain/tests/test_multihop_diary_queue.py
git commit -m "feat(diary): build_episode + append-only enqueue_plan (queue for the swarm)"
```

---

### Task 2: Der Drain — Queue → dual_graph, im Single-Writer-Prozess

**Warum:** Das ist die andere Hälfte. Er läuft **nur** dort, wo Loops an sind (brain-loops, nativ) — also genau dort, wo der `MemoryConsolidator` speichert.

**Files:**
- Create: `core/multihop_diary_drain.py`
- Modify: `web/brain_server.py` (Thread starten, loop-gated)
- Test: `tests/test_multihop_diary_drain.py` (neu)

**Interfaces:**
- Consumes: `build_episode`-Zeilenformat aus Task 1; `record_plan(dual_graph, ...)` (bestehend); `dual_graph` = `state.dual_graph`.
- Produces:
  - `drain_once(dual_graph, *, queue_path=None, state_path=None) -> dict` — liest **neue** Zeilen ab Offset, spielt sie ab, schreibt State. Rückgabe `{"episodes": int, "events": int, "offset": int}`. **Wirft nie.**
  - `DiaryDrain(dual_graph, interval_s=30.0)` mit `.start()` / `.stop()` — Daemon-Thread, ruft `drain_once` in einer Schleife.
  - State-Datei `<queue>.state.json`: `{"offset": <bytes>, "episodes_drained": N, "events_written": M, "last_plan_id": str, "last_ts": float}` — **einzige** Schreibinstanz ist der Drain. brain-core liest sie nur (Task 4).

- [ ] **Step 1: Failing Tests schreiben** (`tests/test_multihop_diary_drain.py`)

```python
"""Phase 1 — Drain: Queue -> dual_graph im Single-Writer-Prozess."""
import json

import pytest

from core.dual_graph import DualGraph
from core.multihop_diary_drain import drain_once
from core.multihop_kotlin_adapter import enqueue_plan


class _Plan:
    def __init__(self, pid):
        self.plan_id = pid
        self.intent = f"intent {pid}"
        self.trace_id = f"tr_{pid}"


EXEC_OK = {
    "s1": {"ok": True, "contract_pass": True, "reward": 1.0,
           "capability": "bubble_create", "target": "supabase:bubble.create"},
    "s2": {"ok": True, "contract_pass": True, "reward": 1.0,
           "capability": "idea_add", "target": "supabase:idea.create"},
}


@pytest.fixture()
def dg(tmp_path):
    return DualGraph(save_dir=str(tmp_path / "mb"), auto_mine_interval=10_000)


def test_drains_one_episode_into_the_graph(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=tmp_path / "d.state.json")

    assert out["episodes"] == 1 and out["events"] == 2
    kg = dg.kotlingraph
    assert kg.stats["total_events"] == 2
    assert kg.stats["total_episodes"] == 1          # Episode geschlossen
    assert kg.events[-1].done is True
    assert kg.events[-1].metadata["plan_id"] == "plan_a"


def test_second_drain_is_a_noop(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)

    out = drain_once(dg, queue_path=q, state_path=st)   # nichts Neues

    assert out["episodes"] == 0
    assert dg.kotlingraph.stats["total_events"] == 2    # keine Doppel-Ingestion


def test_only_new_lines_are_drained(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1                          # nur plan_b
    assert dg.kotlingraph.stats["total_episodes"] == 2   # zwei saubere Episoden


def test_episode_purity_across_plans(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    for pid in ("plan_a", "plan_b", "plan_c"):
        enqueue_plan(_Plan(pid), EXEC_OK, queue_path=q)

    drain_once(dg, queue_path=q, state_path=tmp_path / "d.state.json")

    kg = dg.kotlingraph
    assert kg.stats["total_episodes"] == 3
    by_ep = {}
    for e in kg.events:
        by_ep.setdefault(e.episode_id, set()).add(e.metadata["plan_id"])
    assert all(len(pids) == 1 for pids in by_ep.values())   # keine Vermischung


def test_state_file_records_progress(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)

    s = json.loads(st.read_text(encoding="utf-8"))
    assert s["episodes_drained"] == 1
    assert s["events_written"] == 2
    assert s["last_plan_id"] == "plan_a"
    assert s["offset"] == q.stat().st_size


def test_truncated_queue_resets_offset(tmp_path, dg):
    """Queue rotiert/geleert -> Offset > Dateigröße -> Reset auf 0, kein Absturz."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    q.write_text("", encoding="utf-8")                  # rotiert
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1                          # plan_b gefunden


def test_corrupt_line_is_skipped_not_fatal(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    q.write_text('{"broken":\n', encoding="utf-8")       # kaputte Zeile
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=tmp_path / "d.state.json")

    assert out["episodes"] == 1                          # gute Zeile kam durch


def test_missing_queue_is_a_noop(tmp_path, dg):
    out = drain_once(dg, queue_path=tmp_path / "nope.jsonl",
                     state_path=tmp_path / "nope.state.json")
    assert out == {"episodes": 0, "events": 0, "offset": 0}


def test_never_raises_on_broken_graph(tmp_path):
    class _Broken:
        kotlingraph = None
        def record_event(self, **kw):
            raise RuntimeError("graph down")

    q = tmp_path / "d.jsonl"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    out = drain_once(_Broken(), queue_path=q, state_path=tmp_path / "d.state.json")
    assert out["episodes"] == 0                          # nichts, aber kein Crash
```

- [ ] **Step 2: RED beobachten**

Run: `python -m pytest tests/test_multihop_diary_drain.py -q`
Expected: `ModuleNotFoundError: No module named 'core.multihop_diary_drain'`. Festhalten.

- [ ] **Step 3: `core/multihop_diary_drain.py` implementieren**

Kernlogik (Offset-Semantik **exakt** wie `production/autotrain_drain.py` — dort nachlesen und spiegeln):

```python
"""Phase 1 — Tagebuch-Drain: geteilte Queue -> dual_graph (Single Writer).

Warum es das gibt: der HTTP-Prozess (brain-core) hat N uvicorn-Worker und
startet den MemoryConsolidator NICHT (BRAIN_BACKGROUND_LOOPS=0) — dort
geschriebene Graphen sind flüchtig und pro Worker verschieden. Also hängt
brain-core die Episoden nur an eine Queue; DIESER Drain läuft im
Loop-Prozess (brain-loops, BRAIN_ROLE=learner) bzw. nativ im selben Prozess
und ist der EINZIGE Schreiber ins dual_graph, das anschließend vom
MemoryConsolidator persistiert wird.

Offset-Muster (1:1 von production/autotrain_drain.py): wir lesen ab einem
Byte-Offset und truncaten NIE — währenddessen wird weiter angehängt.
Ist die Datei kleiner als der Offset (rotiert/geleert), setzen wir auf 0.
"""
```

- `_read_state(state_path)` / `_write_state(...)` → dict mit `offset/episodes_drained/events_written/last_plan_id/last_ts`; fehlende/kaputte Datei → Defaults.
- `drain_once(dual_graph, *, queue_path=None, state_path=None) -> dict`:
  1. Pfade auflösen (Defaults: `QUEUE_PATH` aus dem Adapter, State = `str(queue)+".state.json"`).
  2. Queue fehlt → `{"episodes":0,"events":0,"offset":0}`.
  3. `size = queue.stat().st_size`; `offset = state["offset"]`; `if offset > size: offset = 0` (Reset).
  4. Datei öffnen, `seek(offset)`, `readlines()`.
  5. **Nur vollständige Zeilen verarbeiten**: endet die letzte gelesene Zeile nicht auf `\n`, ist sie ein Teilschreibvorgang → verwerfen und den Offset **davor** setzen (sie kommt beim nächsten Lauf komplett).
  6. Pro Zeile: `json.loads` (Fehler → `logger.warning`, Zeile überspringen, weiterlaufen), dann die `events` **in Reihenfolge** via `dual_graph.record_event(state=..., action=..., next_state=..., reward=..., done=..., metadata=...)` einspielen. Zähler mitführen.
  7. Bei einer Exception aus `record_event`: `logger.warning`, Episode abbrechen — **den Offset für diese Episode NICHT vorrücken** (sie wird beim nächsten Lauf erneut versucht), und `drain_once` beendet sich sauber mit den bis dahin erfolgreichen Zählern.
  8. State schreiben (neuer Offset + kumulierte Zähler), Ergebnis zurückgeben.
  9. **Alles** in try/except — `drain_once` wirft nie.
- `DiaryDrain(dual_graph, interval_s=30.0)`: Daemon-Thread, `while not self._stop.wait(interval_s): drain_once(...)`, mit `.start()`/`.stop()`.

- [ ] **Step 4: In `web/brain_server.py` einhängen — loop-gated**

Direkt **hinter** dem `MemoryConsolidator`-Block (dort steht bereits das Muster `if _loops_enabled(): consolidator.start()` / `else: print("  [SKIP] ...")`). Genauso:

```python
    # --- Tagebuch-Drain (Queue -> dual_graph). NUR im Loop-Prozess:
    # brain-core (BRAIN_BACKGROUND_LOOPS=0) schreibt nur in die Queue; hier
    # (brain-loops / nativ) wird sie drainiert und danach persistiert.
    state.diary_drain = None
    try:
        from core.multihop_diary_drain import DiaryDrain
        if _loops_enabled() and getattr(state, "dual_graph", None) is not None:
            state.diary_drain = DiaryDrain(state.dual_graph)
            state.diary_drain.start()
            print("  [OK] DiaryDrain gestartet (multihop queue -> dual_graph)")
        else:
            print("  [SKIP] DiaryDrain (BRAIN_BACKGROUND_LOOPS=0 -> nur enqueue)")
    except Exception as e:
        print(f"  [WARN] DiaryDrain unavailable: {e}")
```

`brain_loops_worker.py` muss **nicht** angefasst werden — es ruft `_init_production_modules()` und erbt den Thread damit automatisch.

- [ ] **Step 5: GREEN + Regression**

Run: `python -m pytest tests/test_multihop_diary_drain.py -q` → Expected: `9 passed`
Run: `python -m py_compile web/brain_server.py` → kein Output.
Run: Regression → Expected: **147 passed** (unverändert).

- [ ] **Step 6: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/core/multihop_diary_drain.py brain/the_brain/web/brain_server.py brain/the_brain/tests/test_multihop_diary_drain.py
git commit -m "feat(diary): drain queue -> dual_graph in the single-writer process"
```

---

### Task 3: Executor hängt an die Queue statt in den flüchtigen Graphen zu schreiben

**Warum:** Erst hier wird der kaputte Pfad tatsächlich abgeschaltet. Vorher war es additiv, jetzt wird umgestellt.

**Files:**
- Modify: `core/plan_executor.py` (Ingest-Block im `finally`; `attach_dual_graph` entfernen)
- Modify: `tests/test_multihop_ingest_e2e.py` (E2E prüft jetzt die Queue statt des Graphen)

**Interfaces:**
- Consumes: `enqueue_plan(...)` aus Task 1.
- Produces: keine neue API. `PlanExecutor.attach_dual_graph()` **entfällt** (die Executor-Seite braucht kein `dual_graph` mehr — den hat jetzt allein der Drain).

- [ ] **Step 1: E2E-Test umschreiben (das ist der RED)**

`tests/test_multihop_ingest_e2e.py` fährt heute den echten `PlanExecutor` und prüft danach `dg.kotlingraph`. Schreibe ihn um auf die Queue — Kern:

```python
def test_execute_enqueues_one_line_with_all_hops(tmp_path, monkeypatch):
    """Der Executor schreibt NICHT mehr in ein (flüchtiges) dual_graph,
    sondern hängt EINE Zeile mit allen Hops an die geteilte Queue."""
    q = tmp_path / "diary.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))
    # WICHTIG: der Adapter liest QUEUE_PATH beim Import -> Modul neu laden,
    # damit die Env greift (siehe reload-Hinweis unten).
    import importlib
    import core.multihop_kotlin_adapter as ad
    importlib.reload(ad)

    pe = _executor_with_stub_target(monkeypatch)      # wie bisher im File
    plan = _three_hop_plan()                          # wie bisher im File
    result = pe.execute(plan)

    assert result["ok"] is True
    lines = q.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1                            # EINE Zeile pro Plan
    ep = json.loads(lines[0])
    assert ep["plan_id"] == plan.plan_id
    assert len(ep["events"]) == 3
    assert [e["done"] for e in ep["events"]] == [False, False, True]


def test_flag_off_enqueues_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTIHOP_KOTLIN_INGEST", "0")
    q = tmp_path / "diary.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))
    ...
    assert not q.exists()
```

**Reload-Hinweis (wichtig, sonst schlägt der Test scheinbar grundlos fehl):** `QUEUE_PATH` wird beim Modul-Import aus der Env gelesen. Im Test muss das Adapter-Modul nach `monkeypatch.setenv` neu geladen werden — **oder** (sauberer) der Executor gibt den Pfad explizit weiter. Entscheide beim Implementieren und **schreibe die Entscheidung als Kommentar in den Test**; wenn du `importlib.reload` nutzt, lade am Test-Ende wieder zurück, damit andere Tests nicht betroffen sind.

- [ ] **Step 2: RED beobachten** — der umgeschriebene Test failt gegen den heutigen Executor (er schreibt noch ins `dual_graph`, die Queue-Datei bleibt leer). Ausgabe festhalten.

- [ ] **Step 3: Executor umstellen**

Im `finally` von `execute()` steht heute der Phase-1-Block mit `record_plan(dg, plan, executed, trace_id=...)`. Ersetze ihn:

```python
            # Phase 1 — episodisches Tagebuch: EINE Zeile pro Plan in die
            # geteilte Queue. NICHT direkt ins dual_graph: der HTTP-Prozess
            # (brain-core) hat N Worker und persistiert nie -> solche Writes
            # sind flüchtig und pro Worker verschieden. Der Drain im
            # Loop-Prozess ist der einzige Schreiber. (enqueue_plan wirft nie.)
            try:
                from core.multihop_kotlin_adapter import enqueue_plan
                if executed:
                    _tc = ""
                    if os.environ.get("TASK_CLASS_CLUSTERING", "0") in ("1", "true", "True"):
                        try:
                            from core.task_class_clusterer import TaskClassClusterer
                            _tc = TaskClassClusterer().cluster_id(plan.intent or "")
                        except Exception:
                            _tc = ""
                    enqueue_plan(
                        plan, executed,
                        trace_id=getattr(plan, "trace_id", "") or "",
                        task_class_id=_tc,
                    )
            except Exception as e:
                logger.debug(f"[plan-executor] diary enqueue skipped: {e}")
```

Entferne `attach_dual_graph()` (Methode) und den `self._dual_graph`-Zugriff — sie sind jetzt tot. **Suche im Repo nach weiteren Aufrufern** (`grep -rn attach_dual_graph`) und entferne auch den Aufruf in `web/brain_server.py`. Der Drain holt sich `state.dual_graph` selbst (Task 2).

- [ ] **Step 4: GREEN + Regression**

Run: `python -m pytest tests/test_multihop_ingest_e2e.py -q` → GREEN
Run: `grep -rn "attach_dual_graph" --include=*.py .` → **0 Treffer**
Run: Regression → Expected: **147 passed** (die E2E-Tests haben nur ihre Zielsetzung gewechselt, nicht ihre Anzahl; falls die Zahl abweicht, im Report begründen).

- [ ] **Step 5: Commit**

```powershell
cd C:\Users\User\Desktop\Vibemind_V1\vibemind-os
git add brain/the_brain/core/plan_executor.py brain/the_brain/web/brain_server.py brain/the_brain/tests/test_multihop_ingest_e2e.py
git commit -m "refactor(diary): executor enqueues instead of writing an ephemeral graph"
```

---

### Task 4: `/api/diary/stats` ehrlich machen

**Warum:** Nach Task 3 zeigt brain-cores In-Memory-Graph **immer 0 Multihop-Events** — korrekt, aber nutzlos. Die brauchbare Zahl liegt in Queue + State-Datei, und die sind **worker-unabhängig** (geteiltes Volume). Ohne das kann der Live-Check (Task 6) nichts sehen.

**Files:**
- Modify: `web/routers/introspection.py` (`diary_stats`)
- Modify: `tests/test_diary_stats_endpoint.py`

**Interfaces:**
- Consumes: `QUEUE_PATH` (Adapter), State-Datei-Format (Task 2).
- Produces: `GET /api/diary/stats` → die bisherigen Top-Level-Felder **bleiben** (Rückwärtskompatibilität), **plus**:
  ```json
  "queue": {"episodes_enqueued": int, "episodes_drained": int, "pending": int,
            "last_plan_id": str|null, "path": str}
  ```
  `episodes_enqueued` = Zeilenzahl der Queue. `episodes_drained`/`last_plan_id` aus der State-Datei (0/null, wenn kein Drain lief).

- [ ] **Step 1: Tests erweitern (RED)**

```python
def test_queue_block_reports_enqueued_and_pending(tmp_path, monkeypatch):
    """Kernnutzen: brain-core sieht, dass Episoden fließen — auch wenn sein
    eigener In-Memory-Graph (korrekt) leer ist."""
    q = tmp_path / "diary.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))
    enqueue_plan(_Plan("plan_x"), EXECUTED, queue_path=q)
    enqueue_plan(_Plan("plan_y"), EXECUTED, queue_path=q)

    body = _client(_empty_dual_graph(tmp_path)).get("/api/diary/stats").json()

    assert body["queue"]["episodes_enqueued"] == 2
    assert body["queue"]["episodes_drained"] == 0
    assert body["queue"]["pending"] == 2
    assert body["multihop_events"] == 0        # ehrlich: dieser Worker hat nichts


def test_queue_block_reflects_drain_progress(tmp_path, monkeypatch):
    q = tmp_path / "diary.jsonl"; st = tmp_path / "diary.jsonl.state.json"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))
    enqueue_plan(_Plan("plan_x"), EXECUTED, queue_path=q)
    dg = DualGraph(save_dir=str(tmp_path / "mb"), auto_mine_interval=10_000)
    drain_once(dg, queue_path=q, state_path=st)

    body = _client(dg).get("/api/diary/stats").json()

    assert body["queue"]["episodes_drained"] == 1
    assert body["queue"]["pending"] == 0
    assert body["queue"]["last_plan_id"] == "plan_x"


def test_queue_block_when_no_queue_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(tmp_path / "nope.jsonl"))
    body = _client(_empty_dual_graph(tmp_path)).get("/api/diary/stats").json()
    assert body["queue"]["episodes_enqueued"] == 0
    assert body["queue"]["pending"] == 0
```

Die **bestehenden zwei Tests** aus Task 1 der Vorrunde bleiben unverändert und müssen grün bleiben (Rückwärtskompatibilität der Top-Level-Felder).

- [ ] **Step 2: RED beobachten** (`KeyError: 'queue'`). Festhalten.

- [ ] **Step 3: Implementieren** — im `diary_stats`-Handler den `queue`-Block ergänzen; Zeilen zählen (streamend, nicht die ganze Datei in den Speicher), State-Datei best-effort lesen, jeder Fehler → Nullen statt 500.

- [ ] **Step 4: GREEN + Regression** → `python -m pytest tests/test_diary_stats_endpoint.py -q` (5 passed) und Regression.

- [ ] **Step 5: Commit**

```powershell
git add brain/the_brain/web/routers/introspection.py brain/the_brain/tests/test_diary_stats_endpoint.py
git commit -m "feat(diary): expose queue depth + drain progress in /api/diary/stats"
```

---

### Task 5: Stack — Ground-Truth an, Queue-Pfad, Config-Bump

**Warum:** Drei Dinge, die alle im **äußeren** Repo liegen (`Vibemind_V1`, nicht vibemind-os): ohne `GROUND_TRUTH_ENABLED=1` bleibt jeder Reward `0.0` (gemessen: `'ground-truth UNVERIFIED: GROUND_TRUTH_ENABLED off'`); ohne den Queue-Pfad landet die Queue im Container-Layer statt im geteilten Volume; ohne Config-Bump bleiben es 22 statt 27 truth-Validatoren (Swarm-Configs sind **immutable**).

**Files:**
- Modify: `infra/swarm/vibemind-stack.yml` (äußeres Repo!)

- [ ] **Step 1: `brain-core`-Environment ergänzen** (im `environment:`-Block, wo `BRAIN_BACKGROUND_LOOPS=0` steht):

```yaml
      # Ground-Truth scharf: ohne dies liefert JEDER truth:-Validator
      # verified=None ("GROUND_TRUTH_ENABLED off") -> contract_pass=None
      # -> reward 0.0. Gemessen 2026-07-14: das Lernsystem war reward-blind.
      # Alle truth:-Validatoren sind on_fail: report (melden, blocken nicht).
      - GROUND_TRUTH_ENABLED=1
      # Tagebuch-Queue ins GETEILTE Volume (brain-loops drainiert sie dort).
      - MULTIHOP_DIARY_QUEUE=/app/data/multihop_diary_queue.jsonl
```

- [ ] **Step 2: `brain-loops`-Environment ergänzen** — **denselben** Queue-Pfad (der Drain läuft dort):

```yaml
      - MULTIHOP_DIARY_QUEUE=/app/data/multihop_diary_queue.jsonl
```

`GROUND_TRUTH_ENABLED` ist dort **nicht** nötig (brain-loops führt keine Pläne aus) — setze es NICHT, um die Verhaltensänderung minimal zu halten.

- [ ] **Step 3: Config-Bump `v7 → v8`** — Swarm-Configs sind immutable, ein Inhalts-Update **ohne** Namensänderung schlägt fehl („only Labels allowed"). Also:
  - im `configs:`-Block unten: `brain_capabilities_v7:` → `brain_capabilities_v8:` (der `file:`-Pfad bleibt)
  - **beide** Verwendungen (`- source: brain_capabilities_v7`, in brain-core **und** brain-loops) → `_v8`
  - `grep -n "brain_capabilities_v7" infra/swarm/vibemind-stack.yml` → muss **0 Treffer** ergeben.

- [ ] **Step 4: Sanity + Commit** (äußeres Repo!)

```powershell
cd C:\Users\User\Desktop\Vibemind_V1
docker stack config -c infra/swarm/vibemind-stack.yml > $null    # YAML-Parse-Check
git branch --show-current   # feat/mcp-tool-hub
git add infra/swarm/vibemind-stack.yml
git commit -m "feat(infra): enable ground truth, wire diary queue, bump capabilities config v7->v8"
```

---

### Task 6: Deployen und beweisen (Controller, nicht Subagent)

**Warum als eigener Task:** Er fasst Produktion an. Und er ist der **einzige** Beweis, der zählt — Komponenten-grün hat uns letztes Mal getäuscht.

- [ ] **Step 1: Vorzustand festhalten**

```bash
docker service ps vibemind_brain-core --format '{{.CurrentState}}' | head -3
curl -s http://127.0.0.1:5000/api/diary/stats
```

- [ ] **Step 2: Image bauen** (der neue Code muss rein — `:latest` allein rollt **nicht** neu):

```powershell
cd C:\Users\User\Desktop\Vibemind_V1
docker build -t vibemind-brain-core:latest -f <Dockerfile-Pfad> <Build-Kontext>
```
Den korrekten Dockerfile-Pfad/Kontext aus dem letzten erfolgreichen Build ableiten (`docker image inspect vibemind-brain-core:latest` → Labels/History) — **nicht raten**.

- [ ] **Step 3: Deploy über `stack deploy`** (nie `docker service update` — das räumt den Stack ab):

```powershell
docker stack deploy -c infra/swarm/vibemind-stack.yml vibemind
echo "EXIT: $LASTEXITCODE"     # der Launcher verschluckt Docker-Fehler -> hier explizit prüfen
```
Danach warten, bis `docker service ls` für `brain-core` und `brain-loops` wieder `1/1` zeigt.

- [ ] **Step 4: Der Beweis — in dieser Reihenfolge**

1. **Ground-Truth ist an:** echten Lauf fahren
   ```bash
   curl -s -X POST http://127.0.0.1:5000/api/multihop/execute \
     -H "Content-Type: application/json" \
     -d '{"intent":"erstelle eine bubble namens QueueProof"}'
   ```
   Erwartung im Hop: **`contract_pass: true`, `reward: 1.0`**, `validator_verdict.verified: true`.
   Kommt weiterhin `'GROUND_TRUTH_ENABLED off'` → Env hat nicht gegriffen, **hier stoppen**.
2. **Queue füllt sich:** `curl -s http://127.0.0.1:5000/api/diary/stats` → `queue.episodes_enqueued >= 1`.
3. **Drain zieht:** bis zu 30s warten, erneut abfragen → `queue.episodes_drained >= 1`, `pending: 0`.
4. **Persistiert:** im brain-loops-Container prüfen, dass die Episode **auf Platte** liegt:
   ```bash
   cid=$(docker ps --filter "name=vibemind_brain-loops" -q | head -1)
   docker exec $cid python -c "
   import json; d=json.load(open('/app/data/moltbook/memory_kotlingraph.json',encoding='utf-8'))
   mh=[e for e in d['events'] if (e.get('metadata') or {}).get('source')=='multihop']
   print('multihop auf Disk:', len(mh))"
   ```
   Erwartung: **≥ 1** (heute gemessen: 0).
5. **Überlebt einen Neustart — der eigentliche Test:**
   ```powershell
   docker service scale vibemind_brain-core=0
   docker service scale vibemind_brain-core=1
   ```
   Danach Schritt 4 wiederholen → die Episode muss **noch da sein**. Genau das ist heute nicht der Fall.

- [ ] **Step 5: Protokoll schreiben + committen**

`docs/plans/2026-07-14-diary-queue-live-proof.md` mit den Rohausgaben aller fünf Schritte und einem **ehrlichen** Fazit — auch Negativbefunde (z.B. „Drain-Intervall 30s → Episode war erst nach 28s auf Platte"). Wenn ein Schritt scheitert: das dokumentieren, **nicht** übertünchen.

---

## Explizit NICHT in diesem Plan

- **Queue-Rotation/Größenkappung.** Die Datei wächst monoton. Bei realem Volumen (eine Zeile pro Plan, wenige KB) unkritisch; sobald es weh tut: der Drain kann nach erfolgreichem Drain rotieren (`queue.jsonl` → `.1`, Offset auf 0). Bewusst später.
- **`BRAIN_HTTP_WORKERS`.** Bleibt bei 2. Die Queue macht die Worker-Anzahl irrelevant — genau das ist der Punkt.
- **Der `openfang:`-Default-Contract** (die ~20 Agent-Caps ohne Ground-Truth). Coverage bleibt bei 27/66. Eigener Plan.
- **Backfill** der historisch verlorenen Episoden. Sie sind weg; das ist der Preis des Befunds.
