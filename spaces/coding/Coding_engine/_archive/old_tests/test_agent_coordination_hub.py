"""Test agent coordination hub."""
import sys
sys.path.insert(0, ".")

from src.services.agent_coordination_hub import AgentCoordinationHub


def test_create_channel():
    """Create and remove channel."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("general", channel_type="broadcast",
                              members=["agent-1"], tags=["team"])
    assert cid.startswith("ch-")

    c = hub.get_channel(cid)
    assert c is not None
    assert c["name"] == "general"
    assert c["channel_type"] == "broadcast"
    assert c["status"] == "active"
    assert "agent-1" in c["members"]
    assert "team" in c["tags"]

    assert hub.remove_channel(cid) is True
    assert hub.remove_channel(cid) is False
    print("OK: create channel")


def test_invalid_channel():
    """Invalid channel rejected."""
    hub = AgentCoordinationHub()
    assert hub.create_channel("") == ""
    assert hub.create_channel("x", channel_type="invalid") == ""
    print("OK: invalid channel")


def test_max_channels():
    """Max channels enforced."""
    hub = AgentCoordinationHub(max_channels=2)
    hub.create_channel("a")
    hub.create_channel("b")
    assert hub.create_channel("c") == ""
    print("OK: max channels")


def test_archive_channel():
    """Archive a channel."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("old")
    assert hub.archive_channel(cid) is True
    assert hub.get_channel(cid)["status"] == "archived"
    assert hub.archive_channel(cid) is False
    print("OK: archive channel")


def test_join_leave_channel():
    """Join and leave channel."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("dev")

    assert hub.join_channel(cid, "agent-1") is True
    assert hub.join_channel(cid, "agent-1") is False  # Already member
    assert hub.get_channel(cid)["member_count"] == 1

    assert hub.leave_channel(cid, "agent-1") is True
    assert hub.leave_channel(cid, "agent-1") is False
    assert hub.get_channel(cid)["member_count"] == 0
    print("OK: join leave channel")


def test_send_message():
    """Send and retrieve message."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("dev")

    mid = hub.send_message(cid, "agent-1", "hello!", msg_type="text")
    assert mid.startswith("msg-")

    m = hub.get_message(mid)
    assert m is not None
    assert m["sender"] == "agent-1"
    assert m["content"] == "hello!"
    assert m["msg_type"] == "text"

    assert hub.get_channel(cid)["message_count"] == 1
    print("OK: send message")


def test_invalid_message():
    """Invalid message rejected."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("dev")

    assert hub.send_message(cid, "", "x") == ""
    assert hub.send_message(cid, "a", "") == ""
    assert hub.send_message(cid, "a", "x", msg_type="invalid") == ""
    assert hub.send_message("nonexistent", "a", "x") == ""
    print("OK: invalid message")


def test_archived_channel_no_send():
    """Can't send to archived channel."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("old")
    hub.archive_channel(cid)
    assert hub.send_message(cid, "a", "x") == ""
    print("OK: archived channel no send")


def test_channel_messages():
    """Get channel messages."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("dev")
    hub.send_message(cid, "a", "first")
    hub.send_message(cid, "b", "second")

    msgs = hub.get_channel_messages(cid)
    assert len(msgs) == 2
    # Most recent first
    assert msgs[0]["content"] == "second"
    print("OK: channel messages")


def test_broadcast():
    """Broadcast to all broadcast channels."""
    hub = AgentCoordinationHub()
    hub.create_channel("bc1", channel_type="broadcast")
    hub.create_channel("bc2", channel_type="broadcast")
    hub.create_channel("direct1", channel_type="direct")

    sent = hub.broadcast("system", "alert!", msg_type="alert")
    assert len(sent) == 2  # Only broadcast channels
    print("OK: broadcast")


def test_create_task():
    """Create coordination task."""
    hub = AgentCoordinationHub()
    tid = hub.create_task("review_pr", coordinator="lead",
                          assigned_to=["agent-1", "agent-2"], priority=5)
    assert tid.startswith("ctask-")

    t = hub.get_task(tid)
    assert t is not None
    assert t["name"] == "review_pr"
    assert t["coordinator"] == "lead"
    assert len(t["assigned_to"]) == 2
    assert t["status"] == "pending"
    print("OK: create task")


def test_task_lifecycle():
    """Task start/complete/fail lifecycle."""
    hub = AgentCoordinationHub()
    tid = hub.create_task("build")

    assert hub.start_task(tid) is True
    assert hub.get_task(tid)["status"] == "active"
    assert hub.start_task(tid) is False

    assert hub.complete_task(tid) is True
    assert hub.get_task(tid)["status"] == "completed"
    assert hub.complete_task(tid) is False
    print("OK: task lifecycle")


def test_fail_task():
    """Fail a task."""
    hub = AgentCoordinationHub()
    tid = hub.create_task("risky")
    hub.start_task(tid)

    assert hub.fail_task(tid) is True
    assert hub.get_task(tid)["status"] == "failed"
    print("OK: fail task")


def test_remove_task():
    """Remove a task."""
    hub = AgentCoordinationHub()
    tid = hub.create_task("temp")
    assert hub.remove_task(tid) is True
    assert hub.remove_task(tid) is False
    print("OK: remove task")


def test_agent_channels():
    """Get channels for an agent."""
    hub = AgentCoordinationHub()
    c1 = hub.create_channel("dev", members=["agent-1"])
    c2 = hub.create_channel("ops", members=["agent-2"])
    hub.join_channel(c2, "agent-1")

    channels = hub.get_agent_channels("agent-1")
    assert len(channels) == 2
    print("OK: agent channels")


def test_agent_tasks():
    """Get tasks for an agent."""
    hub = AgentCoordinationHub()
    hub.create_task("a", assigned_to=["agent-1"])
    t2 = hub.create_task("b", assigned_to=["agent-1"])
    hub.start_task(t2)
    hub.complete_task(t2)
    hub.create_task("c", assigned_to=["agent-2"])

    all_t = hub.get_agent_tasks("agent-1")
    assert len(all_t) == 2

    active = hub.get_agent_tasks("agent-1", status="pending")
    assert len(active) == 1
    print("OK: agent tasks")


def test_list_channels():
    """List channels with filters."""
    hub = AgentCoordinationHub()
    hub.create_channel("a", tags=["team"])
    c2 = hub.create_channel("b")
    hub.archive_channel(c2)

    all_c = hub.list_channels()
    assert len(all_c) == 2

    active = hub.list_channels(status="active")
    assert len(active) == 1

    by_tag = hub.list_channels(tag="team")
    assert len(by_tag) == 1
    print("OK: list channels")


def test_list_tasks():
    """List tasks with filters."""
    hub = AgentCoordinationHub()
    hub.create_task("a", coordinator="lead")
    t2 = hub.create_task("b")
    hub.start_task(t2)

    all_t = hub.list_tasks()
    assert len(all_t) == 2

    by_status = hub.list_tasks(status="active")
    assert len(by_status) == 1

    by_coord = hub.list_tasks(coordinator="lead")
    assert len(by_coord) == 1
    print("OK: list tasks")


def test_all_agents():
    """Get all agents."""
    hub = AgentCoordinationHub()
    hub.create_channel("a", members=["charlie", "alice"])
    hub.create_channel("b", members=["bob", "alice"])

    agents = hub.get_all_agents()
    assert agents == ["alice", "bob", "charlie"]
    print("OK: all agents")


def test_message_callback():
    """Callback fires on message send."""
    hub = AgentCoordinationHub()
    fired = []
    hub.on_change("mon", lambda a, d: fired.append(a))

    cid = hub.create_channel("dev")
    hub.send_message(cid, "agent-1", "hello")
    assert "message_sent" in fired
    print("OK: message callback")


def test_callbacks():
    """Callback registration."""
    hub = AgentCoordinationHub()
    assert hub.on_change("mon", lambda a, d: None) is True
    assert hub.on_change("mon", lambda a, d: None) is False
    assert hub.remove_callback("mon") is True
    assert hub.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    hub = AgentCoordinationHub()
    cid = hub.create_channel("dev")
    hub.send_message(cid, "a", "hi")
    tid = hub.create_task("x")
    hub.start_task(tid)
    hub.complete_task(tid)

    stats = hub.get_stats()
    assert stats["total_channels_created"] == 1
    assert stats["total_messages_sent"] == 1
    assert stats["total_tasks_created"] == 1
    assert stats["total_tasks_completed"] == 1
    assert stats["current_channels"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    hub = AgentCoordinationHub()
    hub.create_channel("dev")
    hub.create_task("x")

    hub.reset()
    assert hub.list_channels() == []
    assert hub.list_tasks() == []
    stats = hub.get_stats()
    assert stats["current_channels"] == 0
    print("OK: reset")


def main():
    print("=== Agent Coordination Hub Tests ===\n")
    test_create_channel()
    test_invalid_channel()
    test_max_channels()
    test_archive_channel()
    test_join_leave_channel()
    test_send_message()
    test_invalid_message()
    test_archived_channel_no_send()
    test_channel_messages()
    test_broadcast()
    test_create_task()
    test_task_lifecycle()
    test_fail_task()
    test_remove_task()
    test_agent_channels()
    test_agent_tasks()
    test_list_channels()
    test_list_tasks()
    test_all_agents()
    test_message_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
