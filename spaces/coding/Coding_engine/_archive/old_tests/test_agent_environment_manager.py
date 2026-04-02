"""Test agent environment manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_environment_manager import AgentEnvironmentManager


def test_create_environment():
    em = AgentEnvironmentManager()
    eid = em.create_environment("agent-1", env_type="python", variables={"PATH": "/usr/bin"})
    assert len(eid) > 0
    assert eid.startswith("aem-")
    print("OK: create environment")


def test_set_variable():
    em = AgentEnvironmentManager()
    eid = em.create_environment("agent-1")
    assert em.set_variable(eid, "KEY", "value") is True
    print("OK: set variable")


def test_get_variable():
    em = AgentEnvironmentManager()
    eid = em.create_environment("agent-1", variables={"FOO": "bar"})
    assert em.get_variable(eid, "FOO") == "bar"
    assert em.get_variable(eid, "MISSING") is None
    print("OK: get variable")


def test_get_all_variables():
    em = AgentEnvironmentManager()
    eid = em.create_environment("agent-1", variables={"A": "1", "B": "2"})
    em.set_variable(eid, "C", "3")
    vars_ = em.get_all_variables(eid)
    assert len(vars_) == 3
    print("OK: get all variables")


def test_destroy_environment():
    em = AgentEnvironmentManager()
    eid = em.create_environment("agent-1")
    assert em.destroy_environment(eid) is True
    assert em.destroy_environment("nonexistent") is False
    print("OK: destroy environment")


def test_get_agent_environments():
    em = AgentEnvironmentManager()
    em.create_environment("agent-1", env_type="python")
    em.create_environment("agent-1", env_type="node")
    envs = em.get_agent_environments("agent-1")
    assert len(envs) == 2
    print("OK: get agent environments")


def test_list_agents():
    em = AgentEnvironmentManager()
    em.create_environment("agent-1")
    em.create_environment("agent-2")
    agents = em.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    em = AgentEnvironmentManager()
    fired = []
    em.on_change("mon", lambda a, d: fired.append(a))
    em.create_environment("agent-1")
    assert len(fired) >= 1
    assert em.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    em = AgentEnvironmentManager()
    em.create_environment("agent-1")
    stats = em.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    em = AgentEnvironmentManager()
    em.create_environment("agent-1")
    em.reset()
    assert em.get_environment_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Environment Manager Tests ===\n")
    test_create_environment()
    test_set_variable()
    test_get_variable()
    test_get_all_variables()
    test_destroy_environment()
    test_get_agent_environments()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
