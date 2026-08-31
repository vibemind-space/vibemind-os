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
    assert kg.stats["total_episodes"] == 1
    assert kg.events[-1].done is True
    assert kg.events[-1].metadata["plan_id"] == "plan_a"


def test_second_drain_is_a_noop(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 0
    assert dg.kotlingraph.stats["total_events"] == 2


def test_only_new_lines_are_drained(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1
    assert dg.kotlingraph.stats["total_episodes"] == 2


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
    assert all(len(pids) == 1 for pids in by_ep.values())


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


def test_trailing_partial_line_is_not_consumed(tmp_path, dg):
    """Ein Writer kann mitten im Append sein: Bytes nach dem letzten \\n sind
    eine unfertige Zeile -> NICHT parsen, Offset davor stehen lassen."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    complete_size = q.stat().st_size
    with q.open("a", encoding="utf-8") as f:          # halbe Zeile anhaengen
        f.write('{"v": 1, "plan_id": "plan_half", "eve')

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1                        # nur die vollstaendige
    s = json.loads(st.read_text(encoding="utf-8"))
    assert s["offset"] == complete_size                # Offset VOR dem Fragment

    # jetzt wird die Zeile fertiggeschrieben -> naechster Drain sieht sie ganz
    q.write_text(q.read_text(encoding="utf-8")[:complete_size], encoding="utf-8")
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)
    out2 = drain_once(dg, queue_path=q, state_path=st)
    assert out2["episodes"] == 1
    assert dg.kotlingraph.stats["total_episodes"] == 2


def test_truncated_queue_resets_offset(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    q.write_text("", encoding="utf-8")
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1


def test_corrupt_line_is_skipped_not_fatal(tmp_path, dg):
    q = tmp_path / "d.jsonl"
    q.write_text('{"broken":\n', encoding="utf-8")
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=tmp_path / "d.state.json")

    assert out["episodes"] == 1


def test_skipped_lines_are_counted_in_the_state_file(tmp_path, dg):
    """A skipped line is CONSUMED but never `drained` — without its own
    counter the books do not balance and `pending` (derived elsewhere) can
    never reach 0. Both skip flavours (corrupt JSON, structurally unusable)
    must land in `lines_skipped`."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    q.write_text('{"broken":\n', encoding="utf-8")           # corrupt JSON
    with q.open("a", encoding="utf-8") as f:                  # valid JSON, no events
        f.write(json.dumps({"v": 1, "plan_id": "p_bad", "events": []}) + "\n")
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1
    state = json.loads(st.read_text(encoding="utf-8"))
    assert state["lines_skipped"] == 2
    assert state["episodes_drained"] == 1


def test_rotation_resets_the_cumulative_counters(tmp_path, dg):
    """After a rotation the old file's totals describe a file that no longer
    exists — keeping them makes every derived number (pending, skipped) lie."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    assert json.loads(st.read_text(encoding="utf-8"))["episodes_drained"] == 1

    q.write_text("", encoding="utf-8")   # rotated out from under us
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)

    state = json.loads(st.read_text(encoding="utf-8"))
    # 1, not 2: the counter was reset with the file, then re-counted this cycle.
    assert state["episodes_drained"] == 1
    assert state["lines_skipped"] == 0


def test_missing_queue_is_a_noop(tmp_path, dg):
    out = drain_once(dg, queue_path=tmp_path / "nope.jsonl",
                     state_path=tmp_path / "nope.state.json")
    assert out == {"episodes": 0, "events": 0, "offset": 0}


def test_failing_record_event_does_not_advance_offset(tmp_path, dg):
    """Regel 5: Replay-Fehler -> Offset NICHT vorruecken, naechster Lauf retryt."""
    class _Broken:
        kotlingraph = None
        def record_event(self, **kw):
            raise RuntimeError("graph down")

    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    out = drain_once(_Broken(), queue_path=q, state_path=st)
    assert out["episodes"] == 0                        # nichts, aber kein Crash

    # ein gesunder Graph holt die Episode beim naechsten Lauf nach
    out2 = drain_once(dg, queue_path=q, state_path=st)
    assert out2["episodes"] == 1
    assert dg.kotlingraph.stats["total_events"] == 2


def test_lost_offset_does_not_double_ingest(tmp_path, dg):
    """WICHTIG 1a: Der Offset wird alle 30s committet, persistiert wird aber
    erst alle 300s. Stirbt der Prozess dazwischen, kann der Offset verloren
    gehen (oder umgekehrt Daten). Ein erneutes Replay derselben Episode MUSS
    ein No-Op sein — sonst dupliziert jeder Crash die Historie."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    drain_once(dg, queue_path=q, state_path=st)
    assert dg.kotlingraph.stats["total_events"] == 2

    # Crash: der State (Offset) ist weg, der Graph hat plan_a aber schon.
    st.unlink()

    drain_once(dg, queue_path=q, state_path=st)

    assert dg.kotlingraph.stats["total_events"] == 2    # NICHT verdoppelt
    assert dg.kotlingraph.stats["total_episodes"] == 1


def test_schema_corrupt_episode_does_not_stall_the_queue(tmp_path, dg):
    """WICHTIG 2: JSON-valide, aber strukturell kaputte Episode (Event ohne
    'state') darf die Queue NICHT dauerhaft blockieren — sonst erreicht keine
    einzige spaetere Episode je den Graphen."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    poison = {"v": 1, "plan_id": "plan_poison", "events": [
        {"action": "a::b::c", "next_state": {}, "reward": 1.0,
         "done": True, "metadata": {}},          # 'state' FEHLT
    ]}
    with q.open("a", encoding="utf-8") as f:
        f.write(json.dumps(poison) + "\n")
    enqueue_plan(_Plan("plan_good"), EXEC_OK, queue_path=q)

    out = drain_once(dg, queue_path=q, state_path=st)

    assert out["episodes"] == 1                        # die gute Episode
    assert dg.kotlingraph.stats["total_events"] == 2
    s = json.loads(st.read_text(encoding="utf-8"))
    assert s["offset"] == q.stat().st_size             # VORBEI an beiden
    assert s["last_plan_id"] == "plan_good"


def test_failing_save_does_not_advance_offset(tmp_path, dg):
    """WICHTIG 1b: persist-then-commit. Schlaegt das Speichern fehl, darf der
    Offset NICHT vorruecken — sonst gilt die Episode als konsumiert, liegt
    aber nirgends auf Platte."""
    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)

    def _boom(name="memory"):
        raise OSError("disk full")

    dg.save = _boom
    drain_once(dg, queue_path=q, state_path=st)
    assert not st.exists() or json.loads(st.read_text(encoding="utf-8"))["offset"] == 0

    # Platte wieder da -> naechster Lauf holt es nach, ohne zu duplizieren
    del dg.save
    out2 = drain_once(dg, queue_path=q, state_path=st)
    assert out2["episodes"] == 1
    assert dg.kotlingraph.stats["total_events"] == 2
    assert json.loads(st.read_text(encoding="utf-8"))["offset"] == q.stat().st_size


def test_permanently_failing_record_event_eventually_skips(tmp_path, dg):
    """WICHTIG 2 (Backstop): ein dauerhaft fehlschlagendes record_event darf
    die Queue nicht ewig blockieren. Nach `stall_count` > Cap wird die Zeile
    uebersprungen — eine Episode verlieren ist besser als alle."""
    class _Broken:
        kotlingraph = None
        def record_event(self, *a, **kw):
            raise RuntimeError("graph down")

    q = tmp_path / "d.jsonl"
    st = tmp_path / "d.state.json"
    enqueue_plan(_Plan("plan_a"), EXEC_OK, queue_path=q)
    enqueue_plan(_Plan("plan_b"), EXEC_OK, queue_path=q)

    # Pro Zeile: _MAX_STALL Fehlversuche, dann wird sie uebersprungen.
    # Zwei Zeilen -> 2 * (5 + 1) Zyklen reichen sicher.
    broken = _Broken()
    for _ in range(12):
        drain_once(broken, queue_path=q, state_path=st)

    s = json.loads(st.read_text(encoding="utf-8"))
    assert s["offset"] == q.stat().st_size             # nicht mehr blockiert
