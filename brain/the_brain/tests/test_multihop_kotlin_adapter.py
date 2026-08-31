"""
Tests for core/multihop_kotlin_adapter.py - ingest adapter that turns a
completed multi-hop plan's HopResults into KotlinGraph episodic events.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from core.dual_graph import DualGraph
from core.plan_schema import HopResult
from core.multihop_kotlin_adapter import ingest_enabled, record_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakePlan:
    plan_id: str
    intent: str
    trace_id: str = ""


def make_dual_graph(tmp_path) -> DualGraph:
    return DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)


def hop_dict(
    ok: bool,
    contract_pass: Optional[bool] = None,
    reward: Optional[float] = None,
    validator_verdict: Optional[Dict[str, Any]] = None,
    capability: Optional[str] = "code_review",
    target: Optional[str] = "openfang:brain-coder",
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "ok": ok,
        "validator_verdict": validator_verdict,
        "capability": capability,
        "target": target,
    }
    if contract_pass is not None:
        d["contract_pass"] = contract_pass
    if reward is not None:
        d["reward"] = reward
    return d


# ===================================================================
# Basic happy path
# ===================================================================


class TestRecordPlanBasic:
    def test_three_hop_plan_writes_three_events(self, tmp_path):
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_abc", intent="do the thing")
        executed = {
            "s1": hop_dict(True, contract_pass=True, reward=1.0, validator_verdict={"verified": True}),
            "s2": hop_dict(True),  # no verdict, no contract_pass, no reward
            "s3": hop_dict(True, contract_pass=True, reward=1.0, validator_verdict={"verified": True}),
        }

        n = record_plan(dg, plan, executed, trace_id="trace-1")

        assert n == 3
        assert len(dg.kotlingraph.events) == 3

        events = dg.kotlingraph.events
        # only last event has done=True
        assert [e.done for e in events] == [False, False, True]

        # episode count
        assert dg.kotlingraph.stats["total_episodes"] == 1

        # rewards
        assert [e.reward for e in events] == [1.0, 0.0, 1.0]

        # last event metadata
        last_meta = events[-1].metadata
        assert last_meta["episode_success"] is True
        assert last_meta["plan_ok"] is True

        # every event metadata has source/plan_id/step_id
        for e in events:
            assert e.metadata["source"] == "multihop"
            assert e.metadata["plan_id"] == "plan_abc"
            assert e.metadata["step_id"] in ("s1", "s2", "s3")
            assert e.metadata["trace_id"] == "trace-1"

    def test_failed_last_hop(self, tmp_path):
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_fail", intent="do the thing")
        executed = {
            "s1": hop_dict(True, contract_pass=True, reward=1.0, validator_verdict={"verified": True}),
            "s2": hop_dict(False, contract_pass=False, reward=-1.0),
        }

        n = record_plan(dg, plan, executed, trace_id="trace-2")

        assert n == 2
        events = dg.kotlingraph.events
        assert events[-1].reward == -1.0
        assert events[-1].metadata["episode_success"] is False
        assert events[-1].metadata["plan_ok"] is False
        # boundary must still close the episode even on failure
        assert events[-1].done is True

    def test_reward_derivation_fallback(self, tmp_path):
        """Hop without reward/contract_pass but ok=True + verdict verified False
        -> reward derived via contract_pass_from -> False -> -1.0."""
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_derive", intent="derive reward")
        executed = {
            "s1": hop_dict(True, validator_verdict={"verified": False}),
        }

        n = record_plan(dg, plan, executed)

        assert n == 1
        events = dg.kotlingraph.events
        assert events[0].reward == -1.0
        # metadata stores the COMPUTED effective contract_pass (the value
        # that drove reward/episode_success), not the raw missing field
        assert events[0].metadata["contract_pass"] is False

    def test_metadata_normalizes_capability(self, tmp_path):
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_norm", intent="normalize")
        executed = {"s1": hop_dict(True, contract_pass=True, reward=1.0, capability=None)}

        n = record_plan(dg, plan, executed)

        assert n == 1
        assert dg.kotlingraph.events[0].metadata["capability"] == ""


# ===================================================================
# Flag off
# ===================================================================


class TestFlagOff:
    def test_disabled_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MULTIHOP_KOTLIN_INGEST", "0")
        assert ingest_enabled() is False

        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_off", intent="noop")
        executed = {"s1": hop_dict(True, contract_pass=True, reward=1.0)}

        n = record_plan(dg, plan, executed)

        assert n == 0
        assert len(dg.kotlingraph.events) == 0


# ===================================================================
# Robustness: never raises
# ===================================================================


class FlakyDualGraph:
    """Stub dual_graph whose record_event raises on the 2nd call."""

    def __init__(self):
        self.kotlingraph = None  # unused by adapter directly in this stub
        self._calls = 0

    def record_event(self, state, action, next_state, reward, done, metadata=None):
        self._calls += 1
        if self._calls == 2:
            raise RuntimeError("boom")
        return self._calls


class FailOnceDualGraph:
    """Wrapper around a REAL DualGraph whose record_event raises exactly on
    the 2nd call ever and delegates otherwise."""

    def __init__(self, inner: DualGraph):
        self._inner = inner
        self._calls = 0

    @property
    def kotlingraph(self):
        return self._inner.kotlingraph

    def record_event(self, state, action, next_state, reward, done, metadata=None):
        self._calls += 1
        if self._calls == 2:
            raise RuntimeError("boom on 2nd call")
        return self._inner.record_event(
            state, action, next_state, reward, done, metadata=metadata
        )


class TestEpisodeClosedOnAbort:
    def test_aborted_plan_does_not_leak_open_episode(self, tmp_path):
        """Plan A dies mid-write (record_event raises on hop 2/3). Without a
        synthetic closing event, A's episode stays OPEN and the next plan's
        events silently join it — breaking one-episode-per-plan."""
        inner = make_dual_graph(tmp_path)
        dg = FailOnceDualGraph(inner)

        plan_a = FakePlan(plan_id="plan_A", intent="dies mid-write")
        executed_a = {
            f"a{i}": hop_dict(True, contract_pass=True, reward=1.0)
            for i in range(3)
        }
        record_plan(dg, plan_a, executed_a)

        plan_b = FakePlan(plan_id="plan_B", intent="healthy plan")
        executed_b = {
            f"b{i}": hop_dict(True, contract_pass=True, reward=1.0)
            for i in range(3)
        }
        n_b = record_plan(dg, plan_b, executed_b)
        assert n_b == 3

        kg = inner.kotlingraph
        b_events = [e for e in kg.events if e.metadata.get("plan_id") == "plan_B"]
        assert len(b_events) == 3
        b_episode_ids = {e.episode_id for e in b_events}
        assert len(b_episode_ids) == 1
        b_ep = b_episode_ids.pop()
        # plan B's episode must contain ONLY plan B's events
        ep_plan_ids = {
            kg.events[eid].metadata.get("plan_id")
            for eid in kg.episodes[b_ep]
        }
        assert ep_plan_ids == {"plan_B"}, (
            f"plan B's episode {b_ep} leaked foreign plan_ids: {ep_plan_ids}"
        )

        # the synthetic closing event on A's aborted episode
        a_events = [e for e in kg.events if e.metadata.get("plan_id") == "plan_A"]
        closers = [e for e in a_events if e.metadata.get("aborted")]
        assert len(closers) == 1
        c = closers[0]
        assert c.done is True
        assert c.reward == -1.0
        assert c.action == "none::aborted"
        assert c.metadata["source"] == "multihop"
        assert c.metadata["episode_success"] is False
        assert c.metadata["plan_ok"] is False


class TestNeverRaises:
    def test_partial_write_on_exception(self):
        dg = FlakyDualGraph()
        plan = FakePlan(plan_id="plan_flaky", intent="flaky")
        executed = {
            "s1": hop_dict(True, contract_pass=True, reward=1.0),
            "s2": hop_dict(True, contract_pass=True, reward=1.0),
            "s3": hop_dict(True, contract_pass=True, reward=1.0),
        }

        n = record_plan(dg, plan, executed)

        assert n == 1

    def test_none_dual_graph_returns_zero(self):
        plan = FakePlan(plan_id="plan_none", intent="none")
        executed = {"s1": hop_dict(True, contract_pass=True, reward=1.0)}
        assert record_plan(None, plan, executed) == 0

    def test_empty_executed_returns_zero(self, tmp_path):
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_empty", intent="empty")
        assert record_plan(dg, plan, {}) == 0
        assert record_plan(dg, plan, None) == 0


# ===================================================================
# Concurrency: episode purity
# ===================================================================


class TestEpisodePurity:
    def test_two_concurrent_plans_do_not_mix_episodes(self, tmp_path):
        dg = make_dual_graph(tmp_path)

        plan_a = FakePlan(plan_id="plan_A", intent="alpha task")
        plan_b = FakePlan(plan_id="plan_B", intent="beta task")

        executed_a = {
            f"a{i}": hop_dict(True, contract_pass=True, reward=1.0)
            for i in range(4)
        }
        executed_b = {
            f"b{i}": hop_dict(True, contract_pass=True, reward=1.0)
            for i in range(4)
        }

        barrier = threading.Barrier(2)
        results: Dict[str, int] = {}

        def worker(name, plan, executed):
            barrier.wait()
            results[name] = record_plan(dg, plan, executed, trace_id=name)

        t1 = threading.Thread(target=worker, args=("A", plan_a, executed_a))
        t2 = threading.Thread(target=worker, args=("B", plan_b, executed_b))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["A"] == 4
        assert results["B"] == 4
        assert dg.kotlingraph.stats["total_episodes"] == 2

        # for every episode, all its events share one plan_id
        for ep_id, event_ids in dg.kotlingraph.episodes.items():
            plan_ids = {
                dg.kotlingraph.events[eid].metadata.get("plan_id")
                for eid in event_ids
            }
            assert len(plan_ids) == 1, f"episode {ep_id} mixed plan_ids: {plan_ids}"


# ===================================================================
# HopResult dataclass input
# ===================================================================


class TestHopResultDataclass:
    def test_hopresult_objects_work_like_dicts(self, tmp_path):
        dg = make_dual_graph(tmp_path)
        plan = FakePlan(plan_id="plan_hr", intent="dataclass hops")
        executed = {
            "s1": HopResult(
                step_id="s1",
                ok=True,
                contract_pass=True,
                reward=1.0,
                capability="code_review",
                target="openfang:brain-coder",
            ),
            "s2": HopResult(
                step_id="s2",
                ok=True,
                contract_pass=True,
                reward=1.0,
                capability="synth",
                target=None,
            ),
        }

        n = record_plan(dg, plan, executed, trace_id="trace-hr")

        assert n == 2
        events = dg.kotlingraph.events
        assert [e.done for e in events] == [False, True]
        assert [e.reward for e in events] == [1.0, 1.0]
        assert events[0].action == "openfang:brain-coder:code_review"
        assert events[1].action == "none::synth"
