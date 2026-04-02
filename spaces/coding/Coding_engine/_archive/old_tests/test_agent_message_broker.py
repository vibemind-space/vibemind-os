"""Test agent message broker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_message_broker import AgentMessageBroker


def test_subscribe():
    mb = AgentMessageBroker()
    sub_id = mb.subscribe("agent-1", "alerts")
    assert sub_id.startswith("amb-")
    assert len(sub_id) > 4
    print("OK: subscribe")


def test_unsubscribe():
    mb = AgentMessageBroker()
    sub_id = mb.subscribe("agent-1", "alerts")
    assert mb.unsubscribe(sub_id) is True
    assert mb.unsubscribe(sub_id) is False
    assert mb.unsubscribe("amb-nonexistent") is False
    print("OK: unsubscribe")


def test_publish():
    mb = AgentMessageBroker()
    msg_id = mb.publish("agent-1", "alerts", "disk full", {"level": "critical"})
    assert msg_id.startswith("amb-")
    assert len(msg_id) > 4
    msgs = mb.get_messages("alerts")
    assert len(msgs) == 1
    assert msgs[0]["message"] == "disk full"
    assert msgs[0]["payload"] == {"level": "critical"}
    assert msgs[0]["agent_id"] == "agent-1"
    print("OK: publish")


def test_get_messages():
    mb = AgentMessageBroker()
    for i in range(10):
        mb.publish("agent-1", "logs", f"msg-{i}")
    # default returns all when under limit
    msgs = mb.get_messages("logs")
    assert len(msgs) == 10
    assert msgs[0]["message"] == "msg-0"
    assert msgs[-1]["message"] == "msg-9"
    # with limit
    msgs = mb.get_messages("logs", limit=3)
    assert len(msgs) == 3
    assert msgs[0]["message"] == "msg-7"
    assert msgs[-1]["message"] == "msg-9"
    # empty topic
    assert mb.get_messages("nonexistent") == []
    print("OK: get_messages")


def test_get_subscribers():
    mb = AgentMessageBroker()
    mb.subscribe("agent-1", "alerts")
    mb.subscribe("agent-2", "alerts")
    mb.subscribe("agent-3", "logs")
    subs = mb.get_subscribers("alerts")
    assert "agent-1" in subs
    assert "agent-2" in subs
    assert "agent-3" not in subs
    assert mb.get_subscribers("nonexistent") == []
    print("OK: get_subscribers")


def test_get_subscription_count():
    mb = AgentMessageBroker()
    mb.subscribe("agent-1", "alerts")
    mb.subscribe("agent-1", "logs")
    mb.subscribe("agent-2", "alerts")
    # total
    assert mb.get_subscription_count() == 3
    # per agent
    assert mb.get_subscription_count("agent-1") == 2
    assert mb.get_subscription_count("agent-2") == 1
    assert mb.get_subscription_count("agent-99") == 0
    print("OK: get_subscription_count")


def test_get_message_count():
    mb = AgentMessageBroker()
    mb.publish("agent-1", "alerts", "msg1")
    mb.publish("agent-1", "alerts", "msg2")
    mb.publish("agent-2", "logs", "msg3")
    # total
    assert mb.get_message_count() == 3
    # per topic
    assert mb.get_message_count("alerts") == 2
    assert mb.get_message_count("logs") == 1
    assert mb.get_message_count("nonexistent") == 0
    print("OK: get_message_count")


def test_list_topics():
    mb = AgentMessageBroker()
    mb.publish("agent-1", "alerts", "msg1")
    mb.subscribe("agent-1", "logs")
    topics = mb.list_topics()
    assert "alerts" in topics
    assert "logs" in topics
    print("OK: list_topics")


def test_list_agents():
    mb = AgentMessageBroker()
    mb.subscribe("agent-1", "alerts")
    mb.subscribe("agent-2", "logs")
    agents = mb.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list_agents")


def test_callbacks():
    mb = AgentMessageBroker()
    fired = []
    mb.on_change("mon", lambda a, d: fired.append(a))
    mb.publish("agent-1", "alerts", "test")
    assert len(fired) >= 1
    assert "published" in fired
    mb.subscribe("agent-1", "logs")
    assert "subscribed" in fired
    assert mb.remove_callback("mon") is True
    assert mb.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    mb = AgentMessageBroker()
    mb.publish("agent-1", "alerts", "msg1")
    mb.subscribe("agent-1", "alerts")
    stats = mb.get_stats()
    assert stats["total_published"] >= 1
    assert stats["total_subscribed"] >= 1
    assert stats["current_messages"] >= 1
    assert stats["current_subscriptions"] >= 1
    assert "max_entries" in stats
    print("OK: stats")


def test_reset():
    mb = AgentMessageBroker()
    mb.publish("agent-1", "alerts", "msg1")
    mb.subscribe("agent-1", "alerts")
    mb.on_change("mon", lambda a, d: None)
    mb.reset()
    assert mb.get_message_count() == 0
    assert mb.get_subscription_count() == 0
    assert mb.list_topics() == []
    assert mb.list_agents() == []
    assert mb.remove_callback("mon") is False
    print("OK: reset")


def main():
    print("=== Agent Message Broker Tests ===\n")
    test_subscribe()
    test_unsubscribe()
    test_publish()
    test_get_messages()
    test_get_subscribers()
    test_get_subscription_count()
    test_get_message_count()
    test_list_topics()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
