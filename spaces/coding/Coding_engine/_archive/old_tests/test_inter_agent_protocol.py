"""Test inter-agent protocol."""
import sys
sys.path.insert(0, ".")

from src.services.inter_agent_protocol import InterAgentProtocol


def test_create_channel():
    """Create a channel."""
    proto = InterAgentProtocol()
    assert proto.create_channel("builds") is True
    assert proto.create_channel("builds") is False  # Duplicate

    channels = proto.list_channels()
    assert len(channels) == 1
    assert channels[0]["name"] == "builds"
    print("OK: create channel")


def test_delete_channel():
    """Delete a channel."""
    proto = InterAgentProtocol()
    proto.create_channel("temp")
    assert proto.delete_channel("temp") is True
    assert proto.delete_channel("temp") is False
    print("OK: delete channel")


def test_subscribe_unsubscribe():
    """Subscribe and unsubscribe from channels."""
    proto = InterAgentProtocol()
    proto.create_channel("builds")

    assert proto.subscribe("builds", "Builder") is True
    assert proto.subscribe("nonexistent", "Builder") is False

    channels = proto.list_channels()
    assert channels[0]["subscriber_count"] == 1

    assert proto.unsubscribe("builds", "Builder") is True
    assert proto.unsubscribe("builds", "Builder") is False
    print("OK: subscribe unsubscribe")


def test_send_direct():
    """Send a direct message."""
    proto = InterAgentProtocol()
    mid = proto.send("Builder", "Tester", "Review code", body={"file": "main.py"})
    assert mid.startswith("msg-")

    inbox = proto.get_inbox("Tester")
    assert len(inbox) == 1
    assert inbox[0]["sender"] == "Builder"
    assert inbox[0]["subject"] == "Review code"
    assert inbox[0]["body"]["file"] == "main.py"
    assert inbox[0]["msg_type"] == "direct"
    print("OK: send direct")


def test_broadcast():
    """Broadcast to channel subscribers."""
    proto = InterAgentProtocol()
    proto.create_channel("alerts")
    proto.subscribe("alerts", "Builder")
    proto.subscribe("alerts", "Tester")

    mid = proto.broadcast("System", "alerts", "Deploy starting")

    b_inbox = proto.get_inbox("Builder")
    t_inbox = proto.get_inbox("Tester")
    assert len(b_inbox) == 1
    assert len(t_inbox) == 1
    assert b_inbox[0]["subject"] == "Deploy starting"
    print("OK: broadcast")


def test_publish_to_channel():
    """Publish to a named channel."""
    received = []
    proto = InterAgentProtocol()
    proto.create_channel("events", handler=lambda m: received.append(m["subject"]))
    proto.subscribe("events", "Listener")

    mid = proto.publish("Source", "events", "New event")
    assert mid is not None

    inbox = proto.get_inbox("Listener")
    assert len(inbox) == 1
    assert received == ["New event"]

    # Nonexistent channel
    assert proto.publish("Source", "nonexistent", "x") is None
    print("OK: publish to channel")


def test_request_reply():
    """Request/reply pattern."""
    replies = []
    proto = InterAgentProtocol()

    cid = proto.request("Builder", "Tester", "Run tests?",
                         body={"module": "auth"},
                         reply_handler=lambda m: replies.append(m["body"]))
    assert cid.startswith("corr-")

    # Tester sees the request
    inbox = proto.get_inbox("Tester")
    assert len(inbox) == 1
    assert inbox[0]["msg_type"] == "request"

    # Tester replies
    reply_id = proto.reply("Tester", cid, body={"passed": True})
    assert reply_id is not None

    # Builder gets the reply
    b_inbox = proto.get_inbox("Builder")
    assert len(b_inbox) == 1
    assert b_inbox[0]["msg_type"] == "reply"
    assert b_inbox[0]["body"]["passed"] is True

    # Reply handler fired
    assert replies == [{"passed": True}]
    print("OK: request reply")


def test_reply_no_correlation():
    """Reply with invalid correlation returns None."""
    proto = InterAgentProtocol()
    assert proto.reply("Agent", "fake-corr", body="x") is None
    print("OK: reply no correlation")


def test_get_conversation():
    """Get all messages in a conversation."""
    proto = InterAgentProtocol()
    cid = proto.request("A", "B", "Question?")
    proto.reply("B", cid, body="Answer!")

    conv = proto.get_conversation(cid)
    assert len(conv) == 2
    assert conv[0]["msg_type"] == "request"
    assert conv[1]["msg_type"] == "reply"
    print("OK: get conversation")


def test_inbox_filters():
    """Filter inbox by subject and type."""
    proto = InterAgentProtocol()
    proto.send("A", "B", "Build report", body="ok")
    proto.send("A", "B", "Test report", body="ok")
    cid = proto.request("A", "B", "Need help?")

    all_msgs = proto.get_inbox("B")
    assert len(all_msgs) == 3

    build_msgs = proto.get_inbox("B", subject_filter="build")
    assert len(build_msgs) == 1

    requests = proto.get_inbox("B", msg_type="request")
    assert len(requests) == 1
    print("OK: inbox filters")


def test_inbox_count():
    """Get inbox count."""
    proto = InterAgentProtocol()
    proto.send("A", "B", "msg1")
    proto.send("A", "B", "msg2")

    assert proto.get_inbox_count("B") == 2
    assert proto.get_inbox_count("C") == 0
    print("OK: inbox count")


def test_clear_inbox():
    """Clear inbox."""
    proto = InterAgentProtocol()
    proto.send("A", "B", "msg1")
    proto.send("A", "B", "msg2")

    count = proto.clear_inbox("B")
    assert count == 2
    assert proto.get_inbox_count("B") == 0
    print("OK: clear inbox")


def test_agent_handler():
    """Register and fire agent message handler."""
    received = []
    proto = InterAgentProtocol()
    proto.register_handler("Builder", lambda m: received.append(m["subject"]))

    proto.send("System", "Builder", "Alert!")
    assert received == ["Alert!"]

    assert proto.unregister_handler("Builder") is True
    assert proto.unregister_handler("Builder") is False
    print("OK: agent handler")


def test_priority():
    """Messages have priority."""
    proto = InterAgentProtocol()
    proto.send("A", "B", "Low", priority=10)
    proto.send("A", "B", "High", priority=90)

    inbox = proto.get_inbox("B")
    assert len(inbox) == 2
    # Messages in inbox order (arrival), but priority is recorded
    assert inbox[0]["priority"] == 10
    assert inbox[1]["priority"] == 90
    print("OK: priority")


def test_get_message():
    """Get a specific message."""
    proto = InterAgentProtocol()
    mid = proto.send("A", "B", "Hello", body="world")

    msg = proto.get_message(mid)
    assert msg is not None
    assert msg["subject"] == "Hello"

    assert proto.get_message("nonexistent") is None
    print("OK: get message")


def test_get_history():
    """Get message history with filters."""
    proto = InterAgentProtocol()
    proto.send("A", "B", "msg1")
    proto.send("B", "A", "msg2")
    proto.send("A", "C", "msg3")

    all_h = proto.get_history()
    assert len(all_h) == 3

    from_a = proto.get_history(sender="A")
    assert len(from_a) == 2

    to_b = proto.get_history(recipient="B")
    assert len(to_b) == 1
    print("OK: get history")


def test_stats():
    """Stats are accurate."""
    proto = InterAgentProtocol()
    proto.create_channel("ch")
    proto.subscribe("ch", "listener")

    proto.send("A", "B", "direct")
    proto.broadcast("A", "ch", "broadcast")
    cid = proto.request("A", "B", "request")
    proto.reply("B", cid, "reply")

    stats = proto.get_stats()
    assert stats["total_sent"] == 4
    assert stats["total_broadcasts"] == 1
    assert stats["total_requests"] == 1
    assert stats["total_replies"] == 1
    assert stats["total_channels"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    proto = InterAgentProtocol()
    proto.create_channel("ch")
    proto.send("A", "B", "msg")

    proto.reset()
    assert proto.list_channels() == []
    assert proto.get_history() == []
    stats = proto.get_stats()
    assert stats["total_channels"] == 0
    print("OK: reset")


def main():
    print("=== Inter-Agent Protocol Tests ===\n")
    test_create_channel()
    test_delete_channel()
    test_subscribe_unsubscribe()
    test_send_direct()
    test_broadcast()
    test_publish_to_channel()
    test_request_reply()
    test_reply_no_correlation()
    test_get_conversation()
    test_inbox_filters()
    test_inbox_count()
    test_clear_inbox()
    test_agent_handler()
    test_priority()
    test_get_message()
    test_get_history()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
