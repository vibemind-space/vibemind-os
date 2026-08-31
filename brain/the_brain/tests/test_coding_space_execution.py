from pathlib import Path
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "brain" / "the_brain"))

from core.capability_router import CapabilityRouter
from core.capability_targets import CodingEngineExecutor
from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_coding_engine_status_health_checks_then_uses_get(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/api/health"):
            return _Response({"healthy": True, "services": {"api": True}})
        return _Response({"state": {"status": "idle"}})

    monkeypatch.setattr("core.capability_targets.requests.request", request)
    executor = CodingEngineExecutor("coding-engine:GET:/api/status")

    result = executor.call()

    assert result["ok"] is True
    assert [(method, url) for method, url, _ in calls] == [
        ("GET", "http://127.0.0.1:8000/api/health"),
        ("GET", "http://127.0.0.1:8000/api/status"),
    ]


def test_coding_engine_fails_closed_when_health_is_unhealthy(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response({"healthy": False, "services": {"api": True, "vnc": False}})

    monkeypatch.setattr("core.capability_targets.requests.request", request)
    executor = CodingEngineExecutor("coding-engine:POST:/api/start")

    result = executor.call(description="write hello.py")

    assert result["ok"] is False
    assert "unhealthy" in result["error"].lower()
    assert len(calls) == 1


def test_coding_engine_start_wraps_description_as_requirements(monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/api/health"):
            return _Response({"healthy": True, "services": {"api": True}})
        return _Response({"message": "engine started"})

    monkeypatch.setattr("core.capability_targets.requests.request", request)
    executor = CodingEngineExecutor("coding-engine:POST:/api/start")

    result = executor.call(description="write hello.py")

    assert result["ok"] is True
    assert calls[1][2]["json"] == {
        "requirements_json": {"description": "write hello.py"}
    }


def test_all_coding_events_route_to_the_health_checked_executor():
    registry = yaml.safe_load((ROOT / "config" / "space_agent_registry.yml").read_text())
    events = registry["spaces"]["coding"]["events"]
    expected = {
        "code.generate": "coding-engine:POST:/api/start",
        "code.modify": "coding-engine:POST:/api/start",
        "code.status": "coding-engine:GET:/api/status",
        "code.show": "coding-engine:GET:/api/logs",
        "code.preview.start": "coding-engine:POST:/api/preview/create",
        "code.preview.stop": "coding-engine:POST:/api/preview/{project_id}/stop",
        "code.list": "coding-engine:GET:/api/preview/",
        "code.cancel": "coding-engine:POST:/api/stop",
    }

    assert {event: config["tool"] for event, config in events.items()} == expected

    router = CapabilityRouter(ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml")
    for event, target in expected.items():
        match = router.route(event)
        assert match is not None, event
        assert match.execution_target == target, event


@pytest.mark.parametrize(
    ("target", "payload", "expected_url"),
    [
        (
            "coding-engine:POST:/api/preview/{project_id}/stop",
            {"project_id": "demo"},
            "http://127.0.0.1:8000/api/preview/demo/stop",
        ),
    ],
)
def test_coding_engine_renders_path_parameters(monkeypatch, target, payload, expected_url):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/api/health"):
            return _Response({"healthy": True, "services": {"api": True}})
        return _Response({"status": "stopped"})

    monkeypatch.setattr("core.capability_targets.requests.request", request)

    result = CodingEngineExecutor(target).call(**payload)

    assert result["ok"] is True
    assert calls[1][1] == expected_url
    assert "project_id" not in calls[1][2]["json"]


def test_plan_executor_keeps_coding_engine_target_when_registry_agent_is_live(monkeypatch):
    events = []
    built_targets = []

    class Registry:
        def get_event_agent(self, event_id):
            events.append(event_id)
            return "brain-coder"

    class Executor:
        def call_with_arg(self, arg, arg_kwarg=None, extra_params=None):
            return {"ok": True, "result": {"state": {"status": "idle"}}}

    monkeypatch.setattr("core.agent_yaml_registry.get_registry", lambda: Registry())
    monkeypatch.setattr(
        "core.capability_targets.build_executor",
        lambda target: built_targets.append(target) or Executor(),
    )
    monkeypatch.setattr(
        "core.plan_executor.PlanExecutor._capture_kg_hits", lambda *args: []
    )

    hop = HopSpec(
        step_id="status",
        description="code.status",
        capability="code_status",
        execution_target="coding-engine:GET:/api/status",
    )
    result = PlanExecutor()._exec_hop(hop, {})

    assert result.ok is True
    assert events == ["code.status"]
    assert built_targets == ["coding-engine:GET:/api/status"]
