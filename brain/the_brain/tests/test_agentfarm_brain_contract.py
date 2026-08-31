"""AgentFarm space contract must stay canonical and fail closed.

The historical ``spaces/autogen`` implementation was removed and its team/run
state lived only in memory.  Until a versioned runtime source is present, the
Brain may understand AgentFarm intents but must not advertise an executable
target or route them to generic database tools.
"""

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.capability_router import CapabilityRouter


ROOT = Path(__file__).resolve().parents[3]
SPACE_REGISTRY = ROOT / "config" / "space_agent_registry.yml"
CAPABILITIES = Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml"
AGENT_MANIFEST = (
    Path(__file__).resolve().parents[1] / "configs" / "agents" / "brain-orchestrator.yaml"
)

OPERATIONS = {
    "create_team",
    "run",
    "status",
    "list_teams",
    "stop",
    "results",
    "list_templates",
    "collaborate",
}


def _space_contract():
    registry = yaml.safe_load(SPACE_REGISTRY.read_text(encoding="utf-8"))
    return registry["spaces"]["agentfarm"]


def _agentfarm_capabilities():
    capabilities = yaml.safe_load(CAPABILITIES.read_text(encoding="utf-8"))
    return {
        item["capability"]: item
        for item in capabilities
        if item.get("space") == "agentfarm"
    }


def test_agentfarm_is_canonical_with_autogen_as_legacy_alias():
    contract = _space_contract()

    assert contract["aliases"] == ["autogen"]
    assert contract["prefixes"] == ["agentfarm.", "autogen."]


def test_agentfarm_registry_is_disabled_until_runtime_source_exists():
    contract = _space_contract()

    assert contract["enabled"] is False
    assert contract["runtime"]["status"] == "blocked"
    source_path = ROOT / contract["runtime"]["source_path"]
    assert not source_path.exists(), "enable only after the runtime source is versioned"


def test_agentfarm_events_name_real_operations_not_generic_database_tools():
    events = _space_contract()["events"]

    assert set(events) == {f"agentfarm.{operation}" for operation in OPERATIONS}
    assert {event["operation"] for event in events.values()} == OPERATIONS
    assert all("tool" not in event for event in events.values())


def test_brain_contract_has_no_execution_target_without_runtime_artifacts():
    capabilities = _agentfarm_capabilities()

    assert set(capabilities) == {f"agentfarm_{operation}" for operation in OPERATIONS}
    for capability in capabilities.values():
        assert capability["enabled"] is False
        assert not capability.get("execution_target")
        assert capability["runtime_blocker"] == "missing_versioned_agentfarm_source"


def test_disabled_capabilities_are_not_routable(tmp_path):
    registry = tmp_path / "capabilities.yaml"
    registry.write_text(
        yaml.safe_dump(
            [
                {
                    "capability": "agentfarm_create_team",
                    "description": "blocked until runtime exists",
                    "enabled": False,
                    "match_patterns": ["create agent team"],
                    "agents": {"primary": ["vibemind"]},
                }
            ]
        ),
        encoding="utf-8",
    )

    router = CapabilityRouter(registry)

    assert router.route("create agent team alpha") is None


def test_removed_agentfarm_worker_does_not_claim_events():
    manifest = yaml.safe_load(AGENT_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["events"] == []
    assert manifest["default_namespace"] == ""
    assert "runtime source is missing" in manifest["notes"]
