"""Test agent communication logger."""
import sys
sys.path.insert(0, ".")

from src.services.agent_communication_logger import AgentCommunicationLogger


def test_log_comm():
    """Log and retrieve comm entry."""
    cl = AgentCommunicationLogger()
    eid = cl.log_comm("alice", "bob", channel="dev",
                      msg_type="message", content_summary="hello",
                      size_bytes=100, tags=["chat"])
    assert eid.startswith("comm-")

    e = cl.get_entry(eid)
    assert e is not None
    assert e["sender"] == "alice"
    assert e["receiver"] == "bob"
    assert e["channel"] == "dev"
    assert e["msg_type"] == "message"
    assert e["size_bytes"] == 100

    assert cl.remove_entry(eid) is True
    assert cl.remove_entry(eid) is False
    print("OK: log comm")


def test_invalid_comm():
    """Invalid comm rejected."""
    cl = AgentCommunicationLogger()
    assert cl.log_comm("", "bob") == ""
    assert cl.log_comm("alice", "") == ""
    assert cl.log_comm("alice", "bob", msg_type="invalid") == ""
    print("OK: invalid comm")


def test_create_thread():
    """Create and manage thread."""
    cl = AgentCommunicationLogger()
    tid = cl.create_thread("deploy discussion",
                           participants=["alice", "bob"])
    assert tid.startswith("thr-")

    t = cl.get_thread(tid)
    assert t is not None
    assert t["subject"] == "deploy discussion"
    assert len(t["participants"]) == 2
    assert t["status"] == "active"

    assert cl.close_thread(tid) is True
    assert cl.get_thread(tid)["status"] == "closed"
    assert cl.close_thread(tid) is False

    assert cl.remove_thread(tid) is True
    assert cl.remove_thread(tid) is False
    print("OK: create thread")


def test_invalid_thread():
    """Invalid thread rejected."""
    cl = AgentCommunicationLogger()
    assert cl.create_thread("") == ""
    print("OK: invalid thread")


def test_max_threads():
    """Max threads enforced."""
    cl = AgentCommunicationLogger(max_threads=2)
    cl.create_thread("a")
    cl.create_thread("b")
    assert cl.create_thread("c") == ""
    print("OK: max threads")


def test_thread_entries():
    """Get entries in thread."""
    cl = AgentCommunicationLogger()
    tid = cl.create_thread("deploy")
    cl.log_comm("alice", "bob", thread_id=tid, content_summary="start")
    cl.log_comm("bob", "alice", thread_id=tid, content_summary="ok")

    t = cl.get_thread(tid)
    assert t["entry_count"] == 2
    assert "alice" in t["participants"]
    assert "bob" in t["participants"]

    entries = cl.get_thread_entries(tid)
    assert len(entries) == 2
    assert entries[0]["content_summary"] == "start"
    assert entries[1]["content_summary"] == "ok"
    print("OK: thread entries")


def test_search_entries():
    """Search entries with filters."""
    cl = AgentCommunicationLogger()
    cl.log_comm("alice", "bob", channel="dev", msg_type="message", tags=["chat"])
    cl.log_comm("bob", "charlie", channel="ops", msg_type="request")
    cl.log_comm("alice", "charlie", channel="dev", msg_type="response")

    by_sender = cl.search_entries(sender="alice")
    assert len(by_sender) == 2

    by_receiver = cl.search_entries(receiver="charlie")
    assert len(by_receiver) == 2

    by_channel = cl.search_entries(channel="dev")
    assert len(by_channel) == 2

    by_type = cl.search_entries(msg_type="request")
    assert len(by_type) == 1

    by_tag = cl.search_entries(tag="chat")
    assert len(by_tag) == 1
    print("OK: search entries")


def test_search_limit():
    """Search respects limit."""
    cl = AgentCommunicationLogger()
    for i in range(20):
        cl.log_comm("a", "b")

    results = cl.search_entries(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_agent_comm_stats():
    """Get agent communication stats."""
    cl = AgentCommunicationLogger()
    cl.log_comm("alice", "bob", size_bytes=100)
    cl.log_comm("alice", "charlie", size_bytes=200)
    cl.log_comm("bob", "alice", size_bytes=50)

    stats = cl.get_agent_comm_stats("alice")
    assert stats["messages_sent"] == 2
    assert stats["messages_received"] == 1
    assert stats["bytes_sent"] == 300
    assert stats["bytes_received"] == 50
    print("OK: agent comm stats")


def test_channel_volume():
    """Get channel volume."""
    cl = AgentCommunicationLogger()
    cl.log_comm("a", "b", channel="dev")
    cl.log_comm("a", "b", channel="dev")
    cl.log_comm("a", "b", channel="ops")

    volume = cl.get_channel_volume()
    assert volume["dev"] == 2
    assert volume["ops"] == 1
    print("OK: channel volume")


def test_msg_type_counts():
    """Get message type counts."""
    cl = AgentCommunicationLogger()
    cl.log_comm("a", "b", msg_type="message")
    cl.log_comm("a", "b", msg_type="request")
    cl.log_comm("a", "b", msg_type="request")

    counts = cl.get_msg_type_counts()
    assert counts["message"] == 1
    assert counts["request"] == 2
    assert counts["response"] == 0
    print("OK: msg type counts")


def test_busiest_pairs():
    """Get busiest comm pairs."""
    cl = AgentCommunicationLogger()
    cl.log_comm("alice", "bob")
    cl.log_comm("alice", "bob")
    cl.log_comm("alice", "bob")
    cl.log_comm("bob", "charlie")

    pairs = cl.get_busiest_pairs()
    assert len(pairs) == 2
    assert pairs[0]["pair"] == "alice->bob"
    assert pairs[0]["count"] == 3
    print("OK: busiest pairs")


def test_list_threads():
    """List threads with filter."""
    cl = AgentCommunicationLogger()
    t1 = cl.create_thread("active_one")
    t2 = cl.create_thread("closed_one")
    cl.close_thread(t2)

    all_t = cl.list_threads()
    assert len(all_t) == 2

    active = cl.list_threads(status="active")
    assert len(active) == 1
    print("OK: list threads")


def test_comm_callback():
    """Callback fires on comm log."""
    cl = AgentCommunicationLogger()
    fired = []
    cl.on_change("mon", lambda a, d: fired.append(a))

    cl.log_comm("a", "b")
    assert "comm_logged" in fired
    print("OK: comm callback")


def test_callbacks():
    """Callback registration."""
    cl = AgentCommunicationLogger()
    assert cl.on_change("mon", lambda a, d: None) is True
    assert cl.on_change("mon", lambda a, d: None) is False
    assert cl.remove_callback("mon") is True
    assert cl.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    cl = AgentCommunicationLogger()
    cl.log_comm("a", "b", size_bytes=100)
    tid = cl.create_thread("t")
    cl.close_thread(tid)

    stats = cl.get_stats()
    assert stats["total_entries_logged"] == 1
    assert stats["total_bytes_logged"] == 100
    assert stats["total_threads_created"] == 1
    assert stats["total_threads_closed"] == 1
    assert stats["current_entries"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    cl = AgentCommunicationLogger()
    cl.log_comm("a", "b")
    cl.create_thread("t")

    cl.reset()
    assert cl.search_entries() == []
    assert cl.list_threads() == []
    stats = cl.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Agent Communication Logger Tests ===\n")
    test_log_comm()
    test_invalid_comm()
    test_create_thread()
    test_invalid_thread()
    test_max_threads()
    test_thread_entries()
    test_search_entries()
    test_search_limit()
    test_agent_comm_stats()
    test_channel_volume()
    test_msg_type_counts()
    test_busiest_pairs()
    test_list_threads()
    test_comm_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
