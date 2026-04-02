"""Test agent session tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_session_tracker import AgentSessionTracker


def test_start_session():
    st = AgentSessionTracker()
    sid = st.start_session("agent-1", session_type="execution", metadata={"task": "build"})
    assert len(sid) > 0
    assert sid.startswith("ast2-")
    print("OK: start session")


def test_get_session():
    st = AgentSessionTracker()
    sid = st.start_session("agent-1", session_type="planning")
    session = st.get_session(sid)
    assert session is not None
    assert session["agent_id"] == "agent-1"
    assert session["session_type"] == "planning"
    assert st.get_session("nonexistent") is None
    print("OK: get session")


def test_end_session():
    st = AgentSessionTracker()
    sid = st.start_session("agent-1")
    assert st.end_session(sid) is True
    session = st.get_session(sid)
    assert session is not None
    print("OK: end session")


def test_get_active_sessions():
    st = AgentSessionTracker()
    s1 = st.start_session("agent-1")
    s2 = st.start_session("agent-1")
    s3 = st.start_session("agent-2")
    st.end_session(s1)
    active = st.get_active_sessions("agent-1")
    assert len(active) == 1
    all_active = st.get_active_sessions()
    assert len(all_active) == 2
    print("OK: get active sessions")


def test_get_session_duration():
    st = AgentSessionTracker()
    sid = st.start_session("agent-1")
    dur = st.get_session_duration(sid)
    assert dur >= 0
    print("OK: get session duration")


def test_get_agent_sessions():
    st = AgentSessionTracker()
    st.start_session("agent-1")
    st.start_session("agent-1")
    st.start_session("agent-2")
    sessions = st.get_agent_sessions("agent-1")
    assert len(sessions) == 2
    print("OK: get agent sessions")


def test_list_agents():
    st = AgentSessionTracker()
    st.start_session("agent-1")
    st.start_session("agent-2")
    agents = st.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    st = AgentSessionTracker()
    fired = []
    st.on_change("mon", lambda a, d: fired.append(a))
    st.start_session("agent-1")
    assert len(fired) >= 1
    assert st.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    st = AgentSessionTracker()
    st.start_session("agent-1")
    stats = st.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    st = AgentSessionTracker()
    st.start_session("agent-1")
    st.reset()
    assert st.get_session_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Session Tracker Tests ===\n")
    test_start_session()
    test_get_session()
    test_end_session()
    test_get_active_sessions()
    test_get_session_duration()
    test_get_agent_sessions()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
