"""Test agent cooldown manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_cooldown_manager import AgentCooldownManager


def test_start_cooldown():
    cm = AgentCooldownManager()
    cid = cm.start_cooldown("agent-1", "deploy", duration_seconds=60.0)
    assert len(cid) > 0
    assert cid.startswith("acm-")
    print("OK: start cooldown")


def test_is_cooled_down_active():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy", duration_seconds=3600.0)
    assert cm.is_cooled_down("agent-1", "deploy") is False  # still in cooldown
    print("OK: is cooled down active")


def test_is_cooled_down_expired():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy", duration_seconds=0.0)  # instant expire
    assert cm.is_cooled_down("agent-1", "deploy") is True  # cooldown expired
    print("OK: is cooled down expired")


def test_is_cooled_down_no_cooldown():
    cm = AgentCooldownManager()
    assert cm.is_cooled_down("agent-1", "deploy") is True  # no cooldown = can proceed
    print("OK: is cooled down no cooldown")


def test_get_remaining():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy", duration_seconds=3600.0)
    remaining = cm.get_remaining("agent-1", "deploy")
    assert remaining > 3500.0
    assert cm.get_remaining("agent-1", "nonexistent") == 0.0
    print("OK: get remaining")


def test_cancel_cooldown():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy", duration_seconds=3600.0)
    assert cm.cancel_cooldown("agent-1", "deploy") is True
    assert cm.cancel_cooldown("agent-1", "nonexistent") is False
    assert cm.is_cooled_down("agent-1", "deploy") is True
    print("OK: cancel cooldown")


def test_get_active_cooldowns():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy", duration_seconds=3600.0)
    cm.start_cooldown("agent-1", "build", duration_seconds=3600.0)
    cm.start_cooldown("agent-1", "expired", duration_seconds=0.0)
    active = cm.get_active_cooldowns("agent-1")
    assert len(active) == 2  # expired one excluded
    print("OK: get active cooldowns")


def test_get_cooldown_count():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy")
    cm.start_cooldown("agent-2", "build")
    assert cm.get_cooldown_count() == 2
    assert cm.get_cooldown_count("agent-1") == 1
    print("OK: get cooldown count")


def test_list_agents():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy")
    cm.start_cooldown("agent-2", "build")
    agents = cm.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    cm = AgentCooldownManager()
    fired = []
    cm.on_change("mon", lambda a, d: fired.append(a))
    cm.start_cooldown("agent-1", "deploy")
    assert len(fired) >= 1
    assert cm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy")
    stats = cm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cm = AgentCooldownManager()
    cm.start_cooldown("agent-1", "deploy")
    cm.reset()
    assert cm.get_cooldown_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Cooldown Manager Tests ===\n")
    test_start_cooldown()
    test_is_cooled_down_active()
    test_is_cooled_down_expired()
    test_is_cooled_down_no_cooldown()
    test_get_remaining()
    test_cancel_cooldown()
    test_get_active_cooldowns()
    test_get_cooldown_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
