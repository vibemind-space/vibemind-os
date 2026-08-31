"""Phase 1 — Observability für das episodische Tagebuch (Live-Beweis-Grundlage)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.introspection import router
from core.dual_graph import DualGraph
from core.multihop_kotlin_adapter import record_plan, enqueue_plan
from core.multihop_diary_drain import drain_once


class _Plan:
    plan_id = "plan_diary_test"
    intent = "diary endpoint test"
    trace_id = "tr_diary"


class _Plan2:
    plan_id = "plan_diary_test_2"
    intent = "diary endpoint test 2"
    trace_id = "tr_diary_2"


_EXECUTED = {
    "s1": {"ok": True, "contract_pass": True, "reward": 1.0,
           "capability": "bubble_create", "target": "supabase:bubble.create"},
}


def _client(dual_graph, plan_executor=None):
    app = FastAPI()
    app.include_router(router)
    app.state.dual_graph = dual_graph
    if plan_executor is not None:
        app.state.plan_executor = plan_executor
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


def test_queue_block_reports_enqueued_and_pending(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True
    assert enqueue_plan(_Plan2(), _EXECUTED) is True

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()

    assert body["multihop_events"] == 0

    queue = body["queue"]
    assert queue["episodes_enqueued"] == 2
    assert queue["episodes_drained"] == 0
    assert queue["pending"] == 2
    assert queue["path"].endswith("diary_queue.jsonl")


def test_queue_block_reflects_drain_progress(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    result = drain_once(dg, queue_path=queue_path)
    assert result["episodes"] == 1

    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()

    queue = body["queue"]
    assert queue["episodes_drained"] == 1
    assert queue["pending"] == 0
    assert queue["last_plan_id"] == "plan_diary_test"


def test_queue_block_when_no_queue_file(tmp_path, monkeypatch):
    queue_path = tmp_path / "does_not_exist.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()

    queue = body["queue"]
    assert queue["episodes_enqueued"] == 0
    assert queue["pending"] == 0


def test_trailing_partial_line_is_not_counted(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True
    # Append a partial line directly — no trailing '\n' — simulating an
    # in-flight write.
    with open(queue_path, "a", encoding="utf-8") as f:
        f.write('{"v": 1, "plan_id": "in_flight_partial"')

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()

    assert body["queue"]["episodes_enqueued"] == 1


class _StubPlanExecutor:
    def __init__(self, ok, failures):
        self._ok = ok
        self._failures = failures

    def stats_dict(self):
        return {"diary_enqueued": self._ok, "diary_enqueue_failures": self._failures}


def test_enqueue_block_reports_executor_counters(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    pe = _StubPlanExecutor(ok=7, failures=2)
    resp = _client(dg, plan_executor=pe).get("/api/diary/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enqueue"]["ok"] == 7
    assert body["enqueue"]["failures"] == 2

    # No plan_executor on state -> 0/0, still 200.
    resp2 = _client(dg).get("/api/diary/stats")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["enqueue"]["ok"] == 0
    assert body2["enqueue"]["failures"] == 0


# --- pending is derived from the drain OFFSET, not from `drained` ----------
# The drain ADVANCES the offset past corrupt / structurally-unusable /
# backstop-abandoned lines but never counts them in `episodes_drained`. So
# `enqueued - drained` permanently overstates the backlog and can never reach
# 0. The authoritative "how far consumed" marker is the byte offset.


def _append_raw(queue_path, text):
    with open(queue_path, "a", encoding="utf-8") as f:
        f.write(text)


def test_pending_is_zero_when_drain_skipped_a_corrupt_line(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True
    _append_raw(queue_path, "this is not json at all\n")
    assert enqueue_plan(_Plan2(), _EXECUTED) is True

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    drain_once(dg, queue_path=queue_path)

    body = _client(dg).get("/api/diary/stats").json()
    queue = body["queue"]

    assert queue["episodes_enqueued"] == 3
    assert queue["episodes_drained"] == 2
    # The corrupt line was CONSUMED (offset advanced past it) — it is not
    # backlog. Deriving pending from `enqueued - drained` would say 1 forever.
    assert queue["pending"] == 0
    assert queue["skipped"] == 1
    # The books balance.
    assert (queue["episodes_enqueued"]
            == queue["episodes_drained"] + queue["skipped"] + queue["pending"])


def test_pending_counts_only_the_undrained_tail(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    for _ in range(3):
        assert enqueue_plan(_Plan(), _EXECUTED) is True

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    drain_once(dg, queue_path=queue_path)

    for _ in range(2):
        assert enqueue_plan(_Plan2(), _EXECUTED) is True

    queue = _client(dg).get("/api/diary/stats").json()["queue"]
    assert queue["episodes_enqueued"] == 5
    assert queue["pending"] == 2


def test_pending_equals_enqueued_when_state_file_missing(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True
    assert enqueue_plan(_Plan2(), _EXECUTED) is True
    # No drain has ever run -> no state file -> offset 0 -> everything pending.
    assert not (tmp_path / "diary_queue.jsonl.state.json").exists()

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    queue = _client(dg).get("/api/diary/stats").json()["queue"]
    assert queue["episodes_enqueued"] == 2
    assert queue["pending"] == 2
    assert queue["skipped"] == 0


def test_corrupt_state_file_degrades_to_offset_zero(tmp_path, monkeypatch):
    queue_path = tmp_path / "diary_queue.jsonl"
    monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(queue_path))

    assert enqueue_plan(_Plan(), _EXECUTED) is True
    assert enqueue_plan(_Plan2(), _EXECUTED) is True
    # A truncated/garbage state file must not 500 the endpoint — it degrades
    # to offset 0, i.e. "we cannot prove anything was drained".
    _append_raw(tmp_path / "diary_queue.jsonl.state.json", '{"offset": 12')

    dg = DualGraph(save_dir=str(tmp_path / "graph"), auto_mine_interval=10_000)
    resp = _client(dg).get("/api/diary/stats")
    assert resp.status_code == 200
    queue = resp.json()["queue"]
    assert queue["episodes_enqueued"] == 2
    assert queue["pending"] == 2
    assert queue["episodes_drained"] == 0
