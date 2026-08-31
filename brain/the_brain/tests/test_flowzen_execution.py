"""Flowzen capability contracts through Brain's real Supabase target."""

import asyncio
from pathlib import Path

import yaml

from core.capability_targets import SupabaseExecutor, build_executor
from core.capability_router import CapabilityRouter
from core.capability_validator import CapabilityValidator
from core.flowzen_ops import accept_op, recommend_op, status_op
from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec, Plan


class _FakeClient:
    def __init__(self):
        self.requests = []
        self.rows = {
            "flowzen_checkins": [
                {
                    "id": "checkin-1",
                    "mood": "focused",
                    "energy": 8,
                    "time_window": "morning",
                    "hour": 9,
                    "created_at": "2026-07-30T09:00:00Z",
                }
            ],
            "flowzen_activity": [],
        }

    async def _request(self, method, path, *, params=None, json=None, prefer=None):
        self.requests.append((method, path, params, json, prefer))
        table = path.removeprefix("/")
        if method == "GET":
            if table == "flowzen_activity" and params and "id" in params:
                activity_id = params["id"].removeprefix("eq.")
                return [r for r in self.rows[table] if r["id"] == activity_id]
            return list(self.rows[table])
        if method == "POST" and table == "flowzen_activity":
            row = {"id": "activity-1", "created_at": "2026-07-30T09:01:00Z", **json}
            self.rows[table].append(row)
            return [row]
        raise AssertionError(f"unexpected request {method} {path}")


def test_recommend_is_read_only_and_returns_minimal_validated_result():
    client = _FakeClient()

    result = asyncio.run(recommend_op(client, {}))

    assert result["ok"] is True
    assert result["event_id"] == "rose.recommend"
    assert result["recommendation"]["category"] == "deep_work"
    assert result["recommendation"]["recommendation_id"].startswith("fzr_")
    assert "notes" not in result
    assert {request[0] for request in client.requests} == {"GET"}


def test_accept_requires_id_mutates_only_activity_and_verifies_readback():
    client = _FakeClient()
    recommendation = asyncio.run(recommend_op(client, {}))["recommendation"]
    client.requests.clear()

    result = asyncio.run(
        accept_op(client, {"recommendation_log_id": recommendation["recommendation_id"]})
    )

    assert result == {
        "ok": True,
        "event_id": "rose.accept",
        "recommendation_id": recommendation["recommendation_id"],
        "activity_id": "activity-1",
        "status": "accepted",
        "verified": True,
    }
    assert [request[0] for request in client.requests] == ["GET", "POST", "GET"]
    assert client.requests[1][1] == "/flowzen_activity"
    assert set(client.requests[1][3]) == {"event_type", "time_window", "hour"}


def test_accept_rejects_untrusted_or_missing_recommendation_id_without_write():
    client = _FakeClient()

    result = asyncio.run(accept_op(client, {"recommendation_log_id": "raw personal text"}))

    assert result["ok"] is False
    assert result["error"] == "invalid recommendation_log_id"
    assert client.requests == []


def test_accept_rejects_well_formed_id_that_does_not_match_latest_recommendation():
    client = _FakeClient()

    result = asyncio.run(
        accept_op(client, {"recommendation_log_id": "fzr_0123456789abcdef"})
    )

    assert result["ok"] is False
    assert result["error"] == "recommendation_log_id is not current"
    assert {request[0] for request in client.requests} == {"GET"}


def test_status_is_read_only_and_exposes_queryable_truth():
    client = _FakeClient()
    client.rows["flowzen_activity"] = [{
        "id": "activity-1",
        "event_type": "recommendation_accepted:fzr_0123456789abcdef",
        "time_window": "morning",
        "hour": 9,
        "created_at": "2026-07-30T09:01:00Z",
    }]

    result = asyncio.run(status_op(client, {}))

    assert result["ok"] is True
    assert result["event_id"] == "rose.status"
    assert result["status"]["latest_checkin"] == {
        "mood": "focused", "energy": 8, "time_window": "morning", "hour": 9,
        "created_at": "2026-07-30T09:00:00Z",
    }
    assert result["status"]["latest_activity"]["status"] == "accepted"
    assert {request[0] for request in client.requests} == {"GET"}


def test_registry_capabilities_resolve_to_real_flowzen_executor():
    caps_path = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
    by_name = {c["capability"]: c for c in yaml.safe_load(caps_path.read_text("utf-8"))}

    for event_id in ("rose.recommend", "rose.accept", "rose.status"):
        target = by_name[event_id]["execution_target"]
        executor = build_executor(target)
        assert isinstance(executor, SupabaseExecutor)
        assert executor.operation == event_id
        assert by_name[event_id]["validator"] == {
            "kind": "rule:flowzen_result", "on_fail": "block"
        }


def test_plan_executor_resolves_flowzen_capability_and_blocks_invalid_result(monkeypatch):
    class _InvalidFlowzenExecutor:
        def call_with_arg(self, *args, **kwargs):
            return {
                "ok": True,
                "result": {"ok": True, "event_id": "rose.recommend", "mutated": False},
                "elapsed_s": 0.0,
                "target": "supabase:rose.recommend",
            }

    monkeypatch.setattr(
        "core.capability_targets.build_executor", lambda target: _InvalidFlowzenExecutor()
    )
    plan = Plan(
        plan_id="flowzen-contract",
        intent="Was empfiehlst du?",
        rationale="Flowzen",
        hops=[HopSpec(step_id="recommend", description="recommend", capability="rose.recommend")],
    )

    caps_path = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
    result = PlanExecutor(
        capability_router=CapabilityRouter(str(caps_path)),
        validator=CapabilityValidator(),
    ).execute(plan)

    assert result["ok"] is False
    assert result["executed"]["recommend"]["contract_pass"] is False
