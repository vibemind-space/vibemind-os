from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from core.capability_targets import MiroFishExecutor, build_executor
from core.capability_executor import extract_arg
from core.capability_validator import CapabilityValidator


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_EVENTS = {
    "mirofish.simulate",
    "mirofish.predict",
    "mirofish.graph.build",
    "mirofish.graph.search",
    "mirofish.status",
    "mirofish.evaluate",
    "mirofish.interview",
}


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def test_build_executor_supports_mirofish_targets() -> None:
    executor = build_executor("mirofish:graph.build")

    assert isinstance(executor, MiroFishExecutor)
    assert executor.operation == "graph.build"


def test_graph_build_returns_a_validated_job_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_request(method: str, url: str, **kwargs: object) -> _Response:
        captured.update(method=method, url=url, **kwargs)
        return _Response({
            "success": True,
            "data": {
                "project_id": "proj_abc123",
                "task_id": "task_def456",
                "message": "Graph build task started",
            },
        })

    monkeypatch.setattr("core.capability_targets.requests.request", fake_request)
    executor = MiroFishExecutor("mirofish:graph.build", base_url="http://mirofish:5001")

    result = executor.call(project_id="proj_abc123", graph_name="Market graph")

    assert result["ok"] is True
    assert result["result"] == {
        "operation": "graph.build",
        "state": "queued",
        "job_id": "task_def456",
        "project_id": "proj_abc123",
        "graph_id": None,
        "simulation_id": None,
        "model_id": None,
        "evidence": {
            "service": "mirofish",
            "endpoint": "/api/graph/build",
            "response_success": True,
        },
    }
    assert captured["method"] == "POST"
    assert captured["url"] == "http://mirofish:5001/api/graph/build"


def test_simulate_fails_closed_without_simulation_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("transport must not run without identity")

    monkeypatch.setattr("core.capability_targets.requests.request", unexpected_request)
    result = MiroFishExecutor("mirofish:simulate").call(model="forecast-v1")

    assert result["ok"] is False
    assert "simulation_id" in result["error"]


def test_backend_success_without_expected_job_identity_is_not_live_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.capability_targets.requests.request",
        lambda *args, **kwargs: _Response({"success": True, "data": {}}),
    )

    result = MiroFishExecutor("mirofish:predict").call(simulation_id="sim_abc123")

    assert result["ok"] is False
    assert "task_id" in result["error"] or "report_id" in result["error"]


def test_graph_search_preserves_graph_identity_and_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.capability_targets.requests.request",
        lambda *args, **kwargs: _Response({
            "success": True,
            "data": {"items": [{"uuid": "node-1", "name": "Demand"}]},
        }),
    )

    result = MiroFishExecutor("mirofish:graph.search").call(
        graph_id="mirofish_graph_123",
        query="demand signals",
    )

    assert result["ok"] is True
    assert result["result"]["graph_id"] == "mirofish_graph_123"
    assert result["result"]["state"] == "completed"
    assert result["result"]["evidence"]["response_success"] is True


def test_registry_uses_real_mirofish_targets_and_identity_contracts() -> None:
    registry = yaml.safe_load(
        (REPO_ROOT / "config" / "space_agent_registry.yml").read_text(encoding="utf-8")
    )
    events = registry["spaces"]["mirofish"]["events"]

    assert set(events) == EXPECTED_EVENTS
    assert {spec["tool"] for spec in events.values()} == {
        "mirofish:simulate",
        "mirofish:predict",
        "mirofish:graph.build",
        "mirofish:graph.search",
        "mirofish:status",
        "mirofish:evaluate",
        "mirofish:interview",
    }
    assert events["mirofish.simulate"]["required_params"] == ["simulation_id"]
    assert events["mirofish.graph.build"]["required_params"] == ["project_id"]
    assert events["mirofish.graph.search"]["required_params"] == ["graph_id", "query"]
    assert events["mirofish.interview"]["required_params"] == [
        "simulation_id", "agent_id", "prompt",
    ]


def test_brain_capability_catalog_routes_all_mirofish_events_to_real_executor() -> None:
    capabilities = yaml.safe_load(
        (REPO_ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml").read_text(
            encoding="utf-8"
        )
    )
    mirofish = {
        item["capability"]: item
        for item in capabilities
        if str(item.get("capability", "")).startswith("mirofish.")
    }

    assert set(mirofish) == EXPECTED_EVENTS
    assert all(
        item["execution_target"] == item["capability"].replace("mirofish.", "mirofish:", 1)
        for item in mirofish.values()
    )
    assert all(item["validator"] == {"kind": "rule:mirofish_evidence", "on_fail": "block"}
               for item in mirofish.values())
    graph_id = "9f4d91fd-3126-4b98-a39f-2f70e3ff6248"
    assert extract_arg(
        f"MiroFish graph search {graph_id} for demand",
        mirofish["mirofish.graph.search"]["result_arg_extractor"],
    ) == graph_id


def test_mirofish_validator_requires_identity_and_transport_evidence() -> None:
    validator = CapabilityValidator()
    config = {"kind": "rule:mirofish_evidence", "on_fail": "block"}

    valid = validator.validate(
        config,
        intent="build graph",
        arg="proj_abc123",
        raw_result={
            "operation": "graph.build",
            "state": "queued",
            "job_id": "task_def456",
            "project_id": "proj_abc123",
            "evidence": {
                "service": "mirofish",
                "endpoint": "/api/graph/build",
                "response_success": True,
            },
        },
    )
    invalid = validator.validate(
        config,
        intent="build graph",
        arg="proj_abc123",
        raw_result={"operation": "graph.build", "state": "queued"},
    )

    assert valid["valid"] is True
    assert invalid["valid"] is False


def test_interview_derives_agent_and_prompt_from_canonical_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_request(method: str, url: str, **kwargs: object) -> _Response:
        captured.update(method=method, url=url, **kwargs)
        return _Response({
            "success": True,
            "data": {"agent_id": 7, "result": {"response": "Demand will rise."}},
        })

    monkeypatch.setattr("core.capability_targets.requests.request", fake_request)
    result = MiroFishExecutor("mirofish:interview").call(
        simulation_id="sim_abc123",
        _intent="MiroFish interview agent 7 about demand next quarter",
    )

    assert result["ok"] is True
    assert captured["json"]["agent_id"] == 7
    assert captured["json"]["prompt"].startswith("MiroFish interview")
