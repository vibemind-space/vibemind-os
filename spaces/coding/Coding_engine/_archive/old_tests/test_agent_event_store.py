"""Test agent event store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_event_store import AgentEventStore


def test_record():
    es = AgentEventStore()
    eid = es.record("agent-1", "action", data={"cmd": "build"}, severity="info")
    assert len(eid) > 0
    e = es.get_event(eid)
    assert e is not None
    assert e["agent_id"] == "agent-1"
    assert e["event_type"] == "action"
    print("OK: record")


def test_query_by_agent():
    es = AgentEventStore()
    es.record("a1", "action", severity="info")
    es.record("a2", "action", severity="info")
    es.record("a1", "error", severity="error")
    results = es.query(agent_id="a1")
    assert len(results) == 2
    print("OK: query by agent")


def test_query_by_type():
    es = AgentEventStore()
    es.record("a1", "action", severity="info")
    es.record("a1", "decision", severity="info")
    es.record("a2", "action", severity="info")
    results = es.query(event_type="action")
    assert len(results) == 2
    print("OK: query by type")


def test_query_by_severity():
    es = AgentEventStore()
    es.record("a1", "e1", severity="info")
    es.record("a1", "e2", severity="error")
    results = es.query(severity="error")
    assert len(results) == 1
    print("OK: query by severity")


def test_agent_timeline():
    es = AgentEventStore()
    es.record("a1", "start", severity="info")
    es.record("a1", "process", severity="info")
    es.record("a1", "end", severity="info")
    timeline = es.get_agent_timeline("a1")
    assert len(timeline) == 3
    print("OK: agent timeline")


def test_event_count():
    es = AgentEventStore()
    es.record("a1", "action", severity="info")
    es.record("a1", "action", severity="info")
    es.record("a2", "action", severity="info")
    assert es.get_event_count(agent_id="a1") == 2
    assert es.get_event_count(event_type="action") == 3
    print("OK: event count")


def test_agent_summary():
    es = AgentEventStore()
    es.record("a1", "action", severity="info")
    es.record("a1", "error", severity="error")
    summary = es.get_agent_summary("a1")
    assert summary["total_events"] == 2
    assert "action" in summary["by_type"]
    print("OK: agent summary")


def test_list_agents():
    es = AgentEventStore()
    es.record("a1", "e1", severity="info")
    es.record("a2", "e1", severity="info")
    agents = es.list_agents()
    assert "a1" in agents
    assert "a2" in agents
    print("OK: list agents")


def test_list_event_types():
    es = AgentEventStore()
    es.record("a1", "action", severity="info")
    es.record("a1", "decision", severity="info")
    types = es.list_event_types()
    assert "action" in types
    assert "decision" in types
    print("OK: list event types")


def test_purge():
    es = AgentEventStore()
    es.record("a1", "e1", severity="info")
    import time
    time.sleep(0.01)
    count = es.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    es = AgentEventStore()
    fired = []
    es.on_change("mon", lambda a, d: fired.append(a))
    es.record("a1", "e1", severity="info")
    assert len(fired) >= 1
    assert es.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    es = AgentEventStore()
    es.record("a1", "e1", severity="info")
    stats = es.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    es = AgentEventStore()
    es.record("a1", "e1", severity="info")
    es.reset()
    assert es.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Event Store Tests ===\n")
    test_record()
    test_query_by_agent()
    test_query_by_type()
    test_query_by_severity()
    test_agent_timeline()
    test_event_count()
    test_agent_summary()
    test_list_agents()
    test_list_event_types()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
