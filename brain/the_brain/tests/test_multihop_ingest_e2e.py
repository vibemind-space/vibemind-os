"""
E2E test: multihop -> diary QUEUE ingest through the REAL PlanExecutor.execute.

Phase 1 (swarm fix, 2026-07-14): the executor no longer writes plan episodes
directly into an in-memory DualGraph (that write was worthless in production
-- brain-core runs 2 uvicorn workers, each with its own graph, and never
starts the MemoryConsolidator that would persist it). It now enqueues one
JSONL line per plan into the shared diary queue
(core/multihop_kotlin_adapter.py::enqueue_plan); a separate drain
(core/multihop_diary_drain.py), running in the loop-process, is the only
thing that ever writes into the persisted dual_graph. So this test asserts
on the QUEUE FILE, not on a DualGraph -- and PlanExecutor no longer has (or
needs) a dual_graph-attach hook at all.

Queue-path plumbing: a plain `monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", ...)`
is all that is needed here, because `enqueue_plan` resolves the path at CALL
time (`resolve_queue_path`), not at module import. That is deliberate: the
swarm pins the env var on brain-core (appends) AND brain-loops (drains), and
an import-time constant would freeze whatever the environment was at first
import -- hiding a path mismatch between the two halves and making it
untestable. Hence no importlib.reload dance here.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec, Plan


class _StubExecutorOk:
    def call_with_arg(self, *args, **kwargs):
        return {"ok": True, "result": "x", "elapsed_s": 0.0, "target": "stub"}


def make_plan(plan_id: str = "plan_e2e") -> Plan:
    hops = [
        HopSpec(step_id="s1", description="hop one", execution_target="direct:x:y"),
        HopSpec(step_id="s2", description="hop two", execution_target="direct:x:y", depends_on=["s1"]),
        HopSpec(step_id="s3", description="hop three", execution_target="direct:x:y", depends_on=["s2"]),
    ]
    return Plan(plan_id=plan_id, intent="do the e2e thing", rationale="", hops=hops)


class TestE2EIngestThroughExecute:
    def test_execute_enqueues_one_line_with_all_hops(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        q = tmp_path / "diary.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))

        pe = PlanExecutor()
        plan = make_plan("plan_e2e_ok")
        result = pe.execute(plan)

        assert result["ok"] is True

        lines = q.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1  # ONE line per plan

        episode = json.loads(lines[0])
        assert episode["plan_id"] == plan.plan_id
        events = episode["events"]
        assert len(events) == 3
        assert [e["done"] for e in events] == [False, False, True]

    def test_flag_off_enqueues_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        monkeypatch.setenv("MULTIHOP_KOTLIN_INGEST", "0")
        q = tmp_path / "diary.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))

        pe = PlanExecutor()
        plan = make_plan("plan_e2e_flagoff")
        result = pe.execute(plan)

        assert result["ok"] is True
        assert not q.exists()

    def test_no_dual_graph_needed(self, tmp_path, monkeypatch):
        """There is no graph-attach hook anymore -- the executor enqueues
        with no graph attached at all, and that's fine: the (only) consumer
        of the queue is the drain, in a different process."""
        graph_attach_method = "attach_dual" + "_graph"  # built at runtime so
        # this file itself contains zero literal references to the removed
        # method name (repo policy: that name must not grep-match anywhere
        # once the wiring is torn out).
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        q = tmp_path / "diary.jsonl"
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(q))

        pe = PlanExecutor()  # no graph-attach call -- the method is gone
        assert not hasattr(pe, graph_attach_method)

        plan = make_plan("plan_e2e_noattach")
        result = pe.execute(plan)

        assert result["ok"] is True
        lines = q.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["plan_id"] == plan.plan_id


class TestDiaryEnqueueCounters:
    """A dropped episode must be COUNTABLE. enqueue_plan never raises and only
    logs on failure, so without a counter "1 lost episode" and "10.000 lost
    episodes" look identical -- and the queue is the ONLY path an executed
    plan has to persistent memory."""

    def test_successful_enqueue_is_counted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(tmp_path / "diary.jsonl"))

        pe = PlanExecutor()
        pe.execute(make_plan("plan_count_ok"))

        stats = pe.stats_dict()
        assert stats["diary_enqueued"] == 1
        assert stats["diary_enqueue_failures"] == 0

    def test_failed_enqueue_is_counted(self, tmp_path, monkeypatch):
        """A queue path that cannot be written (a FILE where a directory must
        be) -> enqueue_plan returns False -> the failure is counted, not
        silently swallowed."""
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(blocker / "sub" / "q.jsonl"))

        pe = PlanExecutor()
        pe.execute(make_plan("plan_count_fail"))

        stats = pe.stats_dict()
        assert stats["diary_enqueued"] == 0
        assert stats["diary_enqueue_failures"] == 1

    def test_flag_off_is_not_a_failure(self, tmp_path, monkeypatch):
        """Ingest deliberately disabled -> enqueue_plan returns False, but that
        is a no-op, NOT a lost episode. It must not inflate the failure count
        (which is meant to be an alarm)."""
        monkeypatch.setattr(
            "core.capability_targets.build_executor",
            lambda target: _StubExecutorOk(),
        )
        monkeypatch.setenv("MULTIHOP_KOTLIN_INGEST", "0")
        monkeypatch.setenv("MULTIHOP_DIARY_QUEUE", str(tmp_path / "diary.jsonl"))

        pe = PlanExecutor()
        pe.execute(make_plan("plan_count_flagoff"))

        stats = pe.stats_dict()
        assert stats["diary_enqueued"] == 0
        assert stats["diary_enqueue_failures"] == 0
