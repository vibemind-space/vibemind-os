"""Tests for AgentEnvConfig service."""

import sys
sys.path.insert(0, ".")

from src.services.agent_env_config import AgentEnvConfig


def test_set_config():
    svc = AgentEnvConfig()
    cid = svc.set_config("agent-1", "db_host", "localhost")
    assert cid.startswith("aec-"), f"Expected 'aec-' prefix, got {cid}"
    assert len(cid) > 4
    # Update returns same id
    cid2 = svc.set_config("agent-1", "db_host", "remotehost")
    assert cid2 == cid
    print("  test_set_config PASSED")


def test_get_config():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "db_host", "localhost")
    val = svc.get_config("agent-1", "db_host")
    assert val == "localhost", f"Expected 'localhost', got {val}"
    print("  test_get_config PASSED")


def test_get_config_default():
    svc = AgentEnvConfig()
    val = svc.get_config("agent-1", "missing_key")
    assert val is None
    val2 = svc.get_config("agent-1", "missing_key", default="fallback")
    assert val2 == "fallback"
    print("  test_get_config_default PASSED")


def test_delete_config():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "db_host", "localhost")
    assert svc.delete_config("agent-1", "db_host") is True
    assert svc.delete_config("agent-1", "db_host") is False
    assert svc.get_config("agent-1", "db_host") is None
    print("  test_delete_config PASSED")


def test_get_all_config():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "db_host", "localhost")
    svc.set_config("agent-1", "db_port", 5432)
    svc.set_config("agent-2", "api_key", "secret")
    all_cfg = svc.get_all_config("agent-1")
    assert all_cfg == {"db_host": "localhost", "db_port": 5432}
    all_cfg2 = svc.get_all_config("agent-999")
    assert all_cfg2 == {}
    print("  test_get_all_config PASSED")


def test_get_config_count():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "k1", "v1")
    svc.set_config("agent-1", "k2", "v2")
    svc.set_config("agent-2", "k3", "v3")
    assert svc.get_config_count() == 3
    assert svc.get_config_count("agent-1") == 2
    assert svc.get_config_count("agent-2") == 1
    assert svc.get_config_count("agent-999") == 0
    print("  test_get_config_count PASSED")


def test_list_agents():
    svc = AgentEnvConfig()
    svc.set_config("agent-b", "k", "v")
    svc.set_config("agent-a", "k", "v")
    agents = svc.list_agents()
    assert agents == ["agent-a", "agent-b"]
    print("  test_list_agents PASSED")


def test_list_keys():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "zeta", 1)
    svc.set_config("agent-1", "alpha", 2)
    keys = svc.list_keys("agent-1")
    assert keys == ["alpha", "zeta"]
    assert svc.list_keys("agent-999") == []
    print("  test_list_keys PASSED")


def test_callbacks():
    svc = AgentEnvConfig()
    events = []
    svc.on_change("tracker", lambda evt, data: events.append((evt, data)))
    svc.set_config("agent-1", "k", "v1")
    assert len(events) == 1
    assert events[0][0] == "config_set"
    svc.set_config("agent-1", "k", "v2")
    assert len(events) == 2
    assert events[1][0] == "config_updated"
    svc.delete_config("agent-1", "k")
    assert len(events) == 3
    assert events[2][0] == "config_deleted"
    assert svc.remove_callback("tracker") is True
    assert svc.remove_callback("tracker") is False
    print("  test_callbacks PASSED")


def test_stats():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "k1", "v1")
    svc.set_config("agent-1", "k2", "v2")
    svc.get_config("agent-1", "k1")
    svc.delete_config("agent-1", "k2")
    stats = svc.get_stats()
    assert stats["total_entries"] == 1
    assert stats["total_agents"] == 1
    assert stats["total_sets"] == 2
    assert stats["total_gets"] == 1
    assert stats["total_deletes"] == 1
    assert stats["max_entries"] == 10000
    assert "seq" in stats
    assert "callbacks_registered" in stats
    print("  test_stats PASSED")


def test_reset():
    svc = AgentEnvConfig()
    svc.set_config("agent-1", "k", "v")
    svc.on_change("cb", lambda e, d: None)
    svc.reset()
    assert svc.get_config_count() == 0
    assert svc.list_agents() == []
    stats = svc.get_stats()
    assert stats["total_entries"] == 0
    assert stats["seq"] == 0
    assert stats["callbacks_registered"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    test_set_config()
    test_get_config()
    test_get_config_default()
    test_delete_config()
    test_get_all_config()
    test_get_config_count()
    test_list_agents()
    test_list_keys()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")
