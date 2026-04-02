"""Test agent communication protocol -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_communication_protocol import AgentCommunicationProtocol


def test_create_channel():
    cp = AgentCommunicationProtocol()
    cid = cp.create_channel("builds", channel_type="topic")
    assert cid.startswith("ach-")
    c = cp.get_channel("builds")
    assert c["name"] == "builds"
    assert c["channel_type"] == "topic"
    assert c["subscriber_count"] == 0
    assert cp.create_channel("builds") == ""  # dup
    print("OK: create channel")


def test_subscribe_unsubscribe():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    assert cp.subscribe("builds", "agent-1") is True
    assert cp.subscribe("builds", "agent-2") is True
    assert cp.subscribe("builds", "agent-1") is False  # dup
    c = cp.get_channel("builds")
    assert c["subscriber_count"] == 2
    assert cp.unsubscribe("builds", "agent-1") is True
    assert cp.unsubscribe("builds", "agent-1") is False
    assert cp.get_channel("builds")["subscriber_count"] == 1
    print("OK: subscribe unsubscribe")


def test_send_receive():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    cp.subscribe("builds", "agent-1")
    cp.subscribe("builds", "agent-2")
    mid = cp.send("builds", sender="agent-1", msg_type="notification", payload={"status": "success"})
    assert mid.startswith("msg-")
    # agent-2 should receive the message
    msgs = cp.receive("builds", "agent-2")
    assert len(msgs) >= 1
    assert msgs[0]["sender"] == "agent-1"
    assert msgs[0]["payload"]["status"] == "success"
    # second receive should return empty (already read)
    msgs2 = cp.receive("builds", "agent-2")
    assert len(msgs2) == 0
    print("OK: send receive")


def test_acknowledge():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    cp.subscribe("builds", "agent-1")
    mid = cp.send("builds", sender="system", msg_type="request", payload={"action": "deploy"}, requires_ack=True)
    cp.receive("builds", "agent-1")  # read it
    assert cp.acknowledge(mid, "agent-1") is True
    assert cp.acknowledge(mid, "agent-1") is False  # already acked
    unacked = cp.get_unacknowledged()
    assert len(unacked) == 0
    print("OK: acknowledge")


def test_unacknowledged():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    cp.subscribe("builds", "agent-1")
    cp.subscribe("builds", "agent-2")
    cp.send("builds", sender="sys", requires_ack=True, payload={"cmd": "restart"})
    unacked = cp.get_unacknowledged()
    assert len(unacked) >= 1
    print("OK: unacknowledged")


def test_get_message():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    mid = cp.send("builds", sender="sys", payload={"x": 1})
    m = cp.get_message(mid)
    assert m is not None
    assert m["sender"] == "sys"
    assert cp.get_message("nonexistent") is None
    print("OK: get message")


def test_list_channels():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds", channel_type="topic", tags=["ci"])
    cp.create_channel("alerts", channel_type="broadcast")
    assert len(cp.list_channels()) == 2
    assert len(cp.list_channels(channel_type="topic")) == 1
    assert len(cp.list_channels(tag="ci")) == 1
    print("OK: list channels")


def test_remove_channel():
    cp = AgentCommunicationProtocol()
    cp.create_channel("builds")
    assert cp.remove_channel("builds") is True
    assert cp.remove_channel("builds") is False
    assert cp.get_channel("builds") is None
    print("OK: remove channel")


def test_message_types():
    cp = AgentCommunicationProtocol()
    cp.create_channel("ch")
    cp.subscribe("ch", "a1")
    for mtype in ["request", "response", "notification", "broadcast"]:
        mid = cp.send("ch", sender="sys", msg_type=mtype)
        m = cp.get_message(mid)
        assert m["msg_type"] == mtype
    print("OK: message types")


def test_history():
    cp = AgentCommunicationProtocol()
    cp.create_channel("ch")
    cp.send("ch", sender="sys")
    hist = cp.get_history()
    assert len(hist) >= 2
    print("OK: history")


def test_callbacks():
    cp = AgentCommunicationProtocol()
    fired = []
    cp.on_change("mon", lambda a, d: fired.append(a))
    cp.create_channel("ch")
    assert "channel_created" in fired
    assert cp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cp = AgentCommunicationProtocol()
    cp.create_channel("ch")
    cp.send("ch", sender="sys")
    stats = cp.get_stats()
    assert stats["total_channels_created"] >= 1
    assert stats["total_messages_sent"] >= 1
    print("OK: stats")


def test_reset():
    cp = AgentCommunicationProtocol()
    cp.create_channel("ch")
    cp.reset()
    assert cp.list_channels() == []
    print("OK: reset")


def main():
    print("=== Agent Communication Protocol Tests ===\n")
    test_create_channel()
    test_subscribe_unsubscribe()
    test_send_receive()
    test_acknowledge()
    test_unacknowledged()
    test_get_message()
    test_list_channels()
    test_remove_channel()
    test_message_types()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
