"""Test agent messenger communication protocol."""
import sys
import time
sys.path.insert(0, ".")

from src.services.agent_messenger import (
    AgentMessenger,
    MessagePriority,
    MessageType,
    DeliveryStatus,
)


def test_direct_message():
    """Send a direct message between agents."""
    m = AgentMessenger()
    msg_id = m.send("Builder", "Tester", "Build complete", topic="handoff")

    assert msg_id.startswith("msg-")
    inbox = m.get_inbox("Tester")
    assert len(inbox) == 1
    assert inbox[0]["sender"] == "Builder"
    assert inbox[0]["body"] == "Build complete"
    assert inbox[0]["topic"] == "handoff"
    assert inbox[0]["is_read"] is False
    print("OK: direct message")


def test_multiple_messages():
    """Multiple messages delivered in order."""
    m = AgentMessenger()
    m.send("A", "B", "First")
    m.send("A", "B", "Second")
    m.send("C", "B", "Third")

    inbox = m.get_inbox("B")
    assert len(inbox) == 3

    # Different sender
    m.send("A", "D", "For D")
    d_inbox = m.get_inbox("D")
    assert len(d_inbox) == 1
    print("OK: multiple messages")


def test_read_unread():
    """Mark messages as read/unread."""
    m = AgentMessenger()
    msg1 = m.send("A", "B", "Message 1")
    msg2 = m.send("A", "B", "Message 2")

    assert m.get_unread_count("B") == 2

    m.mark_read("B", msg1)
    assert m.get_unread_count("B") == 1

    # Unread only filter
    unread = m.get_inbox("B", unread_only=True)
    assert len(unread) == 1
    assert unread[0]["message_id"] == msg2

    # Mark all read
    m.mark_all_read("B")
    assert m.get_unread_count("B") == 0
    print("OK: read unread")


def test_priority_ordering():
    """High priority messages appear first in inbox."""
    m = AgentMessenger()
    m.send("A", "B", "Low", priority=MessagePriority.LOW)
    m.send("A", "B", "Normal", priority=MessagePriority.NORMAL)
    m.send("A", "B", "Urgent", priority=MessagePriority.URGENT)

    inbox = m.get_inbox("B")
    assert inbox[0]["body"] == "Urgent"
    assert inbox[1]["body"] == "Normal"
    assert inbox[2]["body"] == "Low"
    print("OK: priority ordering")


def test_topic_filter():
    """Filter inbox by topic."""
    m = AgentMessenger()
    m.send("A", "B", "Build done", topic="build")
    m.send("A", "B", "Test done", topic="test")
    m.send("A", "B", "Deploy done", topic="deploy")

    build_msgs = m.get_inbox("B", topic="build")
    assert len(build_msgs) == 1
    assert build_msgs[0]["topic"] == "build"
    print("OK: topic filter")


def test_message_ttl():
    """Messages expire after TTL."""
    m = AgentMessenger()
    m.send("A", "B", "Ephemeral", ttl_seconds=0.05)
    m.send("A", "B", "Persistent")

    assert len(m.get_inbox("B")) == 2

    time.sleep(0.1)

    # Expired messages cleaned on inbox access
    inbox = m.get_inbox("B")
    assert len(inbox) == 1
    assert inbox[0]["body"] == "Persistent"
    print("OK: message TTL")


def test_delete_message():
    """Delete specific message from inbox."""
    m = AgentMessenger()
    msg1 = m.send("A", "B", "Keep")
    msg2 = m.send("A", "B", "Delete me")

    assert m.delete_message("B", msg2) is True
    inbox = m.get_inbox("B")
    assert len(inbox) == 1
    assert inbox[0]["body"] == "Keep"

    # Delete nonexistent
    assert m.delete_message("B", "nope") is False
    print("OK: delete message")


def test_clear_inbox():
    """Clear all messages."""
    m = AgentMessenger()
    m.send("A", "B", "One")
    m.send("A", "B", "Two")
    m.send("A", "B", "Three")

    cleared = m.clear_inbox("B")
    assert cleared == 3
    assert len(m.get_inbox("B")) == 0
    print("OK: clear inbox")


def test_create_channel():
    """Create and manage channels."""
    m = AgentMessenger()
    ch = m.create_channel("build-status", description="Build updates", creator="System")

    assert ch.name == "build-status"
    assert ch.description == "Build updates"

    # Duplicate returns existing
    ch2 = m.create_channel("build-status")
    assert ch2 is ch

    channels = m.list_channels()
    assert len(channels) == 1
    assert channels[0]["name"] == "build-status"
    print("OK: create channel")


def test_subscribe_unsubscribe():
    """Subscribe and unsubscribe from channels."""
    m = AgentMessenger()
    m.create_channel("updates")

    assert m.subscribe("updates", "Tester") is True
    assert m.subscribe("updates", "Deployer") is True
    assert m.subscribe("updates", "Tester") is False  # Already subscribed

    subs = m.get_channel_subscribers("updates")
    assert "Tester" in subs
    assert "Deployer" in subs

    assert m.unsubscribe("updates", "Tester") is True
    assert m.unsubscribe("updates", "Tester") is False  # Already unsubbed

    subs = m.get_channel_subscribers("updates")
    assert "Tester" not in subs
    print("OK: subscribe unsubscribe")


def test_broadcast():
    """Broadcast to channel subscribers."""
    m = AgentMessenger()
    m.create_channel("alerts")
    m.subscribe("alerts", "Tester")
    m.subscribe("alerts", "Deployer")
    m.subscribe("alerts", "Monitor")

    msg_id = m.broadcast("alerts", "Builder", "Build v1.2 succeeded")
    assert msg_id != ""

    # All subscribers except sender receive
    assert len(m.get_inbox("Tester")) == 1
    assert len(m.get_inbox("Deployer")) == 1
    assert len(m.get_inbox("Monitor")) == 1

    # Sender doesn't receive own broadcast
    assert len(m.get_inbox("Builder")) == 0

    # Check message content
    tester_msg = m.get_inbox("Tester")[0]
    assert tester_msg["channel"] == "alerts"
    assert tester_msg["msg_type"] == "broadcast"
    print("OK: broadcast")


def test_broadcast_nonexistent_channel():
    """Broadcast to nonexistent channel returns empty."""
    m = AgentMessenger()
    msg_id = m.broadcast("nope", "Builder", "Nobody listening")
    assert msg_id == ""
    print("OK: broadcast nonexistent channel")


def test_request_reply():
    """Request/reply pattern with correlation IDs."""
    m = AgentMessenger()
    req_id = m.request("Builder", "Planner", "Need architecture review")

    assert req_id.startswith("req-")

    # Planner sees the request in inbox
    planner_inbox = m.get_inbox("Planner")
    assert len(planner_inbox) == 1
    assert planner_inbox[0]["msg_type"] == "request"
    assert planner_inbox[0]["correlation_id"] == req_id

    # Planner's incoming requests
    incoming = m.get_incoming_requests("Planner")
    assert len(incoming) == 1
    assert incoming[0]["sender"] == "Builder"

    # Builder's pending requests
    pending = m.get_pending_requests("Builder")
    assert len(pending) == 1

    # Planner replies
    reply_id = m.reply(req_id, "Planner", "Approved with JWT suggestion")
    assert reply_id is not None

    # Builder gets the reply
    builder_inbox = m.get_inbox("Builder")
    assert len(builder_inbox) == 1
    assert builder_inbox[0]["msg_type"] == "reply"
    assert builder_inbox[0]["correlation_id"] == req_id

    # No more pending
    pending = m.get_pending_requests("Builder")
    assert len(pending) == 0
    print("OK: request reply")


def test_reply_nonexistent():
    """Reply to nonexistent request returns None."""
    m = AgentMessenger()
    result = m.reply("req-nonexistent", "Agent", "Hello?")
    assert result is None
    print("OK: reply nonexistent")


def test_conversation_history():
    """Get conversation between two agents."""
    m = AgentMessenger()
    m.send("Builder", "Tester", "Here's the build")
    m.send("Tester", "Builder", "Found 3 bugs")
    m.send("Builder", "Tester", "Fixed, rebuilding")
    m.send("Builder", "Deployer", "Unrelated msg")

    convo = m.get_conversation("Builder", "Tester")
    assert len(convo) == 3
    assert all(
        (c["sender"] in ("Builder", "Tester") and c["recipient"] in ("Builder", "Tester"))
        for c in convo
    )
    print("OK: conversation history")


def test_message_lookup():
    """Look up a specific message."""
    m = AgentMessenger()
    msg_id = m.send("A", "B", "Important", topic="critical")

    info = m.get_message(msg_id)
    assert info is not None
    assert info["sender"] == "A"
    assert info["body"] == "Important"
    assert info["topic"] == "critical"

    # Nonexistent
    assert m.get_message("nope") is None
    print("OK: message lookup")


def test_on_message_callback():
    """Callbacks fire on message delivery."""
    m = AgentMessenger()
    received = []

    m.on_message("Tester", lambda msg: received.append(msg.body))

    m.send("Builder", "Tester", "Callback test")
    assert len(received) == 1
    assert received[0] == "Callback test"

    # Broadcast also triggers
    m.create_channel("ch")
    m.subscribe("ch", "Tester")
    m.broadcast("ch", "Builder", "Broadcast callback")
    assert len(received) == 2
    print("OK: on message callback")


def test_metadata():
    """Messages carry metadata."""
    m = AgentMessenger()
    msg_id = m.send(
        "Builder", "Tester", "Build complete",
        metadata={"build_id": "b-123", "artifacts": ["app.js"]},
    )

    inbox = m.get_inbox("Tester")
    assert inbox[0]["metadata"]["build_id"] == "b-123"
    assert "app.js" in inbox[0]["metadata"]["artifacts"]
    print("OK: metadata")


def test_stats():
    """Messenger stats are accurate."""
    m = AgentMessenger()
    m.create_channel("ch1")
    m.subscribe("ch1", "B")

    m.send("A", "B", "Direct")
    m.broadcast("ch1", "A", "Broadcast")
    req_id = m.request("A", "B", "Request")
    m.reply(req_id, "B", "Reply")

    stats = m.get_stats()
    assert stats["total_sent"] == 1  # Only direct sends count
    assert stats["total_broadcasts"] == 1
    assert stats["total_requests"] == 1
    assert stats["total_replies"] == 1
    assert stats["total_channels"] == 1
    assert stats["pending_requests"] == 0
    print("OK: stats")


def test_cleanup_expired():
    """Cleanup expired across all inboxes."""
    m = AgentMessenger()
    m.send("A", "B", "Expire 1", ttl_seconds=0.05)
    m.send("A", "C", "Expire 2", ttl_seconds=0.05)
    m.send("A", "B", "Keep")

    time.sleep(0.1)

    cleaned = m.cleanup_expired()
    assert cleaned == 2
    assert len(m.get_inbox("B")) == 1
    assert len(m.get_inbox("C")) == 0
    print("OK: cleanup expired")


def test_reset():
    """Reset clears everything."""
    m = AgentMessenger()
    m.send("A", "B", "Msg")
    m.create_channel("ch")

    m.reset()
    assert m.get_inbox("B") == []
    assert m.list_channels() == []
    assert m.get_stats()["total_sent"] == 0
    print("OK: reset")


def test_inbox_limit():
    """Inbox enforces max_history limit."""
    m = AgentMessenger(max_history=5)

    for i in range(10):
        m.send("A", "B", f"Msg {i}")

    inbox = m.get_inbox("B")
    assert len(inbox) == 5
    # Should have the latest 5
    bodies = [msg["body"] for msg in inbox]
    assert "Msg 5" in bodies
    assert "Msg 9" in bodies
    print("OK: inbox limit")


def test_delete_channel():
    """Delete a channel."""
    m = AgentMessenger()
    m.create_channel("temp")
    m.subscribe("temp", "A")

    assert m.delete_channel("temp") is True
    assert m.delete_channel("temp") is False  # Already deleted
    assert m.get_channel("temp") is None
    print("OK: delete channel")


def main():
    print("=== Agent Messenger Tests ===\n")
    test_direct_message()
    test_multiple_messages()
    test_read_unread()
    test_priority_ordering()
    test_topic_filter()
    test_message_ttl()
    test_delete_message()
    test_clear_inbox()
    test_create_channel()
    test_subscribe_unsubscribe()
    test_broadcast()
    test_broadcast_nonexistent_channel()
    test_request_reply()
    test_reply_nonexistent()
    test_conversation_history()
    test_message_lookup()
    test_on_message_callback()
    test_metadata()
    test_stats()
    test_cleanup_expired()
    test_reset()
    test_inbox_limit()
    test_delete_channel()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
