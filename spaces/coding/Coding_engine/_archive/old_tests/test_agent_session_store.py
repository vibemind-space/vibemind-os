"""Test agent session store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_session_store import AgentSessionStore


def test_create_session():
    ss = AgentSessionStore()
    sid = ss.create_session("agent-1", metadata={"ip": "10.0.0.1"}, tags=["web"])
    assert len(sid) > 0
    s = ss.get_session(sid)
    assert s is not None
    assert s["agent_id"] == "agent-1"
    print("OK: create session")


def test_end_session():
    ss = AgentSessionStore()
    sid = ss.create_session("agent-1")
    assert ss.end_session(sid) is True
    assert ss.end_session(sid) is False  # already ended
    print("OK: end session")


def test_get_active_sessions():
    ss = AgentSessionStore()
    ss.create_session("agent-1")
    ss.create_session("agent-1")
    ss.create_session("agent-2")
    active = ss.get_active_sessions(agent_id="agent-1")
    assert len(active) == 2
    all_active = ss.get_active_sessions()
    assert len(all_active) == 3
    print("OK: get active sessions")


def test_refresh_session():
    ss = AgentSessionStore()
    sid = ss.create_session("agent-1")
    import time
    time.sleep(0.01)
    assert ss.refresh_session(sid) is True
    s = ss.get_session(sid)
    assert s["last_active"] > s["created_at"]
    print("OK: refresh session")


def test_session_duration():
    ss = AgentSessionStore()
    sid = ss.create_session("agent-1")
    import time
    time.sleep(0.02)
    dur = ss.get_session_duration(sid)
    assert dur >= 0.01
    print("OK: session duration")


def test_list_agents_with_sessions():
    ss = AgentSessionStore()
    ss.create_session("agent-1")
    ss.create_session("agent-2")
    agents = ss.list_agents_with_sessions()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents with sessions")


def test_purge_expired():
    ss = AgentSessionStore()
    ss.create_session("agent-1")
    import time
    time.sleep(0.01)
    count = ss.purge_expired(max_age_seconds=0.001)
    assert count >= 1
    print("OK: purge expired")


def test_callbacks():
    ss = AgentSessionStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.create_session("agent-1")
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = AgentSessionStore()
    ss.create_session("agent-1")
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = AgentSessionStore()
    ss.create_session("agent-1")
    ss.reset()
    assert ss.get_active_sessions() == []
    print("OK: reset")


def main():
    print("=== Agent Session Store Tests ===\n")
    test_create_session()
    test_end_session()
    test_get_active_sessions()
    test_refresh_session()
    test_session_duration()
    test_list_agents_with_sessions()
    test_purge_expired()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
