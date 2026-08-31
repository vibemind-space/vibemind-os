from pathlib import Path

import yaml

from core.space_contract import (
    CANONICAL_ALIASES,
    load_space_contract,
    normalize_space_id,
    registry_health,
)
from web.routers.introspection import space_registry_health
from spaces._navigator.registry import resolve_alias


ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "config" / "space_agent_registry.yml"
CAPABILITIES = ROOT / "brain" / "the_brain" / "data" / "capabilities.yaml"


def test_aliases_normalize_to_registry_ids():
    contract = load_space_contract(REGISTRY)

    assert CANONICAL_ALIASES == {
        "autogen": "agentfarm",
        "rowboat": "roarboot",
        "shuttles": "bubbles",
    }
    assert normalize_space_id(" AutoGen ", contract) == "agentfarm"
    assert normalize_space_id("rowboat", contract) == "roarboot"
    assert normalize_space_id("shuttles", contract) == "bubbles"
    assert normalize_space_id("coding", contract) == "coding"
    assert normalize_space_id("unknown", contract) is None


def test_registry_contract_owns_event_to_space_mapping():
    contract = load_space_contract(REGISTRY)

    assert contract.event_space_map["agentfarm.run"] == "agentfarm"
    assert contract.event_space_map["roarboot.query"] == "roarboot"
    assert contract.event_space_map["bubble.promote"] == "bubbles"
    assert set(contract.space_ids) == set(contract.spaces)

    from core.space_routing_head import EVENT_SPACE_MAP, SPACE_NAMES

    assert EVENT_SPACE_MAP == contract.event_space_map
    assert SPACE_NAMES == list(contract.space_ids)


def test_navigator_returns_canonical_ids_for_legacy_names():
    assert resolve_alias("autogen") == "agentfarm"
    assert resolve_alias("rowboat") == "roarboot"
    assert resolve_alias("shuttles") == "bubbles"


def test_registry_health_checks_navigator_routing_and_executor_kinds():
    contract = load_space_contract(REGISTRY)
    capabilities = yaml.safe_load(CAPABILITIES.read_text(encoding="utf-8"))
    health = registry_health(contract, capabilities=capabilities)

    assert health["status"] == "ok"
    assert health["canonical_space_count"] == len(contract.space_ids)
    assert health["event_count"] == len(contract.event_space_map)
    assert health["issues"] == []
    assert set(health["executor_kinds_used"]) <= set(health["executor_kinds_supported"])


def test_space_registry_health_is_exposed_as_json_response():
    response = space_registry_health()

    assert response.status_code == 200
    payload = bytes(response.body).decode("utf-8")
    assert '"status":"ok"' in payload
    assert '"canonical_space_count":13' in payload
