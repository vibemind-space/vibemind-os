"""Test agent config store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_config_store import AgentConfigStore


def test_set_config():
    cs = AgentConfigStore()
    cid = cs.set_config("agent-1", "max_retries", 3)
    assert len(cid) > 0
    assert cid.startswith("acs-")
    print("OK: set config")


def test_get_config():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "timeout", 30)
    assert cs.get_config("agent-1", "timeout") == 30
    assert cs.get_config("agent-1", "nonexistent") is None
    assert cs.get_config("agent-1", "nonexistent", default=99) == 99
    print("OK: get config")


def test_get_all_config():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "timeout", 30)
    cs.set_config("agent-1", "retries", 5)
    all_cfg = cs.get_all_config("agent-1")
    assert all_cfg["timeout"] == 30
    assert all_cfg["retries"] == 5
    print("OK: get all config")


def test_delete_config():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "timeout", 30)
    assert cs.delete_config("agent-1", "timeout") is True
    assert cs.get_config("agent-1", "timeout") is None
    assert cs.delete_config("agent-1", "nonexistent") is False
    print("OK: delete config")


def test_has_config():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "timeout", 30)
    assert cs.has_config("agent-1", "timeout") is True
    assert cs.has_config("agent-1", "nonexistent") is False
    print("OK: has config")


def test_list_agents():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "k1", "v1")
    cs.set_config("agent-2", "k2", "v2")
    agents = cs.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_overwrite_config():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "timeout", 30)
    cs.set_config("agent-1", "timeout", 60)
    assert cs.get_config("agent-1", "timeout") == 60
    print("OK: overwrite config")


def test_callbacks():
    cs = AgentConfigStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.set_config("agent-1", "k1", "v1")
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "k1", "v1")
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = AgentConfigStore()
    cs.set_config("agent-1", "k1", "v1")
    cs.reset()
    assert cs.get_config_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Config Store Tests ===\n")
    test_set_config()
    test_get_config()
    test_get_all_config()
    test_delete_config()
    test_has_config()
    test_list_agents()
    test_overwrite_config()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
