"""Test agent communication hub -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_communication_hub import AgentCommunicationHub


def test_send_message():
    hub = AgentCommunicationHub()
    mid = hub.send_message("agent-1", "agent-2", "hello")
    assert len(mid) > 0
    assert mid.startswith("ach-")
    print("OK: send message")


def test_get_message():
    hub = AgentCommunicationHub()
    mid = hub.send_message("agent-1", "agent-2", "hello")
    msg = hub.get_message(mid)
    assert msg is not None
    assert msg["from_agent"] == "agent-1"
    assert msg["to_agent"] == "agent-2"
    assert msg["content"] == "hello"
    assert msg["read"] is False
    assert hub.get_message("nonexistent") is None
    print("OK: get message")


def test_get_inbox():
    hub = AgentCommunicationHub()
    hub.send_message("agent-1", "agent-2", "msg1")
    hub.send_message("agent-3", "agent-2", "msg2")
    hub.send_message("agent-1", "agent-3", "msg3")
    inbox = hub.get_inbox("agent-2")
    assert len(inbox) == 2
    print("OK: get inbox")


def test_get_outbox():
    hub = AgentCommunicationHub()
    hub.send_message("agent-1", "agent-2", "msg1")
    hub.send_message("agent-1", "agent-3", "msg2")
    hub.send_message("agent-2", "agent-1", "msg3")
    outbox = hub.get_outbox("agent-1")
    assert len(outbox) == 2
    print("OK: get outbox")


def test_broadcast():
    hub = AgentCommunicationHub()
    mid = hub.broadcast("agent-1", "attention all")
    msg = hub.get_message(mid)
    assert msg is not None
    assert msg["to_agent"] == "*"
    assert msg["msg_type"] == "broadcast"
    print("OK: broadcast")


def test_mark_read():
    hub = AgentCommunicationHub()
    mid = hub.send_message("agent-1", "agent-2", "hello")
    assert hub.mark_read(mid) is True
    msg = hub.get_message(mid)
    assert msg["read"] is True
    assert hub.mark_read("nonexistent") is False
    print("OK: mark read")


def test_delete_message():
    hub = AgentCommunicationHub()
    mid = hub.send_message("agent-1", "agent-2", "hello")
    assert hub.delete_message(mid) is True
    assert hub.delete_message(mid) is False
    print("OK: delete message")


def test_get_unread_count():
    hub = AgentCommunicationHub()
    m1 = hub.send_message("agent-1", "agent-2", "msg1")
    hub.send_message("agent-1", "agent-2", "msg2")
    assert hub.get_unread_count("agent-2") == 2
    hub.mark_read(m1)
    assert hub.get_unread_count("agent-2") == 1
    print("OK: get unread count")


def test_list_agents():
    hub = AgentCommunicationHub()
    hub.send_message("agent-1", "agent-2", "hello")
    agents = hub.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    hub = AgentCommunicationHub()
    fired = []
    hub.on_change("mon", lambda a, d: fired.append(a))
    hub.send_message("agent-1", "agent-2", "hello")
    assert len(fired) >= 1
    assert hub.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    hub = AgentCommunicationHub()
    hub.send_message("agent-1", "agent-2", "hello")
    stats = hub.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    hub = AgentCommunicationHub()
    hub.send_message("agent-1", "agent-2", "hello")
    hub.reset()
    assert hub.get_message_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Communication Hub Tests ===\n")
    test_send_message()
    test_get_message()
    test_get_inbox()
    test_get_outbox()
    test_broadcast()
    test_mark_read()
    test_delete_message()
    test_get_unread_count()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
