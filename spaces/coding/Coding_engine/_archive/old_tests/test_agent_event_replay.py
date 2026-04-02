"""Test agent event replay -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_event_replay import AgentEventReplay


def test_record_event():
    er = AgentEventReplay()
    eid = er.record_event("agent-1", "click", {"x": 10, "y": 20})
    assert len(eid) > 0
    assert eid.startswith("aer-")
    print("OK: record event")


def test_replay():
    er = AgentEventReplay()
    er.record_event("agent-1", "click", {"x": 10})
    er.record_event("agent-1", "scroll", {"y": 100})
    er.record_event("agent-1", "click", {"x": 20})
    events = er.replay("agent-1", from_index=0, to_index=2)
    assert len(events) == 2
    print("OK: replay")


def test_replay_all():
    er = AgentEventReplay()
    er.record_event("agent-1", "click", {"x": 10})
    er.record_event("agent-1", "scroll", {"y": 100})
    events = er.replay("agent-1")
    assert len(events) == 2
    print("OK: replay all")


def test_get_events():
    er = AgentEventReplay()
    er.record_event("agent-1", "click", {"x": 10})
    er.record_event("agent-1", "scroll", {"y": 100})
    events = er.get_events("agent-1")
    assert len(events) == 2
    print("OK: get events")


def test_get_events_filtered():
    er = AgentEventReplay()
    er.record_event("agent-1", "click", {"x": 10})
    er.record_event("agent-1", "scroll", {"y": 100})
    er.record_event("agent-1", "click", {"x": 20})
    events = er.get_events("agent-1", event_type="click")
    assert len(events) == 2
    print("OK: get events filtered")


def test_get_event_count():
    er = AgentEventReplay()
    er.record_event("agent-1", "click")
    er.record_event("agent-2", "scroll")
    assert er.get_event_count() == 2
    assert er.get_event_count("agent-1") == 1
    print("OK: get event count")


def test_clear_events():
    er = AgentEventReplay()
    er.record_event("agent-1", "click")
    er.record_event("agent-1", "scroll")
    cleared = er.clear_events("agent-1")
    assert cleared == 2
    assert er.get_event_count("agent-1") == 0
    print("OK: clear events")


def test_list_agents():
    er = AgentEventReplay()
    er.record_event("agent-1", "click")
    er.record_event("agent-2", "scroll")
    agents = er.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    er = AgentEventReplay()
    fired = []
    er.on_change("mon", lambda a, d: fired.append(a))
    er.record_event("agent-1", "click")
    assert len(fired) >= 1
    assert er.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    er = AgentEventReplay()
    er.record_event("agent-1", "click")
    stats = er.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    er = AgentEventReplay()
    er.record_event("agent-1", "click")
    er.reset()
    assert er.get_event_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Event Replay Tests ===\n")
    test_record_event()
    test_replay()
    test_replay_all()
    test_get_events()
    test_get_events_filtered()
    test_get_event_count()
    test_clear_events()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
