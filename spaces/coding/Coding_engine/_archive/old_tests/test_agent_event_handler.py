"""Test agent event handler."""
import sys
sys.path.insert(0, ".")

from src.services.agent_event_handler import AgentEventHandler


def test_subscribe():
    """Subscribe and retrieve subscription."""
    eh = AgentEventHandler()
    sid = eh.subscribe("deploy", "worker")
    assert sid.startswith("sub-")

    s = eh.get_subscription(sid)
    assert s is not None
    assert s["event_type"] == "deploy"
    assert s["agent"] == "worker"
    assert s["active"] is True

    assert eh.unsubscribe(sid) is True
    assert eh.unsubscribe(sid) is False
    print("OK: subscribe")


def test_invalid_subscribe():
    """Invalid subscribe rejected."""
    eh = AgentEventHandler()
    assert eh.subscribe("", "worker") == ""
    assert eh.subscribe("deploy", "") == ""
    print("OK: invalid subscribe")


def test_duplicate():
    """Duplicate agent+type rejected."""
    eh = AgentEventHandler()
    eh.subscribe("deploy", "worker")
    assert eh.subscribe("deploy", "worker") == ""
    print("OK: duplicate")


def test_max_subs():
    """Max subscriptions enforced."""
    eh = AgentEventHandler(max_subscriptions=2)
    eh.subscribe("a", "agent1")
    eh.subscribe("b", "agent2")
    assert eh.subscribe("c", "agent3") == ""
    print("OK: max subs")


def test_publish():
    """Publish event delivers to subscribers."""
    eh = AgentEventHandler()
    received = []
    eh.subscribe("deploy", "worker",
                  handler=lambda t, p: received.append(p))

    count = eh.publish("deploy", source="ci", payload={"v": "1.0"})
    assert count == 1
    assert len(received) == 1
    assert received[0]["v"] == "1.0"
    print("OK: publish")


def test_publish_no_subscribers():
    """Publish with no subscribers returns 0."""
    eh = AgentEventHandler()
    count = eh.publish("unknown")
    assert count == 0
    print("OK: publish no subscribers")


def test_wildcard():
    """Wildcard subscription receives all events."""
    eh = AgentEventHandler()
    received = []
    eh.subscribe("*", "monitor",
                  handler=lambda t, p: received.append(t))

    eh.publish("deploy")
    eh.publish("build")
    assert len(received) == 2
    assert "deploy" in received
    assert "build" in received
    print("OK: wildcard")


def test_one_shot():
    """One-shot subscription auto-removes."""
    eh = AgentEventHandler()
    received = []
    eh.subscribe("deploy", "worker", one_shot=True,
                  handler=lambda t, p: received.append(1))

    eh.publish("deploy")
    assert len(received) == 1

    eh.publish("deploy")
    assert len(received) == 1  # not called again
    print("OK: one shot")


def test_pause_resume():
    """Pause and resume subscription."""
    eh = AgentEventHandler()
    received = []
    sid = eh.subscribe("deploy", "worker",
                        handler=lambda t, p: received.append(1))

    assert eh.pause_subscription(sid) is True
    assert eh.pause_subscription(sid) is False  # already paused

    eh.publish("deploy")
    assert len(received) == 0  # paused

    assert eh.resume_subscription(sid) is True
    assert eh.resume_subscription(sid) is False  # already active

    eh.publish("deploy")
    assert len(received) == 1
    print("OK: pause resume")


def test_multiple_subscribers():
    """Multiple subscribers for same event."""
    eh = AgentEventHandler()
    r = []
    eh.subscribe("deploy", "w1", handler=lambda t, p: r.append("w1"))
    eh.subscribe("deploy", "w2", handler=lambda t, p: r.append("w2"))

    count = eh.publish("deploy")
    assert count == 2
    assert "w1" in r and "w2" in r
    print("OK: multiple subscribers")


def test_event_history():
    """Event history recorded."""
    eh = AgentEventHandler()
    eh.publish("deploy", source="ci", payload={"v": 1})
    eh.publish("build", source="ci")
    eh.publish("deploy", source="cd")

    history = eh.get_event_history()
    assert len(history) == 3

    by_type = eh.get_event_history(event_type="deploy")
    assert len(by_type) == 2

    by_source = eh.get_event_history(source="ci")
    assert len(by_source) == 2
    print("OK: event history")


def test_get_event():
    """Get specific event."""
    eh = AgentEventHandler()
    eh.publish("deploy", payload={"v": 1})

    history = eh.get_event_history()
    eid = history[0]["event_id"]

    e = eh.get_event(eid)
    assert e is not None
    assert e["event_type"] == "deploy"
    assert eh.get_event("nonexistent") is None
    print("OK: get event")


def test_list_subscriptions():
    """List subscriptions with filters."""
    eh = AgentEventHandler()
    eh.subscribe("deploy", "w1")
    sid2 = eh.subscribe("build", "w2")
    eh.pause_subscription(sid2)

    all_s = eh.list_subscriptions()
    assert len(all_s) == 2

    by_agent = eh.list_subscriptions(agent="w1")
    assert len(by_agent) == 1

    by_type = eh.list_subscriptions(event_type="build")
    assert len(by_type) == 1

    by_active = eh.list_subscriptions(active=True)
    assert len(by_active) == 1
    print("OK: list subscriptions")


def test_callback():
    """Callback fires on events."""
    eh = AgentEventHandler()
    fired = []
    eh.on_change("mon", lambda a, d: fired.append(a))

    eh.subscribe("deploy", "worker")
    assert "subscription_created" in fired

    eh.publish("deploy")
    assert "event_published" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    eh = AgentEventHandler()
    assert eh.on_change("mon", lambda a, d: None) is True
    assert eh.on_change("mon", lambda a, d: None) is False
    assert eh.remove_callback("mon") is True
    assert eh.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    eh = AgentEventHandler()
    eh.subscribe("deploy", "worker")
    eh.publish("deploy")
    eh.publish("build")

    stats = eh.get_stats()
    assert stats["total_subscriptions"] == 1
    assert stats["total_events"] == 2
    assert stats["total_deliveries"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    eh = AgentEventHandler()
    eh.subscribe("deploy", "worker")
    eh.publish("deploy")

    eh.reset()
    assert eh.list_subscriptions() == []
    assert eh.get_event_history() == []
    stats = eh.get_stats()
    assert stats["current_subscriptions"] == 0
    print("OK: reset")


def main():
    print("=== Agent Event Handler Tests ===\n")
    test_subscribe()
    test_invalid_subscribe()
    test_duplicate()
    test_max_subs()
    test_publish()
    test_publish_no_subscribers()
    test_wildcard()
    test_one_shot()
    test_pause_resume()
    test_multiple_subscribers()
    test_event_history()
    test_get_event()
    test_list_subscriptions()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
