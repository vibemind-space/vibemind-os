"""Test agent communication bus."""
import sys
sys.path.insert(0, ".")

from src.services.agent_communication_bus import AgentCommunicationBus


def test_register_agent():
    """Register and unregister agents."""
    bus = AgentCommunicationBus()
    assert bus.register_agent("Builder") is True
    assert bus.register_agent("Builder") is False

    agents = bus.list_agents()
    assert "Builder" in agents

    assert bus.unregister_agent("Builder") is True
    assert bus.unregister_agent("Builder") is False
    assert bus.list_agents() == []
    print("OK: register agent")


def test_subscribe():
    """Subscribe and unsubscribe."""
    bus = AgentCommunicationBus()
    bus.register_agent("Builder")

    sid = bus.subscribe("Builder", "build.*")
    assert sid is not None and sid.startswith("sub-")

    subs = bus.list_subscriptions()
    assert len(subs) == 1
    assert subs[0]["topic"] == "build.*"

    subs_filtered = bus.list_subscriptions(agent="Builder")
    assert len(subs_filtered) == 1

    assert bus.unsubscribe(sid) is True
    assert bus.unsubscribe(sid) is False

    # Can't subscribe unregistered
    assert bus.subscribe("Ghost", "topic") is None
    print("OK: subscribe")


def test_publish_subscribe():
    """Publish to topic, subscriber receives."""
    bus = AgentCommunicationBus()
    bus.register_agent("Publisher")
    bus.register_agent("Subscriber")
    bus.subscribe("Subscriber", "events")

    msg_id = bus.publish("events", "Publisher", payload={"action": "build"})
    assert msg_id.startswith("msg-")

    msgs = bus.receive("Subscriber")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["action"] == "build"
    assert msgs[0]["sender"] == "Publisher"

    # Queue now empty
    assert bus.receive("Subscriber") == []
    print("OK: publish subscribe")


def test_wildcard_subscribe():
    """Wildcard topic matching."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "build.*")

    bus.publish("build.start", "A", payload="started")
    bus.publish("build.finish", "A", payload="finished")
    bus.publish("test.start", "A", payload="testing")  # Won't match

    msgs = bus.receive("B", limit=10)
    assert len(msgs) == 2
    print("OK: wildcard subscribe")


def test_star_subscribe():
    """Subscribe to all topics with *."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("Monitor")
    bus.subscribe("Monitor", "*")

    bus.publish("build", "A")
    bus.publish("test", "A")

    msgs = bus.receive("Monitor")
    assert len(msgs) == 2
    print("OK: star subscribe")


def test_no_self_delivery():
    """Sender doesn't receive own messages."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.subscribe("A", "events")

    bus.publish("events", "A", payload="self")
    assert bus.receive("A") == []
    print("OK: no self delivery")


def test_send_direct():
    """Direct message to agent."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")

    assert bus.send_direct("B", "A", payload="hello") is True
    msgs = bus.receive("B")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"

    assert bus.send_direct("Ghost", "A") is False
    print("OK: send direct")


def test_request_reply():
    """Request/reply pattern."""
    bus = AgentCommunicationBus()
    bus.register_agent("Client")
    bus.register_agent("Server")
    bus.subscribe("Server", "api.request")

    corr_id = bus.request("api.request", "Client", payload={"q": "status"})
    assert corr_id.startswith("corr-")

    # Server receives request
    msgs = bus.receive("Server")
    assert len(msgs) == 1
    assert msgs[0]["reply_to"] == corr_id

    # Server replies
    assert bus.reply(corr_id, "Server", "Client", payload={"status": "ok"}) is True

    # Client receives reply
    replies = bus.receive("Client")
    assert len(replies) == 1
    assert replies[0]["payload"]["status"] == "ok"
    assert replies[0]["reply_to"] == corr_id

    # Reply to nonexistent
    assert bus.reply("x", "Server", "Ghost") is False
    print("OK: request reply")


def test_peek():
    """Peek without consuming."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "events")

    bus.publish("events", "A", payload="data")

    peeked = bus.peek("B")
    assert len(peeked) == 1

    # Still in queue
    assert bus.queue_size("B") == 1

    # Receive removes it
    bus.receive("B")
    assert bus.queue_size("B") == 0
    print("OK: peek")


def test_queue_size():
    """Queue size tracking."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "events")

    assert bus.queue_size("B") == 0
    assert bus.queue_size("nonexistent") == 0

    bus.publish("events", "A")
    bus.publish("events", "A")
    assert bus.queue_size("B") == 2
    print("OK: queue size")


def test_drain():
    """Drain all messages."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "events")

    for _ in range(5):
        bus.publish("events", "A")

    assert bus.drain("B") == 5
    assert bus.queue_size("B") == 0
    assert bus.drain("nonexistent") == 0
    print("OK: drain")


def test_filter_fn():
    """Filter function on subscription."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")

    # Only accept payloads with priority > 5
    bus.subscribe("B", "tasks", filter_fn=lambda p: p.get("priority", 0) > 5)

    bus.publish("tasks", "A", payload={"priority": 3})
    bus.publish("tasks", "A", payload={"priority": 10})

    msgs = bus.receive("B")
    assert len(msgs) == 1
    assert msgs[0]["payload"]["priority"] == 10
    print("OK: filter fn")


def test_dead_letters():
    """Undeliverable messages go to dead letter queue."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")

    # No subscribers for this topic
    bus.publish("orphan_topic", "A", payload="lost")

    dl = bus.get_dead_letters()
    assert len(dl) == 1
    assert dl[0]["topic"] == "orphan_topic"
    print("OK: dead letters")


def test_history():
    """Message history."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "events")

    bus.publish("events", "A", payload="msg1")
    bus.publish("events", "A", payload="msg2")

    history = bus.get_history()
    assert len(history) == 2

    by_sender = bus.get_history(sender="A")
    assert len(by_sender) == 2

    by_topic = bus.get_history(topic="events")
    assert len(by_topic) == 2

    limited = bus.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_list_topics():
    """List active topics."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.subscribe("A", "build")
    bus.subscribe("A", "test")

    topics = bus.list_topics()
    assert "build" in topics
    assert "test" in topics
    print("OK: list topics")


def test_topic_subscribers():
    """Get subscribers for a topic."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("A", "events")
    bus.subscribe("B", "events")

    subs = bus.get_topic_subscribers("events")
    assert len(subs) == 2
    assert "A" in subs
    assert "B" in subs
    print("OK: topic subscribers")


def test_unregister_cleans_subs():
    """Unregister removes subscriptions."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.subscribe("A", "events")
    bus.subscribe("A", "builds")

    bus.unregister_agent("A")
    assert bus.list_subscriptions() == []
    print("OK: unregister cleans subs")


def test_stats():
    """Stats are accurate."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.register_agent("B")
    bus.subscribe("B", "events")

    bus.publish("events", "A")
    bus.send_direct("B", "A")

    stats = bus.get_stats()
    assert stats["total_agents"] == 2
    assert stats["total_subscriptions"] == 1
    assert stats["total_published"] == 2
    assert stats["total_delivered"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    bus = AgentCommunicationBus()
    bus.register_agent("A")
    bus.subscribe("A", "events")

    bus.reset()
    assert bus.list_agents() == []
    assert bus.list_subscriptions() == []
    stats = bus.get_stats()
    assert stats["total_agents"] == 0
    print("OK: reset")


def main():
    print("=== Agent Communication Bus Tests ===\n")
    test_register_agent()
    test_subscribe()
    test_publish_subscribe()
    test_wildcard_subscribe()
    test_star_subscribe()
    test_no_self_delivery()
    test_send_direct()
    test_request_reply()
    test_peek()
    test_queue_size()
    test_drain()
    test_filter_fn()
    test_dead_letters()
    test_history()
    test_list_topics()
    test_topic_subscribers()
    test_unregister_cleans_subs()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
