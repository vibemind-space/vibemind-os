"""Phase 1 — Tagebuch-Queue: Episode bauen + append-only enqueuen.

Warum: brain-core (HTTP) hat 2 Worker und speichert nie; nur brain-loops
persistiert. Also schreibt brain-core die Episode als EINE Zeile in eine
geteilte Queue, die brain-loops drainiert.
"""
import json
import os
import sys
from pathlib import Path

# Muss VOR dem core-Import stehen: der cross-process-Test unten startet
# via multiprocessing "spawn" (Default auf Windows) Kindprozesse, die
# dieses Modul eigenstaendig re-importieren — ohne pytests rootdir-
# sys.path-Injection. Ohne diesen Bootstrap scheitert dort `import core`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.multihop_kotlin_adapter import build_episode, enqueue_plan  # noqa: E402


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


# --- cross-process fixtures (module-level: muessen spawn-picklebar sein) ---

def _big_executed(hops: int = 50) -> dict:
    """Ein REALER 50-Hop-Plan (MULTIHOP_REPEAT_MAX=50 ist ein ausgelieferter
    Code-Pfad). Die daraus gebaute JSON-Zeile ist ~33 KB — weit ueber
    PIPE_BUF (4096), d.h. selbst ein einzelner os.write() ist auf keinem
    Dateisystem verlaesslich atomar. Groesse allein traegt die Sicherheit
    also NICHT; der cross-process File-Lock muss es tun."""
    return {
        f"s{i}": {
            "ok": True, "contract_pass": True, "reward": 1.0,
            "capability": f"capability_number_{i}",
            "target": f"supabase:some.long.target.name.number.{i}",
        }
        for i in range(hops)
    }


class _MPPlan:
    def __init__(self, plan_id: str) -> None:
        self.plan_id = plan_id
        self.intent = "cross process queue test"
        self.trace_id = "tr_mp"


def _mp_worker(queue_path_str: str, k: int) -> None:
    """Laeuft in einem EIGENEN Prozess (kein geteilter threading.Lock!)."""
    from core.multihop_kotlin_adapter import enqueue_plan as _enq
    executed = _big_executed()
    q = Path(queue_path_str)
    for i in range(20):
        _enq(_MPPlan(f"mp_{k}_{i}"), executed, queue_path=q)


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

    def test_no_crlf_translation_in_the_queue_bytes(self, tmp_path):
        """Der Drain rechnet in BYTE-Offsets. Ohne O_BINARY uebersetzt die
        Windows-CRT jedes \\n zu \\r\\n -> jeder Offset ist um 1 Byte pro Zeile
        falsch. Die Queue muss BYTE-genau LF-terminiert sein."""
        q = tmp_path / "diary.jsonl"
        enqueue_plan(_Plan(), EXECUTED, queue_path=q)
        enqueue_plan(_Plan(), EXECUTED, queue_path=q)

        data = q.read_bytes()
        assert b"\r\n" not in data
        assert b"\r" not in data
        assert data.endswith(b"}\n")
        # Byte-Laenge == Summe der Zeilen + genau 1 LF pro Zeile
        assert len(data) == sum(len(l) + 1 for l in data.split(b"\n")[:-1])

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
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        assert enqueue_plan(_Plan(), EXECUTED, queue_path=blocker / "sub" / "q.jsonl") is False

    def test_concurrent_appends_do_not_interleave(self, tmp_path):
        """8 Threads, 25 Plaene each -> 200 intakte JSON-Zeilen, keine zerrissene.

        GRENZE DIESES TESTS (ehrlich): er beweist nur INTRA-Prozess-/Thread-
        Sicherheit, und das quasi per Konstruktion — alle 8 Threads teilen
        sich denselben modul-globalen threading.Lock, der sie serialisiert.
        Die ECHTE Gefahr in Produktion ist eine andere: brain-core laeuft mit
        ZWEI uvicorn-Worker-PROZESSEN, die dieselbe Datei anhaengen. Ein
        threading.Lock reicht dort per Definition nicht. Diese Luecke deckt
        test_concurrent_process_appends_are_not_torn ab.
        """
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
        ids = {json.loads(l)["plan_id"] for l in lines}
        assert len(ids) == 200

    def test_concurrent_process_appends_are_not_torn(self, tmp_path):
        """4 ECHTE Prozesse x 20 grosse Episoden (~33 KB/Zeile) -> 80 intakte
        JSON-Zeilen. Das ist der Fall, der in Produktion wirklich auftritt
        (brain-core = 2 uvicorn-Worker-Prozesse auf DERSELBEN Queue-Datei):
        kein geteilter threading.Lock, Zeilen weit ueber PIPE_BUF. Nur der
        cross-process File-Lock (flock/msvcrt) haelt das zusammen — eine
        zerrissene Zeile waere eine still verlorene Episode, denn diese
        Queue ist der EINZIGE Pfad zur Persistenz."""
        import multiprocessing as mp

        q = tmp_path / "diary.jsonl"
        ctx = mp.get_context("spawn")  # Windows-Default, explizit fuer POSIX
        procs = [ctx.Process(target=_mp_worker, args=(str(q), k)) for k in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
        assert all(p.exitcode == 0 for p in procs), \
            f"worker exitcodes: {[p.exitcode for p in procs]}"

        raw = q.read_text(encoding="utf-8")
        lines = raw.strip().split("\n")
        assert len(lines) == 80, f"erwartet 80 Zeilen, bekommen {len(lines)}"

        # Jede Zeile muss fuer sich allein parsen — genau das, was der Drain tut.
        ids = set()
        for n, line in enumerate(lines):
            try:
                ep = json.loads(line)
            except json.JSONDecodeError as e:
                raise AssertionError(
                    f"ZERRISSENE Zeile {n} ({len(line)} bytes): {e}"
                ) from e
            assert len(ep["events"]) == 50
            ids.add(ep["plan_id"])
        assert len(ids) == 80

        # Beweis, dass die Zeilen wirklich gross sind (Groesse != Sicherheit).
        assert max(len(l.encode("utf-8")) for l in lines) > 4096


class TestQueuePathResolvedAtCallTime:
    """MULTIHOP_DIARY_QUEUE muss zur AUFRUFZEIT gelesen werden, nicht beim
    Modul-Import.

    Warum das zaehlt: der Stack pinnt die Env-Variable auf brain-core (haengt
    an) UND brain-loops (drainiert). Wuerde der Pfad beim Import einfrieren,
    koennte ein spaeterer Edit, der die Variable nur auf EINEM der beiden
    Services setzt (das Schwester-`ROUTING_AUTOTRAIN_QUEUE` ist genau so von
    Hand in zwei Services gepinnt), die beiden Haelften auf VERSCHIEDENE
    Dateien zeigen lassen — der Drain saehe nie eine Episode, still und
    dauerhaft. Import-Zeit-Aufloesung macht genau diesen Fehler unsichtbar
    UND untestbar (kein monkeypatch.setenv koennte ihn je nachstellen).
    """

    def test_enqueue_uses_env_var_set_after_import(self, tmp_path, monkeypatch):
        from core.multihop_kotlin_adapter import enqueue_plan as _eq

        q = tmp_path / "from_env.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))

        # KEIN importlib.reload: genau das ist der Punkt.
        assert _eq(_Plan(), EXECUTED) is True

        lines = q.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["plan_id"] == "plan_q1"

    def test_explicit_queue_path_still_wins_over_env(self, tmp_path, monkeypatch):
        from core.multihop_kotlin_adapter import enqueue_plan as _eq

        env_q = tmp_path / "from_env.jsonl"
        explicit_q = tmp_path / "explicit.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(env_q))

        assert _eq(_Plan(), EXECUTED, queue_path=explicit_q) is True

        assert explicit_q.exists()
        assert not env_q.exists()

    def test_resolve_falls_back_to_default_without_env(self, monkeypatch):
        from core.multihop_kotlin_adapter import QUEUE_PATH, resolve_queue_path

        monkeypatch.delenv("MULTIHOP_DIARY_QUEUE", raising=False)
        assert resolve_queue_path() == QUEUE_PATH

    def test_drain_resolves_the_same_env_path_at_call_time(self, tmp_path, monkeypatch):
        """Die andere Haelfte: der Drain muss dieselbe Env zur Aufrufzeit
        aufloesen — sonst koennen Schreiber und Leser trotz identischer Env
        auseinanderlaufen."""
        from core.dual_graph import DualGraph
        from core.multihop_diary_drain import drain_once
        from core.multihop_kotlin_adapter import enqueue_plan as _eq

        q = tmp_path / "shared.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))

        assert _eq(_Plan(), EXECUTED) is True

        dg = DualGraph(save_dir=str(tmp_path / "mb"), auto_mine_interval=10_000)
        # weder queue_path noch state_path: beide muessen aus der Env kommen
        out = drain_once(dg)

        assert out["episodes"] == 1
        assert out["events"] == 2
        assert dg.kotlingraph.events[-1].metadata["plan_id"] == "plan_q1"
