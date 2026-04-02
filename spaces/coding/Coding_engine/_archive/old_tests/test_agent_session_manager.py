"""Test agent session manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_session_manager import AgentSessionManager


def test_create_session():
    """Create a session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1", tags=["build"])
    assert sid.startswith("sess-")

    s = sm.get_session(sid)
    assert s is not None
    assert s["agent"] == "agent-1"
    assert s["status"] == "active"
    assert "build" in s["tags"]
    print("OK: create session")


def test_invalid_create():
    """Invalid session creation rejected."""
    sm = AgentSessionManager()
    assert sm.create_session("") == ""
    print("OK: invalid create")


def test_max_sessions():
    """Max sessions enforced."""
    sm = AgentSessionManager(max_sessions=2)
    sm.create_session("a")
    sm.create_session("b")
    assert sm.create_session("c") == ""
    print("OK: max sessions")


def test_complete_session():
    """Complete a session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.complete_session(sid) is True
    s = sm.get_session(sid)
    assert s["status"] == "completed"
    assert s["ended_at"] > 0

    assert sm.complete_session(sid) is False  # Already completed
    print("OK: complete session")


def test_fail_session():
    """Fail a session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.fail_session(sid, "out of memory") is True
    assert sm.get_session(sid)["status"] == "failed"
    assert sm.fail_session(sid) is False
    print("OK: fail session")


def test_pause_resume():
    """Pause and resume session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.pause_session(sid) is True
    assert sm.get_session(sid)["status"] == "paused"

    assert sm.resume_session(sid) is True
    assert sm.get_session(sid)["status"] == "active"

    assert sm.pause_session(sid) is True
    assert sm.pause_session(sid) is False  # Already paused
    print("OK: pause resume")


def test_remove_session():
    """Remove a session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.remove_session(sid) is True
    assert sm.get_session(sid) is None
    assert sm.remove_session(sid) is False
    print("OK: remove session")


def test_context():
    """Session context management."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.set_context(sid, "task_id", "t-123") is True
    assert sm.set_context(sid, "retry_count", 0) is True

    assert sm.get_context(sid, "task_id") == "t-123"
    assert sm.get_context(sid, "nonexistent") is None

    ctx = sm.get_all_context(sid)
    assert ctx["task_id"] == "t-123"
    assert ctx["retry_count"] == 0

    assert sm.remove_context(sid, "task_id") is True
    assert sm.remove_context(sid, "task_id") is False
    print("OK: context")


def test_context_on_closed():
    """Can't set context on closed session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")
    sm.complete_session(sid)

    assert sm.set_context(sid, "key", "val") is False
    print("OK: context on closed")


def test_add_events():
    """Add events to session timeline."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")

    assert sm.add_event(sid, "task_started", {"task": "build"}) is True
    assert sm.add_event(sid, "task_completed", {"task": "build"}) is True

    events = sm.get_events(sid)
    assert len(events) == 2
    assert events[0]["event_type"] == "task_started"
    print("OK: add events")


def test_filter_events():
    """Filter events by type."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")
    sm.add_event(sid, "start")
    sm.add_event(sid, "progress")
    sm.add_event(sid, "start")

    starts = sm.get_events(sid, event_type="start")
    assert len(starts) == 2
    print("OK: filter events")


def test_events_on_closed():
    """Can't add events to closed session."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1")
    sm.complete_session(sid)

    assert sm.add_event(sid, "late") is False
    print("OK: events on closed")


def test_timeout_expiry():
    """Session expires after timeout."""
    sm = AgentSessionManager()
    sid = sm.create_session("agent-1", timeout=0.02)

    time.sleep(0.03)
    s = sm.get_session(sid)
    assert s["status"] == "expired"
    print("OK: timeout expiry")


def test_list_sessions():
    """List sessions with filters."""
    sm = AgentSessionManager()
    s1 = sm.create_session("agent-1", tags=["build"])
    s2 = sm.create_session("agent-2")
    sm.complete_session(s2)

    all_s = sm.list_sessions()
    assert len(all_s) == 2

    by_agent = sm.list_sessions(agent="agent-1")
    assert len(by_agent) == 1

    active = sm.list_sessions(status="active")
    assert len(active) == 1

    tagged = sm.list_sessions(tag="build")
    assert len(tagged) == 1
    print("OK: list sessions")


def test_active_sessions():
    """Get active sessions."""
    sm = AgentSessionManager()
    s1 = sm.create_session("agent-1")
    s2 = sm.create_session("agent-2")
    sm.complete_session(s2)

    active = sm.get_active_sessions()
    assert len(active) == 1
    assert active[0] == s1

    active_a1 = sm.get_active_sessions(agent="agent-1")
    assert len(active_a1) == 1
    print("OK: active sessions")


def test_agent_sessions():
    """Get agent session history."""
    sm = AgentSessionManager()
    sm.create_session("agent-1")
    sm.create_session("agent-1")
    sm.create_session("agent-2")

    history = sm.get_agent_sessions("agent-1")
    assert len(history) == 2
    print("OK: agent sessions")


def test_agent_active_count():
    """Count active sessions per agent."""
    sm = AgentSessionManager()
    s1 = sm.create_session("agent-1")
    s2 = sm.create_session("agent-1")
    sm.complete_session(s2)

    assert sm.get_agent_active_count("agent-1") == 1
    print("OK: agent active count")


def test_callbacks():
    """Callbacks fire on events."""
    sm = AgentSessionManager()

    fired = []
    assert sm.on_change("mon", lambda a, sid: fired.append(a)) is True
    assert sm.on_change("mon", lambda a, s: None) is False

    sid = sm.create_session("agent-1")
    assert "session_created" in fired

    sm.pause_session(sid)
    assert "session_paused" in fired

    sm.resume_session(sid)
    assert "session_resumed" in fired

    sm.complete_session(sid)
    assert "session_completed" in fired

    assert sm.remove_callback("mon") is True
    assert sm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sm = AgentSessionManager()
    s1 = sm.create_session("a")
    s2 = sm.create_session("b")
    sm.complete_session(s1)
    sm.fail_session(s2)

    stats = sm.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_sessions"] == 2
    assert stats["active_sessions"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sm = AgentSessionManager()
    sm.create_session("a")

    sm.reset()
    assert sm.list_sessions() == []
    stats = sm.get_stats()
    assert stats["total_sessions"] == 0
    print("OK: reset")


def main():
    print("=== Agent Session Manager Tests ===\n")
    test_create_session()
    test_invalid_create()
    test_max_sessions()
    test_complete_session()
    test_fail_session()
    test_pause_resume()
    test_remove_session()
    test_context()
    test_context_on_closed()
    test_add_events()
    test_filter_events()
    test_events_on_closed()
    test_timeout_expiry()
    test_list_sessions()
    test_active_sessions()
    test_agent_sessions()
    test_agent_active_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
