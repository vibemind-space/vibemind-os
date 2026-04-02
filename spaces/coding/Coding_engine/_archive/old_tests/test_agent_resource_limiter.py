"""Test agent resource limiter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_resource_limiter import AgentResourceLimiter


def test_set_limit():
    rl = AgentResourceLimiter()
    lid = rl.set_limit("agent-1", "cpu", 80.0)
    assert len(lid) > 0
    assert lid.startswith("arl-")
    print("OK: set limit")


def test_check_limit_within():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 80.0)
    assert rl.check_limit("agent-1", "cpu", 50.0) is True
    print("OK: check limit within")


def test_check_limit_exceeded():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "memory", 1024.0)
    assert rl.check_limit("agent-1", "memory", 2048.0) is False
    print("OK: check limit exceeded")


def test_get_limit():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "connections", 100.0)
    assert rl.get_limit("agent-1", "connections") == 100.0
    assert rl.get_limit("agent-1", "nonexistent") is None
    print("OK: get limit")


def test_get_usage_ratio():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 100.0)
    ratio = rl.get_usage_ratio("agent-1", "cpu", 75.0)
    assert abs(ratio - 0.75) < 0.01
    print("OK: get usage ratio")


def test_remove_limit():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 80.0)
    assert rl.remove_limit("agent-1", "cpu") is True
    assert rl.get_limit("agent-1", "cpu") is None
    print("OK: remove limit")


def test_list_agents():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 80.0)
    rl.set_limit("agent-2", "memory", 512.0)
    agents = rl.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    rl = AgentResourceLimiter()
    fired = []
    rl.on_change("mon", lambda a, d: fired.append(a))
    rl.set_limit("agent-1", "cpu", 80.0)
    assert len(fired) >= 1
    assert rl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 80.0)
    stats = rl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rl = AgentResourceLimiter()
    rl.set_limit("agent-1", "cpu", 80.0)
    rl.reset()
    assert rl.get_limit_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Resource Limiter Tests ===\n")
    test_set_limit()
    test_check_limit_within()
    test_check_limit_exceeded()
    test_get_limit()
    test_get_usage_ratio()
    test_remove_limit()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
