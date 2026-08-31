from pathlib import Path

import pytest

from core.agent_yaml_registry import AgentYamlRegistry
from core.desktop_orchestration import DesktopOrchestration
from core.plan_executor import PlanExecutor
from core.plan_schema import HopSpec, Plan
from core.tool_scope_selector import _CORE_TOOLS


ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "config" / "space_agent_registry.yml"


def test_canonical_registry_drives_all_desktop_event_families():
    orchestration = DesktopOrchestration(REGISTRY_PATH)
    registry = AgentYamlRegistry(configs_dir=ROOT / "brain" / "the_brain" / "configs" / "agents")

    for event_id in (
        "desktop.screenshot",
        "web.fetch",
        "messaging.send",
        "openclaw.browse",
        "openclaw.message.send",
    ):
        route = orchestration.resolve_event(event_id)
        assert route.space == "desktop"
        assert route.agent == "brain-desktop"
        assert registry.get_event_agent(event_id) == "brain-desktop"


@pytest.mark.parametrize(
    ("event_id", "requires_confirmation"),
    [
        ("desktop.screenshot", False),
        ("web.fetch", False),
        ("desktop.click", True),
        ("desktop.type", True),
        ("messaging.send", True),
        ("openclaw.message.send", True),
        ("openclaw.fill_form", True),
    ],
)
def test_mutating_events_fail_closed_without_confirmation(event_id, requires_confirmation):
    orchestration = DesktopOrchestration(REGISTRY_PATH)
    route = orchestration.resolve_event(event_id)
    assert route.requires_confirmation is requires_confirmation
    assert orchestration.can_execute(event_id, confirmed=False) is (not requires_confirmation)


def test_openfang_desktop_agents_have_narrow_visible_tool_profiles():
    assert "handoff_action" in _CORE_TOOLS["skill-coordinator"]
    assert _CORE_TOOLS["openclaw-visible"] == [
        "handoff_action",
        "handoff_read_screen",
        "vision_analyze",
        "app_launch_or_focus",
    ]


def test_capability_intent_resolves_to_specific_safety_contract():
    orchestration = DesktopOrchestration(REGISTRY_PATH)
    assert orchestration.resolve_capability("desktop_skill", "take a desktop screenshot").event_id == "desktop.screenshot"
    assert orchestration.resolve_capability("desktop_skill", "click the OK button").event_id == "desktop.task"
    assert orchestration.resolve_capability("browser_automation", "open https://example.com").event_id == "openclaw.browse"
    assert orchestration.resolve_capability("browser_automation", "fill the login form").event_id == "openclaw.fill_form"


def test_plan_executor_blocks_mutating_desktop_hop_before_live_dispatch():
    plan = Plan(
        plan_id="desktop-confirmation-test",
        intent="click the OK button",
        rationale="test",
        hops=[HopSpec(
            step_id="click",
            description="click the OK button",
            capability="desktop_skill",
            execution_target="openfang:skill-coordinator",
        )],
    )
    result = PlanExecutor().execute(plan)
    hop = result["executed"]["click"]
    assert result["ok"] is False
    assert hop["error"] == "confirmation required for mutating desktop event 'desktop.task'"
    assert hop["contract_pass"] is False
