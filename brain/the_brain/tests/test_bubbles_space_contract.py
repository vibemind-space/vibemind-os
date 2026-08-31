"""Canonical bubbles space and its legacy shuttles input alias."""

import asyncio
from pathlib import Path

import yaml

from core.capability_targets import SupabaseExecutor
from core.intent_envelope import build_envelope
from core.supabase_ideas_client import SupabaseIdeasClient


ROOT = Path(__file__).resolve().parents[3]
CAPS_PATH = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"


def _capability(name: str) -> dict:
    capabilities = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    return next(cap for cap in capabilities if cap["capability"] == name)


def test_registry_declares_shuttles_as_bubbles_input_alias_only():
    registry = yaml.safe_load(
        (ROOT / "config" / "space_agent_registry.yml").read_text(encoding="utf-8")
    )
    spaces = registry["spaces"]

    assert spaces["bubbles"]["aliases"] == ["shuttles"]
    assert "shuttles" not in spaces


def test_intent_envelope_normalizes_legacy_shuttles_override():
    envelope = build_envelope(
        event_id="bubble.list",
        params={},
        space_override="shuttles",
    )

    assert envelope["space"] == "bubbles"
    assert "shuttles" not in str(envelope)


class _PromoteClient:
    def __init__(self) -> None:
        self.promoted = []

    async def find_bubble_by_title(self, title):
        return {
            "id": "bubble-1",
            "title": title,
            "description": "Canonical bubble",
            "score": 82,
            "status": "scored",
        }

    async def get_idea(self, _idea_id):
        return None

    async def promote_bubble(self, bubble):
        self.promoted.append(bubble)
        return {"id": "project-1", "name": bubble["title"]}


def test_promote_uses_real_supabase_project_write_and_returns_queryable_id():
    from core.supabase_ideas_ops import bubble_promote_op

    client = _PromoteClient()

    result = asyncio.run(
        bubble_promote_op(client, {"bubble_name": "Launch Plan"})
    )

    assert client.promoted == [
        {
            "id": "bubble-1",
            "title": "Launch Plan",
            "description": "Canonical bubble",
            "score": 82,
            "status": "scored",
        }
    ]
    assert result == "Bubble 'Launch Plan' promoted to project (id=project-1)."


def test_promote_is_wired_to_supabase_with_project_truth_validation():
    capability = _capability("bubble_promote")

    assert capability["execution_target"] == "supabase:bubble.promote"
    assert capability["validator"] == {
        "kind": "truth:supabase_row",
        "on_fail": "report",
        "postcondition": {
            "check": "supabase_row",
            "table": "projects",
            "match": "id=eq.{result_id}",
            "expect": "present",
        },
    }
    assert "bubble.promote" in SupabaseExecutor.OPERATIONS


class _RecordingSupabaseClient(SupabaseIdeasClient):
    def __init__(self) -> None:
        super().__init__(url="http://supabase.invalid", anon_key="anon")
        self.requests = []

    async def _request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if method == "POST" and path == "/projects":
            return [{**kwargs["json"], "id": "project-1"}]
        if method == "PATCH" and path == "/ideas":
            return [{"id": "bubble-1", **kwargs["json"]}]
        raise AssertionError(f"unexpected request: {method} {path}")


def test_supabase_promotion_persists_project_then_links_canonical_bubble():
    client = _RecordingSupabaseClient()
    bubble = {
        "id": "bubble-1",
        "title": "Launch Plan",
        "description": "Canonical bubble",
        "score": 82,
    }

    project = asyncio.run(client.promote_bubble(bubble))

    assert project["id"] == "project-1"
    assert [(method, path) for method, path, _ in client.requests] == [
        ("POST", "/projects"),
        ("PATCH", "/ideas"),
    ]
    project_payload = client.requests[0][2]["json"]
    assert project_payload["from_idea_id"] == "bubble-1"
    assert project_payload["metadata"]["source_space"] == "bubbles"
    assert client.requests[1][2]["json"] == {
        "status": "promoted",
        "promoted_to_project_id": "project-1",
    }
