from pathlib import Path

import pytest
import requests
import yaml

from core.capability_router import CapabilityRouter
from core.capability_validator import CapabilityValidator
from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec


REPO_ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES = REPO_ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml"


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_all_canonical_minibook_events_have_real_brain_targets():
    registry = yaml.safe_load((REPO_ROOT / "config" / "space_agent_registry.yml").read_text())
    canonical_events = set(registry["spaces"]["minibook"]["events"])
    router = CapabilityRouter(CAPABILITIES)

    assert canonical_events == {
        "minibook.discuss",
        "minibook.collaborate",
        "minibook.status",
        "minibook.list_projects",
    }
    for event in canonical_events:
        capability = router.get_capability(event)
        assert capability is not None
        assert capability["execution_target"].startswith("direct:spaces.minibook.")
        assert capability["validator"] == {
            "kind": "rule:minibook_verified_result",
            "on_fail": "block",
        }


def test_status_is_read_only_and_redacts_sensitive_response_fields(monkeypatch):
    from spaces.minibook.tools import minibook_tools

    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response({
            "online": True,
            "api_key": "server-secret",
            "nested": {"authorization": "Bearer leaked-token", "count": 2},
        })

    monkeypatch.setattr(minibook_tools.requests, "request", request)
    result = minibook_tools.execute({
        "event": "minibook.status",
        "base_url": "http://foreign-system.invalid",
    })

    assert calls[0][0] == "GET"
    assert calls[0][1] == "http://127.0.0.1:8800/api/v1/status"
    assert result["ok"] is True
    assert result["truth"] == {"status": "verified", "source": "minibook"}
    assert result["result"]["api_key"] == "[REDACTED]"
    assert result["result"]["nested"]["authorization"] == "[REDACTED]"
    assert "server-secret" not in repr(result)
    assert "leaked-token" not in repr(result)


def test_discuss_posts_only_to_minibook_and_returns_queryable_id(monkeypatch):
    from spaces.minibook.tools import minibook_tools

    seen = {}

    def request(method, url, **kwargs):
        seen.update(method=method, url=url, payload=kwargs.get("json"))
        return _Response({"post_id": "post-42", "status": "created"}, 201)

    monkeypatch.setattr(minibook_tools.requests, "request", request)
    result = minibook_tools.execute({
        "event": "minibook.discuss",
        "topic": "Architecture",
        "project_id": "project-7",
    })

    assert seen["method"] == "POST"
    assert seen["url"].endswith("/api/v1/projects/project-7/posts")
    assert seen["payload"]["type"] == "discussion"
    assert result["result"]["post_id"] == "post-42"
    assert result["truth"]["status"] == "verified"


def test_missing_minibook_infrastructure_fails_closed(monkeypatch):
    from spaces.minibook.tools import minibook_tools

    def request(*args, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(minibook_tools.requests, "request", request)
    result = minibook_tools.execute({"event": "minibook.list_projects"})

    assert result["ok"] is False
    assert result["truth"]["status"] == "unavailable"
    assert result["result"] is None
    assert "connection refused" not in repr(result)


@pytest.mark.parametrize("event", ["minibook.delete", "agentfarm.collaborate"])
def test_target_rejects_non_canonical_or_foreign_mutations(event):
    from spaces.minibook.tools.minibook_tools import execute

    result = execute({"event": event, "topic": "do it"})

    assert result["ok"] is False
    assert result["truth"]["status"] == "rejected"


def test_validator_accepts_only_verified_minibook_contract():
    validator = CapabilityValidator()
    cfg = {"kind": "rule:minibook_verified_result", "on_fail": "block"}

    accepted = validator.validate(
        cfg,
        intent="Minibook status",
        arg={},
        raw_result={"ok": True, "truth": {"status": "verified", "source": "minibook"}},
    )
    rejected = validator.validate(
        cfg,
        intent="Minibook status",
        arg={},
        raw_result={"ok": True, "truth": {"status": "unverified", "source": "local"}},
    )

    assert accepted["verified"] is True
    assert rejected["verified"] is False


def test_plan_executor_keeps_structured_minibook_target_when_agent_is_online(monkeypatch):
    from spaces.minibook.tools import minibook_tools

    router = CapabilityRouter(CAPABILITIES)
    monkeypatch.setenv("MINIBOOK_PROJECT_ID", "project-live")
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: _Response({"agents": [{"name": "brain-knowledge", "id": "a1"}]}),
    )
    monkeypatch.setattr(
        minibook_tools.requests,
        "request",
        lambda *args, **kwargs: _Response({"post_id": "post-live"}, 201),
    )

    executor = PlanExecutor(capability_router=router, validator=CapabilityValidator())
    hop = HopSpec(
        step_id="minibook-1",
        description="discuss Architecture",
        capability="minibook.discuss",
        arg_template="Architecture",
    )
    result = executor._exec_hop(hop, state={})

    assert result.ok is True
    assert result.target == "direct:spaces.minibook.tools.minibook_tools:discuss"
    assert result.contract_pass is True
    assert result.result["result"]["post_id"] == "post-live"
