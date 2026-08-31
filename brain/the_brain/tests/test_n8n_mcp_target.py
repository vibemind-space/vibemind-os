from __future__ import annotations

import json

import pytest

from core.capability_targets import N8nMcpExecutor, resolve_registry_execution_target
from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec


EXPECTED_TOOLS = {
    "n8n.generate": "n8n_generate_workflow",
    "n8n.list": "n8n_list_workflows",
    "n8n.status": "n8n_health_check",
    "n8n.activate": "n8n_update_partial_workflow",
    "n8n.deactivate": "n8n_update_partial_workflow",
    "n8n.delete": "n8n_delete_workflow",
    "n8n.execute": "n8n_test_workflow",
    "n8n.describe": "n8n_get_workflow",
}


class _Response:
    status_code = 200
    headers = {"content-type": "application/json"}

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_registry_resolves_all_n8n_events_to_mcp_targets():
    for event, tool in EXPECTED_TOOLS.items():
        assert resolve_registry_execution_target(event) == f"n8n-mcp:{event}"
        assert N8nMcpExecutor(f"n8n-mcp:{event}").tool == tool


@pytest.mark.parametrize(
    "event",
    ["n8n.generate", "n8n.activate", "n8n.deactivate", "n8n.delete", "n8n.execute"],
)
def test_mutating_operations_require_explicit_authorization(monkeypatch, event):
    monkeypatch.setenv("N8N_MCP_URL", "http://n8n.invalid/mcp-server/http")
    executor = N8nMcpExecutor(f"n8n-mcp:{event}")

    result = executor.call(name="daily-sync")

    assert result["ok"] is False
    assert "authorization" in result["error"].lower()


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        ("n8n.activate", {"authorized": True}),
        ("n8n.deactivate", {"authorized": True}),
        ("n8n.delete", {"authorized": True}),
        ("n8n.execute", {"authorized": True}),
        ("n8n.describe", {}),
    ],
)
def test_workflow_operations_require_stable_identity(monkeypatch, event, payload):
    monkeypatch.setenv("N8N_MCP_URL", "http://n8n.invalid/mcp-server/http")
    executor = N8nMcpExecutor(f"n8n-mcp:{event}")

    result = executor.call(**payload)

    assert result["ok"] is False
    assert "workflow identity" in result["error"].lower()


def test_mcp_call_uses_registry_tool_and_returns_redacted_evidence(monkeypatch):
    monkeypatch.setenv("N8N_MCP_URL", "http://n8n.invalid/mcp-server/http")
    monkeypatch.setenv("N8N_MCP_TOKEN", "runtime-secret")
    captured = {}

    def _post(url, *, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return _Response({
            "jsonrpc": "2.0",
            "id": json["id"],
            "result": {
                "content": [{"type": "text", "text": json_module.dumps({
                    "id": "wf-17", "name": "daily-sync", "apiKey": "leak-me",
                    "note": "Bearer runtime-secret",
                })}],
            },
        })

    json_module = json
    monkeypatch.setattr("core.capability_targets.requests.post", _post)

    result = N8nMcpExecutor("n8n-mcp:n8n.describe").call(workflow_id="wf-17")

    assert result["ok"] is True
    assert captured["json"]["method"] == "tools/call"
    assert captured["json"]["params"]["name"] == "n8n_get_workflow"
    assert captured["json"]["params"]["arguments"]["workflow_id"] == "wf-17"
    assert captured["headers"]["Authorization"] == "Bearer runtime-secret"
    evidence = result["result"]
    assert evidence["event"] == "n8n.describe"
    assert evidence["tool"] == "n8n_get_workflow"
    assert evidence["workflow"] == {"id": "wf-17", "name": "daily-sync"}
    assert "leak-me" not in json.dumps(evidence)
    assert "runtime-secret" not in json.dumps(evidence)
    assert evidence["provider_backed"] is True


def test_missing_mcp_infrastructure_fails_closed(monkeypatch):
    monkeypatch.delenv("N8N_MCP_URL", raising=False)

    result = N8nMcpExecutor("n8n-mcp:n8n.status").call()

    assert result["ok"] is False
    assert "n8n_mcp_url" in result["error"].lower()
    assert "provider_backed" not in result


def test_plan_executor_routes_canonical_n8n_event_to_mcp_target(monkeypatch):
    captured = {}

    class _Executor:
        def call_with_arg(self, arg, arg_kwarg=None, extra_params=None):
            return {"ok": True, "result": {"provider_backed": True}, "target": captured["target"]}

    def _build(target):
        captured["target"] = target
        return _Executor()

    monkeypatch.setattr("core.capability_targets.build_executor", _build)
    hop = HopSpec(step_id="n8n-list", description="List workflows", capability="n8n.list")

    result = PlanExecutor()._exec_hop(hop, {}, {"plan_id": "plan-n8n"})

    assert result.ok is True
    assert result.target == "n8n-mcp:n8n.list"
    assert result.result == {"provider_backed": True}


def test_n8n_mcp_target_is_not_replaced_by_openfang_agent_routing(monkeypatch):
    captured = {}

    class _Registry:
        def get_event_agent(self, event):
            return "brain-n8n"

    class _AgentResponse:
        ok = True

        def json(self):
            return [{"name": "brain-n8n"}]

    class _Executor:
        def call_with_arg(self, arg, arg_kwarg=None, extra_params=None):
            return {"ok": True, "result": {}, "target": captured["target"]}

    def _build(target):
        captured["target"] = target
        return _Executor()

    monkeypatch.setattr("core.agent_yaml_registry.get_registry", lambda: _Registry())
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _AgentResponse())
    monkeypatch.setattr("core.capability_targets.build_executor", _build)
    hop = HopSpec(step_id="n8n-list", description="List workflows", capability="n8n.list")

    result = PlanExecutor()._exec_hop(hop, {}, {"plan_id": "plan-n8n"})

    assert result.ok is True
    assert captured["target"] == "n8n-mcp:n8n.list"
