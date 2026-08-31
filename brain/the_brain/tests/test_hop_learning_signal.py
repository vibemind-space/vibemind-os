"""Phase 1 — hop-level learning signal (outcome-gate semantics).

Covers:
  1. contract_pass_from() truth table (pure function)
  2. HopResult default backward-compat (contract_pass=None, reward=0.0)
  3. Integration through the REAL PlanExecutor._exec_hop:
       - ok, no validator -> contract_pass is None, reward == 0.0 (UNVERIFIED,
         never trains positive just because nothing crashed)
       - executor fails -> contract_pass is False, reward == -1.0
       - executor ok + truth: validator verifies -> contract_pass is True,
         reward == 1.0
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.plan_schema import HopResult, contract_pass_from, HopSpec
from core.plan_executor import PlanExecutor


# ── 1. contract_pass_from truth table ──────────────────────────────────


@pytest.mark.parametrize(
    "ok,verdict,expected",
    [
        (True, {"verified": True}, True),
        (True, {"verified": False}, False),
        (True, {"verified": None}, None),
        (True, None, None),
        (True, {}, None),
        (False, {"verified": True}, False),
    ],
)
def test_contract_pass_from_truth_table(ok, verdict, expected):
    assert contract_pass_from(ok, verdict) is expected


# ── 2. HopResult defaults (backward compat) ────────────────────────────


def test_hopresult_defaults_backward_compat():
    hr = HopResult(step_id="s", ok=True)
    assert hr.contract_pass is None
    assert hr.reward == 0.0


# ── 3. Integration through the REAL PlanExecutor._exec_hop ─────────────


class _StubExecutorOkNoVerdict:
    def call_with_arg(self, *args, **kwargs):
        return {"ok": True, "result": "x", "elapsed_s": 0.0, "target": "stub"}


class _StubExecutorFails:
    def call_with_arg(self, *args, **kwargs):
        return {"ok": False, "error": "boom"}


class _StubValidator:
    def validate(self, *args, **kwargs):
        return {"valid": True, "verified": True}


def test_exec_hop_ok_without_validator_is_unverified(monkeypatch):
    monkeypatch.setattr(
        "core.capability_targets.build_executor",
        lambda target: _StubExecutorOkNoVerdict(),
    )
    pe = PlanExecutor()
    hop = HopSpec(step_id="s1", description="do a thing", execution_target="stub:test")
    result = pe._exec_hop(hop, state={})
    assert result.ok is True
    assert result.contract_pass is None
    assert result.reward == 0.0


def test_exec_hop_failing_executor_is_contract_fail(monkeypatch):
    monkeypatch.setattr(
        "core.capability_targets.build_executor",
        lambda target: _StubExecutorFails(),
    )
    pe = PlanExecutor()
    hop = HopSpec(
        step_id="s2", description="do a thing that fails",
        execution_target="stub:test", retries=1,
    )
    result = pe._exec_hop(hop, state={})
    assert result.ok is False
    assert result.contract_pass is False
    assert result.reward == -1.0


def test_exec_hop_no_execution_target_is_contract_fail():
    # No execution_target and no capability router -> _exec_hop's early
    # "no execution target" return. A hard failure must gate False/-1.0,
    # not fall back to the neutral defaults (None/0.0).
    pe = PlanExecutor()
    hop = HopSpec(step_id="s4", description="unresolvable hop")
    result = pe._exec_hop(hop, state={})
    assert result.ok is False
    assert result.contract_pass is False
    assert result.reward == -1.0


def test_exec_hop_verified_truth_validator_is_contract_pass(monkeypatch):
    monkeypatch.setattr(
        "core.capability_targets.build_executor",
        lambda target: _StubExecutorOkNoVerdict(),
    )
    pe = PlanExecutor(validator=_StubValidator())
    hop = HopSpec(
        step_id="s3", description="do a verified thing",
        execution_target="stub:test",
    )
    hop.validator = "truth:whatever"
    result = pe._exec_hop(hop, state={})
    assert result.ok is True
    assert result.contract_pass is True
    assert result.reward == 1.0
