from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from fastapi.testclient import TestClient

from core.capability_router import CapabilityRouter
from core.capability_targets import build_executor
from web.brain_server import create_app


ROOT = Path(__file__).resolve().parents[3]
CAPABILITIES = ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml"
SPACE_REGISTRY = ROOT / "config" / "space_agent_registry.yml"


def test_research_events_have_brain_execution_targets():
    registry = yaml.safe_load(SPACE_REGISTRY.read_text(encoding="utf-8"))
    events = registry["spaces"]["research"]["events"]
    assert set(events) >= {
        "research.web",
        "research.scrape",
        "research.summarize",
        "research.to_idea",
    }

    router = CapabilityRouter(CAPABILITIES)
    expected = {
        "research_web": "research:web",
        "research_scrape": "research:scrape",
        "research_summarize": "research:summarize",
        "research_to_idea": "research:to_idea",
    }
    for capability, target in expected.items():
        detail = router.get_capability(capability)
        assert detail is not None
        assert detail["execution_target"] == target


def test_research_target_returns_sources_and_tool_evidence():
    executor = build_executor("research:web")
    agent_result = {
        "ok": True,
        "result": {
            "response": "Verified result from https://example.test/report",
            "tool_calls": [
                {"tool": "fetch", "input": {"url": "https://example.test/report"}}
            ],
        },
    }
    with patch.object(executor, "_agent", Mock(call=Mock(return_value=agent_result))):
        result = executor.call(query="evidence based topic")

    assert result["ok"] is True
    assert result["result"]["sources"] == ["https://example.test/report"]
    assert result["result"]["evidence"]["tool_calls"][0]["tool"] == "fetch"


def test_research_target_fails_closed_without_external_tool_evidence():
    executor = build_executor("research:scrape")
    agent_result = {
        "ok": True,
        "result": {"response": "plausible but unverified", "tool_calls": []},
    }
    with patch.object(executor, "_agent", Mock(call=Mock(return_value=agent_result))):
        result = executor.call(url="https://example.test")

    assert result["ok"] is False
    assert "tool evidence" in result["error"]


def test_to_idea_requires_persisted_queryable_artifact_evidence():
    executor = build_executor("research:to_idea")
    agent_result = {
        "ok": True,
        "result": {
            "response": "Read https://example.test/source but did not save it",
            "tool_calls": [{"tool": "fetch", "input": {"url": "https://example.test/source"}}],
        },
    }
    with patch.object(executor, "_agent", Mock(call=Mock(return_value=agent_result))):
        result = executor.call(query="persist this")

    assert result["ok"] is False
    assert "persisted idea evidence" in result["error"]


def test_research_health_is_false_when_external_infrastructure_is_down():
    executor = build_executor("research:web")
    failed = Mock()
    failed.raise_for_status.side_effect = RuntimeError("offline")
    with patch("spaces.research.execution_target.requests.get", return_value=failed):
        health = executor.health_check()

    assert health["ok"] is False
    assert health["components"]["openfang"]["ok"] is False
    assert health["components"]["qdrant"]["ok"] is False


def test_research_health_is_queryable_from_brain_api():
    reported = {"ok": True, "components": {"openfang": {"ok": True}, "qdrant": {"ok": True}}}
    with patch("spaces.research.execution_target.ResearchTarget.health_check", return_value=reported):
        response = TestClient(create_app(testing=True)).get("/api/research/health")

    assert response.status_code == 200
    assert response.json() == reported
