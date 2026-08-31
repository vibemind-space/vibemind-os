"""Phase 1 — die truth:supabase_edge-Validatoren muessen FEUERN koennen.

`_run_truth_validator` (core/capability_validator.py) bricht zu UNVERIFIED ab,
SOBALD nach der Substitution noch ein "{" in der postcondition steht — es ruft
world_observer dann gar nicht erst auf. Ein Validator, dessen Platzhalter aus
dem Result-String der Operation nie aufloesbar sind, ist deshalb tote Deko:
er kann strukturell NIE VERIFIED/REFUTED liefern und produziert nie ein
Lernsignal.

Dieser Test ruft die ECHTEN ops (auto_link_op, idea_llm_op/link_to_root) mit
einem Fake-Client auf, nimmt deren TATSAECHLICHEN Rueckgabe-String und jagt ihn
durch `_template_postcondition` mit der postcondition aus capabilities.yaml.
Assert: kein "{" ueberlebt — d.h. {result_title} UND {result_title2} loesen auf.
"""
import asyncio
from pathlib import Path

import pytest
import yaml

from core.capability_validator import CapabilityValidator
from core.supabase_ideas_ops import auto_link_op, idea_llm_op

CAPS_PATH = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"


def _postcondition_for(capability: str) -> dict:
    caps = yaml.safe_load(CAPS_PATH.read_text(encoding="utf-8"))
    for c in caps:
        if c.get("capability") == capability:
            return dict((c.get("validator") or {}).get("postcondition") or {})
    raise AssertionError(f"capability {capability!r} not in capabilities.yaml")


class _FakeClient:
    """Minimal stand-in for SupabaseIdeasClient — only what the two ops touch."""

    def __init__(self):
        self.edges_created = []

    async def list_bubbles(self, limit=200):
        return [{"id": "b1", "title": "TestBubble"}]

    async def find_bubble_by_title(self, title):
        return {"id": "b1", "title": "TestBubble"}

    async def get_idea(self, _id):
        return {"id": "b1", "title": "TestBubble"}

    async def list_canvas_nodes_in_bubble(self, bubble_id, limit=200):
        # Titles overlap on the token "cache" -> jaccard clears the 0.30 default
        # threshold, so auto_link_op actually creates an edge.
        return [
            {"id": "n1", "title": "cache warming strategy"},
            {"id": "n2", "title": "cache eviction strategy"},
        ]

    async def find_node_by_title(self, name, bubble_id=None):
        return {"id": "n2", "title": "cache eviction strategy"}

    async def list_edges(self, limit=500):
        return []

    async def create_edge(self, from_id, to_id, edge_type="related"):
        edge = {"id": f"e{len(self.edges_created) + 1}",
                "from_node_id": from_id, "to_node_id": to_id}
        self.edges_created.append(edge)
        return edge


def _resolve(capability: str, result: str, arg: str) -> dict:
    return CapabilityValidator._template_postcondition(
        _postcondition_for(capability), arg, result,
    )


def _unresolved(pc: dict) -> list:
    return [f"{k}={v}" for k, v in pc.items()
            if isinstance(v, str) and "{" in v]


def test_auto_link_result_resolves_both_edge_endpoints():
    client = _FakeClient()
    result = asyncio.run(auto_link_op(client, {"bubble": "TestBubble"}))
    assert client.edges_created, "fixture must actually create an edge"
    pc = _resolve("idea_auto_link", result, "TestBubble")
    assert not _unresolved(pc), (
        f"idea_auto_link truth:supabase_edge can never fire — placeholders "
        f"unresolved {_unresolved(pc)} from op result {result!r}"
    )


def test_link_to_root_result_resolves_both_edge_endpoints():
    client = _FakeClient()
    params = {"idea_id": "cache eviction strategy", "bubble": "TestBubble",
              "_capability": "idea_link_to_root"}
    result = asyncio.run(idea_llm_op(client, params))
    assert client.edges_created, "fixture must actually create an edge"
    pc = _resolve("idea_link_to_root", result, "cache eviction strategy")
    assert not _unresolved(pc), (
        f"idea_link_to_root truth:supabase_edge can never fire — placeholders "
        f"unresolved {_unresolved(pc)} from op result {result!r}"
    )
