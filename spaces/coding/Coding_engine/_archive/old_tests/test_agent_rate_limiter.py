"""Test agent rate limiter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_rate_limiter import AgentRateLimiter


def test_configure():
    rl = AgentRateLimiter()
    lid = rl.configure("agent-1", "api_call", max_requests=10, window_seconds=60.0)
    assert len(lid) > 0
    assert lid.startswith("arl2-")
    print("OK: configure")


def test_is_allowed():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call", max_requests=3, window_seconds=60.0)
    assert rl.is_allowed("agent-1", "api_call") is True
    assert rl.is_allowed("agent-1", "api_call") is True
    assert rl.is_allowed("agent-1", "api_call") is True
    assert rl.is_allowed("agent-1", "api_call") is False  # exceeded
    print("OK: is allowed")


def test_get_remaining():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call", max_requests=5, window_seconds=60.0)
    rl.is_allowed("agent-1", "api_call")
    rl.is_allowed("agent-1", "api_call")
    remaining = rl.get_remaining("agent-1", "api_call")
    assert remaining == 3
    print("OK: get remaining")


def test_get_usage():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call", max_requests=10, window_seconds=60.0)
    rl.is_allowed("agent-1", "api_call")
    usage = rl.get_usage("agent-1", "api_call")
    assert usage["used"] == 1
    assert usage["max"] == 10
    print("OK: get usage")


def test_reset_limiter():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call", max_requests=2, window_seconds=60.0)
    rl.is_allowed("agent-1", "api_call")
    rl.is_allowed("agent-1", "api_call")
    assert rl.is_allowed("agent-1", "api_call") is False
    assert rl.reset_limiter("agent-1", "api_call") is True
    assert rl.is_allowed("agent-1", "api_call") is True  # reset worked
    assert rl.reset_limiter("agent-1", "nonexistent") is False
    print("OK: reset limiter")


def test_get_limiter_count():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call")
    rl.configure("agent-2", "build")
    assert rl.get_limiter_count() == 2
    assert rl.get_limiter_count("agent-1") == 1
    print("OK: get limiter count")


def test_list_agents():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call")
    rl.configure("agent-2", "build")
    agents = rl.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    rl = AgentRateLimiter()
    fired = []
    rl.on_change("mon", lambda a, d: fired.append(a))
    rl.configure("agent-1", "api_call")
    assert len(fired) >= 1
    assert rl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call")
    stats = rl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rl = AgentRateLimiter()
    rl.configure("agent-1", "api_call")
    rl.reset()
    assert rl.get_limiter_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Rate Limiter Tests ===\n")
    test_configure()
    test_is_allowed()
    test_get_remaining()
    test_get_usage()
    test_reset_limiter()
    test_get_limiter_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
