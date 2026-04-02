"""Tests for AgentFeatureFlag service."""

import sys
sys.path.insert(0, ".")

from src.services.agent_feature_flag import AgentFeatureFlag


def test_set_flag():
    svc = AgentFeatureFlag()
    flag_id = svc.set_flag("agent-1", "dark_mode")
    assert flag_id.startswith("aff-"), f"Expected aff- prefix, got {flag_id}"
    assert len(flag_id) > 4
    print("  test_set_flag PASSED")


def test_is_enabled():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "dark_mode", enabled=True)
    assert svc.is_enabled("agent-1", "dark_mode") is True
    svc.set_flag("agent-1", "dark_mode", enabled=False)
    assert svc.is_enabled("agent-1", "dark_mode") is False
    print("  test_is_enabled PASSED")


def test_is_enabled_default():
    svc = AgentFeatureFlag()
    assert svc.is_enabled("agent-1", "nonexistent") is False
    print("  test_is_enabled_default PASSED")


def test_get_flags():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "dark_mode", enabled=True)
    svc.set_flag("agent-1", "beta", enabled=False)
    flags = svc.get_flags("agent-1")
    assert flags == {"dark_mode": True, "beta": False}, f"Got {flags}"
    # empty agent
    assert svc.get_flags("agent-999") == {}
    print("  test_get_flags PASSED")


def test_remove_flag():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "dark_mode")
    assert svc.remove_flag("agent-1", "dark_mode") is True
    assert svc.remove_flag("agent-1", "dark_mode") is False
    assert svc.is_enabled("agent-1", "dark_mode") is False
    print("  test_remove_flag PASSED")


def test_get_flag_count():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "f1")
    svc.set_flag("agent-1", "f2")
    svc.set_flag("agent-2", "f1")
    assert svc.get_flag_count() == 3
    assert svc.get_flag_count("agent-1") == 2
    assert svc.get_flag_count("agent-2") == 1
    assert svc.get_flag_count("agent-999") == 0
    print("  test_get_flag_count PASSED")


def test_list_agents():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "f1")
    svc.set_flag("agent-2", "f2")
    agents = svc.list_agents()
    assert set(agents) == {"agent-1", "agent-2"}
    print("  test_list_agents PASSED")


def test_list_features():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "dark_mode")
    svc.set_flag("agent-2", "beta")
    svc.set_flag("agent-2", "dark_mode")
    features = svc.list_features()
    assert features == ["beta", "dark_mode"], f"Got {features}"
    print("  test_list_features PASSED")


def test_callbacks():
    svc = AgentFeatureFlag()
    events = []
    svc.on_change("tracker", lambda action, detail: events.append((action, detail)))
    svc.set_flag("agent-1", "f1")
    assert len(events) == 1
    assert events[0][0] == "flag_set"
    assert events[0][1]["feature"] == "f1"
    # remove callback
    assert svc.remove_callback("tracker") is True
    assert svc.remove_callback("tracker") is False
    svc.set_flag("agent-1", "f2")
    assert len(events) == 1  # no new event
    print("  test_callbacks PASSED")


def test_stats():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "f1")
    svc.set_flag("agent-2", "f2")
    svc.is_enabled("agent-1", "f1")
    svc.remove_flag("agent-1", "f1")
    stats = svc.get_stats()
    assert stats["total_set"] == 2
    assert stats["total_removed"] == 1
    assert stats["total_queries"] >= 1
    assert stats["current_entries"] == 1
    assert stats["unique_agents"] == 1
    assert stats["max_entries"] == 10000
    print("  test_stats PASSED")


def test_reset():
    svc = AgentFeatureFlag()
    svc.set_flag("agent-1", "f1")
    svc.on_change("cb", lambda a, d: None)
    svc.reset()
    assert svc.get_flag_count() == 0
    assert svc.list_agents() == []
    stats = svc.get_stats()
    assert stats["total_set"] == 0
    assert stats["current_entries"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    tests = [
        test_set_flag,
        test_is_enabled,
        test_is_enabled_default,
        test_get_flags,
        test_remove_flag,
        test_get_flag_count,
        test_list_agents,
        test_list_features,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"\n=== ALL {len(tests)} TESTS PASSED ===")
