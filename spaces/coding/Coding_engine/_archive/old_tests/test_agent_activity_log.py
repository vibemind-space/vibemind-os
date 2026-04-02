"""Test agent activity log -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_activity_log import AgentActivityLog


def test_log_activity():
    al = AgentActivityLog()
    aid = al.log_activity("agent-1", "build", "Started build process")
    assert len(aid) > 0
    assert aid.startswith("aal-")
    print("OK: log activity")


def test_get_activities():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg1")
    al.log_activity("agent-1", "test", "msg2")
    activities = al.get_activities("agent-1")
    assert len(activities) == 2
    print("OK: get activities")


def test_get_activities_filtered():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg1")
    al.log_activity("agent-1", "test", "msg2")
    al.log_activity("agent-1", "build", "msg3")
    activities = al.get_activities("agent-1", activity_type="build")
    assert len(activities) == 2
    print("OK: get activities filtered")


def test_get_latest_activity():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "first")
    al.log_activity("agent-1", "test", "second")
    latest = al.get_latest_activity("agent-1")
    assert latest is not None
    assert latest["description"] == "second"
    assert al.get_latest_activity("nonexistent") is None
    print("OK: get latest activity")


def test_get_activity_count():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg")
    al.log_activity("agent-2", "test", "msg")
    assert al.get_activity_count() == 2
    assert al.get_activity_count("agent-1") == 1
    print("OK: get activity count")


def test_clear_activities():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg1")
    al.log_activity("agent-1", "test", "msg2")
    cleared = al.clear_activities("agent-1")
    assert cleared == 2
    assert al.get_activity_count("agent-1") == 0
    print("OK: clear activities")


def test_list_agents():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg")
    al.log_activity("agent-2", "test", "msg")
    agents = al.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    al = AgentActivityLog()
    fired = []
    al.on_change("mon", lambda a, d: fired.append(a))
    al.log_activity("agent-1", "build", "msg")
    assert len(fired) >= 1
    assert al.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg")
    stats = al.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    al = AgentActivityLog()
    al.log_activity("agent-1", "build", "msg")
    al.reset()
    assert al.get_activity_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Activity Log Tests ===\n")
    test_log_activity()
    test_get_activities()
    test_get_activities_filtered()
    test_get_latest_activity()
    test_get_activity_count()
    test_clear_activities()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
