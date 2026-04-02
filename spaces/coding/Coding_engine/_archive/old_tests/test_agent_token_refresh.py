"""Test agent token refresh -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_token_refresh import AgentTokenRefresh


def test_register_token():
    tr = AgentTokenRefresh()
    tid = tr.register_token("agent-1", "tok-abc123", ttl_seconds=3600.0)
    assert len(tid) > 0
    assert tid.startswith("atrf-")
    print("OK: register token")


def test_get_token():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-abc123")
    tok = tr.get_token("agent-1")
    assert tok == "tok-abc123"
    assert tr.get_token("nonexistent") is None
    print("OK: get token")


def test_is_expired():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-abc", ttl_seconds=3600.0)
    assert tr.is_expired("agent-1") is False
    print("OK: is expired")


def test_refresh_token():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "old-token")
    assert tr.refresh_token("agent-1", "new-token") is True
    assert tr.get_token("agent-1") == "new-token"
    print("OK: refresh token")


def test_get_remaining_ttl():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-abc", ttl_seconds=3600.0)
    remaining = tr.get_remaining_ttl("agent-1")
    assert remaining > 3500.0
    print("OK: get remaining ttl")


def test_list_agents():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-1")
    tr.register_token("agent-2", "tok-2")
    agents = tr.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    tr = AgentTokenRefresh()
    fired = []
    tr.on_change("mon", lambda a, d: fired.append(a))
    tr.register_token("agent-1", "tok-1")
    assert len(fired) >= 1
    assert tr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-1")
    stats = tr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tr = AgentTokenRefresh()
    tr.register_token("agent-1", "tok-1")
    tr.reset()
    assert tr.get_token_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Token Refresh Tests ===\n")
    test_register_token()
    test_get_token()
    test_is_expired()
    test_refresh_token()
    test_get_remaining_ttl()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
