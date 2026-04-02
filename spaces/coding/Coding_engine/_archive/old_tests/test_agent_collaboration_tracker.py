"""Test agent collaboration tracker."""
import sys
sys.path.insert(0, ".")

from src.services.agent_collaboration_tracker import AgentCollaborationTracker


def test_create_collaboration():
    """Create and remove collaboration."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("review_code", ["agent-1", "agent-2"],
                                   collab_type="review", tags=["code"])
    assert cid.startswith("collab-")

    c = ct.get_collaboration(cid)
    assert c is not None
    assert c["name"] == "review_code"
    assert c["collab_type"] == "review"
    assert c["status"] == "active"
    assert "agent-1" in c["agents"]
    assert "code" in c["tags"]

    assert ct.remove_collaboration(cid) is True
    assert ct.remove_collaboration(cid) is False
    print("OK: create collaboration")


def test_invalid_collaboration():
    """Invalid collaboration rejected."""
    ct = AgentCollaborationTracker()
    assert ct.create_collaboration("", ["a", "b"]) == ""
    assert ct.create_collaboration("x", []) == ""
    assert ct.create_collaboration("x", ["a"]) == ""  # Need at least 2
    assert ct.create_collaboration("x", ["a", "b"], collab_type="invalid") == ""
    print("OK: invalid collaboration")


def test_max_collabs():
    """Max collaborations enforced."""
    ct = AgentCollaborationTracker(max_collabs=2)
    ct.create_collaboration("a", ["x", "y"])
    ct.create_collaboration("b", ["x", "y"])
    assert ct.create_collaboration("c", ["x", "y"]) == ""
    print("OK: max collabs")


def test_end_collaboration():
    """End a collaboration."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("task", ["a", "b"])

    assert ct.end_collaboration(cid, status="completed", result="success") is True
    c = ct.get_collaboration(cid)
    assert c["status"] == "completed"
    assert c["result"] == "success"
    assert c["ended_at"] > 0

    assert ct.end_collaboration(cid) is False  # Already ended
    print("OK: end collaboration")


def test_end_with_statuses():
    """End with different statuses."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["x", "y"])
    c2 = ct.create_collaboration("b", ["x", "y"])
    c3 = ct.create_collaboration("c", ["x", "y"])

    ct.end_collaboration(c1, status="completed")
    ct.end_collaboration(c2, status="failed")
    ct.end_collaboration(c3, status="cancelled")

    assert ct.get_collaboration(c1)["status"] == "completed"
    assert ct.get_collaboration(c2)["status"] == "failed"
    assert ct.get_collaboration(c3)["status"] == "cancelled"
    print("OK: end with statuses")


def test_send_message():
    """Send messages within collaboration."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("chat", ["agent-1", "agent-2"])

    mid = ct.send_message(cid, "agent-1", "Hello!", msg_type="message")
    assert mid.startswith("msg-")

    mid2 = ct.send_message(cid, "agent-2", "Hi there!", msg_type="message")
    assert mid2.startswith("msg-")

    msgs = ct.get_messages(cid)
    assert len(msgs) == 2
    assert msgs[0]["content"] == "Hi there!"  # Newest first
    print("OK: send message")


def test_invalid_message():
    """Invalid message rejected."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("chat", ["agent-1", "agent-2"])

    assert ct.send_message("nonexistent", "agent-1", "hi") == ""
    assert ct.send_message(cid, "", "hi") == ""
    assert ct.send_message(cid, "agent-1", "") == ""
    assert ct.send_message(cid, "agent-1", "hi", msg_type="invalid") == ""
    assert ct.send_message(cid, "agent-3", "hi") == ""  # Not in collab
    print("OK: invalid message")


def test_message_to_ended_collab():
    """Cannot send message to ended collaboration."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("chat", ["a", "b"])
    ct.end_collaboration(cid)

    assert ct.send_message(cid, "a", "hello") == ""
    print("OK: message to ended collab")


def test_message_filtering():
    """Filter messages by sender and type."""
    ct = AgentCollaborationTracker()
    cid = ct.create_collaboration("discuss", ["a", "b"])

    ct.send_message(cid, "a", "proposal here", msg_type="proposal")
    ct.send_message(cid, "b", "I vote yes", msg_type="vote")
    ct.send_message(cid, "a", "decided", msg_type="decision")

    by_sender = ct.get_messages(cid, sender="a")
    assert len(by_sender) == 2

    by_type = ct.get_messages(cid, msg_type="vote")
    assert len(by_type) == 1
    assert by_type[0]["sender"] == "b"
    print("OK: message filtering")


def test_message_pruning():
    """Messages pruned when max exceeded."""
    ct = AgentCollaborationTracker(max_messages_per_collab=3)
    cid = ct.create_collaboration("chat", ["a", "b"])

    for i in range(5):
        ct.send_message(cid, "a", f"msg-{i}")

    msgs = ct.get_messages(cid)
    assert len(msgs) == 3
    print("OK: message pruning")


def test_list_collaborations():
    """List collaborations with filters."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["x", "y"], collab_type="pair", tags=["build"])
    c2 = ct.create_collaboration("b", ["x", "z"], collab_type="review")
    ct.end_collaboration(c1)

    all_c = ct.list_collaborations()
    assert len(all_c) == 2

    by_status = ct.list_collaborations(status="active")
    assert len(by_status) == 1

    by_type = ct.list_collaborations(collab_type="pair")
    assert len(by_type) == 1

    by_agent = ct.list_collaborations(agent="z")
    assert len(by_agent) == 1

    by_tag = ct.list_collaborations(tag="build")
    assert len(by_tag) == 1
    print("OK: list collaborations")


def test_active_collaborations():
    """Get active collaborations."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["x", "y"])
    c2 = ct.create_collaboration("b", ["x", "y"])
    ct.end_collaboration(c1)

    active = ct.get_active_collaborations()
    assert len(active) == 1
    print("OK: active collaborations")


def test_agent_collaborations():
    """Get collaborations for an agent."""
    ct = AgentCollaborationTracker()
    ct.create_collaboration("a", ["agent-1", "agent-2"])
    ct.create_collaboration("b", ["agent-1", "agent-3"])
    ct.create_collaboration("c", ["agent-2", "agent-3"])

    a1_collabs = ct.get_agent_collaborations("agent-1")
    assert len(a1_collabs) == 2
    print("OK: agent collaborations")


def test_agent_partners():
    """Get agent partners."""
    ct = AgentCollaborationTracker()
    ct.create_collaboration("a", ["agent-1", "agent-2"])
    ct.create_collaboration("b", ["agent-1", "agent-2"])
    ct.create_collaboration("c", ["agent-1", "agent-3"])

    partners = ct.get_agent_partners("agent-1")
    assert partners["agent-2"] == 2
    assert partners["agent-3"] == 1
    print("OK: agent partners")


def test_agent_stats():
    """Get agent collaboration stats."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["agent-1", "agent-2"])
    c2 = ct.create_collaboration("b", ["agent-1", "agent-3"])

    ct.send_message(c1, "agent-1", "hello")
    ct.send_message(c1, "agent-1", "world")
    ct.end_collaboration(c1)

    stats = ct.get_agent_stats("agent-1")
    assert stats["total_collaborations"] == 2
    assert stats["active"] == 1
    assert stats["completed"] == 1
    assert stats["messages_sent"] == 2

    assert ct.get_agent_stats("nonexistent") == {}
    print("OK: agent stats")


def test_most_active_agents():
    """Get most active agents."""
    ct = AgentCollaborationTracker()
    ct.create_collaboration("a", ["agent-1", "agent-2"])
    ct.create_collaboration("b", ["agent-1", "agent-3"])
    ct.create_collaboration("c", ["agent-2", "agent-3"])

    active = ct.get_most_active_agents(limit=2)
    assert len(active) == 2
    # agent-1 and agent-2 or agent-3 all have 2 collabs
    assert active[0]["collab_count"] == 2
    print("OK: most active agents")


def test_collab_type_summary():
    """Get summary by collaboration type."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["x", "y"], collab_type="pair")
    c2 = ct.create_collaboration("b", ["x", "y"], collab_type="pair")
    ct.create_collaboration("c", ["x", "y"], collab_type="review")
    ct.end_collaboration(c1)

    summary = ct.get_collab_type_summary()
    assert len(summary) == 2
    pair_sum = next(s for s in summary if s["collab_type"] == "pair")
    assert pair_sum["count"] == 2
    assert pair_sum["completed"] == 1
    print("OK: collab type summary")


def test_collab_created_callback():
    """Callback fires on creation."""
    ct = AgentCollaborationTracker()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))

    ct.create_collaboration("test", ["a", "b"])
    assert "collab_created" in fired
    print("OK: collab created callback")


def test_collab_completed_callback():
    """Callback fires on completion."""
    ct = AgentCollaborationTracker()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))

    cid = ct.create_collaboration("test", ["a", "b"])
    ct.end_collaboration(cid, status="completed")
    assert "collab_completed" in fired
    print("OK: collab completed callback")


def test_message_callback():
    """Callback fires on message."""
    ct = AgentCollaborationTracker()
    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))

    cid = ct.create_collaboration("test", ["a", "b"])
    ct.send_message(cid, "a", "hi")
    assert "message_sent" in fired
    print("OK: message callback")


def test_callbacks():
    """Callback registration."""
    ct = AgentCollaborationTracker()
    assert ct.on_change("mon", lambda a, d: None) is True
    assert ct.on_change("mon", lambda a, d: None) is False
    assert ct.remove_callback("mon") is True
    assert ct.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ct = AgentCollaborationTracker()
    c1 = ct.create_collaboration("a", ["x", "y"])
    c2 = ct.create_collaboration("b", ["x", "y"])

    ct.send_message(c1, "x", "hello")
    ct.end_collaboration(c1, status="completed")
    ct.end_collaboration(c2, status="failed")

    stats = ct.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_messages"] == 1
    assert stats["current_collabs"] == 2
    assert stats["active_collabs"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ct = AgentCollaborationTracker()
    ct.create_collaboration("test", ["a", "b"])

    ct.reset()
    assert ct.list_collaborations() == []
    stats = ct.get_stats()
    assert stats["current_collabs"] == 0
    print("OK: reset")


def main():
    print("=== Agent Collaboration Tracker Tests ===\n")
    test_create_collaboration()
    test_invalid_collaboration()
    test_max_collabs()
    test_end_collaboration()
    test_end_with_statuses()
    test_send_message()
    test_invalid_message()
    test_message_to_ended_collab()
    test_message_filtering()
    test_message_pruning()
    test_list_collaborations()
    test_active_collaborations()
    test_agent_collaborations()
    test_agent_partners()
    test_agent_stats()
    test_most_active_agents()
    test_collab_type_summary()
    test_collab_created_callback()
    test_collab_completed_callback()
    test_message_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 23 TESTS PASSED ===")


if __name__ == "__main__":
    main()
