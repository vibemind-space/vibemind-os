"""Test agent collaboration store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_collaboration_store import AgentCollaborationStore


def test_start_collaboration():
    cs = AgentCollaborationStore()
    cid = cs.start_collaboration(["agent-1", "agent-2"], "build feature", metadata={"sprint": 5})
    assert len(cid) > 0
    assert cid.startswith("aco-")
    c = cs.get_collaboration(cid)
    assert c is not None
    assert c["status"] == "active"
    print("OK: start collaboration")


def test_end_collaboration():
    cs = AgentCollaborationStore()
    cid = cs.start_collaboration(["a1", "a2"], "task")
    assert cs.end_collaboration(cid, result={"output": "done"}) is True
    c = cs.get_collaboration(cid)
    assert c["status"] == "completed"
    assert cs.end_collaboration(cid) is False
    print("OK: end collaboration")


def test_cancel_collaboration():
    cs = AgentCollaborationStore()
    cid = cs.start_collaboration(["a1", "a2"], "task")
    assert cs.cancel_collaboration(cid) is True
    c = cs.get_collaboration(cid)
    assert c["status"] == "cancelled"
    print("OK: cancel collaboration")


def test_get_agent_collaborations():
    cs = AgentCollaborationStore()
    cs.start_collaboration(["a1", "a2"], "t1")
    cs.start_collaboration(["a1", "a3"], "t2")
    cs.start_collaboration(["a2", "a3"], "t3")
    a1_collabs = cs.get_agent_collaborations("a1")
    assert len(a1_collabs) == 2
    print("OK: get agent collaborations")


def test_get_active_collaborations():
    cs = AgentCollaborationStore()
    cid1 = cs.start_collaboration(["a1", "a2"], "t1")
    cs.start_collaboration(["a1", "a3"], "t2")
    cs.end_collaboration(cid1)
    active = cs.get_active_collaborations()
    assert len(active) == 1
    print("OK: get active collaborations")


def test_find_collaborators():
    cs = AgentCollaborationStore()
    cs.start_collaboration(["a1", "a2"], "t1")
    cs.start_collaboration(["a1", "a3"], "t2")
    collabs = cs.find_collaborators("a1")
    assert "a2" in collabs
    assert "a3" in collabs
    print("OK: find collaborators")


def test_list_collaborations():
    cs = AgentCollaborationStore()
    cid1 = cs.start_collaboration(["a1", "a2"], "t1")
    cs.start_collaboration(["a1", "a3"], "t2")
    cs.end_collaboration(cid1)
    all_c = cs.list_collaborations()
    assert len(all_c) == 2
    completed = cs.list_collaborations(status="completed")
    assert len(completed) == 1
    print("OK: list collaborations")


def test_get_collaboration_count():
    cs = AgentCollaborationStore()
    cs.start_collaboration(["a1", "a2"], "t1")
    cs.start_collaboration(["a1", "a3"], "t2")
    assert cs.get_collaboration_count() == 2
    assert cs.get_collaboration_count("a1") == 2
    print("OK: get collaboration count")


def test_callbacks():
    cs = AgentCollaborationStore()
    fired = []
    cs.on_change("mon", lambda a, d: fired.append(a))
    cs.start_collaboration(["a1", "a2"], "t")
    assert len(fired) >= 1
    assert cs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cs = AgentCollaborationStore()
    cs.start_collaboration(["a1", "a2"], "t")
    stats = cs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cs = AgentCollaborationStore()
    cs.start_collaboration(["a1", "a2"], "t")
    cs.reset()
    assert cs.list_collaborations() == []
    print("OK: reset")


def main():
    print("=== Agent Collaboration Store Tests ===\n")
    test_start_collaboration()
    test_end_collaboration()
    test_cancel_collaboration()
    test_get_agent_collaborations()
    test_get_active_collaborations()
    test_find_collaborators()
    test_list_collaborations()
    test_get_collaboration_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
